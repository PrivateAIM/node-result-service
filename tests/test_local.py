import uuid

from starlette import status

from project.routers.local import (
    LocalUploadResponse,
)
from tests.common.auth import BearerAuth, issue_client_access_token
from tests.common.helpers import next_random_bytes
from tests.common.rest import wrap_bytes_for_request, detail_of


def test_200_submit_receive_from_local(test_client, rng):
    blob = next_random_bytes(rng)
    r = test_client.put(
        "/local",
        auth=BearerAuth(issue_client_access_token()),
        files=wrap_bytes_for_request(blob),
    )

    assert r.status_code == status.HTTP_200_OK
    model = LocalUploadResponse(**r.json())

    r = test_client.get(
        model.url.path,
        auth=BearerAuth(issue_client_access_token()),
    )

    assert r.status_code == status.HTTP_200_OK
    assert r.read() == blob


def test_404_unknown_oid(test_client):
    oid = uuid.uuid4()
    r = test_client.get(
        f"/local/{oid}",
        auth=BearerAuth(issue_client_access_token()),
    )

    assert r.status_code == status.HTTP_404_NOT_FOUND
    assert detail_of(r) == f"Object with ID {oid} does not exist"
