"""`crestron-controller check`: what a join map would let Home Assistant write."""

from __future__ import annotations

from crestron_controller_cli.__main__ import build_parser

MAP = """\
version: 1
never_write:
  digital: ["200-202"]
  smart_objects:
    3: {digital: [9]}
entities:
  - {type: button, name: All Off, join: 60}
  - {type: button, name: Next Page, join: 30, smart_object: 3}
  - type: select
    name: Den Source
    smart_object: 3
    options:
      - {name: Radio, press: 1}
      - {name: Streaming, press: 2}
"""


def run(tmp_path, text: str) -> int:
    path = tmp_path / "house.yaml"
    path.write_text(text)
    args = build_parser().parse_args(["check", str(path)])
    return args.func(args)


def test_check_lists_each_smart_objects_writes_apart(tmp_path, capsys):
    assert run(tmp_path, MAP) == 0
    out = capsys.readouterr().out
    allowed, denied = out.split("never written")
    assert "digital: 60" in allowed
    assert "SmartObject 3 (untested on real hardware): digital 1-2, 30" in allowed
    assert "digital: 200-202" in denied
    assert "SmartObject 3 (untested on real hardware): digital 9" in denied
    assert "select: 1" in out


def test_check_reports_an_invalid_map(tmp_path, capsys):
    bad = MAP.replace("press: 2}", "press: 9}")
    assert run(tmp_path, bad) == 1
    assert "in SmartObject 3, which is on the never-write list" in capsys.readouterr().err
