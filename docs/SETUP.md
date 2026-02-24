# Setup Guide

## Prerequisites

- Python 3.11+
- Google Cloud Platform account with billing enabled
- Polymarket account logged in via MetaMask
- USDC on Polygon network
- Telegram account

---

## 1. GCP Project Setup

Enable the following APIs in your GCP project:

- Secret Manager API
- BigQuery API
- Compute Engine API

Set IAM permissions on your VM service account:
- `Secret Manager Secret Accessor`
- `BigQuery Data Editor`

---

## 2. Clone the Repository

```bash
git clone https://github.com/Princessx0x0/polymarket-arb-bot
cd polymarket-arb-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 3. GCP Secrets

Store all credentials in GCP Secret Manager. Never hardcode them.

```bash
# From Cloud Shell or a machine with gcloud access

echo -n "YOUR_VALUE" | gcloud secrets create polymarket-private-key \
    --project=YOUR_PROJECT \
    --replication-policy=automatic \
    --data-file=-

# Repeat for each secret:
# polymarket-api-key
# polymarket-api-secret
# polymarket-api-passphrase
# telegram-bot-token
```

### Getting Polymarket API Credentials

```python
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

client = ClobClient(
    "https://clob.polymarket.com",
    key="YOUR_PRIVATE_KEY",
    chain_id=POLYGON,
    signature_type=2,
    funder="YOUR_PROXY_ADDRESS",
)
creds = client.create_or_derive_api_creds()
print(creds)
```

---

## 4. Critical Configuration

### Proxy Wallet Address

Polymarket uses a proxy wallet, NOT your MetaMask address directly.

1. Log into polymarket.com
2. Go to Account Settings
3. Copy the proxy wallet address shown there
4. Set it as `funder` in `src/execution/client.py`

### Signature Type

If you logged into Polymarket via MetaMask, set `signature_type=2` in `client.py`.

```python
return ClobClient(
    "https://clob.polymarket.com",
    key=key,
    chain_id=POLYGON,
    creds=creds,
    signature_type=2,   # MetaMask login
    funder="0xYOUR_PROXY_ADDRESS",
)
```

---

## 5. USDC on Polygon

The bot requires USDC (not USDC.e) on Polygon network.

- Contract: `0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359`
- Bridge USDC from Ethereum or buy directly on Polygon
- Deposit via the Polymarket UI using the Polygon network option

You also need to approve the Polymarket exchange contract to spend your USDC:

1. Go to [Polygonscan](https://polygonscan.com)
2. Connect your wallet
3. Find the USDC contract
4. Call `approve()` with the Polymarket exchange address and max uint256

---

## 6. VM Deployment (GCP)

### Region Selection

Polymarket has geographic restrictions. Use a region outside restricted areas:

- **Doha (me-central1)** — confirmed working as of Feb 2026
- Avoid: London, most EU regions

### Create VM

```bash
gcloud compute instances create poly-bot-doha \
    --project=YOUR_PROJECT \
    --zone=me-central1-a \
    --machine-type=e2-micro \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --scopes=cloud-platform
```

### Install Dependencies on VM

```bash
sudo apt update && sudo apt install -y python3.11 python3.11-venv git
git clone https://github.com/Princessx0x0/polymarket-arb-bot
cd polymarket-arb-bot
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 7. Run as systemd Service

```bash
sudo tee /etc/systemd/system/polymarket-telegram.service << 'EOF'
[Unit]
Description=Polymarket Telegram Bot
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/home/YOUR_USERNAME/polymarket-arb-bot
ExecStart=/home/YOUR_USERNAME/polymarket-arb-bot/venv/bin/python3 src/telegram_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable polymarket-telegram
sudo systemctl start polymarket-telegram
sudo systemctl status polymarket-telegram
```

### Check logs

```bash
sudo journalctl -u polymarket-telegram -f
```

---

## 8. Telegram Bot Setup

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the prompts
3. Copy the token provided
4. Store it in GCP Secret Manager as `telegram-bot-token`
5. Get your chat ID from **@userinfobot**
6. Set `CHAT_ID` in `src/telegram_bot.py`
