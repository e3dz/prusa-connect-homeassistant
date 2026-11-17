"""The models read recorded device records the way the server means them."""

from __future__ import annotations

import pytest

from prusa_connect import Device, DeviceStates, ToolTree, parse_tool_id
from prusa_connect.models import Event

from .conftest import load

RECORDS = [
    "device_coreone.json",
    "device_mk4s_mmu.json",
    "device_xl.json",
    "device_xl_disabled_head.json",
    "device_klipper.json",
]


@pytest.mark.parametrize("name", RECORDS)
def test_state_tree_and_record_agree(name: str) -> None:
    """The tree read from flat paths equals the typed tools member."""
    raw = load(name)
    from_state = ToolTree.from_state(raw["state"])
    from_api = ToolTree.from_api(raw["tools"])
    assert from_state.tool_count == from_api.tool_count
    assert set(from_state.tools) == set(from_api.tools)
    for tool_id, tool in from_api.tools.items():
        other = from_state.tools[tool_id]
        assert other.enabled == tool.enabled
        assert other.active == tool.active
        assert other.material == tool.material
        assert other.nozzle_temp == tool.nozzle_temp
        assert (other.feeder is None) == (tool.feeder is None)


def test_single_head() -> None:
    device = Device.from_dict(load("device_coreone.json"))
    tree = device.tools
    assert [t.id for t in tree.heads] == ["0"]
    head = tree.tools["0"]
    assert head.active is True
    assert head.material == "PLA"
    assert head.nozzle_diameter == 0.4
    assert head.feeder is None
    assert tree.active_head is head
    assert device.printer_state == "PRINTING"
    assert device.job_progress == 3
    assert device.job_time_remaining == 831
    assert device.job_name == "tangle.bgcode"
    assert device.build_volume is not None
    assert device.build_volume.x_mm == 250
    assert device.bed_temp == 60


def test_mmu_slots() -> None:
    tree = Device.from_dict(load("device_mk4s_mmu.json")).tools
    head = tree.tools["0"]
    assert head.feeder is not None
    assert head.feeder.slot_count == 5
    assert head.feeder.type == "MMU"
    assert head.feeder.mmu_progress_code == 0
    assert head.nozzle_target_temp == 0
    slots = tree.slots(0)
    assert [s.id for s in slots] == ["0.0", "0.1", "0.2", "0.3", "0.4"]
    assert slots[0].active is True
    assert slots[1].material == "PETG"
    assert slots[4].material == ""


def test_xl_disabled_head() -> None:
    tree = Device.from_dict(load("device_xl_disabled_head.json")).tools
    assert [t.id for t in tree.heads] == ["0", "1", "2", "3", "4"]
    assert tree.tools["2"].enabled is False
    assert tree.tools["2"].nozzle_temp is None
    assert tree.tools["1"].nozzle_high_flow is True
    assert tree.tools["1"].nozzle_target_temp is None
    assert tree.tool_count == 5


def test_klipper_has_no_features() -> None:
    device = Device.from_dict(load("device_klipper.json"))
    head = device.tools.tools["0"]
    assert head.nozzle_temp == 25.8
    assert head.nozzle_diameter is None
    assert head.material is None
    assert device.build_volume is None
    assert device.arguments("core.command.set_nozzle_temperature") == ["celsius"]


def test_apply_and_remove() -> None:
    device = Device.from_dict(load("device_coreone.json"))
    device.apply("/tools/0/nozzle_temp", 180.5)
    assert device.tools.tools["0"].nozzle_temp == 180.5
    device.apply("/tools/0/nozzle_temp", None)
    assert device.tools.tools["0"].nozzle_temp is None
    device.apply("/job/path", "/usb/other.bgcode")
    assert device.job_name == "other.bgcode"


def test_active_head_falls_back_to_zero() -> None:
    tree = ToolTree.from_state({"/tools/0/type": "FFF_PRINT_HEAD", "/tools/1/active": False})
    assert tree.active_head is not None
    assert tree.active_head.id == "0"


def test_gcode_tool_map() -> None:
    tree = ToolTree.from_state({"/gcode_tool_map/1": "0.1", "/gcode_tool_map/2": 3})
    assert tree.gcode_tool_map == {"1": "0.1"}


@pytest.mark.parametrize(
    ("tool_id", "expected"),
    [("0", (0, None)), ("0.2", (0, 2)), ("12", (12, None)), ("00", None), ("a", None), ("1.", None)],
)
def test_parse_tool_id(tool_id: str, expected: tuple[int, int | None] | None) -> None:
    assert parse_tool_id(tool_id) == expected


def test_device_states_vocabulary() -> None:
    vocab = DeviceStates.from_dict(
        {
            "items": [
                {
                    "kind": "printer",
                    "namespace": "xbuddy",
                    "states": [
                        {"state": "PRINTING", "display_name": "Printing"},
                        {"state": "PAUSED", "display_name": "Paused"},
                    ],
                    "transitions": [
                        {"from": "PRINTING", "to": "PAUSED", "verb": "core.command.pause_print"},
                        {"from": "PAUSED", "to": "PRINTING"},
                    ],
                }
            ]
        }
    )
    assert vocab.states == {"PRINTING", "PAUSED"}
    assert vocab.verbs_from("PRINTING") == {"core.command.pause_print"}
    assert vocab.verbs_from("PAUSED") == set()
    assert vocab.verbs_from("IDLE") is None
    assert DeviceStates.from_dict(load("device_states.json")).states == set()


def test_event_accessors() -> None:
    event = Event(
        type="x",
        envelope={"subject": "device:abc", "time": "2026-10-24T16:13:05Z", "data": {"path": "/p"}},
    )
    assert event.device_id == "abc"
    assert event.data == {"path": "/p"}
    assert event.time is not None
    other = Event(type="x", envelope={"data": {"device_id": "d"}, "time": "bad"})
    assert other.device_id == "d"
    assert other.time is None
    assert Event(type="x", envelope={"data": []}).data == {}
