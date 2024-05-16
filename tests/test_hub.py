from io import BytesIO

import pytest

from tests.common.helpers import next_prefixed_name, is_valid_uuid, next_random_bytes

pytestmark = pytest.mark.live


def test_upload_to_bucket(api, rng, analysis_id):
    # 1) upload file with random name to bucket
    result_bucket_name = f"analysis-result-files.{analysis_id}"
    file_name = next_prefixed_name()
    file_blob = next_random_bytes(rng)

    bucket_file_lst = api.upload_to_bucket(
        result_bucket_name, file_name, BytesIO(file_blob)
    )

    # 2) check that the endpoint returned a single file
    assert len(bucket_file_lst) == 1

    # 3) check that the file matches the uploaded file
    bucket_file = bucket_file_lst[0]

    assert bucket_file.name == file_name
    assert is_valid_uuid(bucket_file.id)

    # 4) link uploaded file to analysis
    analysis_file = api.link_file_to_analysis(
        analysis_id, bucket_file.id, bucket_file.name, "RESULT"
    )

    assert analysis_file.name == bucket_file.name
    assert is_valid_uuid(analysis_file.id)
    assert analysis_file.type == "RESULT"
    assert analysis_file.bucket_file_id == bucket_file.id

    # 5) check that uploaded file appears in list of analysis files
    analysis_file_list = api.get_analysis_files()

    assert analysis_file.id in [f.id for f in analysis_file_list]

    # 6) download the file and check that it's identical with the submitted bytes
    bucket_file_data = next(api.stream_bucket_file(bucket_file.id))
    assert bucket_file_data == file_blob
