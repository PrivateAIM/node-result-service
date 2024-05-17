import json
import logging
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
from project.hub import FlamePasswordAuthClient, FlameHubClient

security = HTTPBearer()
logger = logging.getLogger(__name__)


@lru_cache
def get_settings():
    return Settings()


def get_auth_jwks(settings: Annotated[Settings, Depends(get_settings)]):
    if settings.oidc.skip_jwt_validation:
        logger.warning("Since JWT validation is skipped, an empty JWKS is returned")
        return jwk.JWKSet()

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
    # TODO here be dragons!
    if settings.oidc.skip_jwt_validation:
        logger.warning(
            "JWT validation is skipped, so JWT could be signed by an untrusted party "
            "or be expired"
        )

        token = jwt.JWT(
            jwt=credentials.credentials,
            check_claims={
                settings.oidc.client_id_claim_name: None,
            },
        )

        # this hurts to write but there's no other way. token.token is an instance of JWS, and accessing
        # the payload property expects that it is validated. but it isn't since we're skipping validation.
        # so we have to access the undocumented property objects and read the payload from there.
        return json.loads(token.token.objects["payload"])[
            settings.oidc.client_id_claim_name
        ]

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


def get_auth_client(settings: Annotated[Settings, Depends(get_settings)]):
    return FlamePasswordAuthClient(
        settings.hub.auth_username,
        settings.hub.auth_password,
        base_url=str(settings.hub.auth_base_url),
    )


def get_api_client(
    settings: Annotated[Settings, Depends(get_settings)],
    auth_client: Annotated[FlamePasswordAuthClient, Depends(get_auth_client)],
):
    return FlameHubClient(
        auth_client,
        base_url=str(settings.hub.api_base_url),
    )
