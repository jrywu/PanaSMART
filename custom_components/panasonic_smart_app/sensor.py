"""Support for Panasonic AC sensors."""
import logging

from homeassistant.const import (
    CONF_ICON, CONF_NAME, CONF_TYPE, CONF_DEVICE_CLASS, UnitOfEnergy)
from homeassistant.components.sensor import (
    RestoreSensor,
    SensorEntity,
    SensorStateClass)
from homeassistant.components.sensor.const import SensorDeviceClass
from homeassistant.helpers.entity import Entity
from homeassistant.util.unit_system import UnitSystem
from homeassistant.components.climate.const import (
     ATTR_CURRENT_HUMIDITY)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DATA_COORDINATOR,
    DOMAIN,
    ATTR_INSIDE_TEMPERATURE,
    ATTR_TARGET_TEMPERATURE,
    ATTR_OUTSIDE_TEMPERATURE,
    ATTR_TARGET_HUMIDITY,
    SENSOR_TYPE_TEMPERATURE,
    SENSOR_TYPE_HUMIDITY,
    CLIMATE_SENSOR_TYPES,
    DEHUMI_SENSOR_TYPES)

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
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    entities = []
    for appliance in coordinator.data["appliances"].values():
        entities.append(PanasonicEnergyMeterSensor(coordinator, appliance))
        device_type = appliance.get_device_type()
        sensor_type = None
        if device_type == 1: #AC
            sensor_type = CLIMATE_SENSOR_TYPES
        elif device_type == 4: #dehumidifier
            sensor_type = DEHUMI_SENSOR_TYPES
        if sensor_type is not None:
            entities.extend([
                PanasonicClimateSensor(coordinator, appliance, sensor, hass.config.units)
                for sensor in sensor_type])
    async_add_entities(entities)


class PanasonicClimateSensor(CoordinatorEntity, Entity):
    """Representation of a Sensor."""

    def __init__(self, coordinator, api, monitored_state, units:UnitSystem, name=None)->None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._appliance_id = api.get_id()
        self.device_type = api.get_device_type()
        if self.device_type == 1: #AC
            self._sensor = CLIMATE_SENSOR_TYPES.get(monitored_state)
        elif self.device_type == 4: #AC
            self._sensor = DEHUMI_SENSOR_TYPES.get(monitored_state)
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

    @property
    def _api(self):
        """Return the cached appliance from the coordinator."""
        return self.coordinator.data["appliances"][self._appliance_id]

    @property
    def available(self):
        """Return if the device is available."""
        return (
            self.coordinator.last_update_success
            and self._appliance_id in self.coordinator.data["appliances"]
        )

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
            "via_device": (DOMAIN, str(self._api.get_gwid()))
        }


class PanasonicEnergyMeterSensor(CoordinatorEntity, RestoreSensor):
    """Representation of a Panasonic energy meter sensor."""

    def __init__(self, coordinator, api)->None:
        """Initialize the energy meter sensor."""
        super().__init__(coordinator)
        self._appliance_id = api.get_id()
        self._name = "{} Energy Meter".format(api.get_name())
        self._id = "{}.energy_kwh".format(api.get_id())

    @property
    def _api(self):
        """Return the cached appliance from the coordinator."""
        return self.coordinator.data["appliances"][self._appliance_id]

    async def async_added_to_hass(self):
        """Register entity id for recorder-based completed-hour calibration."""
        await super().async_added_to_hass()
        if hasattr(self.coordinator, "register_energy_entity"):
            self.coordinator.register_energy_entity(
                self._appliance_id, self.entity_id)
        restored_data = await self.async_get_last_sensor_data()
        if restored_data is None:
            return
        if restored_data.native_unit_of_measurement not in (
                None, UnitOfEnergy.KILO_WATT_HOUR):
            return
        if (hasattr(self.coordinator, "restore_energy_kwh")
                and self.coordinator.restore_energy_kwh(
                    self._appliance_id, restored_data.native_value)):
            self.async_write_ha_state()

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._id

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def native_value(self):
        """Return cached energy meter value in kWh."""
        data = self.coordinator.data.get("power_logs", {}).get(
            self._appliance_id, {})
        return data.get("energy_kwh")

    @property
    def native_unit_of_measurement(self):
        """Return kWh as the native unit."""
        return UnitOfEnergy.KILO_WATT_HOUR

    @property
    def device_class(self):
        """Return the Home Assistant energy device class."""
        return SensorDeviceClass.ENERGY

    @property
    def state_class(self):
        """Return total-increasing state class for Energy Dashboard."""
        return SensorStateClass.TOTAL_INCREASING

    @property
    def available(self):
        """Return if the energy meter has cached power-log data."""
        return (
            self.coordinator.last_update_success
            and self._appliance_id in self.coordinator.data.get("power_logs", {})
        )

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
