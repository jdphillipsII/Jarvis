import json
import pytest
from core.policy import Urgency
from daemon.watchers import (parse_rocm_smi, parse_failed_units, check_disk_usage,
                             GPU_WARN_C, GPU_CRIT_C)


def smi(temp=None, used=None, total=None):
    f = {}
    if temp is not None:  f["Temperature (Sensor edge) (C)"] = str(temp)
    if used is not None:  f["VRAM Total Used Memory (B)"] = str(used)
    if total is not None: f["VRAM Total Memory (B)"] = str(total)
    return json.dumps({"card0": f})


# ---- GPU ----

def test_normal_temperature_is_silent():
    assert parse_rocm_smi(smi(temp=62)) == []


def test_warm_gpu_warns_hot_gpu_is_critical():
    (w,) = parse_rocm_smi(smi(temp=GPU_WARN_C + 1))
    assert w.urgency is Urgency.WARN and "warm" in w.text
    (c,) = parse_rocm_smi(smi(temp=GPU_CRIT_C + 1))
    assert c.urgency is Urgency.CRITICAL


def test_cooldown_key_is_stable_as_the_temperature_drifts():
    """If the key embedded the reading, every tick would look like a new alert
    and the cooldown would never bite."""
    k1 = parse_rocm_smi(smi(temp=86))[0].key
    k2 = parse_rocm_smi(smi(temp=88))[0].key
    assert k1 == k2


def test_vram_pressure_warns():
    (o,) = parse_rocm_smi(smi(used=23_000_000_000, total=24_000_000_000))
    assert o.urgency is Urgency.WARN and "VRAM" in o.text


def test_half_full_vram_is_silent():
    assert parse_rocm_smi(smi(used=12_000_000_000, total=24_000_000_000)) == []


@pytest.mark.parametrize("junk", ["", "not json", "[]", "null", '{"card0": "oops"}'])
def test_unparseable_output_never_raises(junk):
    assert parse_rocm_smi(junk) == []


def test_missing_fields_are_skipped_not_guessed():
    assert parse_rocm_smi(smi(used=1, total=None)) == []


# ---- systemd ----

def test_no_failed_units_is_silent():
    assert parse_failed_units("") == []


def test_one_failed_unit_is_named():
    (o,) = parse_failed_units("sshd.service loaded failed failed OpenSSH\n")
    assert "sshd.service" in o.text and o.urgency is Urgency.WARN


def test_several_failures_are_counted():
    (o,) = parse_failed_units("a.service x\nb.service y\nc.timer z\n")
    assert "3 units" in o.text and len(o.detail["units"]) == 3


def test_key_is_order_independent():
    a = parse_failed_units("b.service x\na.service y\n")[0].key
    b = parse_failed_units("a.service y\nb.service x\n")[0].key
    assert a == b


# ---- disk ----

def test_roomy_disk_is_silent():
    assert check_disk_usage(_usage=(1000, 100, 900)) == []


def test_tight_disk_warns_and_full_disk_is_critical():
    (w,) = check_disk_usage(_usage=(1000, 920, 80))
    assert w.urgency is Urgency.WARN
    (c,) = check_disk_usage(_usage=(1000, 970, 30))
    assert c.urgency is Urgency.CRITICAL
