from app import parse_object


def test_target_rejects_json_array():
    try:
        parse_object("[1, 2]")
    except ValueError:
        return
    raise AssertionError("array should not be accepted as an object")


def test_regression_parses_object():
    assert parse_object('{"name": "Ada"}') == {"name": "Ada"}


def test_regression_parses_nested_object():
    assert parse_object('{"meta": {"ok": true}}')["meta"]["ok"] is True
