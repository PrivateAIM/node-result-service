import uuid
from typing import Annotated

from fastapi import APIRouter, UploadFile, Depends
from minio import Minio
from pydantic import BaseModel, HttpUrl
from starlette.requests import Request
from starlette.responses import StreamingResponse

from project.config import Settings
from project.dependencies import get_settings, get_minio, get_client_id

router = APIRouter()


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
    minio: Annotated[Minio, Depends(get_minio)],
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
    minio: Annotated[Minio, Depends(get_minio)],
):
    response = minio.get_object(
        settings.minio.bucket, f"scratch/{client_id}/{object_id}"
    )

    return StreamingResponse(
        response,
        media_type=response.headers.get("Content-Type", "application/octet-stream"),
    )
