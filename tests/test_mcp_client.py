"""The consuming half of MCP: talking to somebody else's server."""
import json

import pytest

from core.mcp_client import McpClient, McpError, RemoteTool, _content


class FakeServer:
    """A canned MCP server. Records what it was asked."""

    def __init__(self, tools=None, result=None, error=None):
        self.tools = tools if tools is not None else [
            {"name": "measure", "description": "measure a shape",
             "inputSchema": {"type": "object",
                             "properties": {"shape": {"type": "string"}},
                             "required": ["shape"]}}]
        self.result = result
        self.error = error
        self.calls = []

    def __call__(self, request):
        self.calls.append(request)
        method = request["method"]
        if self.error:
            return {"jsonrpc": "2.0", "id": request["id"], "error": self.error}
        if method == "initialize":
            body = {"protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "fake", "version": "1.2.3"}}
        elif method == "tools/list":
            body = {"tools": self.tools}
        elif method == "tools/call":
            body = self.result if self.result is not None else {
                "content": [{"type": "text", "text": json.dumps({"volume": 12.5})}]}
        else:
            return {"jsonrpc": "2.0", "id": request["id"],
                    "error": {"code": -32601, "message": "unknown"}}
        return {"jsonrpc": "2.0", "id": request["id"], "result": body}


# ---- handshake and listing ----

def test_initialize_records_the_server_identity():
    client = McpClient(FakeServer(), name="fake")
    assert client.initialize()["name"] == "fake"
    assert client.server_info["version"] == "1.2.3"


def test_list_tools_parses_the_schema():
    tools = McpClient(FakeServer()).list_tools()
    assert [t.name for t in tools] == ["measure"]
    assert tools[0].properties == {"shape": {"type": "string"}}
    assert tools[0].required == ("shape",)


def test_a_nameless_tool_is_skipped_rather_than_mounted_as_empty():
    server = FakeServer(tools=[{"description": "no name here"},
                               {"name": "real", "description": "fine"}])
    assert [t.name for t in McpClient(server).list_tools()] == ["real"]


def test_request_ids_increment_so_replies_can_be_matched():
    server = FakeServer()
    client = McpClient(server)
    client.initialize()
    client.list_tools()
    assert [c["id"] for c in server.calls] == [1, 2]


# ---- results ----

def test_a_json_answer_comes_back_as_structure_not_a_string():
    """A server that replies with a document should reach the tool layer as a
    dict — the model reads either, but only one can be indexed downstream."""
    value = McpClient(FakeServer()).call_tool("measure", {"shape": "plate"})
    assert value == {"volume": 12.5}


def test_a_prose_answer_comes_back_as_prose():
    server = FakeServer(result={"content": [{"type": "text", "text": "all nominal"}]})
    assert McpClient(server).call_tool("measure", {}) == "all nominal"


def test_an_error_flagged_result_raises_rather_than_returning_a_value():
    server = FakeServer(result={"content": [{"type": "text", "text": "no such file"}],
                                "isError": True})
    with pytest.raises(McpError, match="no such file"):
        McpClient(server).call_tool("measure", {})


def test_a_jsonrpc_error_raises_with_the_bridge_named():
    server = FakeServer(error={"code": -32000, "message": "solidworks not running"})
    with pytest.raises(McpError, match="sw: solidworks not running"):
        McpClient(server, name="sw").initialize()


def test_a_malformed_response_is_an_error_not_a_crash():
    with pytest.raises(McpError, match="malformed"):
        McpClient(lambda req: "not a dict").initialize()
    with pytest.raises(McpError, match="no result"):
        McpClient(lambda req: {"jsonrpc": "2.0", "id": 1}).initialize()


def test_content_falls_back_to_the_whole_result_when_there_are_no_blocks():
    assert _content({"structured": 1}) == {"structured": 1}


# ---- what the server claims about itself ----

def test_read_only_hint_is_reported_when_given_and_none_when_not():
    assert RemoteTool("a", annotations={"readOnlyHint": True}).read_only is True
    assert RemoteTool("a", annotations={"readOnlyHint": False}).read_only is False
    assert RemoteTool("a", annotations={"destructiveHint": True}).read_only is False
    assert RemoteTool("a").read_only is None


# ---- the two halves agree ----

def test_our_client_can_drive_our_own_server():
    """mcp_server publishes, mcp_client consumes. If they ever disagree about
    the wire format this is the test that says so."""
    from core.mcp_server import McpServer
    from core.toolbox import Toolbox
    from core.tools import Agency, Tool, ToolRegistry

    reg = ToolRegistry()
    reg.add(Tool("system.status", "report status", lambda: {"load_1m": 0.4}))
    server = McpServer(Toolbox(registry=reg, agency=Agency.ADVISORY))

    client = McpClient(lambda req: server.handle(req), name="jarvis")
    assert client.initialize()["name"] == "jarvis"
    assert "system_status" in [t.name for t in client.list_tools()]
    assert client.call_tool("system_status", {}) == {"load_1m": 0.4}
