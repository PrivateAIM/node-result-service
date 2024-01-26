import uuid
from typing import Annotated

from fastapi import APIRouter, UploadFile, Depends
from minio import Minio
from pydantic import BaseModel, HttpUrl
from starlette.requests import Request
from starlette.responses import StreamingResponse

from project.config import Settings
from project.dependencies import get_settings, get_minio

router = APIRouter()


class ScratchUploadResponse(BaseModel):
    url: HttpUrl


@router.put(
    "/{project_id}",
    response_model=ScratchUploadResponse,
)
async def upload_to_scratch(
    project_id: uuid.UUID,
    file: UploadFile,
    settings: Annotated[Settings, Depends(get_settings)],
    minio: Annotated[Minio, Depends(get_minio)],
    request: Request,
):
    object_id = str(uuid.uuid4())

    minio.put_object(
        settings.minio.bucket,
        f"scratch/{project_id}/{object_id}",
        data=file.file,
        length=file.size,
        content_type=file.content_type or "application/octet-stream",
    )

    return ScratchUploadResponse(
        url=str(
            request.url_for(
                "read_from_scratch",
                project_id=f"{project_id}",
                object_id=object_id,
            )
        ),
    )


@router.get("/{project_id}/{object_id}")
async def read_from_scratch(
    project_id: uuid.UUID,
    object_id: uuid.UUID,
    settings: Annotated[Settings, Depends(get_settings)],
    minio: Annotated[Minio, Depends(get_minio)],
):
    response = minio.get_object(
        settings.minio.bucket, f"scratch/{project_id}/{object_id}"
    )

    return StreamingResponse(
        response,
        media_type=response.getheader("Content-Type", "application/octet-stream"),
    )
