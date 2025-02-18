import random

from project.crypto import encrypt_default, decrypt_default
from tests.common.helpers import next_ecdh_keypair


def test_encrypt_decrypt():
    alice_private, alice_public = next_ecdh_keypair()
    bob_private, bob_public = next_ecdh_keypair()

    t = random.randbytes(1_024)  # generate arbitrary bytes
    ct = encrypt_default(alice_private, bob_public, t)
    t2 = decrypt_default(bob_private, alice_public, ct)

    assert t == t2
    assert ct != t
