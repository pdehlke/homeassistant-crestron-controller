"""The hub's discrete on/off, routing and safety, against the fake processor.

The hub has no Home Assistant imports, so it is tested here directly.
"""

import asyncio

import pytest

from custom_components.crestron_controller.cipcore.client import Timing
from custom_components.crestron_controller.cipcore.joinmap import parse
from custom_components.crestron_controller.hub import Hub, HubError
from tests.conftest import wait_for

FAST = {
    "sync_quiet_seconds": 0.2,
    "entry_min_seconds": 0.1,
    "entry_timeout": 1.0,
    "repoll_timeout": 0.5,
    "bringup_retry_seconds": 0.2,
}


def gated_map(**extra):
    raw = {
        "subsystems": {
            "default": "lights",
            "idle_return_seconds": 0.3,
            "entries": {
                "lights": {"join": 40, "quiet_seconds": 0.1},
                "av": {"join": 41, "quiet_seconds": 0.1},
            },
        },
        "never_write": {"digital": ["200-219"]},
        "timing": FAST,
        "entities": [
            {"type": "light", "name": "Nook", "feedback": 301, "also_reports": [327]},
            {
                "type": "light",
                "name": "Pantry",
                "press": "on_off",
                "feedback": 129,
                "on_join": 127,
                "off_join": 129,
            },
            {"type": "switch", "name": "Pump", "press": "momentary", "on_join": 50},
            {"type": "button", "name": "Menu", "subsystem": "av", "join": 301},
        ],
    }
    raw.update(extra)
    return parse(raw)


def setup_gated(processor):
    processor.entries = {"lights": 40, "av": 41}
    # An entry only counts as landed if its dump carries at least one digital
    # join, so the av subsystem needs one.
    processor.digital = {"lights": {301: 0, 129: 0}, "av": {550: 1}}
    processor.toggles = {"lights": {301: 301, 129: 129}}
    processor.setters = {"lights": {127: (129, 1)}}


async def start(processor, joinmap, writes=True):
    hub = Hub("test", "127.0.0.1", processor.port, 0x2A, joinmap, writes)
    await hub.async_start()
    await wait_for(lambda: hub.connected)
    return hub


def entity(hub, entity_id):
    return next(e for e in hub.joinmap.entities if e.id == entity_id)


async def test_turn_on_presses_once_and_waits_for_feedback(processor):
    setup_gated(processor)
    hub = await start(processor, gated_map())
    try:
        nook = entity(hub, "nook")
        assert hub.is_on(nook) is False
        await hub.async_set(nook, True)
        assert hub.is_on(nook) is True
        assert processor.presses == [40, 301]
        await hub.async_set(nook, True)  # already on: presses nothing
        assert processor.presses == [40, 301]
        await hub.async_set(nook, False)
        assert processor.presses == [40, 301, 301]
    finally:
        await hub.async_stop()


async def test_on_off_entities_press_the_join_for_the_direction(processor):
    setup_gated(processor)
    hub = await start(processor, gated_map())
    try:
        pantry = entity(hub, "pantry")
        await hub.async_set(pantry, True)
        assert processor.presses[-1] == 127
        await hub.async_set(pantry, False)
        assert processor.presses[-1] == 129
        assert hub.is_on(pantry) is False
    finally:
        await hub.async_stop()


async def test_an_alias_moving_moves_the_entity(processor):
    setup_gated(processor)
    hub = await start(processor, gated_map())
    try:
        changes = []
        nook = entity(hub, "nook")
        hub.subscribe(nook.reads(), lambda: changes.append(hub.is_on(nook)))
        await processor.push_digital("lights", 327, 1)
        await wait_for(lambda: hub.is_on(nook) is True)
        assert changes
    finally:
        await hub.async_stop()


async def test_listen_only_refuses_and_reports_lights_unavailable(processor):
    setup_gated(processor)
    hub = Hub("test", "127.0.0.1", processor.port, 0x2A, gated_map(), False)
    await hub.async_start()
    try:
        await wait_for(lambda: hub.connected)
        nook = entity(hub, "nook")
        assert not hub.available(nook)
        with pytest.raises(HubError, match="listen-only"):
            await hub.async_set(nook, True)
        assert processor.presses == []
    finally:
        await hub.async_stop()


async def test_an_unconfirmed_press_retries_after_re_entering_then_fails(processor):
    setup_gated(processor)
    processor.toggles = {"lights": {}}  # presses produce no feedback
    hub = await start(processor, gated_map())
    try:
        import custom_components.crestron_controller.hub as hub_module

        hub_module.CONFIRM_TIMEOUT = 0.3
        with pytest.raises(HubError, match="without the processor confirming"):
            await hub.async_set(entity(hub, "nook"), True)
        # entry, press, re-entry after forgetting the subsystem, press again
        assert processor.presses == [40, 301, 40, 301]
    finally:
        hub_module.CONFIRM_TIMEOUT = 3.0
        await hub.async_stop()


async def test_a_press_in_another_subsystem_enters_it_and_idle_returns(processor):
    setup_gated(processor)
    hub = await start(processor, gated_map())
    try:
        await hub.async_press(entity(hub, "menu"), 301)
        assert processor.presses == [40, 41, 301]
        await wait_for(lambda: hub.client.current_subsystem == "lights", timeout=5)
        assert processor.presses[-1] == 40
    finally:
        await hub.async_stop()


async def test_momentary_presses_without_waiting(processor):
    setup_gated(processor)
    hub = await start(processor, gated_map())
    try:
        pump = entity(hub, "pump")
        assert hub.available(pump)
        await hub.async_press(pump, pump.press_for(True))
        assert processor.presses[-1] == 50
    finally:
        await hub.async_stop()


async def test_concurrent_commands_are_serialised(processor):
    setup_gated(processor)
    hub = await start(processor, gated_map())
    try:
        await asyncio.gather(
            hub.async_set(entity(hub, "nook"), True),
            hub.async_press(entity(hub, "menu"), 301),
            hub.async_set(entity(hub, "pantry"), True),
        )
        # Each command completed its own entry before the next began.
        assert processor.presses[:3] == [40, 301, 41]
        assert hub.is_on(entity(hub, "nook")) and hub.is_on(entity(hub, "pantry"))
    finally:
        await hub.async_stop()


def test_timing_import_is_the_shared_one():
    assert Timing().entry_timeout == 3.0
