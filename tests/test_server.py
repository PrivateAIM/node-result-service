import secrets
from datetime import datetime, timezone, timedelta

from starlette import status

from tests.common.auth import BearerAuth, issue_client_access_token, issue_access_token
from tests.common.rest import detail_of


def test_index_200(test_client):
    client_id = secrets.token_hex(16)
    r = test_client.get("/", auth=BearerAuth(issue_client_access_token(client_id)))

    assert r.status_code == status.HTTP_200_OK
    assert r.json()["client_id"] == client_id


def test_index_403_no_auth_header(test_client):
    r = test_client.get("/")

    assert r.status_code == status.HTTP_403_FORBIDDEN
    assert detail_of(r) == "Not authenticated"


def test_index_403_expired(test_client):
    r = test_client.get(
        "/",
        auth=BearerAuth(
            issue_client_access_token(
                issued_at=datetime.now(tz=timezone.utc) - timedelta(hours=1),
                expires_in=timedelta(seconds=1),
            )
        ),
    )

    assert r.status_code == status.HTTP_403_FORBIDDEN
    assert detail_of(r) == "JWT is malformed"


def test_index_403_no_client_id_claim(test_client):
    r = test_client.get("/", auth=BearerAuth(issue_access_token()))

    assert r.status_code == status.HTTP_403_FORBIDDEN
    assert detail_of(r) == "JWT is malformed"
