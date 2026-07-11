"""
Telegram notifier for the Polymarket Arbitrage Bot.
Sends alerts, trade confirmations, and status updates.
Uses config.py for all credentials - no hardcoded values.
"""
import requests
from src.config import Secrets, TELEGRAM_CHAT_ID

CHAT_ID = TELEGRAM_CHAT_ID

def send(message: str):
    """Send a message to Telegram."""
    try:
        token = Secrets.telegram_token()
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=10
        )
        print(f"Telegram sent: {message[:50]}...")
    except Exception as e:
        print(f"Telegram error: {e}")

def notify_opportunity(title: str, profit_pct: float, conditions: int, budget: float):
    send(
        f"🎯 <b>ARB OPPORTUNITY</b>\n"
        f"📊 {title}\n"
        f"💰 Profit: {profit_pct:.1f}%\n"
        f"📋 Conditions: {conditions}\n"
        f"💵 Budget needed: ${budget:.2f}"
    )

def notify_trade_placed(title: str, filled: int, total: int, budget: float):
    emoji = "✅" if filled == total else "⚠️"
    send(
        f"{emoji} <b>ORDERS PLACED</b>\n"
        f"📊 {title}\n"
        f"🎯 Filled: {filled}/{total} orders\n"
        f"💵 Budget: ${budget:.2f}\n"
        f"{'⚠️ INCOMPLETE ARB - not fully hedged!' if filled < total else '✅ Complete arb position'}"
    )

def notify_trade_failed(title: str, error: str):
    send(
        f"❌ <b>TRADE FAILED</b>\n"
        f"📊 {title}\n"
        f"⚠️ Error: {error}"
    )

def notify_balance(balance: float):
    emoji = "✅" if balance > 10 else "⚠️"
    send(
        f"{emoji} <b>BALANCE UPDATE</b>\n"
        f"💰 Available: ${balance:.2f} USDC"
    )

def notify_startup():
    send("🤖 <b>Polymarket Arb Bot Started</b>\n🌍 Running from Johannesburg\nMonitoring for opportunities...")

def notify_service_down(service: str):
    send(
        f"🚨 <b>SERVICE DOWN</b>\n"
        f"⚠️ {service} has stopped responding\n"
        f"Check: sudo journalctl -u {service} -n 50"
    )

def notify_scan_complete(opportunities: int, top_profit: float):
    send(
        f"🔍 <b>SCAN COMPLETE</b>\n"
        f"📊 Opportunities found: {opportunities}\n"
        f"💰 Top profit: {top_profit:.1f}%"
    )
