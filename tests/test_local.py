import uuid

from starlette import status
import pytest

from project.routers.local import (
    LocalUploadResponse,
)
from tests.common.auth import BearerAuth, issue_client_access_token
from tests.common.helpers import next_random_bytes, eventually
from tests.common.rest import wrap_bytes_for_request, detail_of


pytestmark = pytest.mark.live


def test_200_submit_receive_from_local(test_client, rng, core_client, analysis_id):
    def _analysis_exists():
        return core_client.get_analysis(analysis_id) is not None

    assert eventually(_analysis_exists)

    blob = next_random_bytes(rng)
    r = test_client.put(
        "/local",
        auth=BearerAuth(issue_client_access_token(analysis_id)),
        files=wrap_bytes_for_request(blob),
    )

    assert r.status_code == status.HTTP_200_OK
    model = LocalUploadResponse(**r.json())

    r = test_client.get(
        model.url.path,
        auth=BearerAuth(issue_client_access_token(analysis_id)),
    )

    assert r.status_code == status.HTTP_200_OK
    assert r.read() == blob


def test_404_unknown_oid(test_client, core_client, analysis_id):
    def _analysis_exists():
        return core_client.get_analysis(analysis_id) is not None

    assert eventually(_analysis_exists)

    oid = uuid.uuid4()
    r = test_client.get(
        f"/local/{oid}",
        auth=BearerAuth(issue_client_access_token(analysis_id)),
    )

    assert r.status_code == status.HTTP_404_NOT_FOUND
    assert detail_of(r) == f"Object with ID {oid} does not exist"


def test_200_result_from_another_analysis(test_client, core_client, analysis_id_factory, rng):
    first_analysis_id, second_analysis_id = analysis_id_factory(), analysis_id_factory()

    def _analyses_exist():
        return core_client.get_analysis(first_analysis_id) is not None and core_client.get_analysis(second_analysis_id)

    eventually(_analyses_exist)

    blob = next_random_bytes(rng)
    r = test_client.put(
        "/local",
        auth=BearerAuth(issue_client_access_token(first_analysis_id)),
        files=wrap_bytes_for_request(blob),
    )

    r = test_client.get(r.json()["url"], auth=BearerAuth(issue_client_access_token(second_analysis_id)))

    assert r.status_code == status.HTTP_200_OK
    assert r.read() == blob


def test_404_result_from_another_project(test_client, core_client, rng, project_id_factory, analysis_id_factory):
    first_analysis_id = analysis_id_factory(project_id_factory())
    second_analysis_id = analysis_id_factory(project_id_factory())

    def _analyses_exist():
        return core_client.get_analysis(first_analysis_id) is not None and core_client.get_analysis(second_analysis_id)

    eventually(_analyses_exist)

    blob = next_random_bytes(rng)
    r = test_client.put(
        "/local",
        auth=BearerAuth(issue_client_access_token(first_analysis_id)),
        files=wrap_bytes_for_request(blob),
    )

    object_id = r.json()["url"].split("/")[-1]
    r = test_client.get(r.json()["url"], auth=BearerAuth(issue_client_access_token(second_analysis_id)))

    assert r.status_code == status.HTTP_404_NOT_FOUND
    assert detail_of(r) == f"Object with ID {object_id} does not exist"
