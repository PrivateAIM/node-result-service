import urllib.parse


def build_url(
    scheme="", netloc="", path="", query: dict[str, str] | None = None, fragment=""
):
    if query is None:
        query = {}

    return urllib.parse.urlunsplit(
        (
            scheme,
            netloc,
            path,
            # square brackets must not be encoded to support central filtering stuff
            urllib.parse.urlencode(query, safe="[]"),
            fragment,
        ),
    )
