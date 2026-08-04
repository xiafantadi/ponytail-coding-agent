from app import host


def test_target_drops_explicit_port():
    assert host("https://Example.com:443/api") == "example.com"


def test_regression_plain_host():
    assert host("example.net") == "example.net"


def test_regression_url_without_port():
    assert host("http://Example.org/docs") == "example.org"
