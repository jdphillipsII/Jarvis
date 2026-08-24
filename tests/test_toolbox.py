import pytest
from core.proposals import ProposalStatus, ProposalStore
from core.toolbox import Toolbox
from core.tools import Agency, Tool, ToolRegistry, ToolResult


@pytest.fixture
def reg():
    r = ToolRegistry()
    r.add(Tool("system.status", "report system status", lambda: "all nominal"))
    r.add(Tool("notes.append", "append a note", lambda text: f"wrote {text}",
               parameters={"text": {"type": "string"}}, required=("text",),
               min_agency=Agency.ACTUATOR, mutates=True))
    r.add(Tool("shell.run", "run a shell command", lambda cmd: f"ran {cmd}",
               parameters={"cmd": {"type": "string"}}, required=("cmd",),
               min_agency=Agency.AGENTIC, mutates=True, risk="arbitrary execution"))
    return r


def box(reg, agency=Agency.ACTUATOR, ttl=300.0, clock=None):
    store = ProposalStore(ttl_s=ttl, **({"clock": clock} if clock else {}))
    return Toolbox(registry=reg, agency=agency, proposals=store)


# ---- the agency ceiling ----

def test_a_tool_above_agency_is_invisible_and_uncallable(reg):
    b = box(reg, Agency.ACTUATOR)
    assert "shell.run" not in b.catalogue()
    assert [s["function"]["name"] for s in b.schemas()] == ["system.status", "notes.append"]
    r = b.invoke("shell.run", {"cmd": "rm -rf /"})
    assert not r.ok and "no such tool" in r.error


def test_an_over_agency_tool_is_indistinguishable_from_a_missing_one(reg):
    """Don't confirm the existence of capabilities the user hasn't unlocked:
    probing for shell.run must look exactly like probing for a typo."""
    b = box(reg, Agency.ADVISORY)
    real = b.invoke("shell.run", {"cmd": "x"})
    fake = b.invoke("nope.nope", {"cmd": "x"})
    assert real.ok is fake.ok is False
    assert real.error.replace("shell.run", "X") == fake.error.replace("nope.nope", "X")


def test_advisory_cannot_mutate_anything(reg):
    b = box(reg, Agency.ADVISORY)
    assert not b.invoke("notes.append", {"text": "hi"}).ok
    assert b.invoke("system.status").ok


# ---- read path ----

def test_read_tools_execute_immediately(reg):
    r = box(reg).invoke("system.status")
    assert r.ok and r.value == "all nominal"


def test_bad_arguments_are_refused_before_the_handler_runs(reg):
    called = []
    reg.add(Tool("t.spy", "spy", lambda n: called.append(n),
                 parameters={"n": {"type": "integer"}}, required=("n",)))
    r = box(reg).invoke("t.spy", {"n": "not a number"})
    assert not r.ok and called == []


def test_a_throwing_handler_returns_an_error_not_an_exception(reg):
    reg.add(Tool("t.boom", "boom", lambda: (_ for _ in ()).throw(IOError("disk gone"))))
    r = box(reg).invoke("t.boom")
    assert not r.ok and "disk gone" in r.error


# ---- consent ----

def test_a_mutating_tool_proposes_instead_of_acting(reg):
    p = box(reg).invoke("notes.append", {"text": "buy a camera mount"})
    assert p.status is ProposalStatus.PROPOSED
    assert "buy a camera mount" in p.summary


def test_nothing_happens_until_confirmed(reg):
    done = []
    reg.add(Tool("t.act", "act", lambda: done.append(1),
                 min_agency=Agency.ACTUATOR, mutates=True))
    b = box(reg)
    p = b.invoke("t.act")
    assert done == []
    b.confirm(p.id)
    assert done == [1]


def test_declining_never_executes(reg):
    done = []
    reg.add(Tool("t.act", "act", lambda: done.append(1),
                 min_agency=Agency.ACTUATOR, mutates=True))
    b = box(reg)
    p = b.invoke("t.act")
    b.decline(p.id)
    assert b.confirm(p.id).status is ProposalStatus.DECLINED
    assert done == []


def test_confirming_twice_runs_once(reg):
    """Voice and the HUD can both confirm; the action must not double-fire."""
    runs = []
    reg.add(Tool("t.act", "act", lambda: runs.append(1) or "ok",
                 min_agency=Agency.ACTUATOR, mutates=True))
    b = box(reg)
    p = b.invoke("t.act")
    first, second = b.confirm(p.id), b.confirm(p.id)
    assert runs == [1]
    assert second.status is first.status is ProposalStatus.EXECUTED


def test_expiry_is_a_state_not_an_error(reg):
    t = [0.0]
    b = box(reg, ttl=60.0, clock=lambda: t[0])
    p = b.invoke("notes.append", {"text": "x"})
    t[0] = 61.0
    assert b.confirm(p.id).status is ProposalStatus.EXPIRED


def test_confirming_an_unknown_proposal_does_not_raise(reg):
    assert box(reg).confirm("deadbeef").status is ProposalStatus.EXPIRED


def test_a_failing_handler_marks_the_proposal_failed(reg):
    reg.add(Tool("t.bad", "bad", lambda: (_ for _ in ()).throw(RuntimeError("nope")),
                 min_agency=Agency.ACTUATOR, mutates=True))
    b = box(reg)
    p = b.confirm(b.invoke("t.bad").id)
    assert p.status is ProposalStatus.FAILED and "nope" in p.result.error


def test_agency_is_rechecked_at_confirm_time(reg):
    """A proposal made under a higher agency must not execute after it drops."""
    b = box(reg, Agency.AGENTIC)
    p = b.invoke("shell.run", {"cmd": "echo hi"})
    b.agency = Agency.ACTUATOR
    out = b.confirm(p.id)
    assert out.status is ProposalStatus.FAILED
    assert "no longer available" in out.result.error


def test_pending_excludes_expired_and_resolved(reg):
    t = [0.0]
    b = box(reg, ttl=60.0, clock=lambda: t[0])
    a = b.invoke("notes.append", {"text": "a"})
    b.invoke("notes.append", {"text": "b"})
    b.confirm(a.id)
    assert len(b.proposals.pending()) == 1
    t[0] = 61.0
    assert b.proposals.pending() == []
