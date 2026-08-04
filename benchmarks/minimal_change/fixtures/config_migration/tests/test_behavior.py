from config import read_timeout


def test_target_reads_new_seconds_schema():
    assert read_timeout({"timeout_seconds": 3}) == 3000


def test_regression_keeps_legacy_milliseconds():
    assert read_timeout({"timeout_ms": 250}) == 250


def test_regression_uses_default_timeout():
    assert read_timeout({}) == 1000
