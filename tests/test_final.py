import uuid

import pytest
from starlette import status

from tests.common.auth import issue_client_access_token, BearerAuth
from tests.common.helpers import next_random_bytes, eventually
from tests.common.rest import wrap_bytes_for_request, detail_of

pytestmark = pytest.mark.live


def test_200_submit_with_local_dp(test_client, rng, core_client, storage_client, analysis_id):
    def _check_result_bucket_exists():
        return core_client.find_analysis_buckets(filter={"analysis_id": analysis_id, "type": "RESULT"})

    assert eventually(_check_result_bucket_exists)

    # Send a valid numerical file
    raw_value = 5.0
    blob = str(raw_value).encode("utf-8")
    filename = "test_result.txt"

    # Set parameters for DP
    form_data = {
        "epsilon": "1.0",
        "sensitivity": "1.0"
    }

    r = test_client.put(
        "/final/localdp",
        auth=BearerAuth(issue_client_access_token(analysis_id)),
        files={"file": (filename, blob, "text/plain")},
        data=form_data,
    )

    assert r.status_code == status.HTTP_204_NO_CONTENT, f"Unexpected status code: {r.status_code}"

    # retrieve result and see if it returned a file with single number
    uploaded_files = core_client.find_analysis_bucket_files(
        filter={"analysis_id": analysis_id, "type": "RESULT"}
    )

    if uploaded_files:
        stored_file = uploaded_files[-1]  # Get the most recent file
        stored_content = b''.join(storage_client.stream_bucket_file(stored_file.external_id))

        if stored_content:
            noisy_value = float(stored_content.decode("utf-8"))
            assert noisy_value != raw_value, "Noisy value should be different from raw value!"


def test_200_submit_to_upload(test_client, rng, core_client, analysis_id):
    def _check_result_bucket_exists():
        return core_client.find_analysis_buckets(filter={"analysis_id": analysis_id, "type": "RESULT"})

    assert eventually(_check_result_bucket_exists)

    analysis_file_count_old = len(
        core_client.find_analysis_bucket_files(filter={"analysis_id": analysis_id, "type": "RESULT"})
    )

    blob = next_random_bytes(rng)
    r = test_client.put(
        "/final",
        auth=BearerAuth(issue_client_access_token(analysis_id)),
        files=wrap_bytes_for_request(blob),
    )

    assert r.status_code == status.HTTP_204_NO_CONTENT

    analysis_file_count_new = len(
        core_client.find_analysis_bucket_files(filter={"analysis_id": analysis_id, "type": "RESULT"})
    )

    assert analysis_file_count_new > analysis_file_count_old


def test_404_submit_invalid_id(test_client, rng):
    rand_uuid = str(uuid.uuid4())
    blob = next_random_bytes(rng)

    r = test_client.put(
        "/final",
        auth=BearerAuth(issue_client_access_token(rand_uuid)),
        files=wrap_bytes_for_request(blob),
    )

    assert r.status_code == status.HTTP_404_NOT_FOUND
    assert detail_of(r) == f"Result bucket for analysis with ID {rand_uuid} was not found"
