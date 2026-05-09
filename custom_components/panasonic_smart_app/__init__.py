"""Platform for Panasonic Smart App Taiwan IoT support."""
import inspect
import logging

import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, CONF_HOST
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .panasonic_iot_tw_api import panasonic_iot_tw_api

from homeassistant.core import HomeAssistant
from homeassistant.const import Platform

from .const import DATA_API, DATA_COORDINATOR, DOMAIN, STATUS_UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


PARALLEL_UPDATES = 0

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
    _LOGGER.debug("panasonic_smart_app.async_setup()")
    conf = config.get(DOMAIN)
    if conf is None:  #No user/passwd set in configuration.yaml.  Set api=noe and try to get user/passwd from config entry later
        hass.data.setdefault(DOMAIN, {}).update({DATA_API: None})
        return True
    pana_api = await pana_api_setup(hass, conf[CONF_USERNAME],
                                    conf[CONF_PASSWORD], conf[CONF_HOST])
    hass.data.setdefault(DOMAIN, {}).update({DATA_API: pana_api})

    hass.async_create_task(hass.config_entries.flow.async_init(
            DOMAIN, context={'source': SOURCE_IMPORT}, data={}
        ))
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Panasonic Smart App from a config entry."""
    conf = entry.data
    pana_api = hass.data.setdefault(DOMAIN, {}).get(DATA_API)
    if pana_api is None:
        _LOGGER.debug("panasonic_smart_app.async_setup_entry(): username: %s", conf[CONF_USERNAME])
        pana_api = await pana_api_setup(hass, conf[CONF_USERNAME],
                                        conf[CONF_PASSWORD], conf[CONF_HOST])
        hass.data[DOMAIN][DATA_API] = pana_api

    coordinator = PanasonicDataUpdateCoordinator(hass, pana_api)
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = {
        DATA_API: pana_api,
        DATA_COORDINATOR: coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # This is called when an entry/configured device is to be removed. The class
    # needs to unload itself, and remove callbacks. See the classes for further
    # details
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)

    return unload_ok

async def pana_api_setup(hass, username, password, host):
    """Create a Panasonic Smart App API instance only once."""
    _LOGGER.debug("panasonic_smart_app.pana_api_setup()")

    pana_api = panasonic_iot_tw_api(True)
    appliances = await pana_api.init(
                    username, password,
                    async_get_clientsession(hass), host)

    if appliances is None:
        _LOGGER.error('Got nothing from Panasonic Smart App interface.')

    return pana_api


class PanasonicDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator that centralizes Panasonic cloud status polling."""

    def __init__(self, hass: HomeAssistant, pana_api: panasonic_iot_tw_api) -> None:
        """Initialize the coordinator."""
        self.api = pana_api
        self._force_next_update = True
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=STATUS_UPDATE_INTERVAL,
        )

    async def _async_update_data(self):
        """Fetch status for all appliances once and share it with entities."""
        force = self._force_next_update
        try:
            await self._async_update_api(force)
        except Exception as err:
            raise UpdateFailed(f"Panasonic Smart App update failed: {err}") from err
        self._force_next_update = False

        return {
            appliance.get_id(): appliance
            for appliance in self.api.get_all_appliances() or []
        }

    async def async_request_forced_refresh(self) -> None:
        """Request one refresh that bypasses the appliance-level safety lock."""
        self._force_next_update = True
        await self.async_request_refresh()

    async def _async_update_api(self, force: bool) -> None:
        """Refresh through the newest force path when available."""
        if force:
            appliances = self.api.get_all_appliances() or []
            if appliances and all(_supports_force(appliance.async_update) for appliance in appliances):
                for appliance in appliances:
                    await appliance.async_update(force=True)
                return

            _LOGGER.warning(
                "Panasonic appliance API does not support forced refresh yet; "
                "falling back to guarded refresh. Update panasonic_iot_tw_api "
                "to bypass the 5-minute lock after commands."
            )

        await self.api.async_update()


def _supports_force(method) -> bool:
    """Return True if a callable accepts the force keyword."""
    return "force" in inspect.signature(method).parameters
