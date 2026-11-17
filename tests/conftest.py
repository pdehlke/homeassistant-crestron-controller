"""Shared fixtures. The fake processor is a real TCP server on 127.0.0.1."""

from __future__ import annotations

import asyncio

import pytest

from tests.fake_processor import FakeProcessor


@pytest.fixture
async def processor(socket_enabled):
    # The Home Assistant test harness blocks sockets by default and allows
    # 127.0.0.1 only once they are enabled; the fake listens there and nowhere else.
    fake = FakeProcessor()
    fake.port = await fake.start()
    yield fake
    await fake.stop()


async def wait_for(predicate, timeout: float = 5.0, interval: float = 0.02) -> None:
    """Poll until predicate() is true, failing the test on timeout."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            raise AssertionError("condition not met before timeout")
        await asyncio.sleep(interval)
