from io import BytesIO
from typing import NamedTuple

import httpx
from starlette import status


class AccessToken(NamedTuple):
    access_token: str
    expires_in: int
    token_type: str
    scope: str
    refresh_token: str


class Project(NamedTuple):
    id: str
    name: str


class Analysis(NamedTuple):
    id: str
    name: str


class BucketFile(NamedTuple):
    id: str
    name: str
    bucket_id: str


class AnalysisFile(NamedTuple):
    id: str
    name: str
    type: str
    bucket_file_id: str


class Bucket(NamedTuple):
    id: str
    name: str


class AuthWrapper:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def acquire_access_token_with_password(
        self, username: str, password: str
    ) -> AccessToken:
        r = httpx.post(
            f"{self.base_url}/token",
            json={
                "grant_type": "password",
                "username": username,
                "password": password,
            },
        ).raise_for_status()
        j = r.json()

        return AccessToken(
            access_token=j["access_token"],
            expires_in=j["expires_in"],
            token_type=j["token_type"],
            scope=j["scope"],
            refresh_token=j["refresh_token"],
        )


class ApiWrapper:
    def __init__(self, base_url: str, access_token: str):
        self.base_url = base_url
        self.access_token = access_token

    def __auth_header(self):
        return {"Authorization": f"Bearer {self.access_token}"}

    def create_project(self, name: str) -> Project:
        r = httpx.post(
            f"{self.base_url}/projects",
            headers=self.__auth_header(),
            json={"name": name},
        ).raise_for_status()
        j = r.json()

        return Project(
            id=j["id"],
            name=j["name"],
        )

    def create_analysis(self, name: str, project_id: str) -> Analysis:
        r = httpx.post(
            f"{self.base_url}/analyses",
            headers=self.__auth_header(),
            json={
                "name": name,
                "project_id": project_id,
            },
        ).raise_for_status()
        j = r.json()

        return Analysis(
            id=j["id"],
            name=j["name"],
        )

    def get_bucket(self, bucket_name: str) -> Bucket | None:
        r = httpx.get(
            f"{self.base_url}/storage/buckets/{bucket_name}",
            headers=self.__auth_header(),
        )

        if r.status_code == status.HTTP_404_NOT_FOUND:
            return None

        # catch any other unexpected status
        r.raise_for_status()
        j = r.json()

        return Bucket(
            id=j["id"],
            name=j["name"],
        )

    def get_bucket_file(self, bucket_file_id: str) -> BucketFile | None:
        r = httpx.get(
            f"{self.base_url}/storage/bucket-files/{bucket_file_id}",
            headers=self.__auth_header(),
        ).raise_for_status()

        if r.status_code == status.HTTP_404_NOT_FOUND:
            return None

        r.raise_for_status()
        j = r.json()

        return BucketFile(
            id=j["id"],
            name=j["name"],
            bucket_id=j["bucket_id"],
        )

    def upload_to_bucket(
        self,
        bucket_name: str,
        file_name: str,
        file: BytesIO,
        content_type: str = "application/octet-stream",
    ) -> list[BucketFile]:
        r = httpx.post(
            f"{self.base_url}/storage/buckets/{bucket_name}/upload",
            headers=self.__auth_header(),
            files={
                "file": (file_name, file, content_type),
            },
        ).raise_for_status()
        j = r.json()

        return [
            BucketFile(
                id=b["id"],
                name=b["name"],
                bucket_id=b["bucket_id"],
            )
            for b in j["data"]
        ]

    def link_file_to_analysis(
        self, analysis_id: str, bucket_file_id: str, bucket_file_name: str
    ) -> AnalysisFile:
        r = httpx.post(
            f"{self.base_url}/analysis-files",
            headers=self.__auth_header(),
            json={
                "analysis_id": analysis_id,
                "type": "RESULT",
                "bucket_file_id": bucket_file_id,
                "name": bucket_file_name,
                "root": True,
            },
        ).raise_for_status()
        j = r.json()

        return AnalysisFile(
            id=j["id"],
            name=j["name"],
            type=j["type"],
            bucket_file_id=j["bucket_file_id"],
        )

    def get_analysis_files(self) -> list[AnalysisFile]:
        r = httpx.get(
            f"{self.base_url}/analysis-files",
            headers=self.__auth_header(),
        ).raise_for_status()
        j = r.json()

        return [
            AnalysisFile(
                id=f["id"],
                name=f["name"],
                type=f["type"],
                bucket_file_id=f["bucket_file_id"],
            )
            for f in j["data"]
        ]
