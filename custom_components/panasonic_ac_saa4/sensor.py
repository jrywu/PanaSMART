"""Support for Panasonic SMART AC/dehumidifier sensors."""
import logging

from homeassistant.const import (
    CONF_ICON, CONF_NAME, CONF_TYPE, CONF_DEVICE_CLASS)
from homeassistant.helpers.entity import Entity
from homeassistant.util.unit_system import UnitSystem
from homeassistant.components.climate.const import (
     ATTR_CURRENT_HUMIDITY)

from .const import (
    DOMAIN,
    ATTR_INSIDE_TEMPERATURE,
    ATTR_TARGET_TEMPERATURE,
    ATTR_OUTSIDE_TEMPERATURE,
    ATTR_TARGET_HUMIDITY,
    SENSOR_TYPE_TEMPERATURE,
    SENSOR_TYPE_HUMIDITY,
    TEMPERATURE_SENSOR_TYPES,
    HUMIDITY_SENSOR_TYPES)

_LOGGER = logging.getLogger(__name__)

AVERAGE_TIMES = 10 # running average times for temperature radings

async def async_setup_platform(
        hass, config, async_add_entities, discovery_info=None):
    """Old way of setting up the Panasonic climate temperature sensors.
    Can only be called when a user accidentally mentions the platform in their
    config. But even in that case it would have been ignored.
    """
    pass


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Panasonic climate temperature sensors based on config_entry."""
    #pana_api = hass.data[DOMAIN].get(entry.entry_id)
    pana_api = hass.data[DOMAIN].get('api')
    appliances = pana_api.get_all_appliances()

    if appliances is not None:
        for appliance in appliances:
            device_type = appliance.get_device_type()
            sensor_type = None
            if device_type == 1: #AC
                sensor_type = TEMPERATURE_SENSOR_TYPES
            elif device_type == 4: #dehumidifier
                sensor_type = HUMIDITY_SENSOR_TYPES
            if sensor_type is not None:
                async_add_entities([
                    PanasonicClimateSensor(appliance, sensor, hass.config.units)
                    for sensor in sensor_type])


class PanasonicClimateSensor(Entity):
    """Representation of a Sensor."""

    def __init__(self, api, monitored_state, units:UnitSystem, name=None)->None:
        """Initialize the sensor."""
        self._api = api
        self.device_type = api.get_device_type()
        if self.device_type == 1: #AC
            self._sensor = TEMPERATURE_SENSOR_TYPES.get(monitored_state)
        elif self.device_type == 4: #AC
            self._sensor = HUMIDITY_SENSOR_TYPES.get(monitored_state)
        if name is None:
            name = self._api.get_name()
        self._name = "{} {}".format(name, self._sensor[CONF_NAME])
        self._id = "{}.{}".format(api.get_id(), monitored_state)
        self._device_attribute = monitored_state

        self.buffer_inside_temp = []
        self.buffer_outside_temp = []

        if self._sensor[CONF_TYPE] == SENSOR_TYPE_TEMPERATURE:
            self._unit_of_measurement = units.temperature_unit
        elif self._sensor[CONF_TYPE] == SENSOR_TYPE_HUMIDITY:
            self._unit_of_measurement = '%'
        _LOGGER.debug("panasonic_saa4.PanasonicClimateSensor._name=%s."
            ,self._name)

    def get(self, key):
        """Retrieve device settings from API library cache."""
        value = None

        if key == ATTR_INSIDE_TEMPERATURE:
            value = self._api.get_inside_temperature()
            self.buffer_inside_temp.append(value)
            if AVERAGE_TIMES > 0:
                if len(self.buffer_inside_temp) > AVERAGE_TIMES:
                    del self.buffer_inside_temp[0]
                value = sum(self.buffer_inside_temp) / len(self.buffer_inside_temp)
        elif key == ATTR_OUTSIDE_TEMPERATURE:
            value = self._api.get_outside_temperature()
            self.buffer_outside_temp.append(value)
            if AVERAGE_TIMES > 0:
                if len(self.buffer_outside_temp) > AVERAGE_TIMES:
                    del self.buffer_outside_temp[0]
                value = sum(self.buffer_outside_temp) / len(self.buffer_outside_temp)
        elif key == ATTR_TARGET_TEMPERATURE:
            value = self._api.get_target_temperature()
        elif key == ATTR_CURRENT_HUMIDITY:
            value = self._api.get_current_humidity()
        elif key == ATTR_TARGET_HUMIDITY:
            value = self._api.get_target_humidity()
        else:
            _LOGGER.warning("Invalid value requested for key %s", key)
        return value

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._id
    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self._sensor[CONF_ICON]

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self.get(self._device_attribute)

    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        return self._sensor[CONF_DEVICE_CLASS]

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit_of_measurement

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
