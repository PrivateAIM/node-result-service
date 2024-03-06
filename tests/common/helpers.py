import time
from typing import Callable

from tests.common.env import PYTEST_ASYNC_MAX_RETRIES


def eventually(predicate: Callable[[], bool]) -> bool:
    max_retries = int(PYTEST_ASYNC_MAX_RETRIES)

    for _ in range(max_retries):
        if not predicate():
            time.sleep(1)

        return True

    return False
