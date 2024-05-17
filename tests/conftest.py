import random
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from jwcrypto import jwk
from starlette.testclient import TestClient

from project.config import Settings, MinioBucketConfig, OIDCConfig, HubConfig
from project.dependencies import get_settings
from project.hub import FlamePasswordAuthClient, FlameHubClient
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
from tests.common.helpers import next_prefixed_name


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
def auth_client():
    return FlamePasswordAuthClient(
        PYTEST_HUB_AUTH_USERNAME,
        PYTEST_HUB_AUTH_PASSWORD,
        base_url=PYTEST_HUB_AUTH_BASE_URL,
        force_acquire_on_init=True,
    )


@pytest.fixture(scope="package")
def api_client(auth_client):
    return FlameHubClient(auth_client, base_url=PYTEST_HUB_API_BASE_URL)


@pytest.fixture
def project_id(api_client):
    project_name = next_prefixed_name()
    project = api_client.create_project(project_name)

    # check that project was successfully created
    assert project.name == project_name

    # check that project can be retrieved
    project_get = api_client.get_project_by_id(project.id)
    assert project_get.id == project.id

    # check that project appears in list
    project_get_list = api_client.get_project_list()
    assert any([p.id == project.id for p in project_get_list.data])

    yield project.id

    # check that project can be deleted
    api_client.delete_project(project.id)

    # check that project is no longer found
    assert api_client.get_project_by_id(project.id) is None


@pytest.fixture
def analysis_id(api_client, project_id):
    analysis_name = next_prefixed_name()
    analysis = api_client.create_analysis(analysis_name, project_id)

    # check that analysis was created
    assert analysis.name == analysis_name
    assert analysis.project_id == project_id

    # check that GET on analysis works
    analysis_get = api_client.get_analysis_by_id(analysis.id)
    assert analysis_get.id == analysis.id

    # check that analysis appears in list
    analysis_get_list = api_client.get_analysis_list()
    assert any([a.id == analysis.id for a in analysis_get_list.data])

    yield analysis.id

    # check that DELETE analysis works
    api_client.delete_analysis(analysis.id)

    # check that analysis is no longer found
    assert api_client.get_analysis_by_id(analysis.id) is None
