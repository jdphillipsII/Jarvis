"""Putting `jarvis` on PATH.

Every doc in this repo said `jarvis install` for weeks, and `jarvis` was never
a command. These are the tests that would have caught that.
"""
import os
import subprocess
import sys

import cli


def test_the_launcher_points_at_this_checkout():
    body = cli.launcher_body("/home/someone/jarvis")
    assert 'ROOT="/home/someone/jarvis"' in body
    assert "$ROOT/cli.py" in body


def test_the_venv_is_resolved_at_run_time_not_baked_in():
    """So creating the audio venv later is enough; the launcher does not need
    regenerating when the stack arrives."""
    body = cli.launcher_body("/x")
    assert '[ -x "$PY" ] || PY="$(command -v python3)"' in body
    assert body.index('PY="$ROOT/.venvs') < body.index("command -v python3")


def test_arguments_are_passed_through():
    assert 'exec "$PY" "$ROOT/cli.py" "$@"' in cli.launcher_body("/x")


def test_the_launcher_actually_runs(tmp_path):
    target = tmp_path / "jarvis"
    target.write_text(cli.launcher_body(cli.ROOT))
    target.chmod(0o755)
    done = subprocess.run([str(target), "--help"], capture_output=True, text=True)
    assert done.returncode == 0
    assert "jarvis link" in done.stdout


def test_it_goes_where_the_path_advice_says_it_goes():
    assert cli.bin_dir() == os.path.expanduser("~/.local/bin")


def test_doctor_checks_that_the_command_it_recommends_exists():
    """The tool for finding what is missing should find this missing."""
    source = open(os.path.join(cli.ROOT, "cli.py")).read()
    assert '"jarvis on PATH"' in source
    assert "cli.py link" in source


def test_packaging_declares_the_module_the_script_imports():
    """pyproject declared a `jarvis = cli:main` script while `cli` was not in
    packages, so a pip install produced a command that failed to import."""
    with open(os.path.join(cli.ROOT, "pyproject.toml")) as fh:
        body = fh.read()
    assert 'jarvis = "cli:main"' in body
    assert 'py-modules = ["cli"]' in body


# ---- the other half of the dual boot ----
#
# The engine is portable; only the layer that puts a command on PATH and runs
# something at login is not. These pin that layer to both shapes.

def test_the_launcher_has_a_shape_for_each_half_of_the_dual_boot():
    posix = cli.launcher_body("/home/jp/jarvis", "posix")
    windows = cli.launcher_body(r"C:\Users\jp\jarvis", "windows")
    assert posix.startswith("#!/usr/bin/env bash")
    assert windows.startswith("@echo off")
    assert cli.launcher_name("posix") == "jarvis"
    assert cli.launcher_name("windows") == "jarvis.cmd"


def test_the_windows_launcher_resolves_its_venv_at_run_time_too():
    body = cli.launcher_body(r"C:\jarvis", "windows")
    assert r".venvs\Scripts\python.exe" in body.replace("\\voice", "")
    assert 'if not exist "%PY%" set "PY=python"' in body
    assert '"%ROOT%\\cli.py" %*' in body


def test_each_half_puts_the_command_where_that_os_looks():
    assert cli.bin_dir("posix").endswith(os.path.join(".local", "bin"))
    windows = cli.bin_dir("windows")
    assert windows.endswith(os.path.join("Programs", "jarvis"))


def test_windows_gets_a_window_launcher_of_its_own():
    cmd = os.path.join(cli.ROOT, "setup", "app", "jarvis-window.cmd")
    assert os.path.exists(cmd), "the Linux launcher is bash and will not run"
    body = open(cmd).read()
    assert "--app=" in body and "msedge.exe" in body
    assert "jarvis install" in body, "it should say how to fix a missing install"


def test_the_posix_only_checks_are_behind_a_platform_test():
    """doctor used to shell out to `id -nG` and systemctl unconditionally."""
    source = open(os.path.join(cli.ROOT, "cli.py")).read()
    guard = source.index('if host() == "windows":')
    assert guard < source.index('"id", "-nG"')
    assert guard < source.index("systemctl\", \"--user\", \"is-active\"")


def test_the_windows_path_advice_is_not_the_setx_footgun():
    """`setx PATH "%PATH%;..."` expands the joined system+user PATH and writes
    it back into the user variable, duplicating the system half and truncating
    at 1024 characters. It is the classic way to lose your PATH."""
    printed = [line for line in open(os.path.join(cli.ROOT, "cli.py"))
               if "print(" in line]
    assert not [line for line in printed if "setx" in line], \
        "it is explained in a comment; it must never be recommended"
    assert any("SetEnvironmentVariable" in line for line in printed)
    assert any('"User"' in line for line in printed)
