# Polymarket Arbitrage Bot

An automated arbitrage trading bot for [Polymarket](https://polymarket.com) prediction markets, deployed on Google Cloud Platform.

## What It Does

Detects and executes **Market Rebalancing Arbitrage** on Polymarket NegRisk markets — where the sum of YES prices across all conditions exceeds 1.0, guaranteeing profit by buying NO on every condition.

## Architecture
```
polymarket_bot/
├── src/
│   ├── execution/
│   │   ├── client.py        # Polymarket CLOB client (GCP Secret Manager auth)
│   │   └── executor.py      # Order placement logic
│   ├── strategy/            # Arbitrage detection
│   ├── notifier.py          # Telegram notification helpers
│   └── telegram_bot.py      # Telegram command & control interface
```

## Infrastructure

- **VM**: GCP Compute Engine, Doha region
- **Secrets**: GCP Secret Manager
- **Logging**: BigQuery
- **Process**: systemd services for 24/7 uptime
- **Network**: Polygon blockchain, USDC collateral

## Telegram Bot Commands

| Command | Description |
|---|---|
| `/balance` | Check USDC balance |
| `/opportunities` | Scan live arb opportunities |
| `/positions` | View open positions |
| `/execute slug budget` | Place trades |
| `/status` | Bot health check |
| `/help` | Show all commands |

## Setup

### Prerequisites
- Python 3.11+
- GCP project with Secret Manager, BigQuery, Compute Engine
- Polymarket account (MetaMask wallet)
- USDC on Polygon network

### Installation
```bash
git clone https://github.com/Princessx0x0/polymarket-arb-bot
cd polymarket-arb-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### GCP Secrets Required
```
polymarket-private-key
polymarket-api-key
polymarket-api-secret
polymarket-api-passphrase
telegram-bot-token
```

### Critical Configuration

The `funder` address in `client.py` must be your Polymarket **proxy wallet** from Account Settings, NOT your MetaMask address. Set `signature_type=2` for MetaMask login.

### Run
```bash
# Interactive
source venv/bin/activate
python3 src/telegram_bot.py

# 24/7 service
sudo systemctl start polymarket-telegram
sudo systemctl enable polymarket-telegram
```

## How Arbitrage Works

In a NegRisk market, if `sum(YES prices) > 1.0`, buying NO on every condition guarantees profit at resolution:
```
profit = sum(YES prices) - 1.0
```

Example: GOP Nominee 2028 YES sum = 1.483 → 48.3% guaranteed profit

## Disclaimer

For educational purposes. Execution risk exists as orders are non-atomic.
