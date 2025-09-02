from project.config import FileCryptoConfig, RawCryptoConfig, Settings
from project.dependencies import (
    get_ecdh_private_key_from_path,
    get_ecdh_private_key_from_bytes,
    get_ssl_context,
)
from tests.common.auth import get_test_ecdh_keypair_paths


def test_get_ecdh_private_key_from_path():
    private_key_path, _ = get_test_ecdh_keypair_paths()

    file_crypto = FileCryptoConfig(
        provider="file",
        ecdh_private_key_path=private_key_path,
    )

    # not interested in the results, just make sure it loads correctly
    _ = get_ecdh_private_key_from_path(file_crypto)


def test_ecdh_private_key_from_bytes():
    private_key_path, _ = get_test_ecdh_keypair_paths()

    with private_key_path.open("rb") as f:
        private_key_bytes = f.read()

    raw_crypto = RawCryptoConfig(
        provider="raw",
        ecdh_private_key=private_key_bytes,
    )

    # see above
    _ = get_ecdh_private_key_from_bytes(raw_crypto)


def test_ecdh_private_key_from_file_contents():
    private_key_path, _ = get_test_ecdh_keypair_paths()

    with private_key_path.open("r") as f:
        private_key_file_contents = f.read()

    # noinspection PyTypeChecker
    raw_crypto = RawCryptoConfig(
        provider="raw",
        ecdh_private_key=private_key_file_contents,
    )

    _ = get_ecdh_private_key_from_bytes(raw_crypto)


def test_ecdh_private_key_from_escaped_file_contents():
    private_key_path, _ = get_test_ecdh_keypair_paths()

    with private_key_path.open("r") as f:
        private_key_file_contents = f.read().replace("\n", r"\n")

    raw_crypto = RawCryptoConfig(
        provider="raw",
        ecdh_private_key=private_key_file_contents,
    )

    _ = get_ecdh_private_key_from_bytes(raw_crypto)


def test_extra_ca_certs():
    ssl_ctx = get_ssl_context(Settings())
    # Access protected _ctx member since get_ca_certs() is not implemented for truststore.SSLContext classes.
    assert len(ssl_ctx._ctx.get_ca_certs()) == 1
