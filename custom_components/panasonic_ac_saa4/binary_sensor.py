"""Support for Panasonic AC/ Dehumidifier binary sensors."""
import logging

from homeassistant.const import (
    CONF_ICON, CONF_NAME, CONF_TYPE, CONF_DEVICE_CLASS)
from homeassistant.components.binary_sensor import BinarySensorEntity

from .const import (
    DOMAIN,
    ATTR_TANK_FULL,
    BINARY_SENSOR_TANK_FULL,
    BINARY_SENSOR_TYPES)

_LOGGER = logging.getLogger(__name__)

async def async_setup_platform(
        hass, config, async_add_entities, discovery_info=None):
    """Old way of setting up the Panasonic climate temperature sensors.
    Can only be called when a user accidentally mentions the platform in their
    config. But even in that case it would have been ignored.
    """
    pass


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Panasonic climate binary sensors based on config_entry."""
    #pana_api = hass.data[DOMAIN].get(entry.entry_id)
    pana_api = hass.data[DOMAIN].get('api')
    appliances = pana_api.get_all_appliances()

    if appliances is not None:
        for appliance in appliances:
            device_type = appliance.get_device_type()
            sensor_type = None
            if device_type == 1: #AC
                sensor_type = None  #No binary sensors for AC currently
            elif device_type == 4: #Dehumidifier
                sensor_type = BINARY_SENSOR_TYPES
            if sensor_type is not None:
                async_add_entities([
                    PanasonicBinarySensor(appliance, sensor)
                    for sensor in sensor_type])


class PanasonicBinarySensor(BinarySensorEntity):
    """Representation of a Binary Sensor."""

    def __init__(self, api, sensor_type, name=None)->None:
        """Initialize the binary sensor."""
        self._api = api
        self.device_type = api.get_device_type()
        if self.device_type == 1: #AC
            self._sensor = None
        elif self.device_type == 4: #Dehumidifer
            self._sensor = BINARY_SENSOR_TYPES.get(sensor_type)
        if name is None:
            name = self._api.get_name()
        self._name = "{} {}".format(name, self._sensor[CONF_NAME])
        self._id = "{}.{}".format(api.get_id(), sensor_type)
        self._device_attribute = sensor_type

        _LOGGER.debug("panasonic_saa4.PanasonicBinarySensor._name=%s."
            ,self._name)

    @property
    def is_on(self):
        """Retrieve binary sensor values from API library cache."""
        _LOGGER.debug("panasonic_saa4.PanasonicBinarySensor.is_on()")
        value  = None
        if self._device_attribute == ATTR_TANK_FULL:
            value = self._api.get_tank_full()
        return  value

    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        return self._sensor[CONF_DEVICE_CLASS]

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

