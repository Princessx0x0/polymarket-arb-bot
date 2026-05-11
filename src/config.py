"""
Central configuration for the Polymarket Arbitrage Bot.
All secrets fetched from GCP Secret Manager.
No hardcoded values anywhere.
"""
import os
from google.cloud import secretmanager

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
MAX_YES_SUM_SCALE   = 0.03   # Per-condition threshold for false arb filter

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
