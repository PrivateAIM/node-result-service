import time

from minio import Minio
from starlette import status

from tests.common.auth import BearerAuth, issue_client_access_token
from tests.common.env import PYTEST_REMOTE_VALIDATE_UPLOAD_MAX_ATTEMPTS
from tests.common.rest import next_random_bytes, wrap_bytes_for_request


def __count_bucket_objects(minio: Minio, bucket_name: str) -> int:
    return sum(1 for _ in minio.list_objects(bucket_name, recursive=True))


def test_204_submit_to_upload(test_client, rng, remote_minio):
    minio, bucket_name = remote_minio
    blob = next_random_bytes(rng)

    old_remote_obj_count = __count_bucket_objects(minio, bucket_name)

    r = test_client.put(
        "/upload",
        auth=BearerAuth(issue_client_access_token()),
        files=wrap_bytes_for_request(blob),
    )

    assert r.status_code == status.HTTP_204_NO_CONTENT

    # since the actual upload to the remote server is deferred, the object might not
    # be instantly available on remote. therefore we allow some leeway with some extra attempts.
    max_attempts = int(PYTEST_REMOTE_VALIDATE_UPLOAD_MAX_ATTEMPTS)

    for _ in range(max_attempts):
        new_remote_obj_count = __count_bucket_objects(minio, bucket_name)

        if new_remote_obj_count == old_remote_obj_count + 1:
            return

        time.sleep(1)

    raise AssertionError(
        f"failed to verify successful upload after {max_attempts} attempts"
    )
