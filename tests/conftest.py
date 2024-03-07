import random
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from jwcrypto import jwk
from starlette.testclient import TestClient

from project.config import Settings, MinioBucketConfig, OIDCConfig, HubConfig
from project.dependencies import get_settings
from project.hub import AuthWrapper, ApiWrapper
from project.server import app
from tests.common.auth import get_oid_test_jwk
from tests.common.env import (
    PYTEST_OIDC_CERTS_URL,
    PYTEST_MINIO_ENDPOINT,
    PYTEST_MINIO_ACCESS_KEY,
    PYTEST_MINIO_SECRET_KEY,
    PYTEST_MINIO_REGION,
    PYTEST_MINIO_USE_SSL,
    PYTEST_MINIO_BUCKET,
    PYTEST_OIDC_CLIENT_ID_CLAIM_NAME,
    PYTEST_HUB_AUTH_BASE_URL,
    PYTEST_HUB_AUTH_USERNAME,
    PYTEST_HUB_AUTH_PASSWORD,
    PYTEST_HUB_API_BASE_URL,
)
from tests.common.helpers import eventually, next_prefixed_name, is_valid_uuid


def __get_settings_override() -> Settings:
    return Settings(
        hub=HubConfig(
            api_base_url=PYTEST_HUB_API_BASE_URL,
            auth_base_url=PYTEST_HUB_AUTH_BASE_URL,
            auth_username=PYTEST_HUB_AUTH_USERNAME,
            auth_password=PYTEST_HUB_AUTH_PASSWORD,
        ),
        minio=MinioBucketConfig(
            endpoint=PYTEST_MINIO_ENDPOINT,
            access_key=PYTEST_MINIO_ACCESS_KEY,
            secret_key=PYTEST_MINIO_SECRET_KEY,
            region=PYTEST_MINIO_REGION,
            use_ssl=PYTEST_MINIO_USE_SSL,
            bucket=PYTEST_MINIO_BUCKET,
        ),
        oidc=OIDCConfig(
            certs_url=PYTEST_OIDC_CERTS_URL,
            client_id_claim_name=PYTEST_OIDC_CLIENT_ID_CLAIM_NAME,
        ),
    )


@pytest.fixture(scope="package")
def test_app():
    app.dependency_overrides[get_settings] = __get_settings_override
    return app


@pytest.fixture(scope="package")
def test_client(test_app):
    # see https://fastapi.tiangolo.com/advanced/testing-events/
    # this is to ensure that the lifespan events are called
    with TestClient(test_app) as test_client:
        yield test_client


@pytest.fixture(scope="package", autouse=True)
def setup_jwks_endpoint():
    jwks = jwk.JWKSet()
    jwks["keys"].add(get_oid_test_jwk())
    jwks_str = jwks.export(private_keys=False)

    class JWKSHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(jwks_str.encode("utf-8"))

    httpd_url = urllib.parse.urlparse(PYTEST_OIDC_CERTS_URL)
    httpd = HTTPServer((httpd_url.hostname, httpd_url.port), JWKSHandler)

    t = threading.Thread(target=httpd.serve_forever)
    t.start()

    yield

    httpd.shutdown()


@pytest.fixture(scope="package")
def rng():
    return random.Random(727)


@pytest.fixture(scope="package")
def hub_access_token():
    return (
        AuthWrapper(PYTEST_HUB_AUTH_BASE_URL)
        .acquire_access_token_with_password(
            PYTEST_HUB_AUTH_USERNAME, PYTEST_HUB_AUTH_PASSWORD
        )
        .access_token
    )


@pytest.fixture(scope="package")
def api(hub_access_token):
    return ApiWrapper(PYTEST_HUB_API_BASE_URL, hub_access_token)


@pytest.fixture(scope="package")
def analysis_id(api, rng):
    project_name = next_prefixed_name()
    project = api.create_project(project_name)

    assert project.name == project_name
    assert is_valid_uuid(project.id)

    analysis_name = next_prefixed_name()
    analysis = api.create_analysis(analysis_name, project.id)

    assert analysis.name == analysis_name
    assert is_valid_uuid(analysis.id)

    for bucket_type in ("result", "code", "temp"):

        def __bucket_exists():
            bucket_name = f"analysis-{bucket_type}-files.{analysis.id}"
            bucket = api.get_bucket(bucket_name)

            if bucket is None:
                return False

            assert bucket.name == bucket_name
            assert is_valid_uuid(bucket.id)

        assert eventually(__bucket_exists)

    yield analysis.id
