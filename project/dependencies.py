import json
from functools import lru_cache
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jwcrypto import jwk, jwt, common
from minio import Minio
from starlette import status

from project.config import Settings

security = HTTPBearer()


@lru_cache
def get_settings():
    return Settings()


@lru_cache
def get_auth_jwks(settings: Annotated[Settings, Depends(get_settings)]):
    jwks_url = str(settings.oidc.certs_url)
    jwks_payload = httpx.get(jwks_url).text

    return jwk.JWKSet.from_json(jwks_payload)


def get_minio(
    settings: Annotated[Settings, Depends(get_settings)],
):
    minio = settings.minio

    return Minio(
        minio.endpoint,
        access_key=minio.access_key,
        secret_key=minio.secret_key,
        region=minio.region,
        secure=minio.use_ssl,
    )


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
    except (common.JWException, ValueError) as e:
        print(e)  # TODO log this properly
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="JWT is malformed"
        )
