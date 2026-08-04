from app import consume_quota


def test_target_blocks_exhaustion():
    assert consume_quota(3, 5) is None


def test_regression_consumes_available_quota():
    assert consume_quota(10, 4) == 6


def test_regression_zero_cost():
    assert consume_quota(0, 0) == 0
