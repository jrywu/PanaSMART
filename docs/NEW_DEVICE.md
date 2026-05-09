# New Device Empty CommandList Plan

**Target document:** `docs/NEW_DEVICE.md`

## Summary

Document how to support Panasonic devices whose discovery response omits or returns an empty `CommandList`. The integration should treat missing command lists as expected for newer products, use exact server-provided command lists when available, use local model-type command lists for known missing models like `UJ` and `NNW-L`, and skip unknown devices safely instead of crashing.

## Discovery Policy

- Always prefer Panasonic cloud data:
  - Match `CommandList[].ModelType` against discovered gateway `ModelType`.
  - Use `model["JSON"][0]` only when present and non-empty.
- Use local fallback only for known verified model types:
  - `UJ`: air conditioner models whose cloud discovery omits command definitions.
  - `NNW-L`: newer dehumidifiers such as `F-YV34NNK` / `F-YV32NN` whose command table is app-side or otherwise omitted from API discovery.
- Never fallback by broad `DeviceType` alone:
  - `DeviceType == 4` is not enough because old and new dehumidifiers can have different mode values and supported features.
  - `NNW-L` has sparse mode values like `9`, `10`, `11`, unlike older `CXW`.
- If no exact or verified local command list exists:
  - Log nickname, model, model type, and device type.
  - Do not instantiate `PanasonicAppliance`.
  - Continue discovering the rest of the account.

## Adding A New Device Type

- First collect safe discovery metadata with the existing sanitized helper:
  - `python .Codex/scripts/inspect_panasonic_discovery_models.py`
  - Record `DeviceType`, `Model`, `ModelType`, and whether the server returned command JSON.
- If command JSON exists:
  - Do not add a hardcoded list.
  - Fix parsing only if the returned list uses a new parameter shape.
- If command JSON is missing:
  - Capture command values by switching modes in the official app and querying read-only status commands.
  - Build a model-specific hardcoded command list keyed by `ModelType`.
  - Add it to `HARDCODED_COMMAND_LISTS`.
- For enum commands, store and decode by command value, not list index:
  - Required for sparse values such as `NNW-L` mode `9 = smart energy`, `10 = quick dry`, `11 = silent dry`.
  - Also required when values skip numbers, for example `NNW-L` swing `0 = fixed`, `3 = auto`.

## Worked Examples

- `UJ` air conditioner:
  - Cloud discovery does not provide a usable command list.
  - Local `UJ_COMMAND_LIST` defines power, operation mode, temperature, fan, swing, timers, ECONAVI, and beep.
  - Its fan/swing ranges are compact, so existing AC parsing can derive lists from `Min`/`Max`.

- `NNW-L` dehumidifier:
  - Cloud discovery omits the command list even though the device is controllable.
  - Local `DEHUMIDIFIER_COMMAND_LIST` must be keyed to `NNW-L`, not reused from `CXW`.
  - Preset mapping:
    - `0 = continuous`
    - `1 = mold standby`
    - `3 = fan`
    - `4 = clothes`
    - `6 = fixed humidity`
    - `9 = smart energy`
    - `10 = quick dry`
    - `11 = silent dry`
  - Fan mapping:
    - `0 = 自動`
    - `1 = 弱`
    - `2 = 中`
    - `3 = 強`
  - Swing mapping:
    - `0 = 固定`
    - `3 = 自動`

## Test Plan

- Unit-style parser checks:
  - Exact server `ModelType` match wins over local fallback.
  - `UJ` uses `UJ_COMMAND_LIST` when no server list is present.
  - `NNW-L` uses the local dehumidifier list when no server list is present.
  - Unknown missing model type is skipped and does not crash discovery.
  - Sparse enum values decode correctly and do not use Python list indexes.

- Live debug checks:
  - Run `python my_pypanasonic_ac_saa4.py` with private credentials.
  - Confirm all known devices discover.
  - Confirm `NNW-L` reports the expected preset list, fan list, and swing list.
  - Confirm no auth tokens are dumped in debug device discovery logs.

## Assumptions

- New Panasonic products may continue omitting command lists from cloud discovery.
- Hardcoded command lists are acceptable only when values are observed from the official app or a trusted reverse-engineering report.
- Local fallback should be keyed by `ModelType`, not by display name, model nickname, or broad `DeviceType`.
- The plan file should be saved as UTF-8 with BOM at `docs/NEW_DEVICE.md`.
