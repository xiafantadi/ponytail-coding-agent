"""Deterministic, cross-platform benchmark verifier execution."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from pico.core.shell_command import split_shell_args


_SHELL_OPERATORS = {"&&", "||", "|", ";", ">", ">>", "<", "2>", "2>>"}
_PYTHON_COMMANDS = {"python", "python3", "python.exe", "python3.exe"}


def build_verifier_argv(command) -> list[str]:
    """Convert a verifier command into argv without invoking a shell."""
    if isinstance(command, (list, tuple)):
        args = [str(value) for value in command]
    else:
        args = split_shell_args(str(command))
    if not args:
        raise ValueError("verifier command must not be empty")
    unsupported = _SHELL_OPERATORS.intersection(args)
    if unsupported:
        operators = ", ".join(sorted(unsupported))
        raise ValueError(f"verifier command must not use shell operators: {operators}")
    if Path(args[0]).name.lower() in _PYTHON_COMMANDS:
        args[0] = sys.executable
    return args


def run_verifier(command, *, cwd, timeout=30):
    """Run a verifier as structured argv and return its completed process."""
    return subprocess.run(
        build_verifier_argv(command),
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
