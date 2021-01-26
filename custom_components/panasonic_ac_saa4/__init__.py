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
from homeassistant.helpers.typing import HomeAssistantType
from homeassistant.util import Throttle
from .panasonic_ac_saa4_api import PanasonicSAA4Api

from . import config_flow

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


PARALLEL_UPDATES = 0
MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=60)

COMPONENT_TYPES = ['climate', 'sensor', 'binary_sensor']

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

async def async_setup_entry(hass: HomeAssistantType, entry: ConfigEntry):
    """Establish connection to Panasonic cloud server and discover connected
        devices in the specified account."""
    conf = entry.data
    _LOGGER.debug("panasonic_ac_saa4.async_setup_entry(): username: %s",  conf[CONF_USERNAME])
    pana_api = hass.data[DOMAIN].get('api')
    if pana_api is None:
        pana_api = await pana_api_setup(hass, conf[CONF_USERNAME],
                                        conf[CONF_PASSWORD], conf[CONF_HOST])
        hass.data.setdefault(DOMAIN, {}).update({'api': pana_api})

    hass.data.setdefault(DOMAIN, {}).update({entry.entry_id: pana_api})
    for component in COMPONENT_TYPES:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, component))
    return True


async def async_unload_entry(hass, config_entry):
    """Unload a config entry."""
    await asyncio.wait([
        hass.config_entries.async_forward_entry_unload(config_entry, component)
        for component in COMPONENT_TYPES
    ])
    # hass.data[DOMAIN].pop(config_entry.entry_id)
    if not hass.data[DOMAIN]:
        hass.data.pop(DOMAIN)
    return True


async def pana_api_setup(hass, username, password, host):
    """Create a Panasnoic SAA4  instance only once."""
    _LOGGER.debug("panasonic_ac_saa4.pana_api_setup()")

    pana_api = PanasonicSAA4Api(True)
    appliances = await pana_api.init(
                    username, password,
                    hass.helpers.aiohttp_client.async_get_clientsession(), host)
    await pana_api.async_update()
    if appliances is None:
        _LOGGER.error('Got nothing from Panasonic SAA4 interface.')

    return pana_api
