# Data Coordinator Migration Plan

## Summary

Move Home Assistant polling from per-entity `async_update()` calls and appliance-level time checks into one shared `DataUpdateCoordinator`. This should reduce duplicated cloud calls, make polling cadence explicit, and lower the risk of Panasonic cloud rate limiting or account bans.

References:

- Official Home Assistant developer guide, [Fetching data](https://developers.home-assistant.io/docs/integration_fetching_data/): use `DataUpdateCoordinator` when one API poll can fetch data for multiple entities, then share that cached data through `CoordinatorEntity`.
- Official Home Assistant developer guide, [Entity](https://developers.home-assistant.io/docs/core/entity/): entity properties should expose cached state quickly and avoid doing I/O or slow work directly.

## Current Problem

- `pana_api_setup()` calls `await pana_api.async_update()` immediately after discovery.
- Every platform entity also implements `async_update()` and calls `await self._api.async_update()`.
- Multiple HA entities wrap the same appliance:
  - AC: climate + sensors.
  - Dehumidifier: humidifier + fan + sensors + binary sensor.
- One HA refresh cycle can therefore trigger repeated appliance updates.
- `PanasonicAppliance.async_update()` currently protects itself with `ASYNC_UPDATE_INTERVAL = 300`, but this is a local guard inside each appliance object, not a single HA polling authority.
- Commit `a076905` from 2021-07-11 intentionally added this 5-minute appliance-level throttle so `async_update()` is rate-limited whether the device is on or off.
- `MIN_TIME_BETWEEN_UPDATES` and `Throttle` are imported in `__init__.py` but not actually controlling entity polling.

## Target Architecture

- Add one coordinator per config entry.
- Store coordinator in `hass.data[DOMAIN][entry.entry_id]`.
- Keep `hass.data[DOMAIN]["api"]` temporarily only if needed for backward compatibility during migration, but new platform code should read the entry-scoped coordinator.
- The coordinator update method performs exactly one shared API refresh:
  - `await pana_api.async_update()`
  - returns a stable data object containing appliances keyed by appliance id.
- Entities inherit from `CoordinatorEntity` and read cached `PanasonicAppliance` objects from `coordinator.data`.
- Entity properties must not call Panasonic cloud APIs.
- Entity command methods still call control APIs directly, then request one coordinator refresh after a successful command.

## Polling Cadence

- Use `STATUS_UPDATE_INTERVAL = timedelta(minutes=5)` for normal device status.
- Power-log polling should run in the same coordinator workflow as normal status polling.
- Each 5-minute coordinator refresh should update both normal appliance status and power-log data.
- Keep `ASYNC_UPDATE_INTERVAL = 300` in the low-level API as a defensive fallback, but do not rely on it as the main Home Assistant polling mechanism after coordinator migration.
- Treat the coordinator as the scheduler and the appliance-level interval as the safety lock:
  - The coordinator prevents duplicated HA entity polling.
  - The appliance-level lock protects direct Python API usage, accidental entity bypasses, and partial coordinator migration failures.
- Set `always_update=False` on the coordinator if the returned data can be compared safely; otherwise leave default behavior until cached data models are made comparable.

## Coordinator And Safety Lock Compatibility

The two mechanisms are not exclusive. They operate at different layers:

- `DataUpdateCoordinator` is the Home Assistant orchestration layer.
  - It decides when the integration should poll Panasonic cloud.
  - It shares one cached refresh result with all HA entities.
  - It prevents climate, humidifier, fan, sensor, and binary sensor entities from each triggering their own cloud update.
- `ASYNC_UPDATE_INTERVAL` is the low-level appliance protection layer.
  - It refuses an appliance status refresh when that same appliance was refreshed less than 300 seconds ago.
  - It remains useful outside Home Assistant, especially for `pypanasonic_ac_saa4.py` and any future direct API users.
  - It limits damage if an entity or helper accidentally calls the API directly.

Keep both, with the coordinator as the normal path. The only design caveat is command refresh:

- Scheduled coordinator polling can call the normal guarded update path.
- First setup refresh should be allowed to populate state even if `last_update` was initialized recently.
- User commands may need a forced or targeted refresh after control, otherwise `coordinator.async_request_refresh()` can be swallowed by the 5-minute lock and HA may show stale state.
- Prefer adding an explicit `force=False` argument to the low-level update path rather than removing the guard:
  - `await pana_api.async_update(force=False)` for scheduled coordinator polling.
  - `await pana_api.async_update(force=True)` only for first refresh and post-command resync.
  - Keep forced refreshes rare and command-driven, not periodic.

## Implementation Plan

### 1. Constants And Storage Keys

- Add constants in `const.py`:
  - `DATA_API = "api"`
  - `DATA_COORDINATOR = "coordinator"`
  - `STATUS_UPDATE_INTERVAL = timedelta(minutes=5)` or seconds equivalent if avoiding `timedelta` in constants.
- Keep `DOMAIN = "panasonic_smart_app"`.
- Keep `PLATFORMS` in `__init__.py` unless moving platform constants is done in the same change.

### 2. Coordinator Setup

- In `__init__.py`, import:
  - `DataUpdateCoordinator`
  - `UpdateFailed`
- Replace setup flow with:
  - create `panasonic_iot_tw_api`.
  - call `await pana_api.init(...)` once for login and discovery.
  - create coordinator with `update_method=async_update_data`.
  - call `await coordinator.async_config_entry_first_refresh()`.
  - store `{DATA_API: pana_api, DATA_COORDINATOR: coordinator}` under `hass.data[DOMAIN][entry.entry_id]`.
- `async_update_data()` should:
  - call `await pana_api.async_update()`.
  - return `{appliance.get_id(): appliance for appliance in pana_api.get_all_appliances() or []}`.
  - raise `UpdateFailed` when refresh fails unexpectedly.

### 3. Platform Entity Migration

- Update `sensor.py`, `binary_sensor.py`, `climate.py`, `humidifier.py`, and `fan.py`.
- In each `async_setup_entry()`:
  - read `coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]`.
  - iterate `coordinator.data.values()` for appliances.
  - create entities with the coordinator and appliance id.
- Each entity should inherit from `CoordinatorEntity` plus its HA entity base.
- Entity constructors should store:
  - `self._appliance_id`
  - any sensor key or entity-specific metadata.
- Add a helper property:
  - `api = self.coordinator.data[self._appliance_id]`
- Replace all `self._api` reads with `self.api` reads.
- Remove entity `async_update()` methods that call `self._api.async_update()`.
- Let `CoordinatorEntity` provide polling and availability.

### 4. Command Refresh Behavior

- For control methods such as `async_set_temperature`, `async_set_humidity`, `async_set_hvac_mode`, `async_set_mode`, `async_set_fan_mode`, `async_turn_on`, and `async_turn_off`:
  - call the existing appliance control method.
  - then call `await self.coordinator.async_request_refresh()`.
- Do not call `pana_api.async_update()` directly from entities.
- If a command fails, log the failure and still request one refresh to resync local state.

### 5. Power Log Compatibility

- Implement power-log polling according to `docs/POWER_LOG.md`.
- Keep exactly one periodic coordinator per config entry.
- Each scheduled coordinator refresh should update normal appliance status and power-log data.
- Power-log target cadence is 5 minutes.

## Test Plan

- Static checks:
  - `python -m py_compile custom_components/panasonic_smart_app/__init__.py custom_components/panasonic_smart_app/sensor.py custom_components/panasonic_smart_app/binary_sensor.py custom_components/panasonic_smart_app/climate.py custom_components/panasonic_smart_app/humidifier.py custom_components/panasonic_smart_app/fan.py`
- Setup behavior:
  - HA config entry setup performs login/discovery once.
  - Coordinator first refresh populates all appliances.
  - If first refresh fails, setup raises `ConfigEntryNotReady` or coordinator equivalent instead of creating broken entities.
- Polling behavior:
  - With AC and dehumidifier entities loaded, one scheduled coordinator refresh causes one `pana_api.async_update()` call.
  - Entity properties do not call `async_update()`.
  - Removing entity `async_update()` prevents each platform from multiplying cloud calls.
- Command behavior:
  - After a command, exactly one coordinator refresh is requested.
  - UI state updates after the coordinator refresh.
- Regression:
  - UJ ACs still expose temperature, fan, swing, and operation modes.
  - CXW and NNW-L dehumidifiers still expose humidity, preset, fan, swing, and tank state.
  - Existing direct debug script remains usable because low-level API objects still support direct `async_update()`.

## Acceptance Criteria

- There is exactly one normal status coordinator per config entry.
- No HA platform entity directly calls `pana_api.async_update()` in its own `async_update()`.
- Normal status polling interval is centralized at 5 minutes.
- Command paths request a coordinator refresh instead of bypassing the coordinator.
- Debug logs show one shared update cycle, not one cloud update per entity.
- The integration remains compatible with both YAML import setup and config-entry setup during migration.

## Assumptions

- Panasonic cloud is sensitive to repeated polling; fewer shared calls are safer than per-entity polling.
- Five minutes is the desired default for normal status updates.
- Power-log polling will be added to the shared coordinator according to `POWER_LOG.md`.
- The direct Python API remains useful outside Home Assistant and should not depend on HA coordinator classes.
