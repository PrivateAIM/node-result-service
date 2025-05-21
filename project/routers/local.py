import logging
import re
import uuid
from typing import Annotated
from io import BytesIO

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

# Opacus and PyTorch for DP-Training
from opacus import PrivacyEngine
from opacus.accountants import RDPAccountant
from torch.utils.data import DataLoader, TensorDataset
import torch
import torch.nn as nn
import torch.optim as optim

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

def find_noise_multiplier(
    target_epsilon: float,
    target_delta: float,
    sample_rate: float,
    epochs: int,
    dataset_size: int,
    batch_size: int
) -> float:
    """
    Finds the smallest noise_multiplier that meets the target budget ε for a given sample_rate and epochs.
    Uses the official RDPAccountant API from Opacus.
    """
    import numpy as np

    steps = (dataset_size // batch_size) * epochs
    low = 0.5
    high = 10.0
    tolerance = 0.01
    best_noise = None

    while high - low > tolerance:
        mid = (low + high) / 2
        accountant = RDPAccountant()

        for _ in range(steps):
            accountant.step(noise_multiplier=mid, sample_rate=sample_rate)

        eps = accountant.get_epsilon(delta=target_delta)

        if eps > target_epsilon:
            low = mid
        else:
            best_noise = mid
            high = mid

    if best_noise is None:
        raise ValueError("No suitable noise_multiplier found.")

    return round(best_noise, 4)


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

@router.post(
    "/train-private",
    summary="Train model with Differential Privacy using Opacus and fixed budget",
    operation_id="trainWithDifferentialPrivacyBudget",
)
async def train_with_differential_privacy(
    model_file: Annotated[UploadFile, File(...)],
    dataset_file: Annotated[UploadFile, File(...)],
    target_epsilon: Annotated[float, Form(...)],
    max_grad_norm: Annotated[float, Form(...)],
    epochs: Annotated[int, Form(ge=1)] = 5,
):
    """
    Trains an uploaded PyTorch model with differential privacy
    based on a fixed privacy budget (ε).
    """

    try:
        # Define model structure
        class SimpleNet(nn.Module):
            def __init__(self):
                super().__init__()
                self.fc = nn.Linear(4, 2)

            def forward(self, x):
                return self.fc(x)

        # Load model
        model = SimpleNet()
        model_bytes = await model_file.read()
        buffer = BytesIO(model_bytes)
        state_dict = torch.load(buffer)
        model.load_state_dict(state_dict)
        model.train()

        # Read CSV data
        dataset_bytes = await dataset_file.read()
        lines = dataset_bytes.decode("utf-8-sig").splitlines()

        if ";" in lines[0]:
            lines = [line.replace(";", ",") for line in lines]

        parsed_data = []
        for line in lines:
            try:
                values = [float(val) for val in line.strip().split(",")]
                parsed_data.append(values)
            except ValueError:
                continue

        if not parsed_data:
            raise HTTPException(status_code=400, detail="Keine gültigen Datenzeilen im Dataset.")

        data = torch.tensor(parsed_data)

        if data.shape[1] != 5:
            raise HTTPException(status_code=400, detail="Dataset muss 4 Features + 1 Label enthalten.")

        x = data[:, :-1]
        y = data[:, -1].long()

        dataset = TensorDataset(x, y)
        batch_size = 32
        dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

        # Optimierer
        optimizer = optim.SGD(model.parameters(), lr=0.01)

        # Calculate noise
        delta = 1e-5
        sample_rate = batch_size / len(dataset)

        noise_multiplier = find_noise_multiplier(
            target_epsilon=target_epsilon,
            target_delta=delta,
            sample_rate=sample_rate,
            epochs=epochs,
            dataset_size=len(dataset),
            batch_size=batch_size
        )

        logger.info(f"Training mit ε={target_epsilon}, δ={delta}, noise_multiplier={noise_multiplier}")

        # Activate Privacy Engine
        privacy_engine = PrivacyEngine()
        model, optimizer, dataloader = privacy_engine.make_private(
            module=model,
            optimizer=optimizer,
            data_loader=dataloader,
            noise_multiplier=noise_multiplier,
            max_grad_norm=max_grad_norm,
        )

        # Training
        loss_fn = nn.CrossEntropyLoss()
        for epoch in range(epochs):
            for batch_x, batch_y in dataloader:
                optimizer.zero_grad()
                outputs = model(batch_x)
                loss = loss_fn(outputs, batch_y)
                loss.backward()
                optimizer.step()

        epsilon_spent = privacy_engine.get_epsilon(delta=delta)

        return {
            "message": "Model trained under DP constraints",
            "target_epsilon": target_epsilon,
            "epsilon_spent": epsilon_spent,
            "noise_multiplier_used": noise_multiplier,
        }

    except Exception as e:
        logger.exception("Training failed")
        raise HTTPException(status_code=500, detail=f"Training failed: {str(e)}")
