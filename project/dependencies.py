import json
import logging
import time
from functools import lru_cache
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from httpx import HTTPError
from jwcrypto import jwk, jwt, common
from minio import Minio
from starlette import status

from project.config import Settings, MinioBucketConfig
from project.hub import AccessToken, AuthWrapper

security = HTTPBearer()
logger = logging.getLogger(__name__)

# TODO this doesn't consider the fact that an access token may be invalidated for any reason other than expiration
_access_token: AccessToken | None = None
_access_token_retrieved_at: int


@lru_cache
def get_settings():
    return Settings()


def get_auth_jwks(settings: Annotated[Settings, Depends(get_settings)]):
    jwks_url = str(settings.oidc.certs_url)

    try:
        r = httpx.get(jwks_url)
        r.raise_for_status()
    except HTTPError:
        logger.exception("Failed to read OIDC config")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Auth provider is unavailable",
        )

    jwks_payload = r.text

    return jwk.JWKSet.from_json(jwks_payload)


def __create_minio_from_config(minio: MinioBucketConfig):
    return Minio(
        minio.endpoint,
        access_key=minio.access_key,
        secret_key=minio.secret_key,
        region=minio.region,
        secure=minio.use_ssl,
    )


def get_local_minio(
    settings: Annotated[Settings, Depends(get_settings)],
):
    return __create_minio_from_config(settings.minio)


def get_client_id(
    settings: Annotated[Settings, Depends(get_settings)],
    jwks: Annotated[jwk.JWKSet, Depends(get_auth_jwks)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
):
    try:
        token = jwt.JWT(
            jwt=credentials.credentials,
            key=jwks,
            expected_type="JWS",
            algs=["RS256"],
            check_claims={
                "iat": None,
                "exp": None,
                settings.oidc.client_id_claim_name: None,
            },
        )

        jwt_data = json.loads(token.claims)
        return jwt_data[settings.oidc.client_id_claim_name]
    except (common.JWException, ValueError):
        logger.exception("Failed to deserialize JWT")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="JWT is malformed"
        )


def __obtain_new_access_token(auth: AuthWrapper, username: str, password: str):
    global _access_token, _access_token_retrieved_at

    _access_token = auth.acquire_access_token_with_password(username, password)
    _access_token_retrieved_at = int(time.time())


def get_auth_wrapper(settings: Annotated[Settings, Depends(get_settings)]):
    return AuthWrapper(settings.hub.auth_base_url)


def get_access_token(
    settings: Annotated[Settings, Depends(get_settings)],
    auth_wrapper: Annotated[AuthWrapper, Depends(get_auth_wrapper)],
) -> AccessToken:
    global _access_token, _access_token_retrieved_at

    if _access_token is None:
        __obtain_new_access_token(
            auth_wrapper, settings.hub.auth_username, settings.hub.auth_password
        )

    # TODO configurable leeway?
    if int(time.time()) < _access_token_retrieved_at - 3600:
        __obtain_new_access_token(
            auth_wrapper, settings.hub.auth_username, settings.hub.auth_password
        )

    return _access_token
