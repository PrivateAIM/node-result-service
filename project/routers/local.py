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
    Perform a binary search to determine the smallest noise_multiplier that achieves
    the desired epsilon value for differential privacy given the dataset and training setup.
    """
    steps = (dataset_size // batch_size) * epochs  # Total number of training steps
    low = 0.5  # Initial lower bound for noise
    high = 10.0  # Initial upper bound
    tolerance = 0.01  # Acceptable tolerance in search
    best_noise = None

    # Binary search loop to find a suitable noise multiplier
    while high - low > tolerance:
        mid = (low + high) / 2
        accountant = RDPAccountant()

        # Simulate training steps with current noise level
        for _ in range(steps):
            accountant.step(noise_multiplier=mid, sample_rate=sample_rate)

        eps = accountant.get_epsilon(delta=target_delta)

        # Adjust search range based on epsilon result
        if eps > target_epsilon:
            low = mid
        else:
            best_noise = mid
            high = mid

    # Check if a suitable noise multiplier was found
    if best_noise is None:
        eps_high = accountant.get_epsilon(delta=target_delta)
        raise ValueError(f"No valid noise_multiplier found. ε at max noise ({high}): {eps_high}")

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
    summary="Train model with Differential Privacy using fixed ε-budget",
    operation_id="trainWithDifferentialPrivacyBudget",
)
async def train_with_differential_privacy(
    model_file: Annotated[UploadFile, File(...)],  # Uploaded PyTorch model weights
    dataset_file: Annotated[UploadFile, File(...)],  # Uploaded CSV dataset
    target_epsilon: Annotated[float, Form(...)],  # Desired privacy budget ε
    max_grad_norm: Annotated[float, Form(...)],  # Maximum gradient norm for DP-SGD clipping
    noise_multiplier: Annotated[float | None, Form()] = None,  # Optional DP noise multiplier
    batch_size: Annotated[int, Form()] = 32,  # Mini-batch size
):
    """
    Train a PyTorch model with differential privacy using Opacus.
    Training runs until a fixed ε (privacy budget) is reached or a max number of epochs is hit.
    """
    try:
        # Ensure privacy parameters and batch size are valid
        if target_epsilon <= 0:
            raise HTTPException(400, detail="target_epsilon must be greater than 0.")

        if batch_size <= 0:
            raise HTTPException(400, detail="batch_size must be greater than 0.")

        # Define a simple fully-connected model as an example
        class SimpleNet(nn.Module):
            def __init__(self):
                super().__init__()
                self.fc = nn.Linear(4, 2)  # Expect 4 input features, output 2 classes

            def forward(self, x):
                return self.fc(x)

        # Load model state dictionary from uploaded file
        model = SimpleNet()
        state_dict = torch.load(BytesIO(await model_file.read()))
        try:
            model.load_state_dict(state_dict)
        except RuntimeError as e:
            raise HTTPException(400, detail=f"Model structure mismatch: {str(e)}")
        model.train()  # Set model to training mode

        # Read and decode uploaded dataset (assumed to be CSV with 4 features + 1 label)
        dataset_bytes = await dataset_file.read()
        lines = dataset_bytes.decode("utf-8-sig").splitlines()

        # Handle CSVs that use semicolons instead of commas
        if ";" in lines[0]:
            lines = [line.replace(";", ",") for line in lines]

        parsed_data = []
        for line in lines:
            try:
                values = [float(val) for val in line.strip().split(",")]
                parsed_data.append(values)
            except ValueError:
                continue  # Skip lines with invalid format

        if not parsed_data:
            raise HTTPException(400, detail="Dataset contains no valid rows.")

        # Convert parsed data to PyTorch tensors
        data = torch.tensor(parsed_data)
        if data.shape[1] != 5:
            raise HTTPException(400, detail="Each row must have 4 features + 1 label.")

        x = data[:, :-1]  # Features
        y = data[:, -1].long()  # Labels
        dataset = TensorDataset(x, y)
        dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

        # Define a basic optimizer and loss function
        optimizer = optim.SGD(model.parameters(), lr=0.01)
        loss_fn = nn.CrossEntropyLoss()

        # Differential privacy configuration
        delta = 1e-5  # Typical choice for delta in DP (usually 1/n)
        sample_rate = batch_size / len(dataset)

        auto_estimated = False
        if noise_multiplier is None:
            auto_estimated = True
            try:
                # Estimate number of epochs based on target epsilon
                estimate_epochs = max(20, int(100 / target_epsilon))
                noise_multiplier = find_noise_multiplier(
                    target_epsilon=target_epsilon,
                    target_delta=delta,
                    sample_rate=sample_rate,
                    epochs=estimate_epochs,
                    dataset_size=len(dataset),
                    batch_size=batch_size
                )
                logger.info(f"Automatically estimated noise_multiplier: {noise_multiplier}")
            except Exception as e:
                raise HTTPException(500, detail=f"Failed to estimate noise_multiplier: {str(e)}")

        # Initialize the PrivacyEngine and make the training loop private
        privacy_engine = PrivacyEngine()
        model, optimizer, dataloader = privacy_engine.make_private(
            module=model,
            optimizer=optimizer,
            data_loader=dataloader,
            noise_multiplier=noise_multiplier,
            max_grad_norm=max_grad_norm,
        )

        # Training loop with early stopping when epsilon budget is spent
        epsilon_spent = 0.0
        epoch = 0
        max_epochs = 500  # Safety cap to prevent infinite loops

        while epsilon_spent < target_epsilon and epoch < max_epochs:
            for batch_x, batch_y in dataloader:
                optimizer.zero_grad()
                output = model(batch_x)
                loss = loss_fn(output, batch_y)
                loss.backward()
                optimizer.step()

            epoch += 1
            epsilon_spent = privacy_engine.get_epsilon(delta=delta)
            logger.info(f"Epoch {epoch} completed – ε spent: {epsilon_spent:.4f}")

            if epsilon_spent >= target_epsilon:
                logger.info(f"Training stopped after {epoch} epochs – target ε={target_epsilon} reached.")
                break

        # Return final training metadata to the client
        return {
            "message": "Model trained under privacy budget",
            "target_epsilon": target_epsilon,
            "epsilon_spent": round(epsilon_spent, 4),
            "noise_multiplier": noise_multiplier,
            "epochs_used": epoch,
            "delta": delta,
            "sample_rate": round(sample_rate, 6),
            "auto_estimated_noise_multiplier": auto_estimated,
        }

    except Exception as e:
        logger.exception("Differentially private training failed")
        raise HTTPException(
            status_code=500,
            detail=f"Training failed due to internal error: {str(e)}",
        )
