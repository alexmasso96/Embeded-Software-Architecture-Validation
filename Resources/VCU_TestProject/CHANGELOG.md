# VCU Test Project — Release Change Log

Five releases with real, tool-visible deltas (added/removed/modified functions,
added struct fields, signature changes, new modules and new components).

| Release | Components | Src files | ~Functions | Arch ports | Requirements |
|---------|-----------|-----------|-----------|-----------|--------------|
| R1.0 | 6 | 51 | ~430 | 305 | 127 |
| R2.0 | 7 | 57 | ~481 | 341 | 142 |
| R3.0 | 8 | 69 | ~714 | 544 | 206 |
| R4.0 | 8 | 75 | ~812 | 627 | 224 |
| R5.0 | 8 | 75 | ~923 | 738 | 224 |

## R1.0
- Baseline: 6 components (BodyControl, Powertrain, BatteryMgmt, ThermalMgmt, Diagnostics, CommGateway).
- Each module ships `*_LegacyReset` (deprecated) — these are REMOVED in R2.0.
- State struct has 4 fields (phase/value/raw/valid).

## R2.0
- **New component:** ChassisControl (ABS, traction, steering).
- **Removed:** every `*_LegacyReset` function.
- **Modified struct:** all `*_State_t` gain `fault_count` (REQ *xx1).
- **Modified function:** every `*_Step` now latches a fault when value exceeds the cal limit.
- More `ReadAux*` signal accessors per module (auto growth).

## R3.0
- **New component:** ChargingCtrl (AC/DC sequencer, pilot, metering).
- **New modules:** BatteryMgmt::thermrunaway, Diagnostics::security.
- **Added function:** every module gains `*_SelfTest`; `*_Step` now calls it and can enter LIMP.
- **Added calibration:** `TrimOffset` accessor pair across all modules.

## R4.0
- **New modules:** BodyControl::ambient, Powertrain::launch, ChassisControl::suspension.
- **Modified struct:** `*_State_t` gain `uptime_ticks` + `trim`.
- **Signature change:** the first calibration setter of each module gains a `ramp` parameter.
- `*_Step` now advances `uptime_ticks`.

## R5.0
- **Added calibration:** `LimpFactor` accessor pair across all modules.
- Largest signal-accessor surface (peak function count) — the stress-test release.
- All eight components active simultaneously.
