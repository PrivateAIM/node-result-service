import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, UploadFile, Depends, HTTPException
from minio import Minio, S3Error
from pydantic import BaseModel, HttpUrl
from starlette import status
from starlette.requests import Request
from starlette.responses import StreamingResponse

from project.config import Settings
from project.dependencies import get_settings, get_local_minio, get_client_id

router = APIRouter()
logger = logging.getLogger(__name__)


class ScratchUploadResponse(BaseModel):
    url: HttpUrl


@router.put(
    "/",
    response_model=ScratchUploadResponse,
)
async def upload_to_scratch(
    client_id: Annotated[str, Depends(get_client_id)],
    file: UploadFile,
    settings: Annotated[Settings, Depends(get_settings)],
    minio: Annotated[Minio, Depends(get_local_minio)],
    request: Request,
):
    object_id = str(uuid.uuid4())

    minio.put_object(
        settings.minio.bucket,
        f"scratch/{client_id}/{object_id}",
        data=file.file,
        length=file.size,
        content_type=file.content_type or "application/octet-stream",
    )

    return ScratchUploadResponse(
        url=str(
            request.url_for(
                "read_from_scratch",
                object_id=object_id,
            )
        ),
    )


@router.get("/{object_id}")
async def read_from_scratch(
    client_id: Annotated[str, Depends(get_client_id)],
    object_id: uuid.UUID,
    settings: Annotated[Settings, Depends(get_settings)],
    minio: Annotated[Minio, Depends(get_local_minio)],
):
    try:
        response = minio.get_object(
            settings.minio.bucket, f"scratch/{client_id}/{object_id}"
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
