import os
import random
import ssl
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

import flame_hub.auth
import httpx
import peewee as pw
import pytest
import truststore
from jwcrypto import jwk
from starlette.testclient import TestClient
from testcontainers.minio import MinioContainer
from testcontainers.postgres import PostgresContainer

from project.dependencies import get_postgres_db, get_local_minio, get_ecdh_private_key
from project.server import get_server_instance
from tests.common import env
from tests.common.auth import get_oid_test_jwk, get_test_ecdh_keypair
from tests.common.helpers import (
    next_prefixed_name,
)


@pytest.fixture(scope="package")
def use_testcontainers():
    return os.environ.get("PYTEST__USE_TESTCONTAINERS", "0") == "1"


@pytest.fixture(scope="package")
def override_postgres(use_testcontainers):
    if not use_testcontainers:
        yield None
    else:
        with PostgresContainer(
            "postgres:17.2",
            username=os.environ.get("POSTGRES__USER"),
            password=os.environ.get("POSTGRES__PASSWORD"),
            dbname=os.environ.get("POSTGRES__DB"),
            driver=None,
        ) as postgres:
            pg_url = urllib.parse.urlparse(postgres.get_connection_url())

            def _override_get_postgres_db():
                return pw.PostgresqlDatabase(
                    pg_url.path.lstrip("/"),  # trim leading slash
                    user=pg_url.username,
                    password=pg_url.password,
                    host=pg_url.hostname,
                    port=pg_url.port,
                )

            yield _override_get_postgres_db


@pytest.fixture(scope="package")
def override_minio(use_testcontainers):
    if not use_testcontainers:
        yield None
    else:
        access_key = os.environ.get("MINIO__ACCESS_KEY")
        secret_key = os.environ.get("MINIO__SECRET_KEY")
        bucket = os.environ.get("MINIO__BUCKET")

        with MinioContainer(
            "minio/minio:RELEASE.2024-12-13T22-19-12Z",
            access_key=access_key,
            secret_key=secret_key,
        ) as minio:
            client = minio.get_client()
            client.make_bucket(bucket)

            def _override_get_local_minio():
                return client

            yield _override_get_local_minio


@pytest.fixture(scope="package")
def override_ecdh_private_key():
    private_key, _ = get_test_ecdh_keypair()

    def _get_ecdh_private_key():
        return private_key

    yield _get_ecdh_private_key


# noinspection PyUnresolvedReferences
@pytest.fixture(scope="package")
def test_app(override_minio, override_postgres, override_ecdh_private_key):
    app = get_server_instance()

    if callable(override_postgres):
        app.dependency_overrides[get_postgres_db] = override_postgres

    if callable(override_minio):
        app.dependency_overrides[get_local_minio] = override_minio

    app.dependency_overrides[get_ecdh_private_key] = override_ecdh_private_key

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

    httpd_url = urllib.parse.urlparse(env.oidc_certs_url())
    httpd = HTTPServer((httpd_url.hostname, httpd_url.port), JWKSHandler)

    t = threading.Thread(target=httpd.serve_forever)
    t.start()

    yield

    httpd.shutdown()


@pytest.fixture(scope="package")
def rng():
    return random.Random(727)


@pytest.fixture(scope="package")
def ssl_context():
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


@pytest.fixture(scope="package")
def password_auth_client(ssl_context):
    return flame_hub.auth.PasswordAuth(
        env.hub_password_auth_username(),
        env.hub_password_auth_password(),
        client=httpx.Client(base_url=env.hub_auth_base_url(), verify=ssl_context),
    )


@pytest.fixture(scope="package")
def robot_auth_client(ssl_context):
    return flame_hub.auth.RobotAuth(
        env.hub_robot_auth_id(),
        env.hub_robot_auth_secret(),
        client=httpx.Client(base_url=env.hub_auth_base_url(), verify=ssl_context),
    )


@pytest.fixture(scope="package")
def auth_client(password_auth_client, ssl_context):
    return flame_hub.AuthClient(
        client=httpx.Client(auth=password_auth_client, base_url=env.hub_auth_base_url(), verify=ssl_context)
    )


@pytest.fixture(scope="package")
def core_client(password_auth_client, ssl_context):
    return flame_hub.CoreClient(
        client=httpx.Client(auth=password_auth_client, base_url=env.hub_core_base_url(), verify=ssl_context)
    )


@pytest.fixture(scope="package")
def storage_client(password_auth_client, ssl_context):
    return flame_hub.StorageClient(
        client=httpx.Client(auth=password_auth_client, base_url=env.hub_storage_base_url(), verify=ssl_context)
    )


@pytest.fixture
def project_id(core_client):
    preferred_base_image_name = os.environ.get("PYTEST__PREFERRED_BASE_MASTER_IMAGE", "python/base")
    master_images = core_client.find_master_images(filter={"path": preferred_base_image_name})

    if len(master_images) != 1:
        raise ValueError(f"expected single master image, got {len(master_images)}")

    project_name = next_prefixed_name()
    project = core_client.create_project(project_name, master_images.pop())

    # check that project was successfully created
    assert project.name == project_name

    # check that project can be retrieved
    project_get = core_client.get_project(project.id)
    assert project_get.id == project.id

    # check that project appears in list
    assert len(core_client.find_projects(filter={"id": project.id})) == 1

    yield project.id

    # check that project can be deleted
    core_client.delete_project(project.id)

    # check that project is no longer found
    assert core_client.get_project(project.id) is None


@pytest.fixture
def analysis_id(core_client, project_id):
    analysis_name = next_prefixed_name()
    analysis = core_client.create_analysis(project_id, analysis_name)

    # check that analysis was created
    assert analysis.name == analysis_name
    assert analysis.project_id == project_id

    # check that GET on analysis works
    analysis_get = core_client.get_analysis(analysis.id)
    assert analysis_get.id == analysis.id

    # check that analysis appears in list
    assert len(core_client.find_analyses(filter={"id": analysis.id})) == 1

    yield analysis.id

    # check that DELETE analysis works
    core_client.delete_analysis(analysis.id)

    # check that analysis is no longer found
    assert core_client.get_analysis(analysis.id) is None


@pytest.fixture
def realm_id(auth_client):
    preferred_realm_name = os.environ.get("PYTEST__PREFERRED_REALM_NAME", "master")
    realm_list = auth_client.find_realms(filter={"name": preferred_realm_name})

    assert len(realm_list) == 1

    yield realm_list.pop()
