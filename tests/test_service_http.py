"""The service over a real socket, driven by the real client."""
import socket
import threading

import pytest

from core.client import Client, NotRunning
from core.hud_state import HudState
from core.proposals import ProposalStore
from core.toolbox import Toolbox
from core.tools import Agency, Tool, ToolRegistry
from daemon.service import Jarvis, serve

TOKEN = "socket-token"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def running(tmp_path):
    done = []
    reg = ToolRegistry()
    reg.add(Tool("system.status", "report status", lambda: {"load_1m": 0.4}))
    reg.add(Tool("notes.append", "append a note", lambda text: done.append(text),
                 parameters={"text": {"type": "string"}}, required=("text",),
                 min_agency=Agency.ACTUATOR, mutates=True, confirm_label="Write"))
    jarvis = Jarvis(toolbox=Toolbox(registry=reg, agency=Agency.ACTUATOR,
                                    proposals=ProposalStore()),
                    state=HudState(), token=TOKEN)
    port = free_port()
    server = serve(jarvis, port=port, app_dir=str(tmp_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield port, done, jarvis
    finally:
        server.shutdown()
        server.server_close()


def test_nothing_listening_is_a_fact_to_branch_on_not_an_error():
    assert Client(port=free_port(), token="x").running() is False
    with pytest.raises(NotRunning):
        Client(port=free_port(), token="x").state()


def test_a_client_reads_state_over_the_socket(running):
    port, _, _ = running
    client = Client(port=port, token=TOKEN)
    assert client.running()
    assert client.state()["agency"] == "actuator"
    assert [t["name"] for t in client.tools()["tools"]] == \
        ["notes.append", "system.status"]


def test_a_client_without_the_token_may_read_but_not_act(running):
    port, done, _ = running
    stranger = Client(port=port, token="")
    assert stranger.state()["agency"] == "actuator"
    assert stranger.invoke("notes.append", {"text": "x"})["error"] == "not permitted"
    assert done == []


def test_two_clients_share_one_proposal_over_the_socket(running):
    """The reason the daemon exists, end to end: one surface raises it,
    another confirms it, and the work happens once."""
    port, done, _ = running
    raiser = Client(port=port, token=TOKEN)
    answerer = Client(port=port, token=TOKEN)

    raised = raiser.invoke("notes.append", {"text": "across processes"})
    assert raised["kind"] == "proposal"
    pid = raised["proposal"]["id"]
    assert done == [], "a proposal does not run when it is made"

    assert [p["id"] for p in answerer.proposals()["proposals"]] == [pid]
    assert answerer.answer(pid, "confirm")["proposal"]["status"] == "executed"
    assert done == ["across processes"]

    # and again, from the first client
    raiser.answer(pid, "confirm")
    assert done == ["across processes"], "confirming twice runs it once"


def test_the_served_page_carries_the_token_so_the_window_can_act(running, tmp_path):
    port, _, _ = running
    (tmp_path / "index.html").write_text("<html><head></head><body>hi</body></html>")
    import urllib.request
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as reply:
        page = reply.read().decode()
    assert f'window.JARVIS_TOKEN="{TOKEN}"' in page


def test_a_page_outside_the_app_directory_is_not_served(running):
    port, _, _ = running
    import urllib.error
    import urllib.request
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/../../etc/passwd")
    assert caught.value.code == 404


def test_the_stream_opens_with_the_current_state(running):
    port, _, _ = running
    import urllib.request
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/events",
                                timeout=5) as stream:
        first = stream.readline().decode()
    assert first.startswith("data: ") and "actuator" in first


# ---- the collision that killed the service 150 ms after systemd started it ----

def test_a_held_port_is_named_rather_than_a_bare_oserror():
    """`Address already in use` says nothing about which address or whose."""
    import socket as socket_module
    from daemon.service import PortBusy

    held = socket_module.socket()
    held.setsockopt(socket_module.SOL_SOCKET, socket_module.SO_REUSEADDR, 1)
    held.bind(("127.0.0.1", 0))
    held.listen(1)
    port = held.getsockname()[1]
    jarvis = Jarvis(toolbox=Toolbox(registry=ToolRegistry(),
                                    agency=Agency.ADVISORY),
                    state=HudState(), token="t")
    try:
        with pytest.raises(PortBusy) as caught:
            serve(jarvis, port=port)
        assert str(port) in str(caught.value)
        assert f"sport = :{port}" in caught.value.hint()
    finally:
        held.close()


def test_the_service_and_the_standalone_hud_do_not_want_the_same_port():
    """They both defaulted to 8787, so enabling jarvis-watch stopped the
    service from ever binding."""
    import inspect

    import hud.server as hud_server
    from daemon.service import DEFAULT_PORT

    hud_default = inspect.signature(hud_server.serve).parameters["port"].default
    assert hud_default != DEFAULT_PORT
    assert DEFAULT_PORT == 8787, "the service owns the front door"
