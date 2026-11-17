import pytest
from cipcore.joinmap import JoinMapError, parse
from cipcore.policy import ANALOG, DIGITAL

GATED = {
    "subsystems": {
        "default": "lights",
        "entries": {"lights": {"join": 40, "quiet_seconds": 0.5}, "av": {"join": 41}},
    },
    "never_write": {"digital": ["200-219", 45]},
    "entities": [
        {"type": "light", "name": "Breakfast Nook", "feedback": 301, "also_reports": [327]},
        {
            "type": "light",
            "name": "Mudroom",
            "press": "on_off",
            "feedback": 302,
            "on_join": 327,
            "off_join": 302,
        },
        {"type": "switch", "name": "Fountain", "press": "momentary", "on_join": 50, "off_join": 51},
        {"type": "binary_sensor", "name": "Gate", "join": 205},
        {"type": "button", "name": "All Off", "join": 60},
        {"type": "sensor", "name": "Zone", "serial": 11},
        {
            "type": "number",
            "name": "Volume",
            "subsystem": "av",
            "analog": 11,
            "scale": "percent",
            "writable": True,
        },
    ],
}


def test_a_full_gated_map_parses():
    jm = parse(GATED)
    assert jm.default_subsystem == "lights"
    assert jm.subsystems["lights"].quiet_seconds == 0.5
    assert jm.subsystems["av"].quiet_seconds == 0.85
    table = jm.entities[0]
    assert (table.id, table.press_join, table.subsystem) == ("breakfast_nook", 301, "lights")
    assert 205 in jm.never_write[DIGITAL] and 45 in jm.never_write[DIGITAL]


def test_policy_allows_mapped_writes_and_entry_joins_only():
    policy = parse(GATED).policy(enabled=True)
    assert policy.allow[DIGITAL] == {40, 41, 301, 302, 327, 50, 51, 60}
    assert policy.allow[ANALOG] == {11}
    assert not policy.permits(DIGITAL, 205)  # read-only sensor joins are never writable
    assert not parse(GATED).policy(enabled=False).permits(DIGITAL, 301)


def test_momentary_with_one_join_toggles_blind():
    jm = parse(
        {"entities": [{"type": "switch", "name": "Pump", "press": "momentary", "on_join": 7}]}
    )
    pump = jm.entities[0]
    assert pump.assumed_state and pump.press_for(True) == pump.press_for(False) == 7


@pytest.mark.parametrize(
    ("entities", "message"),
    [
        ([{"type": "light", "name": "X"}], "needs a feedback join"),
        ([{"type": "light", "name": "X", "press": "on_off", "feedback": 1}], "on_join"),
        (
            [{"type": "switch", "name": "X", "press": "momentary", "on_join": 1, "feedback": 2}],
            "no feedback",
        ),
        (
            [
                {"type": "light", "name": "X", "feedback": 1},
                {"type": "light", "name": "X", "feedback": 2},
            ],
            "already used",
        ),
        (
            [
                {"type": "light", "name": "A", "feedback": 1},
                {"type": "switch", "name": "B", "feedback": 1},
            ],
            "also writes",
        ),
        ([{"type": "light", "name": "X", "feedback": 1, "colour": 3}], "unknown key"),
        ([{"type": "fan", "name": "X"}], "type must be"),
        ([{"type": "sensor", "name": "X", "analog": 1, "serial": 2}], "exactly one"),
        ([{"type": "number", "name": "X", "analog": 1, "min": 50, "max": 10}], "min < max"),
        ([{"type": "light", "name": "X", "feedback": 0}], "outside"),
    ],
)
def test_invalid_entities_are_refused_with_a_useful_message(entities, message):
    with pytest.raises(JoinMapError, match=message):
        parse({"entities": entities})


def test_a_writable_join_on_the_never_write_list_is_refused():
    with pytest.raises(JoinMapError, match="never-write"):
        parse(
            {
                "never_write": {"digital": ["204-209"]},
                "entities": [{"type": "light", "name": "Den", "feedback": 206}],
            }
        )


def test_reading_a_denied_join_is_fine():
    jm = parse(
        {
            "never_write": {"digital": [212]},
            "entities": [{"type": "binary_sensor", "name": "Panic", "join": 212}],
        }
    )
    assert jm.entities[0].join == 212


def test_an_entry_join_on_the_never_write_list_is_refused():
    raw = {
        "subsystems": {"default": "alarm", "entries": {"alarm": {"join": 45}}},
        "never_write": {"digital": [45]},
    }
    with pytest.raises(JoinMapError, match="could never be entered"):
        parse(raw)


def test_subsystem_rules():
    with pytest.raises(JoinMapError, match="names a subsystem"):
        parse({"entities": [{"type": "binary_sensor", "name": "X", "join": 1, "subsystem": "av"}]})
    with pytest.raises(JoinMapError, match="default"):
        parse({"subsystems": {"entries": {"lights": {"join": 40}}}})
    with pytest.raises(JoinMapError, match="share an entry join"):
        parse({"subsystems": {"default": "a", "entries": {"a": {"join": 1}, "b": {"join": 1}}}})


def test_same_join_writable_in_two_subsystems_is_fine():
    # Programs that gate subsystems reuse join numbers; that is the point of gating.
    jm = parse(
        {
            "subsystems": {
                "default": "lights",
                "entries": {"lights": {"join": 40}, "av": {"join": 41}},
            },
            "entities": [
                {"type": "light", "name": "Nook", "feedback": 301},
                {"type": "button", "name": "Menu", "join": 301, "subsystem": "av"},
            ],
        }
    )
    assert len(jm.entities) == 2


def test_timing_overrides_and_empty_file():
    jm = parse({"timing": {"entry_timeout": 6}})
    assert jm.timing.entry_timeout == 6.0
    with pytest.raises(JoinMapError, match="unknown"):
        parse({"timing": {"bogus": 1}})
    assert parse(None).entities == ()


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (
            {"subsystems": {"default": "a", "entries": {"a": {"join": 1, "quiet_second": 1}}}},
            "unknown key",
        ),
        (
            {"subsystems": {"default": "a", "entries": {"a": {"join": 1, "quiet_seconds": 0}}}},
            "positive",
        ),
        (
            {
                "subsystems": {
                    "default": "a",
                    "idle_return_seconds": -1,
                    "entries": {"a": {"join": 1}},
                }
            },
            "positive",
        ),
        (
            {"subsystems": {"default": "a", "idle_return": 5, "entries": {"a": {"join": 1}}}},
            "unknown key",
        ),
        (
            {
                "entities": [
                    {
                        "type": "light",
                        "name": "X",
                        "feedback": 1,
                        "brightness": {"join": 2, "writeable": True},
                    }
                ]
            },
            "unknown brightness",
        ),
    ],
)
def test_typos_in_nested_sections_are_refused(raw, message):
    with pytest.raises(JoinMapError, match=message):
        parse(raw)
