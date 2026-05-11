#!/bin/bash
set -e

BOT_DIR=$(find /home -name "polymarket_bot" -type d 2>/dev/null | head -1)
[[ -z "$BOT_DIR" ]] && echo "ERROR: polymarket_bot not found" && exit 1

echo "Deploying to: $BOT_DIR"
GCP_PROJECT=$(gcloud config get-value project 2>/dev/null || echo "polymarket-02")

git config --global --add safe.directory "$BOT_DIR"
cd "$BOT_DIR"

PAT=$(gcloud secrets versions access latest --secret=github-pat --project=${GCP_PROJECT})
git remote set-url origin "https://Princessx0x0:${PAT}@github.com/Princessx0x0/polymarket-arb-bot.git"

# Force reset - always match GitHub exactly, no conflicts ever
git fetch origin main
git reset --hard origin/main
git clean -fd

git remote set-url origin "https://github.com/Princessx0x0/polymarket-arb-bot.git"

source venv/bin/activate
pip install -r requirements.txt -q

sudo systemctl restart polymarket-scanner
sudo systemctl restart polymarket-telegram

echo "Deployment complete - $(date)"
