"""`crestron-controller listen` and the watch labeller, against the TCP fake processor."""

from __future__ import annotations

import pytest
import yaml
from cipcore.joinmap import parse

from crestron_controller_cli import session
from crestron_controller_cli.__main__ import build_parser


def args_for(processor, *extra, seconds="2"):
    return build_parser().parse_args(
        [
            "listen",
            "127.0.0.1",
            "--ipid",
            "0x2A",
            "--port",
            str(processor.port),
            "--seconds",
            seconds,
            *extra,
        ]
    )


async def test_listen_records_joins_and_writes_a_valid_draft(processor, tmp_path, capsys):
    processor.digital[None] = {121: 1, 122: 0}
    processor.analog[None] = {11: 500}
    processor.serial[5] = "Den"
    draft = tmp_path / "draft.yaml"
    assert await session._listen(args_for(processor, "--draft", str(draft))) == 0
    jm = parse(yaml.safe_load(draft.read_text()))
    assert {e.join for e in jm.entities if e.type == "binary_sensor"} == {121, 122}
    assert {e.analog for e in jm.entities if e.analog} == {11}
    assert processor.presses == []
    assert "high: d121" in capsys.readouterr().out


async def test_listen_on_an_undefined_ipid_fails_before_registering_for_real(processor):
    args = build_parser().parse_args(
        ["listen", "127.0.0.1", "--ipid", "0x30", "--port", str(processor.port)]
    )
    assert await session._listen(args) == 2


async def test_enter_without_allow_press_refuses(processor):
    with pytest.raises(SystemExit, match="allow-press"):
        await session._listen(args_for(processor, "--enter", "40"))
    assert processor.presses == []


async def test_enter_on_the_never_write_list_refuses(processor):
    with pytest.raises(SystemExit, match="never-write"):
        await session._listen(
            args_for(processor, "--enter", "45", "--allow-press", "--never-write", "45,200-219")
        )
    assert processor.presses == []


async def test_enter_presses_one_join_and_measures_the_dump(processor, tmp_path, capsys):
    processor.entries = {"lights": 40}
    processor.digital = {None: {1: 1}, "lights": {301: 1, 302: 0, 303: 1}}
    draft = tmp_path / "draft.yaml"
    result = await session._listen(
        args_for(processor, "--enter", "40", "--allow-press", "--draft", str(draft), seconds="5")
    )
    assert result == 0
    assert processor.presses == [40]
    out = capsys.readouterr().out
    assert "Suggested quiet_seconds" in out
    jm = parse(yaml.safe_load(draft.read_text()))
    assert jm.subsystems["main"].entry_join == 40
    assert {e.join for e in jm.entities} >= {301, 302, 303}


async def test_label_appends_an_entry_that_validates(tmp_path, monkeypatch):
    target = tmp_path / "labels.yaml"
    target.write_text("version: 1\nentities:\n")
    monkeypatch.setattr("builtins.input", lambda prompt: "Porch Light")
    await session._label(target, [("digital", 121, 1), ("digital", 122, 1), ("analog", 3, 9)])
    jm = parse(yaml.safe_load(target.read_text()))
    assert [(e.name, e.join) for e in jm.entities] == [("Porch Light", 121)]
