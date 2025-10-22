import random
import string
import uuid
import os

import pytest
from starlette import status

from project import crud
from project.routers.local import (
    is_valid_tag,
    LocalUploadResponse,
    LocalTagListResponse,
    LocalTaggedResultListResponse,
)
from tests.common.auth import BearerAuth, issue_client_access_token
from tests.common.helpers import next_random_bytes, eventually, next_prefixed_name
from tests.common.rest import wrap_bytes_for_request, detail_of

pytestmark = pytest.mark.live

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


def test_200_create_tagged_upload(test_client, rng, analysis_id, core_client):
    # use global random here to generate different tags for each run
    tag = "".join(random.choices(string.ascii_lowercase, k=16))
    filename = str(uuid.uuid4())
    blob = next_random_bytes(rng)
    auth = BearerAuth(issue_client_access_token(analysis_id))

    r = test_client.put(
        "/local",
        auth=auth,
        files=wrap_bytes_for_request(blob, file_name=filename),
        data={"tag": tag},
    )

    assert r.status_code == status.HTTP_200_OK
    model = LocalUploadResponse(**r.json())
    result_url = model.url

    r = test_client.get(
        "/local/tags",
        auth=auth,
    )

    assert r.status_code == status.HTTP_200_OK
    model = LocalTagListResponse(**r.json())
    assert any(tag_obj.name == tag for tag_obj in model.tags)

    r = test_client.get(
        f"/local/tags/{tag}",
        auth=auth,
    )

    assert r.status_code == status.HTTP_200_OK
    model = LocalTaggedResultListResponse(**r.json())

    tagged_result = model.results.pop()
    assert len(model.results) == 0  # check that it is empty after pop()

    assert tagged_result.url == result_url
    assert tagged_result.filename == filename


def test_404_submit_tagged(test_client, rng):
    rand_uuid = str(uuid.uuid4())
    blob = next_random_bytes(rng)

    r = test_client.put(
        "/local",
        auth=BearerAuth(issue_client_access_token(rand_uuid)),
        files=wrap_bytes_for_request(blob),
        data={"tag": "foobar"},
    )

    assert r.status_code == status.HTTP_404_NOT_FOUND
    assert detail_of(r) == f"Analysis with ID {rand_uuid} not found"


def test_404_get_tags(test_client):
    rand_uuid = str(uuid.uuid4())

    r = test_client.get(
        "/local/tags",
        auth=BearerAuth(issue_client_access_token(rand_uuid)),
    )

    assert r.status_code == status.HTTP_404_NOT_FOUND
    assert detail_of(r) == f"Analysis with ID {rand_uuid} not found"


def test_404_get_results_by_tag(test_client):
    rand_uuid = str(uuid.uuid4())

    r = test_client.get(
        # tag doesn't really matter here bc analysis check happens before everything else
        "/local/tags/foobar",
        auth=BearerAuth(issue_client_access_token(rand_uuid)),
    )

    assert r.status_code == status.HTTP_404_NOT_FOUND
    assert detail_of(r) == f"Analysis with ID {rand_uuid} not found"


def test_200_delete_tagged_results(test_client, core_client, rng, minio, postgres):
    project = core_client.create_project(name=next_prefixed_name())
    analysis = core_client.create_analysis(project_id=project.id, name=next_prefixed_name())

    def _project_and_analysis_exist():
        return core_client.get_project(project.id) is not None and core_client.get_analysis(analysis.id) is not None

    assert eventually(_project_and_analysis_exist)

    blob = next_random_bytes(rng)
    tag = "".join(random.choices(string.ascii_lowercase, k=16))
    test_client.put(
        "/local",
        auth=BearerAuth(issue_client_access_token(analysis.id)),
        files=wrap_bytes_for_request(blob),
        data={"tag": tag},
    )

    core_client.delete_analysis(analysis.id)
    core_client.delete_project(project.id)

    r = test_client.delete(
        "/local",
        params={"project_id": project.id},
    )

    assert r.status_code == status.HTTP_200_OK

    bucket = os.environ.get("MINIO__BUCKET")
    assert len(list(minio.list_objects(bucket, prefix=f"local/{project.id}/"))) == 0

    with crud.bind_to(postgres):
        assert len(crud.Result.select().where(crud.Result.client_id == analysis.id)) == 0
        assert len(crud.Tag.select().where(crud.Tag.project_id == project.id)) == 0
