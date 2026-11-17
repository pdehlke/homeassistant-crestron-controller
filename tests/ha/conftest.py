"""Home Assistant harness fixtures for the integration tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def config_dir(hass, tmp_path):
    """Point Home Assistant's config directory at a throwaway one."""
    hass.config.config_dir = str(tmp_path)
    return tmp_path
