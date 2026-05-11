#!/bin/bash
# ── Polymarket Arbitrage Bot - Restore Script ──────────────────────────────
# Runs on a fresh GCP VM and sets up everything from scratch.
# Usage: curl -sSL https://raw.githubusercontent.com/Princessx0x0/polymarket-arb-bot/main/restore.sh | bash

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()   { echo -e "${GREEN}[+]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[x]${NC} $1"; exit 1; }

log "Starting Polymarket Bot restore..."
log "Timestamp: $(date)"

# ── System Dependencies ────────────────────────────────────────────────────
log "Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3 python3-pip python3-venv \
    git curl wget jq

# ── Detect User ────────────────────────────────────────────────────────────
BOT_USER=$(whoami)
BOT_DIR="/home/${BOT_USER}/polymarket_bot"
log "Running as: $BOT_USER"
log "Install dir: $BOT_DIR"

# ── Fetch GitHub PAT ───────────────────────────────────────────────────────
log "Fetching GitHub credentials..."
GCP_PROJECT=$(gcloud config get-value project 2>/dev/null || echo "polymarket-02")
PAT=$(gcloud secrets versions access latest \
    --secret=github-pat \
    --project=${GCP_PROJECT} 2>/dev/null) || error "Failed to fetch GitHub PAT from Secret Manager"

# ── Clone Repository ───────────────────────────────────────────────────────
if [ -d "$BOT_DIR" ]; then
    warn "Directory exists, pulling latest..."
    cd "$BOT_DIR"
    git config --global --add safe.directory "$BOT_DIR"
    git remote set-url origin "https://Princessx0x0:${PAT}@github.com/Princessx0x0/polymarket-arb-bot.git"
    git pull origin main
else
    log "Cloning repository..."
    git clone "https://Princessx0x0:${PAT}@github.com/Princessx0x0/polymarket-arb-bot.git" "$BOT_DIR"
    cd "$BOT_DIR"
fi

# Remove PAT from remote URL immediately
git remote set-url origin "https://github.com/Princessx0x0/polymarket-arb-bot.git"
log "PAT removed from git config"

# ── Python Virtual Environment ─────────────────────────────────────────────
log "Setting up Python environment..."
python3 -m venv "${BOT_DIR}/venv"
source "${BOT_DIR}/venv/bin/activate"
pip install --upgrade pip -q
pip install -r "${BOT_DIR}/requirements.txt" -q
log "Python dependencies installed"

# ── Environment File ───────────────────────────────────────────────────────
log "Writing environment config..."
cat > "${BOT_DIR}/.env" << ENVEOF
GCP_PROJECT=${GCP_PROJECT}
BQ_DATASET=polymarket
ENVEOF
chmod 600 "${BOT_DIR}/.env"

# ── Systemd Services ───────────────────────────────────────────────────────
log "Installing systemd services..."

sudo tee /etc/systemd/system/polymarket-scanner.service > /dev/null << SVCEOF
[Unit]
Description=Polymarket Opportunity Scanner
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=${BOT_USER}
WorkingDirectory=${BOT_DIR}
Environment=GCP_PROJECT=${GCP_PROJECT}
ExecStart=${BOT_DIR}/venv/bin/python3 -m src.scanner
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SVCEOF

sudo tee /etc/systemd/system/polymarket-telegram.service > /dev/null << SVCEOF
[Unit]
Description=Polymarket Telegram Bot
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=${BOT_USER}
WorkingDirectory=${BOT_DIR}
Environment=GCP_PROJECT=${GCP_PROJECT}
ExecStart=${BOT_DIR}/venv/bin/python3 -m src.telegram_bot
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SVCEOF

sudo systemctl daemon-reload
sudo systemctl enable polymarket-scanner polymarket-telegram
sudo systemctl restart polymarket-scanner polymarket-telegram
log "Services installed and started"

# ── OS Hardening ───────────────────────────────────────────────────────────
log "Applying security hardening..."

# SSH hardening
sudo sed -i 's/#PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sudo sed -i 's/#PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo sed -i 's/#X11Forwarding.*/X11Forwarding no/' /etc/ssh/sshd_config
echo "MaxAuthTries 3" | sudo tee -a /etc/ssh/sshd_config > /dev/null
echo "LoginGraceTime 20" | sudo tee -a /etc/ssh/sshd_config > /dev/null
sudo systemctl restart sshd

# Kernel hardening
sudo tee /etc/sysctl.d/99-polymarket.conf > /dev/null << KERNEOF
net.ipv4.tcp_syncookies = 1
net.ipv4.ip_forward = 0
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.all.accept_source_route = 0
kernel.randomize_va_space = 2
KERNEOF
sudo sysctl -p /etc/sysctl.d/99-polymarket.conf > /dev/null
log "Security hardening applied"

# ── Verify ─────────────────────────────────────────────────────────────────
log "Verifying deployment..."
sleep 5

SCANNER_STATUS=$(systemctl is-active polymarket-scanner)
BOT_STATUS=$(systemctl is-active polymarket-telegram)

echo ""
echo "══════════════════════════════════════"
echo "  Polymarket Bot - Restore Complete"
echo "══════════════════════════════════════"
echo "  User:     $BOT_USER"
echo "  Dir:      $BOT_DIR"
echo "  Project:  $GCP_PROJECT"
echo "  Scanner:  $SCANNER_STATUS"
echo "  Bot:      $BOT_STATUS"
echo "══════════════════════════════════════"
echo ""

if [ "$SCANNER_STATUS" = "active" ] && [ "$BOT_STATUS" = "active" ]; then
    log "Both services running. Bot is live!"
else
    warn "One or more services not running. Check: sudo journalctl -u polymarket-scanner -n 50"
fi
