import json
import logging.config
import os.path
from contextlib import asynccontextmanager
from pathlib import Path

import flame_hub
import tomli
import uvicorn
from fastapi import FastAPI, HTTPException
from starlette import status
from starlette.requests import Request

from project.routers import final, intermediate, local


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs("logs", exist_ok=True)
    log_config_file_path = os.path.join(os.path.dirname(__file__), "..", "config", "logging.json")

    with open(log_config_file_path) as f:
        log_config = json.load(f)

    logging.config.dictConfig(log_config)

    yield


with open(Path(__file__).parent.parent / "pyproject.toml", mode="rb") as f:
    pyproject_data = tomli.load(f)

with open(Path(__file__).parent.parent / "README.md", mode="r") as f:
    app_description = f.read()

app_version = pyproject_data["tool"]["poetry"]["version"]
app_summary = pyproject_data["tool"]["poetry"]["description"]

app = FastAPI(
    title="FLAME Node Result Service",
    summary=app_summary,
    version=app_version,
    lifespan=lifespan,
    description=app_description,
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
        "identifier": "Apache-2.0",
    },
    openapi_tags=[
        {
            "name": "final",
            "description": "Upload final results to FLAME Hub",
        },
        {
            "name": "intermediate",
            "description": "Upload intermediate results to FLAME Hub",
        },
        {
            "name": "local",
            "description": "Upload intermediate results to local storage",
        },
    ],
)


@app.get("/healthz", summary="Check service readiness", operation_id="getHealth")
async def do_healthcheck():
    """Check whether the service is ready to process requests. Responds with a 200 on success."""
    return {"status": "ok"}


logger = logging.getLogger(__name__)


# re-raise as a http exception
@app.exception_handler(flame_hub.HubAPIError)
async def handle_hub_api_error(request: Request, exc: flame_hub.HubAPIError):
    logger.exception("unexpected response from remote", exc_info=exc)

    remote_status_code = "unknown"

    if exc.error_response is not None:
        remote_status_code = exc.error_response.status_code

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Hub returned an unexpected response ({remote_status_code})",
    )


app.include_router(
    final.router,
    prefix="/final",
    tags=["final"],
)

app.include_router(
    intermediate.router,
    prefix="/intermediate",
    tags=["intermediate"],
)

app.include_router(
    local.router,
    prefix="/local",
    tags=["local"],
)


def run_server():
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run_server()
