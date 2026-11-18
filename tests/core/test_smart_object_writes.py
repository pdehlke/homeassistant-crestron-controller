"""Writing into SmartObjects: the encoding, the policy keyed by object, and choosing from a list.

The encoding follows rellis-erigon/Crestron-CIP-HA's pack_smart_object(). Neither that project nor
this one has seen a processor accept it, so the expected bytes below are worked out by hand from
that layout ("built"), not recorded.
"""

import asyncio

import pytest

# One import path throughout: the join map builds its policy from this
# package, and a WriteRefused from the top-level `cipcore` copy is another class.
from custom_components.crestron_controller.cipcore import protocol as p
from custom_components.crestron_controller.cipcore.client import CipClient
from custom_components.crestron_controller.cipcore.joinmap import JoinMapError, parse
from custom_components.crestron_controller.cipcore.policy import (
    ANALOG,
    DIGITAL,
    WritePolicy,
    WriteRefused,
)
from custom_components.crestron_controller.hub import Hub, HubError
from tests.conftest import wait_for
from tests.core.test_client import FAST

# ---- encoding ------------------------------------------------------------------------------


def test_a_smart_object_press_matches_the_documented_layout():
    # built: join 4011 is 0x0FAA on the wire; object 7; one 3-byte digital item.
    assert p.smart_digital_packet(7, 4011, True).hex(" ") == (
        "05 00 0c 00 00 09 38 00 00 00 07 03 00 aa 0f"
    )
    assert p.smart_digital_packet(7, 4011, False).hex(" ").endswith("00 aa 8f")


def test_any_record_wraps_and_reads_back_as_the_same_join():
    analog = bytes([p.DATA_ANALOG, 0, 10, 0x9C, 0x40])
    serial = bytes([p.DATA_SERIAL, 0, 11, 0x03]) + b"Zone"
    for record in (analog, serial):
        [(ciptype, payload)], _ = p.split_frames(p.smart_object_packet(9, record))
        [(kind, body)] = p.iter_records(ciptype, payload)
        assert kind == p.DATA_SMART_OBJECT
        assert p.smart_object_records(body) == [(9, record[0], record[1:])]


@pytest.mark.parametrize(
    ("obj", "record"),
    [(0, b"\x00\x00\x00"), (0x1_0000_0000, b"\x00\x00\x00"), (3, b""), (3, bytes(256))],
)
def test_impossible_smart_object_packets_are_refused(obj, record):
    with pytest.raises(ValueError):
        p.smart_object_packet(obj, record)


def test_a_smart_object_press_checks_its_join_number():
    with pytest.raises(ValueError):
        p.smart_digital_packet(3, 0, True)


# ---- policy ----------------------------------------------------------------------------------


def policy(enabled=True):
    return WritePolicy(
        enabled=enabled,
        allow={DIGITAL: frozenset({5})},
        deny={DIGITAL: frozenset({9})},
        object_allow={3: {DIGITAL: frozenset({9, 6})}},
        object_deny={3: {DIGITAL: frozenset({6, 5})}},
    )


def test_an_objects_lists_are_its_own():
    pol = policy()
    pol.check(DIGITAL, 5)
    pol.check(DIGITAL, 9, 3)  # denied in the program's range, allowed in object 3
    with pytest.raises(WriteRefused, match="never-write"):
        pol.check(DIGITAL, 5, 3)  # allowed in the program's range, denied in object 3
    with pytest.raises(WriteRefused, match="not mapped"):
        pol.check(DIGITAL, 9, 4)  # no lists at all for object 4
    with pytest.raises(WriteRefused, match="SmartObject 3"):
        pol.check(ANALOG, 9, 3)


def test_object_deny_wins_and_listen_only_refuses_objects():
    with pytest.raises(WriteRefused, match="never-write"):
        policy().check(DIGITAL, 6, 3)
    with pytest.raises(WriteRefused, match="listen-only"):
        policy(enabled=False).check(DIGITAL, 9, 3)
    assert policy().conflicts() == [(DIGITAL, 6, 3)]


# ---- join map ------------------------------------------------------------------------------


def source_map(**never_write):
    return parse(
        {
            "timing": {"sync_quiet_seconds": 0.2},
            "never_write": never_write,
            "entities": [
                {
                    "type": "select",
                    "name": "Den source",
                    "smart_object": 3,
                    "options": [
                        {"name": "Radio", "press": 1},
                        {"press": 2, "feedback": 12, "name_serial": 22},
                        {"name": "Spare", "press": 4},
                    ],
                },
                {"type": "button", "name": "Next page", "join": 30, "smart_object": 3},
                {"type": "button", "name": "Program 1", "join": 1},
            ],
        }
    )


def test_select_options_default_their_feedback_to_the_press_join():
    select = source_map().entities[0]
    assert [(o.press, o.feedback, o.name, o.name_serial) for o in select.options] == [
        (1, 1, "Radio", None),
        (2, 12, None, 22),
        (4, 4, "Spare", None),
    ]
    assert select.writes() == [(DIGITAL, 1), (DIGITAL, 2), (DIGITAL, 4)]
    assert (DIGITAL, 12) in select.reads()
    assert ("serial", 22) in select.reads()


def test_the_derived_policy_keeps_object_writes_in_their_object():
    pol = source_map().policy(True)
    assert pol.allow[DIGITAL] == frozenset({1})
    assert pol.object_allow[3][DIGITAL] == frozenset({1, 2, 4, 30})
    assert not source_map().policy(False).permits(DIGITAL, 1, 3)


def test_never_write_names_object_joins():
    jm = parse({"never_write": {"smart_objects": {3: {"digital": [7, "9-10"]}}}})
    assert jm.denied(3)[DIGITAL] == frozenset({7, 9, 10})
    assert jm.denied()[DIGITAL] == frozenset()
    # The wire check enforces them too, on its own, not only the map's validation.
    with pytest.raises(WriteRefused, match="never-write"):
        jm.policy(True).check(DIGITAL, 9, 3)
    with pytest.raises(JoinMapError, match="in SmartObject 3, which is on the never-write"):
        source_map(smart_objects={3: {"digital": [4]}})
    # The program's own join 4 being denied says nothing about object 3's join 4.
    source_map(digital=[4])


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"smart_objects": {0: {"digital": [1]}}}, "SmartObject number"),
        ({"smart_objects": {"3": {"digital": [1]}}}, "SmartObject number"),
        ({"smart_objects": {3: [1]}}, "must be a mapping"),
        ({"smart_objects": {3: {"digitals": [1]}}}, "unknown key"),
        ({"smart_objects": [3]}, "must map SmartObject numbers"),
    ],
)
def test_bad_object_never_write_lists_are_refused(raw, message):
    with pytest.raises(JoinMapError, match=message):
        parse({"never_write": raw})


@pytest.mark.parametrize(
    ("options", "message"),
    [
        (None, "needs a list of options"),
        ([], "needs a list of options"),
        ([{"name": "A"}], "needs a press join"),
        ([{"press": 1}], "needs a name, a name_serial, or both"),
        ([{"press": 1, "name": "A", "colour": "red"}], "unknown key"),
        ([{"press": 1, "name": "A"}, {"press": 1, "name": "B", "feedback": 2}], "share a press"),
        ([{"press": 1, "name": "A"}, {"press": 2, "name": "B", "feedback": 1}], "share a feedback"),
        ([{"press": 1, "name": "A"}, {"press": 2, "name": "A"}], "share a name"),
        ([{"press": 1, "name": ""}], "name must be text"),
        ([{"press": 0, "name": "A"}], "outside"),
    ],
)
def test_bad_select_options_are_refused(options, message):
    entity = {"type": "select", "name": "S"}
    if options is not None:
        entity["options"] = options
    with pytest.raises(JoinMapError, match=message):
        parse({"entities": [entity]})


def test_one_object_join_may_be_written_by_one_entity_only():
    button = {"type": "button", "name": "B", "join": 1, "smart_object": 3}
    select = {
        "type": "select",
        "name": "S",
        "smart_object": 3,
        "options": [{"press": 1, "name": "A"}],
    }
    with pytest.raises(JoinMapError, match="in SmartObject 3, which b also writes"):
        parse({"entities": [button, select]})
    # Different objects, or an object and the program, do not collide.
    parse({"entities": [button, {**select, "smart_object": 4}]})
    parse({"entities": [{**button, "smart_object": None}, select]})


# ---- on the wire ---------------------------------------------------------------------------


def client(processor, **kwargs) -> CipClient:
    return CipClient("t", "127.0.0.1", 0x2A, port=processor.port, timing=FAST, **kwargs)


async def test_an_allowed_object_press_reaches_the_wire_and_is_released(processor):
    processor.digital[None] = {1: 1}
    pol = WritePolicy(enabled=True, object_allow={3: {DIGITAL: frozenset({2})}})
    cip = client(processor, policy=pol)
    await cip.async_start()
    try:
        await wait_for(lambda: cip.synced)
        await cip.async_press(2, None, obj=3)
        await wait_for(lambda: processor.smart_releases == [(3, 2)])
        assert processor.smart_presses == [(3, 2)]
        assert processor.presses == []  # nothing went to the program's join 2
    finally:
        await cip.async_stop()


async def test_object_presses_off_the_allow_list_never_reach_the_wire(processor):
    processor.digital[None] = {1: 1}
    pol = WritePolicy(
        enabled=True,
        allow={DIGITAL: frozenset({2})},
        object_allow={3: {DIGITAL: frozenset({2, 4})}},
        object_deny={3: {DIGITAL: frozenset({4})}},
    )
    cip = client(processor, policy=pol)
    await cip.async_start()
    try:
        await wait_for(lambda: cip.synced)
        with pytest.raises(WriteRefused, match="not mapped"):
            await cip.async_press(2, None, obj=5)
        with pytest.raises(WriteRefused, match="never-write"):
            await cip.async_press(4, None, obj=3)
        await asyncio.sleep(0.2)
        assert processor.smart_presses == []
    finally:
        await cip.async_stop()


async def test_a_listen_only_link_sends_no_object_press(processor):
    processor.digital[None] = {1: 1}
    cip = client(processor, policy=source_map().policy(False))
    await cip.async_start()
    try:
        await wait_for(lambda: cip.synced)
        with pytest.raises(WriteRefused, match="listen-only"):
            await cip.async_press(1, None, obj=3)
        await asyncio.sleep(0.2)
        assert processor.smart_presses == [] and processor.presses == []
    finally:
        await cip.async_stop()


async def test_a_cancelled_object_press_is_still_released(processor):
    processor.digital[None] = {1: 1}
    pol = WritePolicy(enabled=True, object_allow={3: {DIGITAL: frozenset({2})}})
    cip = client(processor, policy=pol)
    await cip.async_start()
    try:
        await wait_for(lambda: cip.synced)
        press = asyncio.create_task(cip.async_press(2, None, hold=5.0, obj=3))
        await wait_for(lambda: processor.smart_presses == [(3, 2)])
        press.cancel()
        with pytest.raises(asyncio.CancelledError):
            await press
        await wait_for(lambda: processor.smart_releases == [(3, 2)])
        assert processor.releases == []
    finally:
        await cip.async_stop()


# ---- the hub -------------------------------------------------------------------------------


async def start_hub(processor, writes=True) -> Hub:
    hub = Hub("test", "127.0.0.1", processor.port, 0x2A, source_map(), writes)
    await hub.async_start()
    await wait_for(lambda: hub.connected)
    return hub


def entity(hub, entity_id):
    return next(e for e in hub.joinmap.entities if e.id == entity_id)


def seed(processor):
    processor.digital[None] = {1: 1}
    processor.smart = {None: {3: {1: 1, 12: 0, 4: 0}}}
    processor.smart_serial = {3: {22: "Streaming"}}
    processor.smart_radio = {3: [1, 2, 4]}


async def test_choosing_an_option_presses_its_join_and_follows_feedback(processor):
    seed(processor)
    # The list reports option 2 on join 12, not on its press join: model that.
    processor.smart_radio = {3: [1, 4]}
    hub = await start_hub(processor)
    try:
        den = entity(hub, "den_source")
        assert hub.option_labels(den) == ["Radio", "Streaming", "Spare"]
        assert hub.selected(den) == den.options[0]
        await hub.async_select(den, den.options[2])
        assert processor.smart_presses == [(3, 4)]
        await wait_for(lambda: hub.selected(den) == den.options[2])
        await processor.push_smart_digital(None, 3, 4, 0)
        await processor.push_smart_digital(None, 3, 12, 1)
        await wait_for(lambda: hub.selected(den) == den.options[1])
        # Already chosen: nothing is pressed.
        await hub.async_select(den, den.options[1])
        assert processor.smart_presses == [(3, 4)]
    finally:
        await hub.async_stop()


async def test_a_select_with_none_or_several_high_reports_no_choice(processor):
    seed(processor)
    processor.smart = {None: {3: {1: 1, 4: 1}}}
    hub = await start_hub(processor)
    try:
        assert hub.selected(entity(hub, "den_source")) is None
    finally:
        await hub.async_stop()


async def test_labels_fall_back_and_never_repeat(processor):
    seed(processor)
    processor.smart_serial = {3: {22: "Radio"}}
    hub = await start_hub(processor)
    try:
        assert hub.option_labels(entity(hub, "den_source")) == ["Radio", "Radio (2)", "Spare"]
    finally:
        await hub.async_stop()
    processor.smart_serial = {}
    hub = await start_hub(processor)
    try:
        # No text seen and no name: the option is called by its place in the list.
        assert hub.option_labels(entity(hub, "den_source"))[1] == "Option 2"
    finally:
        await hub.async_stop()


async def test_a_button_in_a_list_presses_inside_its_object(processor):
    seed(processor)
    hub = await start_hub(processor)
    try:
        await hub.async_press(entity(hub, "next_page"), 30)
        await hub.async_press(entity(hub, "program_1"), 1)
        await wait_for(lambda: processor.releases == [1])
        assert processor.smart_presses == [(3, 30)]
        assert processor.presses == [1]
    finally:
        await hub.async_stop()


async def test_a_listen_only_hub_refuses_to_choose(processor):
    seed(processor)
    hub = await start_hub(processor, writes=False)
    try:
        den = entity(hub, "den_source")
        with pytest.raises(HubError, match="listen-only"):
            await hub.async_select(den, den.options[2])
        assert processor.smart_presses == []
    finally:
        await hub.async_stop()
