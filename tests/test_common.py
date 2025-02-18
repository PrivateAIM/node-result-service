from project.common import build_url, hex_to_ecdh_public_key
from tests.common.helpers import next_ecdh_keypair_bytes

from cryptography.hazmat.primitives import serialization


def test_build_url():
    assert (
        build_url("http", "privateaim.de", "analysis", {"foo": "bar"}, "baz")
        == "http://privateaim.de/analysis?foo=bar#baz"
    )


def test_hex_to_ecdh_public_key():
    _, pk_bytes = next_ecdh_keypair_bytes()
    pk_hex = pk_bytes.hex()
    pk = hex_to_ecdh_public_key(pk_hex)

    assert pk_bytes == pk.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
