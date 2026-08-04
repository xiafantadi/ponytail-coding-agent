import sys

import pytest

from pico.evaluation.verifier import build_verifier_argv, run_verifier


def test_build_verifier_argv_maps_python_alias_to_current_interpreter():
    args = build_verifier_argv('python3 -c "raise SystemExit(0)"')

    assert args == [sys.executable, "-c", "raise SystemExit(0)"]


def test_run_verifier_preserves_python_exit_code(tmp_path):
    result = run_verifier('python -c "raise SystemExit(7)"', cwd=tmp_path)

    assert result.returncode == 7


def test_build_verifier_argv_rejects_shell_composition():
    with pytest.raises(ValueError, match="must not use shell operators"):
        build_verifier_argv('python -c "print(1)" && echo done')
