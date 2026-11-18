import pytest
from cipcore.policy import ANALOG, DIGITAL, WritePolicy, WriteRefused


def make(enabled=True):
    return WritePolicy(
        enabled=enabled,
        allow={DIGITAL: frozenset({10, 20}), ANALOG: frozenset({5})},
        deny={DIGITAL: frozenset({20, 99})},
    )


def test_listen_only_refuses_even_allowed_joins():
    with pytest.raises(WriteRefused, match="listen-only"):
        make(enabled=False).check(DIGITAL, 10)


def test_unmapped_joins_are_refused():
    with pytest.raises(WriteRefused, match="not mapped"):
        make().check(DIGITAL, 11)


def test_deny_wins_over_allow_and_over_listen_only_message():
    with pytest.raises(WriteRefused, match="never-write"):
        make().check(DIGITAL, 20)
    with pytest.raises(WriteRefused, match="never-write"):
        make(enabled=False).check(DIGITAL, 99)


def test_kinds_are_separate():
    policy = make()
    policy.check(ANALOG, 5)
    assert not policy.permits(ANALOG, 10)
    assert policy.conflicts() == [(DIGITAL, 20, 0)]
