"""Support for the Pansonic dehumidifier with SAA4 gateway."""
import logging

from homeassistant.components.humidifier import PLATFORM_SCHEMA, HumidifierEntity
from homeassistant.components.humidifier.const import (
    HumidifierEntityFeature,
    )
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import (
    DATA_COORDINATOR,
    DOMAIN,
    )

_LOGGER = logging.getLogger(__name__)


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
    async_add_entities([
        PanasonicDehumidifier(coordinator, appliance)
        for appliance in coordinator.data["appliances"].values()
        if appliance.get_device_type() == 4
    ])


class PanasonicDehumidifier(CoordinatorEntity, HumidifierEntity):
    """Representation of a Panasonic dehumidifier."""

    def __init__(self, coordinator, api):
        """Initialize the dehumidifier device."""
        super().__init__(coordinator)
        self._appliance_id = api.get_id()
        self.device_type = self._api.get_device_type()
        self._supported_features = HumidifierEntityFeature.MODES

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
        """Return if the device is available."""
        return (
            self.coordinator.last_update_success
            and self._appliance_id in self.coordinator.data["appliances"]
        )


    @property
    def current_humidity(self):
        """Return the current humidity."""
        return self._api.get_current_humidity()

    @property
    def target_humidity(self):
        """Return the humidity we try to reach."""
        return self._api.get_target_humidity()

    @property
    def min_humidity(self):
        """Return the minimum humidity."""
        return self._api.get_humidity_min()

    @property
    def max_humidity(self):
        """Return the maximum humidity."""
        return self._api.get_humidity_max()

    async def async_set_humidity(self, humidity):
        """Set new target humidity."""
        _LOGGER.debug(
            "async_set_humidity() humidity = %s", humidity)
        try:
            return await self._api.set_target_humidity(humidity)
        finally:
            await self.coordinator.async_request_forced_refresh()

    @property
    def is_on(self):
        """Return True if entity is on."""
        return self._api.is_on()

    @property
    def mode(self):
        """Return current preset mode."""
        mode = self._api.get_preset_mode()
        _LOGGER.debug("dehumidifier.preset_ mode() = %s", mode)
        return mode.title()


    @property
    def available_modes(self):
        """Return the list of available preset modes."""
        pana_list = self._api.get_preset_mode_list()
        ha_list = []
        for mode in pana_list:
                ha_list.append(mode.title())
        return ha_list


    async def async_turn_on(self):
        """Turn device on."""
        try:
            return await self._api.set_power('on')
        finally:
            await self.coordinator.async_request_forced_refresh()

    async def async_turn_off(self):
        """Turn device off."""
        try:
            return await self._api.set_power('off')
        finally:
            await self.coordinator.async_request_forced_refresh()

    async def async_set_mode(self, mode):
        """Set preset mode."""
        _LOGGER.debug(
            "humidifier.async_set_preset_mode() mode = %s", mode)
        try:
            return await self._api.set_preset_mode(mode.lower())
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
