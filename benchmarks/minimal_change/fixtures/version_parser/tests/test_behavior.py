from app import parse_version


def test_target_pads_minor_version():
    assert parse_version("2.4") == (2, 4, 0)


def test_regression_full_version():
    assert parse_version("1.2.3") == (1, 2, 3)


def test_regression_zero_version():
    assert parse_version("0.0.1") == (0, 0, 1)
