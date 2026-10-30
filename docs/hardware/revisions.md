# Model revisions and lineage

All files live under [`hardware/3d-models/`](../../hardware/3d-models/).
Dates are the file dates in the source folder; "evidence" is what the imported
records actually show.

| Order | Family | Date | Built on | Evidence of acceptance |
| --- | --- | --- | --- | --- |
| 1 | `explorer-v0.1` | 2026-10-12 | stock acrylic chassis (reconstructed from ELEGOO plate STLs) | v0.3 docs say the deck, spacers, Pi tray and roof "already fit or were previously designed"; no fit record |
| 2 | `body-v0.2-full` | 2026-10-12 | explorer deck | digital checks only (`verification/body_fit_review.json`) |
| 3 | `roof-battery-v2` | 2026-10-14 | v0.2 roof | none (loose exports; `body-v0.3` reference snapshot `previous_rover_roof_snap_v2.step` includes it) |
| 4 | `body-v0.3-wheelbase76` | 2026-10-14 | v0.2, wheel bays corrected | 12 regression tests passed in the source environment; not printed |
| 5 | `service-hatch-v4` | 2026-10-15 | v0.3 right side | none |
| 6 | `rover-v2-p1` | 2026-10-17 to 19 | new printed box chassis (design direction change) | P1B chassis was printed and measured (retrofit R1 guide: ground clearance ~24 mm, wheel/body gap 14 mm, shaft/post gap 3 mm) |
| 7 | `motor-retrofit-r1` | 2026-10-19 to 20 | V2 P1B | CAD-only clearance review; "physical fit pending" |
| 8 | `rover-v3` | 2026-10-20 | new full PLA chassis widened to 230 mm, C1/C3 motor interface | C1 coupon marked "successful"/"tested" in `docs/project_instructions.txt`; native Fusion build completed; chassis unprinted |

## Wheelbase and axle conflicts (unresolved, not reconciled)

The reference geometry changed its wheel positions three times. None of these
values was changed during the import.

| Revision | Same-side wheel/axle spacing | Where it comes from |
| --- | --- | --- |
| explorer-v0.1, body-v0.2 | 114.0 mm (tire centres Y = +55.0 / −59.0) | estimated envelopes in `component_manifest.json` / `body_manifest.json` |
| body-v0.3 | 76.2 mm (axles inferred at Y = +36.15 / −40.05) | user-reported 3 in wheel-screw spacing, tires 64.77 × 27.94 mm; `verification/axle_alignment_evidence.json` |
| rover-v3 | motor bracket-hole pairs centred at Y = +59.62 / −63.53 (123.15 mm apart); nominal wheel axes at Y = +39.62 / −43.53 (83.15 mm apart) | OEM bottom-plate hole pattern in `source/assembly_layout.json`; axes are "illustrative placements", not measured shafts |

The task brief also carries a flat power bank of 146.05 × 95.25 × 12.7 mm.
The V3 project record uses 69.85 × 146.05 × 12.7 mm (2¾ × 5¾ × ½ in) and a
73.025 × 149.225 mm clear tray. The 95.25 mm figure appears nowhere in the
imported files; the rail spacing was not changed.

## What each revision says about the known constraints

| Constraint | explorer-v0.1 / body-v0.2 | body-v0.3 | rover-v2-p1 + retrofit | rover-v3 |
| --- | --- | --- | --- | --- |
| Micro-USB / charging access with the body on | v0.2 right side has "UNO and Pi connector passages"; user reports the right side had to be removed to charge | not addressed (right side only changed at the wheel bay) | no document; `service-hatch-v4` (2026-10-15) is probably the response but is undocumented | motor battery moved to the rear deck so its "plug, switch and charging-port area" sits above the motors; power-bank rail centres left open for plugs; "check actual plug access before tightening" (not verified) |
| Motor / axle alignment | estimated | inferred from bracket pattern; fit templates provided | P1B needed an 11 mm end-ward correction (retrofit R1) | OEM hole pattern retained; C3 pocket 7.4 × 3.3 mm with 1.8 mm floor from the tested C1 coupon |
| Wheel clearance | 4.0 mm nominal to tires | ≥ 9.2 mm nominal, ≥ 4 mm target physical | 14 mm measured on P1B (user) | not stated for the widened base |
| Battery support | roof snap tray (v2) | unchanged roof tray | `battery_tray_centered_73p025x149p225.step` | low centred tray with rails + two hook-and-loop straps; motor battery 65–90 mm pitch slot |
| Board mounting | optional Pi tray 58 × 49 pattern | unchanged | Pi/UNO carriers | Pi (58 × 49, "reported to fit") and UNO side by side on 6 mm standoffs |
| Service access | removable roof, end panels | same | cover | removable deck on six through-bolted posts; post at X48,Y0 is under the UNO: install the deck nuts before the UNO |
| Front floor-sensor cable reach | notches clear the carrier screw heads; cable reach not discussed | not discussed | not discussed | line tracker under the base on 3 mm spacers with the existing harness; "cable windows" provided; reach not verified |

## Script revisions on record

* `RoverFusion.py` builder 3.0.1: three runs on 2026-10-20 (21:24–21:26 UTC)
  failed with `RuntimeError: 3 : root component name cannot be changed`; the
  3.0.1 script (modified 16:30 local) then completed at 21:30 UTC with 21
  "PLA physical material unavailable" and 64 "colour appearance assignment
  failed: invalid name" warnings. Reports in
  `rover-v3/verification/build_reports/fusion/`.
* `RoverMotion.py` 1.0.0 → 1.0.1: adds `palette_uri()` (Windows file URI for
  the palette HTML). Two 1.0.0 runs and one 1.0.1 run reached stage `closed`
  with no warnings; the 1.0.1 report records `palette_url`. Whether the panel
  rendered is not recorded.
* `RoverMotion.py` 1.1.0 (this repository): Pi and power-bank units removed
  from the plan; offline tests updated and passing; not run in Fusion.
