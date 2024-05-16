import pytest

from project.hub_ng import (
    FlamePasswordAuthClient,
    FlameHubClient,
    format_analysis_bucket_name,
    BucketType,
)
from tests.common.env import (
    PYTEST_HUB_AUTH_USERNAME,
    PYTEST_HUB_AUTH_PASSWORD,
    PYTEST_HUB_AUTH_BASE_URL,
    PYTEST_HUB_API_BASE_URL,
)
from tests.common.helpers import next_prefixed_name, eventually, next_random_bytes

pytestmark = pytest.mark.hub


@pytest.fixture(scope="module")
def auth_client():
    return FlamePasswordAuthClient(
        PYTEST_HUB_AUTH_USERNAME,
        PYTEST_HUB_AUTH_PASSWORD,
        base_url=PYTEST_HUB_AUTH_BASE_URL,
        force_acquire_on_init=True,
    )


def test_auth_acquire_token(auth_client):
    assert auth_client.get_access_token_object() is not None


def test_auth_no_reissue(auth_client):
    at = auth_client.get_access_token_object()
    at_new = auth_client.get_access_token_object()

    assert at.access_token == at_new.access_token


@pytest.fixture(scope="module")
def api_client(auth_client):
    return FlameHubClient(auth_client, base_url=PYTEST_HUB_API_BASE_URL)


@pytest.fixture
def project_id(api_client):
    project_name = next_prefixed_name()
    project = api_client.create_project(project_name)

    # check that project was successfully created
    assert project.name == project_name

    # check that project can be retrieved
    project_get = api_client.get_project_by_id(project.id)
    assert project_get.id == project.id

    # check that project appears in list
    project_get_list = api_client.get_project_list()
    assert any([p.id == project.id for p in project_get_list.data])

    yield project.id

    # check that project can be deleted
    api_client.delete_project(project.id)

    # check that project is no longer found
    assert api_client.get_project_by_id(project.id) is None


@pytest.fixture
def analysis_id(api_client, project_id):
    analysis_name = next_prefixed_name()
    analysis = api_client.create_analysis(analysis_name, project_id)

    # check that analysis was created
    assert analysis.name == analysis_name
    assert analysis.project_id == project_id

    # check that GET on analysis works
    analysis_get = api_client.get_analysis_by_id(analysis.id)
    assert analysis_get.id == analysis.id

    # check that analysis appears in list
    analysis_get_list = api_client.get_analysis_list()
    assert any([a.id == analysis.id for a in analysis_get_list.data])

    yield analysis.id

    # check that DELETE analysis works
    api_client.delete_analysis(analysis.id)

    # check that analysis is no longer found
    assert api_client.get_analysis_by_id(analysis.id) is None


@pytest.fixture
def result_bucket_name(analysis_id, api_client):
    bucket_types: tuple[BucketType, ...] = ("CODE", "TEMP", "RESULT")

    # check that buckets are eventually created (happens asynchronously)
    def _check_buckets_exist():
        for bucket_type in bucket_types:
            bucket_name = format_analysis_bucket_name(analysis_id, bucket_type)
            bucket = api_client.get_bucket_by_id_or_name(bucket_name)

            if bucket is None:
                return False

        return True

    assert eventually(_check_buckets_exist)

    # check that buckets are listed correctly
    bucket_list = api_client.get_bucket_list()

    for bucket_type in bucket_types:
        bucket_name = format_analysis_bucket_name(analysis_id, bucket_type)
        assert any([b.name == bucket_name for b in bucket_list.data])

    yield format_analysis_bucket_name(analysis_id, "RESULT")


@pytest.fixture
def uploaded_bucket_file(result_bucket_name, api_client, rng):
    file_name = next_prefixed_name()
    file_blob = next_random_bytes(rng)

    # check that bucket file is created
    bucket_file_created_list = api_client.upload_to_bucket(
        result_bucket_name, file_name, file_blob
    )
    assert len(bucket_file_created_list.data) == 1

    # check that metadata aligns with file name and blob size
    bucket_file = bucket_file_created_list.data[0]
    assert bucket_file.name == file_name
    assert bucket_file.size == len(file_blob)

    # check that bucket file appears in list
    bucket_file_list = api_client.get_bucket_file_list()
    assert any([bf.id == bucket_file.id for bf in bucket_file_list.data])

    yield file_blob, bucket_file


def test_link_bucket_file_to_analysis(uploaded_bucket_file, analysis_id, api_client):
    _, bucket_file = uploaded_bucket_file

    # check that the analysis file was created
    analysis_file = api_client.link_bucket_file_to_analysis(
        analysis_id, bucket_file.id, bucket_file.name, bucket_type="RESULT"
    )

    assert analysis_file.name == bucket_file.name
    assert analysis_file.bucket_file_id == bucket_file.id

    # check that it appears in the list
    analysis_file_list = api_client.get_analysis_file_list()
    assert any([af.id == analysis_file.id for af in analysis_file_list.data])


def test_stream_bucket_file(uploaded_bucket_file, api_client):
    file_blob, bucket_file = uploaded_bucket_file

    # default chunk size is 1024 and the blobs in these tests are 16 bytes large, so one call to next()
    # should fetch the blob in its entirety from hub
    remote_file_blob = next(api_client.stream_bucket_file(bucket_file.id))
    assert file_blob == remote_file_blob
