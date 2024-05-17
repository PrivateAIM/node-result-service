import random
import time
import uuid
from typing import Callable

from tests.common import env


def eventually(predicate: Callable[[], bool]) -> bool:
    """Return True if the predicate passed into this function returns True after a set amount of attempts.
    Between each attempt there is a delay of one second. The amount of retries can be configured with the
    PYTEST__ASYNC_MAX_RETRIES environment variable."""
    max_retries = int(env.async_max_retries())
    delay_secs = int(env.async_retry_delay_seconds())

    for _ in range(max_retries):
        if not predicate():
            time.sleep(delay_secs)

        return True

    return False


def next_uuid():
    """Get random UUID as string."""
    return str(uuid.uuid4())


def next_prefixed_name():
    """Get random UUID prefixed with 'node-it-'."""
    return f"node-it-{next_uuid()}"


def is_valid_uuid(val: str):
    """Return True if the value provided can be parsed into a valid UUID."""
    try:
        uuid.UUID(val)
    except ValueError:
        return False

    return True


def next_random_bytes(rng: random.Random, n: int = 16):
    """Return a bytes object with random content. (default length: 16)"""
    return rng.randbytes(n)
