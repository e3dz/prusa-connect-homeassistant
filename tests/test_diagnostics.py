"""Diagnostics leave out the token, the server's address and what identifies a machine."""

from __future__ import annotations

import json

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import get_diagnostics_for_config_entry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from .conftest import TOKEN, URL


async def test_diagnostics(
    hass: HomeAssistant, hass_client: ClientSessionGenerator, setup_integration: MockConfigEntry
) -> None:
    result = await get_diagnostics_for_config_entry(hass, hass_client, setup_integration)
    text = json.dumps(result)
    assert TOKEN not in text
    assert URL not in text
    assert "connect.local" not in text
    assert "DEMO-01" not in text
    assert "10:9c:70" not in text
    assert result["server_version"] == "1.2.3"
    assert len(result["devices"]) == 5
    assert result["devices"][0]["state"]["/network/lan_mac"] == "**REDACTED**"
    assert result["cameras"][0]["name"] == "cam-demo-01"
