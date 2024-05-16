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
    get_access_token,
)
from project.hub import AccessToken, ApiWrapper

router = APIRouter()
logger = logging.getLogger(__name__)

# TODO fix this jank
object_id_to_hub_bucket_dict: dict[str, Optional[str]] = {}


class ScratchUploadResponse(BaseModel):
    url: HttpUrl


def __bg_upload_to_remote(
    minio: Minio,
    bucket_name: str,
    object_name: str,
    api: ApiWrapper,
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
            f"analysis-temp-files.{client_id}",
            object_name,
            io.BytesIO(minio_resp.data),
            minio_resp.headers.get("Content-Type", "application/octet-stream"),
        )

        assert len(bucket_file_lst) == 1
        bucket_file = bucket_file_lst[0]
        api.link_file_to_analysis(client_id, bucket_file.id, bucket_file.name, "TEMP")
        object_id_to_hub_bucket_dict[object_id] = bucket_file.id
        minio.remove_object(bucket_name, object_name)
    finally:
        if minio is not None:
            minio_resp.close()
            minio_resp.release_conn()


@router.put(
    "/",
    response_model=ScratchUploadResponse,
    summary="Upload file to local object storage",
    operation_id="putIntermediateFile",
)
async def upload_to_scratch(
    client_id: Annotated[str, Depends(get_client_id)],
    file: UploadFile,
    settings: Annotated[Settings, Depends(get_settings)],
    minio: Annotated[Minio, Depends(get_local_minio)],
    request: Request,
    api_access_token: Annotated[AccessToken, Depends(get_access_token)],
    background_tasks: BackgroundTasks,
):
    """Upload a file to the local S3 instance.
    The file is not forwarded to the FLAME hub.
    Responds with a 200 on success and a link to the endpoint for fetching the uploaded file.

    This endpoint is to be used for submitting intermediate results of a federated analysis.
    """
    object_id = str(uuid.uuid4())
    object_name = f"temp/{client_id}/{object_id}"

    minio.put_object(
        settings.minio.bucket,
        object_name,
        data=file.file,
        length=file.size,
        content_type=file.content_type or "application/octet-stream",
    )

    api = ApiWrapper(str(settings.hub.api_base_url), api_access_token.access_token)
    object_id_to_hub_bucket_dict[object_id] = None

    background_tasks.add_task(
        __bg_upload_to_remote,
        minio,
        settings.minio.bucket,
        object_name,
        api,
        client_id,
        object_id,
    )

    return ScratchUploadResponse(
        url=str(
            request.url_for(
                "read_from_scratch",
                object_id=object_id,
            )
        ),
    )


@router.get(
    "/{object_id}",
    summary="Get file from local object storage",
    operation_id="getIntermediateFile",
)
async def read_from_scratch(
    client_id: Annotated[str, Depends(get_client_id)],
    object_id: uuid.UUID,
    settings: Annotated[Settings, Depends(get_settings)],
    api_access_token: Annotated[AccessToken, Depends(get_access_token)],
):
    """Get a file from the local S3 instance.
    The file must have previously been uploaded using the PUT method of this endpoint.
    Responds with a 200 on success and the requested file in the response body.

    This endpoint is to be used for retrieving intermediate results of a federated analysis.
    """
    api = ApiWrapper(str(settings.hub.api_base_url), api_access_token.access_token)
    oid = str(object_id)

    if (
        oid not in object_id_to_hub_bucket_dict
        or object_id_to_hub_bucket_dict[oid] is None
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Object with ID {oid} does not exist",
        )

    bucket_file_id = object_id_to_hub_bucket_dict[oid]

    async def _stream_bucket_file():
        for b in api.stream_bucket_file(bucket_file_id):
            yield b

    return StreamingResponse(_stream_bucket_file())
