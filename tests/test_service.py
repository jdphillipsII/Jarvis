"""One JARVIS, and the surfaces that are views of it."""
import pytest

from core.hud_state import HudState
from core.proposals import ProposalStore
from core.toolbox import Toolbox
from core.tools import Agency, Tool, ToolRegistry
from daemon.service import Api, Jarvis, write_token

TOKEN = "a-known-token"


@pytest.fixture
def jarvis():
    reg = ToolRegistry()
    reg.add(Tool("system.status", "report status", lambda: {"load_1m": 0.4}))
    reg.add(Tool("notes.append", "append a note", lambda text: f"wrote {text}",
                 parameters={"text": {"type": "string"}}, required=("text",),
                 min_agency=Agency.ACTUATOR, mutates=True, confirm_label="Write"))
    reg.add(Tool("shell.run", "run a command", lambda cmd: f"ran {cmd}",
                 parameters={"cmd": {"type": "string"}}, required=("cmd",),
                 min_agency=Agency.AGENTIC, mutates=True, risk="arbitrary execution"))
    box = Toolbox(registry=reg, agency=Agency.ACTUATOR, proposals=ProposalStore())
    return Jarvis(toolbox=box, state=HudState(), token=TOKEN)


@pytest.fixture
def api(jarvis):
    return Api(jarvis)


# ---- reading ----

def test_state_reports_agency_and_what_is_pending(api):
    code, body = api.handle("GET", "/api/state")
    assert code == 200
    assert body["agency"] == "actuator" and body["proposals"] == []
    assert "hud" in body


def test_tools_honour_the_agency_ceiling(api):
    _, body = api.handle("GET", "/api/tools")
    names = [t["name"] for t in body["tools"]]
    assert names == ["notes.append", "system.status"]
    assert "shell.run" not in names


def test_reading_needs_no_token(api):
    assert api.handle("GET", "/api/state")[0] == 200
    assert api.handle("GET", "/api/tools")[0] == 200
    assert api.handle("GET", "/api/proposals")[0] == 200


# ---- acting ----

def test_acting_without_a_token_is_refused(api):
    code, body = api.handle("POST", "/api/invoke", {"tool": "system.status"})
    assert code == 403 and body["error"] == "not permitted"



def test_a_wrong_token_says_exactly_what_no_token_says(api):
    """A caller probing for the difference learns nothing from the answer."""
    absent = api.handle("POST", "/api/invoke", {"tool": "system.status"})
    wrong = api.handle("POST", "/api/invoke", {"tool": "system.status"},
                       token="not-it")
    assert absent == wrong


def test_a_read_tool_runs_and_returns_its_value(api):
    code, body = api.handle("POST", "/api/invoke",
                            {"tool": "system.status"}, token=TOKEN)
    assert code == 200 and body["kind"] == "result"
    assert body["value"] == {"load_1m": 0.4}


def test_a_mutating_tool_returns_a_proposal_not_a_result(api):
    _, body = api.handle("POST", "/api/invoke",
                         {"tool": "notes.append", "args": {"text": "hello"}},
                         token=TOKEN)
    assert body["kind"] == "proposal"
    assert body["proposal"]["confirm_label"] == "Write"


def test_a_tool_above_the_ceiling_is_invisible_over_the_api(api):
    _, body = api.handle("POST", "/api/invoke",
                         {"tool": "shell.run", "args": {"cmd": "rm -rf /"}},
                         token=TOKEN)
    assert body["kind"] == "result" and not body["ok"]
    assert "no such tool" in body["error"]


# ---- the reason the service exists ----

def test_a_proposal_raised_by_one_surface_is_confirmable_by_another(api, jarvis):
    """The whole point. Voice raises it, the window confirms it, because both
    are talking to the same process."""
    _, raised = api.handle("POST", "/api/invoke",
                           {"tool": "notes.append", "args": {"text": "x"}},
                           token=TOKEN)
    pid = raised["proposal"]["id"]

    # a second surface, with no memory of the first
    elsewhere = Api(jarvis)
    _, seen = elsewhere.handle("GET", "/api/proposals")
    assert [p["id"] for p in seen["proposals"]] == [pid]

    _, done = elsewhere.handle("POST", "/api/answer",
                               {"id": pid, "answer": "confirm"}, token=TOKEN)
    assert done["proposal"]["status"] == "executed"


def test_confirming_twice_from_two_surfaces_runs_it_once(api, jarvis):
    ran = []
    reg = jarvis.toolbox.registry
    reg.add(Tool("notes.append", "append", lambda text: ran.append(text),
                 parameters={"text": {"type": "string"}}, required=("text",),
                 min_agency=Agency.ACTUATOR, mutates=True))
    _, raised = api.handle("POST", "/api/invoke",
                           {"tool": "notes.append", "args": {"text": "once"}},
                           token=TOKEN)
    pid = raised["proposal"]["id"]
    first = api.handle("POST", "/api/answer",
                       {"id": pid, "answer": "confirm"}, token=TOKEN)
    second = Api(jarvis).handle("POST", "/api/answer",
                                {"id": pid, "answer": "confirm"}, token=TOKEN)
    assert ran == ["once"]
    assert first[1]["proposal"]["status"] == second[1]["proposal"]["status"]


def test_declining_leaves_it_unrun(api):
    _, raised = api.handle("POST", "/api/invoke",
                           {"tool": "notes.append", "args": {"text": "x"}},
                           token=TOKEN)
    _, done = api.handle("POST", "/api/answer",
                         {"id": raised["proposal"]["id"], "answer": "decline"},
                         token=TOKEN)
    assert done["proposal"]["status"] == "declined"
    assert api.handle("GET", "/api/proposals")[1]["proposals"] == []


# ---- what the api will not do ----

def test_agency_cannot_be_raised_over_a_socket(api):
    """Raising the ceiling is a deliberate act by the user at the machine."""
    code, body = api.handle("POST", "/api/agency", {"agency": "agentic"},
                            token=TOKEN)
    assert code == 403 and "config/jarvis.env" in body["error"]


def test_an_unknown_path_and_a_wrong_method_say_so(api):
    assert api.handle("GET", "/api/nope")[0] == 404
    assert api.handle("DELETE", "/api/state")[0] == 405


def test_a_malformed_answer_is_refused(api):
    code, body = api.handle("POST", "/api/answer", {"id": "x", "answer": "maybe"},
                            token=TOKEN)
    assert code == 400 and "confirm or decline" in body["error"]


def test_saying_something_with_no_model_is_an_error_not_a_crash(api):
    code, body = api.handle("POST", "/api/say", {"text": "hello"}, token=TOKEN)
    assert code == 200 and "no model attached" in body["error"]


def test_trailing_slashes_and_queries_do_not_make_a_new_path(api):
    assert api.handle("GET", "/api/state/")[0] == 200
    assert api.handle("GET", "/api/state?since=4")[0] == 200


# ---- the token on disk ----

def test_the_token_file_is_readable_only_by_its_owner(tmp_path):
    import os
    import stat as stat_module
    path = str(tmp_path / "token")
    token = write_token(path)
    assert len(token) > 20
    mode = os.stat(path).st_mode
    assert not mode & stat_module.S_IRGRP and not mode & stat_module.S_IROTH


def test_a_service_with_no_token_permits_nothing(jarvis):
    jarvis.token = ""
    code, _ = Api(jarvis).handle("POST", "/api/invoke",
                                 {"tool": "system.status"}, token="")
    assert code == 403
