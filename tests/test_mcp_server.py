import io
import json
import pytest

from core.mcp_server import CONFIRM, DECLINE, McpServer, PROTOCOL_VERSION
from core.toolbox import Toolbox
from core.tools import Agency, Tool, ToolRegistry


@pytest.fixture
def server():
    r = ToolRegistry()
    r.add(Tool("system.status", "report status", lambda: {"gpu_temp_c": 61}))
    r.add(Tool("notes.append", "append a note", lambda text: f"noted: {text}",
               parameters={"text": {"type": "string"}}, required=("text",),
               min_agency=Agency.ACTUATOR, mutates=True))
    r.add(Tool("shell.run", "run a command", lambda cmd: "ran",
               parameters={"cmd": {"type": "string"}}, required=("cmd",),
               min_agency=Agency.AGENTIC, mutates=True))
    return McpServer(Toolbox(registry=r, agency=Agency.ACTUATOR))


def rpc(server, method, params=None, rid=1):
    return server.handle({"jsonrpc": "2.0", "id": rid, "method": method,
                          "params": params or {}})


# ---- handshake ----

def test_initialize_advertises_tools():
    s = McpServer(Toolbox(registry=ToolRegistry()))
    r = rpc(s, "initialize")["result"]
    assert r["protocolVersion"] == PROTOCOL_VERSION
    assert "tools" in r["capabilities"]
    assert r["serverInfo"]["name"] == "jarvis"


def test_notifications_get_no_reply(server):
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_unknown_method_errors_but_does_not_crash(server):
    assert rpc(server, "nonsense/thing")["error"]["code"] == -32601


# ---- listing ----

def test_dots_become_underscores(server):
    names = [t["name"] for t in rpc(server, "tools/list")["result"]["tools"]]
    assert "system_status" in names and "notes_append" in names


def test_tools_above_agency_are_not_listed(server):
    names = [t["name"] for t in rpc(server, "tools/list")["result"]["tools"]]
    assert "shell_run" not in names


def test_mutating_tools_advertise_that_they_only_propose(server):
    tools = {t["name"]: t for t in rpc(server, "tools/list")["result"]["tools"]}
    assert "does not execute" in tools["notes_append"]["description"]
    assert CONFIRM in tools["notes_append"]["description"]


def test_confirm_and_decline_are_offered(server):
    names = [t["name"] for t in rpc(server, "tools/list")["result"]["tools"]]
    assert CONFIRM in names and DECLINE in names


def test_schema_is_carried_through(server):
    tools = {t["name"]: t for t in rpc(server, "tools/list")["result"]["tools"]}
    schema = tools["notes_append"]["inputSchema"]
    assert schema["required"] == ["text"]
    assert schema["properties"]["text"]["type"] == "string"


# ---- calling ----

def test_read_tool_returns_its_value(server):
    out = rpc(server, "tools/call", {"name": "system_status", "arguments": {}})["result"]
    assert "61" in out["content"][0]["text"]
    assert not out.get("isError")


def test_unknown_tool_is_an_error_not_a_crash(server):
    out = rpc(server, "tools/call", {"name": "nope", "arguments": {}})["result"]
    assert out["isError"] and "no such tool" in out["content"][0]["text"]


def test_a_gated_tool_looks_exactly_like_a_missing_one(server):
    """Never confirm that a capability exists above the caller's agency."""
    gated = rpc(server, "tools/call", {"name": "shell_run",
                                       "arguments": {"cmd": "x"}})["result"]
    missing = rpc(server, "tools/call", {"name": "nope",
                                         "arguments": {"cmd": "x"}})["result"]
    a = gated["content"][0]["text"].replace("shell_run", "X")
    b = missing["content"][0]["text"].replace("nope", "X")
    assert a == b and gated["isError"] and missing["isError"]


def test_bad_arguments_are_rejected_before_the_handler(server):
    out = rpc(server, "tools/call", {"name": "notes_append",
                                     "arguments": {}})["result"]
    assert out["isError"] and "missing required" in out["content"][0]["text"]


# ---- the consent guarantee across the boundary ----

def test_a_mutating_call_proposes_and_does_not_execute(server):
    out = rpc(server, "tools/call",
              {"name": "notes_append", "arguments": {"text": "hi"}})["result"]
    payload = json.loads(out["content"][0]["text"])
    assert payload["status"] == "proposal"
    assert payload["confirm_with"] == CONFIRM
    assert server.toolbox.proposals.pending()          # nothing ran


def test_confirm_executes_it(server):
    made = rpc(server, "tools/call",
               {"name": "notes_append", "arguments": {"text": "hi"}})["result"]
    pid = json.loads(made["content"][0]["text"])["proposal_id"]
    out = rpc(server, "tools/call",
              {"name": CONFIRM, "arguments": {"proposal_id": pid}})["result"]
    assert "noted: hi" in out["content"][0]["text"]


def test_declining_prevents_execution(server):
    made = rpc(server, "tools/call",
               {"name": "notes_append", "arguments": {"text": "hi"}})["result"]
    pid = json.loads(made["content"][0]["text"])["proposal_id"]
    rpc(server, "tools/call", {"name": DECLINE, "arguments": {"proposal_id": pid}})
    out = rpc(server, "tools/call",
              {"name": CONFIRM, "arguments": {"proposal_id": pid}})["result"]
    assert out["isError"] and "declined" in out["content"][0]["text"]


def test_confirming_nonsense_does_not_crash(server):
    out = rpc(server, "tools/call",
              {"name": CONFIRM, "arguments": {"proposal_id": "deadbeef"}})["result"]
    assert out["isError"]


# ---- the stdio loop ----

def test_serve_round_trips_over_pipes(server):
    lines = [json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
             json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
             json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})]
    out = io.StringIO()
    server.serve(io.StringIO("\n".join(lines) + "\n"), out)
    replies = [json.loads(l) for l in out.getvalue().splitlines()]
    assert [r["id"] for r in replies] == [1, 2]        # notification got no reply


def test_a_malformed_frame_does_not_kill_the_session(server):
    payload = "}{ not json\n" + json.dumps(
        {"jsonrpc": "2.0", "id": 7, "method": "ping"}) + "\n"
    out = io.StringIO()
    server.serve(io.StringIO(payload), out)
    assert json.loads(out.getvalue().strip())["id"] == 7
