"""Cross-platform helpers for shell command construction and inspection."""

import os
import shlex
import subprocess
import sys

_HOST_WINDOWS_SHELL = os.environ.get("COMSPEC") or os.environ.get("ComSpec")


def shell_executable(*, platform=None):
    if (platform or os.name) == "nt":
        return _HOST_WINDOWS_SHELL
    return None


def run_shell_process(command, **kwargs):
    kwargs["shell"] = True
    executable = shell_executable()
    if executable:
        kwargs["executable"] = executable
    return subprocess.run(command, **kwargs)


def join_shell_args(args, *, platform=None):
    values = [str(value) for value in args]
    if (platform or os.name) == "nt":
        return subprocess.list2cmdline(values)
    return shlex.join(values)


def python_shell_command(*args):
    values = list(args)
    if len(values) >= 2 and values[0] == "-c" and "\n" in str(values[1]):
        values[1] = f"exec({str(values[1])!r})"
    return join_shell_args([sys.executable, *values])


def split_shell_args(command, *, platform=None):
    is_windows = (platform or os.name) == "nt"
    tokens = shlex.split(str(command), posix=not is_windows)
    return [token.strip("\"'") for token in tokens]
