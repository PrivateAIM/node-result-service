from project.server import load_pyproject


def test_load_pyproject():
    # should parse correctly
    _ = load_pyproject()
