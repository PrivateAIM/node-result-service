import urllib.parse


def build_url(scheme="", netloc="", path="", query: dict[str, str] | None = None, fragment=""):
    """
    Build a URL consisting of multiple parts.
    The function signature is identical to that of `urllib.parse.urlunsplit`, except that query parameters can be
    passed in as a dictionary and are automatically encoded.
    Furthermore, square brackets are not encoded to support the filtering mechanisms of the FLAME Hub API.

    Args:
        scheme: URL scheme specifier
        netloc: network location part
        path: hierarchical path
        query: query component
        fragment: fragment identifier

    Returns:
        combination of all parameters into a complete URL
    """
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
