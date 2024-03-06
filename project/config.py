from pydantic import BaseModel, HttpUrl, ConfigDict
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

    model_config = ConfigDict(frozen=True)


class HubConfig(BaseModel):
    api_base_url: HttpUrl = "https://api.privateaim.net"
    auth_base_url: HttpUrl = "https://auth.privateaim.net"
    auth_username: str
    auth_password: str

    model_config = ConfigDict(frozen=True)


class Settings(BaseSettings):
    hub: HubConfig
    minio: MinioBucketConfig
    remote: MinioBucketConfig
    oidc: OIDCConfig

    model_config = SettingsConfigDict(
        frozen=True,
        env_file=".env",
        env_nested_delimiter="__",
    )
