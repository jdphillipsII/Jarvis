import threading, time, os, tempfile
import pytest
from core.bus import Bus, SocketSource, send
from core.intent import Intent
from core.registry import Registry


@pytest.fixture
def bus():
    return Bus(registry=Registry.load(), enforce=True)


def test_delivers_to_matching_subscriber(bus):
    got = []
    bus.subscribe("workspace.next", got.append)
    assert bus.publish(Intent("workspace.next", "gesture", 0.9))
    assert len(got) == 1


def test_wildcard_subscriber_sees_everything(bus):
    seen = []
    bus.subscribe("*", lambda i: seen.append(i.intent))
    bus.publish(Intent("workspace.next", "gesture", 0.9))
    bus.publish(Intent("mic.mute", "voice", 1.0))
    assert seen == ["workspace.next", "mic.mute"]


def test_non_matching_subscriber_not_called(bus):
    got = []
    bus.subscribe("mic.mute", got.append)
    bus.publish(Intent("workspace.next", "gesture", 0.9))
    assert got == []


def test_registry_gate_blocks_low_confidence(bus):
    got = []
    bus.subscribe("mic.mute", got.append)
    assert bus.publish(Intent("mic.mute", "gesture", 0.5)) is False
    assert got == []
    assert bus.rejected and "floor" in bus.rejected[0][1]


def test_unknown_intent_never_reaches_actuators(bus):
    seen = []
    bus.subscribe("*", seen.append)
    assert bus.publish(Intent("system.launch_missiles", "voice", 1.0)) is False
    assert seen == []


def test_one_failing_handler_does_not_starve_the_others(bus):
    """The isolation guarantee: a crashing actuator must not break the bus."""
    order = []
    bus.subscribe("workspace.next", lambda i: order.append("first"))
    bus.subscribe("workspace.next", lambda i: (_ for _ in ()).throw(RuntimeError("boom")))
    bus.subscribe("workspace.next", lambda i: order.append("third"))

    assert bus.publish(Intent("workspace.next", "gesture", 0.9)) is True
    assert order == ["first", "third"]        # third still ran
    assert len(bus.errors) == 1
    # and the bus is still healthy afterwards
    assert bus.publish(Intent("workspace.next", "gesture", 0.9)) is True


def test_malformed_wire_input_is_dropped_not_raised(bus):
    seen = []
    bus.subscribe("*", seen.append)
    assert bus.publish_line("}{ not json") is False
    assert bus.publish_line('{"intent":"workspace.next","source":"gesture","confidence":0.9}')
    assert len(seen) == 1


def test_decorator_subscription(bus):
    got = []

    @bus.on("mic.mute")
    def _handler(i):
        got.append(i)

    bus.publish(Intent("mic.mute", "voice", 1.0))
    assert len(got) == 1


def test_socket_transport_end_to_end(bus):
    """An out-of-process source can publish without importing anything."""
    got = []
    bus.subscribe("workspace.next", got.append)
    path = os.path.join(tempfile.mkdtemp(), "jarvis.sock")
    src = SocketSource(bus, path).start()
    try:
        send(path, Intent("workspace.next", "gesture", 0.92))
        deadline = time.time() + 3
        while not got and time.time() < deadline:
            time.sleep(0.02)
        assert len(got) == 1
        assert got[0].source == "gesture"
    finally:
        src.stop()
