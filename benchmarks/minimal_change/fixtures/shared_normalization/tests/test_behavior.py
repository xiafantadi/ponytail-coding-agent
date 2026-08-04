from app import get, put


def test_target_get_uses_shared_normalization():
    put(" User-1 ", "active")
    assert get(" user-1 ") == "active"


def test_regression_exact_key_lookup():
    put("user-2", "pending")
    assert get("user-2") == "pending"


def test_regression_missing_key():
    assert get("missing") is None
