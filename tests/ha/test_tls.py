"""Encrypted CIP through Home Assistant: setup, pinning, repairs, and TLS on one end only."""

from __future__ import annotations

import functools
import time

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.data_entry_flow import FlowResultType

from custom_components.crestron_controller import ISSUE_CERT_CHANGED, evaluate_health
from custom_components.crestron_controller.cipcore import client as cip
from custom_components.crestron_controller.config_flow import _port
from custom_components.crestron_controller.const import (
    CONF_FINGERPRINT,
    CONF_IPID,
    CONF_JOIN_MAP,
    CONF_LEGACY_TLS,
    CONF_TLS,
    DOMAIN,
)
from tests.conftest import wait_for
from tests.ha.test_integration import add_entry, seed, setup

WRONG = ":".join(["00"] * 32)


async def _submit(hass, port, tls, ipid="0x2A", legacy=False):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Secure",
            CONF_HOST: "127.0.0.1",
            CONF_IPID: ipid,
            CONF_TLS: tls,
            CONF_LEGACY_TLS: legacy,
            CONF_PORT: port,
            CONF_JOIN_MAP: "",
        },
    )


def tls_entry(hass, config_dir, processor, fingerprint):
    entry = add_entry(hass, config_dir, processor)
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_TLS: True, CONF_FINGERPRINT: fingerprint}
    )
    return entry


async def test_config_flow_pins_the_certificate(hass, config_dir, tls_processor):
    result = await _submit(hass, tls_processor.port, True)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_TLS] is True
    assert result["data"][CONF_FINGERPRINT] == tls_processor.fingerprint
    assert tls_processor.presses == []
    await hass.async_block_till_done()
    for entry in hass.config_entries.async_entries(DOMAIN):
        await hass.config_entries.async_unload(entry.entry_id)


async def test_a_plain_entry_stores_no_pin(hass, config_dir, processor):
    result = await _submit(hass, processor.port, False)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_TLS] is False
    assert result["data"][CONF_FINGERPRINT] is None
    await hass.async_block_till_done()
    for entry in hass.config_entries.async_entries(DOMAIN):
        await hass.config_entries.async_unload(entry.entry_id)


async def test_a_tls_entry_connects_and_reports_state(hass, config_dir, tls_processor):
    seed(tls_processor)
    entry = tls_entry(hass, config_dir, tls_processor, tls_processor.fingerprint)
    hub = await setup(hass, entry)
    try:
        assert hub.client.tls
        assert hass.states.get("binary_sensor.house_link").state == "on"
        assert hass.states.get("sensor.house_now_playing").state == "Track One"
    finally:
        await hass.config_entries.async_unload(entry.entry_id)


async def test_a_changed_certificate_raises_the_repair(hass, config_dir, tls_processor):
    entry = tls_entry(hass, config_dir, tls_processor, WRONG)
    assert await hass.config_entries.async_setup(entry.entry_id)
    hub = entry.runtime_data.hub
    try:
        await wait_for(lambda: hub.client.last_error_kind == cip.ERROR_CERT_CHANGED)
        assert evaluate_health(hub, time.monotonic()) == {ISSUE_CERT_CHANGED}
        assert tls_processor.registrations == []
    finally:
        await hass.config_entries.async_unload(entry.entry_id)


async def test_tls_on_a_plain_port_is_a_setup_error(hass, config_dir, processor):
    result = await _submit(hass, processor.port, True)
    assert result["errors"] == {"base": "tls_failed"}


async def test_plain_on_a_tls_port_is_a_setup_error(hass, config_dir, tls_processor, monkeypatch):
    monkeypatch.setattr(
        cip, "async_probe", functools.partial(cip.async_probe, greeting_timeout=0.5)
    )
    result = await _submit(hass, tls_processor.port, False)
    assert result["errors"] == {"base": "no_greeting"}


async def test_reconfigure_accepts_a_new_certificate(hass, config_dir, tls_processor):
    entry = tls_entry(hass, config_dir, tls_processor, WRONG)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "127.0.0.1", CONF_IPID: "0x2A", CONF_TLS: True, CONF_PORT: tls_processor.port},
    )
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.data[CONF_FINGERPRINT] == tls_processor.fingerprint
    await wait_for(lambda: entry.runtime_data.hub.connected)
    await hass.config_entries.async_unload(entry.entry_id)


def test_a_blank_port_means_the_standard_one_for_the_transport():
    assert _port({CONF_TLS: True}) == 41796
    assert _port({CONF_TLS: False}) == 41794
    assert _port({}) == 41794
    assert _port({CONF_TLS: True, CONF_PORT: 5000}) == 5000


async def test_an_old_processor_needs_old_tls_turned_on(hass, config_dir, old_tls_processor):
    result = await _submit(hass, old_tls_processor.port, True)
    assert result["errors"] == {"base": "tls_failed"}
    # The same form, resubmitted with old TLS ticked, as a user would.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Secure",
            CONF_HOST: "127.0.0.1",
            CONF_IPID: "0x2A",
            CONF_TLS: True,
            CONF_LEGACY_TLS: True,
            CONF_PORT: old_tls_processor.port,
            CONF_JOIN_MAP: "",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_LEGACY_TLS] is True
    assert result["data"][CONF_FINGERPRINT] == old_tls_processor.fingerprint
    await hass.async_block_till_done()
    (entry,) = hass.config_entries.async_entries(DOMAIN)
    await wait_for(lambda: entry.runtime_data.hub.connected)
    assert entry.runtime_data.hub.client.tls_version == "TLSv1"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_old_tls_without_tls_is_not_stored(hass, config_dir, processor):
    result = await _submit(hass, processor.port, False, legacy=True)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_LEGACY_TLS] is False
    await hass.async_block_till_done()
    for entry in hass.config_entries.async_entries(DOMAIN):
        await hass.config_entries.async_unload(entry.entry_id)
