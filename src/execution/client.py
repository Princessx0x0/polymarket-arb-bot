from google.cloud import secretmanager
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON
from py_clob_client.clob_types import ApiCreds

def get_secret(name):
    sm = secretmanager.SecretManagerServiceClient()
    path = f"projects/polymarket-bot-dev/secrets/{name}/versions/latest"
    return sm.access_secret_version(request={"name": path}).payload.data.decode("UTF-8").strip()

def get_client():
    key = get_secret("polymarket-private-key")
    creds = ApiCreds(
        api_key=get_secret("polymarket-api-key"),
        api_secret=get_secret("polymarket-api-secret"),
        api_passphrase=get_secret("polymarket-api-passphrase"),
    )
    return ClobClient(
        "https://clob.polymarket.com",
        key=key,
        chain_id=POLYGON,
        creds=creds,
        signature_type=2,
        funder="0xf406FE30a38a5b39C2cc2B3D392A02c851ac10E6",
    )
