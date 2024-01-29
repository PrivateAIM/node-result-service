import io
import random

from httpx import Response


def detail_of(r: Response) -> str:
    """Retrieve the content of the `detail` key within an error response."""
    return r.json()["detail"]


def next_random_bytes(rng: random.Random, n: int = 16):
    """Return a bytes object with random content. (default length: 16)"""
    return rng.randbytes(n)


def wrap_bytes_for_request(b: bytes):
    """Wrap a bytes object into a dictionary s.t. it can be passed into a httpx request."""
    return {"file": io.BytesIO(b)}
