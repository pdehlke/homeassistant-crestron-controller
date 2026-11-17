"""Wire encodings, checked against frames recorded from real processors where possible."""

import pytest
from cipcore import protocol as p


def test_digital_press_and_release_match_recorded_frames():
    # Recorded on real hardware: pressing join 24 and releasing it.
    assert p.digital_packet(24, True).hex(" ") == "05 00 06 00 00 03 00 17 00"
    assert p.digital_packet(24, False).hex(" ") == "05 00 06 00 00 03 00 17 80"


def test_digital_high_join_numbers_use_the_second_byte():
    # Join 300 is 0x12B on the wire after the -1.
    assert p.digital_packet(300, True)[-2:] == bytes([0x2B, 0x01])
    assert p.decode_digitals(bytes([0x2B, 0x01])) == [(300, 1)]
    assert p.decode_digitals(bytes([0x2B, 0x81])) == [(300, 0)]


def test_one_frame_can_carry_several_digitals():
    body = bytes([0x64, 0x00, 0x65, 0x80, 0x66, 0x00])
    assert p.decode_digitals(body) == [(101, 1), (102, 0), (103, 1)]


def test_registration_packet_carries_the_ipid():
    assert p.registration(0x14).hex(" ") == "01 00 0b 00 00 00 00 00 14 40 ff ff f1 01"
    with pytest.raises(ValueError):
        p.registration(0x02)
    with pytest.raises(ValueError):
        p.registration(0xFF)


def test_analog_and_serial_writes_match_the_reference_client():
    # Byte layouts taken from klenae/python-cipclient. Not yet observed
    # working against a live processor; see docs/protocol/cip-wire-format.md.
    assert p.analog_packet(11, 0x1234).hex(" ") == "05 00 08 00 00 05 14 00 0a 12 34"
    assert p.serial_packet(3, "Hi").hex(" ") == "12 00 0a 00 00 00 06 34 00 02 03 48 69"


def test_analog_decode_reads_four_bytes_per_join():
    assert p.decode_analogs(bytes([0x00, 0x0A, 0xFF, 0xFF, 0x00, 0x15, 0x00, 0x10])) == [
        (11, 65535),
        (22, 16),
    ]


def test_split_frames_keeps_a_partial_frame_for_the_next_read():
    whole = p.HEARTBEAT + p.UPDATE_REQUEST
    frames, rest = p.split_frames(whole + b"\x05\x00")
    assert frames == [(0x0D, b"\x00\x00"), (0x05, b"\x00\x00\x02\x03\x00")]
    assert rest == b"\x05\x00"


@pytest.mark.parametrize("join", [0, 0x8001])
def test_out_of_range_joins_are_refused(join):
    with pytest.raises(ValueError):
        p.digital_packet(join, True)
