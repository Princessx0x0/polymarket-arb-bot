"""
Central configuration for the Polymarket Arbitrage Bot.
All secrets fetched from GCP Secret Manager.
No hardcoded values anywhere.
"""
import os
import socket
import urllib3.util.connection as _urllib3_cn
from google.cloud import secretmanager

# ── Network ───────────────────────────────────────────────────────────────────
# poly-bot-joburg has no functional IPv6 route (link-local only — confirmed via
# `ip -6 route`), but hosts it talks to (Telegram) publish both A and AAAA
# records. Left alone, requests/urllib3 can pick the IPv6 address first and
# fail instantly with ENETUNREACH — this was the dominant cause of "Network is
# unreachable" errors against api.telegram.org (100% poll failure observed).
# Forcing IPv4 for all outbound HTTP calls sidesteps it. Nothing this bot talks
# to (Telegram, Polymarket, GCP) requires IPv6, so this is safe process-wide.
def _force_ipv4():
    return socket.AF_INET

_urllib3_cn.allowed_gai_family = _force_ipv4

# ── GCP Settings ──────────────────────────────────────────────────────────────
GCP_PROJECT = os.getenv("GCP_PROJECT", "polymarket-02")
BQ_DATASET  = os.getenv("BQ_DATASET", "polymarket")

# ── Polymarket API ────────────────────────────────────────────────────────────
CLOB_HOST   = "https://clob.polymarket.com"
GAMMA_API   = "https://gamma-api.polymarket.com"
CHAIN_ID    = 137  # Polygon mainnet

# ── Trading Settings ──────────────────────────────────────────────────────────
MIN_ORDER_USDC      = 1.0    # Minimum order size in USDC
MIN_PROFIT_PCT      = 0.02   # Minimum 2% profit to flag opportunity
SCAN_INTERVAL_SECS  = 300    # Scan every 5 minutes
MAX_YES_SUM_SCALE   = 0.03   # Per-condition threshold for false arb filter — hand-tuned
                              # (see docs/Challenges.md), not derived from the paper's
                              # VWAP+liquidity methodology. Treat as a known weak point.
NOTIFY_COOLDOWN_SECS = 1800  # Don't re-alert the same opportunity more than once per 30 min

# ── Telegram ──────────────────────────────────────────────────────────────────
# Single source of truth for the authorised chat — bot.py and notifier.py both read this.
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8264835175")

# ── Secret Manager ────────────────────────────────────────────────────────────
_sm_client = None

def _get_sm_client():
    global _sm_client
    if _sm_client is None:
        _sm_client = secretmanager.SecretManagerServiceClient()
    return _sm_client

def get_secret(name: str) -> str:
    """Fetch a secret from GCP Secret Manager."""
    client = _get_sm_client()
    path = f"projects/{GCP_PROJECT}/secrets/{name}/versions/latest"
    response = client.access_secret_version(request={"name": path})
    return response.payload.data.decode("UTF-8").strip()

# ── Cached Secrets ────────────────────────────────────────────────────────────
# Fetched once at startup, cached for the process lifetime
class Secrets:
    _cache = {}

    @classmethod
    def get(cls, name: str) -> str:
        if name not in cls._cache:
            cls._cache[name] = get_secret(name)
        return cls._cache[name]

    @classmethod
    def api_key(cls):         return cls.get("polymarket-api-key")
    @classmethod
    def api_secret(cls):      return cls.get("polymarket-api-secret")
    @classmethod
    def api_passphrase(cls):  return cls.get("polymarket-api-passphrase")
    @classmethod
    def private_key(cls):     return cls.get("polymarket-private-key")
    @classmethod
    def funder_address(cls):  return cls.get("polymarket-funder-address")
    @classmethod
    def telegram_token(cls):  return cls.get("telegram-bot-token")
    @classmethod
    def github_pat(cls):      return cls.get("github-pat")
