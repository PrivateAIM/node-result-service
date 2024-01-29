import json
import logging.config
import os.path
from contextlib import asynccontextmanager

from fastapi import FastAPI

from project.routers import upload, scratch


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs("logs", exist_ok=True)
    log_config_file_path = os.path.join(
        os.path.dirname(__file__), "..", "config", "logging.json"
    )

    with open(log_config_file_path) as f:
        log_config = json.load(f)

    logging.config.dictConfig(log_config)

    yield


app = FastAPI(lifespan=lifespan)

app.include_router(
    upload.router,
    prefix="/upload",
    tags=["upload"],
)

app.include_router(
    scratch.router,
    prefix="/scratch",
    tags=["scratch"],
)
