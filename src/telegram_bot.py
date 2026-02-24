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
    client = get_client()
    bal = client.get_balance()
    usdc = int(bal.get("balance", 0)) / 1e6
    return f"Balance\n\nAvailable: ${usdc:.2f} USDC"

def cmd_opportunities():
    slugs = [
        ("uefa-champions-league-winner", "Champions League"),
        ("republican-presidential-nominee-2028", "GOP Nominee 2028"),
        ("fed-chair-nomination", "Fed Chair"),
    ]
    lines = ["Scanning opportunities...\n"]
    for slug, label in slugs:
        try:
            resp = requests.get(
                "https://gamma-api.polymarket.com/events",
                params={"slug": slug}, timeout=15
            )
            events = resp.json()
            if not events:
                continue
            markets = events[0].get("markets", [])
            yes_sum = 0
            count = 0
            for m in markets:
                prices = m.get("outcomePrices", [])
                if isinstance(prices, str):
                    prices = json.loads(prices)
                outcomes = m.get("outcomes", [])
                if isinstance(outcomes, str):
                    outcomes = json.loads(outcomes)
                for i, o in enumerate(outcomes):
                    if o.lower() == "yes" and i < len(prices):
                        yes_sum += float(prices[i])
                        count += 1
            profit = yes_sum - 1.0
            status = "OPPORTUNITY" if profit > 0.02 else "no arb"
            lines.append(
                f"{label}\n"
                f"  YES sum: {yes_sum:.4f}\n"
                f"  Profit: {profit*100:.2f}%\n"
                f"  Conditions: {count}\n"
                f"  Status: {status}\n"
            )
        except Exception as e:
            lines.append(f"{label}: error - {e}\n")
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

def cmd_execute(slug, budget):
    from execution.executor import execute_short
    try:
        execute_short(slug, budget_usdc=budget, dry_run=False)
        return f"Execute triggered: {slug} with ${budget} budget"
    except Exception as e:
        return f"Execute failed: {e}"

def cmd_help():
    return (
        "Polymarket Arb Bot Commands\n\n"
        "/balance - Check USDC balance\n"
        "/opportunities - Scan for arb opportunities\n"
        "/positions - View open positions\n"
        "/execute slug budget - Place trades\n"
        "  e.g. /execute uefa-champions-league-winner 20\n"
        "/status - Bot status\n"
        "/help - Show this menu"
    )

def cmd_status():
    return (
        "Bot Status\n\n"
        "Scanner: running\n"
        "Executor: ready\n"
        "Network: Doha VM\n"
        "Exchange: Polymarket CLOB\n"
        "Funder: 0xf406...a03e"
    )

def run():
    token = get_token()
    offset = 0
    print("Telegram bot polling started...")
    send(token, CHAT_ID, "Bot started. Type /help for commands.")

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
                    send(token, CHAT_ID, "Scanning... please wait.")
                    reply = cmd_opportunities()
                elif cmd == "/positions":
                    reply = cmd_positions()
                elif cmd == "/status":
                    reply = cmd_status()
                elif cmd == "/execute":
                    if len(parts) < 3:
                        reply = "Usage: /execute slug budget\ne.g. /execute uefa-champions-league-winner 20"
                    else:
                        slug = parts[1]
                        try:
                            budget = float(parts[2])
                            send(token, CHAT_ID, f"Executing {slug} with ${budget}...")
                            reply = cmd_execute(slug, budget)
                        except ValueError:
                            reply = "Budget must be a number"
                else:
                    reply = f"Unknown command: {cmd}\nType /help for commands."

                send(token, CHAT_ID, reply)

        except KeyboardInterrupt:
            print("Stopped.")
            break
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    run()
