"""The chamber light of a printer that has one, such as the CORE One."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, LightEntity
from homeassistant.components.light.const import ColorMode
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .coordinator import PrusaConnectConfigEntry, PrusaConnectCoordinator
from .entity import PrusaConnectEntity, async_add_entities_as_found
from .helpers import command
from .library import Device

PARALLEL_UPDATES = 1

VERB_SET_CHAMBER_LED = "core.command.set_chamber_led_intensity"
ARG_INTENSITY = "chamber.led_intensity"
# The intensity, if a printer reports it in its state tree. The CORE One on
# firmware 8.0 does not, so the light then shows what was last sent.
STATE_INTENSITY = "/chamber/led_intensity"


def _to_percent(brightness: int) -> int:
    return max(1, min(100, round(brightness * 100 / 255)))


def _to_brightness(percent: float) -> int:
    return max(0, min(255, round(percent * 255 / 100)))


def _entities(coordinator: PrusaConnectCoordinator, device: Device) -> Iterator[Entity]:
    if device.may("operate") and device.supports(VERB_SET_CHAMBER_LED):
        yield ChamberLight(coordinator, device)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PrusaConnectConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the chamber lights."""
    async_add_entities_as_found(entry, async_add_entities, _entities)


class ChamberLight(PrusaConnectEntity, LightEntity, RestoreEntity):
    """The chamber LEDs, dimmable from 1 to 100 %."""

    _attr_translation_key = "chamber_light"
    _attr_color_mode = ColorMode.BRIGHTNESS

    def __init__(self, coordinator: PrusaConnectCoordinator, device: Device) -> None:
        super().__init__(coordinator, device, "chamber_light")
        self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
        # What was last sent, for a printer that does not report it.
        self._sent: int | None = None
        # The brightness to come back to after an off.
        self._last_on = 255

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state == STATE_ON:
            self._sent = last.attributes.get(ATTR_BRIGHTNESS) or 255
            self._last_on = self._sent

    @property
    def _reported(self) -> int | None:
        device = self.device
        value = device.state.get(STATE_INTENSITY) if device else None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return _to_brightness(value)

    @property
    def assumed_state(self) -> bool:
        return self._reported is None

    @property
    def brightness(self) -> int | None:
        reported = self._reported
        return reported if reported is not None else self._sent

    @property
    def is_on(self) -> bool | None:
        brightness = self.brightness
        return None if brightness is None else brightness > 0

    @command
    async def async_turn_on(self, /, **kwargs: Any) -> None:
        brightness = kwargs.get(ATTR_BRIGHTNESS, self._last_on) or self._last_on
        await self._send(_to_percent(brightness))
        self._sent = _to_brightness(_to_percent(brightness))
        self._last_on = self._sent
        self.async_write_ha_state()

    @command
    async def async_turn_off(self, /, **kwargs: Any) -> None:
        await self._send(0)
        self._sent = 0
        self.async_write_ha_state()

    async def _send(self, percent: int) -> None:
        await self.coordinator.client.command(self.device_id, VERB_SET_CHAMBER_LED, {ARG_INTENSITY: percent})
