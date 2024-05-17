import os


def __get_env(env_name: str, val_def: str | None = None) -> str:
    val = os.getenv(env_name, val_def)

    if val is None:
        raise ValueError(f"environment variable `{env_name}` is not set")

    return val


def hub_api_base_url():
    return __get_env("HUB__API_BASE_URL", "https://api.privateaim.net")


def hub_auth_base_url():
    return __get_env("HUB__AUTH_BASE_URL", "https://auth.privateaim.net")


def hub_auth_username():
    return __get_env("HUB__AUTH_USERNAME")


def hub_auth_password():
    return __get_env("HUB__AUTH_PASSWORD")


def oidc_certs_url():
    return __get_env("OIDC__CERTS_URL", "http://localhost:8001/.well-known/jwks.json")


def oidc_client_id_claim_name():
    return __get_env("OIDC__CLIENT_ID_CLAIM_NAME", "client_id")


def async_max_retries():
    return __get_env("ASYNC_MAX_RETRIES", "10")


def async_retry_delay_seconds():
    return __get_env("ASYNC_RETRY_DELAY_SECONDS", "1")
