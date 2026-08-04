from app import total


def test_target_includes_last_value():
    assert total([2, 3, 5]) == 10


def test_regression_empty_values():
    assert total([]) == 0


def test_regression_trailing_zero():
    assert total([7, 0]) == 7
