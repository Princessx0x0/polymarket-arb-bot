#!/bin/bash
set -e

# Works regardless of which user runs it
BOT_DIR=$(find /home -name "polymarket_bot" -type d 2>/dev/null | head -1)

if [ -z "$BOT_DIR" ]; then
    echo "ERROR: polymarket_bot directory not found"
    exit 1
fi

echo "Deploying to: $BOT_DIR"

GCP_PROJECT=$(gcloud config get-value project 2>/dev/null || echo "polymarket-02")

git config --global --add safe.directory "$BOT_DIR"
cd "$BOT_DIR"

PAT=$(gcloud secrets versions access latest --secret=github-pat --project=${GCP_PROJECT})
git remote set-url origin "https://Princessx0x0:${PAT}@github.com/Princessx0x0/polymarket-arb-bot.git"
git pull origin main
git remote set-url origin "https://github.com/Princessx0x0/polymarket-arb-bot.git"

source venv/bin/activate
pip install -r requirements.txt -q

sudo systemctl restart polymarket-scanner
sudo systemctl restart polymarket-telegram

echo "Deployment complete - $(date)"
