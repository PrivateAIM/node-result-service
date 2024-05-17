import logging
import uuid
from typing import Annotated

from fastapi import Depends, UploadFile, APIRouter, HTTPException
from minio import Minio, S3Error
from pydantic import BaseModel, HttpUrl
from starlette import status
from starlette.requests import Request
from starlette.responses import StreamingResponse

from project.config import Settings
from project.dependencies import get_client_id, get_settings, get_local_minio

router = APIRouter()
logger = logging.getLogger(__name__)


class LocalUploadResponse(BaseModel):
    url: HttpUrl


@router.put(
    "/",
    response_model=LocalUploadResponse,
    summary="Upload file as intermediate result to local storage",
    operation_id="putLocalResult",
)
async def submit_intermediate_result_to_local(
    client_id: Annotated[str, Depends(get_client_id)],
    file: UploadFile,
    settings: Annotated[Settings, Depends(get_settings)],
    minio: Annotated[Minio, Depends(get_local_minio)],
    request: Request,
):
    object_id = uuid.uuid4()
    object_name = f"local/{client_id}/{object_id}"

    minio.put_object(
        settings.minio.bucket,
        object_name,
        data=file.file,
        length=file.size,
        content_type=file.content_type or "application/octet-stream",
    )

    return LocalUploadResponse(
        url=str(
            request.url_for(
                "retrieve_intermediate_result_from_local",
                object_id=object_id,
            )
        )
    )


@router.get(
    "/{object_id}",
    summary="Get intermediate result as file from local storage",
    operation_id="getLocalResult",
)
async def retrieve_intermediate_result_from_local(
    client_id: Annotated[str, Depends(get_client_id)],
    object_id: uuid.UUID,
    settings: Annotated[Settings, Depends(get_settings)],
    minio: Annotated[Minio, Depends(get_local_minio)],
):
    try:
        response = minio.get_object(
            settings.minio.bucket,
            f"local/{client_id}/{object_id}",
        )
    except S3Error as e:
        logger.exception(f"Could not get object `{object_id}` for client `{client_id}`")

        if e.code == "NoSuchKey":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Object with ID {object_id} does not exist",
            )

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unexpected error from object store",
        )

    return StreamingResponse(
        response,
        media_type=response.headers.get("Content-Type", "application/octet-stream"),
    )
