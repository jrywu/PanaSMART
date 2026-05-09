"""Support for the Panasonic dehumidifier with SAA4 gateway."""
import logging

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_COORDINATOR, DOMAIN
_LOGGER = logging.getLogger(__name__)


def _normalize_ha_string(value):
    """Normalize HA service/display strings without changing non-ASCII labels."""
    if value is None:
        return None
    if hasattr(value, "value"):
        value = value.value
    value = str(value).strip()
    if value.isascii():
        return value.lower().replace("_", " ")
    return value


def _resolve_supported_mode(value, supported_modes):
    """Return a supported canonical mode from an HA value."""
    if supported_modes is None:
        return None
    if value in supported_modes:
        return value
    normalized = _normalize_ha_string(value)
    if normalized in supported_modes:
        return normalized
    return None


async def async_setup_platform(
        hass, config, async_add_entities, discovery_info=None):
    """Old way of setting up the platform.

    Can only be called when a user accidentally mentions the platform in their
    config. But even in that case it would have been ignored.
    """
    pass


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Panasonic dehumidifier based on config_entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    _LOGGER.debug('Humidifier async_setup_entry.')
    async_add_entities([
        PanasonicDehumidifierFan(coordinator, appliance)
        for appliance in coordinator.data["appliances"].values()
        if appliance.get_device_type() == 4
    ])


class PanasonicDehumidifierFan(CoordinatorEntity, FanEntity):
    """Representation of a Panasonic dehumidifier fan."""

    def __init__(self, coordinator, api):
        """Initialize the dehumidifier device."""
        _LOGGER.debug('Humidifier __init__.')
        super().__init__(coordinator)
        self._appliance_id = api.get_id()
        self.device_type = self._api.get_device_type()
        self._supported_features = FanEntityFeature.PRESET_MODE
           # | FanEntityFeature.DIRECTION | FanEntityFeature.OSCILLATE
           # SUPPORT_PRESET_MODE | SUPPORT_DIRECTION | SUPPORT_OSCILLATE
        return None

    @property
    def _api(self):
        """Return the cached appliance from the coordinator."""
        return self.coordinator.data["appliances"][self._appliance_id]

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return self._supported_features


    @property
    def name(self):
        """Return the name of the thermostat, if any."""
        return self._api.get_name()

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._api.get_id()

    @property
    def available(self):
        return (
            self.coordinator.last_update_success
            and self._appliance_id in self.coordinator.data["appliances"]
        )

    # @property
    # def is_on(self) -> bool | None:
    #     """Return True if entity is on."""
    #     return self._api.is_on()

    @property
    def preset_mode(self) -> str | None:
        """Return current preset mode."""
        mode = self._api.get_fan_mode()
        _LOGGER.debug("dehumidifier.preset_ mode() = %s", mode)
        return mode


    @property
    def preset_modes(self) -> list[str] | None:
        """Return the list of available preset modes."""
        return self._api.get_fan_mode_list()


    # async def async_turn_on(self):
    #     """Turn device on."""
    #     return await self._api.set_power('on')
    # async def async_turn_off(self):
    #     """Turn device off."""
    #     return await self._api.set_power('off')

    async def async_set_preset_mode(self, preset_mode):
        """Set preset mode."""
        _LOGGER.debug(
            "humidifier.async_set_preset_mode() mode = %s", preset_mode)
        command = _resolve_supported_mode(
            preset_mode, self._api.get_fan_mode_list())
        if command is None:
            _LOGGER.error(
                "%s async_set_preset_mode() unsupported mode: requested=%s normalized=%s supported=%s",
                self._api.get_name(),
                preset_mode,
                _normalize_ha_string(preset_mode),
                self._api.get_fan_mode_list(),
            )
            return
        try:
            return await self._api.set_fan_mode(command)
        finally:
            await self.coordinator.async_request_forced_refresh()

    @property
    def device_info(self):
        """Return a device description for device registry."""
        return {
            "identifiers": {(DOMAIN, self._api.get_id())},
            "name": self._api.get_name(),
            "manufacturer": "Panasonic",
            "model": self._api.get_model(),
            "sw_version": "0.0",
            "via_device": (DOMAIN, str(self._api.get_gwid()))
        }
