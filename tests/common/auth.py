import os
from datetime import timedelta, datetime, timezone
from functools import lru_cache
from typing import Any
from uuid import UUID

import httpx
from httpx import Request
from jwcrypto import jwk, jwt

from tests.common import env


@lru_cache()
def get_oid_test_jwk() -> jwk.JWK:
    with open(
        os.path.join(os.path.dirname(__file__), "..", "assets", "keypair.pem"), "rb"
    ) as f:
        oid_jwk = jwk.JWK()
        oid_jwk.import_from_pem(f.read())
        oid_jwk["use"] = "sig"

    return oid_jwk


def issue_access_token(
    claims: dict[str, Any] | None = None,
    issued_at: datetime | None = None,
    expires_in: timedelta | None = None,
) -> str:
    if claims is None:
        claims = {}

    if issued_at is None:
        issued_at = datetime.now(tz=timezone.utc)

    if expires_in is None:
        expires_in = timedelta(hours=1)

    token = jwt.JWT(
        header={"alg": "RS256"},
        claims={
            "iat": int(issued_at.timestamp()),
            "exp": int((issued_at + expires_in).timestamp()),
            **claims,
        },
    )

    token.make_signed_token(get_oid_test_jwk())

    return token.serialize()


def issue_client_access_token(
    client_id: UUID | str = "flame",
    issued_at: datetime | None = None,
    expires_in: timedelta | None = None,
):
    return issue_access_token(
        {
            env.oidc_client_id_claim_name(): str(client_id),
        },
        issued_at,
        expires_in,
    )


class BearerAuth(httpx.Auth):
    def __init__(self, token: str):
        self.__token = token

    def auth_flow(self, request: Request):
        request.headers["Authorization"] = f"Bearer {self.__token}"
        yield request
