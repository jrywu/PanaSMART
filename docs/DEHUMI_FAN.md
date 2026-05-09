# Dehumidifier Fan Entity Plan

## Problem Statement

Panasonic dehumidifiers expose fan mode controls, and the integration currently creates a Home Assistant `fan.*` entity for each dehumidifier so users can change fan preset modes such as:

- `自動`
- `弱`
- `中`
- `強`
- legacy values such as `急速`, `標準`, `靜音`

The Home Assistant fan UI presents a power-style control for the entity. When the user taps the fan power control, Home Assistant calls actions such as:

```text
fan.turn_on
fan.turn_off
```

The current `PanasonicDehumidifierFan` entity only supports preset mode changes. It does not advertise or implement fan turn-on/turn-off support, so Home Assistant shows an error:

```text
Entity fan.<name> does not support action fan.turn_off.
```

## Root Cause

In `custom_components/panasonic_smart_app/fan.py`, the dehumidifier fan entity currently sets:

```python
self._supported_features = FanEntityFeature.PRESET_MODE
```

and the turn-on/turn-off methods are commented out:

```python
# async def async_turn_on(self):
#     return await self._api.set_power('on')
# async def async_turn_off(self):
#     return await self._api.set_power('off')
```

Because `FanEntityFeature.TURN_ON` and `FanEntityFeature.TURN_OFF` are not included, Home Assistant correctly treats `fan.turn_on` and `fan.turn_off` as unsupported actions.

The physical Panasonic dehumidifier does not have an independently powered fan separate from the appliance. The fan control surface is part of the dehumidifier. Therefore, the practical meaning of fan entity power is appliance power.

## Solution

Wire the dehumidifier fan entity's power actions to the dehumidifier appliance power.

Update `PanasonicDehumidifierFan` in `custom_components/panasonic_smart_app/fan.py`:

```python
self._supported_features = (
    FanEntityFeature.PRESET_MODE
    | FanEntityFeature.TURN_ON
    | FanEntityFeature.TURN_OFF
)
```

Add:

```python
@property
def is_on(self) -> bool | None:
    """Return True if the dehumidifier is powered on."""
    return self._api.is_on()

async def async_turn_on(self, **kwargs):
    """Turn the dehumidifier on from the fan entity."""
    try:
        return await self._api.set_power('on')
    finally:
        await self.coordinator.async_request_forced_refresh()

async def async_turn_off(self, **kwargs):
    """Turn the dehumidifier off from the fan entity."""
    try:
        return await self._api.set_power('off')
    finally:
        await self.coordinator.async_request_forced_refresh()
```

Keep fan preset mode behavior unchanged:

```python
async def async_set_preset_mode(self, preset_mode):
    return await self._api.set_fan_mode(preset_mode)
```

## Expected Behavior

- The fan entity no longer shows unsupported-action errors when the user taps the fan power control.
- `fan.turn_on` powers on the dehumidifier.
- `fan.turn_off` powers off the dehumidifier.
- The humidifier entity and fan entity both control the same physical appliance power state.
- Fan preset mode still controls only the dehumidifier fan setting.
- The fan entity remains a convenience/control surface for the dehumidifier, not a separate physical fan device.

## Verification

Run static compile checks:

```bash
python -m py_compile custom_components/panasonic_smart_app/fan.py
```

Manual Home Assistant checks:

- Open the `fan.<dehumidifier>` entity card.
- Tap the fan power control.
- Confirm no unsupported-action toast appears.
- Confirm `fan.turn_off` turns off the dehumidifier.
- Confirm `fan.turn_on` turns on the dehumidifier.
- Confirm changing preset mode still updates Panasonic fan mode.
