import os
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.ciphers import aead


BITS_PER_BYTE = 8
DEFAULT_IV_BIT_SIZE = 128
DEFAULT_SHARED_SECRET_BIT_SIZE = 256

EllipticCurveKeyPair = tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]


# we only do ec in this household
# noinspection PyTypeChecker
def load_ecdh_public_key(public_key_bytes: bytes) -> ec.EllipticCurvePrivateKey:
    return serialization.load_pem_public_key(public_key_bytes)


def load_ecdh_private_key(private_key_bytes: bytes) -> ec.EllipticCurvePrivateKey:
    return serialization.load_pem_private_key(private_key_bytes, password=None)


def load_ecdh_public_key_from_path(public_key_path: Path):
    with public_key_path.open(mode="rb") as f:
        return load_ecdh_public_key(f.read())


def load_ecdh_private_key_from_path(private_key_path: Path):
    with private_key_path.open(mode="rb") as f:
        return load_ecdh_private_key(f.read())


def load_ecdh_public_key_from_hex_string(hex_str: str):
    return load_ecdh_public_key(bytes.fromhex(hex_str))


def random_iv(bit_size: int = DEFAULT_IV_BIT_SIZE):
    return os.urandom(bit_size // BITS_PER_BYTE)


def exchange_ecdh_shared_secret(
    private_key: ec.EllipticCurvePrivateKey,
    public_key: ec.EllipticCurvePublicKey,
    bit_size: int = DEFAULT_SHARED_SECRET_BIT_SIZE,
) -> bytes:
    if bit_size not in (256, 384):
        raise ValueError("size of secret key must be either 256 or 384 bits")

    shared_secret = private_key.exchange(ec.ECDH(), public_key)
    return shared_secret[: (bit_size // BITS_PER_BYTE)]


def encrypt_aesgcm(
    shared_secret: bytes, iv: bytes, data: bytes, associated_data: bytes = b""
):
    aesgcm = aead.AESGCM(shared_secret)
    return aesgcm.encrypt(iv, data, associated_data)


def split_iv_from_data(
    data: bytes, iv_bit_size: int = DEFAULT_IV_BIT_SIZE
) -> tuple[bytes, bytes]:
    iv_byte_size = iv_bit_size // BITS_PER_BYTE
    return data[:iv_byte_size], data[iv_byte_size:]


def decrypt_aesgcm(
    shared_secret: bytes, iv: bytes, data: bytes, associated_data: bytes = b""
):
    aesgcm = aead.AESGCM(shared_secret)
    return aesgcm.decrypt(iv, data, associated_data)


def encrypt_default(
    private_key: ec.EllipticCurvePrivateKey,
    public_key: ec.EllipticCurvePublicKey,
    data: bytes,
):
    shared_secret = exchange_ecdh_shared_secret(private_key, public_key)
    iv = random_iv()

    return iv + encrypt_aesgcm(shared_secret, iv, data)


def decrypt_default(
    private_key: ec.EllipticCurvePrivateKey,
    public_key: ec.EllipticCurvePublicKey,
    data: bytes,
):
    shared_secret = exchange_ecdh_shared_secret(private_key, public_key)
    iv, data = split_iv_from_data(data)

    return decrypt_aesgcm(shared_secret, iv, data)
