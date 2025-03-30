import os
from google.cloud import secretmanager
from dotenv import load_dotenv
from io import StringIO

def load_env_from_secret(secret_id: str, project_id: str):
    """
    Loads environment variables from Google Secret Manager if deployed,
    otherwise falls back to .env file for local dev.
    """
    running_on_cloud_run = os.getenv("K_SERVICE") is not None

    if running_on_cloud_run:
        print(f"🔐 Loading secrets from GCP Secret Manager: {secret_id}")
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(name=name)
        secret_str = response.payload.data.decode("utf-8")
        load_dotenv(stream=StringIO(secret_str))
    else:
        print("💻 Running locally. Loading from .env")
        load_dotenv()
