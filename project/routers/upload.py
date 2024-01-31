import io
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile, BackgroundTasks
from minio import Minio, S3Error
from starlette import status

from project.config import Settings
from project.dependencies import (
    get_local_minio,
    get_settings,
    get_client_id,
    get_remote_minio,
)

router = APIRouter()
logger = logging.getLogger(__name__)


async def __bg_upload_to_remote(
    remote_minio: Minio,
    remote_bucket_name: str,
    local_minio: Minio,
    local_bucket_name: str,
    object_name: str,
):
    max_attempts = 3  # TODO: should be configurable

    for i in range(max_attempts):
        logger.info(
            "__bg_upload_to_remote: bucket `%s`, object `%s` (attempt: %d)",
            local_bucket_name,
            object_name,
            i + 1,
        )

        r = None

        try:
            r = local_minio.get_object(local_bucket_name, object_name)
            remote_minio.put_object(
                remote_bucket_name,
                object_name,
                io.BytesIO(r.data),
                length=-1,
                content_type=r.headers.get("Content-Type", "application/octet-stream"),
                part_size=10 * 1024 * 1024,
            )
            local_minio.remove_object(local_bucket_name, object_name)

            return
        except S3Error:
            logger.exception("Failed to upload object to remote")
        finally:
            if r is not None:
                r.close()
                r.release_conn()

    logger.error("Failed to upload `%s` to remote after %d attempts", object_name)


@router.put(
    "/",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def upload_to_remote(
    client_id: Annotated[str, Depends(get_client_id)],
    file: UploadFile,
    background_tasks: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
    local_minio: Annotated[Minio, Depends(get_local_minio)],
    remote_minio: Annotated[Minio, Depends(get_remote_minio)],
):
    object_id = str(uuid.uuid4())
    object_name = f"upload/{client_id}/{object_id}"

    local_minio.put_object(
        settings.minio.bucket,
        object_name,
        data=file.file,
        length=file.size,
        content_type=file.content_type or "application/octet-stream",
    )

    background_tasks.add_task(
        __bg_upload_to_remote,
        remote_minio,
        settings.remote.bucket,
        local_minio,
        settings.minio.bucket,
        object_name,
    )
