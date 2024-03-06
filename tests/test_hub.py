import uuid

import pytest

pytestmark = pytest.mark.live


def _next_uuid():
    return str(uuid.uuid4())


def test_access_token(hub_access_token):
    pass
