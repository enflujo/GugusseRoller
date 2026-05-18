# Driver Scaling And Speed Notes

## Context

On this scanner, some motor-driver configurations do not match the step scale assumed by the original Gugusse defaults.

This can produce a deterministic error:

- the film does not skip frames randomly
- it skips exactly one frame every time
- the scanner captures every other frame

That behavior strongly suggests a step-scale mismatch, not random instability.

## What likely happened

If this hardware moves more physical distance per pulse than the original setup, then the original values in `hardwarecfg.json` are too large in step-based units.

That affects parameters such as:

- `speed`
- `speed2`
- `ignoreInitial`
- `faultTreshold`

Reducing those values by about half can make the software and this driver's step scale line up again.

## Important distinction

Not every capture parameter means the same thing.

Step-domain parameters:

- `speed`
- `speed2`
- `ignoreInitial`
- `faultTreshold`

These depend on how many pulses this driver needs to move a given physical distance.

Time-domain parameters:

- `targetTime`
- `settleDelay`
- `rawSkipBuffers`

These are about timing and stabilization, not motor step scale.

## Practical consequence

Halving step-domain values does not simply mean "scanning at half speed".

It more likely means:

- the software now speaks the correct distance scale for this driver
- one frame advance now lands on one frame, instead of overshooting to the next one

Once the step scale is correct, throughput should be improved by tuning timing and motion profile from that corrected baseline.

## How to think about maximum speed

Do not treat the original values from Carl as the target to return to directly.

Instead:

1. Keep the driver-correct step scale for this hardware.
2. Treat that as the calibrated baseline.
3. Increase performance from there by adjusting timing and motion parameters carefully.

For this codebase, the safest next-performance knobs are usually:

- `targetTime`
- `speed`
- `speed2`

But only after preserving the step scale that matches this hardware.

## Better long-term model

The clean model would be:

- keep reference tuning values in physical intent
- add a driver step-scale factor for this hardware
- derive step-domain values from that factor

Conceptually:

- `scaled_speed = reference_speed * driverStepScale`
- `scaled_speed2 = reference_speed2 * driverStepScale`
- `scaled_ignoreInitial = reference_ignoreInitial * driverStepScale`
- `scaled_faultTreshold = reference_faultTreshold * driverStepScale`
- `targetTime` stays unchanged

If this scanner really needs about half the original step-domain values, then `driverStepScale` would be about `0.5`.

That would let the project separate two different concerns:

- hardware step calibration
- performance tuning

## Runtime format structure

The code supports an explicit split inside a film-format motor profile:

- `reference`: original step-domain values for that format
- `driverStepScale`: hardware calibration for this scanner
- direct fields such as `speed`, `speed2`, `targetTime`: runtime tuning overrides

Example:

```json
{
  "driverStepScale": 0.5,
  "reference": {
    "faultTreshold": 8000,
    "ignoreInitial": 10,
    "speed": 1000.0,
    "speed2": 100.0,
    "targetTime": 0.33
  },
  "speed": 850.0,
  "speed2": 100.0,
  "targetTime": 0.22
}
```

Resolution order:

1. start from `reference`
2. scale step-domain fields by `driverStepScale`
3. apply direct overrides from the runtime profile

This keeps driver calibration explicit while still allowing local performance tuning.

## Current takeaway

For this machine, the "half values" are not just a conservative slowdown.

They are likely the calibration that makes the driver's pulse scale match the mechanical distance between frames.

## Current stable 16mm profile

This is the current stable `16mm` setup after validation on this scanner.

Resolved runtime values actually used by the motors:

- feeder:
  - `faultTreshold = 4000`
  - `ignoreInitial = 5`
  - `speed = 850.0`
  - `speed2 = 100.0`
  - `targetTime = 0.22`
- filmdrive:
  - `faultTreshold = 4000`
  - `ignoreInitial = 900`
  - `speed = 6100.0`
  - `speed2 = 800.0`
  - `targetTime = 0.28`
- pickup:
  - `faultTreshold = 4000`
  - `ignoreInitial = 5`
  - `speed = 1500.0`
  - `speed2 = 100.0`
  - `targetTime = 0.22`

Capture tuning:

- `mainSkipBuffers = 3`
- `rawSkipBuffers = 2`
- `settleDelay = 0.06`

Source profile structure now stored in `hardwarecfg.json`:

- `reference` keeps the original format intent
- `driverStepScale = 0.5` expresses this scanner's driver calibration
- direct fields override the resolved runtime tuning

Observed behavior during validation:

- stable capture
- no visible frame skipping
- no visible blurred frames with `rawSkipBuffers = 2`
- FTP not acting as the bottleneck (`queue_max = 0`)

Representative performance range from recent stable runs:

- total frame time around `3.87s` to `3.97s`
- filmdrive around `1.24s` to `1.33s`
- reels around `1.32s` to `1.46s`

## What changed across formats

The project now separates three different layers:

1. Carl's original format intent in `reference`
2. this scanner's driver calibration in `driverStepScale`
3. runtime tuning overrides for performance or behavior

For most formats, the current runtime behavior is still just:

- Carl reference
- scaled by `driverStepScale = 0.5`
- with no extra tuning overrides

That means these formats are currently treated as "driver calibration only":

- `16mmBigReels`
- `35mm`
- `35mmBigReels`
- `8mm`
- `pathex`
- `super8`

Formats with extra local behavior beyond the generic `0.5` driver scaling:

- `16mm`
  - explicit performance tuning overrides
  - capture tuning (`rawSkipBuffers`, `settleDelay`, etc.)
- `35mmSoundtrack`
  - `feeder.ignoreInitial = 20` is kept as an explicit local override
  - this does not match a pure half-scaling from Carl's original settings

## Diagnostic takeaway for future work

If a format was already working after the original "divide by two" adaptation, that does not automatically mean it needs the same performance tuning as `16mm`.

The safer interpretation is:

- first apply the driver calibration model
- then validate the format
- only after that decide whether that format needs its own tuning pass

So the `16mm` work should not be blindly copied to every other format.

What *can* be generalized safely is the driver calibration structure:

- `reference`
- `driverStepScale`
- optional runtime overrides only when a specific format proves it needs them
