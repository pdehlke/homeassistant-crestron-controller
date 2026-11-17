"""Fixtures for the CLI tests. Nothing here reaches a real device."""

from __future__ import annotations

import socket
from collections.abc import Callable, Iterator

import pytest
from cli_fakes import FakeServer


@pytest.fixture
def fake_server(
    socket_enabled: None,
) -> Iterator[Callable[[Callable[[socket.socket], None]], FakeServer]]:
    """Start scripted loopback servers, joined and checked at teardown.

    The Home Assistant test plugin blocks sockets for every test in the repo;
    `socket_enabled` lifts that for the tests that need a loopback server.
    """
    servers: list[FakeServer] = []

    def start(handler: Callable[[socket.socket], None]) -> FakeServer:
        server = FakeServer(handler)
        servers.append(server)
        return server

    yield start
    for server in servers:
        server.close()
