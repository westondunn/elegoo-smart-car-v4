# Rover 3D models

CAD, print files and editable sources for the custom rover built on the ELEGOO
Smart Robot Car V4.0 kit. The firmware in the repository root is unchanged by
these files.

**Recommended revision: `rover-v3/`.** It is the latest design, the only one
with a completed native Fusion build on record, and it ships a complete
two-plate Bambu Lab X1 Carbon print project. Its motor interface is derived
from a coupon the project record marks as physically tested. The full V3
chassis itself has **not** been printed yet. Older revisions are kept for
history and for the parts that are physically on the rover today (V2 P1B).

Scope rule applied to this tree: hardware reference models are limited to what
ships in the ELEGOO kit. Envelopes for the Raspberry Pi and the flat power bank
were removed (see [Decisions](../../docs/hardware/decisions.md)); the printed
parts that carry them (Pi standoffs, power-bank rails) are kept.

| Go to | Path |
| --- | --- |
| Start editing (Fusion) | [`rover-v3/docs/readme_fusion.txt`](rover-v3/docs/readme_fusion.txt), script in [`rover-v3/fusion/RoverFusion/`](rover-v3/fusion/RoverFusion/) |
| Print | [`rover-v3/print/full_rover_x1c_pla.3mf`](rover-v3/print/full_rover_x1c_pla.3mf), guidance in [docs/hardware/printing.md](../../docs/hardware/printing.md) |
| Assemble | [docs/hardware/assembly.md](../../docs/hardware/assembly.md) |
| Validate | `python hardware/3d-models/validate_manifest.py --geometry`, results in [docs/hardware/validation.md](../../docs/hardware/validation.md) |
| Provenance | [`manifest.json`](manifest.json) (every file: origin, SHA-256, role, units, status, patches) |
| Lineage and conflicts | [docs/hardware/revisions.md](../../docs/hardware/revisions.md), [known-issues.md](../../docs/hardware/known-issues.md) |

## Layout

```
hardware/3d-models/<family>/<category>/<lowercase_snake_case_name>
  cad/           STEP parts and assemblies, Fusion F3D archive
  print/         3MF print projects and STL meshes
  source/        generator scripts, parameters, geometry inputs
  fusion/        Fusion 360 script packages (folder and module names fixed by Fusion)
  docs/          package documentation as delivered, paths updated
  verification/  validation records, build reports, BOM/catalogs, sha256sums.txt
  preview/       rendered previews
  reference/     electrical reference tables and provenance
```

Every family carries `verification/sha256sums.txt` (relative paths, same
hashes as `manifest.json`). Files are stored byte-for-byte (`.gitattributes`
disables line-ending conversion), so hashes are stable on every platform.

## Families

| Family | What it is | Status label | Start here |
| --- | --- | --- | --- |
| [`rover-v3/`](rover-v3/) | Full PLA chassis: 230 × 230.8 mm lower base, 168 × 210 mm service deck, rails, posts, standoffs, spacers. Fusion builder + motion/exploded-view script. | Digitally checked prototype. C1 motor-corner coupon physically tested (project record). Native Fusion build completed 2026-10-20. Chassis not printed. | [`rover-v3/docs/start_here.txt`](rover-v3/docs/start_here.txt) |
| [`motor-retrofit-r1/`](motor-retrofit-r1/) | Motor-block adapters for the printed V2 P1B chassis (11 mm end-ward offset, 0–18 mm lateral slot). R2 variant has no documentation. | Digitally checked prototype; physical fit pending (R1). R2 unassessed. | [`motor-retrofit-r1/docs/motor_adapters_r1_guide.md`](motor-retrofit-r1/docs/motor_adapters_r1_guide.md) |
| [`rover-v2-p1/`](rover-v2-p1/) | Box chassis, cover, Pi/UNO/servo carriers (STEP + sliced PETG project). | P1B chassis physically printed (evidence: retrofit guide and user measurements). No source scripts or assembly guide were located. | [`rover-v2-p1/cad/`](rover-v2-p1/cad/) |
| [`body-v0.3-wheelbase76/`](body-v0.3-wheelbase76/) | Six-panel body for the explorer deck, corrected to the measured 76.2 mm wheel-screw spacing. Open wheel bays, fit templates. | Digitally checked prototype (12 regression tests in source environment). Not printed. | [`body-v0.3-wheelbase76/docs/start_here.md`](body-v0.3-wheelbase76/docs/start_here.md) |
| [`body-v0.2-full/`](body-v0.2-full/) | First six-panel removable body on the explorer deck. | Digitally checked prototype; superseded (wheel arches assume 114 mm tire spacing). | [`body-v0.2-full/docs/start_here.txt`](body-v0.2-full/docs/start_here.txt) |
| [`explorer-v0.1/`](explorer-v0.1/) | Slotted deck, 36 mm spacers, side/front guards, carriers, optional Pi tray on the stock acrylic chassis. | Digitally checked prototype. Later docs imply the deck, spacers and Pi tray were installed; no direct fit record. | [`explorer-v0.1/docs/start_here.txt`](explorer-v0.1/docs/start_here.txt) |
| [`roof-battery-v2/`](roof-battery-v2/) | Roof-mounted snap-lid battery tray, spacers, latch and fit coupons. | **Unverified**: geometry-only exports, no documentation found. | [`roof-battery-v2/print/`](roof-battery-v2/print/) |
| [`service-hatch-v4/`](service-hatch-v4/) | Right side panel with a service hatch (124 × 166 × 21 mm, same envelope as the v0.3 right side). | **Unverified**: single export, no documentation; purpose inferred from the filename only. | [`service-hatch-v4/print/`](service-hatch-v4/print/) |

Labels mean: *concept* = no geometry checks on record; *digitally checked
prototype* = source environment ran solid/mesh/interference checks and this
repository re-parsed the files; *physically tested* = a print was fitted to the
rover and the result is recorded. Nothing here is labelled physically tested
for a whole chassis.

## Rover V3 parts

Printed parts (21 pieces, 7 unique designs), all PLA, from
[`rover-v3/docs/start_here.txt`](rover-v3/docs/start_here.txt) and
[`rover-v3/verification/component_catalog.csv`](rover-v3/verification/component_catalog.csv):

| Part | Qty | Purpose | Editable source | Printable export | Status |
| --- | --- | --- | --- | --- | --- |
| Full lower chassis (`base`) | 1 | 230 × 230.78 × 5.1 mm base; C3 motor pockets, bank strap slots | `source/build_printed_rover.py`, STEP in `fusion/RoverFusion/assets/printed/base.step` | plate 1 of `print/full_rover_x1c_pla.3mf` | digitally checked; motor corner derived from tested C1/C3 coupon |
| Upper service deck (`upper_deck`) | 1 | 168 × 210 mm deck with motor-battery slider pocket | same | plate 2 | digitally checked |
| Power-bank rail (`bank_rail_left/right`) | 2 | retains the flat power bank (non-kit item) | same | plate 2 | digitally checked |
| Deck support post | 6 | Ø12 × 40.5 mm, 3.4 mm bore | native recipe in `assembly_manifest.json` + STEP | plate 2 | digitally checked |
| Pi standoff | 4 | Ø8 × 6 mm, 2.8 mm bore (non-kit board) | native recipe + STEP | plate 2 | digitally checked |
| UNO standoff | 3 | Ø8 × 6 mm, 3.4 mm bore | native recipe + STEP | plate 2 | digitally checked |
| Line-tracker spacer | 4 | Ø7 × 3 mm, 3.2 mm bore | native recipe + STEP | plate 2 | digitally checked |

Kit hardware modelled as reference envelopes (39 solids in
`fusion/RoverFusion/assets/hardware/`, nominal unless noted):

| Kit item | Envelope files |
| --- | --- |
| TT gearmotors with aluminium mounting blocks (4) | `motor_*`, `motor_can_*`, `shaft_*`, `block_*` (block 22 × 12 × 4 mm measured) |
| Wheels and tires (4) | `wheel_hub_*`, `tire_*` |
| Arduino UNO R3 + SmartRobot shield | `uno_board`, `uno_board_connectors`, `motor_shield`, `shield_connectors` |
| Battery pack with switch | `motor_battery`, `motor_battery_switch` |
| Pan servo, horn, head bracket | `pan_servo`, `servo_horn`, `sensor_head` |
| HC-SR04 ultrasonic | `ultrasonic_board`, `sonar_transducers` |
| ESP32 camera module | `camera_board`, `camera_lens` |
| ITR20001 line-tracking module | `line_tracker`, `tracker_sensors` |

Removed non-kit envelopes: `pi_board`, `pi_board_connectors`, `pi_processor`,
`power_bank` (still present inside the archived `cad/complete_assembly.step`
and `cad/complete_assembly.f3d`, which were exported before the removal).

## Fusion scripts

* **RoverFusion** (builder 3.0.1): `fusion/RoverFusion/`. Builds the assembly
  from the STEP assets, 17 native parametric posts/standoffs/spacers, 59 joints
  (54 rigid, 5 revolute: four wheels, head pan). Instructions in
  `rover-v3/docs/readme_fusion.txt`. The recorded 2026-10-20 run used Fusion
  2705.1.30 and produced `cad/complete_assembly.f3d`
  (report: `verification/build_reports/fusion/20261020T213050_475130Z/`).
  Three earlier runs failed on a root-component rename; 3.0.1 fixed that.
* **RoverMotion** (1.1.0): `fusion/RoverMotion/`. Wheel rotation, turn-in-place,
  sensor pan and exploded views in a separate presentation document. Motors
  stay whole units; the UNO/shield stays one board. 1.0.1 added the file-URI
  palette fix for the Windows `ERR_INVALID_URL` problem; the 1.0.1 run report
  shows the palette URL and no error, but palette rendering is not confirmed by
  the report. 1.1.0 (this repository) removes the Pi and power-bank units and
  has **not** been run in Fusion. `fusion/history/rovermotion_1.0.0.py` is the
  pre-fix script kept for diff evidence.
* Install: Fusion → Utilities → Scripts and Add-Ins → Scripts → `+` → select
  the `RoverFusion` or `RoverMotion` folder (keep folder and file names).
* Offline checks (no Fusion needed): `python fusion/validate_bundle.py`,
  `python fusion/verify_preflight.py`, `python fusion/tests/verify_motion.py`,
  `python fusion/tests/verify_fusion_boundary.py` (run from `rover-v3/`).

## Regenerating exports

* Rover V3 printed parts: `python rover-v3/source/build_printed_rover.py`
  (CadQuery 2.7, NumPy; writes under `rover-v3/cad/generated/`). Hardware
  envelopes: `python rover-v3/source/build_hardware.py` (still generates the
  Pi and power-bank envelopes if run; delete them afterwards to stay kit-only).
* Body v0.3: `python source/build_revision.py --output rebuilt` and
  `python source/test_revision.py` from `body-v0.3-wheelbase76/`.
* Body v0.2 / explorer v0.1: `python source/build_full_body.py --output rebuilt`
  and `python source/build_explorer.py --output rebuilt` (CadQuery 2.7,
  requirements in each `source/requirements.txt`).
* Retrofit R1: `python source/motor_adapters_r1.py` (writes `cad/` and `print/`).
* None of the CadQuery generators were executed in this repository (CadQuery
  is not installed here); their path literals were updated for the layout and
  the scripts compile. A regenerated STEP is not the archived STEP until its
  hash is checked.

## Previews

| View | Image |
| --- | --- |
| Rover V3 full assembly (CAD render) | [`rover-v3/preview/full_assembly.png`](rover-v3/preview/full_assembly.png) |
| Body v0.3 assembled / side / fit templates | [`revised_rover_v3.png`](body-v0.3-wheelbase76/preview/revised_rover_v3.png), [`revised_side_view.png`](body-v0.3-wheelbase76/preview/revised_side_view.png), [`fit_templates_installed.png`](body-v0.3-wheelbase76/preview/fit_templates_installed.png) |
| Body v0.2 assembled / exploded / printed parts only | [`full_body_preview.png`](body-v0.2-full/preview/full_body_preview.png), [`full_body_exploded.png`](body-v0.2-full/preview/full_body_exploded.png), [`full_body_parts.png`](body-v0.2-full/preview/full_body_parts.png) |
| Explorer v0.1 assembled / exploded / stock | [`explorer_preview.png`](explorer-v0.1/preview/explorer_preview.png), [`explorer_exploded.png`](explorer-v0.1/preview/explorer_exploded.png), [`stock_reference_preview.png`](explorer-v0.1/preview/stock_reference_preview.png) |
| Retrofit R1 plate | [`retrofit_r1_plate_closeup.png`](motor-retrofit-r1/preview/retrofit_r1_plate_closeup.png) |

No exploded or printed-parts-only render exists for Rover V3; RoverMotion
produces those views live in Fusion.

## Third-party material

ELEGOO's schematic archive and vendor datasheets are not stored here. Pinned
sources and retrieval steps: [`reference/README.md`](reference/README.md).
