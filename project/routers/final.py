import logging
from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile, HTTPException
from starlette import status

from project.dependencies import (
    get_client_id,
    get_core_client,
    get_storage_client,
)
from project.hub import FlameCoreClient, FlameStorageClient

router = APIRouter()
logger = logging.getLogger(__name__)


@router.put(
    "/",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Upload file as final result to Hub",
    operation_id="putFinalResult",
)
async def submit_final_result_to_hub(
    client_id: Annotated[str, Depends(get_client_id)],
    file: UploadFile,
    core_client: Annotated[FlameCoreClient, Depends(get_core_client)],
    storage_client: Annotated[FlameStorageClient, Depends(get_storage_client)],
):
    """Upload a file as a final result to the FLAME Hub.
    Returns a 204 on success."""
    # fetch analysis bucket
    analysis_bucket = core_client.get_analysis_bucket(client_id, "RESULT")

    # upload to remote
    bucket_file_lst = storage_client.upload_to_bucket(
        analysis_bucket.external_id,
        file.filename,
        file.file,
        file.content_type or "application/octet-stream",
    )

    if len(bucket_file_lst.data) != 1:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Expected single uploaded file to be returned by storage service, got {len(bucket_file_lst.data)}",
        )

    # fetch file s.t. it can be linked to result bucket
    bucket_file = bucket_file_lst.data[0]
    analysis_bucket = core_client.get_analysis_bucket(client_id, "RESULT")

    # link file to analysis
    core_client.link_bucket_file_to_analysis(
        analysis_bucket.id, bucket_file.id, bucket_file.name
    )
