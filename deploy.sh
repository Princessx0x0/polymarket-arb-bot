#!/bin/bash
set -e

cd /home/okaforprincess32/polymarket_bot

PAT=$(gcloud secrets versions access latest --secret=github-pat --project=polymarket-bot-dev)
git remote set-url origin https://Princessx0x0:${PAT}@github.com/Princessx0x0/polymarket-arb-bot.git
git pull origin main
git remote set-url origin https://github.com/Princessx0x0/polymarket-arb-bot.git

source venv/bin/activate
pip install -r requirements.txt -q
sudo systemctl restart polymarket-telegram
echo "Deployment complete"
