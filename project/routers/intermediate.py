import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, UploadFile, Depends, HTTPException
from pydantic import BaseModel, HttpUrl
from starlette import status
from starlette.requests import Request
from starlette.responses import StreamingResponse

from project.dependencies import (
    get_client_id,
    get_core_client,
    get_storage_client,
)
from project.hub import FlameCoreClient, FlameStorageClient

router = APIRouter()
logger = logging.getLogger(__name__)


class IntermediateUploadResponse(BaseModel):
    url: HttpUrl
    object_id: uuid.UUID


@router.put(
    "/",
    response_model=IntermediateUploadResponse,
    summary="Upload file as intermediate result to Hub",
    operation_id="putIntermediateResult",
)
async def submit_intermediate_result_to_hub(
    client_id: Annotated[str, Depends(get_client_id)],
    file: UploadFile,
    request: Request,
    core_client: Annotated[FlameCoreClient, Depends(get_core_client)],
    storage_client: Annotated[FlameStorageClient, Depends(get_storage_client)],
):
    """Upload a file as an intermediate result to the FLAME Hub.
    Returns a 200 on success.
    This endpoint uploads the file and returns a link with which it can be retrieved."""

    analysis_bucket = core_client.get_analysis_bucket(client_id, "TEMP")

    bucket_file_lst = storage_client.upload_to_bucket(
        analysis_bucket.external_id,
        file.filename,
        await file.read(),  # TODO should be chunked for large files
        file.content_type or "application/octet-stream",
    )

    if len(bucket_file_lst.data) != 1:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Expected single uploaded file to be returned by storage service, got {len(bucket_file_lst.data)}",
        )

    # retrieve uploaded bucket file
    bucket_file = bucket_file_lst.data[0]

    # link bucket file to analysis
    core_client.link_bucket_file_to_analysis(
        analysis_bucket.id, bucket_file.id, bucket_file.name
    )

    return IntermediateUploadResponse(
        object_id=bucket_file.id,
        url=str(
            request.url_for(
                "retrieve_intermediate_result_from_hub",
                object_id=bucket_file.id,
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
    storage_client: Annotated[FlameStorageClient, Depends(get_storage_client)],
):
    """Get an intermediate result as file from the FLAME Hub."""
    object_id_str = str(object_id)

    if storage_client.get_bucket_file_by_id(object_id_str) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Object with ID {object_id} does not exist",
        )

    async def _stream_bucket_file():
        for b in storage_client.stream_bucket_file(object_id_str):
            yield b

    return StreamingResponse(_stream_bucket_file())
