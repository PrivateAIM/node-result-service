import json
import logging
from functools import lru_cache
from typing import Annotated

import httpx
import peewee as pw
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from httpx import HTTPError
from jwcrypto import jwk, jwt, common
from minio import Minio
from starlette import status

from project import crypto
from project.config import Settings, MinioBucketConfig, AuthMethod, CryptoProvider
from project.hub import (
    FlamePasswordAuthClient,
    FlameCoreClient,
    FlameStorageClient,
    FlameRobotAuthClient,
    BaseAuthClient,
)

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
    if settings.hub.auth_method == AuthMethod.password:
        return FlamePasswordAuthClient(
            settings.hub.password_auth.username,
            settings.hub.password_auth.password,
            base_url=str(settings.hub.auth_base_url),
        )

    if settings.hub.auth_method == AuthMethod.robot:
        return FlameRobotAuthClient(
            settings.hub.robot_auth.id,
            settings.hub.robot_auth.secret,
            base_url=str(settings.hub.auth_base_url),
        )

    raise NotImplementedError(f"unknown auth method {settings.hub.auth_method}")


def get_core_client(
    settings: Annotated[Settings, Depends(get_settings)],
    auth_client: Annotated[BaseAuthClient, Depends(get_auth_client)],
):
    return FlameCoreClient(
        auth_client,
        base_url=str(settings.hub.core_base_url),
    )


def get_storage_client(
    settings: Annotated[Settings, Depends(get_settings)],
    auth_client: Annotated[BaseAuthClient, Depends(get_auth_client)],
):
    return FlameStorageClient(auth_client, base_url=str(settings.hub.storage_base_url))


def get_postgres_db(
    settings: Annotated[Settings, Depends(get_settings)],
):
    pg = settings.postgres

    return pw.PostgresqlDatabase(
        pg.db,
        user=pg.user,
        password=pg.password,
        host=pg.host,
        port=pg.port,
    )


def get_ecdh_keypair(settings: Annotated[Settings, Depends(get_settings)]):
    # settings enforce that either path or bytes are set
    if settings.crypto.provider == CryptoProvider.raw:
        return (
            crypto.load_ecdh_private_key(settings.crypto.ecdh_private_key),
            crypto.load_ecdh_public_key(settings.crypto.ecdh_public_key),
        )

    if settings.crypto.provider == CryptoProvider.file:
        return (
            crypto.load_ecdh_private_key_from_path(
                settings.crypto.ecdh_private_key_file
            ),
            crypto.load_ecdh_public_key_from_path(settings.crypto.ecdh_public_key_file),
        )

    raise ValueError(f"unknown crypto provider {settings.crypto.provider}")
