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
    get_api_client,
)
from project.hub_ng import FlameHubClient, format_analysis_bucket_name

router = APIRouter()
logger = logging.getLogger(__name__)


def __bg_upload_to_remote(
    minio: Minio,
    bucket_name: str,
    object_name: str,
    api: FlameHubClient,
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
        # upload to remote
        bucket_file_lst = api.upload_to_bucket(
            format_analysis_bucket_name(client_id, "RESULT"),
            object_name,
            io.BytesIO(minio_resp.data),
            minio_resp.headers.get("Content-Type", "application/octet-stream"),
        )

        # check that only one file has been submitted
        assert len(bucket_file_lst.data) == 1
        # fetch file s.t. it can be linked
        bucket_file = bucket_file_lst.data[0]
        # link file to analysis
        api.link_bucket_file_to_analysis(
            client_id, bucket_file.id, bucket_file.name, "RESULT"
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
    summary="Upload file to submit to Hub",
    operation_id="putResultFile",
)
async def upload_to_remote(
    client_id: Annotated[str, Depends(get_client_id)],
    file: UploadFile,
    background_tasks: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
    local_minio: Annotated[Minio, Depends(get_local_minio)],
    api_client: Annotated[FlameHubClient, Depends(get_api_client)],
):
    """Upload a file to the local S3 instance and send it to FLAME Hub in the background.
    The request is successful if the file was uploaded to the local S3 instance.
    Responds with a 204 on success.

    This endpoint is to be used for submitting final results of a federated analysis.

    Currently, there is no way of determining the status or progress of the upload to the FLAME Hub."""
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
        api_client,
        client_id,
    )
