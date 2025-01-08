import uuid

from starlette import status

from project.routers.local import (
    LocalUploadResponse,
    LocalTagListResponse,
    LocalTaggedResultListResponse,
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


def test_200_get_tags_empty(test_client):
    r = test_client.get(
        "/local/tags",
        auth=BearerAuth(issue_client_access_token()),
    )

    assert r.status_code == status.HTTP_200_OK
    model = LocalTagListResponse(**r.json())

    assert len(model.tags) == 0


def test_200_create_tagged_upload(test_client, rng):
    tag, filename = str(uuid.uuid4()), str(uuid.uuid4())
    blob = next_random_bytes(rng)

    r = test_client.put(
        "/local",
        auth=BearerAuth(issue_client_access_token()),
        files=wrap_bytes_for_request(blob, file_name=filename),
        data={"tag": tag},
    )

    assert r.status_code == status.HTTP_200_OK
    model = LocalUploadResponse(**r.json())
    result_url = model.url

    r = test_client.get(
        "/local/tags",
        auth=BearerAuth(issue_client_access_token()),
    )

    assert r.status_code == status.HTTP_200_OK
    model = LocalTagListResponse(**r.json())

    tag = model.tags.pop()
    assert len(model.tags) == 0  # check that this is empty after pop()

    r = test_client.get(
        tag.url.path,
        auth=BearerAuth(issue_client_access_token()),
    )

    assert r.status_code == status.HTTP_200_OK
    model = LocalTaggedResultListResponse(**r.json())

    tagged_result = model.results.pop()
    assert len(model.results) == 0  # check that it is empty after pop()

    assert tagged_result.url == result_url
    assert tagged_result.filename == filename
