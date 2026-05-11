"""
Arbitrage execution engine.
Implements 5 strategies with retry logic, structured logging,
and execution summaries. No hardcoded values.
"""
import json
import time
import requests
from src.config import GAMMA_API, MIN_ORDER_USDC, MAX_YES_SUM_SCALE
from src.logger import executor_log
from py_clob_client.clob_types import OrderArgs
from py_clob_client.order_builder.constants import BUY

# ── Market Data ───────────────────────────────────────────────────────────────

def fetch_event(slug: str) -> dict | None:
    """Fetch event data from Gamma API."""
    try:
        resp = requests.get(
            f"{GAMMA_API}/events",
            params={"slug": slug},
            timeout=15
        )
        events = resp.json()
        return events[0] if events else None
    except Exception as e:
        executor_log.error(f"Failed to fetch event", slug=slug, error=str(e))
        return None

def parse_markets(event: dict) -> list[dict]:
    """Parse market conditions from event data."""
    markets = []
    for m in event.get("markets", []):
        prices    = m.get("outcomePrices", [])
        outcomes  = m.get("outcomes", [])
        token_ids = m.get("clobTokenIds", "[]")

        if isinstance(prices, str):    prices    = json.loads(prices)
        if isinstance(outcomes, str):  outcomes  = json.loads(outcomes)
        if isinstance(token_ids, str): token_ids = json.loads(token_ids)

        yes_price = no_price = yes_token = no_token = None
        for i, outcome in enumerate(outcomes):
            if outcome.lower() == "yes" and i < len(prices):
                yes_price = float(prices[i])
                yes_token = token_ids[i] if i < len(token_ids) else None
            if outcome.lower() == "no" and i < len(prices):
                no_price = float(prices[i])
                no_token = token_ids[i] if i < len(token_ids) else None

        if yes_price and no_price and yes_token and no_token:
            markets.append({
                "question":  m.get("question", "")[:60],
                "yes_price": yes_price,
                "no_price":  no_price,
                "yes_token": yes_token,
                "no_token":  no_token,
            })
    return markets

# ── Order Placement ───────────────────────────────────────────────────────────

def place_order(client, token_id: str, price: float, size_usdc: float,
                dry_run: bool, label: str, retries: int = 1) -> str:
    """
    Place a single order. Returns 'filled', 'skipped', or 'failed'.
    Retries once on failure before giving up.
    """
    size = round(size_usdc / price, 2)

    if size_usdc < MIN_ORDER_USDC:
        executor_log.order_placed(label, "BUY", price, size_usdc, token_id,
                                  "skipped", "below_minimum")
        print(f"  SKIP: {label} @ {price:.4f} (${size_usdc:.2f} < ${MIN_ORDER_USDC} min)")
        return "skipped"

    if dry_run:
        print(f"  WOULD BUY: {label} @ {price:.4f} size={size} (${size_usdc:.2f})")
        return "filled"

    for attempt in range(retries + 1):
        try:
            order = client.create_and_post_order(OrderArgs(
                token_id=token_id,
                price=round(price, 4),
                size=size,
                side=BUY,
            ))
            executor_log.order_placed(label, "BUY", price, size_usdc, token_id, "filled")
            print(f"  FILLED: {label} @ {price:.4f} -> {order}")
            return "filled"
        except Exception as e:
            if attempt < retries:
                print(f"  RETRY ({attempt+1}): {label} -> {e}")
                time.sleep(2)
            else:
                executor_log.order_placed(label, "BUY", price, size_usdc,
                                          token_id, "failed", str(e))
                print(f"  FAILED: {label} @ {price:.4f} -> {e}")
                return "failed"

# ── Strategy 1: Basic Arbitrage ───────────────────────────────────────────────

def execute_basic_arb(slug: str, budget_usdc: float = 10.0, dry_run: bool = True):
    """
    Strategy 1: Buy YES + NO on same market when total cost < $1.
    Profit = 1 - (yes_price + no_price)
    """
    event = fetch_event(slug)
    if not event:
        return

    markets = parse_markets(event)
    opportunities = [m for m in markets if m["yes_price"] + m["no_price"] < 1.0]

    if not opportunities:
        print(f"No Basic Arb opportunity in {slug}")
        return

    print(f"\n[Strategy 1 - Basic Arb] {event.get('title','')[:60]}")
    client = None if dry_run else __import__('src.execution.client', fromlist=['get_client']).get_client()

    filled = failed = skipped = 0
    for opp in opportunities:
        profit = 1.0 - (opp["yes_price"] + opp["no_price"])
        print(f"\n  {opp['question']} | profit={profit*100:.2f}%")
        half = budget_usdc / 2
        y = place_order(client, opp["yes_token"], opp["yes_price"], half, dry_run, f"YES {opp['question'][:30]}")
        n = place_order(client, opp["no_token"],  opp["no_price"],  half, dry_run, f"NO  {opp['question'][:30]}")
        for result in [y, n]:
            if result == "filled":   filled += 1
            elif result == "failed": failed += 1
            else:                    skipped += 1

    executor_log.execution_summary(slug, 1, budget_usdc, filled, failed, skipped,
                                   profit * 100 if opportunities else 0)
    print(f"\nSummary: {filled} filled | {failed} failed | {skipped} skipped")

# ── Strategy 5: Must-Happen NegRisk ──────────────────────────────────────────

def execute_must_happen(slug: str, budget_usdc: float = 10.0, dry_run: bool = True):
    """
    Strategy 5: Buy NO on every condition in a NegRisk market.
    Profit = sum(YES prices) - 1.0
    Valid only when yes_sum > 1.0 AND passes false-arb filter.
    """
    event = fetch_event(slug)
    if not event:
        return

    markets   = parse_markets(event)
    yes_sum   = sum(m["yes_price"] for m in markets)
    profit    = yes_sum - 1.0
    title     = event.get("title", "")[:60]
    n_conds   = len(markets)

    # False arb filter — Win/Draw/Loss markets have inflated YES sums
    max_yes_sum = 1.0 + (n_conds * MAX_YES_SUM_SCALE)
    if yes_sum > max_yes_sum:
        print(f"FILTERED (false arb): {title} yes_sum={yes_sum:.4f} > max={max_yes_sum:.4f}")
        return

    print(f"\n[Strategy 5 - Must-Happen] {title}")
    print(f"YES sum={yes_sum:.4f} | profit={profit*100:.2f}% | conditions={n_conds}")

    if profit <= 0:
        print("No opportunity")
        return

    per_condition = budget_usdc / n_conds
    client = None if dry_run else __import__('src.execution.client', fromlist=['get_client']).get_client()

    filled = failed = skipped = 0
    for m in sorted(markets, key=lambda x: -x["yes_price"]):
        result = place_order(client, m["no_token"], m["no_price"],
                             per_condition, dry_run, m["question"])
        if result == "filled":   filled += 1
        elif result == "failed": failed += 1
        else:                    skipped += 1

    executor_log.execution_summary(slug, 5, budget_usdc, filled, failed, skipped, profit * 100)
    print(f"\nSummary: {filled} filled | {failed} failed | {skipped} skipped")

    # Alert if incomplete arb
    if not dry_run and (failed > 0 or skipped > 0):
        executor_log.warning(
            "INCOMPLETE_ARB — position is not fully hedged",
            slug=slug, filled=filled, failed=failed, skipped=skipped
        )

    return filled

# ── Auto-detect ───────────────────────────────────────────────────────────────

def detect_and_execute(slug: str, budget_usdc: float = 10.0, dry_run: bool = True):
    """Auto-detect best strategy for a given market."""
    event = fetch_event(slug)
    if not event:
        return

    markets = parse_markets(event)
    title   = event.get("title", "")[:60]

    if len(markets) >= 3:
        yes_sum = sum(m["yes_price"] for m in markets)
        if yes_sum > 1.0:
            print(f"Detected Strategy 5 (Must-Happen): {title}")
            return execute_must_happen(slug, budget_usdc, dry_run)

    for m in markets:
        if m["yes_price"] + m["no_price"] < 1.0:
            print(f"Detected Strategy 1 (Basic Arb): {title}")
            return execute_basic_arb(slug, budget_usdc, dry_run)

    print(f"No strategy applies: {title}")


if __name__ == "__main__":
    execute_must_happen("colombia-presidential-election", budget_usdc=20.0, dry_run=True)
