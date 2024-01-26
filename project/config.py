from pydantic import BaseModel, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class MinioConnection(BaseModel):
    endpoint: str
    access_key: str
    secret_key: str
    region: str = "us-east-1"
    use_ssl: bool = True


class MinioBucketConfig(MinioConnection):
    bucket: str


class Settings(BaseSettings):
    minio: MinioBucketConfig
    openid_certs_url: HttpUrl

    model_config = SettingsConfigDict(
        frozen=True,
        env_file=".env",
        env_nested_delimiter="__",
    )
