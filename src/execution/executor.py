"""
Arbitrage execution engine.
Implements 5 strategies with retry logic, structured logging,
and execution summaries. No hardcoded values.
"""
import json
import time
import requests
from datetime import datetime, timezone
from google.cloud import bigquery
from src.config import GAMMA_API, MIN_ORDER_USDC, MAX_YES_SUM_SCALE, GCP_PROJECT, BQ_DATASET
from src.logger import executor_log
from py_clob_client.clob_types import OrderArgs
from py_clob_client.order_builder.constants import BUY

# ── BigQuery ─────────────────────────────────────────────────────────────────
# Every order attempt (filled/failed/skipped) is logged here, alongside the
# scanner's `paper_trades` table, so real fills can be analysed against
# predicted opportunities instead of only living in Cloud Logging.
# Lazy, like config.py's Secret Manager client — importing this module (e.g.
# for tests) must not require live GCP credentials just to define functions.
_bq_client = None

def _get_bq():
    global _bq_client
    if _bq_client is None:
        _bq_client = bigquery.Client(project=GCP_PROJECT)
    return _bq_client

def log_fill(slug: str, strategy: int, token_id: str, price: float,
             size_usdc: float, result: str, error: str = None):
    row = {
        "ts":        datetime.now(timezone.utc).isoformat(),
        "slug":      slug,
        "strategy":  strategy,
        "token_id":  token_id,
        "price":     price,
        "size_usdc": size_usdc,
        "result":    result,
        "error":     error,
    }
    errors = _get_bq().insert_rows_json(f"{GCP_PROJECT}.{BQ_DATASET}.fills", [row])
    if errors:
        print(f"BQ fill log error: {errors}")

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
                dry_run: bool, label: str, retries: int = 1,
                slug: str = "", strategy: int = 0) -> str:
    """
    Place a single order. Returns 'filled', 'skipped', or 'failed'.
    Retries once on failure before giving up.

    `slug`/`strategy` are for BigQuery fill logging only (see log_fill) — pass
    the market slug and strategy number so real fills are queryable later.
    Dry-run "fills" are never written to BigQuery; they aren't real trades.
    """
    size = round(size_usdc / price, 2)

    if size_usdc < MIN_ORDER_USDC:
        executor_log.order_placed(label, "BUY", price, size_usdc, token_id,
                                  "skipped", "below_minimum")
        log_fill(slug, strategy, token_id, price, size_usdc, "skipped", "below_minimum")
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
            log_fill(slug, strategy, token_id, price, size_usdc, "filled")
            print(f"  FILLED: {label} @ {price:.4f} -> {order}")
            return "filled"
        except Exception as e:
            if attempt < retries:
                print(f"  RETRY ({attempt+1}): {label} -> {e}")
                time.sleep(2)
            else:
                executor_log.order_placed(label, "BUY", price, size_usdc,
                                          token_id, "failed", str(e))
                log_fill(slug, strategy, token_id, price, size_usdc, "failed", str(e))
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
        y = place_order(client, opp["yes_token"], opp["yes_price"], half, dry_run,
                        f"YES {opp['question'][:30]}", slug=slug, strategy=1)
        n = place_order(client, opp["no_token"],  opp["no_price"],  half, dry_run,
                        f"NO  {opp['question'][:30]}", slug=slug, strategy=1)
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
                             per_condition, dry_run, m["question"], slug=slug, strategy=5)
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

# ── Strategies 2 & 3: Complementary Cross-Market Pairs ───────────────────────
#
# These were referenced by telegram_bot.py's /execute2 and /execute3 but never
# implemented — every /execute* command failed on import because of it (see
# CLAUDE.md "Known gaps"). Both reduce to the same guaranteed-profit math as
# Strategy 1 (Definition 3 / footnote 6 of the paper): two YES tokens that are
# logical complements of each other should sum to $1. The only difference
# between "Mutually Exclusive" and "Contradiction Arb" is the semantic reason
# the two conditions are complements — the arbitrage math is identical, so
# they share one implementation.
#
# IMPORTANT: this is only a guaranteed arbitrage if slug_a and slug_b really
# are exhaustive AND mutually exclusive (exactly one can resolve YES). The bot
# has no way to verify that semantic relationship on its own — the paper uses
# an LLM step for exactly this reason. You are asserting the relationship by
# choosing to call this on these two slugs; verify it yourself first.

def fetch_primary_position(slug: str) -> dict | None:
    """Fetch the first parsed condition for a market slug (single-condition markets)."""
    event = fetch_event(slug)
    if not event:
        return None
    markets = parse_markets(event)
    return markets[0] if markets else None

def _execute_complementary_pair(slug_a: str, slug_b: str, budget_usdc: float,
                                 dry_run: bool, strategy_num: int, strategy_name: str):
    a = fetch_primary_position(slug_a)
    b = fetch_primary_position(slug_b)
    if not a or not b:
        print(f"Could not fetch positions for {slug_a} / {slug_b}")
        return

    total  = a["yes_price"] + b["yes_price"]
    profit = abs(1.0 - total)
    pair_slug = f"{slug_a}+{slug_b}"
    print(f"\n[Strategy {strategy_num} - {strategy_name}] {a['question'][:35]} <-> {b['question'][:35]}")
    print(f"yes_a={a['yes_price']:.4f} yes_b={b['yes_price']:.4f} | sum={total:.4f} | profit={profit*100:.2f}%")

    if profit <= 0:
        print("No opportunity")
        return

    client = None if dry_run else __import__('src.execution.client', fromlist=['get_client']).get_client()
    half = budget_usdc / 2

    # sum < 1: both YES legs are jointly underpriced, buy both (Definition 3, long).
    # sum > 1: both YES legs are jointly overpriced, buy both NO legs instead —
    # NO_a and NO_b are themselves complements of each other by the same logic
    # (A <=> not-B implies not-A <=> B), so this is the same guaranteed trade
    # mirrored onto the NO side, not a Split across two different conditions.
    if total < 1.0:
        legs = [(a["yes_token"], a["yes_price"], f"YES {a['question'][:30]}"),
                (b["yes_token"], b["yes_price"], f"YES {b['question'][:30]}")]
    else:
        legs = [(a["no_token"], a["no_price"], f"NO {a['question'][:30]}"),
                (b["no_token"], b["no_price"], f"NO {b['question'][:30]}")]

    filled = failed = skipped = 0
    for token, price, label in legs:
        r = place_order(client, token, price, half, dry_run, label,
                        slug=pair_slug, strategy=strategy_num)
        if r == "filled":   filled += 1
        elif r == "failed": failed += 1
        else:                skipped += 1

    executor_log.execution_summary(pair_slug, strategy_num, budget_usdc,
                                   filled, failed, skipped, profit * 100)
    print(f"\nSummary: {filled} filled | {failed} failed | {skipped} skipped")

    if not dry_run and (failed > 0 or skipped > 0):
        executor_log.warning(
            "INCOMPLETE_ARB — position is not fully hedged",
            slug=pair_slug, filled=filled, failed=failed, skipped=skipped
        )
    return filled

def execute_mutually_exclusive(slug_a: str, slug_b: str, budget_usdc: float = 10.0, dry_run: bool = True):
    """Strategy 2: two markets asserted to be mutually exclusive and exhaustive."""
    return _execute_complementary_pair(slug_a, slug_b, budget_usdc, dry_run, 2, "Mutually Exclusive")

def execute_contradiction_arb(slug_a: str, slug_b: str, budget_usdc: float = 10.0, dry_run: bool = True):
    """Strategy 3: two markets that are direct logical negations of each other."""
    return _execute_complementary_pair(slug_a, slug_b, budget_usdc, dry_run, 3, "Contradiction Arb")

# ── Strategy 4: One-of-Many ──────────────────────────────────────────────────
#
# Cross-market generalisation of Strategy 5 (Must-Happen): N independently
# listed single-condition markets where exactly one can resolve YES, instead
# of one grouped NegRisk event. Same math, same both-directions handling.

def execute_one_of_many(slugs: list[str], budget_usdc: float = 10.0, dry_run: bool = True):
    positions = []
    for slug in slugs:
        pos = fetch_primary_position(slug)
        if pos:
            positions.append(pos)
        else:
            print(f"Could not fetch position for {slug}, skipping")

    if len(positions) < 2:
        print(f"Need at least 2 valid markets, got {len(positions)}")
        return

    yes_sum = sum(p["yes_price"] for p in positions)
    n = len(positions)
    group_slug = ",".join(slugs)
    print(f"\n[Strategy 4 - One-of-Many] {n} markets | yes_sum={yes_sum:.4f}")

    if yes_sum == 1.0:
        print("No opportunity")
        return

    per_condition = budget_usdc / n
    client = None if dry_run else __import__('src.execution.client', fromlist=['get_client']).get_client()
    filled = failed = skipped = 0

    if yes_sum < 1.0:
        profit = 1.0 - yes_sum
        for p in positions:
            r = place_order(client, p["yes_token"], p["yes_price"], per_condition, dry_run,
                            p["question"], slug=group_slug, strategy=4)
            if r == "filled":   filled += 1
            elif r == "failed": failed += 1
            else:                skipped += 1
    else:
        profit = yes_sum - 1.0
        for p in sorted(positions, key=lambda x: -x["yes_price"]):
            r = place_order(client, p["no_token"], p["no_price"], per_condition, dry_run,
                            p["question"], slug=group_slug, strategy=4)
            if r == "filled":   filled += 1
            elif r == "failed": failed += 1
            else:                skipped += 1

    print(f"profit={profit*100:.2f}%")
    executor_log.execution_summary(group_slug, 4, budget_usdc, filled, failed, skipped, profit * 100)
    print(f"\nSummary: {filled} filled | {failed} failed | {skipped} skipped")

    if not dry_run and (failed > 0 or skipped > 0):
        executor_log.warning(
            "INCOMPLETE_ARB — position is not fully hedged",
            slug=group_slug, filled=filled, failed=failed, skipped=skipped
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
