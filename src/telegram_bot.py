import json
import time
import requests
import sys
sys.path.insert(0, "/home/okaforprincess32/polymarket_bot/src")

from google.cloud import secretmanager

CHAT_ID = "8264835175"
PROJECT = "polymarket-bot-dev"

def get_secret(name):
    sm = secretmanager.SecretManagerServiceClient()
    path = f"projects/{PROJECT}/secrets/{name}/versions/latest"
    return sm.access_secret_version(request={"name": path}).payload.data.decode("UTF-8").strip()

def get_token():
    return get_secret("telegram-bot-token")

def send(token, chat_id, text):
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        timeout=10
    )

def cmd_balance():
    from execution.client import get_client
    from py_clob_client.clob_types import AssetType, BalanceAllowanceParams
    client = get_client()
    bal = client.get_balance_allowance(params=BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
    usdc = int(bal.get("balance", 0)) / 1e6
    return f"Balance\n\nAvailable: ${usdc:.2f} USDC"

def cmd_opportunities():
    from execution.executor import fetch_event, parse_markets
    try:
        resp = requests.get(
            "https://gamma-api.polymarket.com/events",
            params={"active": "true", "closed": "false", "limit": 100},
            timeout=15
        )
        events = resp.json()
    except Exception as e:
        return f"Error fetching markets: {e}"

    lines = ["Market Scan\n"]
    opportunities = []
    for event in events:
        markets = event.get("markets", [])
        if len(markets) < 3:
            continue
        if not event.get('negRisk', False):
            continue
        yes_prices = []
        for m in markets:
            prices = m.get("outcomePrices", [])
            outcomes = m.get("outcomes", [])
            if isinstance(prices, str): prices = json.loads(prices)
            if isinstance(outcomes, str): outcomes = json.loads(outcomes)
            for i, o in enumerate(outcomes):
                if o.lower() == "yes" and i < len(prices):
                    yes_prices.append(float(prices[i]))
        if not yes_prices:
            continue
        yes_sum = sum(yes_prices)
        profit = yes_sum - 1.0
        # Filter fake arb - valid NegRisk yes_sum scales with conditions
        max_yes_sum = 1.0 + (len(yes_prices) * 0.03)
        if yes_sum > max_yes_sum:
            continue
        if profit > 0.02:
            opportunities.append({
                "title": event.get("title", "")[:40],
                "slug": event.get("slug", ""),
                "profit": profit,
                "conditions": len(yes_prices),
                "yes_sum": yes_sum,
            })

    if not opportunities:
        lines.append("No opportunities above 2% found.")
    else:
        opportunities.sort(key=lambda x: -x["profit"])
        for o in opportunities[:10]:
            lines.append(
                f"{o['title']}\n"
                f"  Profit: {o['profit']*100:.2f}% | Conditions: {o['conditions']}\n"
                f"  Slug: {o['slug']}\n"
            )
    return "\n".join(lines)

def cmd_positions():
    from execution.client import get_client
    client = get_client()
    try:
        positions = client.get_positions()
        if not positions:
            return "No open positions."
        lines = ["Open Positions\n"]
        for p in positions[:10]:
            asset = p.get("asset", "")[:30]
            size = p.get("size", 0)
            avg = p.get("avgPrice", 0)
            cur = p.get("curPrice", 0)
            pnl = (float(cur) - float(avg)) * float(size)
            lines.append(f"{asset}\n  Size: {size} | Avg: {avg} | Now: {cur} | PnL: ${pnl:.2f}\n")
        return "\n".join(lines)
    except Exception as e:
        return f"Could not fetch positions: {e}"

def cmd_execute(parts):
    """
    /execute5 slug budget          - Must-Happen Arb
    /execute1 slug budget          - Basic Arb
    /execute2 slug_a slug_b budget - Mutually Exclusive
    /execute3 slug_a slug_b budget - Contradiction Arb
    /execute4 slug1 slug2 slug3 budget - One-of-Many
    /execute slug budget           - Auto-detect
    """
    from execution.executor import (
        execute_must_happen, execute_basic_arb,
        execute_mutually_exclusive, execute_contradiction_arb,
        execute_one_of_many, detect_and_execute
    )

    cmd = parts[0].lower()

    try:
        if cmd == "/execute" or cmd == "/execute5":
            if len(parts) < 3:
                return "Usage: /execute slug budget\ne.g. /execute uefa-champions-league-winner 20"
            slug, budget = parts[1], float(parts[2])
            if cmd == "/execute5":
                execute_must_happen(slug, budget, dry_run=False)
            else:
                detect_and_execute(slug, budget, dry_run=False)
            return f"Strategy executed: {slug} ${budget}"

        elif cmd == "/execute1":
            if len(parts) < 3:
                return "Usage: /execute1 slug budget"
            execute_basic_arb(parts[1], float(parts[2]), dry_run=False)
            return f"Basic Arb executed: {parts[1]}"

        elif cmd == "/execute2":
            if len(parts) < 4:
                return "Usage: /execute2 slug_a slug_b budget"
            execute_mutually_exclusive(parts[1], parts[2], float(parts[3]), dry_run=False)
            return f"Mutually Exclusive Arb executed"

        elif cmd == "/execute3":
            if len(parts) < 4:
                return "Usage: /execute3 slug_a slug_b budget"
            execute_contradiction_arb(parts[1], parts[2], float(parts[3]), dry_run=False)
            return f"Contradiction Arb executed"

        elif cmd == "/execute4":
            if len(parts) < 4:
                return "Usage: /execute4 slug1 slug2 ... budget"
            slugs = parts[1:-1]
            budget = float(parts[-1])
            execute_one_of_many(slugs, budget, dry_run=False)
            return f"One-of-Many Arb executed: {len(slugs)} markets"

    except Exception as e:
        return f"Execute failed: {e}"

def cmd_help():
    return (
        "Polymarket Arb Bot\n\n"
        "MONITORING\n"
        "/balance - Check USDC balance\n"
        "/opportunities - Scan all markets\n"
        "/positions - View open positions\n"
        "/status - Bot health\n\n"
        "EXECUTION\n"
        "/execute slug budget - Auto-detect strategy\n"
        "/execute1 slug budget - Basic Arb (YES+NO)\n"
        "/execute2 a b budget - Mutually Exclusive\n"
        "/execute3 a b budget - Contradiction Arb\n"
        "/execute4 a b c budget - One-of-Many\n"
        "/execute5 slug budget - Must-Happen (NegRisk)\n\n"
        "EXAMPLES\n"
        "/execute5 uefa-champions-league-winner 20\n"
        "/execute2 slug-a slug-b 10\n"
    )

def cmd_status():
    return (
        "Bot Status\n\n"
        "Telegram: online\n"
        "Strategies: 1-5 loaded\n"
        "Network: Doha VM\n"
        "Exchange: Polymarket CLOB\n"
        "Funder: 0xf406...a03e"
    )

def run():
    token = get_token()
    offset = 0
    print("Telegram bot polling started...")
    send(token, CHAT_ID, "Bot restarted. Type /help for commands.")

    while True:
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=35
            )
            updates = resp.json().get("result", [])
            for update in updates:
                offset = update["update_id"] + 1
                msg = update.get("message", {})
                chat_id = str(msg.get("chat", {}).get("id", ""))
                text = msg.get("text", "").strip()

                if chat_id != CHAT_ID:
                    continue

                print(f"Command: {text}")
                parts = text.split()
                cmd = parts[0].lower() if parts else ""

                if cmd in ("/help", "/start"):
                    reply = cmd_help()
                elif cmd == "/balance":
                    reply = cmd_balance()
                elif cmd == "/opportunities":
                    send(token, CHAT_ID, "Scanning all markets... please wait.")
                    reply = cmd_opportunities()
                elif cmd == "/positions":
                    reply = cmd_positions()
                elif cmd == "/status":
                    reply = cmd_status()
                elif cmd in ("/execute", "/execute1", "/execute2", "/execute3", "/execute4", "/execute5"):
                    send(token, CHAT_ID, f"Executing {cmd}...")
                    reply = cmd_execute(parts)
                else:
                    reply = f"Unknown command: {cmd}\nType /help"

                send(token, CHAT_ID, reply)

        except KeyboardInterrupt:
            print("Stopped.")
            break
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    run()
