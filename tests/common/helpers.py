import random
import time
import uuid
from typing import Callable

from tests.common.env import PYTEST_ASYNC_MAX_RETRIES


def eventually(predicate: Callable[[], bool]) -> bool:
    max_retries = int(PYTEST_ASYNC_MAX_RETRIES)

    for _ in range(max_retries):
        if not predicate():
            time.sleep(1)

        return True

    return False


def next_uuid():
    return str(uuid.uuid4())


def next_prefixed_name():
    return f"node-it-{next_uuid()}"


def is_valid_uuid(val: str):
    try:
        uuid.UUID(val)
    except ValueError:
        return False

    return True


def next_random_bytes(rng: random.Random, n: int = 16):
    """Return a bytes object with random content. (default length: 16)"""
    return rng.randbytes(n)
