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
