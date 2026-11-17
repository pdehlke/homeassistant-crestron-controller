"""Crestron CIP panel emulation with no Home Assistant dependency.

Shared by the Home Assistant integration and the `crestron-controller` inventory CLI, so
the two can never disagree about the wire format, the write policy or what a
valid join map is. Nothing in this package may import from Home Assistant.
"""
