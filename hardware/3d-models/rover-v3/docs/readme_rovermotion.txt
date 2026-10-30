ROVER V3 - MOTION AND ASSEMBLY VIEWS
RoverMotion 1.0.0 | Windows / Autodesk Fusion

This companion gives your existing Rover V3 model live wheel and sensor motion,
plus exploded assembly views that separate printed parts from whole purchased
modules. Motors, boards, batteries, and the front sensor head stay complete
during explosion.

Start with the completed rover assembly open in Fusion. Run RoverMotion, choose
Full assembly, and press Play. Fusion creates a separate presentation document.


1. INSTALL AND RUN

1) Extract the entire download to a stable folder that you can write to, such as:

   C:\Users\<you>\Documents\Rover\Rover_V3_Motion\

   Keep the extracted files together. Do not run the script from inside the ZIP.

2) In Fusion, open and activate either:

   - The completed native Rover V3 design built by RoverFusion; or
   - The previously delivered cad/complete_assembly.step, opened as a
     complete assembly with its component names intact.

   Use the assembled model. A partially created design left by an earlier failed
   build, an individual part, or the print-plate 3MF will not supply all required
   geometry. The source assembly contains 64 geometry components and 78 solid
   bodies before this companion adds its optional wheel markers.

3) Switch to the Design workspace. Finish or cancel any active modeling command.

4) Open Utilities > Add-Ins > Scripts and Add-Ins.

5) On the Scripts tab, click + to add an existing script. In Fusion's newer
   manager, use the Scripts filter and + > Script or add-in from device. The
   wording varies between Fusion's old and new script-manager layouts.

6) Select the RoverMotion folder that directly contains these files:

   RoverMotion.py
   RoverMotion.manifest
   motion_plan.py
   motion_math.py
   part_catalog.json
   palette.html

   Select that folder, not the ZIP, its outer parent folder, or the Python file
   by itself. Preserve the RoverMotion folder name and the matching main script
   and manifest names.

7) Select RoverMotion in the script list and click Run, or its Run icon.

   The script copies the assembly solids into a new document called
   "Rover V3 - Motion and Assembly Views" when Fusion permits that title. A
   "Rover motion and assembly" panel opens on the right. Wait for the controls
   to become available, then select a view or motion and press Play.

This is a script you run when needed. You do not need to edit its Python or HTML
files to use the controls. Fusion remembers the linked script folder; keep it
in the same location for future runs.


2. WHAT THE PRESENTATION COPY CONTAINS

The source rover remains your engineering model. RoverMotion makes independent
solid copies in a separate direct-design document, with no source joints or
parametric feature history to constrain the presentation movements. It copies
the source body colors where Fusion permits and reports any color-copy issue.

The presentation covers the existing 64 geometry components:

  21 printed components
     Base, upper deck, two battery rails, six support posts, four Pi standoffs,
     three Uno standoffs, and four line-tracker spacers.

  43 hardware reference components grouped into 10 whole purchased units
     These are geometry subdivisions used by the source model. They do not mean
     that you need to dismantle your purchased hardware into 43 pieces.

The 10 purchased units are:

  1. Power bank: complete reference body.
  2. Motor battery: battery body and switch together.
  3. Raspberry Pi: board, ports/connectors, and processor together.
  4. Arduino Uno assembly: Uno board, its connectors, installed motor shield,
     and shield connectors together.
  5. Front-left motor/wheel module.
  6. Front-right motor/wheel module.
  7. Rear-left motor/wheel module.
  8. Rear-right motor/wheel module.
     Each motor/wheel module includes its silver mounting block, gearbox,
     motor can, shaft, wheel hub, and tire.
  9. Front sensor-head module: servo body, horn, sensor carrier, ultrasonic
     board and transducers, camera board, and camera lens together.
 10. Line tracker: board and sensor references together.

Every member of a purchased unit receives the same translation throughout an
exploded view. Motor cases do not split, and board ports or chips do not lift
away from their board. The printed parts remain separately identifiable in the
Fusion browser. Their names begin with PRINTED; hardware names begin with BOUGHT.

The script adds up to four small wheel-marker bodies to make rotation visible
on the simplified, symmetric wheels. They are labeled VISUAL ONLY. When all four
are created, the presentation contains the original 78 solids plus four marker
solids. These markers belong only to the presentation copy.


3. CHOOSE A VIEW OR MOTION

Full assembly
  Lifts the upper deck with its mounted hardware, separates the lower printed
  parts and complete motor/wheel modules, then separates whole electronics,
  the motor battery, and the front head from their printed supports.

Electronics access
  Lifts and spreads the complete Pi and Uno/shield assemblies, with their
  printed standoffs separated for inspection. Other rover parts stay assembled.

Raspberry Pi access
  Moves the complete Pi assembly and its four printed standoffs. All Pi ports
  and the processor stay on the board.

Arduino Uno access
  Moves the complete Uno with its installed shield and three printed standoffs.
  The Uno and shield stay together for this view.

Drive - wheel rotation
  Rotates all four wheels through two revolutions. Each hub, tire, and shaft
  rotates together; the motor cases and rover body remain stationary. This
  demonstrates wheel rotation in place; it does not drive the model across a
  simulated floor.

Turn in place
  Rotates the left and right wheels in opposite directions through two
  revolutions. It demonstrates the wheel pattern for a turn; the rover body
  does not itself yaw or follow a simulated path.

Sensor pan
  Sweeps the mounted sensor head approximately 45 degrees each side of center,
  then returns to center. The servo body stays fixed. This separate motion
  demonstration does not change the whole-head grouping used by exploded views.

The internal mode names, if shown in a report or saved filename, are full,
electronics, pi, uno, drive, turn, and pan.


4. PLAYBACK AND RETURNING TO THE ASSEMBLED ROVER

Play
  Runs forward from the current progress. A complete 0-to-100% pass takes about
  eight seconds; a partial pass takes the corresponding fraction. Playback
  stops at the end. Pressing Play again from 100% starts a new pass.

Pause
  Stops at the current pose so you can inspect it or change the camera.

Reverse
  Runs backward toward 0%. If already at 0%, it starts at 100% and plays back.

Progress slider
  Sets a pose directly and pauses playback. In an exploded view, 0% is assembled
  and 100% is fully separated. Motion demonstrations return to their starting
  orientation at the end of their cycle.

Assembled
  Immediately restores every component to its saved starting placement.

Show wheel rotation markers
  Shows or hides the small visual dots that help you see wheel rotation.
  Changing this setting also pauses playback. Hidden markers still exist as
  bodies in the presentation document and in a saved presentation archive.

Close and restore
  Stops the script, restores the starting placements, and closes the controls.
  It leaves the presentation document open. Keep the presentation tab active
  in Design with no editing command active while using this button. Closing the
  palette with its X also attempts restore. If another tab, workspace, or editing
  command prevents restore, the script shows a warning: finish the command,
  activate this presentation in Design, and run RoverMotion again to restore it.

Changing the selected mode starts that mode at 0%. The source geometry and the
previously supplied full print-project 3MF are not changed by these controls.
The camera fits the selected view when you first play or scrub it; exploded
views are framed for their fully separated extent. Assembled fits the assembled
rover again. After that initial fit, you can orbit, pan, and zoom for inspection.

If you switch to another document or workspace, or start a modeling command,
playback pauses. Reactivate the presentation tab in Design, finish or cancel the
active command, and press Play again. Use the presentation controls for posing;
avoid deleting its parts or changing it to a parametric-history document if you
want to resume it later.


5. SAVE A PICTURE OR AN INSPECTABLE POSE

Save image
  Pauses playback and saves the current Fusion viewport as a 1920 x 1080 PNG.
  First use orbit, zoom, and pan to frame the view you want. For a large exploded
  view, zoom out or use Fit before saving. Marker visibility follows the current
  checkbox. This saves a still picture, not a video or the control panel.

Save pose (.f3d)
  Pauses playback and exports the current presentation document as a Fusion
  archive. It contains the current static pose, the copied geometry, any visual
  marker bodies, and the stored original placements needed to restore it later.
  The saved file is a presentation asset, not a replacement manufacturing or
  print file and not a recorded animation.

Both controls open a Save dialog so you can choose a folder and filename. The
initial location is the current run's output folder. Canceling leaves the
current pose available. A failed optional export is reported in the panel and
report; it does not make playback depend on that export succeeding.

To revisit a saved pose, open its .f3d in Fusion. It initially displays the saved
static arrangement. With that presentation active, run RoverMotion again to
resume the controls. Resuming automatically returns it to the assembled pose
and turns the wheel markers on. Select a mode and use the slider or Play to
create a new pose. A saved presentation that is incomplete, missing components,
or converted to parametric history must be regenerated from the original rover.


6. WHAT HAS BEEN CHECKED, AND THE CURRENT LIMITS

The package passed 26 offline checks: 16 assembly/transform checks and 10 focused
API-double checks. These include the earlier root-component naming failure,
nested geometry copying, unit conversion, and recovery. The pure-Python motion
plan and transform logic have been validated offline.
Checks cover the exact component-ID map, complete purchased-unit grouping,
rotation axes from the source manifest, deterministic placement, and restoration
to the original pose. The control-panel and script files have also been checked
without running the native Fusion application here.

Native execution inside your Fusion installation has NOT been performed here.
Your first run supplies that application-level check. The companion uses
standard Fusion Design API operations for copying solids, placing occurrences,
showing the panel, and requesting optional exports. This is not a guarantee about
every feature or export entitlement in a particular Fusion account or release.

Playback takes place live in the Design workspace. This package does not create
an Animation-workspace storyboard, an animation timeline, or a rendered video.
The presentation copy does not inherit the source design's joints or editable
feature history. It uses its own reversible display movements.

The Pi, Uno, motors, and sensors remain the source project's simplified hardware
references. The package does not add full PCB internals, hidden electronic
components, detailed motor internals, wiring, or a physical assembly procedure.
The wheel and sensor axes are the project's nominal demonstration axes. Motion
does not validate fit, collisions, ground contact, traction, forces, servo travel,
or cable clearance. Continue using the original print files for PLA printing.


7. TROUBLESHOOTING AND THE REPORT TO SEND BACK

"Missing components" or "not the completed Rover V3 assembly"
  Activate the finished native assembly or cad/complete_assembly.step and
  run again. Do not use the partial document left by the earlier failed build,
  the 3MF, a single part, or an assembly whose imported component names were
  flattened or renamed. Keep the missing-ID list if the complete source fails.

RoverMotion does not appear in the Scripts list
  Check that you selected the folder directly containing RoverMotion.py and
  RoverMotion.manifest. Keep both names and the folder name as RoverMotion.
  Clear the manager's filters or choose Scripts, then add the folder again.

The panel is blank or says to open it through Fusion
  Run RoverMotion from Fusion's script manager. Opening palette.html directly in
  a web browser cannot connect to Fusion. If necessary, close the controls and
  run the script again with the presentation or completed source tab active.

The wheel looks stationary
  Enable Show wheel rotation markers and look from a side angle. The reference
  wheel is rotationally symmetric, so its unmarked shape can look unchanged.

"Playback paused" or the buttons cannot move the model
  Activate the presentation document in Design and finish or cancel any modeling
  command. Press Play. If a component was deleted, regenerate from the original
  assembly.

Close could not restore, or the presentation was inactive when closed
  Finish or cancel any active modeling command. Activate that presentation in
  Design and run RoverMotion again. A valid saved or open presentation has
  persistent home placements, so resuming restores assembly. If it is incomplete
  or damaged, regenerate it from the original rover.

Save image or Save pose fails
  Choose a writable local destination and a different filename. If Fusion blocks
  an optional export, keep using the live view and send the exact error/report
  for review. Do not treat an export failure as a successful saved file.

Any native Fusion error
  Keep the complete message and the report path shown by the script. Send the
  JSON report and, if useful, a screenshot of the active model and panel.

Each run normally writes:

  RoverMotion\output\<UTC timestamp>\rover_motion_report.json

If the script folder cannot be written, the output folder falls back to a
RoverMotion_... folder under Windows' temporary directory. Error dialogs show
the actual report path. Reports contain the build stage, copied-body/component
counts, warnings, exceptions when available, and successful export paths. A
failure before the script creates its session may have no report; in that case,
send the complete Fusion error text.


INSTALLATION REFERENCES

Autodesk: Manage scripts and add-ins
https://help.autodesk.com/cloudhelp/ENU/Fusion-Model/files/SLD-MANAGE-SCRIPTS-ADD-INS.htm

Autodesk: Creating a Script or Add-In; linking an existing script in the old
and new Scripts and Add-Ins managers
https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/WritingDebugging_UM.htm

Package behavior described here comes from RoverMotion.py, motion_plan.py,
motion_math.py, and palette.html supplied with this companion.
