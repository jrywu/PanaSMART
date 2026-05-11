# Power Log And Status Five-Minute Coordinator Plan

**Target document:** `docs/POWER_LOG.md`

## Summary

Power-log support uses the same `PanasonicDataUpdateCoordinator` that already owns normal status polling. Every 5-minute coordinator cycle refreshes both datasets:

- Normal appliance status.
- Panasonic power-log data, exposed to Home Assistant as energy meter data in kWh.

Do not add a separate power-log coordinator. Do not add per-entity cloud polling. Home Assistant energy meter sensors read cached kWh values from the same shared coordinator data model. The integration should add one Home Assistant energy meter entity for each discovered appliance.

## References

- `docs/DATA_COORDINATOR.md`: normal coordinator pattern and appliance-level safety lock.
- Official Home Assistant developer guide, [Fetching data](https://developers.home-assistant.io/docs/integration_fetching_data/): use `DataUpdateCoordinator` to centralize API polling shared by entities.
- Official Home Assistant developer guide, [Sensor entity](https://developers.home-assistant.io/docs/core/entity/sensor/): energy sensors should expose the right device class, state class, and unit.

## Polling Rule

- Refresh normal appliance status every 5 minutes.
- Refresh power-log data every 5 minutes.
- Run both refreshes from the same `DataUpdateCoordinator` cycle.
- Entity property reads must never call Panasonic cloud.
- Entity `async_update()` methods must not call Panasonic cloud.
- Command methods may still call control APIs, then request a forced coordinator refresh for status resync.

## Panasonic Power Log API

Panasonic area power logs are fetched from:

```text
POST https://ems2.panasonic.com.tw/api/PowerGetCTAreaLog
```

Payload shape:

```python
{
    "gw_id": "80D21D321A9F",
    "area_ids": [0],
    "from": "YYYY/MM/DD",
    "unit": "month" | "day" | "hour",
    "max_num": 12 | 30 | 24,
}
```

Response shape:

```python
{
    "state": "success",
    "Areas": [
        {
            "area_id": 0,
            "nickname": "全部",
            "kwh": [0.0, 0.3, 0.1],
        }
    ],
}
```

Supported units:

- `unit="month"`:
  - Use `max_num=12`.
  - Returns monthly kWh buckets.
- `unit="day"`:
  - Use `max_num=30`.
  - Returns daily kWh buckets.
- `unit="hour"`:
  - Use `max_num=24`.
  - Returns hourly kWh buckets.

Reject unsupported units locally before network call.

## Energy Sensor Strategy

- Use a 5-minute delta accumulator for v1:
  - Request `unit="hour"`.
  - Use `from=today`.
  - Use `max_num=24`.
  - Read only the current hour bucket for normal 5-minute updates.
  - Compute `delta_kwh = current_hour_kwh - previous_current_hour_kwh`.
  - Add only positive same-hour deltas to the cached HA energy meter reading.
  - Expose the cached HA energy meter reading as the sensor value.
- Do not use rolling multi-day or multi-month totals for Home Assistant Energy Dashboard:
  - Rolling windows can decrease when old buckets leave the response.
  - `TOTAL_INCREASING` must not represent a rolling total.
- Configure energy sensor properties:
  - `device_class = SensorDeviceClass.ENERGY`
  - `state_class = SensorStateClass.TOTAL_INCREASING`
  - `native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR`
  - `native_value = cached cumulative kWh`
- Do not reset the HA energy meter value at midnight:
  - Keep `energy_kwh` monotonic/incremental across days.
  - Reset only the current-hour baseline and date tracking fields when the local date changes.
  - Home Assistant `TOTAL_INCREASING` expects an increasing meter, not a daily-only value.

## Target Architecture

Use the existing `PanasonicDataUpdateCoordinator` as the single periodic cloud scheduler. Add cached power-log fields to the shared coordinator result:

```python
{
    "appliances": {
        appliance_id: appliance,
    },
    "power_logs": {
        appliance_id: {
            "energy_kwh": float,
            "delta_kwh": float,
            "current_hour_kwh": float,
            "hour_index": int,
            "raw": dict,
            "last_update": datetime,
        },
    },
}
```

The shared coordinator owns:

- cached appliance objects.
- cached energy meter values from Panasonic power-log data.
- last normal status refresh time.
- last power-log refresh time.

## Scheduling Policy

Every coordinator tick runs at `STATUS_UPDATE_INTERVAL = timedelta(minutes=5)`.

First setup:

- Run one forced normal status refresh so entities have initial state.
- Run one power-log refresh in the same coordinator setup cycle so energy sensors have initial state when the endpoint succeeds.

Normal periodic ticks:

- Run status refresh.
- Run power-log refresh.
- Return one combined cached coordinator data object.

Example 5-minute schedule:

```text
00:00 status + power_log
00:05 status + power_log
00:10 status + power_log
00:15 status + power_log
00:20 status + power_log
00:25 status + power_log
```

## API Expansion

Expand the low-level API before adding the Home Assistant entity.

In `core.py`:

- Change `get_power_log()` to accept explicit resolution arguments:
  - `unit="hour"`
  - `from_date=None`
  - `max_num=24`
  - `retries=2`
- Accept only `"hour"`, `"day"`, and `"month"`.
- Reject unsupported units before network call.
- Build payload:

```python
{
    "gw_id": appliance.get_gwid(),
    "area_ids": [appliance.get_area_id()],
    "from": "YYYY/MM/DD",
    "unit": "hour",
    "max_num": 24,
}
```

In `PanasonicAppliance.py`:

- Keep one public `get_power_log()` method.
- Add `async_update_power_log(unit="hour", from_date=None, max_num=24)`.
- Add cached fields:
  - `energy_kwh`
  - `previous_current_hour_kwh`
  - `current_hour_delta_kwh`
  - `current_hour_index`
  - `calibrated_hour_keys`
  - `pending_calibration_hour_keys`
  - `calibrated_day_keys`
  - `pending_day_calibration_keys`
  - `power_log_date`
  - `power_log_unit`
  - `power_log_raw`
  - `power_log_last_update`
- Add getters:
  - `get_energy_kwh()`
  - `get_power_log_delta_kwh()`
  - `get_power_log_last_update()`

## Response Parsing

Add a parser helper in the low-level API layer:

- Match the area by `area_id`.
- Extract `kwh`.
- Parse each bucket as `float`.
- Read the bucket for the current hour.
- Compare the current hour bucket with the previous current hour bucket from the last successful poll.
- Add the positive difference to the cached HA energy meter value.
- Keep the raw matching area response for diagnostics.
- Return `None` when:
  - no matching area exists.
  - `kwh` is missing.
  - any `kwh` bucket is not numeric.
  - server response is a failure state.

If parsing fails, keep the previous cached sensor value and log a warning. Do not reset the sensor to `0`, because that would create false energy history.

## Delta Accumulator Rules

- On first successful poll of a day:
  - Set `current_hour_index = now.hour`.
  - Set `previous_current_hour_kwh = kwh[current_hour_index]`.
  - Set `current_hour_delta_kwh = 0`.
  - Do not add the first current-hour bucket as a delta, because it may contain energy used before the integration started.
- On later successful polls in the same hour:
  - `current_hour_kwh = kwh[current_hour_index]`.
  - `delta_kwh = current_hour_kwh - previous_current_hour_kwh`.
  - If `delta_kwh > 0`, add it to `energy_kwh`.
  - If `delta_kwh > 0`, also add it to `current_hour_delta_kwh`.
  - If `delta_kwh <= 0`, do not subtract from `energy_kwh`; update diagnostics and keep the previous HA meter value.
  - Update `previous_current_hour_kwh = current_hour_kwh`.
- When the hour changes:
  - Switch to the new hour baseline immediately.
  - Delay completed-hour calibration until a successful poll where `now.minute >= 5`.
  - Add the completed hour key to `pending_calibration_hour_keys`.
  - Set `current_hour_index = now.hour`.
  - Set `previous_current_hour_kwh = kwh[current_hour_index]`.
  - Set `current_hour_delta_kwh = 0`.
- On local date change:
  - Keep `energy_kwh` unchanged.
  - Reset hour tracking fields from the first new-day response.
  - Clear `calibrated_hour_keys`.
  - Continue exposing one cumulative/incremental Home Assistant energy meter.

## Completed Hour Calibration

At the first successful poll at or after `xx:05`, Panasonic's previous hour bucket should be finalized. Use it to calibrate exactly once. Do not calibrate at exactly `xx:00`, because Home Assistant and Panasonic server time may not align perfectly.

- Determine the completed hour:
  - `completed_hour_index = (now.hour - 1) % 24`.
  - `completed_hour_key = YYYY-MM-DDTHH`.
- Only run calibration when:
  - `now.minute >= 5`.
  - `completed_hour_key` belongs to the hour before the current hour.
  - The current poll has valid Panasonic `kwh` data.
- Skip calibration if `completed_hour_key` is already in `calibrated_hour_keys`.
- Read the finalized Panasonic value:
  - `panasonic_completed_hour_kwh = kwh[completed_hour_index]`.
- Read Home Assistant's persisted energy meter increase for that same completed hour.
  - Prefer recorder/statistics if the completed hour statistic is available.
  - Fallback to recorder state history around the hour start/end if statistics are not available.
  - Do not use only in-memory `current_hour_delta_kwh`, because Home Assistant may have restarted during the completed hour.
- Compute:

```python
missing_kwh = panasonic_completed_hour_kwh - ha_completed_hour_energy_kwh
```

- If `missing_kwh > 0`, add it once to `energy_kwh`.
- If `missing_kwh <= 0`, do not subtract from `energy_kwh`.
- Add `completed_hour_key` to `calibrated_hour_keys` only after calibration succeeds or after deciding no correction is needed from valid HA data.
- Remove `completed_hour_key` from `pending_calibration_hour_keys` only after it is added to `calibrated_hour_keys`.

This catches missed 5-minute deltas from network disconnects, Home Assistant downtime, or coordinator failures without double-applying the same completed hour correction.

## HA History Read For Calibration

`ha_completed_hour_energy_kwh` should come from Home Assistant's persisted data, not from the integration's in-memory delta tracker.

Preferred source: Home Assistant recorder statistics for the energy meter entity.

Query shape:

```yaml
action: recorder.get_statistics
data:
  statistic_ids:
    - sensor.<appliance>_energy_meter
  start_time: "YYYY-MM-DD HH:00:00"
  end_time: "YYYY-MM-DD HH+1:00:00"
  period: 5minute
  types:
    - change
    - state
    - sum
  units:
    energy: kWh
```

For a completed hour such as `10:00:00` through `10:59:59`, prefer:

```python
ha_completed_hour_energy_kwh = sum(
    row["change"]
    for row in recorder_statistics_5minute_rows
    if row.get("change") is not None
)
```

Fallback when `change` is unavailable but state values are available:

```python
ha_completed_hour_energy_kwh = (
    last_valid_state_in_completed_hour
    - first_valid_state_in_completed_hour
)
```

Last fallback:

- Recorder state history for the energy meter entity around the completed hour start and end.
  - Use the same subtraction approach: end state minus start state.
  - Skip calibration if either boundary state is unavailable or non-numeric.

Retry behavior:

- First attempt calibration at `xx:05`.
- If recorder/statistics/history data is not ready, keep the hour in `pending_calibration_hour_keys`.
- Retry on later 5-minute polls such as `xx:10`, `xx:15`, and `xx:20`.
- Do not apply correction without valid HA persisted data.
- Do not apply correction more than once for the same `completed_hour_key`.

## Completed Day Calibration

Add a daily safety calibration at the first successful coordinator poll at or after `00:05`. This is a second layer on top of hourly calibration. It catches missed hourly corrections and limits long-term undercount after Home Assistant downtime, recorder delay, network disconnects, or Panasonic hourly bucket timing differences.

Daily calibration should calibrate **yesterday**, not the current day.

- Determine the completed day:
  - `completed_day = local_today - timedelta(days=1)`.
  - `completed_day_key = completed_day.strftime("%Y-%m-%d")`.
- Only run daily calibration when:
  - `now.hour == 0`.
  - `now.minute >= 5`.
  - `completed_day_key` is not in `calibrated_day_keys`.
  - Valid Panasonic daily kWh data exists for `completed_day_key`.
- Track retry state:
  - Add `completed_day_key` to `pending_day_calibration_keys` when it becomes eligible.
  - Keep it pending if recorder/statistics/history data is not ready.
  - Retry on later polls such as `00:10`, `00:15`, and `00:20`.
  - Move it to `calibrated_day_keys` only after valid HA persisted data was read and the correction decision was made.

Fetch Panasonic's finalized daily value with the power-log API:

```python
await appliance.get_power_log(
    unit="day",
    from_date=completed_day,
    max_num=1,
)
```

The preferred request is `from=completed_day` with `max_num=1`, because it avoids month-length and bucket-index ambiguity. If live probing shows Panasonic rejects `max_num=1`, fall back to `max_num=30` with a start date that makes `completed_day` land inside the returned window, and document the exact bucket-index mapping. If the response cannot be mapped confidently to `completed_day`, skip daily calibration and keep the day pending rather than guessing.

Read Home Assistant's persisted energy meter increase for the same completed day:

```yaml
action: recorder.get_statistics
data:
  statistic_ids:
    - sensor.<appliance>_energy_meter
  start_time: "YYYY-MM-DD 00:00:00"
  end_time: "NEXT-DAY-YYYY-MM-DD 00:00:00"
  period: 5minute
  types:
    - change
    - state
    - sum
  units:
    energy: kWh
```

Prefer summing `change` values:

```python
ha_completed_day_energy_kwh = sum(
    row["change"]
    for row in recorder_statistics_5minute_rows
    if row.get("change") is not None
)
```

Fallback to persisted meter state subtraction when `change` is unavailable:

```python
ha_completed_day_energy_kwh = (
    last_valid_state_in_completed_day
    - first_valid_state_in_completed_day
)
```

Compute:

```python
missing_kwh = panasonic_completed_day_kwh - ha_completed_day_energy_kwh
```

- If `missing_kwh > 0`, add it once to the current `energy_kwh`.
- If `missing_kwh <= 0`, do not subtract from `energy_kwh`.
- Mark `completed_day_key` calibrated after a valid persisted HA comparison says either correction was applied or no correction was needed.

Daily calibration can make the `00:05` hour look higher in Home Assistant because the correction is recorded when it is applied, not backfilled into yesterday. This is acceptable for the monotonic energy meter because it prevents undercount without decreasing the sensor. The next hourly or daily calibration may see HA higher than Panasonic for that period; the rule to never subtract prevents runaway correction.

## Coordinator Changes

Extend `PanasonicDataUpdateCoordinator` to carry both normal appliance status and cached power-log data.

Add fields:

```python
self._last_status_refresh = None
self._last_power_log_refresh = None
self._power_logs = {}
```

Add update methods:

```python
async def _async_update_status(self, force: bool) -> None:
    await self._async_update_api(force)
    self._last_status_refresh = utcnow()

async def _async_update_power_log(self) -> None:
    for appliance in self.api.get_all_appliances() or []:
        await appliance.async_update_power_log(
            unit="hour",
            from_date=date.today(),
            max_num=24,
        )
        await self._async_calibrate_completed_hours(appliance)
        await self._async_calibrate_completed_day(appliance)
        if appliance.get_energy_kwh() is not None:
            self._power_logs[appliance.get_id()] = {
                "energy_kwh": appliance.get_energy_kwh(),
                "delta_kwh": appliance.get_power_log_delta_kwh(),
                "current_hour_kwh": appliance.power_log_current_hour_kwh,
                "hour_index": appliance.current_hour_index,
                "raw": appliance.power_log_raw,
                "last_update": appliance.get_power_log_last_update(),
            }
    self._last_power_log_refresh = utcnow()
```

`_async_update_data()` should:

- Run status refresh.
- Run power-log refresh.
- Return both cached status and cached power-log data.

```python
return {
    "appliances": {
        appliance.get_id(): appliance
        for appliance in self.api.get_all_appliances() or []
    },
    "power_logs": self._power_logs,
}
```

## Entity Migration Impact

The coordinator data shape changes from:

```python
coordinator.data[appliance_id]
```

to:

```python
coordinator.data["appliances"][appliance_id]
```

Update existing climate, humidifier, fan, sensor, and binary sensor entities to use the new nested shape.

Add helper methods/properties if possible:

```python
def get_appliance(coordinator, appliance_id):
    return coordinator.data["appliances"][appliance_id]
```

## Energy Sensor Entity

Add `PanasonicEnergyMeterSensor` in `sensor.py`.

- It should inherit from `CoordinatorEntity` and `SensorEntity`.
- It should use the same shared `DATA_COORDINATOR`.
- Create one Home Assistant energy meter entity per discovered appliance.
- Entity fields:
  - `unique_id = f"{appliance_id}.energy_kwh"`
  - `name = f"{appliance.get_name()} Energy Meter"`
  - `native_value = coordinator.data["power_logs"].get(appliance_id, {}).get("energy_kwh")`
  - `native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR`
  - `device_class = SensorDeviceClass.ENERGY`
  - `state_class = SensorStateClass.TOTAL_INCREASING`
- Entity availability:
  - Available when coordinator succeeded and `appliance_id` has a cached energy kWh value.
  - Unknown/unavailable before the first successful power-log refresh is acceptable.
- Device info should match existing appliance registry identity.

## Polling And Rate Safety

- There is exactly one periodic coordinator per config entry.
- That coordinator refreshes both status and power-log data every 5 minutes.
- No power-log entity should implement `async_update()`.
- Entity properties must only read coordinator cached data.
- Run power-log refresh from the coordinator, not from entities.
- Keep status and power-log refreshes in the same coordinator workflow.
- Keep the low-level appliance status safety lock; it remains a fallback for status calls.

## Failure Behavior

- Status refresh failure:
  - Normal status entities follow coordinator availability.
  - Existing cached energy meter values remain in coordinator data.
- Power-log refresh failure:
  - Keep previous cached energy meter values.
  - Do not make climate/humidifier/fan unavailable if cached status still exists.
  - Mark or log power-log refresh failure separately.
- Unsupported unit:
  - Raise `ValueError` or return a local structured error before network call.
  - Do not retry unsupported units.

## Test Plan

- Static checks:

```bash
python -m py_compile custom_components/panasonic_smart_app/__init__.py custom_components/panasonic_smart_app/sensor.py custom_components/panasonic_smart_app/panasonic_iot_tw_api/core.py custom_components/panasonic_smart_app/panasonic_iot_tw_api/PanasonicAppliance.py
```

- API checks:
  - `get_power_log(unit="hour", from_date=today, max_num=24)` builds expected payload.
  - `get_power_log(unit="day", max_num=30)` builds expected payload.
  - `get_power_log(unit="month", max_num=12)` builds expected payload.
  - Unsupported units are rejected before network call.
  - Parser returns matching area by `area_id`.
  - Parser returns `None` for missing or invalid `kwh`.
- Coordinator checks:
  - First coordinator refresh performs status and power log.
  - Each scheduled coordinator refresh performs status and power log.
  - Creating multiple energy sensors does not multiply cloud calls.
  - Hourly calibration only adds positive missing kWh once per completed hour.
  - Daily calibration only adds positive missing kWh once per completed day.
  - Daily calibration waits until `00:05` or later and never runs at exactly `00:00`.
- Home Assistant checks:
  - Energy sensor appears for each appliance.
  - Sensor state is numeric kWh after successful power-log refresh.
  - Sensor has energy device class, total-increasing state class, and kWh unit.
  - No power-log entity has its own `async_update()` cloud call.
- Live debug checks:
  - Run read-only probes:
    - `unit="month", max_num=12`
    - `unit="day", max_num=30`
    - `unit="hour", from=today, max_num=24`
  - Confirm `hour/today/max_num=24` gives hourly buckets suitable for today's energy meter.

## Acceptance Criteria

- There is one periodic coordinator per config entry.
- Status refresh runs every 5 minutes.
- Power-log refresh runs every 5 minutes.
- Energy entities read cached values only.
- No power-log cloud call is triggered by individual entity property reads.
- Home Assistant Energy Dashboard can consume the daily kWh sensor.

## Assumptions

- Panasonic power logs support `unit="month"`, `unit="day"`, and `unit="hour"`.
- `unit="hour", from=today, max_num=24` is the safest v1 source for an HA-compatible daily energy meter.
- Status and power-log data should both update every 5 minutes.
