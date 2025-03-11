import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers import aead

BITS_PER_BYTE = 8
DEFAULT_IV_BIT_SIZE = 96
DEFAULT_SHARED_SECRET_BIT_SIZE = 256

EllipticCurveKeyPair = tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]


# we only do ec in this household
# noinspection PyTypeChecker
def load_ecdh_public_key(public_key_bytes: bytes) -> ec.EllipticCurvePrivateKey:
    """Load an ECDH public key from bytes."""
    return serialization.load_pem_public_key(public_key_bytes)


def load_ecdh_private_key(private_key_bytes: bytes) -> ec.EllipticCurvePrivateKey:
    """Load an ECDH private key from bytes."""
    return serialization.load_pem_private_key(private_key_bytes, password=None)


def load_ecdh_public_key_from_path(public_key_path: Path):
    """Load an ECDH public key from a path pointing to a file."""
    with public_key_path.open(mode="rb") as f:
        return load_ecdh_public_key(f.read())


def load_ecdh_private_key_from_path(private_key_path: Path):
    """Load an ECDH private key from a path pointing to a file."""
    with private_key_path.open(mode="rb") as f:
        return load_ecdh_private_key(f.read())


def load_ecdh_public_key_from_hex_string(hex_str: str):
    """Load an ECDH public key from a hex representation of its bytes."""
    return load_ecdh_public_key(bytes.fromhex(hex_str))


def random_iv():
    """Generate a random 12-byte initialization vector using `random.urandom`."""
    return os.urandom(DEFAULT_IV_BIT_SIZE // BITS_PER_BYTE)


def exchange_ecdh_shared_secret(
    private_key: ec.EllipticCurvePrivateKey,
    public_key: ec.EllipticCurvePublicKey,
    bit_size: int = DEFAULT_SHARED_SECRET_BIT_SIZE,
) -> bytes:
    """Generate the shared secret key between the sender's private key and the recipient's public key."""
    if bit_size not in (256, 384):
        raise ValueError("size of secret key must be either 256 or 384 bits")

    shared_secret = private_key.exchange(ec.ECDH(), public_key)
    return shared_secret[: (bit_size // BITS_PER_BYTE)]


def encrypt_aesgcm(shared_secret: bytes, iv: bytes, data: bytes, associated_data: bytes = b""):
    """Encrypt bytes with AESGCM using the provided shared secret, initialization vector and associated data."""
    aesgcm = aead.AESGCM(shared_secret)
    return aesgcm.encrypt(iv, data, associated_data)


def split_iv_from_data(data: bytes, iv_bit_size: int = DEFAULT_IV_BIT_SIZE) -> tuple[bytes, bytes]:
    """Split the initialization vector from the ciphertext it's attached to."""
    iv_byte_size = iv_bit_size // BITS_PER_BYTE
    return data[:iv_byte_size], data[iv_byte_size:]


def decrypt_aesgcm(shared_secret: bytes, iv: bytes, data: bytes, associated_data: bytes = b""):
    """Decrypt bytes with AESGCM using the provided shared secret, initialization vector and associated data."""
    aesgcm = aead.AESGCM(shared_secret)
    return aesgcm.decrypt(iv, data, associated_data)


def encrypt_default(
    private_key: ec.EllipticCurvePrivateKey,
    public_key: ec.EllipticCurvePublicKey,
    data: bytes,
):
    """Encrypt data using AESGCM with the sender's private key and the recipient's public key.
    This function uses all defaults in this module for convenience.
    The generated 12-byte IV is prepended to the ciphertext.
    """
    shared_secret = exchange_ecdh_shared_secret(private_key, public_key)
    iv = random_iv()

    return iv + encrypt_aesgcm(shared_secret, iv, data)


def decrypt_default(
    private_key: ec.EllipticCurvePrivateKey,
    public_key: ec.EllipticCurvePublicKey,
    data: bytes,
):
    """Decrypt data using AESGCM with the recipient's private key and the sender's public key.
    This function uses all defaults in this module for convenience.
    The IV must be 12 bytes in length and prepended to the ciphertext."""
    shared_secret = exchange_ecdh_shared_secret(private_key, public_key)
    iv, data = split_iv_from_data(data)

    return decrypt_aesgcm(shared_secret, iv, data)
