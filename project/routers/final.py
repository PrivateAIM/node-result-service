import io
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile, BackgroundTasks
from minio import Minio
from starlette import status

from project.config import Settings
from project.dependencies import (
    get_local_minio,
    get_settings,
    get_client_id,
    get_core_client,
    get_storage_client,
)
from project.hub import FlameCoreClient, FlameStorageClient

router = APIRouter()
logger = logging.getLogger(__name__)


def __bg_upload_to_remote(
    minio: Minio,
    bucket_name: str,
    object_name: str,
    core_client: FlameCoreClient,
    storage_client: FlameStorageClient,
    client_id: str,
):
    logger.info(
        "__bg_upload_to_remote: bucket `%s`, object `%s`",
        bucket_name,
        object_name,
    )

    minio_resp = None

    try:
        # fetch from local minio
        minio_resp = minio.get_object(bucket_name, object_name)

        # fetch analysis bucket
        analysis_bucket = core_client.get_analysis_bucket(client_id, "RESULT")

        # upload to remote
        bucket_file_lst = storage_client.upload_to_bucket(
            analysis_bucket.external_id,
            object_name,
            io.BytesIO(minio_resp.data),
            minio_resp.headers.get("Content-Type", "application/octet-stream"),
        )

        # check that only one file has been submitted
        assert len(bucket_file_lst.data) == 1
        # fetch file s.t. it can be linked to result bucket
        bucket_file = bucket_file_lst.data[0]
        analysis_bucket = core_client.get_analysis_bucket(client_id, "RESULT")
        # link file to analysis
        core_client.link_bucket_file_to_analysis(
            analysis_bucket.id, bucket_file.id, bucket_file.name
        )
        # remove from local minio
        minio.remove_object(bucket_name, object_name)
    finally:
        # docs are wrong here. resp could be uninitialized so this is a necessary check.
        if minio_resp is not None:
            minio_resp.close()
            minio_resp.release_conn()


@router.put(
    "/",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Upload file as final result to Hub",
    operation_id="putFinalResult",
)
async def submit_final_result_to_hub(
    client_id: Annotated[str, Depends(get_client_id)],
    file: UploadFile,
    background_tasks: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
    local_minio: Annotated[Minio, Depends(get_local_minio)],
    core_client: Annotated[FlameCoreClient, Depends(get_core_client)],
    storage_client: Annotated[FlameStorageClient, Depends(get_storage_client)],
):
    """Upload a file as a final result to the FLAME Hub.
    Returns a 204 on success.
    This endpoint returns immediately and submits the file in the background."""
    object_id = uuid.uuid4()
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
        local_minio,
        settings.minio.bucket,
        object_name,
        core_client,
        storage_client,
        client_id,
    )
