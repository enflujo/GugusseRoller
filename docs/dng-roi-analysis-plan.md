# DNG ROI Analysis Plan

## Status
This document records a previous local experiment that should be recovered selectively.

The implementation is not present in this clean branch yet. The previous work is preserved in the stash named `wip-before-clean-development-plan-20260613`.

## Goal
Improve DNG review and camera calibration in Gugusse Compact by adding guided analysis based on the actual frame area, or ROI, so diagnostics are closer to final RAW captures than preview-only checks.

## Useful Ideas To Recover
- ROI selection on preview.
- Per-format ROI persistence.
- ROI guide overlays hidden during active capture.
- RAW/DNG analysis based on the selected ROI.
- Material profiles:
  - `Negativo color`
  - `Blanco y negro`
  - `Positivo`
- Single-capture RAW check for calibration.
- Offline `Analyze Latest DNG` workflow for local project folders.
- Operator recommendations based on clipping, range, and color balance.

## Proposed Metric Set
- Black clipping percentage.
- White clipping percentage.
- Dynamic range occupancy.
- RGB/Bayer channel balance.
- Optional focus score summary.

## Performance Rules
- Keep live analysis off by default until Phase 2 and Phase 3 are done.
- Do not analyze full-resolution preview frames continuously on Raspberry Pi 4.
- Prefer ROI sampling, downscale, histograms, and approximate percentiles.
- Avoid blocking the GUI while decoding DNG or computing metrics.
- Disable heavy analysis during RUN capture unless it has a strict time budget.

## Recovery Milestones
1. Add ROI editing only, with no analysis.
2. Add ROI persistence by film format.
3. Add offline latest-DNG analysis as a separate process.
4. Add snapshot RAW analysis outside RUN.
5. Add optional live preview analysis at a low cadence.
6. Add guidance text and threshold tuning per material profile.

## Open Decisions
- Whether live ROI analysis should be always available or only explicit/on-demand.
- Default ROI presets for 8mm, Super 8, 16mm, and 35mm.
- Thresholds per material type.
- Which camera controls are RAW-impacting vs preview-only.
