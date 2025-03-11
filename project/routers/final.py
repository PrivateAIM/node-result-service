import logging
from typing import Annotated

import flame_hub
from fastapi import APIRouter, Depends, UploadFile, HTTPException
from starlette import status

from project.dependencies import (
    get_client_id,
    get_core_client,
    get_storage_client,
)

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
    core_client: Annotated[flame_hub.CoreClient, Depends(get_core_client)],
    storage_client: Annotated[flame_hub.StorageClient, Depends(get_storage_client)],
):
    """Upload a file as a final result to the FLAME Hub.
    Returns a 204 on success."""
    # fetch analysis bucket
    analysis_bucket_lst = core_client.find_analysis_buckets(
        filter={"analysis_id": client_id, "type": "RESULT"}
    )

    if len(analysis_bucket_lst) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Result bucket for analysis with ID {client_id} was not found",
        )

    analysis_bucket = analysis_bucket_lst.pop()

    # upload to remote
    bucket_file_lst = storage_client.upload_to_bucket(
        analysis_bucket.external_id,
        {
            "file_name": file.filename,
            "content": file.file,
            "content_type": file.content_type or "application/octet-stream",
        },
    )

    if len(bucket_file_lst) != 1:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Expected single uploaded file to be returned by storage service, got {len(bucket_file_lst)}",
        )

    # fetch file s.t. it can be linked to result bucket
    bucket_file = bucket_file_lst.pop()

    # link file to analysis
    core_client.create_analysis_bucket_file(
        bucket_file.name, bucket_file, analysis_bucket
    )
