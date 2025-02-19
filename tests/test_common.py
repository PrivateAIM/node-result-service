from project.common import build_url


def test_build_url():
    assert (
        build_url("http", "privateaim.de", "analysis", {"foo": "bar"}, "baz")
        == "http://privateaim.de/analysis?foo=bar#baz"
    )
