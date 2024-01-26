import os


def __get_env(env_name: str, val_def: str | None = None) -> str:
    val = os.getenv(env_name, val_def)

    if val is None:
        raise ValueError(f"environment variable `{env_name}` is not set")

    return val


PYTEST_OIDC_CERTS_URL = __get_env(
    "PYTEST__OIDC__CERTS_URL", "http://localhost:8001/.well-known/jwks.json"
)
PYTEST_OIDC_CLIENT_ID_CLAIM_NAME = __get_env(
    "PYTEST__OIDC__CLIENT_ID_CLAIM_NAME", "client_id"
)

PYTEST_MINIO_ENDPOINT = __get_env("PYTEST__MINIO__ENDPOINT")
PYTEST_MINIO_ACCESS_KEY = __get_env("PYTEST__MINIO__ACCESS_KEY")
PYTEST_MINIO_SECRET_KEY = __get_env("PYTEST__MINIO__SECRET_KEY")
PYTEST_MINIO_REGION = __get_env("PYTEST__MINIO__REGION", "us-east-1")
PYTEST_MINIO_BUCKET = __get_env("PYTEST__MINIO__BUCKET")
PYTEST_MINIO_USE_SSL = __get_env("PYTEST__MINIO__USE_SSL", "0")
