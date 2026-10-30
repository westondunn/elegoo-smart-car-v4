ROVER V3 - AUTODESK FUSION PERSONAL PROJECT BUILDER
Prepared 2026-10-20

START HERE

This package supplies the complete assembly geometry as STEP solids and a
desktop Fusion script that builds a native assembly. A .f3d archive is produced
by Fusion when the script runs successfully on your computer. The script has
been checked offline; Autodesk Fusion is not installed in the preparation
environment, so desktop execution and native F3D export remain to be performed.

This is the CAD/electronics package. The separate Rover_V3_Full_X1C_PLA.3mf is
the two-plate print project. project_context contains the shared quick-start,
project instructions, assembly/hardware notes, final interference reports,
actual CAD assembly preview and Bambu transfer workflow for reference.

The imported main chassis preserves the supplied mechanical CAD. The package
contains 64 named components. Seventeen printed instances have native feature
recipes: six support posts, four Pi-pattern standoffs, three UNO-pattern
standoffs and four line-tracker spacers. These use native sketch dimensions,
extrusions and bore cuts. The other 47 components import exact STEP geometry.
Each component's actual build method is recorded separately when Fusion runs.
The CadQuery construction source and its required geometry inputs are supplied
in mechanical_source; imported parts do not acquire that history in Fusion.

OPEN THE COMPLETE GEOMETRY IMMEDIATELY

Rover_V3_Complete_Assembly.step contains all 64 named components in their
assembled positions. Open or upload this file in Fusion to inspect the solid
geometry without running the script. It was exported and re-imported through
OpenCascade: 78 solids were valid, with a total volume difference below
0.001 mm3. STEP contains geometry, component names and colours; it does not
carry the Fusion joint definitions or the native parametric feature recipes.

CREATE THE NATIVE ASSEMBLY IN FUSION

1. Extract the whole package to a normal local folder. Keep RoverFusion.py,
   RoverFusion.manifest, manifest_tools.py, native_features.py,
   assembly_manifest.json and the assets folder together inside RoverFusion.

2. Open Autodesk Fusion desktop and enter the Design workspace. Open Utilities
   > Scripts and Add-Ins, choose the Scripts tab, and add an existing script.
   Select the RoverFusion folder. Select RoverFusion in the list and click Run.
   Menu wording may vary slightly between Fusion releases; search for
   "Scripts and Add-Ins" if needed.

3. The script validates the manifest and all referenced STEP files before it
   creates a new design. It imports the parts, builds supported native feature
   recipes, applies appearances and available physical materials, grounds the
   base, and creates the assembly joints. Existing open designs are untouched.

4. On success, the message gives the local output folder. Each run has its own
   timestamped folder under RoverFusion/output. It contains:
     - Rover_V3_Full_Assembly.f3d: the actual native Fusion archive.
     - Rover_V3_BOM.csv: an ordinary component list for this assembly.
     - fusion_build_report.json: individual imports, native features, physical
       material results, joint results, warnings and archive checksum.
   If the extracted folder cannot be written to, a temporary output folder is
   used and its complete path is shown.

5. Save the open design in Fusion to your chosen project. All parts are internal
   components of this one design; the builder creates no linked external design
   documents. Keep the generated local F3D as a portable backup.

WHAT IS EDITABLE

Native recipe parts
  The manifest's native_recipe entries identify the exact supported parts.
  Intended native geometry includes round support posts and board standoffs:
  an outside-diameter sketch, extrusion height, a through-bore sketch and cut.
  Recipes also support rectangular extrusions, outside corner rounds, holes,
  rectangular openings and straight capsule slots/pockets when supplied.
  Modify > Change Parameters shows their named DRIVING NATIVE FEATURE values.
  Changing diameter, bore or height rebuilds those native features.

  Their initial solid must match the source STEP reference bounding box and
  volume within the documented tolerances. This check catches unit, placement
  and dimension errors; it is not a full geometric equivalence proof. If the
  installed Fusion version rejects a recipe or this check fails, that component
  is replaced by its supplied STEP solid. The build report clearly records
  that fallback. Only entries listed under native_parametric_parts in the
  actual desktop report should be treated as successfully built native parts.

Imported main base, deck, rails and hardware reference solids
  These are editable solid BRep geometry inside native components. STEP does
  not encode the source sketch/extrusion/fillet history. You can add new Fusion
  sketches, holes, cuts, fillets and direct face edits to these solids. Existing
  imported shape dimensions do not automatically respond to reference user
  parameters. Use the supplied mechanical source to regenerate the complete
  body family, or deliberately build new Fusion features on the imported body.

Reference parameters and construction sketches
  Comments start with REFERENCE. These document clearances, mounting patterns
  and design intent. Editing them alone does not resize an imported STEP body.
  Reference sketches are hidden by default and contain construction geometry.

Assembly placement
  The supplied assembly uses as-built positions. Native post height changes
  reshape a post; they do not automatically lift the upper deck or change all
  dependent component locations. Review the deck and joint positions when
  changing stack height. Run the master mechanical generator for a coordinated
  layout change. Re-running this builder creates a fresh design, so preserve
  any manual Fusion edits in a separately saved version.

JOINTS AND MOTION

The builder grounds the base and defines 63 native joints: 58 rigid joints and
five revolute joints. Four wheel hubs have the wheel revolute definitions; the
tyre for each wheel moves rigidly with its hub. The fifth revolute definition
is the camera/sonar head pan joint. Pi/UNO standoffs connect rigidly to the upper
deck. The manifest is one connected constraint tree with no active cycles.

The wheel and servo axes are nominal reference axes until checked against the
actual installed hardware. The servo travel limits in the manifest illustrate
motion and are not measured mechanical stop angles. Right-click a revolute
joint in Fusion and use Drive Joint to inspect motion. No friction, tyre-ground
contact, motor torque, vibration, stability or collision simulation is implied
by the joints. There is no automatic electrical-to-mechanical motor simulation.

The motor-battery mounting rail has one fixed hole and an elongated hole for
mounting-pitch adjustment. The installed battery is rigidly secured. Its slot
does not give the entire fastened battery a free sliding degree of freedom.
This installed assembly does not define a battery slider joint.

MATERIALS AND APPEARANCES

PLA is the intended print material. The script searches the loaded Fusion
material libraries for a matching PLA physical material and copies a matching
definition into the design. Steel, aluminum and rubber intents for hardware
are nominal unless the component information explicitly says otherwise.

If a named physical material is unavailable, the script retains the material
intent as component metadata and records unresolved_material_intent in the
report. It does not substitute a different polymer and relabel it PLA. Use
Modify > Physical Material to assign the material you actually print. A custom
material should use your filament supplier's data and clearly identify any
assumed properties.

If you need to create a PLA entry:
  1. Open Manage Materials in the Design tools/utility commands. Work in
     Favorites or a custom library, where materials are editable.
  2. Create a material or duplicate a plastic template. Give it a clear name
     such as "My PLA - density reference only" until its properties are known.
  3. In its Physical properties, set Density from your actual filament data.
     If you use the supplied Generic PLA print-profile assumption instead,
     label it "Nominal PLA - 1.24 g/cm3 - density only". That value equals
     1240 kg/m3 or 0.00124 g/mm3; enter the units shown by your material editor.
  4. In Identity/description, record the density source and state that copied
     stiffness, strength and thermal fields are unverified and must not be
     used for analysis. Changing density does not make the template's other
     physical fields correct for PLA or for your printed infill.
  5. Apply the changes, then use Modify > Physical Material to drag the new
     material onto the printed components. Save the design. Appearance colours
     can remain as assigned. The generated report describes the initial script
     run; it does not automatically update after manual edits.

Named colour appearances are assigned separately. Colour does not establish
physical density or mechanical properties. PCB assemblies, battery packs and
other composite reference components deliberately have no single verified
bulk material. Fusion may still display its own default material properties;
those defaults are not calibrated hardware masses.

A solid PLA CAD volume is also different from a sliced print with walls and
infill. Do not use this assembly's default mass, centre of gravity or material
strength as a validated prediction of the printed rover. The print project's
slicer estimates and measured hardware masses are the appropriate inputs for
later weight and balance calculations.

ELECTRONICS

The assembly includes separate reference components for the electronics and
existing hardware. Their fidelity notes distinguish measured outer sizes,
known mounting patterns and approximate connector/body envelopes. The actual
Pi generation, UNO/shield revision and some sensor dimensions remain
unidentified; the model does not certify their complete connector clearance.

electrical_reference contains the recovered original ELEGOO shield PDF and
manufacturer-supplied datasheets, the exact download provenance, a revision
comparison, and a functional harness reference. The original 2020 DRV8835
shield diagram and the newer firmware pin table differ. Keep the existing
working connections and match the physical board revision before using either
document as a pin assignment reference.

These PDFs and mechanical reference solids are not an editable Fusion
Electronics schematic or PCB. No verified netlist, board layout or custom
Pi-to-UNO connection is invented. See ELECTRICAL_REFERENCE.txt for the actual
source contents and the known revision difference.

PERSONAL EDITION SCOPE

See FUSION_PERSONAL_CAPABILITIES.txt and source_references.json. This workflow
uses standard design tools, internal components, native joints, scripts/API,
appearances, available physical materials and local native/STEP files. It does
not depend on a paid extension, cloud rendering, generative design or the
unavailable Personal simulation workspace. The CSV is a supplied component
list; it is not the paid Fusion Bill of Materials feature.

VALIDATION AND TROUBLESHOOTING

Offline checks cover Python syntax, safe relative asset paths, STEP headers,
asset checksums, rigid transforms, mm-to-cm conversion, native recipe inputs,
unique IDs, joint references and active connectivity to the grounded base.
Thirteen focused portable checks also exercise rejected scaling, reflections,
zero joint axes, conflicting constraints, escaped paths and altered assets.
These checks do not prove successful Autodesk runtime execution.

The desktop builder checks imported solids, native recipe initial bounds and
volume, timeline joint health and actual archive export. Any failure keeps the
partially created design open for inspection and writes a detailed report.
If a STEP is missing, restore the complete extracted package. If a material is
missing, assign it manually and save the native design. For a script failure,
send fusion_build_report.json along with the Fusion version; it identifies the
specific operation that failed.

For optional local preflight outside Fusion, use Python 3:
  python validate_bundle.py
  python verify_preflight.py
No Autodesk libraries are needed for those two portable checks. Run the
RoverFusion script itself only from inside Fusion desktop.
