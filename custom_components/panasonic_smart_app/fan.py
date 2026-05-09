"""Support for the Panasonic dehumidifier with SAA4 gateway."""
import logging

from homeassistant.components.fan import FanEntity, FanEntityFeature

from .const import DOMAIN
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
    # pana_api = hass.data[DOMAIN].get(entry.entry_id)
    pana_api = hass.data[DOMAIN].get('api')
    appliances = pana_api.get_all_appliances()
    _LOGGER.debug('Humidifier async_setup_entry.')
    if appliances is not None:
        for appliance in appliances:
            device_type = appliance.get_device_type()
            if device_type == 4: #Dehumidifier
                async_add_entities([PanasonicDehumidifierFan(appliance)])


class PanasonicDehumidifierFan(FanEntity):
    """Representation of a Panasonic dehumidifier fan."""

    def __init__(self, api):
        """Initialize the dehumidifier device."""
        _LOGGER.debug('Humidifier __init__.')
        self._api = api
        self.device_type = self._api.get_device_type()
        self._supported_features = FanEntityFeature.PRESET_MODE
           # | FanEntityFeature.DIRECTION | FanEntityFeature.OSCILLATE
           # SUPPORT_PRESET_MODE | SUPPORT_DIRECTION | SUPPORT_OSCILLATE
        return None


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
        return True

    # @property
    # def is_on(self) -> bool | None:
    #     """Return True if entity is on."""
    #     return self._api.is_on()

    @property
    def preset_mode(self) -> str | None:
        """Return current preset mode."""
        mode = self._api.get_fan_mode()
        _LOGGER.debug("dehumidifier.preset_ mode() = %s", mode)
        return mode.title()


    @property
    def preset_modes(self) -> list[str] | None:
        """Return the list of available preset modes."""
        pana_list = self._api.get_fan_mode_list()
        ha_list = []
        for mode in pana_list:
                ha_list.append(mode.title())
        return ha_list


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
        await self._api.set_fan_mode(preset_mode.lower())

    async def async_update(self):
        """Retrieve latest state."""
        await self._api.async_update()

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
