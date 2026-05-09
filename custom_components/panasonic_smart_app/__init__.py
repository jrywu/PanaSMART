"""Platform for the Panasonic AC support SAAnet 4 (TAISEIA 101) standard."""
import asyncio
from datetime import timedelta
import logging
import json

from aiohttp import ClientConnectionError
from async_timeout import timeout
import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, CONF_HOST
from homeassistant.exceptions import ConfigEntryNotReady
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
#from homeassistant.helpers.typing import HomeAssistantType
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import Throttle

from .panasonic_iot_tw_api import panasonic_iot_tw_api

#from . import config_flow
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


PARALLEL_UPDATES = 0
MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=60)

# List of platforms to support. There should be a matching .py file for each,
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR,
             Platform.CLIMATE, Platform.HUMIDIFIER, Platform.FAN]


CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_HOST, default='ems2.panasonic.com.tw'): cv.string,
    })
}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass, config):
    """Establish connection to Panasonic cloud server and
        discover connected devices in the specified account."""
    _LOGGER.debug("panasonic_ac_saa4.async_setup()")
    conf = config.get(DOMAIN)
    if conf is None:  #No user/passwd set in configuration.yaml.  Set api=noe and try to get user/passwd from config entry later
        hass.data.setdefault(DOMAIN, {}).update({'api': None})
        return True
    pana_api = await pana_api_setup(hass, conf[CONF_USERNAME],
                                    conf[CONF_PASSWORD], conf[CONF_HOST])
    hass.data.setdefault(DOMAIN, {}).update({'api': pana_api})

    hass.async_create_task(hass.config_entries.flow.async_init(
            DOMAIN, context={'source': SOURCE_IMPORT}, data={}
        ))
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Hello World from a config entry."""
    # Store an instance of the "connecting" class that does the work of speaking
    # with your actual devices.
    conf = entry.data
    pana_api = hass.data[DOMAIN].get('api')
    if pana_api is None:
        _LOGGER.debug("panasonic_ac_saa4.async_setup_entry(): username: %s",  conf[CONF_USERNAME])
        pana_api = await pana_api_setup(hass, conf[CONF_USERNAME],
                                        conf[CONF_PASSWORD], conf[CONF_HOST])
        hass.data.setdefault(DOMAIN, {}).update({'api': pana_api})
    hass.data.setdefault(DOMAIN, {}).update({entry.entry_id: pana_api})
    # This creates each HA object for each platform your device requires.
    # It's done by calling the `async_setup_entry` function in each platform module.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # This is called when an entry/configured device is to be removed. The class
    # needs to unload itself, and remove callbacks. See the classes for further
    # details
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    return unload_ok

#async def async_setup_entry(hass: HomeAssistantType, entry: ConfigEntry):
    #     """Establish connection to Panasonic cloud server and discover connected
    #     devices in the specified account."""
    # conf = entry.data
    # pana_api = hass.data[DOMAIN].get('api')
    # if pana_api is None:
    #     _LOGGER.debug("panasonic_ac_saa4.async_setup_entry(): username: %s",  conf[CONF_USERNAME])
    #     pana_api = await pana_api_setup(hass, conf[CONF_USERNAME],
    #                                     conf[CONF_PASSWORD], conf[CONF_HOST])
    #     hass.data.setdefault(DOMAIN, {}).update({'api': pana_api})

    # hass.data.setdefault(DOMAIN, {}).update({entry.entry_id: pana_api})
    # for component in COMPONENT_TYPES:
    #     hass.async_create_task(
    #         hass.config_entries.async_forward_entry_setup(entry, component))
    # return True


# async def async_unload_entry(hass, config_entry):
#     """Unload a config entry."""
#     await asyncio.wait([
#         hass.config_entries.async_forward_entry_unload(config_entry, component)
#         for component in COMPONENT_TYPES
#     ])
#     # hass.data[DOMAIN].pop(config_entry.entry_id)
#     if not hass.data[DOMAIN]:
#         hass.data.pop(DOMAIN)
#     return True


async def pana_api_setup(hass, username, password, host):
    """Create a Panasnoic SAA4  instance only once."""
    _LOGGER.debug("panasonic_ac_saa4.pana_api_setup()")

    pana_api = panasonic_iot_tw_api(True)
    appliances = await pana_api.init(
                    username, password,
                    async_get_clientsession(hass), host)

    await pana_api.async_update()
    if appliances is None:
        _LOGGER.error('Got nothing from Panasonic SAA4 interface.')

    return pana_api
