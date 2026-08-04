from pathlib import Path

from app import safe_join


def test_target_rejects_parent_escape():
    try:
        safe_join("/srv/app", "../secret.txt")
    except ValueError:
        return
    raise AssertionError("parent traversal should be rejected")


def test_regression_keeps_child_path():
    assert safe_join("/srv/app", "logs/today.txt") == str(Path("/srv/app/logs/today.txt"))


def test_regression_keeps_root_file():
    assert safe_join("/srv/app", "config.json") == str(Path("/srv/app/config.json"))
