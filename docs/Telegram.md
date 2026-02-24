# Telegram Bot Guide

The Telegram bot is the primary interface for controlling and monitoring the Polymarket Arb Bot. All commands are sent from your phone — no SSH required.

---

## Setup

1. Create a bot via **@BotFather** on Telegram
2. Send `/newbot`, follow the prompts, copy the token
3. Store token in GCP Secret Manager as `telegram-bot-token`
4. Get your chat ID from **@userinfobot**
5. Set `CHAT_ID` in `src/telegram_bot.py`

---

## Commands

### `/help`
Shows all available commands.

```
Polymarket Arb Bot Commands

/balance - Check USDC balance
/opportunities - Scan for arb opportunities
/positions - View open positions
/execute slug budget - Place trades
/status - Bot status
/help - Show this menu
```

---

### `/balance`
Checks your current USDC balance available for trading.

```
Balance

Available: $17.51 USDC
```

---

### `/opportunities`
Scans all tracked markets for live arbitrage opportunities. Takes a few seconds.

```
Scanning opportunities...

Champions League
  YES sum: 1.0140
  Profit: 1.40%
  Conditions: 39
  Status: no arb

GOP Nominee 2028
  YES sum: 1.4830
  Profit: 48.30%
  Conditions: 34
  Status: OPPORTUNITY
```

A market shows **OPPORTUNITY** when profit exceeds 2%. Below 2% is flagged as **no arb** due to execution risk from non-atomic order placement.

---

### `/positions`
Shows currently open positions with size, average price, current price, and unrealised PnL.

```
Open Positions

Will PSG win Champions League
  Size: 1.1 | Avg: 0.90 | Now: 0.905 | PnL: $0.01

Will Real Madrid win Champions League
  Size: 1.1 | Avg: 0.92 | Now: 0.925 | PnL: $0.01
```

---

### `/execute slug budget`
Places live arbitrage trades on a market. Buys NO on every condition proportionally within the budget.

**Format**: `/execute market-slug budget-in-dollars`

**Examples**:
```
/execute uefa-champions-league-winner 20
/execute republican-presidential-nominee-2028 50
/execute fed-chair-nomination 30
```

The bot will confirm execution:
```
Executing uefa-champions-league-winner with $20.0...
Execute triggered: uefa-champions-league-winner with $20.0 budget
```

**Important**: Each condition requires a minimum of $1. Make sure your budget covers `$1 × number of conditions` at minimum.

---

### `/status`
Shows the current bot health and configuration.

```
Bot Status

Scanner: running
Executor: ready
Network: Doha VM
Exchange: Polymarket CLOB
Funder: 0xf406...a03e
```

---

## Common Market Slugs

| Market | Slug |
|---|---|
| UEFA Champions League Winner | `uefa-champions-league-winner` |
| Republican Presidential Nominee 2028 | `republican-presidential-nominee-2028` |
| Fed Chair Nomination | `fed-chair-nomination` |

To find a slug for any market, go to the Polymarket event page — the slug is the last part of the URL after `/event/`.

---

## Running the Bot

```bash
# Start manually
cd ~/polymarket-arb-bot
source venv/bin/activate
python3 src/telegram_bot.py

# Start as systemd service (recommended)
sudo systemctl start polymarket-telegram

# Check status
sudo systemctl status polymarket-telegram

# View live logs
sudo journalctl -u polymarket-telegram -f
```
