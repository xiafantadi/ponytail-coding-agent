from pathlib import PurePosixPath

from app import config_path


def test_target_normalizes_trailing_separator():
    assert config_path("srv/app/") == str(PurePosixPath("srv/app") / "config.json")


def test_regression_joins_plain_root():
    assert config_path("srv/app") == str(PurePosixPath("srv/app") / "config.json")


def test_regression_uses_config_filename():
    assert PurePosixPath(config_path("tmp/service")).name == "config.json"
