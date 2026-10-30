# Decision log (3D model import)

| Date | Decision | Why |
| --- | --- | --- |
| 2026-10-29 | Two commits: a verbatim import (33baab6) and a separate normalisation/reduction commit | The brief required packaging changes to be a separate, reviewable change; the original bytes stay retrievable from history |
| 2026-10-29 | Ordinary Git, no Git LFS | Repository had no LFS policy; largest file is 13.9 MB, total about 137 MB, all under GitHub's 50 MB warning; LFS would add a client requirement and a bandwidth quota and make files unusable without it |
| 2026-10-29 | Recommended revision = Rover V3 | Latest; only completed native Fusion build on record; complete sliced two-plate X1C project; C3 interface derived from the physically tested C1 coupon. Still unprinted as a whole |
| 2026-10-29 | Keep the older families (explorer v0.1, body v0.2, body v0.3, V2 P1, retrofit, roof battery, service hatch) | They document the lineage, the measured constraints (76.2 mm, tires, V2 P1B measurements) and the parts physically on the rover (V2 P1B) |
| 2026-10-29 | Drop byte-identical loose duplicates; keep package-internal duplicates that a checksum list or script references | Package integrity over deduplication; all duplicates are cross-referenced in `manifest.json` |
| 2026-10-29 | Do not redistribute ELEGOO's schematic archive or vendor datasheets | No license in the ELEGOO repositories; pinned blob/commit and retrieval steps in `hardware/3d-models/reference/README.md` |
| 2026-10-29 | Limit hardware reference models to kit hardware (maintainer's instruction) | Removed `pi_board`, `pi_board_connectors`, `pi_processor`, `power_bank` from the Fusion asset folder, builder manifest, motion catalog and offline tests; printed Pi standoffs and power-bank rails kept; archived STEP/F3D left intact |
| 2026-10-29 | Rename and regroup every file into `<family>/<category>/<snake_case>` (maintainer's instruction) | One scheme across eight packages; Fusion script folder/module names and the files written by `recover_oem_references.py` are the only exceptions; old names recorded per asset in `manifest.json` (`imported_as`, `original_filename`) |
| 2026-10-29 | Patch script path literals and documentation references instead of leaving dangling names | 96 recorded patches; scripts compile; package offline tests re-run; CadQuery generators could not be executed |
| 2026-10-29 | Keep historical validation records unchanged (apart from path redaction) under `verification/original_package/` and `verification/build_reports/` | They are evidence of the original environment; regenerated records live beside them |
| 2026-10-29 | Redact machine-specific paths in build reports and docs (`<package>`, `<home>`, `<you>`) | Brief excludes personal paths from committed reports |
| 2026-10-29 | Per-family `verification/sha256sums.txt` plus a repository-level validator and a lightweight GitHub workflow | Keeps the firmware CI gate (on the `agentic-trial` branch) untouched; standard-library only |
| 2026-10-29 | Carry forward conflicting measurements as evidence, not as geometry edits | Brief forbids silent reconciliation; conflicts listed in `revisions.md` |

## Next physical validation step

Print [`rover-v3/print/fit_checks/fit_batch_x1c_pla.3mf`](../../hardware/3d-models/rover-v3/print/fit_checks/fit_batch_x1c_pla.3mf)
(about 1 h 28 min, 35 g) and
[`c3_motor_corner_and_battery_rail_x1c_pla.3mf`](../../hardware/3d-models/rover-v3/print/fit_checks/c3_motor_corner_and_battery_rail_x1c_pla.3mf)
(about 1 h 08 min, 36 g), then check with the real hardware: washer gauge,
flat-battery frame, Pi 58 × 49 pattern, motor-battery pitch, motor block on the
C3 corner. Record the results in `known-issues.md` before committing to the
11-hour two-plate chassis print.
