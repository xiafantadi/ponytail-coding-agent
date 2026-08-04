from app import is_retryable


def test_target_accepts_string_status_from_http_client():
    assert is_retryable("503") is True


def test_regression_accepts_integer_status():
    assert is_retryable(502) is True


def test_regression_rejects_success_status():
    assert is_retryable(200) is False
