import pytest

from project.hub import (
    BucketType,
)
from tests.common.helpers import next_prefixed_name, eventually, next_random_bytes

pytestmark = pytest.mark.live


def test_auth_acquire_token(auth_client):
    assert auth_client.get_access_token_object() is not None


def test_auth_no_reissue(auth_client):
    at = auth_client.get_access_token_object()
    at_new = auth_client.get_access_token_object()

    assert at.access_token == at_new.access_token


@pytest.fixture
def result_bucket_name(analysis_id, api_client):
    bucket_types: tuple[BucketType, ...] = ("CODE", "TEMP", "RESULT")

    # check that buckets are eventually created (happens asynchronously)
    def _check_buckets_exist():
        for bucket_type in bucket_types:
            analysis_bucket = api_client.get_analysis_bucket(analysis_id, bucket_type)
            bucket = api_client.get_bucket_by_id(analysis_bucket.external_id)

            if bucket is None:
                return False

        return True

    assert eventually(_check_buckets_exist)


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

    analysis_bucket = api_client.get_analysis_bucket(analysis_id, "RESULT")

    # check that the analysis file was created
    analysis_file = api_client.link_bucket_file_to_analysis(
        analysis_bucket.external_id, bucket_file.id, bucket_file.name
    )

    assert analysis_file.name == bucket_file.name
    assert analysis_file.bucket_file_id == bucket_file.id

    # check that it appears in the list
    analysis_file_list = api_client.get_analysis_bucket_file_list()
    assert any([af.id == analysis_file.id for af in analysis_file_list.data])


def test_stream_bucket_file(uploaded_bucket_file, api_client):
    file_blob, bucket_file = uploaded_bucket_file

    # default chunk size is 1024 and the blobs in these tests are 16 bytes large, so one call to next()
    # should fetch the blob in its entirety from hub
    remote_file_blob = next(api_client.stream_bucket_file(bucket_file.id))
    assert file_blob == remote_file_blob
