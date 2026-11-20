"""Tests for reading x60/x70 HTML5 (.ch5z) panel projects.

Two kinds of fixture. Most tests build a small .ch5z in the test, with invented
pages, labels and joins, laid out like the archives Crestron's tools produce.
Two files under fixtures/ch5/ are public MIT-licensed demo projects, trimmed to
the HTML, contract and config files the reader looks at (see
THIRD_PARTY_NOTICES.md): Construct-Themes-Showcase's LightDark build, which
places joins by number, and CwsDebug's example, which uses a contract and a
SmartObject list. Neither describes a real installation.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import zipfile

import pytest
import yaml
from cipcore import joinmap
from cli_fakes import FIXTURES

from crestron_controller_cli import ch5, panel
from crestron_controller_cli.draft import draft_join_map
from crestron_controller_cli.project import FORMATS_DOC, Control, Project, UnsupportedFormat

LIGHTDARK = FIXTURES / "ch5" / "construct-themes-showcase-lightdark.ch5z"
CWSDEBUG = FIXTURES / "ch5" / "cwsdebug-example.ch5z"


def make_ch5z(files: dict[str, str | bytes], name: str = "demo") -> bytes:
    """A .ch5z holding `files` as its web project, as ch5-cli archive builds one."""
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        for path, data in files.items():
            z.writestr(path, data)
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w") as z:
        z.writestr(f"{name}.ch5", inner.getvalue())
        z.writestr(f"{name}_manifest.json", json.dumps({"projectname": f"{name}.ch5"}))
    return outer.getvalue()


def contract(states: dict | None = None, events: dict | None = None) -> str:
    return json.dumps(
        {
            "name": "Demo",
            "schema_version": 1,
            "signals": {"states": states or {}, "events": events or {}},
        }
    )


def read(files: dict[str, str | bytes]) -> Project:
    return ch5.load_ch5z(make_ch5z(files))


def by_object(project: Project, name: str) -> list[Control]:
    return [c for c in project.controls if c.object_name == name]


def draft(project: Project) -> joinmap.JoinMap:
    return joinmap.parse(yaml.safe_load(draft_join_map(project, source="demo.ch5z")))


# ---- the archive -------------------------------------------------------------------


def test_load_project_reads_a_ch5z_by_its_contents(tmp_path):
    path = tmp_path / "anything.bin"
    path.write_bytes(make_ch5z({"index.html": '<ch5-button sendeventonclick="10">'}))
    project = panel.load_project(path)
    assert project.experimental
    assert [c.press for c in project.controls] == [10]


def test_archive_layout_matches_the_published_archiver():
    # The real sample keeps Crestron's layout: one .ch5 and its manifest.
    names = zipfile.ZipFile(CWSDEBUG).namelist()
    assert sorted(names) == ["CwsDebugExample.ch5", "CwsDebugExample_manifest.json"]


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (b"PK\x03\x04damaged", "does not open"),
        (make_ch5z({"index.html": ""}).replace(b".ch5", b".vtp"), "not a .ch5z"),
        (make_ch5z({"page.html": "<ch5-button sendeventonclick='1'>"}), "no index.html"),
    ],
)
def test_archives_that_are_not_ch5z_projects_are_refused(raw, message):
    with pytest.raises(UnsupportedFormat, match=message) as info:
        ch5.load_ch5z(raw)
    assert FORMATS_DOC in str(info.value)


def test_an_oversized_inner_archive_is_refused_unread(monkeypatch):
    monkeypatch.setattr(ch5, "_MAX_INNER", 10)
    with pytest.raises(UnsupportedFormat, match="too large"):
        read({"index.html": '<ch5-button sendeventonclick="10">'})


def test_files_outside_the_web_project_are_ignored():
    project = read(
        {
            "index.html": '<ch5-button sendeventonclick="10">',
            "node_modules/pkg/index.html": '<ch5-button sendeventonclick="99">',
            "app.js": 'CrComLib.publishEvent("b", "98", true)',
        }
    )
    assert [c.press for c in project.controls] == [10]


def test_a_project_with_joins_only_in_javascript_is_refused():
    with pytest.raises(UnsupportedFormat, match="JavaScript"):
        read({"index.html": '<div id="root"></div><script src="app.js"></script>'})


# ---- join attributes ---------------------------------------------------------------


HAND_WRITTEN = """
<ch5-button label="Pendants" sendeventonclick="10" receivestateselected="11"
            receivestateshow="12"></ch5-button>
<ch5-slider componentname="Volume" receivestatevalue="5" sendeventonchange="6"></ch5-slider>
<ch5-toggle label="Fan" receivestatevalue="13" sendeventonclick="13"></ch5-toggle>
<ch5-textinput label="Name" receivestatevalue="3"></ch5-textinput>
<span id="status" data-ch5-textcontent="4" class="ignored"></span>
<input id="plain" receivestatevalue="8">
<ch5-button label="Unused" sendeventonclick="0" receivestatelabel=""></ch5-button>
"""


@pytest.fixture
def hand_written() -> Project:
    return read({"index.html": HAND_WRITTEN})


def test_press_feedback_and_other_joins(hand_written):
    (button,) = [c for c in hand_written.controls if c.label == "Pendants"]
    assert (button.press, button.feedback, button.smart_object) == (10, 11, 0)
    assert button.other == (("receivestateshow", 12),)


def test_the_same_attribute_means_different_kinds_on_different_components(hand_written):
    (slider,) = by_object(hand_written, "Volume")
    assert slider.analog == 5 and slider.other == (("sendeventonchange", 6),)
    (toggle,) = [c for c in hand_written.controls if c.label == "Fan"]
    assert (toggle.press, toggle.feedback, toggle.analog) == (13, 13, None)
    (name,) = [c for c in hand_written.controls if c.label == "Name"]
    assert name.serial == 3 and name.analog is None


def test_data_ch5_attributes_on_plain_html(hand_written):
    (span,) = by_object(hand_written, "status")
    assert (span.control, span.serial) == ("span", 4)
    assert by_object(hand_written, "plain") == []  # component attributes do nothing on <input>


def test_zero_and_empty_joins_are_not_joins(hand_written):
    assert not [c for c in hand_written.controls if c.label == "Unused"]
    assert hand_written.unresolved == []


def test_a_hand_written_index_is_the_home_page(hand_written):
    assert hand_written.home_page == "index" and hand_written.pages == ["index"]


def test_list_templates_without_a_contract_are_reported_not_guessed():
    project = read(
        {
            "index.html": """
            <ch5-list size="4" indexid="idx">
              <template>
                <ch5-button label="Item" sendeventonclick="1{{idx}}"></ch5-button>
              </template>
            </ch5-list>
            <ch5-button label="Off" sendeventonclick="20"></ch5-button>
            """
        }
    )
    assert [c.press for c in project.controls] == [20]
    (note,) = project.unresolved
    assert 'sendeventonclick="1{{idx}}"' in note and "run time" in note


def test_a_name_with_no_contract_is_reported():
    project = read({"index.html": '<ch5-button sendeventonclick="Room.PowerOn"></ch5-button>'})
    assert project.controls == []
    assert "no contract to look it up in" in project.unresolved[0]


# ---- the contract ------------------------------------------------------------------


CONTRACT = contract(
    states={
        "boolean": {"1": {"3": "Room.Power.Selected"}, "2": {"1": "Room.Mute.Selected"}},
        "numeric": {"1": {"4": "Room.Volume.Feedback"}},
        "string": {"1": {"1": "Room.Name.Text"}},
    },
    events={
        "boolean": {"Room.Power.Press": {"joinId": 3, "smartObjectId": 1}},
        "numeric": {"Room.Volume.Set": {"joinId": 4, "smartObjectId": 1}},
    },
)


@pytest.fixture
def with_contract() -> Project:
    return read(
        {
            "index.html": """
            <ch5-button label="Power" sendeventonclick="Room.Power.Press"
                        receivestateselected="Room.Power.Selected"></ch5-button>
            <ch5-slider label="Volume" sendeventonchange="Room.Volume.Set"
                        receivestatevalue="Room.Volume.Feedback"></ch5-slider>
            <ch5-text receivestatelabel="Room.Name.Text"></ch5-text>
            <ch5-button label="Local" sendeventonclick="logsbtn.clicked"></ch5-button>
            """,
            "config/contract.cse2j": CONTRACT,
        }
    )


def test_contract_names_resolve_to_smart_object_joins(with_contract):
    (power,) = [c for c in with_contract.controls if c.label == "Power"]
    assert (power.press, power.feedback, power.smart_object) == (3, 3, 1)
    (volume,) = [c for c in with_contract.controls if c.label == "Volume"]
    assert (volume.analog, volume.smart_object) == (4, 1)
    (text,) = [c for c in with_contract.controls if c.control == "ch5-text"]
    assert (text.serial, text.smart_object) == (1, 1)


def test_contract_signals_no_html_names_are_still_listed(with_contract):
    (mute,) = [c for c in with_contract.controls if c.page == "(contract only)"]
    assert (mute.label, mute.feedback, mute.smart_object) == ("Room.Mute.Selected", 1, 2)


def test_names_missing_from_the_contract_are_reported(with_contract):
    (note,) = with_contract.unresolved
    assert 'sendeventonclick="logsbtn.clicked"' in note and "not in the contract" in note


def test_draft_from_a_contract_reads_smart_objects_and_writes_nothing(with_contract):
    jm = draft(with_contract)
    assert all(not e.writes() for e in jm.entities)
    keyed = {(e.type, e.smart_object, e.join or e.analog or e.serial) for e in jm.entities}
    assert {("binary_sensor", 1, 3), ("sensor", 1, 4), ("sensor", 1, 1)} <= keyed
    assert ("binary_sensor", 2, 1) in keyed


def test_draft_says_it_is_experimental_and_lists_unresolved(with_contract):
    text = draft_join_map(with_contract)
    assert "EXPERIMENTAL" in text and FORMATS_DOC in text
    assert "logsbtn.clicked" in text
    assert all(len(line) <= 100 for line in text.splitlines())


def test_contract_parsing_tolerates_junk_entries():
    parsed = ch5.Contract.parse(
        json.dumps(
            {
                "signals": {
                    "states": {"boolean": {"1": {"0": "zero", "x": "bad"}}, "weird": {}},
                    "events": {"string": {"A.B": {"joinId": 7, "smartObjectId": 9}, "C": 5}},
                }
            }
        ).encode()
    )
    assert [(s.name, s.kind, s.smart_object, s.join) for s in parsed.signals] == [
        ("A.B", "serial", 9, 7)
    ]


def test_a_broken_contract_is_refused():
    with pytest.raises(UnsupportedFormat, match="not valid JSON"):
        read({"index.html": "", "config/contract.cse2j": "{nope"})


# ---- Construct pages and widgets ---------------------------------------------------


def construct(pages: list[tuple[str, str, str]], default: str) -> dict:
    config = {
        "content": {
            "$defaultView": default,
            "pages": [
                {
                    "pageName": name,
                    "fullPath": f"./app/project/components/pages/{name}/",
                    "fileName": f"{name}.html",
                    "triggerViewChildProperties": {"receiveStateShow": show},
                    "navigation": {"label": name.title()},
                }
                for name, show, _ in pages
            ],
        }
    }
    out = {
        "index.html": "<div></div>",
        "assets/data/project-config.json": json.dumps(config),
        "app/template/components/widgets/template-logs/template-logs.html": (
            '<ch5-button sendeventonclick="logsbtn.clicked" receivestateshow="77"></ch5-button>'
        ),
    }
    for name, _, body in pages:
        out[f"app/project/components/pages/{name}/{name}.html"] = body
    return out


def test_construct_pages_home_first_with_visibility_joins():
    project = read(
        construct(
            [
                ("lights", "31", '<ch5-button label="All Off" sendeventonclick="40"></ch5-button>'),
                ("home", "30", '<ch5-button label="Lights" sendeventonclick="21"></ch5-button>'),
            ],
            default="home",
        )
    )
    assert project.pages == ["Home", "Lights"] and project.home_page == "Home"
    flips = [c for c in project.controls if c.control == "Page"]
    assert [(c.page, c.other) for c in flips] == [
        ("Home", (("receivestateshow (page visibility)", 30),)),
        ("Lights", (("receivestateshow (page visibility)", 31),)),
    ]


def test_construct_shell_files_are_skipped():
    page = '<ch5-button label="Lights" sendeventonclick="21"></ch5-button>'
    project = read(construct([("home", "0", page)], default="home"))
    assert all(77 not in (c.press, *dict(c.other).values()) for c in project.controls)
    assert project.unresolved == []


WIDGET = (
    '<template id="Row-widget">'
    '<ch5-button label="Scene" sendeventonclick="10" receivestatelabel="2"></ch5-button>'
    "</template>"
)


def test_a_template_placement_applies_its_offsets():
    project = read(
        construct(
            [
                (
                    "home",
                    "0",
                    '<ch5-template templateid="Row-widget" componentname="Row A"></ch5-template>'
                    '<ch5-template templateid="Row-widget" componentname="Row B" '
                    'booleanjoinoffset="100" stringjoinoffset="50"></ch5-template>',
                )
            ],
            default="home",
        )
        | {"app/project/components/widgets/row/row.html": WIDGET}
    )
    scenes = [(c.path, c.press, c.serial, c.offset_note) for c in project.controls]
    assert scenes == [
        ("Home > Row A", 10, 2, ""),
        ("Home > Row B", 110, 52, "d+100 s+50"),
    ]


def test_a_list_placement_steps_each_item():
    project = read(
        construct(
            [
                (
                    "home",
                    "0",
                    '<ch5-subpage-reference-list widgetid="Row-widget" componentname="Rows" '
                    'numberofitems="3" booleanjoinincrement="5"></ch5-subpage-reference-list>',
                )
            ],
            default="home",
        )
        | {"app/project/components/widgets/row/row.html": WIDGET}
    )
    assert [(c.path, c.press, c.serial) for c in project.controls] == [
        ("Home > Rows item 1", 10, 2),
        ("Home > Rows item 2", 15, 2),
        ("Home > Rows item 3", 20, 2),
    ]


def test_a_contract_list_resolves_each_item_from_the_contract():
    items = {str(10 + i): {"1201": f"Main.List.Items[{i}].Item.Button.Selected"} for i in range(2)}
    events = {
        f"Main.List.Items[{i}].Item.Button.Press": {"joinId": 1201, "smartObjectId": 10 + i}
        for i in range(2)
    }
    widget = (
        '<template id="Item-widget"><ch5-button label="label" '
        'sendeventonclick="Item.Button.Press" receivestateselected="Item.Button.Selected">'
        "</ch5-button></template>"
    )
    project = read(
        construct(
            [
                (
                    "main",
                    "0",
                    '<ch5-subpage-reference-list widgetid="Item-widget" contractname="Main.List" '
                    'numberofitems="2" indexid="idx"></ch5-subpage-reference-list>',
                )
            ],
            default="main",
        )
        | {
            "app/project/components/widgets/item/item.html": widget,
            "config/contract.cse2j": contract(
                states={"boolean": items}, events={"boolean": events}
            ),
        }
    )
    buttons = [(c.smart_object, c.press, c.feedback) for c in project.controls]
    assert buttons == [(10, 1201, 1201), (11, 1201, 1201)]
    assert project.unresolved == []
    assert not [c for c in project.controls if c.page == "(contract only)"]


def test_contract_enabled_marker_is_not_a_signal_name():
    project = read(
        {
            "index.html": '<ch5-dpad contractname="Media.Dpad" '
            'sendeventonclickstart="Contract Enabled"></ch5-dpad>',
            "config/contract.cse2j": contract(
                events={"boolean": {"Media.Dpad.Up": {"joinId": 1, "smartObjectId": 5}}}
            ),
        }
    )
    assert project.unresolved == []
    assert [(c.label, c.press, c.smart_object) for c in project.controls] == [
        ("Media.Dpad.Up", 1, 5)
    ]


def test_an_unplaced_widget_is_still_inventoried_and_recursion_stops():
    looping = (
        '<template id="Loop-widget"><ch5-button label="Again" sendeventonclick="9"></ch5-button>'
        '<ch5-template templateid="Loop-widget"></ch5-template></template>'
    )
    project = read({"index.html": "<p></p>", "widget.html": looping})
    assert [(c.page, c.press) for c in project.controls] == [("(unplaced) Loop-widget", 9)]


def test_one_unresolved_name_on_many_pages_is_reported_once():
    menu = (
        '<template id="Menu-widget">'
        '<ch5-button sendeventontouch="infoBtn.clicked"></ch5-button></template>'
    )
    place = '<ch5-template templateid="Menu-widget" componentname="Menu"></ch5-template>'
    project = read(
        construct(
            [("a", "0", place * 2), ("b", "0", place), ("c", "0", place)],  # twice on page a
            default="a",
        )
        | {
            "app/project/components/widgets/menu/menu.html": menu,
            "config/contract.cse2j": contract(states={"boolean": {"1": {"1": "Other"}}}),
        }
    )
    assert project.unresolved == [
        'A > Menu, ch5-button: sendeventontouch="infoBtn.clicked" '
        "(not in the contract; also on 2 other pages)"
    ]


def test_list_presses_are_never_subsystem_entry_candidates():
    project = read(
        {
            "index.html": (
                '<ch5-button label="Item" sendeventonclick="Main.Item.Press"></ch5-button>'
                '<ch5-button label="Lights" sendeventonclick="21"></ch5-button>'
            ),
            "config/contract.cse2j": contract(
                events={"boolean": {"Main.Item.Press": {"joinId": 1, "smartObjectId": 3}}}
            ),
        }
    )
    text = draft_join_map(project)
    assert "lights: {join: 21}" in text
    assert "item: {join: 1}" not in text


# ---- the public samples ------------------------------------------------------------


@pytest.fixture(scope="module")
def lightdark() -> Project:
    return panel.load_project(LIGHTDARK)


@pytest.fixture(scope="module")
def cwsdebug() -> Project:
    return panel.load_project(CWSDEBUG)


def test_cwsdebug_toggle_slider_and_list(cwsdebug):
    (toggle,) = [c for c in cwsdebug.controls if c.object_name == "Toggle"]
    assert (toggle.press, toggle.feedback, toggle.smart_object) == (3, 3, 1)
    (slider,) = [c for c in cwsdebug.controls if c.object_name == "Slider"]
    assert (slider.analog, slider.smart_object) == (4, 1)
    items = [c for c in cwsdebug.controls if c.path.startswith("main > Widget List item")]
    assert [(c.smart_object, c.press, c.feedback, c.serial) for c in items] == [
        (obj, 1201, 1201, 1) for obj in range(3, 8)
    ]
    assert cwsdebug.unresolved == []
    assert cwsdebug.home_page == "main"


def test_lightdark_pages_and_numeric_joins(lightdark):
    assert lightdark.home_page == "buttons" and lightdark.pages[0] == "buttons"
    assert len(lightdark.pages) == 28
    presses = {c.press for c in lightdark.controls if c.smart_object == 0 and c.press}
    assert presses == {70, 71}  # the showcase reuses two joins on every button


def test_lightdark_accounts_for_every_contract_signal(lightdark):
    raw = zipfile.ZipFile(LIGHTDARK)
    inner = zipfile.ZipFile(io.BytesIO(raw.read("LightDark.ch5")))
    signals = ch5.Contract.parse(inner.read("config/contract.cse2j")).signals
    assert len(signals) == 336
    seen = {
        (c.smart_object, join)
        for c in lightdark.controls
        if c.smart_object
        for join in (c.press, c.feedback, c.analog, c.serial, *dict(c.other).values())
        if join
    }
    assert {(s.smart_object, s.join) for s in signals} <= seen


def test_lightdark_reports_only_the_shell_menu_name(lightdark):
    assert lightdark.unresolved == [
        'buttons > Theme Menu, Info Button: sendeventontouch="infoBtn.clicked" '
        "(not in the contract; also on 27 other pages)"
    ]


def test_lightdark_draft_validates_and_writes_nothing(lightdark):
    jm = draft(lightdark)
    assert len(jm.entities) > 150
    assert all(not e.writes() for e in jm.entities)
    assert any(e.smart_object for e in jm.entities)


# ---- the command -------------------------------------------------------------------


def parse_args(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    panel.register(parser.add_subparsers())
    return parser.parse_args(["panel", *argv])


def test_parse_command_on_a_ch5z(tmp_path, capsys):
    out = tmp_path / "draft.yaml"
    args = parse_args("parse", str(CWSDEBUG), "-o", str(out))
    assert args.func(args) == 0
    assert "EXPERIMENTAL" in out.read_text()
    assert "experimental and untested" in capsys.readouterr().err


def test_csv_carries_the_smart_object(capsys):
    args = parse_args("parse", str(CWSDEBUG), "--format", "csv")
    assert args.func(args) == 0
    rows = list(csv.DictReader(io.StringIO(capsys.readouterr().out)))
    assert {row["smart_object"] for row in rows} >= {"1", "3", "7"}


# ---- damaged and odd input ---------------------------------------------------------


def test_a_corrupted_member_is_refused_cleanly():
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        z.writestr("index.html", '<ch5-button sendeventonclick="10">')
    data = bytearray(inner.getvalue())
    data[data.find(b"sendeventonclick")] ^= 0xFF  # index.html now fails its checksum
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w") as z:
        z.writestr("demo.ch5", bytes(data))
        z.writestr("demo_manifest.json", "{}")
    with pytest.raises(UnsupportedFormat, match="index.html inside the archive cannot be read"):
        ch5.load_ch5z(outer.getvalue())


def test_a_contract_section_of_the_wrong_type_is_ignored():
    parsed = ch5.Contract.parse(b'{"signals": {"states": [], "events": "x"}}')
    assert parsed.signals == []


def test_a_name_of_another_kind_is_not_used_for_this_attribute():
    project = read(
        {
            "index.html": '<ch5-button label="Power" sendeventonclick="Room.Power"></ch5-button>',
            "config/contract.cse2j": contract(states={"string": {"1": {"5": "Room.Power"}}}),
        }
    )
    assert not [c for c in project.controls if c.label == "Power"]
    assert "in the contract as serial, but this attribute is digital" in project.unresolved[0]


def test_only_ascii_digits_are_join_numbers():
    project = read({"index.html": '<ch5-button label="Sq" sendeventonclick="²"></ch5-button>'})
    assert project.controls == []
    assert "no contract" in project.unresolved[0]
