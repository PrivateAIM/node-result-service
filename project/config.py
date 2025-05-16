from enum import Enum
from pathlib import Path
from typing import Literal, Annotated, Union

from pydantic import BaseModel, HttpUrl, ConfigDict, Field, AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


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


class AuthFlow(str, Enum):
    password = "password"
    robot = "robot"


class PasswordAuthConfig(BaseModel):
    flow: Literal[AuthFlow.password]
    username: str
    password: str


class RobotAuthConfig(BaseModel):
    flow: Literal[AuthFlow.robot]
    id: str
    secret: str


class HubConfig(BaseModel):
    core_base_url: HttpUrl = "https://core.privateaim.net"
    auth_base_url: HttpUrl = "https://auth.privateaim.net"
    storage_base_url: HttpUrl = "https://storage.privateaim.net"

    auth: Annotated[Union[RobotAuthConfig, PasswordAuthConfig], Field(discriminator="flow")]

    model_config = ConfigDict(frozen=True)


class PostgresConfig(BaseModel):
    host: str
    password: str
    user: str
    db: str
    port: int = 5432


class CryptoProvider(str, Enum):
    raw = "raw"
    file = "file"


class RawCryptoConfig(BaseModel):
    provider: Literal[CryptoProvider.raw]
    ecdh_private_key: bytes


class FileCryptoConfig(BaseModel):
    provider: Literal[CryptoProvider.file]
    ecdh_private_key_path: Path


class ProxyConfig(BaseModel):
    http_url: AnyHttpUrl | None = None
    https_url: AnyHttpUrl | None = None


class Settings(BaseSettings):
    hub: HubConfig
    minio: MinioBucketConfig
    oidc: OIDCConfig
    postgres: PostgresConfig
    crypto: Annotated[Union[RawCryptoConfig, FileCryptoConfig], Field(discriminator="provider")]
    proxy: Annotated[ProxyConfig, Field(default_factory=ProxyConfig)]

    model_config = SettingsConfigDict(
        frozen=True,
        env_file=".env",
        env_nested_delimiter="__",
    )
