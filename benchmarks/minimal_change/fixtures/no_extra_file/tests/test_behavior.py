from app import is_enabled


def test_target_parses_false_text():
    assert is_enabled("false") is False


def test_regression_true_boolean():
    assert is_enabled(True) is True


def test_regression_false_boolean():
    assert is_enabled(False) is False
