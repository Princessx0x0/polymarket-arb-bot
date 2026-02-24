import json
import requests
import sys
sys.path.insert(0, "/home/okaforprincess32/polymarket_bot/src")
from execution.client import get_client
from py_clob_client.clob_types import OrderArgs
from py_clob_client.order_builder.constants import BUY

def execute_short(event_slug, budget_usdc=5.0, dry_run=True):
    resp = requests.get(
        "https://gamma-api.polymarket.com/events",
        params={"slug": event_slug},
        timeout=15,
    )
    events = resp.json()
    if not events:
        print(f"Event not found: {event_slug}")
        return

    event = events[0]
    markets = event.get("markets", [])
    yes_prices = []
    tradeable = []
    for m in markets:
        prices = m.get("outcomePrices", [])
        if isinstance(prices, str):
            prices = json.loads(prices)
        outcomes = m.get("outcomes", [])
        if isinstance(outcomes, str):
            outcomes = json.loads(outcomes)
        token_ids = m.get("clobTokenIds", "[]")
        if isinstance(token_ids, str):
            token_ids = json.loads(token_ids)
        yes_price = no_price = no_token = None
        for i, outcome in enumerate(outcomes):
            if outcome.lower() == "yes" and i < len(prices):
                yes_price = float(prices[i])
            if outcome.lower() == "no" and i < len(prices):
                no_price = float(prices[i])
                no_token = token_ids[i] if i < len(token_ids) else None
        if yes_price and no_price and no_token:
            yes_prices.append(yes_price)
            tradeable.append({
                "question": m.get("question","")[:50],
                "yes_price": yes_price,
                "no_price": no_price,
                "no_token": no_token,
            })

    yes_sum = sum(yes_prices)
    profit = yes_sum - 1.0
    if profit <= 0:
        print(f"No SHORT opportunity: yes_sum={yes_sum:.4f}")
        return

    title = event.get("title","")[:60]
    print(f"Event: {title}")
    print(f"YES sum: {yes_sum:.4f} | profit/dollar: {profit:.4f} | conditions: {len(tradeable)}")
    print(f"Budget: ${budget_usdc} | per condition: ${budget_usdc/len(tradeable):.4f}")
    print(f"Dry run: {dry_run}")
    print()

    if dry_run:
        for t in sorted(tradeable, key=lambda x: -x["yes_price"])[:10]:
            print(f"  WOULD BUY NO: {t['question']:50s} no_price={t['no_price']:.4f}")
        return

    client = get_client()
    per_condition = budget_usdc / len(tradeable)
    filled = 0
    for t in tradeable:
        try:
            order = client.create_and_post_order(OrderArgs(
                token_id=t["no_token"],
                price=round(t["no_price"], 4),
                size=round(per_condition / t["no_price"], 2),
                side=BUY,
            ))
            print(f"  ORDER: {t['question']:45s} @ {t['no_price']:.4f} -> {order}")
            filled += 1
        except Exception as ex:
            print(f"  FAILED: {t['question']:45s} -> {ex}")

    print(f"Filled {filled}/{len(tradeable)} orders")

if __name__ == "__main__":
    execute_short("uefa-champions-league-winner", budget_usdc=5.0, dry_run=True)
