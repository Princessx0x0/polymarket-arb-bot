import requests
from google.cloud import secretmanager

CHAT_ID = "8264835175"

def get_secret(name):
    sm = secretmanager.SecretManagerServiceClient()
    path = f"projects/polymarket-bot-dev/secrets/{name}/versions/latest"
    return sm.access_secret_version(request={"name": path}).payload.data.decode("UTF-8").strip()

def send(message):
    try:
        token = get_secret("telegram-bot-token")
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=10
        )
        print(f"Telegram sent: {message[:50]}...")
    except Exception as e:
        print(f"Telegram error: {e}")

def notify_opportunity(title, profit_pct, conditions, budget):
    send(
        f"🎯 <b>ARB OPPORTUNITY</b>\n"
        f"📊 {title}\n"
        f"💰 Profit: {profit_pct:.1f}%\n"
        f"📋 Conditions: {conditions}\n"
        f"💵 Budget needed: ${budget:.2f}"
    )

def notify_trade_placed(title, filled, total, budget):
    send(
        f"✅ <b>ORDERS PLACED</b>\n"
        f"📊 {title}\n"
        f"🎯 Filled: {filled}/{total} orders\n"
        f"💵 Budget: ${budget:.2f}"
    )

def notify_trade_failed(title, error):
    send(
        f"❌ <b>TRADE FAILED</b>\n"
        f"📊 {title}\n"
        f"⚠️ Error: {error}"
    )

def notify_balance(balance):
    emoji = "✅" if balance > 10 else "⚠️"
    send(
        f"{emoji} <b>BALANCE UPDATE</b>\n"
        f"💰 Available: ${balance:.2f}"
    )

def notify_startup():
    send("🤖 <b>Polymarket Arb Bot Started</b>\nMonitoring for opportunities...")
