"""Constants for Panasonic."""
from homeassistant.const import (
    CONF_ICON,
    CONF_NAME,
    CONF_TYPE,
    CONF_DEVICE_CLASS,
    DEVICE_CLASS_HUMIDITY,
    DEVICE_CLASS_TEMPERATURE,
)
from homeassistant.components.climate.const import (
    ATTR_CURRENT_TEMPERATURE, ATTR_CURRENT_HUMIDITY,
    ATTR_FAN_MODE, ATTR_PRESET_MODE ,  ATTR_SWING_MODE,
    HVAC_MODE_OFF, HVAC_MODE_HEAT, HVAC_MODE_COOL,
    HVAC_MODE_AUTO, HVAC_MODE_DRY,  HVAC_MODE_FAN_ONLY, HVAC_MODES)
from homeassistant.components.binary_sensor import (
    DEVICE_CLASS_PROBLEM,  DEVICE_CLASS_POWER)

from homeassistant.const import (
    ATTR_TEMPERATURE,  STATE_OFF)
import logging

DOMAIN = 'panasonic_ac_saa4'

ATTR_TARGET_TEMPERATURE = 'attr_target_temperature'
ATTR_INSIDE_TEMPERATURE = 'attr_inside_temperature'
ATTR_OUTSIDE_TEMPERATURE = 'outside_temperature'
ATTR_TARGET_HUMIDITY = 'attr_target_humidity'
ATTR_TANK_FULL ='attr_tank_full'

HA_STATE_TO_PANA= {
    HVAC_MODE_DRY: 'dry',
    HVAC_MODE_COOL: 'cool',
    HVAC_MODE_FAN_ONLY: 'fan',
    HVAC_MODE_HEAT: 'heat',
    HVAC_MODE_AUTO: 'auto',
    HVAC_MODE_OFF: 'off',
}

PANA_TO_HA_STATE = {
    'dry': HVAC_MODE_DRY,
    'cool': HVAC_MODE_COOL,
    'fan': HVAC_MODE_FAN_ONLY,
    'cool': HVAC_MODE_COOL,
    'heat': HVAC_MODE_HEAT,
    'auto': HVAC_MODE_AUTO,
    'off': HVAC_MODE_OFF,
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

TEMPERATURE_SENSOR_TYPES = {
    ATTR_INSIDE_TEMPERATURE: {
        CONF_NAME: 'Inside Temperature',
        CONF_ICON: 'mdi:thermometer',
        CONF_TYPE: SENSOR_TYPE_TEMPERATURE,
        CONF_DEVICE_CLASS : DEVICE_CLASS_TEMPERATURE,
    },
    ATTR_OUTSIDE_TEMPERATURE: {
        CONF_NAME: 'Outside Temperature',
        CONF_ICON: 'mdi:thermometer',
        CONF_TYPE: SENSOR_TYPE_TEMPERATURE,
        CONF_DEVICE_CLASS : DEVICE_CLASS_TEMPERATURE,
    },
    ATTR_TARGET_TEMPERATURE: {
        CONF_NAME: 'Target Temperature',
        CONF_ICON: 'mdi:thermometer',
        CONF_TYPE: SENSOR_TYPE_TEMPERATURE,
        CONF_DEVICE_CLASS : DEVICE_CLASS_TEMPERATURE,
    },
}

HUMIDITY_SENSOR_TYPES = {
    ATTR_CURRENT_HUMIDITY: {
        CONF_NAME: 'Current Humidity',
        CONF_ICON: 'mdi:water-percent',
        CONF_TYPE: SENSOR_TYPE_HUMIDITY,
        CONF_DEVICE_CLASS : DEVICE_CLASS_HUMIDITY,
    },
    ATTR_TARGET_HUMIDITY: {
        CONF_NAME: 'Target Humidity',
        CONF_ICON: 'mdi:thermometer',
        CONF_TYPE: SENSOR_TYPE_HUMIDITY,
        CONF_DEVICE_CLASS : DEVICE_CLASS_HUMIDITY,
    },
}

BINARY_SENSOR_TYPES = {
    ATTR_TANK_FULL: {
        CONF_NAME: 'Tank is Full',
        CONF_ICON: 'mdi:cup-water',
        CONF_TYPE: BINARY_SENSOR_TANK_FULL,
        CONF_DEVICE_CLASS : DEVICE_CLASS_PROBLEM,
    },
}

