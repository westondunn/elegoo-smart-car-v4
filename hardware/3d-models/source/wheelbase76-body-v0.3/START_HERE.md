# ELEGOO V4 — body correction for the measured 76.2 mm wheelbase

**Body revision 0.3.0 · October 14, 2026 · Units: millimeters · PLA prototype**

This is a correction to the earlier full-body model, not a change to your real rover's motor positions. Keep the deck, four tall spacers, Pi tray, roof, rear panel and roof-mounted snap-lid battery holder that already fit or were previously designed. The replacement body has **one continuous open-bottom wheel bay on each side**, with no body strip between the tires.

## Start with the small fit templates

1. Open **`print/00_wheel_bay_fit_checks.3mf`** in Bambu Studio. It contains a left and right template; print either side first or both together. Select your printer and established PLA profile. The package contains geometry, not a printer profile or G-code.
2. Disconnect the rover battery and the Pi-to-UNO USB cable before fitting parts. Keep the deck and Pi mount in place. These templates use the same two side-guard/body holes on each side of the custom deck; they do **not** replace the four tall deck spacers or their screws.
3. Put each template's horizontal tabs **under the deck**, with the long rail on the outside. The small downturned leg goes toward the **rear**. Use two M3 × 10 mm machine screws and two M3 nuts per side, as used by the prior body tabs. Check screw engagement and clearance on the actual build; tighten gently.
4. The **bottom edge of the long rail** represents the new side body's wheel-opening ceiling. Turn both wheels through a complete revolution and check the rear leg as well. Check with the actual tire movement and normal, light side-to-side play. Nothing should rub. The model has about **9.2 mm nominal space above the tire**; use **at least 4 mm physically measured clearance** as this prototype's initial fit target, not as a general safety standard. Stop and report a mismatch rather than forcing the mount.
5. Two small V-notches in the rail mark the **inferred** axle-center positions. Check their approximate alignment with the wheel screws. The wide opening tolerates some offset, but a notable shift should be corrected before accepting the reference as calibrated.
6. Route the USB cable and head wiring above/away from the wheels, without tension on their connectors. Remove the templates before powered movement: they are temporary fit tools, not operating guards.
7. Only after this test, print the replacement body panels. Keep the earlier roof and rear panel.

See `preview/fit_templates_installed.png` for orientation. Each template is roughly **4.95 cm³ of CAD solid volume**, compared with 30–34 cm³ for a full side panel. This is not a slicer filament or print-time estimate.

## Print only these four replacement panels

| Part | Bambu Studio file | Action |
|---|---|---|
| Left side | `print/01_left_side_v3.3mf` | Replaces old left side; continuous open wheel bay |
| Right side | `print/02_right_side_v3.3mf` | Replaces old right side; continuous open wheel bay |
| Front bulkhead | `print/04_front_bulkhead_v3.3mf` | Lower edge raised for wheel clearance; mounting holes unchanged |
| Front cowl | `print/06_front_cowl_v3.3mf` | Lower skirts relieved around the corrected front-wheel region |

**Unchanged:** custom slotted deck, four 36 mm spacers, Pi tray and its short spacers, front guard and its 4 mm shims, rear body panel, removable roof, snap-lid battery tray/lid and four 8 mm roof spacers. Do not reprint those to fix this wheelbase issue. Byte-identical copies of the previous rear-panel and roof 3MFs are in `print/unchanged/` for convenience.

The six-panel body still requires the earlier custom front guard and its two 4 mm shims. Use those files from your original rover package if not already printed. The cowl uses that guard's mounting interface; it is not a direct replacement for the bare acrylic chassis.

Do not stretch or scale the complete model, change actual wheel spacing, or relocate the motors to make a body fit.

## Dimensions and what is known

| Quantity | Nominal model value | Evidence |
|---|---:|---|
| Tire outer diameter | 64.77 mm | User's approximately 2.55 inches |
| Tire width | 27.94 mm | User's approximately 1.10 inches |
| Front-to-rear wheel-screw spacing, same side | 76.20 mm | User's 3 inches, explicitly clarified |
| Tire-to-tire gap | 11.43 mm | Spacing minus diameter |
| Outer front-to-rear span of the tire pair | 140.97 mm | Spacing plus diameter |
| Wheel bay | Y = −90 to +90; top at Z = 74 | New design allowance, original rover coordinates |

These are exact unit conversions of rounded measurements, **not claims of hundredth-millimeter measurement accuracy**.

### Axle alignment is not assumed to be the plate center

The supplied lower-plate data place the mirrored motor-bracket patterns at approximately **Y = +59.622 and −63.526 mm**. Their midpoint is **−1.952 mm**. Assuming identical, oppositely oriented gearmotors, the axle pair shares that midpoint. With a 76.2 mm wheelbase, the reference axle positions are therefore approximately **+36.148 and −40.052 mm**.

This is a **reasoned estimate**, not a directly measured shaft location: the supplied chassis mesh contains bracket holes, not motor internals or a shaft datum. Lateral wheel centers and chassis height retain earlier reference assumptions. The new open bay and physical templates deliberately avoid relying on the old tight, separate wheel arches. Source hole indices and calculations are recorded in `verification/axle_alignment_evidence.json`.

## Fasteners and installation

No new fastener sizes are introduced by this correction:

- Side panels to deck: **4 × M3 × 10 mm**, with M3 nuts. These are separate from the Pi board's M2.5 screws.
- Front and rear end panels to side tabs: **8 × M3 × 12 mm**, with M3 nuts.
- Front cowl/guard: existing **2 × M3 × 20 mm**, retaining the original guard and two 4 mm guard shims.
- Roof by itself: **4 × M3 × 10 mm**, with retained roof nuts.
- With the snap-lid battery mount: its prior **4 × M3 × 20 mm**, washers, **8 mm roof spacers**, and captive roof nuts remain unchanged. Do not omit the spacers.

Assemble side panels, end panels and cowl before installing the roof/battery holder. With all power disconnected, check wheel rotation, cable movement and the camera/sonar head sweep. The files do not validate the actual USB plug, loose wires, or the sensor's full field of view. Snug metal hardware by hand; do not crush the PLA or force screws into a tight print.

For inherited details such as the roof-nut insertion sequence, `reference/PREVIOUS_v02_assembly_instructions.txt` is included. **Its old wheel dimensions and old clearance claims are superseded by this release.** It is background documentation, not new validation.

## Print orientation and PLA starting settings

Use your established PLA profile. A starting setup is a 0.4 mm nozzle, 0.20 mm layers, four perimeters and approximately 20–25% infill. Side panels, gauges and front bulkhead are oriented broad exterior face down; the cowl is bonnet-face down. Inspect layers, nut channels, small bridges and tabs in the slicer; use local supports where your process requires them. No physical support-free claim is made.

All **new** part geometries fit a 180 × 180 mm area with a 4 mm brim. The side panels' longest footprint dimension is 166 mm; the two fit templates are arranged together on one plate. Do not scale to correct a hole or local fit. Adjust the specific CAD feature instead.

## Fusion / CAD files

- **`cad/rover_body_v3_with_snap_battery.step`** — corrected full rover reference, with the unchanged snap-lid battery mount; **206 named components**.
- **`cad/body_shell_v3.step`** — all six body panels in their installed positions, including unchanged roof and rear panel.
- **`cad/open_rover_v3_reference.step`** — open-rover reference with corrected wheels, excluding the body and roof-mounted battery assembly.
- Individual new panels and fit templates are supplied as STEP and STL in their print orientations.

STEP supplies solid geometry and component names, not a native Fusion feature timeline, parameter table or joints. Imported assemblies include simplified, nonprintable reference electronics, motors, tires, batteries and metal fasteners. **Do not print the whole assembly.** Use the individual print files.

`reference/previous_rover_roof_snap_v2.step` is the **old source snapshot used to preserve existing geometry**. It deliberately retains the old wheelbase; do not use it as the updated model. The new CAD files are under `cad/`.

## Checks performed

The actual build and regression logs are under `verification/`:

- All four tires in the exported assembly have the nominal 64.77 × 27.94 mm dimensions and 76.2 mm spacing.
- **166 components retained their prior geometry/position**; four body panels and 36 simplified drivetrain/reference components were revised. Motor movement in the CAD is not an instruction to move real motors.
- **16 local mounting-interface regions** on the revised side panels match the previous geometry.
- No positive-volume body interference against the retained reference assembly above the review threshold of 0.01 mm³.
- Minimum nominal body-to-tire separation: approximately **9.23 mm**.
- A conservative bounding box enclosing tire radius increased by 3 mm, axle-pair Y translation ±8 mm, axle Z translation ±2 mm, and an extra 3 mm on each tire's X face retains at least **4.23 mm** to the body. These are **design-check allowances**, not measured tolerances or a guarantee for unmeasured hardware.
- The inherited conservative rigid-head sweep and nominal service-access probes were rerun against the revised panels; the minimum rigid-head separation remains approximately **7.39 mm**.
- Six new printable parts are valid single CAD solids and closed, consistently oriented single-component STL meshes.
- Five new 3MF packs were checked with the included Core-format validator and independently imported with trimesh. STEP assemblies and parts were reimported for names, dimensions, volume and solid validity.
- **12 regression tests passed** against exported files, including preserved-part checks and nonblank rendered previews.

Previews come from the actual CAD geometry. Nothing has been physically printed or fit-tested here. Native Fusion/Bambu GUI import, actual slicing, load/impact capacity, thermal behavior, battery retention cycling, real cable clearance and on-rover operation remain untested. This is a fit-check-first prototype.

## Source and reproducibility

Keep the source and reference folders in place. The source preserves the previous geometry and applies localized replacements.

```bash
python -m pip install -r source/requirements.txt
python source/build_revision.py --output rebuilt
python source/test_revision.py
```

The regression script checks the delivered package by default. Use `python source/test_revision.py --root rebuilt` to check a separate rebuild; it still compares against the original reference snapshot beside the source folder. Build-time geometry and export validations also run for the selected output path. Preview tests apply to images present in that output tree.

Actual-CAD preview rendering is optional:

```bash
python -m pip install -r source/requirements-render.txt
python source/render_revision.py
# On headless Linux where needed:
xvfb-run -a python source/render_revision.py
```

Python 3.11 or newer is recommended for reproducing this captured dependency set; the delivery was tested with the versions pinned in the requirements files. No code here accesses the rover, GitHub, Home Assistant, or a printer.
