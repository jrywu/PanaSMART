"""Platform for Panasonic Smart App Taiwan IoT support."""
import inspect
import logging
from datetime import datetime, timedelta

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
        self._last_status_refresh = None
        self._last_power_log_refresh = None
        self._power_logs = {}
        self._energy_entity_ids = {}
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=STATUS_UPDATE_INTERVAL,
        )

    async def _async_update_data(self):
        """Fetch status and power-log data once and share it with entities."""
        force = self._force_next_update
        try:
            await self._async_update_status(force)
        except Exception as err:
            raise UpdateFailed(f"Panasonic Smart App update failed: {err}") from err
        try:
            await self._async_update_power_log()
        except Exception:
            _LOGGER.exception("Panasonic Smart App power-log update failed.")
        self._force_next_update = False

        return {
            "appliances": {
                appliance.get_id(): appliance
                for appliance in self.api.get_all_appliances() or []
            },
            "power_logs": self._power_logs,
        }

    def register_energy_entity(self, appliance_id, entity_id) -> None:
        """Register the HA entity id used for completed-hour calibration."""
        self._energy_entity_ids[appliance_id] = entity_id

    def restore_energy_kwh(self, appliance_id, energy_kwh) -> bool:
        """Restore cached appliance and coordinator energy meter state."""
        appliances = {
            appliance.get_id(): appliance
            for appliance in self.api.get_all_appliances() or []
        }
        appliance = appliances.get(appliance_id)
        if appliance is None or not appliance.restore_energy_kwh(energy_kwh):
            return False
        existing_power_log = self._power_logs.get(appliance_id, {})
        self._power_logs[appliance_id] = {
            **existing_power_log,
            "energy_kwh": appliance.get_energy_kwh(),
            "delta_kwh": appliance.get_power_log_delta_kwh(),
            "current_hour_kwh": appliance.get_power_log_current_hour_kwh(),
            "hour_index": appliance.current_hour_index,
            "raw": appliance.power_log_raw,
            "last_update": appliance.get_power_log_last_update(),
        }
        return True

    async def async_request_forced_refresh(self) -> None:
        """Request one refresh that bypasses the appliance-level safety lock."""
        self._force_next_update = True
        await self.async_request_refresh()

    async def _async_update_status(self, force: bool) -> None:
        """Refresh appliance status and remember the successful refresh time."""
        await self._async_update_api(force)
        self._last_status_refresh = datetime.now()

    async def _async_update_power_log(self) -> None:
        """Refresh cached appliance energy meter data from Panasonic power logs."""
        now = datetime.now()
        for appliance in self.api.get_all_appliances() or []:
            try:
                updated = await appliance.async_update_power_log(
                    unit="hour",
                    from_date=now.date(),
                    max_num=24,
                )
            except Exception:
                _LOGGER.exception(
                    "Power-log refresh failed for %s.", appliance.get_name())
                continue
            if not updated or appliance.get_energy_kwh() is None:
                continue
            appliance.queue_completed_day_calibration(now)
            await self._async_calibrate_power_log(appliance)
            await self._async_calibrate_power_log_day(appliance, now)
            self._power_logs[appliance.get_id()] = {
                "energy_kwh": appliance.get_energy_kwh(),
                "delta_kwh": appliance.get_power_log_delta_kwh(),
                "current_hour_kwh": appliance.get_power_log_current_hour_kwh(),
                "hour_index": appliance.current_hour_index,
                "raw": appliance.power_log_raw,
                "last_update": appliance.get_power_log_last_update(),
            }
        self._last_power_log_refresh = datetime.now()

    async def _async_calibrate_power_log(self, appliance) -> None:
        """Calibrate missed completed-hour kWh exactly once when HA data exists."""
        entity_id = self._energy_entity_ids.get(appliance.get_id())
        if entity_id is None:
            return
        for completed_hour_key in appliance.get_pending_power_log_calibrations():
            panasonic_kwh = appliance.get_completed_hour_power_log_kwh(
                completed_hour_key)
            if panasonic_kwh is None:
                continue
            ha_kwh = await self._async_get_ha_completed_hour_energy_kwh(
                entity_id, completed_hour_key)
            if ha_kwh is None:
                continue
            missing_kwh = panasonic_kwh - ha_kwh
            appliance.apply_power_log_calibration(completed_hour_key, missing_kwh)

    async def _async_calibrate_power_log_day(self, appliance, now) -> None:
        """Calibrate missed completed-day kWh exactly once when HA data exists."""
        if now.hour != 0 or now.minute < 5:
            return
        entity_id = self._energy_entity_ids.get(appliance.get_id())
        if entity_id is None:
            return
        for completed_day_key in appliance.get_pending_power_log_day_calibrations():
            panasonic_kwh = await appliance.get_completed_day_power_log_kwh(
                completed_day_key)
            if panasonic_kwh is None:
                continue
            ha_kwh = await self._async_get_ha_completed_day_energy_kwh(
                entity_id, completed_day_key)
            if ha_kwh is None:
                continue
            missing_kwh = panasonic_kwh - ha_kwh
            appliance.apply_power_log_day_calibration(
                completed_day_key, missing_kwh)

    async def _async_get_ha_completed_hour_energy_kwh(
            self, entity_id, completed_hour_key):
        """Read HA persisted energy increase for one completed hour."""
        try:
            start = datetime.strptime(completed_hour_key, "%Y-%m-%dT%H")
        except ValueError:
            return None
        end = start + timedelta(hours=1)
        return await self._async_get_ha_energy_kwh(entity_id, start, end)

    async def _async_get_ha_completed_day_energy_kwh(
            self, entity_id, completed_day_key):
        """Read HA persisted energy increase for one completed day."""
        try:
            start = datetime.strptime(completed_day_key, "%Y-%m-%d")
        except ValueError:
            return None
        end = start + timedelta(days=1)
        return await self._async_get_ha_energy_kwh(entity_id, start, end)

    async def _async_get_ha_energy_kwh(self, entity_id, start, end):
        """Read HA persisted energy increase for a time range."""
        data = {
            "statistic_ids": [entity_id],
            "start_time": start.isoformat(sep=" "),
            "end_time": end.isoformat(sep=" "),
            "period": "5minute",
            "types": ["change", "state", "sum"],
            "units": {"energy": "kWh"},
        }
        try:
            response = await self.hass.services.async_call(
                "recorder",
                "get_statistics",
                data,
                blocking=True,
                return_response=True,
            )
        except TypeError:
            return None
        except Exception:
            _LOGGER.debug(
                "Unable to read recorder statistics for %s.", entity_id,
                exc_info=True)
            return None

        rows = _extract_statistic_rows(response, entity_id)
        changes = []
        states = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            if row.get("change") is not None:
                try:
                    changes.append(float(row["change"]))
                except (TypeError, ValueError):
                    pass
            state = row.get("state")
            if state is None:
                state = row.get("sum")
            if state is not None:
                try:
                    states.append(float(state))
                except (TypeError, ValueError):
                    pass
        if changes:
            return max(sum(changes), 0)
        if len(states) >= 2:
            return max(states[-1] - states[0], 0)
        return None

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


def _extract_statistic_rows(response, entity_id):
    """Extract recorder statistic rows from common HA service response shapes."""
    if not isinstance(response, dict):
        return []
    if isinstance(response.get(entity_id), list):
        return response[entity_id]
    statistics = response.get("statistics")
    if isinstance(statistics, dict) and isinstance(statistics.get(entity_id), list):
        return statistics[entity_id]
    for value in response.values():
        if isinstance(value, dict) and isinstance(value.get(entity_id), list):
            return value[entity_id]
    return []
