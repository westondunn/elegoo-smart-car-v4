# Validation record

Checks run while importing and normalising the models (2026-10-29). Each is
**passed**, **failed** or **not run**, with the tool and its limits. Fusion,
Bambu Studio and physical printing were not available here and are not counted
as passes.

Reusable command (standard-library Python, also run by the
`3D model manifest` GitHub workflow):

```bash
python hardware/3d-models/validate_manifest.py                      # manifest, sizes, SHA-256, doc links
python hardware/3d-models/validate_manifest.py --geometry --report out.json
```

| # | Check | Result | Tool / evidence | Limitation |
| --- | --- | --- | --- | --- |
| 1 | Imported files identical to the source files (SHA-256 of all 299 files in the verbatim commit) | passed | import script hashed source and copy; `manifest.json` records both | files later patched for layout or kit-only scope carry `sha256_as_imported` |
| 2 | Package checksum lists (`SHA256SUMS.txt`) of explorer v0.1 (37 files), body v0.2 (38), body v0.3 (52) | passed on the verbatim commit of the follow-up history PR | `sha256sum -c` | lists regenerated as `verification/sha256sums.txt` after renames |
| 3 | Fusion asset hashes in `assembly_manifest.json` and `bundle_preflight.json` (64, then 60 STEPs) | passed | package `validate_bundle.py` | checks files, not geometry |
| 4 | C3 coupon hash pinned in `build_printed_rover.py` matches `cad/coupons/c3_motor_fit_integrated.step` | passed | sha256 | — |
| 5 | Retrofit R1: `final_package_manifest.json` hash matches the 3MF; STL/STEP hashes match `geometry_manifest.json` and the retention review | passed | sha256 | — |
| 6 | Body v0.3 reference snapshot hash matches `verification/manifest.json` | passed | sha256 | — |
| 7 | Rover V3 offline preflight (`validate_bundle.py`): 60 parts, 59 joints (54 rigid, 5 revolute), connected tree, 17 native recipes | passed | package script, re-run after the kit-only edit | input validation only; "Fusion runtime has not run" |
| 8 | `verify_preflight.py` (13 tests), `tests/verify_motion.py` (16), `tests/verify_fusion_boundary.py` (10) | passed | package unit tests, re-run after the kit-only edit; reports in `rover-v3/verification/` | API doubles, no Fusion |
| 9 | Manifest integrity: every asset present, size and SHA-256 match, no unlisted files, 140 assets | passed | `validate_manifest.py` | — |
| 10 | Documentation links (index, reference, docs/hardware, root README) | passed | `validate_manifest.py` | imported package docs are not link-checked |
| 11 | STEP parse: 63 files, AP214, declared unit mm, solid counts (e.g. V3 complete assembly 78 solids / 64 products; body v0.2 assembly 195 solids) | passed | regex parser in `validate_manifest.py` | no B-rep kernel; bounding boxes from CARTESIAN_POINT extents are approximate; no solid-validity check |
| 12 | 3MF parse: 6 files, unit millimeter, every mesh closed with consistent orientation and positive volume; Bambu presets and G-code presence recorded | passed | XML/zip parser | no slicer; bed/cutter placement not re-checked here (the V3 package's own audit covers it) |
| 13 | STL parse: 0 binary files, closed and consistently oriented, positive signed volume | passed | binary parser | STL has no units; mm assumed from matching STEP |
| 14 | Package scripts compile after path patches (all 16 `.py`) | passed | `py_compile` | compile only |
| 15 | No pre-normalisation file names left in scripts/docs (except historical records and the v0.2 doc snapshot in body v0.3) | passed | grep | — |
| 16 | No machine-specific personal paths in committed text | passed | grep after redaction (`<package>`, `<home>`) | — |
| 17 | Firmware and unrelated files unchanged | passed | `git diff --stat main` touches only `hardware/`, `docs/hardware/`, `.github/workflows/models-manifest.yml`, `.gitignore`, `README.md` | — |
| 18 | CadQuery generators (`build_printed_rover.py`, `build_hardware.py`, `build_revision.py`, `build_full_body.py`, `build_explorer.py`, `motor_adapters_r1.py`) | **not run** | CadQuery 2.7 / OCP not installed | path literals patched; regeneration unverified |
| 19 | Body v0.3 `test_revision.py` (12 tests), explorer `validate_final_exports.py`, body v0.2 `validate_body_exports.py` | **not run** | need CadQuery, VTK, lib3mf | results in the source environment are kept under each `verification/` |
| 20 | Fusion desktop build (RoverFusion) and motion script (RoverMotion 1.1.0) | **not run** | Fusion not driven from here | last recorded runs: builder 3.0.1 completed with warnings; RoverMotion 1.0.1 closed without error; 1.1.0 untested |
| 21 | Bambu Studio open / reslice / X1C plate fit | **not run** | no slicer here | project's own audit (`rover-v3/docs/bambu_workflow.txt`) reports plate membership, cutter exclusion and extrusion checks |
| 22 | Physical print, fit, load | **not run** | — | only the C1 motor coupon has a recorded physical result |
| 23 | Companion-package contents list `package_contents.json` vs files | failed for 3 of 14 entries | sha256 | `RoverMotion.py` (expected: 1.0.1 vs listed 1.0.0) and two validation JSONs were regenerated after the list was written; kept as a historical record under `verification/original_package/` |

Full machine-readable results: [`hardware/3d-models/validation/validation_report.json`](../../hardware/3d-models/validation/validation_report.json).
