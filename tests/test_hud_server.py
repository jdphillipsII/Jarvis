import json
import time
import urllib.request
import pytest

from core.hud_state import HudState
from core.intent import Intent
from hud.server import Hub, serve


@pytest.fixture
def running():
    hub = Hub(HudState())
    httpd = serve(hub, port=0)
    port = httpd.socket.getsockname()[1]
    yield hub, f"http://127.0.0.1:{port}"
    httpd.shutdown()


def get(url, path):
    with urllib.request.urlopen(url + path, timeout=5) as r:
        return json.loads(r.read())


def post(url, payload):
    req = urllib.request.Request(url + "/answer", method="POST",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, json.loads(r.read())


def test_serves_the_page(running):
    _, url = running
    with urllib.request.urlopen(url + "/", timeout=5) as r:
        body = r.read().decode()
    assert r.status == 200 and "JARVIS" in body


def test_state_starts_calm(running):
    _, url = running
    assert get(url, "/state")["state"] == "calm"


def test_an_offer_intent_raises_the_state(running):
    hub, url = running
    hub.on_intent(Intent("jarvis.offer", "system", 1.0,
                         {"text": "GPU warm, sir.", "urgency": "warn",
                          "category": "gpu", "reason": "attention available"}))
    snap = get(url, "/state")
    assert snap["state"] == "elevated"
    assert snap["offers"][0]["text"] == "GPU warm, sir."


def test_a_badge_does_not_raise_the_state(running):
    hub, url = running
    hub.on_intent(Intent("jarvis.badge", "system", 1.0,
                         {"text": "noted", "urgency": "warn", "category": "x"}))
    snap = get(url, "/state")
    assert snap["state"] == "calm" and snap["feed"]


def test_confirming_from_the_hud_reaches_the_callback(running):
    hub, url = running
    answered = []
    hub.on_answer = lambda i, verb: answered.append((i, verb))
    hub.on_intent(Intent("jarvis.offer", "system", 1.0,
                         {"id": "o1", "text": "do it?", "urgency": "warn",
                          "category": "x"}))
    status, body = post(url, {"id": "o1", "answer": "confirm"})
    assert status == 200 and body["ok"]
    assert answered == [("o1", "confirm")]
    assert get(url, "/state")["offers"] == []       # cleared from the ring


def test_declining_is_reported_too(running):
    hub, url = running
    answered = []
    hub.on_answer = lambda i, verb: answered.append(verb)
    hub.on_intent(Intent("jarvis.offer", "system", 1.0,
                         {"id": "o2", "text": "x", "urgency": "info", "category": "c"}))
    post(url, {"id": "o2", "answer": "decline"})
    assert answered == ["decline"]


def test_a_forged_answer_verb_is_refused(running):
    hub, url = running
    hub.on_answer = lambda i, verb: pytest.fail("must not fire")
    with pytest.raises(urllib.error.HTTPError) as e:
        post(url, {"id": "x", "answer": "sudo"})
    assert e.value.code == 400


def test_malformed_body_does_not_crash_the_server(running):
    hub, url = running
    req = urllib.request.Request(url + "/answer", method="POST", data=b"{{{",
                                 headers={"Content-Type": "application/json"})
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(req, timeout=5)
    assert get(url, "/state")["state"] == "calm"     # still serving


def test_presence_updates_the_chip(running):
    hub, url = running
    hub.on_presence(Intent("presence.left", "presence", 0.9))
    assert get(url, "/state")["present"] is False
    hub.on_presence(Intent("presence.arrived", "presence", 0.9))
    assert get(url, "/state")["present"] is True


def test_slow_clients_are_dropped_not_queued_forever(running):
    """A stalled tab must not grow memory without bound."""
    hub, _ = running
    q = hub.subscribe()
    for _ in range(100):
        hub.broadcast()
    assert q.qsize() <= 32
