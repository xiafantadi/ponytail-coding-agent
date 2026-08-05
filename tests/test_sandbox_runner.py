import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from ponytail.features.sandbox.config import SandboxConfig
from ponytail.features.sandbox.runner import SandboxRunner
from ponytail.core.shell_command import python_shell_command


def test_required_sandbox_rejects_when_backend_is_unavailable(tmp_path):
    runner = SandboxRunner(
        SandboxConfig(mode="required", backend="bubblewrap"), which=lambda name: None
    )

    with pytest.raises(RuntimeError, match="sandbox required but unavailable"):
        runner.run("echo hi", cwd=tmp_path, env={}, timeout=5)


def test_required_sandbox_does_not_honor_excluded_commands(tmp_path):
    runner = SandboxRunner(
        SandboxConfig(mode="required", backend="bubblewrap", excluded_commands=("*",)),
        which=lambda name: None,
    )

    with pytest.raises(RuntimeError, match="sandbox required but unavailable"):
        runner.run("echo hi", cwd=tmp_path, env={}, timeout=5)


def test_best_effort_sandbox_records_degrade_and_runs_without_backend(tmp_path):
    events = []
    runner = SandboxRunner(
        SandboxConfig(mode="best_effort", backend="bubblewrap"),
        which=lambda name: None,
        emit_event=lambda event, payload: events.append((event, payload)),
    )

    result = runner.run(
        python_shell_command("-c", "print(42)"),
        cwd=tmp_path,
        env=os.environ.copy(),
        timeout=5,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "42"
    assert events[0][0] == "sandbox_unavailable"


def test_off_sandbox_keeps_plain_subprocess_behavior(tmp_path):
    runner = SandboxRunner(SandboxConfig(mode="off"), run=subprocess.run)

    result = runner.run(
        python_shell_command("-c", "import os; print(os.getcwd())"),
        cwd=tmp_path,
        env=os.environ.copy(),
        timeout=5,
    )

    assert Path(result.stdout.strip()) == tmp_path


def test_off_sandbox_starts_with_cleared_ambient_environment(tmp_path):
    runner = SandboxRunner(SandboxConfig(mode="off"), run=subprocess.run)

    with patch.dict(os.environ, {}, clear=True):
        result = runner.run(
            python_shell_command("-c", "print('ok')"),
            cwd=tmp_path,
            env={},
            timeout=5,
        )

    assert result.returncode == 0
    assert result.stdout.strip() == "ok"
