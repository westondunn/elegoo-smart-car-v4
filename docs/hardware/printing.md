# Printing (Bambu Lab X1 Carbon)

Every project file was opened and classified by inspecting its contents
(`Metadata/project_settings.config`, `slice_info.config`, G-code entries).
Three kinds exist:

* **sliced project** – Bambu Studio project with printer, filament and
  process presets and G-code for every plate;
* **unsliced project** – presets present, no G-code;
* **geometry-only 3MF** – meshes in millimetres, no printer configuration.

Estimates are the slicer's own numbers, not measured print times.

## Rover V3 production project

[`rover-v3/print/full_rover_x1c_pla.3mf`](../../hardware/3d-models/rover-v3/print/full_rover_x1c_pla.3mf)
is a sliced project: X1 Carbon, 0.4 mm nozzle, Generic PLA, process
"Rover V3 Full 0.15mm PLA Strength", Textured PEI plate (55 °C), 220 °C nozzle,
0.15 mm layers including the first, 6 walls, 6/6 top/bottom layers, 35 % gyroid,
supports off, 2 mm outer brim. The base sits at plate XY (22, 20) mm to clear
the X1C cutter exclusion.

| Plate | Objects | Estimate |
| --- | --- | --- |
| 1 "01 FULL LOWER CHASSIS" | lower chassis (230 × 230.78 × 5.1 mm) | 5 h 31 min, 164.56 g |
| 2 "02 DECK RAILS AND STANDOFFS" | deck, 2 rails, 6 posts, 4 Pi standoffs, 3 UNO standoffs, 4 spacers (20 objects) | 5 h 31 min, 160.30 g |

Two production plates is the project's goal; it has not been printed, so it is
not an achieved result. Open the file with File → Open Project, keep the
presets, confirm the physical plate, use Slice All only if something changed,
then Send All. Full workflow: [`rover-v3/docs/bambu_workflow.txt`](../../hardware/3d-models/rover-v3/docs/bambu_workflow.txt).

## Fit-check jobs (count separately from production)

| File | Contents | Settings | Estimate | Print status |
| --- | --- | --- | --- | --- |
| `rover-v3/print/fit_checks/c1_motor_fit_x1c_pla.3mf` | C1 motor corner (66 × 115 × 4.5 mm) | 0.15 mm, 5 walls, 100 % zig-zag | 53 min, 29.45 g | printed and tested per project record (pocket 7.4 × 3.3 selected from it) |
| `.../c2_washer_gauge_x1c_pla.3mf` | 7.4 mm washer gauge | same | 15 min, 3.11 g | unknown |
| `.../c3_motor_seat_and_battery_rail_x1c_pla.3mf` | C3 seat reference + recessed battery rail | same | 30 min, 9.99 g | unknown |
| `.../c3_motor_corner_and_battery_rail_x1c_pla.3mf` | full C3 corner from C1 + battery rail | same | 1 h 08 min, 36.23 g | unknown |
| `.../fit_batch_x1c_pla.3mf` | washer gauge, flat-battery XY frame, Pi 58 × 49 pattern, motor-battery pitch, hardware selector | same | 1 h 28 min, 35.22 g | unknown |

## Other families

| File | Kind | Settings | Estimate |
| --- | --- | --- | --- |
| `motor-retrofit-r1/print/motor_retrofit_r1_x1c_pla.3mf` | sliced, 1 plate, 8 objects | PLA 0.20 mm, 5 walls, 100 % zig-zag, 2 mm brim | 46 min, 12.67 g |
| `motor-retrofit-r1/print/motor_retrofit_r2_x1c_pla.3mf` | sliced, 2 plates ("fit check first" B2; "remaining three") | same | 18 min + 39 min, 3.37 + 9.47 g |
| `rover-v2-p1/print/p1b_x1c_all_plates_petg.3mf` | sliced, 3 plates | Generic PETG 0.20 mm, 5 walls, 25 % gyroid, 4 mm brim, 255/70 °C | 6 h 57 min + 4 h 49 min + 40 min; 238.27 + 176.80 + 14.01 g |
| `rover-v2-p1/print/p1b_x1c_all_plates_pla_unsliced.3mf` | unsliced re-save | Generic PLA, "0.20mm Standard @BBL X1C", High Temp Plate | — |
| `rover-v2-p1/print/plate_1_p1b.3mf` | geometry only | — | — |
| `explorer-v0.1/print/*.3mf`, `body-v0.2-full/print/*.3mf`, `body-v0.3-wheelbase76/print/*.3mf`, `roof-battery-v2/print/*.3mf`, `service-hatch-v4/print/*.3mf` | geometry only (mm) | choose printer and PLA profile in Studio; the packages suggest 0.4 mm nozzle, 0.20 mm layers, 4 walls, 20–25 % infill, 4 mm brim on large panels | — |

STL files carry no units; all of them match their STEP/3MF counterparts in
millimetres (bounding boxes in
[`hardware/3d-models/validation/validation_report.json`](../../hardware/3d-models/validation/validation_report.json)).
Do not scale any part to make it fit: every motor and board interface would
change with it.
