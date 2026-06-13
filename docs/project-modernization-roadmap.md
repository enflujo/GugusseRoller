# Gugusse Compact Modernization Roadmap

## Purpose
Create a clean, community-friendly development path for growing Gugusse Compact without making the Raspberry Pi GUI unstable.

This branch starts from `upstream/master` and should only receive small, reviewable changes. Previous local experiments are preserved in Git and can be recovered selectively.

## Working Principles
- Keep Python as the main application language for camera control, GUI, hardware integration, and community contributions.
- Do not add expensive image processing directly to the Qt GUI event path.
- Prefer one camera owner and explicit data flow from camera preview/capture to tools.
- Treat Raspberry Pi 4 as the baseline performance target; Raspberry Pi 5 can be a faster target, not the architecture fix.
- Add instrumentation before large feature work.
- Merge experiments only after they are isolated, measured, and documented.

## Phase 0: Repository Cleanup
- Start from `upstream/master`.
- Preserve local experiments in a stash and archive branch.
- Add project docs for roadmap and experiment inventory.
- Keep runtime logs, caches, local settings, and generated files out of version control.

## Phase 1: Measurement Baseline
- Add lightweight performance logging for:
  - Qt event-loop latency.
  - CPU load.
  - RAM use.
  - Temperature and throttling state.
  - Camera capture time.
  - DNG save time.
  - Export queue size.
- Create repeatable benchmark runs:
  - Idle GUI.
  - Preview only.
  - Snapshot JPG.
  - Snapshot DNG.
  - Run mode for 100 frames.
  - Offline DNG analysis.

## Phase 2: Camera And Preview Budget
- Lower preview workload while preserving full-resolution still/DNG capture.
- Define preview, analysis, and still-capture streams explicitly.
- Ensure live tools consume downscaled frames or ROI samples.
- Add backpressure: if an analysis worker is busy, drop stale frames.

## Phase 3: Process Isolation
- Move expensive analysis into a separate process instead of only a `QThread`.
- Keep the GUI responsive even if analysis is slow or crashes.
- Define a simple message contract for analysis jobs and results.

## Phase 4: Feature Recovery
Recover useful work from the previous experiments in small slices:
- ROI editing and per-format ROI storage.
- DNG/RAW ROI analysis.
- Focus score and focus peaking.
- Histogram and exposure guidance.
- Better camera-control grouping and naming.

## Phase 5: Native Kernels Where Needed
Keep Python orchestration, but consider Rust or C++ for hot paths:
- RAW unpacking.
- Histogram and percentile approximation.
- Focus score.
- Focus peaking mask generation.

## Phase 6: Hardware Evaluation
Compare Raspberry Pi 4 and Raspberry Pi 5 using the same benchmarks.

Pi 5 should be evaluated with proper power, cooling, and storage. The target is not only higher speed, but stable headroom for future tools.

## Branch Policy
- `plan-clean-modernization`: planning and cleanup baseline.
- `feature/perf-baseline`: instrumentation only.
- `feature/camera-stream-budget`: preview/capture stream changes.
- `feature/analysis-process`: process-isolated analysis.
- `feature/dng-roi-analysis`: recover DNG/ROI work.
- `feature/focus-tools`: recover focus score and focus peaking.

## Current Local Preservation
- Clean branch base: `upstream/master`.
- Local branch preserved: `archive-local-main-before-cleanup-20260613`.
- Stash preserved: `wip-before-clean-development-plan-20260613`.
