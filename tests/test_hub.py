import uuid
from io import BytesIO

import pytest

from tests.common.helpers import eventually
from tests.common.rest import next_random_bytes

pytestmark = pytest.mark.live


def _next_uuid():
    return str(uuid.uuid4())


def _next_prefixed_name():
    return f"node-it-{_next_uuid()}"


def _is_valid_uuid(val: str):
    try:
        uuid.UUID(val)
    except ValueError:
        return False

    return True


def test_upload_to_bucket(api, rng):
    project_name = _next_prefixed_name()
    project = api.create_project(project_name)

    assert project.name == project_name
    assert _is_valid_uuid(project.id)

    analysis_name = _next_prefixed_name()
    analysis = api.create_analysis(analysis_name, project.id)

    assert analysis.name == analysis_name
    assert _is_valid_uuid(analysis.id)

    for bucket_type in ("result", "code", "temp"):

        def __bucket_exists():
            bucket_name = f"analysis-{bucket_type}-files.{analysis.id}"
            bucket = api.get_bucket(bucket_name)

            if bucket is None:
                return False

            assert bucket.name == bucket_name
            assert _is_valid_uuid(bucket.id)

        assert eventually(__bucket_exists)

    result_bucket_name = f"analysis-result-files.{analysis.id}"
    file_name = _next_prefixed_name()
    bucket_file_lst = api.upload_to_bucket(
        result_bucket_name, file_name, BytesIO(next_random_bytes(rng))
    )

    assert len(bucket_file_lst) == 1

    bucket_file = bucket_file_lst[0]

    assert bucket_file.name == file_name
    assert _is_valid_uuid(bucket_file.id)

    analysis_file = api.link_file_to_analysis(
        analysis.id, bucket_file.id, bucket_file.name
    )

    assert analysis_file.name == bucket_file.name
    assert _is_valid_uuid(analysis_file.id)
    assert analysis_file.type == "RESULT"
    assert analysis_file.bucket_file_id == bucket_file.id

    analysis_file_list = api.get_analysis_files()

    assert analysis_file.id in [f.id for f in analysis_file_list]
