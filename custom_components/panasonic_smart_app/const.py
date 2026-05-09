"""Constants for Panasonic."""
from datetime import timedelta

from homeassistant.const import (
    CONF_ICON,
    CONF_NAME,
    CONF_TYPE,
    CONF_DEVICE_CLASS,
)
from homeassistant.components.climate.const import (
    ATTR_CURRENT_TEMPERATURE, ATTR_CURRENT_HUMIDITY,
    ATTR_FAN_MODE, ATTR_PRESET_MODE ,  ATTR_SWING_MODE,
    HVACMode)

from homeassistant.components.sensor.const import (
    SensorDeviceClass)

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass)

from homeassistant.const import (
    ATTR_TEMPERATURE,  STATE_OFF)
import logging

DOMAIN = 'panasonic_smart_app'
DATA_API = 'api'
DATA_COORDINATOR = 'coordinator'
STATUS_UPDATE_INTERVAL = timedelta(minutes=5)

ATTR_TARGET_TEMPERATURE = 'attr_target_temperature'
ATTR_INSIDE_TEMPERATURE = 'attr_inside_temperature'
ATTR_OUTSIDE_TEMPERATURE = 'outside_temperature'
ATTR_TARGET_HUMIDITY = 'attr_target_humidity'
ATTR_TANK_FULL ='attr_tank_full'

HA_STATE_TO_PANA= {
    HVACMode.DRY: 'dry',
    HVACMode.COOL: 'cool',
    HVACMode.FAN_ONLY: 'fan',
    HVACMode.HEAT: 'heat',
    HVACMode.AUTO: 'auto',
    HVACMode.OFF: 'off',
}

PANA_TO_HA_STATE = {
    'dry': HVACMode.DRY,
    'cool': HVACMode.COOL,
    'fan': HVACMode.FAN_ONLY,
    'heat': HVACMode.HEAT,
    'auto': HVACMode.AUTO,
    'off': HVACMode.OFF,
}

HA_ATTR_TO_PANA = {
    ATTR_PRESET_MODE: 'operation_mode',
    ATTR_FAN_MODE: 'fan_mode',
    ATTR_SWING_MODE: 'swing_mode',
    ATTR_INSIDE_TEMPERATURE: 'inside_temp',
    ATTR_OUTSIDE_TEMPERATURE: 'outside_temp',
    ATTR_TARGET_TEMPERATURE: 'target_temp',
}



SENSOR_TYPE_TEMPERATURE = 'temperature'
SENSOR_TYPE_HUMIDITY = 'humidity'
BINARY_SENSOR_TANK_FULL = 'tank_full'

CLIMATE_SENSOR_TYPES = {
    ATTR_INSIDE_TEMPERATURE: {
        CONF_NAME: 'Inside Temperature',
        CONF_ICON: 'mdi:thermometer',
        CONF_TYPE: SENSOR_TYPE_TEMPERATURE,
        CONF_DEVICE_CLASS : SensorDeviceClass.TEMPERATURE,
    },
    ATTR_OUTSIDE_TEMPERATURE: {
        CONF_NAME: 'Outside Temperature',
        CONF_ICON: 'mdi:thermometer',
        CONF_TYPE: SENSOR_TYPE_TEMPERATURE,
        CONF_DEVICE_CLASS : SensorDeviceClass.TEMPERATURE,
    },
    ATTR_TARGET_TEMPERATURE: {
        CONF_NAME: 'Target Temperature',
        CONF_ICON: 'mdi:thermometer',
        CONF_TYPE: SENSOR_TYPE_TEMPERATURE,
        CONF_DEVICE_CLASS : SensorDeviceClass.TEMPERATURE,
    },
}

DEHUMI_SENSOR_TYPES = {
    ATTR_CURRENT_HUMIDITY: {
        CONF_NAME: 'Current Humidity',
        CONF_ICON: 'mdi:water-percent',
        CONF_TYPE: SENSOR_TYPE_HUMIDITY,
        CONF_DEVICE_CLASS : SensorDeviceClass.HUMIDITY,
    },
    ATTR_TARGET_HUMIDITY: {
        CONF_NAME: 'Target Humidity',
        CONF_ICON: 'mdi:thermometer',
        CONF_TYPE: SENSOR_TYPE_HUMIDITY,
        CONF_DEVICE_CLASS : SensorDeviceClass.HUMIDITY,
    },
}

BINARY_SENSOR_TYPES = {
    ATTR_TANK_FULL: {
        CONF_NAME: 'Tank is Full',
        CONF_ICON: 'mdi:cup-water',
        CONF_TYPE: BINARY_SENSOR_TANK_FULL,
        CONF_DEVICE_CLASS : BinarySensorDeviceClass.PROBLEM,
    },
}
