# Known issues and open questions

## Unverified or missing inputs

* **Rover V3 chassis never printed.** Only the C1 motor-corner coupon has a
  recorded physical test. The fit batch, C2, C3 and full plates have no print
  record.
* **Non-kit hardware removed from the Fusion package.** `assembly_manifest.json`,
  `part_catalog.json` and the offline tests now describe 60 components; the
  archived `cad/complete_assembly.step` and `.f3d` still contain the Pi and
  power-bank envelopes. Re-running RoverFusion produces a 60-component design.
  RoverMotion 1.1.0 ignores unknown components when run on the old
  64-component design (its matcher only collects catalogued IDs) but this has
  not been exercised in Fusion. `source/build_hardware.py` still generates the
  removed envelopes if run.
* **Generators not executed here.** CadQuery is not installed; every path
  patch was compile-checked only. Regenerated exports must be hash-compared to
  the archived files before replacing them.
* **Missing originals.** `Rover_V3_Fusion_Personal_Project_R1.zip` was not
  found (only the extracted folder). `ELEGOO_V4_Complete_CAD_and_Print_Files.zip`
  is a truncated download and cannot be opened. No documentation, source or
  validation record exists for `roof-battery-v2`, `service-hatch-v4`,
  `rover-v2-p1` or retrofit R2.
* **Historical records reference old names and hashes.** Files under
  `rover-v3/verification/original_package/`, the build reports, and the older
  packages' `*_validation.json`, `component_manifest.json`, `body_manifest.json`
  and `verification/manifest.json` keep the pre-normalisation file names and
  source-script hashes. The pre-normalisation bytes are commit 33baab6.
* `package_contents.json` lists `RoverMotion.py` 1.0.0 while the package ships
  1.0.1; two validation JSONs also differ from the list.

## Unresolved fit questions

* **Wheelbase / axle positions** differ between revisions (114 mm estimated,
  76.2 mm measured screw spacing, OEM bracket pattern in V3) and were not
  reconciled. V3 wheel axes are display axes, not measured shafts. See
  [revisions.md](revisions.md).
* **Flat power bank width**: 69.85 mm in the project record versus 95.25 mm in
  the task brief. The V3 rails are built for 73.025 mm clear width.
* **Charging / Micro-USB access with the body installed** (the right side had
  to be removed on the earlier body). V3 relocates the motor-battery connector
  area to the rear deck and leaves the power-bank rail centres open, but plug
  access was never checked physically. The v4 service hatch is undocumented.
* **Front floor-sensor cable reach** is not addressed by any revision's
  documentation; V3 provides cable windows but no cable-length check.
* **Motor battery pitch**: the 65–90 mm slot covers the OEM nominal 76 mm; the
  actual pack spacing and lug thickness are unmeasured.
* **Pi and UNO board revisions** are unconfirmed; connector envelopes are
  representative (relevant to the deck windows and standoff heights).
* **Servo travel** limits (−80/+80°) are illustrative, not measured stops.
* **Support post at X48, Y0** sits under the UNO; the deck must be bolted
  down before the UNO is installed.
* **V2 P1B chassis** (the printed one) required the motor retrofit; the
  retrofit itself is physically unfitted. Ground clearance drops from about
  24 mm to about 20 mm with the adapters.

## Fusion / tooling

* RoverFusion run 3.0.1 completed with warnings: no PLA physical material in
  the library (assign manually) and colour appearance assignment failed
  ("invalid name") for all 64 parts.
* RoverMotion 1.0.1 fixed the Windows `ERR_INVALID_URL` palette problem by
  passing a file URI; the run report shows the URI and no error, but does not
  prove the panel rendered.
* The builder writes new runs to `fusion/RoverFusion/output/<timestamp>/`
  (names `Rover_V3_Full_Assembly.f3d`, `Rover_V3_BOM.csv`); archived copies
  were renamed into `cad/` and `verification/build_reports/`.

## Repository

* Total model payload is about 137 MB in ordinary Git (largest file 13.9 MB).
  Cloning fetches everything; Git LFS was deliberately not introduced
  ([decisions.md](decisions.md)).
