from enum import Enum

from pydantic import BaseModel, HttpUrl, ConfigDict, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Self


class MinioConnection(BaseModel):
    endpoint: str
    access_key: str
    secret_key: str
    region: str = "us-east-1"
    use_ssl: bool = True

    model_config = ConfigDict(frozen=True)


class MinioBucketConfig(MinioConnection):
    bucket: str


class OIDCConfig(BaseModel):
    certs_url: HttpUrl
    client_id_claim_name: str = "client_id"
    skip_jwt_validation: bool = False

    model_config = ConfigDict(frozen=True)


class PasswordAuthConfig(BaseModel):
    username: str
    password: str


class RobotAuthConfig(BaseModel):
    id: str
    secret: str


class AuthMethod(str, Enum):
    password = "password"
    robot = "robot"


class HubConfig(BaseModel):
    core_base_url: HttpUrl = "https://core.privateaim.net"
    auth_base_url: HttpUrl = "https://auth.privateaim.net"
    storage_base_url: HttpUrl = "https://storage.privateaim.net"

    auth_method: AuthMethod

    password_auth: PasswordAuthConfig | None = None
    robot_auth: RobotAuthConfig | None = None

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def check_auth_credentials_provided(self) -> Self:
        if self.auth_method == AuthMethod.password and self.password_auth is None:
            raise ValueError("password auth specified but no credentials provided")

        if self.auth_method == AuthMethod.robot and self.robot_auth is None:
            raise ValueError("robot auth specified but no credentials provided")

        return self


class PostgresConfig(BaseModel):
    host: str
    password: str
    user: str
    db: str
    port: int = 5432


class Settings(BaseSettings):
    hub: HubConfig
    minio: MinioBucketConfig
    oidc: OIDCConfig
    postgres: PostgresConfig

    model_config = SettingsConfigDict(
        frozen=True,
        env_file=".env",
        env_nested_delimiter="__",
    )
