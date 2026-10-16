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
