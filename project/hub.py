import time
from datetime import datetime
from io import BytesIO
from typing import TypeVar, Generic, Literal, Optional
from urllib.parse import urljoin
from uuid import UUID

import httpx
from pydantic import BaseModel
from starlette import status

BucketType = Literal["CODE", "TEMP", "RESULT"]
ResourceT = TypeVar("ResourceT")


class AccessToken(BaseModel):
    access_token: str
    expires_in: int
    token_type: str
    scope: str
    refresh_token: str


class Project(BaseModel):
    id: UUID
    name: Optional[str]
    analyses: int
    created_at: datetime
    updated_at: datetime


class Analysis(BaseModel):
    id: UUID
    name: Optional[str]
    project_id: UUID
    created_at: datetime
    updated_at: datetime


class Bucket(BaseModel):
    id: UUID
    name: Optional[str]
    created_at: datetime
    updated_at: datetime


class BucketFile(BaseModel):
    id: UUID
    name: Optional[str]
    size: int
    directory: str
    hash: str
    bucket_id: UUID
    created_at: datetime
    updated_at: datetime


class AnalysisBucket(BaseModel):
    id: UUID
    type: BucketType
    external_id: UUID
    analysis_id: UUID
    created_at: datetime
    updated_at: datetime


class AnalysisBucketFile(BaseModel):
    id: UUID
    name: Optional[str]
    root: bool
    created_at: datetime
    updated_at: datetime
    external_id: UUID
    bucket_id: UUID
    analysis_id: Optional[UUID]


class ResourceListMeta(BaseModel):
    total: int


class ResourceList(BaseModel, Generic[ResourceT]):
    data: list[ResourceT]
    meta: ResourceListMeta


def _now():
    return int(time.time())


class FlamePasswordAuthClient:
    def __init__(
        self,
        username: str,
        password: str,
        base_url="https://auth.privateaim.net",
        token_expiration_leeway_seconds=60,
        force_acquire_on_init=False,
    ):
        self.base_url = base_url
        self._username = username
        self._password = password
        self._token_expiration_leeway_seconds = token_expiration_leeway_seconds
        self._current_access_token = None
        self._current_access_token_expires_at = 0

        if force_acquire_on_init:
            self._acquire_token()

    def _acquire_token(self):
        r = httpx.post(
            urljoin(self.base_url, "/token"),
            json={
                "grant_type": "password",
                "username": self._username,
                "password": self._password,
            },
        )

        r.raise_for_status()
        at = AccessToken(**r.json())

        self._current_access_token = at
        self._current_access_token_expires_at = _now() + at.expires_in

    def get_access_token_object(self) -> AccessToken:
        if self._current_access_token is None:
            self._acquire_token()
        elif (
            self._current_access_token_expires_at
            < _now() + self._token_expiration_leeway_seconds
        ):
            self._acquire_token()

        return self._current_access_token

    def get_access_token(self):
        return self.get_access_token_object().access_token

    def get_auth_bearer_header(self):
        return {
            "Authorization": f"Bearer {self.get_access_token()}",
        }


class FlameHubClient:
    def __init__(
        self,
        auth_client: FlamePasswordAuthClient,
        base_url="https://api.privateaim.net",
    ):
        self.base_url = base_url
        self.auth_client = auth_client

    def create_project(self, name: str) -> Project:
        r = httpx.post(
            urljoin(self.base_url, "/projects"),
            headers=self.auth_client.get_auth_bearer_header(),
            json={
                "name": name,
            },
        )

        r.raise_for_status()
        return Project(**r.json())

    def delete_project(self, project_id: str | UUID):
        r = httpx.delete(
            urljoin(self.base_url, f"/projects/{project_id}"),
            headers=self.auth_client.get_auth_bearer_header(),
        )

        r.raise_for_status()

    def get_project_list(self) -> ResourceList[Project]:
        r = httpx.get(
            urljoin(self.base_url, "/projects"),
            headers=self.auth_client.get_auth_bearer_header(),
        )

        r.raise_for_status()
        return ResourceList[Project](**r.json())

    def get_project_by_id(self, project_id: str | UUID) -> Project | None:
        r = httpx.get(
            urljoin(self.base_url, f"/projects/{project_id}"),
            headers=self.auth_client.get_auth_bearer_header(),
        )

        if r.status_code == status.HTTP_404_NOT_FOUND:
            return None

        r.raise_for_status()
        return Project(**r.json())

    def create_analysis(self, name: str, project_id: str | UUID) -> Analysis:
        r = httpx.post(
            urljoin(self.base_url, "/analyses"),
            headers=self.auth_client.get_auth_bearer_header(),
            json={
                "name": name,
                "project_id": str(project_id),
            },
        )

        r.raise_for_status()
        return Analysis(**r.json())

    def delete_analysis(self, analysis_id: str | UUID):
        r = httpx.delete(
            urljoin(self.base_url, f"/analyses/{analysis_id}"),
            headers=self.auth_client.get_auth_bearer_header(),
        )

        r.raise_for_status()

    def get_analysis_list(self) -> ResourceList[Analysis]:
        r = httpx.get(
            urljoin(self.base_url, "/analyses"),
            headers=self.auth_client.get_auth_bearer_header(),
        )

        r.raise_for_status()
        return ResourceList[Analysis](**r.json())

    def get_analysis_by_id(self, analysis_id: str | UUID) -> Analysis | None:
        r = httpx.get(
            urljoin(self.base_url, f"/analyses/{analysis_id}"),
            headers=self.auth_client.get_auth_bearer_header(),
        )

        if r.status_code == status.HTTP_404_NOT_FOUND:
            return None

        r.raise_for_status()
        return Analysis(**r.json())

    def get_bucket_list(self) -> ResourceList[Bucket]:
        r = httpx.get(
            urljoin(self.base_url, "/storage/buckets"),
            headers=self.auth_client.get_auth_bearer_header(),
        )

        r.raise_for_status()
        return ResourceList[Bucket](**r.json())

    def get_bucket_by_id(self, bucket_id: str | UUID) -> Bucket | None:
        r = httpx.get(
            urljoin(self.base_url, f"/storage/buckets/{bucket_id}"),
            headers=self.auth_client.get_auth_bearer_header(),
        )

        if r.status_code == status.HTTP_404_NOT_FOUND:
            return None

        r.raise_for_status()
        return Bucket(**r.json())

    def get_bucket_file_list(self) -> ResourceList[BucketFile]:
        r = httpx.get(
            urljoin(self.base_url, "/storage/bucket-files"),
            headers=self.auth_client.get_auth_bearer_header(),
        )

        r.raise_for_status()
        return ResourceList[BucketFile](**r.json())

    def upload_to_bucket(
        self,
        bucket_id_or_name: str | UUID,
        file_name: str,
        file: bytes | BytesIO,
        content_type: str = "application/octet-stream",
    ) -> ResourceList[BucketFile]:
        # wrap into BytesIO if raw bytes are passed in
        if isinstance(file, bytes):
            file = BytesIO(file)

        r = httpx.post(
            urljoin(self.base_url, f"/storage/buckets/{bucket_id_or_name}/upload"),
            headers=self.auth_client.get_auth_bearer_header(),
            files={"file": (file_name, file, content_type)},
        )

        r.raise_for_status()
        return ResourceList[BucketFile](**r.json())

    def get_analysis_bucket_file_list(self) -> ResourceList[AnalysisBucketFile]:
        r = httpx.get(
            urljoin(self.base_url, "/analysis-bucket-files"),
            headers=self.auth_client.get_auth_bearer_header(),
        )

        r.raise_for_status()
        return ResourceList[AnalysisBucketFile](**r.json())

    def get_analysis_bucket(
        self, analysis_id: str | UUID, bucket_type: BucketType
    ) -> AnalysisBucket:
        r = httpx.get(
            urljoin(
                self.base_url,
                "/analysis-buckets?filter[analysis_id]="
                + str(analysis_id)
                + "&filter[type]="
                + str(bucket_type),
            ),
            headers=self.auth_client.get_auth_bearer_header(),
        )

        r.raise_for_status()
        lst = ResourceList[AnalysisBucket](**r.json())

        assert len(lst.data) == 1

        return lst.data[0]

    def link_bucket_file_to_analysis(
        self,
        analysis_bucket_id: str | UUID,
        bucket_file_id: str | UUID,
        bucket_file_name: str,
        root=True,
    ) -> AnalysisBucketFile:
        r = httpx.post(
            urljoin(self.base_url, "/analysis-bucket-files"),
            headers=self.auth_client.get_auth_bearer_header(),
            json={
                "bucket_id": str(analysis_bucket_id),
                "external_id": str(bucket_file_id),
                "name": bucket_file_name,
                "root": root,
            },
        )

        r.raise_for_status()
        return AnalysisBucketFile(**r.json())

    def stream_bucket_file(self, bucket_file_id: str | UUID, chunk_size=1024):
        with httpx.stream(
            "GET",
            urljoin(self.base_url, f"/storage/bucket-files/{bucket_file_id}/stream"),
            headers=self.auth_client.get_auth_bearer_header(),
        ) as r:
            for b in r.iter_bytes(chunk_size=chunk_size):
                yield b
