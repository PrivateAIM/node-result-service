import io
import logging
import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, UploadFile, Depends, HTTPException, BackgroundTasks
from minio import Minio
from pydantic import BaseModel, HttpUrl
from starlette import status
from starlette.requests import Request
from starlette.responses import StreamingResponse

from project.config import Settings
from project.dependencies import (
    get_settings,
    get_local_minio,
    get_client_id,
    get_api_client,
)
from project.hub import FlameHubClient, format_analysis_bucket_name

router = APIRouter()
logger = logging.getLogger(__name__)

# TODO fix this jank
object_id_to_hub_bucket_dict: dict[str, Optional[str]] = {}


class IntermediateUploadResponse(BaseModel):
    url: HttpUrl


def __bg_upload_to_remote(
    minio: Minio,
    bucket_name: str,
    object_name: str,
    api: FlameHubClient,
    client_id: str,
    object_id: str,
):
    logger.info(
        "__bg_upload_to_remote: bucket `%s`, object `%s`", bucket_name, object_name
    )

    minio_resp = None

    try:
        minio_resp = minio.get_object(bucket_name, object_name)
        bucket_file_lst = api.upload_to_bucket(
            format_analysis_bucket_name(client_id, "TEMP"),
            object_name,
            io.BytesIO(minio_resp.data),
            minio_resp.headers.get("Content-Type", "application/octet-stream"),
        )

        assert len(bucket_file_lst.data) == 1
        bucket_file = bucket_file_lst.data[0]
        api.link_bucket_file_to_analysis(
            client_id, bucket_file.id, bucket_file.name, "TEMP"
        )
        object_id_to_hub_bucket_dict[object_id] = str(bucket_file.id)
        minio.remove_object(bucket_name, object_name)
    finally:
        if minio is not None:
            minio_resp.close()
            minio_resp.release_conn()


@router.put(
    "/",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=IntermediateUploadResponse,
    summary="Upload file as intermediate result to Hub",
    operation_id="putIntermediateResult",
)
async def submit_intermediate_result_to_hub(
    client_id: Annotated[str, Depends(get_client_id)],
    file: UploadFile,
    settings: Annotated[Settings, Depends(get_settings)],
    minio: Annotated[Minio, Depends(get_local_minio)],
    request: Request,
    api_client: Annotated[FlameHubClient, Depends(get_api_client)],
    background_tasks: BackgroundTasks,
):
    """Upload a file as an intermediate result to the FLAME Hub.
    Returns a 202 on success.
    This endpoint returns immediately and submits the file in the background."""
    object_id = str(uuid.uuid4())
    object_name = f"temp/{client_id}/{object_id}"

    minio.put_object(
        settings.minio.bucket,
        object_name,
        data=file.file,
        length=file.size,
        content_type=file.content_type or "application/octet-stream",
    )

    object_id_to_hub_bucket_dict[object_id] = None

    background_tasks.add_task(
        __bg_upload_to_remote,
        minio,
        settings.minio.bucket,
        object_name,
        api_client,
        client_id,
        object_id,
    )

    return IntermediateUploadResponse(
        url=str(
            request.url_for(
                "retrieve_intermediate_result_from_hub",
                object_id=object_id,
            )
        ),
    )


@router.get(
    "/{object_id}",
    summary="Get intermediate result as file to Hub",
    operation_id="getIntermediateResult",
    # client id is not actually used here but required for auth. having this
    # as a path dependency makes pycharm stop complaining about unused params.
    dependencies=[Depends(get_client_id)],
)
async def retrieve_intermediate_result_from_hub(
    object_id: uuid.UUID,
    api_client: Annotated[FlameHubClient, Depends(get_api_client)],
):
    """Get an intermediate result as file from the FLAME Hub."""
    object_id_str = str(object_id)

    if (
        object_id_str not in object_id_to_hub_bucket_dict
        or object_id_to_hub_bucket_dict[object_id_str] is None
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Object with ID {object_id} does not exist",
        )

    bucket_file_id = object_id_to_hub_bucket_dict[object_id_str]

    async def _stream_bucket_file():
        for b in api_client.stream_bucket_file(bucket_file_id):
            yield b

    return StreamingResponse(_stream_bucket_file())
