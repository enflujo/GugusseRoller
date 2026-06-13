# Experiment Inventory

## Preserved Local Work
- `archive-local-main-before-cleanup-20260613`
  - Local `main` commit before cleanup.
  - Contains previous calibration, capture-loop, speed, logging, and optimization changes.
- `stash@{0}` / `wip-before-clean-development-plan-20260613`
  - Large uncommitted DNG/ROI experiment.
  - Includes modified `CameraSettings.py`, `CaptureSettings.py`, `ConfigFiles.py`, `GCamera.py`, and `GugusseGUI.py`.
  - Includes untracked logs and `docs/dng-roi-analysis-plan.md`.

## Upstream Branches Worth Inspecting
- `upstream/master`
  - Current clean base for this work.
- `upstream/histogram`
  - Earlier histogram work.
- `upstream/histogram2`
  - Newer histogram pull-request branch.
- `upstream/convert-to-c`
  - Relevant to performance discussions, but should not be merged wholesale without review.
- `upstream/imx_183`
  - Camera-specific work that may be useful later.

## Recovery Rule
Do not merge experimental branches wholesale. Extract one feature at a time, measure it, and commit it with documentation.
