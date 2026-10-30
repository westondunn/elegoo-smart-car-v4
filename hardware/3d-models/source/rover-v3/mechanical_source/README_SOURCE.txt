Mechanical master source supplied with the Fusion project.

Requires Python with CadQuery 2.7 and NumPy. Run from this extracted source tree:
  python cad/source/build_printed_rover.py
  python hardware/build_hardware.py

The printed generator recreates print parts and assembly-coordinate STEP instances
from the retained C3 local interface and OEM outline/reference data. The hardware
generator creates explicitly approximate packaging models. The generated STEP files
do not update an already edited Fusion document automatically. Preserve manual
Fusion edits before regenerating the project. These source scripts are separate
from the dependency-free RoverFusion.py script that runs inside Fusion.

The original user-supplied C1 motor STEP and C1 print 3MF are preserved in
baseline for fit provenance. The C1 3MF is an earlier fit test, not the
current full two-plate rover print project. The generator consumes C3.
