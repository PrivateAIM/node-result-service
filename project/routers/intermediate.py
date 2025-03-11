import logging
import uuid
from typing import Annotated

import flame_hub
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import APIRouter, UploadFile, Depends, HTTPException, File, Form
from pydantic import BaseModel, HttpUrl
from starlette import status
from starlette.requests import Request
from starlette.responses import StreamingResponse

from project import crypto
from project.dependencies import (
    get_client_id,
    get_core_client,
    get_storage_client,
    get_ecdh_private_key,
)

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
    file: Annotated[UploadFile, File()],
    request: Request,
    core_client: Annotated[flame_hub.CoreClient, Depends(get_core_client)],
    storage_client: Annotated[flame_hub.StorageClient, Depends(get_storage_client)],
    private_key: Annotated[ec.EllipticCurvePrivateKey, Depends(get_ecdh_private_key)],
    remote_node_id: Annotated[str | None, Form()] = None,
):
    """Upload a file as an intermediate result to the FLAME Hub.
    Returns a 200 on success.
    This endpoint uploads the file and returns a link with which it can be retrieved."""

    analysis_bucket_lst = core_client.find_analysis_buckets(filter={"analysis_id": client_id, "type": "TEMP"})

    if len(analysis_bucket_lst) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Temp bucket for analysis with ID {client_id} was not found",
        )

    analysis_bucket = analysis_bucket_lst.pop()

    # TODO this should be chunked for large files, will be addressed in a later version
    result_file = await file.read()

    # encryption requested
    if remote_node_id is not None:
        # fetch remote node
        remote_node = core_client.get_node(remote_node_id)

        # check if it has a public key assigned to it
        if remote_node.public_key is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Remote node with ID {remote_node_id} does not provide a public key",
            )

        # construct public key
        remote_public_key = crypto.load_ecdh_public_key_from_hex_string(remote_node.public_key)

        # encrypt result file
        result_file = crypto.encrypt_default(private_key, remote_public_key, result_file)

    bucket_file_lst = storage_client.upload_to_bucket(
        analysis_bucket.external_id,
        {
            "file_name": file.filename,
            "content": result_file,
            "content_type": file.content_type or "application/octet-stream",
        },
    )

    if len(bucket_file_lst) != 1:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Expected single uploaded file to be returned by storage service, got {len(bucket_file_lst)}",
        )

    # retrieve uploaded bucket file
    bucket_file = bucket_file_lst.pop()

    # link bucket file to analysis
    core_client.create_analysis_bucket_file(bucket_file.name, bucket_file, analysis_bucket)

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
    storage_client: Annotated[flame_hub.StorageClient, Depends(get_storage_client)],
):
    """Get an intermediate result as file from the FLAME Hub."""
    if storage_client.get_bucket_file(object_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Object with ID {object_id} does not exist",
        )

    async def _stream_bucket_file():
        for b in storage_client.stream_bucket_file(object_id):
            yield b

    return StreamingResponse(_stream_bucket_file())
