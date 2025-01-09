import random
import string
import uuid

import pytest
from starlette import status

from project.routers.local import (
    LocalUploadResponse,
    LocalTagListResponse,
    LocalTaggedResultListResponse,
    is_valid_tag,
)
from tests.common.auth import BearerAuth, issue_client_access_token
from tests.common.helpers import next_random_bytes
from tests.common.rest import wrap_bytes_for_request, detail_of

_tag_test_cases = [
    ("", False),
    (" ", False),
    ("-", False),
    ("--", False),
    ("-ab", False),
    ("ab-", False),
    ("-0", False),
    ("0-", False),
    (" -a", False),
    ("a- ", False),
    ("a", True),
    ("0", True),
    ("aa", True),
    ("00", True),
    ("a0", True),
    ("0a", True),
    ("result1", True),
    ("result-1", True),
    ("result--1", True),
    ("a" + "-" * 30 + "a", True),
    ("a" + "-" * 31 + "a", False),
    ("a" * 33, False),
]


@pytest.mark.parametrize("pattern,expected", _tag_test_cases)
def test_is_valid_tag(pattern, expected):
    assert is_valid_tag(pattern) == expected


@pytest.mark.parametrize("pattern,expected", _tag_test_cases)
def test_200_400_tag_validation(test_client, rng, pattern, expected):
    filename = str(uuid.uuid4())
    blob = next_random_bytes(rng)

    r = test_client.put(
        "/local",
        auth=BearerAuth(issue_client_access_token()),
        files=wrap_bytes_for_request(blob, file_name=filename),
        data={"tag": pattern},
    )

    if expected:
        assert r.status_code == status.HTTP_200_OK
    else:
        assert r.status_code == status.HTTP_400_BAD_REQUEST
        assert detail_of(r) == f"Invalid tag `{pattern}`"


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


def test_200_create_tagged_upload(test_client, rng):
    # use global random here to generate different tags for each run
    tag = "".join(random.choices(string.ascii_lowercase, k=16))
    filename = str(uuid.uuid4())
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
    assert any(tag_obj.name == tag for tag_obj in model.tags)

    r = test_client.get(
        f"/local/tags/{tag}",
        auth=BearerAuth(issue_client_access_token()),
    )

    assert r.status_code == status.HTTP_200_OK
    model = LocalTaggedResultListResponse(**r.json())

    tagged_result = model.results.pop()
    assert len(model.results) == 0  # check that it is empty after pop()

    assert tagged_result.url == result_url
    assert tagged_result.filename == filename
