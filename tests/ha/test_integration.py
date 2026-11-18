"""The integration end to end in a real Home Assistant core, against the fake processor."""

from __future__ import annotations

import time

import pytest
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.crestron_controller import (
    ISSUE_IPID_MISSING,
    ISSUE_UNREACHABLE,
    evaluate_health,
)
from custom_components.crestron_controller.cipcore import client as cip
from custom_components.crestron_controller.config_flow import parse_ipid
from custom_components.crestron_controller.const import (
    CONF_ALLOW_WRITES,
    CONF_IPID,
    CONF_JOIN_MAP,
    DOMAIN,
    UNREACHABLE_REPAIR_SECONDS,
)
from custom_components.crestron_controller.diagnostics import async_get_config_entry_diagnostics
from tests.conftest import wait_for

JOIN_MAP = """\
version: 1
timing: {sync_quiet_seconds: 0.2, entry_min_seconds: 0.1, entry_timeout: 1.0,
         repoll_timeout: 0.5, bringup_retry_seconds: 0.2}
never_write:
  digital: ["200-219"]
entities:
  - {type: light, name: Hall Pendants, feedback: 121}
  - {type: light, name: Den Lamp, feedback: 122, brightness: {join: 11}}
  - {type: switch, name: Fountain, press: momentary, on_join: 50, off_join: 51}
  - {type: binary_sensor, name: Gate Open, join: 205, device_class: opening}
  - {type: button, name: All Off, join: 60}
  - {type: sensor, name: Level, analog: 11, scale: percent}
  - {type: sensor, name: Now Playing, serial: 5}
  - {type: number, name: Volume, analog: 12, writable: true, scale: percent}
"""


def add_entry(hass, config_dir, processor, *, writes=True, join_map=JOIN_MAP):
    (config_dir / "crestron_controller").mkdir(exist_ok=True)
    (config_dir / "crestron_controller" / "house.yaml").write_text(join_map)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="House",
        unique_id="127.0.0.1:2a",
        data={
            CONF_NAME: "House",
            CONF_HOST: "127.0.0.1",
            CONF_PORT: processor.port,
            CONF_IPID: 0x2A,
            CONF_JOIN_MAP: "crestron_controller/house.yaml",
        },
        options={CONF_ALLOW_WRITES: writes},
    )
    entry.add_to_hass(hass)
    return entry


def seed(processor):
    processor.digital[None] = {121: 0, 205: 1}
    processor.analog[None] = {11: 32768, 12: 0}
    processor.serial[5] = "Track One"
    processor.toggles[None] = {121: 121}


async def setup(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    hub = entry.runtime_data.hub
    await wait_for(lambda: hub.connected)
    await hass.async_block_till_done()
    return hub


async def test_entities_reflect_the_processor(hass: HomeAssistant, config_dir, processor):
    seed(processor)
    entry = add_entry(hass, config_dir, processor)
    hub = await setup(hass, entry)
    try:
        assert hass.states.get("binary_sensor.house_link").state == "on"
        assert hass.states.get("light.house_hall_pendants").state == "off"
        assert hass.states.get("light.house_den_lamp").attributes["level"] == 128
        assert hass.states.get("binary_sensor.house_gate_open").state == "on"
        assert hass.states.get("sensor.house_level").state == "50.0"
        assert hass.states.get("sensor.house_now_playing").state == "Track One"
        assert hass.states.get("switch.house_fountain").attributes.get("assumed_state")
    finally:
        await hass.config_entries.async_unload(entry.entry_id)
    assert not hub.client.connected


async def test_services_drive_the_processor(hass: HomeAssistant, config_dir, processor):
    seed(processor)
    entry = add_entry(hass, config_dir, processor)
    await setup(hass, entry)
    try:
        await hass.services.async_call(
            "light", "turn_on", {"entity_id": "light.house_hall_pendants"}, blocking=True
        )
        await hass.async_block_till_done()
        assert processor.presses == [121]
        assert hass.states.get("light.house_hall_pendants").state == "on"

        await hass.services.async_call(
            "switch", "turn_off", {"entity_id": "switch.house_fountain"}, blocking=True
        )
        assert processor.presses[-1] == 51
        assert hass.states.get("switch.house_fountain").state == "off"

        await hass.services.async_call(
            "button", "press", {"entity_id": "button.house_all_off"}, blocking=True
        )
        assert processor.presses[-1] == 60

        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": "number.house_volume", "value": 50},
            blocking=True,
        )
        await wait_for(lambda: processor.analog_writes == [(12, 32768)])
    finally:
        await hass.config_entries.async_unload(entry.entry_id)


async def test_listen_only_refuses_writes(hass: HomeAssistant, config_dir, processor):
    seed(processor)
    entry = add_entry(hass, config_dir, processor, writes=False)
    await setup(hass, entry)
    try:
        with pytest.raises(HomeAssistantError, match="listen-only"):
            await hass.services.async_call(
                "light",
                "turn_on",
                {"entity_id": "light.house_hall_pendants"},
                blocking=True,
            )
        assert processor.presses == []
    finally:
        await hass.config_entries.async_unload(entry.entry_id)


async def test_a_bad_join_map_is_a_setup_error(hass: HomeAssistant, config_dir, processor):
    entry = add_entry(
        hass, config_dir, processor, join_map="entities:\n  - {type: light, name: X}\n"
    )
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR


async def test_diagnostics_list_every_join(hass: HomeAssistant, config_dir, processor):
    seed(processor)
    entry = add_entry(hass, config_dir, processor)
    await setup(hass, entry)
    try:
        diag = await async_get_config_entry_diagnostics(hass, entry)
        assert diag["joins"]["(no subsystem)"]["digital_high"] == [205]
        assert diag["serial"] == {5: "Track One"}
    finally:
        await hass.config_entries.async_unload(entry.entry_id)


LIST_MAP = (
    JOIN_MAP
    + """\
  - {type: sensor, name: Source Name, serial: 5, smart_object: 3}
  - {type: binary_sensor, name: Source Selected, join: 205, smart_object: 3}
"""
)


async def test_list_entities_read_their_smart_object(hass: HomeAssistant, config_dir, processor):
    seed(processor)
    processor.smart_serial = {3: {5: "Item one"}}
    processor.smart = {None: {3: {205: 0}}}
    entry = add_entry(hass, config_dir, processor, join_map=LIST_MAP)
    await setup(hass, entry)
    try:
        # Same join numbers as Now Playing and Gate Open, different values.
        assert hass.states.get("sensor.house_now_playing").state == "Track One"
        assert hass.states.get("sensor.house_source_name").state == "Item one"
        assert hass.states.get("binary_sensor.house_gate_open").state == "on"
        selected = hass.states.get("binary_sensor.house_source_selected")
        assert selected.state == "off"
        assert selected.attributes["smart_object"] == 3
        await processor.push_smart_digital(None, 3, 205, 1)
        await wait_for(lambda: hass.states.get("binary_sensor.house_source_selected").state == "on")
        diag = await async_get_config_entry_diagnostics(hass, entry)
        assert diag["smart_objects"]["3"]["serial"] == {5: "Item one"}
    finally:
        await hass.config_entries.async_unload(entry.entry_id)


async def test_config_flow_creates_entry_and_starter_map(hass, config_dir, processor):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Main Processor",
            CONF_HOST: "127.0.0.1",
            CONF_IPID: "0x2A",
            CONF_PORT: processor.port,
            CONF_JOIN_MAP: "",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_IPID] == 0x2A
    assert result["options"] == {CONF_ALLOW_WRITES: False}
    assert (config_dir / "crestron_controller" / "main_processor.yaml").exists()
    assert processor.presses == []
    await hass.async_block_till_done()
    for entry in hass.config_entries.async_entries(DOMAIN):
        await hass.config_entries.async_unload(entry.entry_id)


async def test_config_flow_reports_an_undefined_ipid(hass, config_dir, processor):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "X",
            CONF_HOST: "127.0.0.1",
            CONF_IPID: "0x30",
            CONF_PORT: processor.port,
            CONF_JOIN_MAP: "",
        },
    )
    assert result["errors"] == {"base": "ipid_missing"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "X",
            CONF_HOST: "127.0.0.1",
            CONF_IPID: "zz",
            CONF_PORT: processor.port,
            CONF_JOIN_MAP: "",
        },
    )
    assert result["errors"] == {CONF_IPID: "invalid_ipid"}


async def test_options_flow_turns_writes_on(hass, config_dir, processor):
    seed(processor)
    entry = add_entry(hass, config_dir, processor, writes=False)
    await setup(hass, entry)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_ALLOW_WRITES: True}
    )
    await hass.async_block_till_done()
    assert entry.options[CONF_ALLOW_WRITES] is True
    assert entry.runtime_data.hub.writes_enabled
    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(
    ("text", "value"), [("0x2A", 0x2A), ("2a", 0x2A), ("20d", 20), (" 0XfE ", 0xFE)]
)
def test_ipid_parsing(text, value):
    assert parse_ipid(text) == value


@pytest.mark.parametrize("text", ["0x02", "ff", "abc", "300d"])
def test_ipid_parsing_rejects(text):
    with pytest.raises(ValueError):
        parse_ipid(text)


class _Client:
    def __init__(self, kind=None, since=None, displaced=0):
        self.last_error_kind = kind
        self.disconnected_since = since
        self._displaced = displaced

    def recent_displacements(self):
        return self._displaced


class _Hub:
    def __init__(self, connected, client):
        self.connected = connected
        self.client = client


def test_health_rules():
    now = time.monotonic()
    assert evaluate_health(_Hub(True, _Client()), now) == set()
    assert evaluate_health(_Hub(False, _Client(cip.ERROR_IPID_MISSING, now)), now) == {
        ISSUE_IPID_MISSING
    }
    stale = now - UNREACHABLE_REPAIR_SECONDS - 1
    assert evaluate_health(_Hub(False, _Client(cip.ERROR_UNREACHABLE, stale)), now) == {
        ISSUE_UNREACHABLE
    }
    assert evaluate_health(_Hub(True, _Client(displaced=3)), now) == {"displaced"}


async def test_repairs_are_registered_with_translations(hass, config_dir, processor):
    # Exercise the translation keys by creating each issue the way the watcher does.
    for issue in ("unreachable", "ipid_missing", "refused", "displaced"):
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue,
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key=issue,
            translation_placeholders={"name": "n", "host": "h", "ipid": "0x2A", "error": "e"},
        )
    assert len(ir.async_get(hass).issues) == 4


async def test_reconfigure_moves_the_link_to_a_new_address(hass, config_dir, processor):
    seed(processor)
    entry = add_entry(hass, config_dir, processor)
    await setup(hass, entry)
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "localhost", CONF_IPID: "0x2A", CONF_PORT: processor.port},
    )
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.data[CONF_HOST] == "localhost"
    assert entry.unique_id == "localhost:2a"
    await hass.config_entries.async_unload(entry.entry_id)
