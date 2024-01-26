from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from minio import Minio

from project.config import Settings


@lru_cache
def get_settings():
    return Settings()


def get_minio(
    settings: Annotated[Settings, Depends(get_settings)],
):
    minio = settings.minio

    return Minio(
        minio.endpoint,
        access_key=minio.access_key,
        secret_key=minio.secret_key,
        region=minio.region,
        secure=minio.use_ssl,
    )
