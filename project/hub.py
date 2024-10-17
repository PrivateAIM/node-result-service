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
    refresh_token: str | None = None


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


class BaseAuthClient:
    def __init__(
        self, base_url="https://auth.privateaim.net", token_expiration_leeway_seconds=60
    ):
        self.base_url = base_url

        base_url_parts = urllib.parse.urlsplit(base_url)

        self._base_scheme = base_url_parts[0]
        self._base_netloc = base_url_parts[1]
        self._base_path = base_url_parts[2]

        self._token_expiration_leeway_seconds = token_expiration_leeway_seconds

        self.current_access_token = None
        self.current_access_token_expires_at = 0

    def format_url(self, path: str, query: dict[str, str] = None):
        return build_url(
            self._base_scheme,
            self._base_netloc,
            urllib.parse.urljoin(self._base_path, path),
            query,
            "",
        )

    def acquire_token(self):
        raise NotImplementedError()

    def format_auth_header(self):
        raise NotImplementedError()

    def get_auth_header(self):
        if self.current_access_token is None:
            self.acquire_token()
        elif (
            self.current_access_token_expires_at
            < _now() + self._token_expiration_leeway_seconds
        ):
            self.acquire_token()

        return self.format_auth_header()


class FlameRobotAuthClient(BaseAuthClient):
    def __init__(
        self,
        robot_id: str,
        robot_secret: str,
        base_url="https://auth.privateaim.net",
        token_expiration_leeway_seconds=60,
    ):
        """
        Create a new client to interact with the FLAME Auth API.
        This client uses Authup's robot credentials flow to authenticate itself.

        Args:
            robot_id: robot ID
            robot_secret: robot secret
            base_url: base API url
            token_expiration_leeway_seconds: amount of seconds before a token's set expiration timestamp to allow a
                new token to be fetched in advance
        """
        super().__init__(base_url, token_expiration_leeway_seconds)

        self._robot_id = robot_id
        self._robot_secret = robot_secret

    def acquire_token(self):
        r = httpx.post(
            self.format_url("/token"),
            json={
                "grant_type": "robot_credentials",
                "id": self._robot_id,
                "secret": self._robot_secret,
            },
        )

        r.raise_for_status()
        at = AccessToken(**r.json())

        self.current_access_token = at
        self.current_access_token_expires_at = _now() + at.expires_in

    def format_auth_header(self):
        return {
            "Authorization": f"Bearer {self.current_access_token.access_token}",
        }


class FlamePasswordAuthClient(BaseAuthClient):
    def __init__(
        self,
        username: str,
        password: str,
        base_url="https://auth.privateaim.net",
        token_expiration_leeway_seconds=60,
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
        """
        super().__init__(base_url, token_expiration_leeway_seconds)

        self._username = username
        self._password = password

    def acquire_token(self):
        r = httpx.post(
            self.format_url("/token"),
            json={
                "grant_type": "password",
                "username": self._username,
                "password": self._password,
            },
        )

        r.raise_for_status()
        at = AccessToken(**r.json())

        self.current_access_token = at
        self.current_access_token_expires_at = _now() + at.expires_in

    def format_auth_header(self):
        return {
            "Authorization": f"Bearer {self.current_access_token.access_token}",
        }


class FlameCoreClient:
    def __init__(
        self,
        auth_client: BaseAuthClient,
        base_url="https://core.privateaim.net",
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
            headers=self.auth_client.get_auth_header(),
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
            headers=self.auth_client.get_auth_header(),
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
            headers=self.auth_client.get_auth_header(),
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
            headers=self.auth_client.get_auth_header(),
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
            headers=self.auth_client.get_auth_header(),
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
            headers=self.auth_client.get_auth_header(),
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
            headers=self.auth_client.get_auth_header(),
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
            headers=self.auth_client.get_auth_header(),
        )

        if r.status_code == status.HTTP_404_NOT_FOUND:
            return None

        r.raise_for_status()
        return Analysis(**r.json())

    def get_analysis_bucket_file_list(self) -> ResourceList[AnalysisBucketFile]:
        """
        Get list of files that have been linked to an analysis.

        Returns:
            list of analysis bucket file resources
        """
        r = httpx.get(
            self._format_url("/analysis-bucket-files"),
            headers=self.auth_client.get_auth_header(),
        )

        r.raise_for_status()
        return ResourceList[AnalysisBucketFile](**r.json())

    def get_analysis_bucket(
        self, analysis_id: str | UUID, bucket_type: BucketType
    ) -> AnalysisBucket | None:
        """
        Get an analysis bucket by its ID and type.

        Args:
            analysis_id: ID of the analysis
            bucket_type: type of the bucket

        Returns:
            analysis bucket resource, or *None* if no analysis bucket was found
        """
        r = httpx.get(
            self._format_url(
                "/analysis-buckets",
                query={
                    "filter[analysis_id]": str(analysis_id),
                    "filter[type]": str(bucket_type),
                },
            ),
            headers=self.auth_client.get_auth_header(),
        )

        r.raise_for_status()
        lst = ResourceList[AnalysisBucket](**r.json())

        if len(lst.data) > 1:
            raise ValueError(
                f"expected no more than one analysis bucket with ID `{str(analysis_id)}` of "
                f"type `{str(bucket_type)}, found {len(lst.data)}`"
            )

        if len(lst.data) == 1:
            return lst.data[0]

        return None

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
            headers=self.auth_client.get_auth_header(),
            json={
                "bucket_id": str(analysis_bucket_id),
                "external_id": str(bucket_file_id),
                "name": bucket_file_name,
                "root": root,
            },
        )

        r.raise_for_status()
        return AnalysisBucketFile(**r.json())


class FlameStorageClient:
    def __init__(
        self,
        auth_client: BaseAuthClient,
        base_url="https://storage.privateaim.net",
    ):
        """
        Create a new client to interact with the FLAME Storage API.

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

    def get_bucket_list(self) -> ResourceList[Bucket]:
        """
        Get list of buckets.

        Returns:
            list of bucket resources
        """
        r = httpx.get(
            self._format_url("/buckets"),
            headers=self.auth_client.get_auth_header(),
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
            self._format_url(f"/buckets/{bucket_id}"),
            headers=self.auth_client.get_auth_header(),
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
            self._format_url("/bucket-files"),
            headers=self.auth_client.get_auth_header(),
        )

        r.raise_for_status()
        return ResourceList[BucketFile](**r.json())

    def get_bucket_file_by_id(self, bucket_file_id: str | UUID) -> BucketFile | None:
        """
        Get a bucket file by its ID.

        Args:
            bucket_file_id: ID of the bucket file to get

        Returns:
            bucket file resource, or *None* if no bucket file was found
        """
        r = httpx.get(
            self._format_url(f"/bucket-files/{str(bucket_file_id)}"),
            headers=self.auth_client.get_auth_header(),
        )

        if r.status_code == status.HTTP_404_NOT_FOUND:
            return None

        r.raise_for_status()
        return BucketFile(**r.json())

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
            self._format_url(f"/buckets/{bucket_id}/upload"),
            headers=self.auth_client.get_auth_header(),
            files={"file": (file_name, file, content_type)},
        )

        r.raise_for_status()
        return ResourceList[BucketFile](**r.json())

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
            self._format_url(f"/bucket-files/{bucket_file_id}/stream"),
            headers=self.auth_client.get_auth_header(),
        ) as r:
            for b in r.iter_bytes(chunk_size=chunk_size):
                yield b
