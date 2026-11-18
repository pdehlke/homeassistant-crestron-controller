"""The CIP client against a fake processor over real TCP."""

import pytest
from cipcore import client as cip
from cipcore.client import CipClient, CipError, Subsystem, Timing
from cipcore.policy import DIGITAL, WritePolicy, WriteRefused

from tests.conftest import wait_for

FAST = Timing(
    sync_quiet_seconds=0.2,
    entry_min_seconds=0.1,
    entry_timeout=1.0,
    repoll_timeout=0.5,
    bringup_retry_seconds=0.2,
    reconnect_backoff=(0.05,),
)
GATES = {
    "lights": Subsystem("lights", 40, quiet_seconds=0.1),
    "av": Subsystem("av", 41, quiet_seconds=0.1),
}


def writable(*joins, deny=()):
    return WritePolicy(
        enabled=True, allow={DIGITAL: frozenset(joins)}, deny={DIGITAL: frozenset(deny)}
    )


async def started(client):
    await client.async_start()
    return client


async def test_ungated_link_registers_and_syncs(processor):
    processor.digital[None] = {121: 1, 126: 0}
    processor.serial[5] = "Hello"
    seen = []
    client = await started(
        CipClient(
            "t",
            "127.0.0.1",
            0x2A,
            port=processor.port,
            timing=FAST,
            on_join=lambda *a: seen.append(a),
        )
    )
    try:
        await wait_for(lambda: client.synced)
        assert client.digital_for(None) == {121: 1, 126: 0}
        assert client.serial[5] == "Hello"
        assert client.has_state_for(None)
        assert ("digital", 121, 1, None) in seen
        assert processor.presses == []  # nothing pressed, ever
    finally:
        await client.async_stop()


async def test_an_undefined_ipid_is_reported_by_kind(processor):
    client = await started(CipClient("t", "127.0.0.1", 0x30, port=processor.port, timing=FAST))
    try:
        await wait_for(lambda: client.last_error_kind == cip.ERROR_IPID_MISSING)
        assert "not defined" in client.last_error
    finally:
        await client.async_stop()


async def test_probe_distinguishes_the_ways_a_first_connection_fails(processor):
    assert (await cip.async_probe("127.0.0.1", 0x2A, processor.port)).ok
    missing = await cip.async_probe("127.0.0.1", 0x30, processor.port)
    assert missing.result == cip.ERROR_IPID_MISSING
    await processor.stop()
    gone = await cip.async_probe("127.0.0.1", 0x2A, processor.port, 1)
    assert gone.result == cip.ERROR_UNREACHABLE


async def test_gated_link_in_listen_only_mode_presses_nothing_and_claims_nothing(processor):
    processor.entries = {"lights": 40}
    processor.digital = {None: {1: 1}, "lights": {301: 1}}
    client = await started(
        CipClient(
            "t",
            "127.0.0.1",
            0x2A,
            port=processor.port,
            subsystems=GATES,
            default_subsystem="lights",
            timing=FAST,
        )
    )
    try:
        await wait_for(lambda: client.synced)
        assert processor.presses == []
        # The menu arrived, but nothing about lights: reading lights as off
        # would be the confidently wrong answer.
        assert not client.has_state_for("lights")
        assert client.current_subsystem is None
    finally:
        await client.async_stop()


async def test_gated_bring_up_enters_and_a_repoll_fills_a_partial_dump(processor):
    processor.entries = {"lights": 40, "av": 41}
    processor.digital = {"lights": {301: 1, 341: 1}, "av": {301: 0}}
    processor.omit_on_entry = {"lights": {341}}
    client = await started(
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
        await wait_for(lambda: client.synced)
        assert processor.presses == [40]
        assert client.current_subsystem == "lights"
        # 341 was left out of the entry dump; the re-poll brought it back.
        assert client.digital_for("lights") == {301: 1, 341: 1}
    finally:
        await client.async_stop()


async def test_joins_are_filed_under_the_subsystem_that_reported_them(processor):
    processor.entries = {"lights": 40, "av": 41}
    processor.digital = {"lights": {301: 1}, "av": {301: 0, 550: 1}}
    client = await started(
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
        await wait_for(lambda: client.synced)
        assert await client.async_enter("av")
        assert client.digital_for("av")[301] == 0
        assert client.digital_for("lights")[301] == 1  # untouched by the av dump
        with pytest.raises(CipError, match="slot is in av"):
            await client.async_press(301, "lights")
    finally:
        await client.async_stop()


async def test_a_merge_never_turns_an_omitted_join_off(processor):
    processor.entries = {"lights": 40, "av": 41}
    processor.digital = {"lights": {341: 1}, "av": {550: 1}}
    client = await started(
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
        )
    )
    try:
        await wait_for(lambda: client.synced)
        assert client.digital_for("lights")[341] == 1
        await client.async_enter("av")
        processor.omit_on_entry = {"lights": {341}}
        await client.async_enter("lights")
        assert client.digital_for("lights")[341] == 1
    finally:
        await client.async_stop()


async def test_the_policy_is_checked_at_the_wire(processor):
    client = await started(
        CipClient(
            "t", "127.0.0.1", 0x2A, port=processor.port, timing=FAST, policy=writable(5, deny=[6])
        )
    )
    try:
        await wait_for(lambda: client.synced)
        await client.async_press(5, None)
        with pytest.raises(WriteRefused):
            await client.async_press(6, None)
        with pytest.raises(WriteRefused):
            await client.async_press(7, None)
        await wait_for(lambda: processor.releases == [5])
        assert processor.presses == [5]
    finally:
        await client.async_stop()


async def test_a_gated_entry_join_on_the_deny_list_is_never_pressed(processor):
    processor.entries = {"lights": 40}
    client = await started(
        CipClient(
            "t",
            "127.0.0.1",
            0x2A,
            port=processor.port,
            subsystems={"lights": GATES["lights"]},
            default_subsystem="lights",
            policy=writable(40, deny=[40]),
            timing=FAST,
        )
    )
    try:
        await wait_for(lambda: client.synced)
        assert processor.presses == []
    finally:
        await client.async_stop()


async def test_reconnects_after_a_drop_and_counts_displacements(processor):
    processor.digital[None] = {1: 1}
    client = await started(CipClient("t", "127.0.0.1", 0x2A, port=processor.port, timing=FAST))
    try:
        await wait_for(lambda: client.synced)
        await processor.drop(disconnect_frame=True)
        await wait_for(lambda: processor.connections == 2 and client.synced)
        assert client.recent_displacements() == 1
        assert client.generation == 2
    finally:
        await client.async_stop()


async def test_disconnected_since_tracks_an_outage(processor):
    client = await started(CipClient("t", "127.0.0.1", 0x2A, port=processor.port, timing=FAST))
    try:
        await wait_for(lambda: client.synced)
        assert client.disconnected_since is None
        await processor.stop()
        await wait_for(lambda: client.disconnected_since is not None)
        assert client.last_error_kind in (cip.ERROR_CLOSED, cip.ERROR_UNREACHABLE)
    finally:
        await client.async_stop()


async def test_unanswered_repoll_still_syncs(processor):
    processor.entries = {"lights": 40}
    processor.digital = {"lights": {301: 1}}
    processor.answer_repoll = False
    client = await started(
        CipClient(
            "t",
            "127.0.0.1",
            0x2A,
            port=processor.port,
            subsystems={"lights": GATES["lights"]},
            default_subsystem="lights",
            policy=writable(40),
            timing=FAST,
        )
    )
    try:
        await wait_for(lambda: client.synced)
        assert client.digital_for("lights") == {301: 1}
    finally:
        await client.async_stop()
