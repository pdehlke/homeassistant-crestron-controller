"""Diagnostics download: every join the processor has reported on this link.

This doubles as an inventory tool that needs nothing installed. A user who has
connected listen-only can download diagnostics, see which joins are high, and
work out which one is the light they just switched at a keypad.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry) -> dict[str, Any]:
    hub = entry.runtime_data.hub
    client = hub.client
    return {
        "link": {
            "host": client.host,
            "port": client.port,
            "ipid": f"0x{client.ipid:02X}",
            "connected": client.connected,
            "synced": client.synced,
            "writes_enabled": hub.writes_enabled,
            "current_subsystem": client.current_subsystem,
            "entered_subsystems": sorted(client.entered),
            "last_error": client.last_error,
            "recent_displacements": client.recent_displacements(),
        },
        "joins": {
            (name or "(no subsystem)"): {
                "digital_high": sorted(j for j, v in client.digital_for(name).items() if v),
                "digital_low": sorted(j for j, v in client.digital_for(name).items() if not v),
                "analog": dict(sorted(client.analog_for(name).items())),
            }
            for name in client.buckets()
        },
        "serial": dict(sorted(client.serial.items())),
        "entities": [
            {
                "id": e.id,
                "type": e.type,
                "subsystem": e.subsystem,
                "reads": e.reads(),
                "writes": e.writes(),
            }
            for e in hub.joinmap.entities
        ],
    }
