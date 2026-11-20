"""Tests for the x52 Environment.xml parser, the draft join map, and `panel fetch`.

The fixture is synthetic: it copies the element and attribute names of a real
x52 project file, its UTF-16 encoding with a byte-order mark, and its padded
tail, with invented pages, labels and join numbers.
"""

from __future__ import annotations

import argparse
import codecs
import csv
import socket
import zipfile

import pytest
import yaml
from cipcore import joinmap
from cli_fakes import FIXTURES, read_line

from crestron_controller_cli import ctp, draft, panel, x52
from crestron_controller_cli.project import FORMATS_DOC, Control, Project, UnsupportedFormat

FIXTURE = FIXTURES / "environment-x52-synthetic.xml"


@pytest.fixture(scope="module")
def project() -> Project:
    return panel.load_project(FIXTURE)


def by_label(project: Project, label: str) -> list[Control]:
    return [c for c in project.controls if c.label == label]


# ---- decoding --------------------------------------------------------------------


def test_fixture_is_utf16_with_bom_and_a_junk_tail():
    raw = FIXTURE.read_bytes()
    assert raw.startswith(codecs.BOM_UTF16_LE)
    assert not raw.rstrip(b"\x00").endswith("</Crestron>\r\n".encode("utf-16-le"))
    assert len(raw) < 50_000


def test_decode_trims_everything_after_the_root():
    text = x52.decode_project(FIXTURE.read_bytes())
    assert text.startswith("<Crestron>") and text.endswith("</Crestron>")


def test_decode_utf8_with_bom_and_declaration():
    raw = codecs.BOM_UTF8 + b'<?xml version="1.0" encoding="UTF-16"?>\n<Crestron></Crestron>\0\0'
    assert x52.decode_project(raw) == "<Crestron></Crestron>"


def test_decode_utf16_without_bom():
    raw = "<Crestron></Crestron>".encode("utf-16-le") + b"\0" * 5
    assert x52.decode_project(raw) == "<Crestron></Crestron>"


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (b"<!DOCTYPE html><html><body></body></html>", "HTML"),
        (b"\x89PNG\r\n\x1a\n binary", "not look like XML"),
        (b"<Crestron><Properties>", "never closed"),
        (b'<!DOCTYPE x [<!ENTITY a "b">]><Crestron></Crestron>', "DTD"),
    ],
)
def test_unsupported_inputs_are_refused(raw, message):
    with pytest.raises(UnsupportedFormat, match=message):
        x52.decode_project(raw)


def test_unsupported_formats_point_at_the_docs():
    with pytest.raises(UnsupportedFormat) as info:
        x52.decode_project(b"\x89PNG\r\n\x1a\n binary")
    assert FORMATS_DOC in str(info.value)


def test_a_zip_that_is_not_a_ch5z_is_refused_with_the_docs(tmp_path):
    path = tmp_path / "project.vtz"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Environment.xml", "<Crestron></Crestron>")
    with pytest.raises(UnsupportedFormat, match="not a .ch5z project") as info:
        panel.load_project(path)
    assert FORMATS_DOC in str(info.value)


def test_other_xml_is_refused():
    with pytest.raises(UnsupportedFormat, match="not a Crestron"):
        x52.parse_project("<project><page/></project>")
    with pytest.raises(UnsupportedFormat, match="Pages"):
        x52.parse_project(
            "<Crestron><TargetControl>Project</TargetControl><Properties/></Crestron>"
        )


# ---- parsing ---------------------------------------------------------------------


def test_project_metadata(project):
    assert project.panel_type == "TSW-752"
    assert project.home_page == "Home"
    assert project.pages == ["Home", "Lights", "Audio", "Security"]


def test_buttons_labels_and_feedback(project):
    (pendants,) = by_label(project, "Kitchen Pendants")
    assert (pendants.page, pendants.press, pendants.feedback) == ("Lights", 301, 301)
    (vol_up,) = by_label(project, "Volume Up")
    assert vol_up.press == 231 and vol_up.feedback is None  # ShowSelectFeedback false


def test_advanced_button_label_is_unescaped(project):
    (pool,) = by_label(project, "Pool & Spa")
    assert pool.press == 303


def test_indirect_text_becomes_a_serial_join(project):
    assert by_label(project, "Room Name")[0].serial == 17
    assert by_label(project, "Now Playing")[0].serial == 26
    assert by_label(project, "Status")[0].serial == 33  # IndirectTextJoin


def test_analog_feedback(project):
    (gauge,) = [c for c in project.controls if c.control == "Liquid_Gauge"]
    assert gauge.analog == 5


def test_dpad_directions_are_separate_rows(project):
    rows = [c for c in project.controls if c.control == "_DPad2"]
    assert [(c.label.split()[-1], c.press) for c in rows] == [
        ("Up", 201),
        ("Down", 202),
        ("Left", 203),
        ("Right", 204),
        ("OK", 205),
    ]


def test_subpage_reference_offsets_are_applied(project):
    (scene_a,) = by_label(project, "Scene A")
    assert scene_a.press == 110  # 10 on the subpage, +100 from the reference
    assert scene_a.path == "Lights > Scene Row"
    assert scene_a.offset_note == "d+100"


def test_shared_subpage_appears_under_each_page(project):
    banners = by_label(project, "Home")
    banner_rows = [c for c in banners if c.control == "Simple_Button"]
    assert {c.page for c in banner_rows} == {"Home", "Lights"}
    assert all(c.page_flip == "Home" for c in banner_rows)
    assert ("DigitalVisibilityJoin", 57) in banner_rows[0].other


def test_navigation_and_page_joins(project):
    (lights,) = [c for c in by_label(project, "Lights") if c.control == "Simple_Button"]
    assert lights.page_flip == "Lights" and lights.press == 21
    pages = [c for c in project.controls if c.control == "Page"]
    assert ("DigitalJoin (page flip)", 1102) in pages[1].other


def test_unplaced_subpage_and_hardkeys(project):
    (spare,) = by_label(project, "Spare")
    assert spare.page == "(unplaced) Spare Popup"
    keys = [c for c in project.controls if c.control == "Hardkey"]
    assert {(c.page, c.press) for c in keys} == {("(project)", 7), ("Home", 21)}


# ---- outputs ---------------------------------------------------------------------


def test_inventory_csv(project):
    lines = draft.inventory_csv(project).splitlines()
    assert lines[0].split(",") == list(draft.CSV_FIELDS)
    assert any("Kitchen Pendants,301,301" in line for line in lines)
    rows = list(csv.DictReader(lines))
    assert any(row["offsets_applied"] == "d+100" for row in rows)
    assert all(row["smart_object"] == "" for row in rows)  # x52 projects have none


def test_draft_passes_join_map_validation_and_writes_nothing(project):
    text = draft.draft_join_map(project, source="fixture.xml")
    jm = joinmap.parse(yaml.safe_load(text))
    assert {e.type for e in jm.entities} == {"binary_sensor", "sensor"}
    assert all(not e.writes() for e in jm.entities)
    assert not jm.subsystems


def test_draft_lists_a_shared_join_once(project):
    text = draft.draft_join_map(project)
    jm = joinmap.parse(yaml.safe_load(text))
    porch = [e for e in jm.entities if e.join == 302]
    assert len(porch) == 1 and porch[0].name == "Porch"
    assert "also appears as: Porch Light on Security" in text


def test_draft_names_hardkey_joins_after_a_labelled_button(project):
    jm = joinmap.parse(yaml.safe_load(draft.draft_join_map(project)))
    (lights,) = [e for e in jm.entities if e.join == 21]
    assert lights.name == "Lights"


def test_draft_header_and_subsystem_candidates(project):
    text = draft.draft_join_map(project)
    assert draft.JOIN_MAP_DOC in text
    assert "#       lights: {join: 21}" in text
    assert "flips the panel to Lights" in text
    assert "#       audio: {join: 22}" in text
    assert "Unlabelled buttons on the home page" in text
    assert "join offset applied (d+100)" in text
    assert "# ---- page: Lights" in text
    assert all(len(line) <= 100 for line in text.splitlines())


def test_draft_handles_awkward_labels():
    # Labels YAML would misread as numbers or booleans, a repeated label on
    # different joins, and an empty label.
    controls = [
        Control("A", "A", "Simple_Button", "B1", "Off", press=11),
        Control("B", "B", "Simple_Button", "B2", "Off", press=12),
        Control("A", "A", "Simple_Button", "B3", "4", press=13),
        Control("A", "A", "Simple_Button", "B4", "yes", press=14),
        Control("A", "A", "Simple_Button", "B5", "", press=15),
        Control("A", "A", "Simple_Label", "L1", '"Quoted" #hash', serial=3),
    ]
    project = Project("TSW-752", None, ["A", "B"], controls)
    jm = joinmap.parse(yaml.safe_load(draft.draft_join_map(project)))
    ids = [e.id for e in jm.entities]
    assert len(set(ids)) == len(ids)
    names = {e.name for e in jm.entities}
    assert {"Off (A)", "Off (B)", "4", "yes", "B5 d15", '"Quoted" #hash'} <= names


def test_empty_project_drafts_an_empty_map():
    text = draft.draft_join_map(Project(None, None))
    assert joinmap.parse(yaml.safe_load(text)).entities == ()


# ---- the commands ------------------------------------------------------------------


def parse_args(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    panel.register(parser.add_subparsers())
    return parser.parse_args(["panel", *argv])


def test_parse_command_writes_yaml(tmp_path, capsys):
    out = tmp_path / "draft.yaml"
    args = parse_args("parse", str(FIXTURE), "-o", str(out))
    assert args.func(args) == 0
    joinmap.parse(yaml.safe_load(out.read_text()))
    assert "wrote" in capsys.readouterr().err


def test_parse_command_csv_to_stdout(capsys):
    args = parse_args("parse", str(FIXTURE), "--format", "csv")
    assert args.func(args) == 0
    assert capsys.readouterr().out.startswith("page,path,control")


def test_parse_command_refuses_unsupported(tmp_path, capsys):
    bad = tmp_path / "project.ch5z"
    bad.write_bytes(b"PK\x03\x04whatever")  # a zip signature on a damaged file
    args = parse_args("parse", str(bad))
    assert args.func(args) == 2
    assert FORMATS_DOC in capsys.readouterr().err


def _fetch_args(port: int, out) -> argparse.Namespace:
    args = parse_args("fetch", "127.0.0.1", "-o", str(out))
    args.port = port  # argparse limits --port to 23/41795; the fake listens elsewhere
    return args


def test_fetch_downloads_over_xmodem(fake_server, tmp_path, capsys):
    content = FIXTURE.read_bytes()[:3000]
    blocks = [content[i : i + 1024] for i in range(0, len(content), 1024)]

    def handle(conn: socket.socket) -> None:
        conn.sendall(b"TSW-752>")
        assert read_line(conn) == "XGETFILE \\display\\swf\\Environment.xml"
        conn.sendall(b"Sending file...\r\n")
        assert conn.recv(1) == b"C"
        for num, data in enumerate(blocks, 1):
            payload = data.ljust(1024, bytes([ctp.SUB]))
            crc = ctp.crc16(payload)
            conn.sendall(
                bytes([ctp.STX, num, 0xFF - num]) + payload + bytes([crc >> 8, crc & 0xFF])
            )
            assert conn.recv(1) == bytes([ctp.ACK])
        conn.sendall(bytes([ctp.EOT]))
        assert conn.recv(1) == bytes([ctp.ACK])

    server = fake_server(handle)
    out = tmp_path / "Environment.xml"
    args = _fetch_args(server.port, out)
    assert args.func(args) == 0
    assert out.read_bytes() == content
    err = capsys.readouterr().err
    assert "10-15 minutes" in err and "panel parse" in err


def test_fetch_reports_a_refusal_and_writes_nothing(fake_server, tmp_path, capsys):
    def handle(conn: socket.socket) -> None:
        conn.sendall(b"TSW-752>")
        read_line(conn)
        conn.sendall(b"File(s) \\display\\swf\\Environment.xml Not Found\r\nTSW-752>")

    server = fake_server(handle)
    out = tmp_path / "Environment.xml"
    args = _fetch_args(server.port, out)
    assert args.func(args) == 1
    assert not out.exists()
    assert "Not Found" in capsys.readouterr().err


@pytest.mark.parametrize("brk", ["\x85", " ", " ", "\r", "\n"])
def test_a_crafted_label_cannot_add_entries_to_the_draft(brk):
    # YAML reads \x85, U+2028 and U+2029 as line breaks; a label carrying one
    # must not end a comment early and smuggle in a writable entity.
    evil = f"Lamp{brk}  - type: switch{brk}    name: Gate{brk}    feedback: 9{brk}    press: toggle"
    controls = [
        Control("Home", "Home", "Simple_Button", "B1", evil, press=11),
        Control("Other", "Other", "Simple_Button", "B2", "Lamp", press=11),
        Control("Home", "Home", "Simple_Button", "B3", "Hall", press=12),
    ]
    project = Project("TSW-752", "Home", ["Home", "Other"], controls, unresolved=[evil])
    text = draft.draft_join_map(project)
    jm = joinmap.parse(yaml.safe_load(text))
    assert {e.type for e in jm.entities} == {"binary_sensor"}
    assert all(not e.writes() for e in jm.entities)
    assert len(jm.entities) == 2
    assert all(c not in draft.summary(project) for c in ("\x85", " ", " "))


def test_a_long_unresolved_list_is_capped_in_the_draft_and_the_summary():
    unresolved = [f"page: receivestateshow=sig{i} (not in the contract)" for i in range(25)]
    project = Project(None, None, unresolved=unresolved)
    for text in (draft.draft_join_map(project), draft.summary(project)):
        assert "sig19 " in text and "sig20 " not in text
        assert "... and 5 more" in text


def test_reader_caveats_appear_in_the_draft_and_the_summary():
    project = Project(None, None, caveats=["CAVEAT: check every join before trusting it."])
    assert "# CAVEAT: check every join" in draft.draft_join_map(project)
    assert "CAVEAT: check every join" in draft.summary(project)
