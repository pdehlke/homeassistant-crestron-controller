"""A scripted TCP server on 127.0.0.1 for the CLI tests.

Nothing in these tests reaches a real device. Each fake server listens on an
ephemeral loopback port and runs one handler against one connection.
"""

from __future__ import annotations

import socket
import threading
from collections.abc import Callable
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


class FakeServer:
    def __init__(self, handler: Callable[[socket.socket], None]) -> None:
        self._listener = socket.create_server(("127.0.0.1", 0))
        self.port = self._listener.getsockname()[1]
        self.error: BaseException | None = None
        self._thread = threading.Thread(target=self._run, args=(handler,), daemon=True)
        self._thread.start()

    def _run(self, handler: Callable[[socket.socket], None]) -> None:
        self._listener.settimeout(10)
        try:
            conn, _ = self._listener.accept()
        except OSError as err:
            self.error = err
            return
        with conn:
            conn.settimeout(10)
            try:
                handler(conn)
            except BaseException as err:  # surfaced by close() in the test thread
                self.error = err

    def close(self) -> None:
        self._thread.join(timeout=15)
        self._listener.close()
        if self.error is not None:
            raise self.error


def read_line(conn: socket.socket) -> str:
    """Read one CRLF-terminated line the client sent."""
    buf = b""
    while not buf.endswith(b"\r\n"):
        try:
            chunk = conn.recv(1)
        except ConnectionResetError:
            # The client is allowed to hang up as soon as it has its answer.
            break
        if not chunk:
            break
        buf += chunk
    return buf.decode("latin-1").strip()
