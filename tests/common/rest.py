from httpx import Response


def detail_of(r: Response) -> str:
    return r.json()["detail"]
