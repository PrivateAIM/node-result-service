import time
import urllib.parse
from datetime import datetime
from io import BytesIO
from typing import TypeVar, Generic, Literal, Optional
from uuid import UUID

import httpx
from pydantic import BaseModel
from starlette import status

from project.common import build_url

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
    external_id: UUID  # external_id points to a Bucket
    analysis_id: UUID
    created_at: datetime
    updated_at: datetime


class AnalysisBucketFile(BaseModel):
    id: UUID
    name: Optional[str]
    root: bool
    created_at: datetime
    updated_at: datetime
    external_id: UUID  # external_id points to a BucketFile
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
        """
        Create a new client to interact with the FLAME Auth API.
        This client uses Authup's password flow to authenticate itself.

        Args:
            username: client username
            password: client password
            base_url: base API url
            token_expiration_leeway_seconds: amount of seconds before a token's set expiration timestamp to allow a
                new token to be fetched in advance
            force_acquire_on_init: *True* if a token should be fetched when this client is instantiated,
                *False* otherwise
        """
        self.base_url = base_url

        base_url_parts = urllib.parse.urlsplit(base_url)

        self._base_scheme = base_url_parts[0]
        self._base_netloc = base_url_parts[1]
        self._base_path = base_url_parts[2]

        self._username = username
        self._password = password
        self._token_expiration_leeway_seconds = token_expiration_leeway_seconds
        self._current_access_token = None
        self._current_access_token_expires_at = 0

        if force_acquire_on_init:
            self._acquire_token()

    def _format_url(self, path: str, query: dict[str, str] = None):
        return build_url(
            self._base_scheme,
            self._base_netloc,
            urllib.parse.urljoin(self._base_path, path),
            query,
            "",
        )

    def _acquire_token(self):
        r = httpx.post(
            self._format_url("/token"),
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
        """
        Get an active and valid access token object to authenticate with against the FLAME Hub API.
        If no token has been fetched yet, or if the most recently fetched token is expired, a new one will be fetched.

        Returns:
            valid access token object
        """
        if self._current_access_token is None:
            self._acquire_token()
        elif (
            self._current_access_token_expires_at
            < _now() + self._token_expiration_leeway_seconds
        ):
            self._acquire_token()

        return self._current_access_token

    def get_access_token(self):
        """
        Get a valid access token code.

        Returns:
            access token code
        """
        return self.get_access_token_object().access_token

    def get_auth_bearer_header(self):
        """
        Get a valid access token code and return it as an HTTP authorization header to be used in *httpx* and
        *requests* headers.

        Returns:
            access token code wrapped in a dictionary for use with HTTP headers
        """
        return {
            "Authorization": f"Bearer {self.get_access_token()}",
        }


class FlameHubClient:
    def __init__(
        self,
        auth_client: FlamePasswordAuthClient,
        base_url="https://api.privateaim.net",
    ):
        """
        Create a new client to interact with the FLAME Hub API.

        Args:
            auth_client: FLAME Auth API client to use
            base_url: base API url
        """
        self.base_url = base_url
        self.auth_client = auth_client

        base_url_parts = urllib.parse.urlsplit(base_url)

        self._base_scheme = base_url_parts[0]
        self._base_netloc = base_url_parts[1]
        self._base_path = base_url_parts[2]

    def _format_url(self, path: str, query: dict[str, str] = None):
        return build_url(
            self._base_scheme,
            self._base_netloc,
            urllib.parse.urljoin(self._base_path, path),
            query,
            "",
        )

    def create_project(self, name: str) -> Project:
        """
        Create a named project.

        Args:
            name: project name

        Returns:
            created project resource
        """
        r = httpx.post(
            self._format_url("/projects"),
            headers=self.auth_client.get_auth_bearer_header(),
            json={
                "name": name,
            },
        )

        r.raise_for_status()
        return Project(**r.json())

    def delete_project(self, project_id: str | UUID):
        """
        Delete a project by its ID.

        Args:
            project_id: ID of the project to delete
        """
        r = httpx.delete(
            self._format_url(f"/projects/{str(project_id)}"),
            headers=self.auth_client.get_auth_bearer_header(),
        )

        r.raise_for_status()

    def get_project_list(self) -> ResourceList[Project]:
        """
        Get a list of projects.

        Returns:
            list of project resources
        """
        r = httpx.get(
            self._format_url("/projects"),
            headers=self.auth_client.get_auth_bearer_header(),
        )

        r.raise_for_status()
        return ResourceList[Project](**r.json())

    def get_project_by_id(self, project_id: str | UUID) -> Project | None:
        """
        Get a project by its ID.

        Args:
            project_id: ID of the project to get

        Returns:
            project resource, or *None* if no project was found
        """
        r = httpx.get(
            self._format_url(f"/projects/{str(project_id)}"),
            headers=self.auth_client.get_auth_bearer_header(),
        )

        if r.status_code == status.HTTP_404_NOT_FOUND:
            return None

        r.raise_for_status()
        return Project(**r.json())

    def create_analysis(self, name: str, project_id: str | UUID) -> Analysis:
        """
        Create a named analysis and assign it to a project.

        Args:
            name: analysis name
            project_id: ID of the project to assign the analysis to

        Returns:
            created analysis resource
        """
        r = httpx.post(
            self._format_url("/analyses"),
            headers=self.auth_client.get_auth_bearer_header(),
            json={
                "name": name,
                "project_id": str(project_id),
            },
        )

        r.raise_for_status()
        return Analysis(**r.json())

    def delete_analysis(self, analysis_id: str | UUID):
        """
        Delete a analysis by its ID.

        Args:
            analysis_id: ID of the analysis to delete
        """
        r = httpx.delete(
            self._format_url(f"/analyses/{str(analysis_id)}"),
            headers=self.auth_client.get_auth_bearer_header(),
        )

        r.raise_for_status()

    def get_analysis_list(self) -> ResourceList[Analysis]:
        """
        Get a list of analyses.

        Returns:
            list of analysis resources
        """
        r = httpx.get(
            self._format_url("/analyses"),
            headers=self.auth_client.get_auth_bearer_header(),
        )

        r.raise_for_status()
        return ResourceList[Analysis](**r.json())

    def get_analysis_by_id(self, analysis_id: str | UUID) -> Analysis | None:
        """
        Get an analysis by its ID.

        Args:
            analysis_id: ID of the analysis to get

        Returns:
            analysis resource, or *None* if no analysis was found
        """
        r = httpx.get(
            self._format_url(f"/analyses/{str(analysis_id)}"),
            headers=self.auth_client.get_auth_bearer_header(),
        )

        if r.status_code == status.HTTP_404_NOT_FOUND:
            return None

        r.raise_for_status()
        return Analysis(**r.json())

    def get_bucket_list(self) -> ResourceList[Bucket]:
        """
        Get list of buckets.

        Returns:
            list of bucket resources
        """
        r = httpx.get(
            self._format_url("/storage/buckets"),
            headers=self.auth_client.get_auth_bearer_header(),
        )

        r.raise_for_status()
        return ResourceList[Bucket](**r.json())

    def get_bucket_by_id(self, bucket_id: str | UUID) -> Bucket | None:
        """
        Get a bucket by its ID.

        Args:
            bucket_id: ID of the bucket to get

        Returns:
            bucket resource, or *None* if no bucket was found
        """
        r = httpx.get(
            self._format_url(f"/storage/buckets/{bucket_id}"),
            headers=self.auth_client.get_auth_bearer_header(),
        )

        if r.status_code == status.HTTP_404_NOT_FOUND:
            return None

        r.raise_for_status()
        return Bucket(**r.json())

    def get_bucket_file_list(self) -> ResourceList[BucketFile]:
        """
        Get list of bucket files.

        Returns:
            list of bucket file resources
        """
        r = httpx.get(
            self._format_url("/storage/bucket-files"),
            headers=self.auth_client.get_auth_bearer_header(),
        )

        r.raise_for_status()
        return ResourceList[BucketFile](**r.json())

    def upload_to_bucket(
        self,
        bucket_id: str | UUID,
        file_name: str,
        file: bytes | BytesIO,
        content_type: str = "application/octet-stream",
    ) -> ResourceList[BucketFile]:
        """
        Upload a single file to a bucket.

        Args:
            bucket_id: ID of the bucket to upload the file to
            file_name: file name
            file: file contents
            content_type: content type of the file (*application/octet-stream* by default)

        Returns:
            list of bucket file resources for the uploaded file
        """
        # wrap into BytesIO if raw bytes are passed in
        if isinstance(file, bytes):
            file = BytesIO(file)

        r = httpx.post(
            self._format_url(f"/storage/buckets/{bucket_id}/upload"),
            headers=self.auth_client.get_auth_bearer_header(),
            files={"file": (file_name, file, content_type)},
        )

        r.raise_for_status()
        return ResourceList[BucketFile](**r.json())

    def get_analysis_bucket_file_list(self) -> ResourceList[AnalysisBucketFile]:
        """
        Get list of files that have been linked to an analysis.

        Returns:
            list of analysis bucket file resources
        """
        r = httpx.get(
            self._format_url("/analysis-bucket-files"),
            headers=self.auth_client.get_auth_bearer_header(),
        )

        r.raise_for_status()
        return ResourceList[AnalysisBucketFile](**r.json())

    def get_analysis_bucket(
        self, analysis_id: str | UUID, bucket_type: BucketType
    ) -> AnalysisBucket:
        """
        Get an analysis bucket by its ID and type.

        Args:
            analysis_id: ID of the analysis
            bucket_type: type of the bucket

        Returns:
            analysis bucket resource
        """
        r = httpx.get(
            self._format_url(
                "/analysis-buckets",
                query={
                    "filter[analysis_id]": str(analysis_id),
                    "filter[type]": str(bucket_type),
                },
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
        """
        Link a bucket file to an analysis.

        Args:
            analysis_bucket_id: ID of the analysis bucket
            bucket_file_id: ID of the bucket file
            bucket_file_name: name of the bucket file
            root: not documented (should be left as *True*)

        Returns:
            analysis bucket file resource
        """
        r = httpx.post(
            self._format_url("/analysis-bucket-files"),
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
        """
        Fetch the contents of a bucket file.
        The resulting iterator yields chunks of bytes of specified size until the file stream is exhausted.

        Args:
            bucket_file_id: ID of the bucket file to fetch
            chunk_size: amount of bytes to return on every call of the returned iterator

        Returns:
            iterator that streams the file's contents
        """
        with httpx.stream(
            "GET",
            self._format_url(f"/storage/bucket-files/{bucket_file_id}/stream"),
            headers=self.auth_client.get_auth_bearer_header(),
        ) as r:
            for b in r.iter_bytes(chunk_size=chunk_size):
                yield b
