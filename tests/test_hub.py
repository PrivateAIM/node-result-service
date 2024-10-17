from uuid import uuid4

import pytest

from project.hub import (
    BucketType,
)
from tests.common.helpers import next_prefixed_name, eventually, next_random_bytes

pytestmark = pytest.mark.live


def test_password_auth_acquire_token(password_auth_client):
    assert password_auth_client.get_auth_header() is not None


def test_password_auth_no_reissue(password_auth_client):
    at = password_auth_client.get_auth_header()
    at_new = password_auth_client.get_auth_header()

    assert at is not None
    assert at == at_new


def test_robot_auth_acquire_token(robot_auth_client):
    assert robot_auth_client.get_auth_header() is not None


def test_robot_auth_no_reissue(robot_auth_client):
    at = robot_auth_client.get_auth_header()
    at_new = robot_auth_client.get_auth_header()

    assert at is not None
    assert at == at_new


@pytest.fixture
def result_bucket_id(analysis_id, core_client, storage_client):
    bucket_types: tuple[BucketType, ...] = ("CODE", "TEMP", "RESULT")

    # check that buckets are eventually created (happens asynchronously)
    def _check_buckets_exist():
        for bucket_type in bucket_types:
            analysis_bucket = core_client.get_analysis_bucket(analysis_id, bucket_type)

            if analysis_bucket is None:
                return False

            bucket = storage_client.get_bucket_by_id(analysis_bucket.external_id)

            if bucket is None:
                return False

        return True

    assert eventually(_check_buckets_exist)

    # bucket id is referenced from analysis bucket by its external_id prop
    yield core_client.get_analysis_bucket(analysis_id, "RESULT").external_id


@pytest.fixture
def uploaded_bucket_file(result_bucket_id, storage_client, rng):
    file_name = next_prefixed_name()
    file_blob = next_random_bytes(rng)

    # check that bucket file is created
    bucket_file_created_list = storage_client.upload_to_bucket(
        result_bucket_id, file_name, file_blob
    )
    assert len(bucket_file_created_list.data) == 1

    # check that metadata aligns with file name and blob size
    bucket_file = bucket_file_created_list.data[0]
    assert bucket_file.name == file_name
    assert bucket_file.size == len(file_blob)

    # check that bucket file appears in list
    bucket_file_list = storage_client.get_bucket_file_list()
    assert any([bf.id == bucket_file.id for bf in bucket_file_list.data])

    # check that bucket file can be accessed individually
    assert storage_client.get_bucket_file_by_id(bucket_file.id) is not None

    yield file_blob, bucket_file


def test_get_bucket_file_by_id_not_found(storage_client):
    assert storage_client.get_bucket_file_by_id(uuid4()) is None


def test_link_bucket_file_to_analysis(uploaded_bucket_file, analysis_id, core_client):
    _, bucket_file = uploaded_bucket_file

    analysis_bucket = core_client.get_analysis_bucket(analysis_id, "RESULT")
    assert analysis_bucket is not None

    # check that the analysis file was created
    analysis_file = core_client.link_bucket_file_to_analysis(
        analysis_bucket.id, bucket_file.id, bucket_file.name
    )

    assert analysis_file.name == bucket_file.name
    assert analysis_file.external_id == bucket_file.id

    # check that it appears in the list
    analysis_file_list = core_client.get_analysis_bucket_file_list()
    assert any([af.id == analysis_file.id for af in analysis_file_list.data])


def test_stream_bucket_file(uploaded_bucket_file, storage_client):
    file_blob, bucket_file = uploaded_bucket_file

    # default chunk size is 1024 and the blobs in these tests are 16 bytes large, so one call to next()
    # should fetch the blob in its entirety from hub
    remote_file_blob = next(storage_client.stream_bucket_file(bucket_file.id))
    assert file_blob == remote_file_blob
