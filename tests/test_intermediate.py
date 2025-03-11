import uuid

import pytest
from starlette import status

from project import crypto
from project.routers.intermediate import IntermediateUploadResponse
from tests.common.auth import (
    BearerAuth,
    issue_client_access_token,
    get_test_ecdh_keypair,
)
from tests.common.helpers import (
    next_random_bytes,
    eventually,
    next_uuid,
    next_ecdh_keypair_bytes,
)
from tests.common.rest import wrap_bytes_for_request, detail_of

pytestmark = pytest.mark.live


@pytest.fixture()
def node(robot_auth_client, core_client, realm_id):
    node_name = next_uuid()
    new_node = core_client.create_node(name=node_name, realm_id=realm_id, node_type="default")
    yield new_node
    core_client.delete_node(new_node.id)


def test_200_submit_receive_intermediate_encrypted(test_client, rng, analysis_id, node, core_client):
    def _check_temp_bucket_exists():
        return len(core_client.find_analysis_buckets(filter={"analysis_id": analysis_id, "type": "TEMP"})) == 1

    assert eventually(_check_temp_bucket_exists)

    private_key, public_key = get_test_ecdh_keypair()

    # update node with public key
    remote_private_key_bytes, remote_public_key_bytes = next_ecdh_keypair_bytes()
    core_client.update_node(node, public_key=remote_public_key_bytes.decode("ascii"))

    # update local node reference (public key must be updated)
    node = core_client.get_node(node.id)
    assert node.public_key is not None

    blob = next_random_bytes(rng)
    r = test_client.put(
        "/intermediate",
        auth=BearerAuth(issue_client_access_token(analysis_id)),
        files=wrap_bytes_for_request(blob),
        data={"remote_node_id": str(node.id)},
    )

    assert r.status_code == status.HTTP_200_OK

    # check that the response contains a path to a valid resource
    model = IntermediateUploadResponse(**r.json())
    assert str(model.object_id) in str(model.url.path)

    r = test_client.get(
        model.url.path,
        auth=BearerAuth(issue_client_access_token()),
    )

    assert r.status_code == status.HTTP_200_OK

    # read encrypted blob
    ct_blob = r.read()
    assert ct_blob != blob

    # pretend we're the remote node and decrypt using their private key
    decrypted_blob = crypto.decrypt_default(crypto.load_ecdh_private_key(remote_private_key_bytes), public_key, ct_blob)

    assert blob == decrypted_blob


def test_400_submit_encrypted_no_remote_public_key(test_client, rng, analysis_id, node, core_client):
    def _check_temp_bucket_exists():
        return len(core_client.find_analysis_buckets(filter={"analysis_id": analysis_id, "type": "TEMP"})) == 1

    assert eventually(_check_temp_bucket_exists)

    blob = next_random_bytes(rng)
    r = test_client.put(
        "/intermediate",
        auth=BearerAuth(issue_client_access_token(analysis_id)),
        files=wrap_bytes_for_request(blob),
        data={
            "remote_node_id": str(node.id),
        },
    )

    assert r.status_code == status.HTTP_400_BAD_REQUEST
    assert detail_of(r) == f"Remote node with ID {node.id} does not provide a public key"


def test_200_submit_receive_intermediate(test_client, rng, analysis_id, core_client):
    def _check_temp_bucket_exists():
        return len(core_client.find_analysis_buckets(filter={"analysis_id": analysis_id, "type": "TEMP"})) == 1

    assert eventually(_check_temp_bucket_exists)

    blob = next_random_bytes(rng)
    r = test_client.put(
        "/intermediate",
        auth=BearerAuth(issue_client_access_token(analysis_id)),
        files=wrap_bytes_for_request(blob),
    )

    assert r.status_code == status.HTTP_200_OK

    # check that the response contains a path to a valid resource
    model = IntermediateUploadResponse(**r.json())
    assert str(model.object_id) in str(model.url.path)

    r = test_client.get(
        model.url.path,
        auth=BearerAuth(issue_client_access_token()),
    )

    assert r.status_code == status.HTTP_200_OK
    assert r.read() == blob


def test_404_invalid_id(test_client):
    rand_uuid = str(uuid.uuid4())
    r = test_client.get(
        f"/intermediate/{rand_uuid}",
        auth=BearerAuth(issue_client_access_token()),
    )

    assert r.status_code == status.HTTP_404_NOT_FOUND
    assert detail_of(r) == f"Object with ID {rand_uuid} does not exist"


def test_404_submit_invalid_id(test_client, rng):
    rand_uuid = str(uuid.uuid4())
    blob = next_random_bytes(rng)

    r = test_client.put(
        "/intermediate",
        auth=BearerAuth(issue_client_access_token(rand_uuid)),
        files=wrap_bytes_for_request(blob),
    )

    assert r.status_code == status.HTTP_404_NOT_FOUND
    assert detail_of(r) == f"Temp bucket for analysis with ID {rand_uuid} was not found"
