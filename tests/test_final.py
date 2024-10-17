import pytest
from starlette import status

from tests.common.auth import issue_client_access_token, BearerAuth
from tests.common.helpers import next_random_bytes
from tests.common.rest import wrap_bytes_for_request

pytestmark = pytest.mark.live


def test_200_submit_to_upload(test_client, rng, core_client, analysis_id):
    analysis_file_count_old = len(core_client.get_analysis_bucket_file_list().data)

    blob = next_random_bytes(rng)
    r = test_client.put(
        "/final",
        auth=BearerAuth(issue_client_access_token(analysis_id)),
        files=wrap_bytes_for_request(blob),
    )

    assert r.status_code == status.HTTP_204_NO_CONTENT

    analysis_file_count_new = len(core_client.get_analysis_bucket_file_list().data)
    assert analysis_file_count_new > analysis_file_count_old
