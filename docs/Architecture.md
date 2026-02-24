# Architecture

## Overview

The bot runs as a persistent service on a GCP VM, connecting to Polymarket's CLOB API to detect and execute arbitrage opportunities. All control and monitoring is done via Telegram.

```
┌─────────────────────────────────────────────────────┐
│                    Your Phone                        │
│                 Telegram App                         │
│         /opportunities  /balance  /execute           │
└──────────────────────┬──────────────────────────────┘
                       │ HTTPS
┌──────────────────────▼──────────────────────────────┐
│              GCP VM (Doha, Qatar)                    │
│                                                      │
│  ┌─────────────────────────────────────────────┐    │
│  │           telegram_bot.py                    │    │
│  │      Command router + polling loop           │    │
│  └──────┬──────────────────────┬───────────────┘    │
│         │                      │                     │
│  ┌──────▼──────┐      ┌───────▼───────┐             │
│  │ executor.py │      │  notifier.py  │             │
│  │ Place orders│      │ Send alerts   │             │
│  └──────┬──────┘      └───────────────┘             │
│         │                                            │
│  ┌──────▼──────┐                                    │
│  │  client.py  │                                    │
│  │ CLOB client │                                    │
│  └──────┬──────┘                                    │
│         │                                            │
│  ┌──────▼──────────────┐                            │
│  │  GCP Secret Manager │                            │
│  │  - private key      │                            │
│  │  - api credentials  │                            │
│  │  - telegram token   │                            │
│  └─────────────────────┘                            │
└──────────────────────┬──────────────────────────────┘
                       │ HTTPS
┌──────────────────────▼──────────────────────────────┐
│            Polymarket CLOB API                       │
│         clob.polymarket.com                          │
│                                                      │
│   Gamma API (market data)                            │
│   gamma-api.polymarket.com                           │
└──────────────────────┬──────────────────────────────┘
                       │ on-chain settlement
┌──────────────────────▼──────────────────────────────┐
│              Polygon Blockchain                      │
│         USDC conditional tokens                     │
└─────────────────────────────────────────────────────┘
```

---

## Components

### `src/execution/client.py`
Initialises the Polymarket CLOB client using credentials from GCP Secret Manager. Handles authentication with `signature_type=2` (MetaMask) and the proxy funder address.

### `src/execution/executor.py`
Core trading logic. Given an event slug and budget:
1. Fetches all conditions from Gamma API
2. Calculates YES sum to confirm arbitrage exists
3. Places BUY NO orders for each condition proportionally

### `src/notifier.py`
Sends formatted messages to Telegram. Used by other modules to push alerts for opportunities, trade fills, failures, and balance updates.

### `src/telegram_bot.py`
Long-polling Telegram bot that acts as the command interface. Receives commands from the authorised chat ID only, routes them to the appropriate module, and returns results.

### `src/strategy/`
Expanding module for arbitrage detection logic. Currently opportunity scanning is embedded in executor and telegram_bot. Will be refactored here as strategy types grow.

---

## Data Flow

### Opportunity Scan (`/opportunities`)
```
Telegram → telegram_bot.py → Gamma API (fetch markets)
         → calculate YES sum per market
         → return results to Telegram
```

### Trade Execution (`/execute slug budget`)
```
Telegram → telegram_bot.py → executor.py → Gamma API (fetch conditions)
         → client.py (authenticate via Secret Manager)
         → Polymarket CLOB API (post orders)
         → Polygon blockchain (settlement)
         → return fill results to Telegram
```

---

## Infrastructure

| Component | Service | Details |
|---|---|---|
| Compute | GCP Compute Engine | e2-micro, Doha (me-central1) |
| Secrets | GCP Secret Manager | 5 secrets, accessed at runtime |
| Logging | GCP BigQuery | Paper trading logs, scan history |
| Process | systemd | Auto-restart, starts on boot |
| Blockchain | Polygon | USDC collateral, conditional tokens |
| Exchange | Polymarket CLOB | Hybrid centralised/on-chain order book |

---

## Security

- No secrets in code or environment variables — all fetched from Secret Manager at runtime
- Telegram bot only responds to the authorised `CHAT_ID`
- VM service account has minimum required permissions (Secret Accessor, BigQuery Editor)
- Private key never leaves Secret Manager
