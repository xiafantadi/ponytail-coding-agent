from app import is_valid_token


def test_target_rejects_wrong_prefix():
    assert is_valid_token("key_0123456789abcdef") is False


def test_regression_accepts_valid_token():
    assert is_valid_token("tok_0123456789abcdef") is True


def test_regression_rejects_short_value():
    assert is_valid_token("tok_123") is False
