import uuid

import pytest
from starlette import status

from project.routers.intermediate import IntermediateUploadResponse
from tests.common.auth import BearerAuth, issue_client_access_token
from tests.common.helpers import next_random_bytes, eventually
from tests.common.rest import wrap_bytes_for_request, detail_of

pytestmark = pytest.mark.live


def test_200_submit_receive_intermediate(test_client, rng, analysis_id, core_client):
    def _check_temp_bucket_exists():
        return core_client.get_analysis_bucket(analysis_id, "TEMP") is not None

    assert eventually(_check_temp_bucket_exists)

    blob = next_random_bytes(rng)
    r = test_client.put(
        "/intermediate",
        auth=BearerAuth(issue_client_access_token(analysis_id)),
        files=wrap_bytes_for_request(blob),
    )

    assert r.status_code == status.HTTP_200_OK

    # check that the response contains a path to a valid resource
    model = IntermediateUploadResponse(**r.json())
    assert str(model.object_id) in str(model.url.path)

    r = test_client.get(
        model.url.path,
        auth=BearerAuth(issue_client_access_token()),
    )

    if r.status_code != status.HTTP_200_OK:
        return False

    assert r.read() == blob


def test_404_invalid_id(test_client):
    rand_uuid = str(uuid.uuid4())
    r = test_client.get(
        f"/intermediate/{rand_uuid}",
        auth=BearerAuth(issue_client_access_token()),
    )

    assert r.status_code == status.HTTP_404_NOT_FOUND
    assert detail_of(r) == f"Object with ID {rand_uuid} does not exist"
