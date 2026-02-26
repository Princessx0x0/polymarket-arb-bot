import json
import time
import asyncio
import websockets
import requests
from datetime import datetime, timezone
from google.cloud import bigquery

PROJECT = "polymarket-bot-dev"
DATASET = "polymarket"
BQ = bigquery.Client(project=PROJECT)

def fetch_all_negrisk_events():
    events = []
    offset = 0
    limit = 100
    print("Fetching all active NegRisk markets...")
    while True:
        try:
            resp = requests.get(
                "https://gamma-api.polymarket.com/events",
                params={"active": "true", "closed": "false", "limit": limit, "offset": offset},
                timeout=15
            )
            batch = resp.json()
            if not batch:
                break
            for e in batch:
                if len(e.get("markets", [])) >= 3 and e.get("negRisk", False):
                    events.append(e)
            offset += limit
            if len(batch) < limit:
                break
            time.sleep(0.2)
        except Exception as ex:
            print(f"Error at offset {offset}: {ex}")
            break
    print(f"Found {len(events)} valid NegRisk events")
    return events

def analyse_event(event):
    markets = event.get("markets", [])
    yes_prices = []
    token_ids = []
    for m in markets:
        prices = m.get("outcomePrices", [])
        outcomes = m.get("outcomes", [])
        tids = m.get("clobTokenIds", "[]")
        if isinstance(prices, str): prices = json.loads(prices)
        if isinstance(outcomes, str): outcomes = json.loads(outcomes)
        if isinstance(tids, str): tids = json.loads(tids)
        for i, o in enumerate(outcomes):
            if o.lower() == "yes" and i < len(prices):
                yes_prices.append(float(prices[i]))
                if i < len(tids):
                    token_ids.append(tids[i])
    if not yes_prices:
        return None
    yes_sum = sum(yes_prices)
    return {
        "slug": event.get("slug", ""),
        "title": event.get("title", "")[:60],
        "yes_sum": yes_sum,
        "profit": yes_sum - 1.0,
        "conditions": len(yes_prices),
        "token_ids": token_ids,
        "volume": float(event.get("volume24hr", 0) or 0),
    }

def log_opportunity(data):
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event_title": data["title"],
        "event_slug": data["slug"],
        "direction": "SHORT",
        "yes_sum": data["yes_sum"],
        "profit_per_dollar": data["profit"],
        "num_conditions": data["conditions"],
        "volume_24hr": data["volume"],
    }
    errors = BQ.insert_rows_json(f"{PROJECT}.{DATASET}.paper_trades", [row])
    if errors:
        print(f"BQ error: {errors}")

def log_tick(market_id, price, raw):
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "market_id": market_id,
        "price": price,
        "raw": json.dumps(raw),
    }
    errors = BQ.insert_rows_json(f"{PROJECT}.{DATASET}.market_ticks_v2", [row])
    if errors:
        print(f"BQ tick error: {errors}")

def scan_all():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Scanning all NegRisk markets...")
    events = fetch_all_negrisk_events()
    opportunities = []
    for event in events:
        data = analyse_event(event)
        if not data:
            continue
        if data["profit"] > 0:
            log_opportunity(data)
            opportunities.append(data)
            if data["profit"] > 0.02:
                print(f"  OPPORTUNITY: {data['title'][:40]} | profit={data['profit']*100:.2f}% | conditions={data['conditions']}")
    print(f"Scan complete: {len(opportunities)} opportunities from {len(events)} NegRisk markets")
    return opportunities

async def stream_tokens(token_ids, duration=270):
    if not token_ids:
        return
    uri = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    try:
        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps({
                "type": "subscribe",
                "channel": "market",
                "assets_ids": token_ids
            }))
            print(f"Streaming {len(token_ids)} tokens for {duration}s...")
            async def listen():
                async for message in ws:
                    try:
                        data = json.loads(message)
                        if isinstance(data, list):
                            for tick in data:
                                price = tick.get("price")
                                asset = tick.get("asset_id", "")
                                if price and asset:
                                    log_tick(asset, float(price), tick)
                    except Exception as e:
                        print(f"Tick error: {e}")
            await asyncio.wait_for(listen(), timeout=duration)
    except asyncio.TimeoutError:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")

async def run_scanner():
    print("Scanner starting - monitoring all Polymarket NegRisk events")
    while True:
        opportunities = scan_all()
        top_tokens = []
        for opp in sorted(opportunities, key=lambda x: -x["profit"])[:10]:
            top_tokens.extend(opp["token_ids"][:3])
        if top_tokens:
            await stream_tokens(top_tokens[:20], duration=270)
        else:
            await asyncio.sleep(270)

if __name__ == "__main__":
    asyncio.run(run_scanner())
