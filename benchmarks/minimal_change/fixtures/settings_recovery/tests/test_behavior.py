from app import load_settings


def test_target_preserves_previous_settings_on_parse_error():
    previous = {"mode": "safe", "retries": 2}
    assert load_settings("{broken", previous) == previous


def test_regression_loads_valid_settings():
    assert load_settings('{"mode": "fast"}', {}) == {"mode": "fast"}


def test_regression_keeps_empty_previous_settings():
    assert load_settings("{broken", {}) == {}
