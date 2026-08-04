import sqlite3

from app import find_user


def connection():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE users (id INTEGER, name TEXT)")
    db.executemany("INSERT INTO users VALUES (?, ?)", [(1, "Ada"), (2, "Grace")])
    return db


def test_target_does_not_treat_input_as_sql():
    result = find_user(connection(), "Ada' OR 1=1 --")
    assert result == []


def test_regression_finds_exact_name():
    assert find_user(connection(), "Ada") == [(1, "Ada")]


def test_regression_returns_empty_for_unknown_name():
    assert find_user(connection(), "Alan") == []
