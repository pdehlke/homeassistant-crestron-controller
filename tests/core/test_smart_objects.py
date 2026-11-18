"""SmartObject joins: lists on a panel, numbered in a range of their own.

Byte sources, frame by frame:

- "rellis capture": the layout of a frame rellis-erigon/Crestron-CIP-HA captured from a live
  processor (its tests/test_protocol.py), with the text replaced so that nothing from that site
  is repeated here. Lengths are adjusted to the new text; every other byte is as captured.
- "built": assembled here from the same layout, to exercise a combination neither source
  recorded.

No processor has been seen sending SmartObject records to this project.
"""

import pytest
from cipcore import protocol as p
from cipcore.client import CipClient

from custom_components.crestron_controller.cipcore.joinmap import JoinMapError, parse
from custom_components.crestron_controller.hub import Hub
from tests.conftest import wait_for
from tests.core.test_client import FAST, GATES, started, writable


def smart(obj: int, *items: bytes) -> bytes:
    """A SmartObject record body: the object number, then length-prefixed items."""
    return obj.to_bytes(4, "big") + b"".join(bytes([len(i)]) + i for i in items)


def data(record: bytes) -> bytes:
    """A DATA payload holding one record, type byte first."""
    return bytes([0, len(record) >> 8, len(record) & 0xFF]) + record


def digital(join: int, value: int) -> bytes:
    n = join - 1
    return bytes([p.DATA_DIGITAL, n & 0xFF, ((n >> 8) & 0x7F) | (0 if value else 0x80)])


def serial(join: int, text: str) -> bytes:
    n = join - 1
    return bytes([p.DATA_SERIAL, n >> 8, n & 0xFF, 0x03]) + text.encode("latin-1")


# rellis capture: object 1, serial 31, format 03; the captured text was nine characters.
CAPTURED_LAYOUT = "00 00 13 38 00 00 00 01 0d 15 00 1e 03" + b"Source 01".hex(" ")
# rellis capture: object 1, serial 21; the captured text was three characters.
CAPTURED_LAYOUT_SHORT = "00 00 0d 38 00 00 00 01 07 15 00 14 03" + b"Aux".hex(" ")


def test_captured_smart_object_frames_decode_to_their_object():
    for hexes, join, text in (
        (CAPTURED_LAYOUT, 31, "Source 01"),
        (CAPTURED_LAYOUT_SHORT, 21, "Aux"),
    ):
        [(kind, body)] = p.iter_records(p.TYPE_DATA, bytes.fromhex(hexes))
        assert kind == p.DATA_SMART_OBJECT
        [(obj, inner, record)] = p.smart_object_records(body)
        assert (obj, inner) == (1, p.DATA_SERIAL)
        assert p.decode_serial(record) == (join, text)


def test_one_object_can_carry_several_records_of_any_kind():
    # built
    body = smart(7, digital(5, 1), bytes([p.DATA_ANALOG, 0, 2, 0x12, 0x34]), serial(3, "Hi"))
    assert p.smart_object_records(body) == [
        (7, p.DATA_DIGITAL, b"\x04\x00"),
        (7, p.DATA_ANALOG, b"\x00\x02\x12\x34"),
        (7, p.DATA_SERIAL, b"\x00\x02\x03Hi"),
    ]


def test_a_nested_object_owns_its_own_joins():
    # built: object 7 holding a digital of its own and object 9, which holds another.
    inner = bytes([p.DATA_SMART_OBJECT]) + smart(9, digital(2, 1))
    assert p.smart_object_records(smart(7, digital(1, 1), inner)) == [
        (7, p.DATA_DIGITAL, b"\x00\x00"),
        (9, p.DATA_DIGITAL, b"\x01\x00"),
    ]


def test_malformed_objects_stop_cleanly():
    assert p.smart_object_records(b"\x00\x00\x01") == []
    # built: an item claiming more bytes than follow ends the walk after the good one.
    body = smart(7, digital(1, 1)) + bytes([9, p.DATA_DIGITAL, 0])
    assert p.smart_object_records(body) == [(7, p.DATA_DIGITAL, b"\x00\x00")]
    # built: nesting far past the cap returns what it can rather than recursing forever.
    body = smart(1, digital(1, 1))
    for obj in range(2, 12):
        body = smart(obj, bytes([p.DATA_SMART_OBJECT]) + body)
    assert p.smart_object_records(body) == []


def client(**kwargs) -> tuple[CipClient, list]:
    seen: list = []
    return CipClient("t", "127.0.0.1", 0x2A, on_join=lambda *a: seen.append(a), **kwargs), seen


async def test_an_object_join_never_lands_in_the_programs_range():
    cip, seen = client()
    await cip._handle(p.TYPE_DATA, data(serial(31, "Program text")))
    await cip._handle(
        p.TYPE_DATA, data(bytes([p.DATA_SMART_OBJECT]) + smart(3, serial(31, "Item")))
    )
    await cip._handle(p.TYPE_DATA, data(bytes([p.DATA_SMART_OBJECT]) + smart(3, digital(31, 1))))
    assert cip.serial == {31: "Program text"}
    assert cip.serial_for(3) == {31: "Item"}
    assert cip.digital_for(None) == {}
    assert cip.digital_for(None, 3) == {31: 1}
    assert cip.smart_objects() == [3]
    assert seen == [
        ("serial", 31, "Program text", None, 0),
        ("serial", 31, "Item", None, 3),
        ("digital", 31, 1, None, 3),
    ]


async def test_smart_objects_arrive_in_extended_data_too():
    cip, seen = client()
    # built: the record inside an EXTENDED_DATA header.
    record = bytes([p.DATA_SMART_OBJECT]) + smart(4, digital(8, 1))
    await cip._handle(p.TYPE_EXTENDED_DATA, bytes([0, 0, 0, len(record)]) + record)
    assert seen == [("digital", 8, 1, None, 4)]


async def test_object_zero_and_non_join_records_inside_an_object_are_skipped():
    cip, seen = client()
    await cip._handle(p.TYPE_DATA, data(bytes([p.DATA_SMART_OBJECT]) + smart(0, digital(1, 1))))
    # An end-of-query marker inside an object must not be taken for the real
    # one: that would acknowledge and start bring-up. With no connection, any
    # send would raise here.
    marker = bytes([p.DATA_UPDATE, p.END_OF_QUERY])
    await cip._handle(p.TYPE_DATA, data(bytes([p.DATA_SMART_OBJECT]) + smart(5, marker)))
    assert seen == []
    assert not cip._end_of_query.is_set()


async def test_object_digitals_during_an_entry_are_collected_then_merged():
    cip, seen = client()
    cip._collecting, cip._collecting_for = {}, "lights"
    await cip._handle(p.TYPE_DATA, data(bytes([p.DATA_SMART_OBJECT]) + smart(3, digital(5, 1))))
    await cip._handle(p.TYPE_DATA, data(digital(5, 0)))
    assert cip._collecting == {(3, 5): 1, (0, 5): 0}
    assert seen == []
    collected, cip._collecting = cip._collecting, None
    cip._merge("lights", collected)
    assert cip.digital_for("lights", 3) == {5: 1}
    assert cip.digital_for("lights") == {5: 0}
    assert ("digital", 5, 1, "lights", 3) in seen


async def test_an_entry_dump_carrying_list_joins_is_filed_and_merged(processor):
    processor.entries = {"lights": 40, "av": 41}
    processor.digital = {"lights": {301: 1}, "av": {550: 1}}
    processor.smart = {"lights": {3: {1: 1, 2: 0, 301: 0}}, "av": {3: {1: 0}}}
    processor.omit_smart_on_entry = {"lights": {(3, 2)}}
    cip = await started(
        CipClient(
            "t",
            "127.0.0.1",
            0x2A,
            port=processor.port,
            subsystems=GATES,
            default_subsystem="lights",
            policy=writable(40, 41),
            timing=FAST,
        )
    )
    try:
        await wait_for(lambda: cip.synced)
        # (3, 2) was left out of the entry dump; the re-poll brought it back.
        assert cip.digital_for("lights", 3) == {1: 1, 2: 0, 301: 0}
        # The program's own join 301 is untouched by the list's join 301.
        assert cip.digital_for("lights")[301] == 1
        assert await cip.async_enter("av")
        assert cip.digital_for("av", 3) == {1: 0}
        assert cip.digital_for("lights", 3)[1] == 1  # untouched by the av dump
        # A list join left out of a later entry dump keeps what it said before,
        # even though the processor's value moved: merged, never rebuilt, and
        # the omitted join really was not sent.
        processor.smart["lights"][3][1] = 0
        processor.omit_smart_on_entry = {"lights": {(3, 1)}}
        cip.repoll_after_entry = False
        assert await cip.async_enter("lights")
        assert cip.digital_for("lights", 3)[1] == 1
    finally:
        await cip.async_stop()


async def test_list_serials_arrive_with_the_registration_dump(processor):
    processor.digital[None] = {1: 1}
    processor.serial = {11: "Program text"}
    processor.smart_serial = {3: {11: "Item one", 12: "Item two"}}
    cip = await started(CipClient("t", "127.0.0.1", 0x2A, port=processor.port, timing=FAST))
    try:
        await wait_for(lambda: cip.synced)
        assert cip.serial == {11: "Program text"}
        assert cip.serial_for(3) == {11: "Item one", 12: "Item two"}
    finally:
        await cip.async_stop()


def list_map():
    return parse(
        {
            "timing": {"sync_quiet_seconds": 0.2},
            "entities": [
                {"type": "binary_sensor", "name": "Program 5", "join": 5},
                {"type": "binary_sensor", "name": "List 5", "join": 5, "smart_object": 3},
                {"type": "sensor", "name": "Program text", "serial": 11},
                {"type": "sensor", "name": "List text", "serial": 11, "smart_object": 3},
            ],
        }
    )


async def test_object_and_program_entities_never_update_each_other(processor):
    processor.digital[None] = {1: 1}
    hub = Hub("test", "127.0.0.1", processor.port, 0x2A, list_map(), False)
    await hub.async_start()
    try:
        await wait_for(lambda: hub.connected)
        by_id = {e.id: e for e in hub.joinmap.entities}
        fired: list[str] = []
        for entity_id, item in by_id.items():
            hub.subscribe(
                item.reads(),
                lambda entity_id=entity_id: fired.append(entity_id),
                item.smart_object or 0,
            )
        await processor.push_smart_digital(None, 3, 5, 1)
        await wait_for(lambda: hub.digital(None, 5, 3) == 1)
        assert hub.digital(None, 5) == 0
        assert set(fired) == {"list_5"}
        fired.clear()
        await processor.push_digital(None, 5, 1)
        await wait_for(lambda: "program_5" in fired)
        assert set(fired) == {"program_5"}
        assert hub.serial(11, 3) is None
    finally:
        await hub.async_stop()


@pytest.mark.parametrize(
    ("entity", "message"),
    [
        ({"type": "light", "name": "L", "feedback": 5, "smart_object": 3}, "read-only"),
        ({"type": "button", "name": "B", "join": 5, "smart_object": 3}, "read-only"),
        ({"type": "number", "name": "N", "analog": 5, "smart_object": 3}, "read-only"),
        ({"type": "sensor", "name": "S", "serial": 5, "smart_object": 0}, "outside"),
        ({"type": "sensor", "name": "S", "serial": 5, "smart_object": "3"}, "whole number"),
        ({"type": "sensor", "name": "S", "serial": 5, "smart_object": True}, "whole number"),
    ],
)
def test_the_join_map_accepts_smart_object_only_where_it_reads(entity, message):
    with pytest.raises(JoinMapError, match=message):
        parse({"entities": [entity]})


def test_a_reading_entity_keeps_its_smart_object():
    jm = list_map()
    assert [e.smart_object for e in jm.entities] == [None, 3, None, 3]
    # Nothing that reads a SmartObject adds to what the link may write.
    assert all(not e.writes() for e in jm.entities)
