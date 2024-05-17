import uuid

import pytest
from starlette import status

from project.routers.intermediate import IntermediateUploadResponse
from tests.common.auth import BearerAuth, issue_client_access_token
from tests.common.helpers import next_random_bytes, eventually
from tests.common.rest import wrap_bytes_for_request, detail_of

pytestmark = pytest.mark.live


def test_200_submit_receive_from_scratch(test_client, rng, analysis_id):
    blob = next_random_bytes(rng)
    r = test_client.put(
        "/intermediate",
        auth=BearerAuth(issue_client_access_token(analysis_id)),
        files=wrap_bytes_for_request(blob),
    )

    assert r.status_code == status.HTTP_202_ACCEPTED

    # check that the response contains a path to a valid resource
    model = IntermediateUploadResponse(**r.json())

    def _check_response_from_hub():
        r = test_client.get(
            model.url.path,
            auth=BearerAuth(issue_client_access_token()),
        )

        if r.status_code != status.HTTP_200_OK:
            return False

        assert r.read() == blob
        return True

    assert eventually(_check_response_from_hub)


def test_whatever(test_client):
    rand_uuid = str(uuid.uuid4())
    r = test_client.get(
        f"/intermediate/{rand_uuid}",
        auth=BearerAuth(issue_client_access_token()),
    )

    assert r.status_code == status.HTTP_404_NOT_FOUND
    assert detail_of(r) == f"Object with ID {rand_uuid} does not exist"
