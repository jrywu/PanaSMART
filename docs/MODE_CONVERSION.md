# Mode Conversion Stability Plan

## Problem Statement

Occasionally, changing operation mode, preset mode, fan mode, or swing mode from Home Assistant produces an unknown/unsupported mode error or leaves the entity in an unexpected mode.

The integration has three different names for the same concept:

- Panasonic command value, such as `0`, `1`, `6`, or `11`.
- Internal canonical string, such as `fan`, `濕度設定`, `靜音除濕`, or `自動`.
- Home Assistant display/service value, such as `Fan Only`, `濕度設定`, `靜音除濕`, or `fan_only`.

The Panasonic API wrapper already converts raw Panasonic numeric command/status values into internal canonical strings where needed. For AC, those canonical strings are English because Home Assistant HVAC modes require an enum mapping:

```python
self.ac_operation_mode_list = ['cool', 'dry', 'fan', 'auto', 'heat']
```

and power-off state becomes:

```python
self.operation_mode = 'off'
```

So `"off"`, `"cool"`, `"dry"`, `"fan"`, `"auto"`, and `"heat"` are not raw Home Assistant strings. They are this integration's canonical appliance-layer strings for AC operation mode.

For dehumidifier preset modes, do **not** translate Panasonic command-list titles into English canonical names. The Panasonic command list already contains the same Chinese mode titles shown in the app, such as:

```python
["連續除濕", 0]
["送風模式", 3]
["衣物乾燥", 4]
["濕度設定", 6]
["智慧節能", 9]
["快速除濕", 10]
["靜音除濕", 11]
```

Those Panasonic titles should become the canonical strings exposed to Home Assistant.

The current code sometimes assumes these strings can be converted by calling `.title()` for display and `.lower()` for commands. That is not reliable. It works for simple English values but fails for Home Assistant enum strings, translated Chinese labels, and multi-word values when the display value is not exactly reversible.

## Root Cause

### 1. `fan_only` Is Not Normalized To Panasonic `fan`

In `custom_components/panasonic_smart_app/climate.py`, `async_set_hvac_mode()` maps enum values through `HA_STATE_TO_PANA`, but can fall back to raw lowercased strings:

```python
if hvac_mode in HA_STATE_TO_PANA:
    command = HA_STATE_TO_PANA[hvac_mode]
else:
    command = hvac_mode.lower()
```

If Home Assistant sends the string `"fan_only"` instead of an `HVACMode.FAN_ONLY` enum, the command becomes `"fan_only"`.

In `custom_components/panasonic_smart_app/panasonic_iot_tw_api/PanasonicAppliance.py`, AC mode control expects:

```python
self.ac_operation_mode_list = ['cool', 'dry', 'fan', 'auto', 'heat']
```

`"fan_only"` is not in that list, so mode conversion fails.

### 2. Display Values Are Used As Command Values

Several entity properties display modes by title-casing internal values:

```python
return mode.title()
```

Setters then reverse this with:

```python
return await self._api.set_preset_mode(mode.lower())
return await self._api.set_fan_mode(preset_mode.lower())
```

This assumes:

```python
mode == mode.title().lower()
```

That is fragile. It is especially risky for:

- Home Assistant enum strings such as `fan_only`.
- Chinese labels such as `自動`, `弱`, `中`, `強`, `固定`.
- Translated multi-word modes such as `fixed humidity`, `mold standby`, `smart energy`, `quick dry`, and `silent dry`.
- Any future mode where the UI display label differs from the internal API key.

### 3. Unsupported Commands Are Soft-Failed

The appliance layer logs an error and returns the old mode when a lookup fails:

```python
value = self.preset_value_by_mode.get(command)
if value is None:
    _LOGGER.error("%s set_preset_mode() unsupported mode: %s", self.name, command)
    return self.preset_mode
```

This avoids crashing, but Home Assistant may see a requested mode that was not applied and then show an unknown/unexpected state.

## Solution Overview

Use Panasonic command-list titles/canonical strings as the source of truth. Avoid display-string conversion where Home Assistant allows arbitrary options.

Only `ClimateEntity.hvac_mode` needs a required HA mapping, because Home Assistant climate operation mode must use `HVACMode` enum values instead of arbitrary strings.

For other mode lists, pass canonical appliance strings directly to Home Assistant and back. For dehumidifier preset modes, those canonical strings should be the Panasonic Chinese command-list titles:

```text
Panasonic numeric command/status
    -> PanasonicAppliance canonical string
    -> Home Assistant option string
    -> PanasonicAppliance canonical string
    -> Panasonic numeric command
```

This means humidifier modes, dehumidifier fan presets, AC fan modes, and swing modes should not use `.title()` for options and `.lower()` for commands. They should expose the canonical list returned by the appliance object and send selected values back unchanged.

Rules:

- The low-level API should continue using canonical Panasonic strings.
- For dehumidifier preset modes, canonical means the Panasonic command-list title, not an English translation.
- Home Assistant entity properties should expose canonical Panasonic strings directly where HA accepts arbitrary string options.
- Entity setters must not use raw `.lower()` as the primary conversion.
- `ClimateEntity.hvac_mode` and `hvac_modes` must map between Panasonic canonical strings and HA `HVACMode` values.
- `fan_only`, `Fan Only`, `HVACMode.FAN_ONLY`, and `fan` must all normalize to Panasonic canonical `fan` when setting climate HVAC mode.
- Preset/fan/swing setters should validate against the appliance-supported mode lists.
- Unsupported requested modes should log the original value, normalized value, and supported list.

## HVACMode Mapping Boundary

The only required mode translation should be the climate HVAC mode boundary.

Panasonic canonical to HA:

```python
PANA_TO_HA_STATE = {
    'dry': HVACMode.DRY,
    'cool': HVACMode.COOL,
    'fan': HVACMode.FAN_ONLY,
    'heat': HVACMode.HEAT,
    'auto': HVACMode.AUTO,
    'off': HVACMode.OFF,
}
```

HA to Panasonic canonical:

```python
HA_STATE_TO_PANA = {
    HVACMode.DRY: 'dry',
    HVACMode.COOL: 'cool',
    HVACMode.FAN_ONLY: 'fan',
    HVACMode.HEAT: 'heat',
    HVACMode.AUTO: 'auto',
    HVACMode.OFF: 'off',
    'dry': 'dry',
    'cool': 'cool',
    'fan': 'fan',
    'fan_only': 'fan',
    'fan only': 'fan',
    'heat': 'heat',
    'auto': 'auto',
    'off': 'off',
}
```

`climate.hvac_mode` should return `PANA_TO_HA_STATE[self._api.get_operation_mode()]`.

`climate.hvac_modes` should derive from `self._api.get_operation_mode_list()` and return only HA enum values:

```python
return [
    PANA_TO_HA_STATE[mode]
    for mode in self._api.get_operation_mode_list()
    if mode in PANA_TO_HA_STATE
]
```

`climate.async_set_hvac_mode()` should normalize only the HA climate input and send the Panasonic canonical value to `set_operation_mode()`.

## Target Files

- `custom_components/panasonic_smart_app/climate.py`
  - Keep explicit HVACMode mapping for operation modes.
  - Pass AC fan and swing canonical strings directly where possible.
  - Remove `.title()`/`.lower()` round-trip for fan and swing options.
- `custom_components/panasonic_smart_app/humidifier.py`
  - Pass Panasonic dehumidifier preset titles directly to/from Home Assistant modes.
- `custom_components/panasonic_smart_app/fan.py`
  - Pass dehumidifier fan canonical strings directly to/from Home Assistant preset modes.
- `custom_components/panasonic_smart_app/panasonic_iot_tw_api/PanasonicAppliance.py`
  - Stop using `DEHUMI_PRESET_MODE_BY_VALUE` as the normal dehumidifier preset canonical path.
  - Build preset maps directly from Panasonic command-list titles.
  - Improve unsupported-mode logs with supported values.

## Implementation Plan

### Task 1: Keep Canonical Appliance Strings As HA Option Values

Remove title-casing from option lists and current option values where HA accepts arbitrary strings.

Preferred behavior:

```python
@property
def available_modes(self):
    return self._api.get_preset_mode_list()

@property
def mode(self):
    return self._api.get_preset_mode()

async def async_set_mode(self, mode):
    if mode not in self._api.get_preset_mode_list():
        _LOGGER.error(...)
        return
    return await self._api.set_preset_mode(mode)
```

Apply the same principle to:

- Humidifier `mode` / `available_modes`.
- Dehumidifier fan `preset_mode` / `preset_modes`.
- AC fan `fan_mode` / `fan_modes`.
- AC swing `swing_mode` / `swing_modes`.

### Task 2: Use Panasonic Titles For Dehumidifier Presets

Update `PanasonicAppliance.setup_command_list()` for device type `4`.

Current behavior:

```python
preset_mode = self._get_dehumi_preset_mode_name(value, mode[0])
self.preset_mode_by_value[value] = preset_mode
self.preset_value_by_mode[preset_mode] = value
self.preset_mode_list.append(preset_mode)
```

New behavior:

```python
preset_mode = mode[0]
self.preset_mode_by_value[value] = preset_mode
self.preset_value_by_mode[preset_mode] = value
self.preset_mode_list.append(preset_mode)
```

This makes the HA mode list match the Panasonic app and the command list:

- `連續除濕`
- `送風模式`
- `衣物乾燥`
- `濕度設定`
- `智慧節能`
- `快速除濕`
- `靜音除濕`

Remove `DEHUMI_PRESET_MODE_BY_VALUE` and `_get_dehumi_preset_mode_name()` from the normal path. Do not add legacy English aliases unless later testing proves existing automations require them.

### Task 3: Add Minimal Defensive Normalization Helpers

Add a small helper for service calls or older UI values that may still send display strings:

```python
def _normalize_ha_string(value):
    if value is None:
        return None
    if hasattr(value, "value"):
        value = value.value
    value = str(value).strip()
    if value.isascii():
        return value.lower().replace("_", " ")
    return value
```

Do not use this helper to transform the supported mode lists. Lists should come from the appliance directly. Because we are not supporting legacy English dehumidifier aliases in v1, this helper is mainly for `HVACMode` compatibility and simple ASCII fan/swing values such as `Auto`.

### Task 4: Normalize And Validate Climate HVACMode Only

Update `PanasonicClimate.async_set_hvac_mode()` to use the explicit HA-to-Panasonic mapping:

```python
async def async_set_hvac_mode(self, hvac_mode):
    key = hvac_mode.value if hasattr(hvac_mode, "value") else hvac_mode
    command = HA_STATE_TO_PANA.get(key)
    if command is None:
        normalized = _normalize_ha_string(key)
        command = HA_STATE_TO_PANA.get(normalized)
    if command not in self._api.get_operation_mode_list():
        _LOGGER.error(
            "%s async_set_hvac_mode() unsupported mode: requested=%s normalized=%s supported=%s",
            self._api.get_name(),
            hvac_mode,
            command,
            self._api.get_operation_mode_list(),
        )
        return
    try:
        return await self._api.set_operation_mode(command)
finally:
    await self.coordinator.async_request_forced_refresh()
```

Update `PanasonicClimate.hvac_modes()` to map canonical Panasonic values to HA enum values, not title strings.

### Task 5: Validate Canonical String Setters

For preset/fan/swing setters:

- First try the value exactly as received.
- If it is not supported, try `_normalize_ha_string(value)` only for simple compatibility.
- If still unsupported, log requested, normalized, and supported values.
- Send the supported canonical value unchanged to the appliance layer.

For AC numeric fan and swing modes, make sure `"1"`, `"2"`, `"3"`, `"4"`, `"5"`, and `"auto"` remain valid.

### Task 6: Update Dehumidifier Preset Mode

Update `PanasonicDehumidifier.async_set_mode()`:

```python
command = mode
if command not in self._api.get_preset_mode_list():
    command = _normalize_ha_string(mode)
if command not in self._api.get_preset_mode_list():
    _LOGGER.error(
        "%s async_set_mode() unsupported mode: requested=%s normalized=%s supported=%s",
        self._api.get_name(),
        mode,
        command,
        self._api.get_preset_mode_list(),
    )
    return
try:
    return await self._api.set_preset_mode(command)
finally:
    await self.coordinator.async_request_forced_refresh()
```

This should support:

- Canonical `連續除濕`.
- Canonical `送風模式`.
- Canonical `衣物乾燥`.
- Canonical `濕度設定`.
- Canonical `智慧節能`.
- Canonical `快速除濕`.
- Canonical `靜音除濕`.

### Task 7: Update Dehumidifier Fan Preset Mode

Update `PanasonicDehumidifierFan.async_set_preset_mode()`.

Chinese values should pass through unchanged and be validated against:

```python
self._api.get_fan_mode_list()
```

Use `_normalize_ha_string()` only as a fallback. It preserves non-ASCII values exactly:

```python
command = preset_mode
if command not in self._api.get_fan_mode_list():
    command = _normalize_ha_string(preset_mode)
```

### Task 8: Improve Appliance-Layer Diagnostics

Keep defensive logs in `PanasonicAppliance.py`, but include supported modes:

```python
_LOGGER.error(
    "%s set_preset_mode() unsupported mode: %s; supported=%s",
    self.name,
    command,
    self.preset_mode_list,
)
```

Do the same for:

- `set_fan_mode()`
- `set_swing_mode()`
- `set_operation_mode()` before calling `.index(command)` for AC modes.

### Task 9: Verification

Run static compile checks:

```bash
python -m py_compile custom_components/panasonic_smart_app/climate.py custom_components/panasonic_smart_app/humidifier.py custom_components/panasonic_smart_app/fan.py custom_components/panasonic_smart_app/panasonic_iot_tw_api/PanasonicAppliance.py
```

Run direct API smoke checks with `my_pypanasonic_ac_saa4.py` only when needed. Do not commit or expose that file.

Manual Home Assistant checks:

- AC operation mode:
  - `Cool`
  - `Dry`
  - `Fan Only`
  - `Auto`
  - `Heat` where supported
  - `Off`
- Dehumidifier mode:
  - `連續除濕`
  - `送風模式`
  - `衣物乾燥`
  - `濕度設定`
  - `智慧節能`
  - `快速除濕`
  - `靜音除濕`
- Dehumidifier fan:
  - `自動`
  - `弱`
  - `中`
  - `強`
  - Legacy values such as `急速`, `標準`, `靜音`

## Acceptance Criteria

- Setting AC `Fan Only` never sends `fan_only` to `PanasonicAppliance.set_operation_mode()`.
- Entity setters pass canonical appliance strings through unchanged where HA allows arbitrary options.
- Dehumidifier preset modes shown in HA match Panasonic command-list titles.
- No English dehumidifier alias layer is added unless later testing proves it is needed.
- Unsupported mode logs include requested value, normalized value, and supported list.
- Chinese fan/swing labels are preserved exactly.
- No entity enters unknown mode because of `.title()`/`.lower()` round-trip mismatch.
