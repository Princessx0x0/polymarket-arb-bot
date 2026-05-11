"""
Polymarket CLOB v2 client.
Handles authentication and client initialisation.
All credentials fetched from GCP Secret Manager via config.
"""
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON
from py_clob_client.clob_types import ApiCreds
from src.config import Secrets, CLOB_HOST, CHAIN_ID

_client = None

def get_client() -> ClobClient:
    """
    Returns a cached ClobClient instance.
    Initialised once per process to avoid repeated Secret Manager calls.
    """
    global _client
    if _client is None:
        _client = ClobClient(
            CLOB_HOST,
            key=Secrets.private_key(),
            chain_id=CHAIN_ID,
            creds=ApiCreds(
                api_key=Secrets.api_key(),
                api_secret=Secrets.api_secret(),
                api_passphrase=Secrets.api_passphrase(),
            ),
            signature_type=2,
            funder=Secrets.funder_address(),
        )
    return _client
