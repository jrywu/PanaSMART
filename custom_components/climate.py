"""Support for the Pansonic SMART applicances  with SAA4 gateway."""
import logging

from homeassistant.components.climate import PLATFORM_SCHEMA, ClimateEntity
from homeassistant.components.climate.const import (
    SUPPORT_SWING_MODE,
    SUPPORT_FAN_MODE,
    SUPPORT_TARGET_TEMPERATURE,
    SUPPORT_TARGET_HUMIDITY,
    SUPPORT_PRESET_MODE,
    ATTR_CURRENT_HUMIDITY,
    ATTR_CURRENT_TEMPERATURE,
    ATTR_FAN_MODES,
    ATTR_FAN_MODE,
    ATTR_PRESET_MODES,
    ATTR_PRESET_MODE,
    ATTR_HUMIDITY,
    ATTR_MAX_HUMIDITY,
    ATTR_MIN_HUMIDITY,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_HVAC_MODES,
    ATTR_HVAC_MODE,
    ATTR_SWING_MODES,
    ATTR_SWING_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ATTR_TARGET_TEMP_STEP,
    )
from homeassistant.const import (
    ATTR_TEMPERATURE, TEMP_CELSIUS, PRECISION_WHOLE)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.temperature import display_temp as show_temp
from .const import (
    DOMAIN,
    HA_STATE_TO_PANA,
    PANA_TO_HA_STATE,
    HA_ATTR_TO_PANA,
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
    """Set up Panasonic climate based on config_entry."""
    # pana_api = hass.data[DOMAIN].get(entry.entry_id)
    pana_api = hass.data[DOMAIN].get('api')
    appliances = pana_api.get_all_appliances()
    if appliances is not None:
        for appliance in appliances:
            async_add_entities([PanasonicClimate(appliance)])


class PanasonicClimate(ClimateEntity):
    """Representation of a Panasonic HVAC."""

    def __init__(self, api):
        """Initialize the climate device."""
        self._api = api
        self._supported_features =  SUPPORT_FAN_MODE \
            | SUPPORT_SWING_MODE
        self.device_type = self._api.get_device_type()
        if  self.device_type == 1: #AC
            self._supported_features |= SUPPORT_TARGET_TEMPERATURE
        elif self.device_type == 4: #Dehumidifier
            self._supported_features |= \
                (SUPPORT_TARGET_HUMIDITY | SUPPORT_PRESET_MODE)
        else: # Other appliance type not yet supported
            return None


    @property
    def supported_features(self):
        """Return the list of supported features."""
        return self._supported_features

    @property
    def state_attributes(self):
        """Return the optional state attributes."""
        data = {
            ATTR_FAN_MODE:  self.fan_mode,
            ATTR_SWING_MODE: self.swing_mode,
            }

        if self.device_type == 1:#AC
            data[ATTR_CURRENT_TEMPERATURE] = show_temp(
                    self.hass,
                    self.current_temperature,
                    self.temperature_unit,
                    self.precision,
                    )
            data[ATTR_TEMPERATURE] = show_temp(
                    self.hass,
                    self.target_temperature,
                    self.temperature_unit,
                    self.precision,
                    )
        if self.device_type == 4:#Dehumidifer
            data[ATTR_CURRENT_HUMIDITY] = self.current_humidity
            data[ATTR_HUMIDITY] = self.target_humidity
            data[ATTR_PRESET_MODE] = self.preset_mode
        return data

    @property
    def capability_attributes(self):
        """Return the capability attributes."""

        data = {
                ATTR_HVAC_MODES: self.hvac_modes,
                ATTR_FAN_MODES: self.fan_modes,
                ATTR_SWING_MODES: self.swing_modes,
                }

        if self.device_type == 1:#AC
            data[ATTR_MAX_TEMP] = show_temp(
                    self.hass,
                    self.max_temp,
                    self.temperature_unit,
                    self.precision,
                    )
            data[ATTR_MIN_TEMP] = show_temp(
                    self.hass,
                    self.min_temp,
                    self.temperature_unit,
                    self.precision,
                    )
            data[ATTR_TARGET_TEMP_STEP] = self.target_temperature_step
        if self.device_type == 4:#Dehumidifer
            data[ATTR_MIN_HUMIDITY] = self.min_humidity
            data[ATTR_MAX_HUMIDITY] = self.max_humidity
            data[ATTR_PRESET_MODES] = self.preset_modes

        return data

    @property
    def precision(self):
        """Return the precision of the system."""
        return PRECISION_WHOLE

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

    @property
    def temperature_unit(self):
        """Return the unit of measurement which this thermostat uses."""
        return TEMP_CELSIUS

    @property
    def current_temperature(self):
        """Return the current temperature."""
        if self.device_type == 1:#AC
            return self._api.get_inside_temperature()
        #elif self.device_type == 4:#Dehumidifer
        #    return 0 # self._api.get_current_humidity()
        return None

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        if self.device_type == 1:#AC
            return self._api.get_target_temperature()
        else:
            return None

    @property
    def current_humidity(self):
        """Return the current humidity."""
        if self.device_type == 4:#Dehumidifier
            return self._api.get_current_humidity()
        else:
            return None

    @property
    def target_humidity(self):
        """Return the humidity we try to reach."""
        if self.device_type == 4:#Dehumidifier
            return self._api.get_target_humidity()
        else:
            return None

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature."""
        return 1

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        if self.device_type == 1:#AC
            return self._api.get_temp_max()
        else:
            return 0

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        if self.device_type == 1:#AC
            return self._api.get_temp_min()
        else:
            return 0

    @property
    def min_humidity(self):
        """Return the minimum humidity."""
        return self._api.get_humidity_min()

    @property
    def max_humidity(self):
        """Return the maximum humidity."""
        return self._api.get_humidity_max()

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        temperature = int(kwargs.get(ATTR_TEMPERATURE))
        _LOGGER.debug(
            "async_set_temperature() temperature = %s", temperature)
        if temperature is None:
            return
        await self._api.set_target_temperature(temperature)

    async def async_set_humidity(self, humidity):
        """Set new target humidity."""
        _LOGGER.debug(
            "async_set_humidity() humidity = %s", humidity)
        await self._api.set_target_humidity(humidity)

    @property
    def preset_mode(self):
        """Return current preset mode."""
        mode = self._api.get_preset_mode()
        _LOGGER.debug("climate.preset_ mode() = %s", mode)
        return mode.title()

    @property
    def hvac_mode(self):
        """Return current operation ie. heat, cool, idle."""
        mode = self._api.get_operation_mode()
        _LOGGER.debug("climate.current_mode() = %s", mode)
        if mode in PANA_TO_HA_STATE:
            return PANA_TO_HA_STATE[mode]
        else:
            return mode.title()

    @property
    def preset_modes(self):
        """Return the list of available preset modes."""
        pana_list = self._api.get_preset_mode_list()
        ha_list = []
        for mode in pana_list:
                ha_list.append(mode.title())
        return ha_list

    @property
    def hvac_modes(self):
        """Return the list of available operation modes."""
        pana_list = self._api.get_operation_mode_list()
        ha_list = []
        for mode in pana_list:
            if mode in PANA_TO_HA_STATE:
                ha_list.append(PANA_TO_HA_STATE.get(mode))
            else:
                ha_list.append(mode.title())
        return ha_list


    async def async_turn_on(self):
        """Turn device on."""
        return await self._api.set_power('on')
    async def async_turn_off(self):
        """Turn device off."""
        return await self._api.set_power('off')

    async def async_set_preset_mode(self, preset_mode):
        """Set preset mode."""
        _LOGGER.debug(
            "climate.async_set_preset_mode() mode = %s", preset_mode)
        await self._api.set_preset_mode(preset_mode.lower())

    async def async_set_hvac_mode(self, hvac_mode):
        """Set HVAC mode."""
        _LOGGER.debug(
            "climate.async_set_operation_mode() mode = %s", hvac_mode)
        if hvac_mode in HA_STATE_TO_PANA:
            await self._api.set_operation_mode(HA_STATE_TO_PANA[hvac_mode])
        else:
            await self._api.set_operation_mode(hvac_mode.lower())

    @property
    def fan_mode(self):
        """Return the fan setting."""
        return self._api.get_fan_mode().title()

    async def async_set_fan_mode(self, fan_mode):
        """Set fan mode."""
        _LOGGER.debug("climate.async_set_fan_mode() fan_mode = %s", fan_mode)
        await self._api.set_fan_mode(fan_mode.lower())

    @property
    def fan_modes(self):
        """List of available fan modes."""
        return list(map(str.title, self._api.get_fan_mode_list()))

    @property
    def swing_mode(self):
        """Return the fan setting."""
        mode = self._api.get_swing_mode().title()
        _LOGGER.debug("climate.current_swing_mode() swing_mode = %s", mode)
        return mode

    async def async_set_swing_mode(self, swing_mode):
        """Set new target temperature."""
        await self._api.set_swing_mode(swing_mode.lower())

    @property
    def swing_modes(self):
        """List of available swing modes."""
        return list(map(str.title, self._api.get_swing_mode_list()))

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
            "via_device": self._api.get_gwid(),
        }
