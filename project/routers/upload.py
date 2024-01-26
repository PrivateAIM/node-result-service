import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile, BackgroundTasks
from minio import Minio
from starlette import status

from project.config import Settings
from project.dependencies import get_minio, get_settings

router = APIRouter()


async def upload_to_remote(
    local_minio: Minio,
    bucket_name: str,
    object_name: str,
):
    obj = local_minio.get_object(bucket_name, object_name)
    print(f"uploading {object_name} ({obj.getheader('Content-Type')}) to remote")
    local_minio.remove_object(bucket_name, object_name)
    print("object has been deleted")


@router.put(
    "/{project_id}",
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_for_upload(
    project_id: uuid.UUID,
    file: UploadFile,
    background_tasks: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
    minio: Annotated[Minio, Depends(get_minio)],
):
    object_id = str(uuid.uuid4())
    object_name = f"upload/{project_id}/{object_id}"

    minio.put_object(
        settings.minio.bucket,
        object_name,
        data=file.file,
        length=file.size,
        content_type=file.content_type or "application/octet-stream",
    )

    background_tasks.add_task(
        upload_to_remote,
        minio,
        settings.minio.bucket,
        object_name,
    )

    return "OK"
