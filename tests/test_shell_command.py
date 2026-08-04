import subprocess

from pico.core.shell_command import (
    join_shell_args,
    python_shell_command,
    split_shell_args,
)


def test_windows_shell_args_round_trip_executable_with_spaces():
    command = join_shell_args(
        [r"C:\Program Files\Python\python.exe", "-c", "print('hello world')"],
        platform="nt",
    )

    assert split_shell_args(command, platform="nt") == [
        r"C:\Program Files\Python\python.exe",
        "-c",
        "print('hello world')",
    ]


def test_posix_shell_args_quote_script_as_one_argument():
    command = join_shell_args(["python3", "-c", "print('hello world')"], platform="posix")

    assert split_shell_args(command, platform="posix") == [
        "python3",
        "-c",
        "print('hello world')",
    ]


def test_python_shell_command_preserves_multiline_exit_code():
    command = python_shell_command("-c", "print('before exit')\nraise SystemExit(7)")

    result = subprocess.run(command, shell=True, capture_output=True, text=True)

    assert result.returncode == 7
    assert result.stdout.strip() == "before exit"
