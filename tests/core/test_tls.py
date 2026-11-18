"""CIP over TLS against the fake processor, and what happens when only one end speaks it."""

import time

from cipcore import client as cip
from cipcore.client import CipClient, Timing

from tests.conftest import wait_for

FAST = Timing(sync_quiet_seconds=0.2, reconnect_backoff=(0.05,), greeting_timeout=0.5)
WRONG = ":".join(["00"] * 32)


async def started(client):
    await client.async_start()
    return client


async def test_a_tls_link_registers_and_syncs(tls_processor):
    tls_processor.digital[None] = {121: 1}
    client = await started(
        CipClient("t", "127.0.0.1", 0x2A, port=tls_processor.port, tls=True, timing=FAST)
    )
    try:
        await wait_for(lambda: client.synced)
        assert client.digital_for(None) == {121: 1}
        assert client.peer_fingerprint == tls_processor.fingerprint
        assert tls_processor.presses == []
    finally:
        await client.async_stop()


async def test_a_pinned_certificate_that_matches_is_accepted(tls_processor):
    # Written the way a person might paste it: lower case, no colons.
    pin = tls_processor.fingerprint.replace(":", "").lower()
    client = await started(
        CipClient(
            "t",
            "127.0.0.1",
            0x2A,
            port=tls_processor.port,
            tls=True,
            pinned_fingerprint=pin,
            timing=FAST,
        )
    )
    try:
        await wait_for(lambda: client.synced)
    finally:
        await client.async_stop()


async def test_a_changed_certificate_is_refused_before_registering(tls_processor):
    client = await started(
        CipClient(
            "t",
            "127.0.0.1",
            0x2A,
            port=tls_processor.port,
            tls=True,
            pinned_fingerprint=WRONG,
            timing=FAST,
        )
    )
    try:
        await wait_for(lambda: client.last_error_kind == cip.ERROR_CERT_CHANGED)
        assert tls_processor.fingerprint in client.last_error
        assert tls_processor.registrations == []
        assert not client.registered
    finally:
        await client.async_stop()


async def test_probe_over_tls_returns_the_fingerprint(tls_processor):
    probe = await cip.async_probe("127.0.0.1", 0x2A, tls_processor.port, tls=True)
    assert probe.ok
    assert probe.fingerprint == tls_processor.fingerprint
    probe = await cip.async_probe(
        "127.0.0.1", 0x2A, tls_processor.port, tls=True, pinned_fingerprint=WRONG
    )
    assert probe.result == cip.ERROR_CERT_CHANGED
    assert tls_processor.registrations == [0x2A]  # only the first probe registered


async def test_tls_to_a_plain_port_fails_fast_with_a_tls_error(processor):
    began = time.monotonic()
    probe = await cip.async_probe("127.0.0.1", 0x2A, processor.port, tls=True)
    assert probe.result == cip.ERROR_TLS
    assert time.monotonic() - began < 2
    client = await started(
        CipClient("t", "127.0.0.1", 0x2A, port=processor.port, tls=True, timing=FAST)
    )
    try:
        await wait_for(lambda: client.last_error_kind == cip.ERROR_TLS, timeout=2)
        assert "plain CIP" in client.last_error
    finally:
        await client.async_stop()


async def test_plain_to_a_tls_port_fails_at_the_greeting_timeout(tls_processor):
    began = time.monotonic()
    probe = await cip.async_probe("127.0.0.1", 0x2A, tls_processor.port, greeting_timeout=0.5)
    assert probe.result == cip.ERROR_NO_GREETING
    assert time.monotonic() - began < 2
    client = await started(CipClient("t", "127.0.0.1", 0x2A, port=tls_processor.port, timing=FAST))
    try:
        await wait_for(lambda: client.last_error_kind == cip.ERROR_NO_GREETING, timeout=3)
        assert "may expect TLS" in client.last_error
    finally:
        await client.async_stop()


async def test_old_tls_is_refused_unless_the_link_allows_it(old_tls_processor):
    probe = await cip.async_probe("127.0.0.1", 0x2A, old_tls_processor.port, tls=True)
    assert probe.result == cip.ERROR_TLS
    probe = await cip.async_probe(
        "127.0.0.1", 0x2A, old_tls_processor.port, tls=True, legacy_tls=True
    )
    assert probe.ok
    assert probe.tls_version == "TLSv1"
    assert probe.fingerprint == old_tls_processor.fingerprint


async def test_a_legacy_link_registers_over_tls_1_0(old_tls_processor):
    old_tls_processor.digital[None] = {121: 1}
    client = await started(
        CipClient(
            "t",
            "127.0.0.1",
            0x2A,
            port=old_tls_processor.port,
            tls=True,
            legacy_tls=True,
            pinned_fingerprint=old_tls_processor.fingerprint,
            timing=FAST,
        )
    )
    try:
        await wait_for(lambda: client.synced)
        assert client.tls_version == "TLSv1"
        assert client.digital_for(None) == {121: 1}
    finally:
        await client.async_stop()


async def test_legacy_still_prefers_modern_tls(tls_processor):
    probe = await cip.async_probe("127.0.0.1", 0x2A, tls_processor.port, tls=True, legacy_tls=True)
    assert probe.ok
    assert probe.tls_version in ("TLSv1.2", "TLSv1.3")
