import re
import uuid

from starlette import status

from project.routers.scratch import ScratchUploadResponse
from tests.common.auth import BearerAuth, issue_client_access_token
from tests.common.helpers import next_random_bytes
from tests.common.rest import wrap_bytes_for_request, detail_of


def test_200_submit_receive_from_scratch(test_client, rng):
    blob = next_random_bytes(rng)
    r = test_client.put(
        "/scratch",
        auth=BearerAuth(issue_client_access_token()),
        files=wrap_bytes_for_request(blob),
    )

    assert r.status_code == status.HTTP_200_OK

    # check that the response contains a path to a valid resource
    model = ScratchUploadResponse(**r.json())
    path_regex = (
        r"/scratch/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    )

    assert re.fullmatch(path_regex, model.url.path) is not None

    r = test_client.get(
        model.url.path,
        auth=BearerAuth(issue_client_access_token()),
    )

    assert r.status_code == status.HTTP_200_OK
    assert r.read() == blob


def test_whatever(test_client):
    rand_uuid = str(uuid.uuid4())
    r = test_client.get(
        f"/scratch/{rand_uuid}",
        auth=BearerAuth(issue_client_access_token()),
    )

    assert r.status_code == status.HTTP_404_NOT_FOUND
    assert detail_of(r) == f"Object with ID {rand_uuid} does not exist"
