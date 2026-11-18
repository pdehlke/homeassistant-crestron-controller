"""EXTENDED_DATA (type 12) frames and frames holding several join records.

Byte sources, frame by frame:

- "recorded": captured from a real processor on the system this project was developed on.
- "rellis": laid out from rellis-erigon/Crestron-CIP-HA's protocol.py, whose comments say a live
  DMPS sent `00 00 00 12 34 ...` (an extended serial) and sent one IP-ID all of its joins as
  EXTENDED_DATA. This project has not seen a processor do that.
- "built": assembled here from the same record layout, to exercise a combination neither source
  recorded.
"""

from cipcore import protocol as p
from cipcore.client import CipClient

from tests.conftest import wait_for
from tests.core.test_client import FAST, GATES, started, writable


def frames(hexes: str) -> tuple[int, bytes]:
    raw = bytes.fromhex(hexes)
    [(ciptype, payload)], rest = p.split_frames(raw)
    assert rest == b""
    return ciptype, payload


# recorded: the processor's feedback for join 24 going high, as one DATA record.
DATA_DIGITAL_24_HIGH = "05 00 06 00 00 03 00 17 00"
# rellis: the header the DMPS used, `00 00 00 12 34`, here carrying "Now playing 12" on serial 3.
EXTENDED_SERIAL = "12 00 16 00 00 00 12 34 00 02 03 4e 6f 77 20 70 6c 61 79 69 6e 67 20 31 32"
# rellis: digital join 24 high and join 25 low as EXTENDED_DATA.
EXTENDED_DIGITALS = "12 00 09 00 00 00 05 00 17 00 18 80"
# rellis: analog join 11 at 0x1234 as EXTENDED_DATA.
EXTENDED_ANALOG = "12 00 09 00 00 00 05 14 00 0a 12 34"
# built: a DATA frame holding a digital record and then an analog record.
DATA_TWO_RECORDS = "05 00 0d 00 00 03 00 17 00 00 05 14 00 0a 12 34"
# built: an EXTENDED_DATA frame holding a digital record and then an extended serial.
EXTENDED_TWO_RECORDS = "12 00 0f 00 00 00 03 00 17 00 00 06 34 00 02 03 48 69"


def test_a_recorded_data_frame_is_one_digital_record():
    assert p.iter_records(*frames(DATA_DIGITAL_24_HIGH)) == [(p.DATA_DIGITAL, b"\x17\x00")]


def test_extended_data_records_are_read_past_the_longer_header():
    ciptype, payload = frames(EXTENDED_SERIAL)
    [(kind, body)] = p.iter_records(ciptype, payload)
    assert kind == p.DATA_SERIAL_EXTENDED
    assert body[3:] == b"Now playing 12"
    assert p.iter_records(*frames(EXTENDED_DIGITALS)) == [(p.DATA_DIGITAL, b"\x17\x00\x18\x80")]
    assert p.iter_records(*frames(EXTENDED_ANALOG)) == [(p.DATA_ANALOG, b"\x00\x0a\x12\x34")]


def test_every_record_in_a_frame_is_returned():
    assert p.iter_records(*frames(DATA_TWO_RECORDS)) == [
        (p.DATA_DIGITAL, b"\x17\x00"),
        (p.DATA_ANALOG, b"\x00\x0a\x12\x34"),
    ]
    assert p.iter_records(*frames(EXTENDED_TWO_RECORDS)) == [
        (p.DATA_DIGITAL, b"\x17\x00"),
        (p.DATA_SERIAL_EXTENDED, b"\x00\x02\x03Hi"),
    ]


def test_a_frame_whose_lengths_do_not_add_up_is_read_as_one_record():
    # built: the length claims nine bytes and three follow. Read the way the
    # client always has, so nothing that decoded before stops decoding.
    assert p.iter_records(p.TYPE_DATA, bytes.fromhex("00 00 09 00 17 00")) == [
        (p.DATA_DIGITAL, b"\x17\x00")
    ]
    assert p.iter_records(p.TYPE_DATA, b"\x00\x00") == []


def test_our_own_serial_write_parses_as_an_extended_serial_record():
    ciptype, payload = p.split_frames(p.serial_packet(3, "Hi"))[0][0]
    assert p.iter_records(ciptype, payload) == [(p.DATA_SERIAL_EXTENDED, b"\x00\x02\x03Hi")]


class ExtendedDigitals:
    """Counts received EXTENDED_DATA frames holding a digital record, so a test
    can prove the fake really sent them rather than falling back to DATA."""

    def __init__(self) -> None:
        self.count = 0

    def __call__(self, direction: str, ciptype: int, payload: bytes) -> None:
        if direction == "rx" and ciptype == p.TYPE_EXTENDED_DATA:
            kinds = [kind for kind, _ in p.iter_records(ciptype, payload)]
            self.count += p.DATA_DIGITAL in kinds


def client(**kwargs) -> tuple[CipClient, list]:
    seen: list = []
    return CipClient("t", "127.0.0.1", 0x2A, on_join=lambda *a: seen.append(a), **kwargs), seen


async def test_extended_digitals_and_analogs_are_not_published_as_serials():
    cip, seen = client()
    await cip._handle(*frames(EXTENDED_DIGITALS))
    await cip._handle(*frames(EXTENDED_ANALOG))
    await cip._handle(*frames(EXTENDED_SERIAL))
    assert seen == [
        ("digital", 24, 1, None, 0),
        ("digital", 25, 0, None, 0),
        ("analog", 11, 0x1234, None, 0),
        ("serial", 3, "Now playing 12", None, 0),
    ]
    assert cip.serial == {3: "Now playing 12"}


async def test_every_record_in_a_frame_is_applied():
    cip, seen = client()
    await cip._handle(*frames(DATA_TWO_RECORDS))
    await cip._handle(*frames(EXTENDED_TWO_RECORDS))
    assert seen == [
        ("digital", 24, 1, None, 0),
        ("analog", 11, 0x1234, None, 0),
        ("serial", 3, "Hi", None, 0),
    ]


async def test_repeat_digital_and_the_other_serial_records_decode_inside_data():
    cip, seen = client()
    # built: record types 27, 2a and 34 inside ordinary DATA, as rellis's parser accepts.
    await cip._handle(p.TYPE_DATA, bytes.fromhex("00 00 03 27 17 00"))
    await cip._handle(p.TYPE_DATA, bytes.fromhex("00 00 06 2a 00 04 00 4f 6e"))
    await cip._handle(p.TYPE_DATA, bytes.fromhex("00 00 07 34 00 05 03 4f 66 66"))
    assert seen == [
        ("digital", 24, 1, None, 0),
        ("serial", 5, "On", None, 0),
        ("serial", 6, "Off", None, 0),
    ]


async def test_digitals_in_extended_data_during_an_entry_are_collected_not_published():
    cip, seen = client()
    cip._collecting, cip._collecting_for = {}, "lights"
    await cip._handle(*frames(EXTENDED_TWO_RECORDS))
    assert cip._collecting == {(0, 24): 1}
    assert [s for s in seen if s[0] == "digital"] == []
    assert cip.digital_for(None) == {}


async def test_an_entry_dump_sent_as_extended_data_is_filed_under_its_subsystem(processor):
    processor.extended = True
    extended = ExtendedDigitals()
    processor.entries = {"lights": 40, "av": 41}
    processor.digital = {"lights": {301: 1, 341: 1}, "av": {301: 0, 550: 1}}
    processor.omit_on_entry = {"lights": {341}}
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
            on_frame=extended,
        )
    )
    try:
        await wait_for(lambda: cip.synced)
        # 341 was left out of the entry dump; the re-poll, also EXTENDED_DATA, brought it back.
        assert cip.digital_for("lights") == {301: 1, 341: 1}
        assert await cip.async_enter("av")
        assert cip.digital_for("av") == {301: 0, 550: 1}
        assert cip.digital_for("lights")[301] == 1
        assert cip.digital_for(None) == {}
        assert extended.count
    finally:
        await cip.async_stop()


async def test_a_partial_entry_dump_in_extended_data_is_merged(processor):
    processor.extended = True
    extended = ExtendedDigitals()
    processor.entries = {"lights": 40, "av": 41}
    processor.digital = {"lights": {341: 1}, "av": {550: 1}}
    cip = await started(
        CipClient(
            "t",
            "127.0.0.1",
            0x2A,
            port=processor.port,
            subsystems=GATES,
            default_subsystem="lights",
            repoll_after_entry=False,
            policy=writable(40, 41),
            timing=FAST,
            on_frame=extended,
        )
    )
    try:
        await wait_for(lambda: cip.synced)
        assert cip.digital_for("lights")[341] == 1
        await cip.async_enter("av")
        processor.omit_on_entry = {"lights": {341}}
        processor.digital["lights"][342] = 1
        await cip.async_enter("lights")
        assert cip.digital_for("lights") == {341: 1, 342: 1}
        assert extended.count
    finally:
        await cip.async_stop()


def serial_body(join: int, fmt: int, data: bytes) -> bytes:
    return bytes([(join - 1) >> 8, (join - 1) & 0xFF, fmt]) + data


def test_format_bit_04_marks_utf16_text():
    # built: the format-byte meaning is rellis's; no processor has been seen sending it here.
    text = "Grüße こんにちは"
    assert p.decode_serial(serial_body(7, 0x04, text.encode("utf-16-be"))) == (7, text)


def test_text_without_bit_04_stays_latin1():
    # 03 is the format byte our own serial writes send; neither of its bits means UTF-16.
    assert p.decode_serial(serial_body(7, 0x03, "Café".encode("latin-1"))) == (7, "Café")
    assert p.decode_serial(serial_body(7, 0x00, b"Hi")) == (7, "Hi")


def test_truncated_utf16_text_does_not_raise():
    join, text = p.decode_serial(serial_body(7, 0x04, "Hi".encode("utf-16-be")[:-1]))
    assert join == 7
    assert text == "H\ufffd"


async def test_utf16_serials_are_published_decoded_from_any_serial_record_type():
    cip, seen = client()
    text = "こんにちは"
    data = text.encode("utf-16-be")
    record = bytes([p.DATA_SERIAL_EXTENDED]) + serial_body(3, 0x04, data)
    await cip._handle(p.TYPE_EXTENDED_DATA, bytes([0, 0, 0, len(record)]) + record)
    record = bytes([p.DATA_SERIAL]) + serial_body(4, 0x04, data)
    await cip._handle(p.TYPE_DATA, bytes([0, 0, len(record)]) + record)
    assert seen == [("serial", 3, text, None, 0), ("serial", 4, text, None, 0)]
