import os
import pytest
from core.config import cfg


@pytest.fixture
def envfile(tmp_path):
    p = tmp_path / "jarvis.env"
    p.write_text('JARVIS_CAM=http://192.168.1.42:8080/video\n'
                 'JARVIS_AGENCY=actuator   # trailing comment\n'
                 'QUOTED="en_GB-alan-medium"\n')
    return str(p)


def test_reads_from_file(envfile):
    assert cfg("JARVIS_CAM", path=envfile) == "http://192.168.1.42:8080/video"


def test_strips_trailing_comments_and_quotes(envfile):
    assert cfg("JARVIS_AGENCY", path=envfile) == "actuator"
    assert cfg("QUOTED", path=envfile) == "en_GB-alan-medium"


def test_env_wins_over_file(envfile, monkeypatch):
    """So a single run can override without editing config."""
    monkeypatch.setenv("JARVIS_CAM", "0")
    assert cfg("JARVIS_CAM", path=envfile) == "0"


def test_default_when_absent(envfile):
    assert cfg("NOT_THERE", "fallback", path=envfile) == "fallback"


def test_missing_file_is_not_an_error(tmp_path):
    assert cfg("ANY", "d", path=str(tmp_path / "nope.env")) == "d"


def test_falls_back_to_the_example_when_no_local_config(monkeypatch, tmp_path):
    """A fresh clone has only jarvis.env.example — the CLI must still work."""
    import core.config as c
    monkeypatch.setattr(c, "CONFIG_PATH", str(tmp_path / "absent.env"))
    monkeypatch.setattr(c, "EXAMPLE_PATH", str(tmp_path / "absent.env.example"))
    (tmp_path / "absent.env.example").write_text("JARVIS_AGENCY=advisory\n")
    assert c.cfg("JARVIS_AGENCY") == "advisory"


def test_local_config_wins_over_the_example(monkeypatch, tmp_path):
    import core.config as c
    (tmp_path / "j.env").write_text("JARVIS_AGENCY=actuator\n")
    (tmp_path / "j.env.example").write_text("JARVIS_AGENCY=advisory\n")
    monkeypatch.setattr(c, "CONFIG_PATH", str(tmp_path / "j.env"))
    monkeypatch.setattr(c, "EXAMPLE_PATH", str(tmp_path / "j.env.example"))
    assert c.cfg("JARVIS_AGENCY") == "actuator"
