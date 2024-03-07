import pytest
from starlette import status

from tests.common.auth import issue_client_access_token, BearerAuth
from tests.common.helpers import eventually
from tests.common.rest import next_random_bytes, wrap_bytes_for_request
from tests.test_hub import _next_prefixed_name

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def analysis_id(api, rng):
    project_name = _next_prefixed_name()
    project = api.create_project(project_name)

    analysis_name = _next_prefixed_name()
    analysis = api.create_analysis(analysis_name, project.id)

    def __check_result_bucket():
        bucket_name = f"analysis-result-files.{analysis.id}"
        bucket = api.get_bucket(bucket_name)

        return bucket is not None

    # make sure result bucket exists before firing off requests
    assert eventually(__check_result_bucket)

    yield analysis.id


def test_200_submit_to_upload(test_client, rng, api, analysis_id):
    analysis_file_count_old = len(api.get_analysis_files())

    blob = next_random_bytes(rng)
    r = test_client.put(
        "/upload",
        auth=BearerAuth(issue_client_access_token(analysis_id)),
        files=wrap_bytes_for_request(blob),
    )

    assert r.status_code == status.HTTP_204_NO_CONTENT

    def __check_analysis_file_count_increases():
        analysis_file_count_new = len(api.get_analysis_files())
        return analysis_file_count_new > analysis_file_count_old

    assert eventually(__check_analysis_file_count_increases)
