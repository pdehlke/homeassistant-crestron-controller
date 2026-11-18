"""Constants shared across the integration's Home Assistant modules."""

from __future__ import annotations

DOMAIN = "crestron_controller"

CONF_IPID = "ipid"
CONF_JOIN_MAP = "join_map"
CONF_ALLOW_WRITES = "allow_writes"
CONF_TLS = "tls"
# Also accept TLS 1.0 and 1.1, for processors too old for 1.2. Off unless the
# user turns it on. See docs/configuration/encrypted-cip.md.
CONF_LEGACY_TLS = "legacy_tls"
# The SHA-256 of the processor's TLS certificate, pinned when the entry was
# created or last reconfigured. See docs/adr/0011-cip-over-tls-with-a-pinned-certificate.md.
CONF_FINGERPRINT = "fingerprint"

DEFAULT_JOIN_MAP_DIR = "crestron_controller"

# How long a link may stay down before Home Assistant raises a repair. Long
# enough that a processor reboot does not page anyone, short enough that a
# processor that moved address overnight is noticed the same morning. The
# reason this exists at all is in docs/case-study/post-mortem-dhcp-address-change.md.
UNREACHABLE_REPAIR_SECONDS = 600.0

# How many times the processor may end our session inside the displacement
# window before a repair suggests something else is using the IP-ID.
DISPLACEMENT_REPAIR_COUNT = 3

HEALTH_CHECK_INTERVAL = 30.0
IDLE_WATCH_INTERVAL = 1.0
CONFIRM_TIMEOUT = 3.0
CONFIRM_ATTEMPTS = 2

STARTER_JOIN_MAP = """\
# Join map for one Crestron processor, used by the Crestron Controller integration.
#
# This file starts empty on purpose. With no entities, Home Assistant still
# connects, registers as your panel's IP-ID and shows a connectivity sensor,
# which proves the connection before you map a single light.
#
# Next steps:
#   1. Inventory your system with the crestron-controller CLI and paste entries here.
#   2. Reload the integration (Settings > Devices & services > Crestron Controller >
#      three-dot menu > Reload) after every edit.
#
# Format: docs/configuration/join-map-reference.md in the
# homeassistant-crestron-controller repository.
version: 1

# Joins that must never be written, whatever else this file says. If your
# system has an alarm keypad, gate or anything safety-related on panel pages,
# list its joins here before you enable writes.
never_write:
  digital: []

entities: []
"""
