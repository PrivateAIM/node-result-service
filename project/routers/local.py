import logging
import re
import uuid
from typing import Annotated

import flame_hub
import peewee as pw
from fastapi import Depends, UploadFile, APIRouter, HTTPException, File, Form
from minio import Minio, S3Error
from pydantic import BaseModel, HttpUrl, Field
from starlette import status
from starlette.requests import Request
from starlette.responses import StreamingResponse

from project import crud
from project.config import Settings
from project.dependencies import (
    get_client_id,
    get_settings,
    get_local_minio,
    get_postgres_db,
    get_core_client,
)

router = APIRouter()
logger = logging.getLogger(__name__)

_TAG_PATTERN = re.compile(r"[a-z0-9]{1,2}|[a-z0-9][a-z0-9-]{,30}[a-z0-9]")


def is_valid_tag(tag: str) -> bool:
    return _TAG_PATTERN.fullmatch(tag) is not None


class LocalUploadResponse(BaseModel):
    url: HttpUrl


class LocalTag(BaseModel):
    name: str
    url: HttpUrl


class LocalTagListResponse(BaseModel):
    tags: Annotated[list[LocalTag], Field(default_factory=list)]


class LocalTaggedResult(BaseModel):
    filename: str
    url: HttpUrl


class LocalTaggedResultListResponse(BaseModel):
    results: Annotated[list[LocalTaggedResult], Field(default_factory=list)]


def _get_project_id_for_analysis_or_raise(core_client: flame_hub.CoreClient, analysis_id: str):
    analysis = core_client.get_analysis(analysis_id)

    if analysis is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis with ID {analysis_id} not found",
        )

    return str(analysis.project_id)


@router.put(
    "/",
    response_model=LocalUploadResponse,
    summary="Upload file as intermediate result to local storage",
    operation_id="putLocalResult",
)
async def submit_intermediate_result_to_local(
    client_id: Annotated[str, Depends(get_client_id)],
    file: Annotated[UploadFile, File()],
    settings: Annotated[Settings, Depends(get_settings)],
    minio: Annotated[Minio, Depends(get_local_minio)],
    db: Annotated[pw.PostgresqlDatabase, Depends(get_postgres_db)],
    core_client: Annotated[flame_hub.CoreClient, Depends(get_core_client)],
    request: Request,
    tag: Annotated[str | None, Form()] = None,
):
    """Upload a file as a local result.
    Returns a 200 on success.
    This endpoint uploads the file and returns a link with which it can be retrieved.
    An optional tag can be supplied to group the file with other files."""
    has_tag = tag is not None

    if has_tag:
        if not is_valid_tag(tag):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid tag `{tag}`",
            )

    object_id = uuid.uuid4()
    object_name = f"local/{client_id}/{object_id}"

    minio.put_object(
        settings.minio.bucket,
        object_name,
        data=file.file,
        length=file.size,
        content_type=file.content_type or "application/octet-stream",
    )

    if has_tag:
        # retrieve project id from analysis
        project_id = _get_project_id_for_analysis_or_raise(core_client, client_id)

        with crud.bind_to(db):
            tag, _ = crud.Tag.get_or_create(tag_name=tag, project_id=project_id)
            # TODO more elegant solution for filename being None?
            result = crud.Result.create(
                client_id=client_id,
                object_id=object_id,
                filename=file.filename or "data.bin",
            )
            crud.TaggedResult.create(tag=tag, result=result)

    return LocalUploadResponse(
        url=str(
            request.url_for(
                "retrieve_intermediate_result_from_local",
                object_id=object_id,
            )
        )
    )


@router.get(
    "/tags",
    summary="Get tags for a specific project",
    operation_id="getProjectTags",
    response_model=LocalTagListResponse,
)
async def get_project_tags(
    client_id: Annotated[str, Depends(get_client_id)],
    core_client: Annotated[flame_hub.CoreClient, Depends(get_core_client)],
    db: Annotated[pw.PostgresqlDatabase, Depends(get_postgres_db)],
    request: Request,
):
    """Get a list of tags assigned to the project for an analysis.
    Returns a 200 on success."""
    project_id = _get_project_id_for_analysis_or_raise(core_client, client_id)

    with crud.bind_to(db):
        db_tags = crud.Tag.select().where(crud.Tag.project_id == project_id)

    return LocalTagListResponse(
        tags=[
            LocalTag(
                name=tag.tag_name,
                url=str(
                    request.url_for(
                        "get_results_by_project_tag",
                        tag_name=tag.tag_name,
                    )
                ),
            )
            for tag in db_tags
        ]
    )


@router.get(
    "/tags/{tag_name}",
    summary="Get results linked to a specific tag",
    operation_id="getTaggedResults",
    response_model=LocalTaggedResultListResponse,
)
async def get_results_by_project_tag(
    tag_name: str,
    client_id: Annotated[str, Depends(get_client_id)],
    db: Annotated[pw.PostgresqlDatabase, Depends(get_postgres_db)],
    core_client: Annotated[flame_hub.CoreClient, Depends(get_core_client)],
    request: Request,
):
    """Get a list of files assigned to a tag.
    Returns a 200 on success."""
    project_id = _get_project_id_for_analysis_or_raise(core_client, client_id)

    with crud.bind_to(db):
        db_tagged_results = (
            crud.Result.select()
            .join(crud.TaggedResult)
            .join(crud.Tag)
            .where((crud.Tag.project_id == project_id) & (crud.Tag.tag_name == tag_name))
        )

    return LocalTaggedResultListResponse(
        results=[
            LocalTaggedResult(
                filename=result.filename,
                url=str(
                    request.url_for(
                        "retrieve_intermediate_result_from_local",
                        object_id=result.object_id,
                    )
                ),
            )
            for result in db_tagged_results
        ],
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
    """Geta local result as file."""
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
