import json
import requests
import sys
sys.path.insert(0, "/home/okaforprincess32/polymarket_bot/src")
from execution.client import get_client
from py_clob_client.clob_types import OrderArgs
from py_clob_client.order_builder.constants import BUY

GAMMA_API = "https://gamma-api.polymarket.com"
MIN_ORDER = 1.0

def fetch_event(slug):
    resp = requests.get(f"{GAMMA_API}/events", params={"slug": slug}, timeout=15)
    events = resp.json()
    return events[0] if events else None

def parse_markets(event):
    markets = []
    for m in event.get("markets", []):
        prices = m.get("outcomePrices", [])
        outcomes = m.get("outcomes", [])
        token_ids = m.get("clobTokenIds", "[]")
        if isinstance(prices, str): prices = json.loads(prices)
        if isinstance(outcomes, str): outcomes = json.loads(outcomes)
        if isinstance(token_ids, str): token_ids = json.loads(token_ids)
        yes_price = no_price = yes_token = no_token = None
        for i, outcome in enumerate(outcomes):
            if outcome.lower() == "yes" and i < len(prices):
                yes_price = float(prices[i])
                yes_token = token_ids[i] if i < len(token_ids) else None
            if outcome.lower() == "no" and i < len(prices):
                no_price = float(prices[i])
                no_token = token_ids[i] if i < len(token_ids) else None
        if yes_price and no_price:
            markets.append({
                "question": m.get("question", "")[:60],
                "yes_price": yes_price,
                "no_price": no_price,
                "yes_token": yes_token,
                "no_token": no_token,
            })
    return markets

def place_order(client, token_id, price, size_usdc, dry_run, label):
    size = round(size_usdc / price, 2)
    if size_usdc < MIN_ORDER:
        print(f"  SKIP (below min): {label} @ {price:.4f} size=${size_usdc:.2f}")
        return False
    if dry_run:
        print(f"  WOULD BUY: {label} @ {price:.4f} size={size} (${size_usdc:.2f})")
        return True
    try:
        order = client.create_and_post_order(OrderArgs(
            token_id=token_id,
            price=round(price, 4),
            size=size,
            side=BUY,
        ))
        print(f"  ORDER: {label} @ {price:.4f} -> {order}")
        return True
    except Exception as ex:
        print(f"  FAILED: {label} @ {price:.4f} -> {ex}")
        return False

def execute_basic_arb(slug, budget_usdc=10.0, dry_run=True):
    event = fetch_event(slug)
    if not event:
        print(f"Event not found: {slug}")
        return
    markets = parse_markets(event)
    opportunities = [m for m in markets if m["yes_price"] + m["no_price"] < 1.0]
    if not opportunities:
        print(f"No Basic Arb opportunity in {slug}")
        return
    print(f"\n[Strategy 1 - Basic Arb] {event.get('title','')[:60]}")
    print(f"Found {len(opportunities)} conditions")
    client = get_client() if not dry_run else None
    filled = 0
    for opp in opportunities:
        profit = 1.0 - (opp["yes_price"] + opp["no_price"])
        print(f"\n  {opp['question']} | profit={profit*100:.2f}%")
        half = budget_usdc / 2
        y = place_order(client, opp["yes_token"], opp["yes_price"], half, dry_run, "YES")
        n = place_order(client, opp["no_token"], opp["no_price"], half, dry_run, "NO")
        if y and n: filled += 1
    print(f"\nFilled {filled}/{len(opportunities)} basic arb pairs")
    return filled

def execute_mutually_exclusive(slug_a, slug_b, budget_usdc=10.0, dry_run=True):
    event_a = fetch_event(slug_a)
    event_b = fetch_event(slug_b)
    if not event_a or not event_b:
        print("One or both events not found")
        return
    m_a = parse_markets(event_a)[0]
    m_b = parse_markets(event_b)[0]
    total_cost = m_a["yes_price"] + m_b["yes_price"]
    profit = 1.0 - total_cost
    print(f"\n[Strategy 2 - Mutually Exclusive Arb]")
    print(f"  A: {event_a.get('title','')[:40]} YES @ {m_a['yes_price']:.4f}")
    print(f"  B: {event_b.get('title','')[:40]} YES @ {m_b['yes_price']:.4f}")
    print(f"  Total cost: {total_cost:.4f} | Profit: {profit*100:.2f}%")
    if profit <= 0:
        print("  No opportunity")
        return
    client = get_client() if not dry_run else None
    half = budget_usdc / 2
    place_order(client, m_a["yes_token"], m_a["yes_price"], half, dry_run, f"YES {slug_a[:20]}")
    place_order(client, m_b["yes_token"], m_b["yes_price"], half, dry_run, f"YES {slug_b[:20]}")

def execute_contradiction_arb(slug_a, slug_b, budget_usdc=10.0, dry_run=True):
    event_a = fetch_event(slug_a)
    event_b = fetch_event(slug_b)
    if not event_a or not event_b:
        print("One or both events not found")
        return
    m_a = parse_markets(event_a)[0]
    m_b = parse_markets(event_b)[0]
    cost_1 = m_a["yes_price"] + m_b["no_price"]
    cost_2 = m_a["no_price"] + m_b["yes_price"]
    print(f"\n[Strategy 3 - Contradiction Arb]")
    print(f"  Option 1 YES(A)+NO(B): {cost_1:.4f} profit={((1-cost_1)*100):.2f}%")
    print(f"  Option 2 NO(A)+YES(B): {cost_2:.4f} profit={((1-cost_2)*100):.2f}%")
    best_cost = min(cost_1, cost_2)
    if best_cost >= 1.0:
        print("  No opportunity")
        return
    client = get_client() if not dry_run else None
    half = budget_usdc / 2
    if cost_1 <= cost_2:
        place_order(client, m_a["yes_token"], m_a["yes_price"], half, dry_run, f"YES {slug_a[:20]}")
        place_order(client, m_b["no_token"], m_b["no_price"], half, dry_run, f"NO {slug_b[:20]}")
    else:
        place_order(client, m_a["no_token"], m_a["no_price"], half, dry_run, f"NO {slug_a[:20]}")
        place_order(client, m_b["yes_token"], m_b["yes_price"], half, dry_run, f"YES {slug_b[:20]}")

def execute_one_of_many(slugs, budget_usdc=10.0, dry_run=True):
    events_data = []
    for slug in slugs:
        event = fetch_event(slug)
        if not event: continue
        markets = parse_markets(event)
        if markets:
            events_data.append({"title": event.get("title","")[:40], "slug": slug, "market": markets[0]})
    if len(events_data) < 2:
        print("Need at least 2 events")
        return
    total_no = sum(e["market"]["no_price"] for e in events_data)
    profit = 1.0 - total_no
    print(f"\n[Strategy 4 - One-of-Many Arb]")
    for e in events_data:
        print(f"  NO @ {e['market']['no_price']:.4f} - {e['title']}")
    print(f"  Total NO cost: {total_no:.4f} | Profit: {profit*100:.2f}%")
    if profit <= 0:
        print("  No opportunity")
        return
    client = get_client() if not dry_run else None
    per_event = budget_usdc / len(events_data)
    filled = 0
    for e in events_data:
        m = e["market"]
        if place_order(client, m["no_token"], m["no_price"], per_event, dry_run, f"NO {e['slug'][:20]}"): filled += 1
    print(f"Filled {filled}/{len(events_data)} orders")
    return filled

def execute_must_happen(slug, budget_usdc=10.0, dry_run=True):
    event = fetch_event(slug)
    if not event:
        print(f"Event not found: {slug}")
        return
    markets = parse_markets(event)
    yes_sum = sum(m["yes_price"] for m in markets)
    profit = yes_sum - 1.0
    title = event.get("title", "")[:60]
    print(f"\n[Strategy 5 - Must-Happen Arb] {title}")
    print(f"YES sum: {yes_sum:.4f} | profit: {profit*100:.2f}% | conditions: {len(markets)}")
    if profit <= 0:
        print(f"No opportunity")
        return
    per_condition = budget_usdc / len(markets)
    client = get_client() if not dry_run else None
    filled = 0
    for m in sorted(markets, key=lambda x: -x["yes_price"]):
        if place_order(client, m["no_token"], m["no_price"], per_condition, dry_run, m["question"]): filled += 1
    print(f"\nFilled {filled}/{len(markets)} orders")
    return filled

def detect_and_execute(slug, budget_usdc=10.0, dry_run=True):
    event = fetch_event(slug)
    if not event:
        print(f"Event not found: {slug}")
        return
    markets = parse_markets(event)
    title = event.get("title","")[:60]
    if len(markets) >= 3:
        yes_sum = sum(m["yes_price"] for m in markets)
        if yes_sum > 1.0:
            print(f"Detected Strategy 5 (Must-Happen) for: {title}")
            return execute_must_happen(slug, budget_usdc, dry_run)
    for m in markets:
        if m["yes_price"] + m["no_price"] < 1.0:
            print(f"Detected Strategy 1 (Basic Arb) for: {title}")
            return execute_basic_arb(slug, budget_usdc, dry_run)
    print(f"No strategy applies to: {title}")

if __name__ == "__main__":
    execute_must_happen("uefa-champions-league-winner", budget_usdc=20.0, dry_run=True)
