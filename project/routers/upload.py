import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile, BackgroundTasks
from minio import Minio
from starlette import status

from project.config import Settings
from project.dependencies import get_minio, get_settings, get_client_id

router = APIRouter()
logger = logging.getLogger(__name__)


async def __bg_upload_to_remote(
    local_minio: Minio,
    bucket_name: str,
    object_name: str,
):
    logger.info(
        "Dummy call to __bg_upload_to_remote for bucket %s and object",
        bucket_name,
        object_name,
    )
    local_minio.get_object(bucket_name, object_name)
    local_minio.remove_object(bucket_name, object_name)


@router.put(
    "/",
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_to_remote(
    client_id: Annotated[str, Depends(get_client_id)],
    file: UploadFile,
    background_tasks: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
    minio: Annotated[Minio, Depends(get_minio)],
):
    object_id = str(uuid.uuid4())
    object_name = f"upload/{client_id}/{object_id}"

    minio.put_object(
        settings.minio.bucket,
        object_name,
        data=file.file,
        length=file.size,
        content_type=file.content_type or "application/octet-stream",
    )

    background_tasks.add_task(
        __bg_upload_to_remote,
        minio,
        settings.minio.bucket,
        object_name,
    )

    return "OK"
