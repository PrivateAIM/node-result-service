import io

from httpx import Response


def detail_of(r: Response) -> str:
    """Retrieve the content of the `detail` key within an error response."""
    return r.json()["detail"]


def wrap_bytes_for_request(b: bytes):
    """Wrap a bytes object into a dictionary s.t. it can be passed into a httpx request."""
    return {"file": io.BytesIO(b)}
