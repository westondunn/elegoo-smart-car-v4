# Rover motor retrofit R1 — assembly and fit guide

**For the already printed Rover V2 P1B chassis.** Reuses the ELEGOO motors, silver mounting blocks and wheels. Print material: PLA. Revision date: October 20, 2026.

The project contains **one plate with eight parts: two Adapter A, two Adapter B, and four 1.6 mm floor-screw spacers**. Native Bambu Studio estimate: **45 minutes 47 seconds and 12.67 g PLA**. These are slicer estimates, not measured print results.

**Status: digitally checked fit prototype; physical fit pending.** The adapter geometry clears the existing chassis and carriers in CAD. The real motors, shafts, screw dimensions and final wheel position must be checked during assembly.

## 1. What the adapters change

| Feature | R1 design |
| --- | --- |
| Mounting correction | Moves the silver block's bottom mounting pair 11 mm toward its chassis end: forward at the front, rearward at the rear. |
| Sideways adjustment | Two parallel slots provide 0–18 mm of screw-center adjustment outward from the original floor-hole line. Set this from the actual motor position. The slot range does not establish how far the real motor can move. |
| Motor seat | Adds 4 mm above the existing inside floor. |
| Ground clearance | Your current approximately 24 mm body clearance becomes approximately 20 mm if the motors start seated directly on the original floor and the wheel geometry is unchanged. Check the assembled rover. |
| Existing chassis attachment | One M3 floor screw clamps each adapter; a printed locating key engages the other existing floor slot to resist rotation. |
| Wheel position | Start from the fully seated wheel position you measured, with 14 mm horizontal wheel/body clearance. Check that clearance again after setting the adapter. |
| Inner shaft | Your measured 3 mm inner shaft/board-post gap is a starting reference. Recheck it after the fore/aft and height changes. |

The axle does not need to sit at the center of the wall opening. It needs to rotate freely throughout its full sweep, with the motor firmly secured.

## 2. Print project

Open **Rover_Motor_Retrofit_R1_X1C_PLA.3mf** as a project in Bambu Studio, preserving its settings and eight arranged objects. Use the project with an X1 Carbon, standard 0.4 mm nozzle and Textured PEI plate. Select the loaded PLA spool before sending the print. The file includes native sliced G-code; inspect the plate preview before printing and re-slice if you change the printer, nozzle, material or process settings.

Send this local project to the printer through Bambu Studio. Once printing, Bambu Handy can monitor the printer and show its live camera. Operation in a live Studio/Handy account and direct local-file import into Handy have not been tested for this project.

| Setting | Included value |
| --- | --- |
| Printer / nozzle | Bambu Lab X1 Carbon / standard 0.4 mm |
| Material / plate | Generic PLA / Textured PEI |
| Layer height | 0.20 mm |
| Walls | 5 |
| Top / bottom layers | 5 / 5 |
| Infill | 100% Rectilinear |
| Supports | Off |
| Brim | 2 mm outer brim |
| Print sequence | By layer |

The adapters are already oriented with the **motor-contact face on the bed and the locating key pointing up**. The A/B marks and arrows are visible from above in the print arrangement. In the rover, that marked face points down toward the chassis floor, and the key enters the floor slot.

Each adapter occupies approximately 28.4 × 28.2 × 7.8 mm in its print orientation. The 7.8 mm height includes the locating key; the flat adapter body is 4 mm thick. Each spacer is 8 mm outside diameter, 3.4 mm inside diameter and 1.6 mm thick. Remove the brims and any first-layer lip that prevents the key or nut from seating. Keep the flat seating faces flat.

## 3. Hardware for all four motors

| Quantity | Hardware | Purpose |
| --- | --- | --- |
| 8 | **M3 × 8 mm, 90° flat-head/countersunk screws, head diameter no more than 6.2 mm** | Two screws from beneath each adapter into the bottom of its silver block. The countersunk screw's 8 mm length includes its head. |
| 4 | M3 × 10 mm floor screws, measured beneath a socket, button or pan head | Reuse the original floor screws if their measured dimensions match. One per adapter. |
| 4 | Standard M3 hex nuts, nominal 5.5 mm across flats and approximately 2.4 mm thick | Captive nuts in the adapter pockets. The printed pocket is 5.8 mm across flats. |
| 4 | Printed 1.6 mm spacers, included on the plate | Between each floor screw head and the underside of the chassis. |
| Existing set | Original long motor-to-block bolts | Retain the original motor/block attachment. |

**Check the flat-head screws by dimension.** The adapter countersink opening is 6.4 mm wide. A 6.0 mm head gives useful clearance. Accu's DIN 7991 M3 × 8 example specifies a 6.0 mm head and a 90° countersink; its ISO 10642 M3 × 8 example permits a 6.72 mm head, which is too large for this opening. Do not choose a screw solely because its label says “M3 flat-head.” See the dimension references below.

The floor screw and printed spacer are a matched stack. With a 10 mm screw, 4.5 mm chassis floor and 1.6 mm spacer, the nominal screw tip is only **0.1 mm below the adapter's motor-contact face**. Actual screw length and printed thickness matter. Confirm that the screw passes fully through the nut while its tip remains flush with or below that face. If the tip protrudes, correct the fastener/spacer stack and repeat the check; keep full nut engagement. Do not leave the spacer out.

## 4. Which adapter goes where

Left and right mean the rover's own left and right when facing its front.

| Chassis corner | Adapter | Arrow direction when installed |
| --- | --- | --- |
| Front right | A | Toward the front |
| Front left | B | Toward the front |
| Rear left | A | Toward the rear |
| Rear right | B | Toward the rear |

The rear adapters are the corresponding handed parts rotated 180° in the horizontal plane. At every corner, the **locating key enters the existing floor slot nearest that chassis end**, and the **captive nut sits above the existing floor slot nearer the middle of the rover**. The two long adjustment slots extend sideways toward the wheel.

## 5. Assemble one front corner and one rear corner first

1. **Disconnect the battery and prepare the hardware.** Keep the original motor attached to its silver block. Leave its wheel fully seated in the position used for the 14 mm measurement. Select the correct A/B adapter.

2. **Check the floor fastening stack before the motor covers it.** Seat one M3 nut fully in the hex pocket on the motor-contact face. Place the key into its chassis slot. From beneath the chassis, install one M3 × 10 floor screw through a printed 1.6 mm spacer, through the floor, and into that nut. Snug it by hand. Confirm the adapter sits flat, the nut is fully engaged and the screw tip does not project above the motor-contact face. Remove this floor screw and lift out the adapter for the next step.

3. **Attach the silver block loosely to the adapter.** Place the block on the flat motor-contact face. Insert two specified M3 × 8 flat-head screws from the marked/key side through the two adjustment slots into the block's bottom threads. Both screws should start easily by hand. The design uses the existing CAD's 7.8 mm hole pitch; if the actual block differs, stop this fit attempt rather than forcing the threads. Leave enough freedom to slide the block sideways.

4. **Dry-fit the complete module in the chassis.** Put the key back in its endward floor slot and hold the adapter flat on the floor. Slide the motor/block sideways to reproduce the current freely rotating wheel position. Check the wheel/body gap, inner white shaft/board-post gap, shaft opening, motor body and upper carrier clearance. Mark the selected block position on the adapter.

5. **Lift the module out and tighten the two block screws.** The adjustment screw heads are underneath the adapter, so adjust and tighten them with the module removed. Preserve the marked position. The floor-nut pocket prevents the nut from turning but is open at the top: keep that nut seated while handling the module, and check its seating before installing the floor screw. Check with a straightedge that both block-screw heads are flush with or recessed into the adapter's underside. The adapter must lie flat on the chassis. Check that the block is clamped rather than a screw bottoming out in its threaded hole.

6. **Install the assembled module.** Seat the key and fit the floor screw from below with its printed spacer. Tighten by hand until the adapter is seated and cannot rock. Stop before deforming the PLA. Recheck the gaps after tightening.

7. **Repeat at one rear corner.** The rear board mounting post is the tighter CAD location. Once both a front and rear module fit, install the remaining two using the same procedure.

For later sideways adjustments, remove the floor screw and lift the module out to reach the two block screws. Keep the floor spacer with its screw.

## 6. Physical fit checks before driving

With the battery still disconnected, turn each wheel through a full revolution and move it gently through its normal play. It must clear the sidewall at every position. Watch the unused inner shaft as it rotates; check its clearance to the nearby **board mounting post** and wiring. Check the shaft at the wall opening, motor end/can at the chassis, and silver block beneath the carrier.

The nominal block-to-carrier gap is **1.5 mm**: 27.5 mm carrier underside height above the original floor, minus a 22 mm high block, minus the 4 mm adapter. The block's height axis was inferred from the supplied photos and dimensions. Actual block, motor, bolt and carrier clearances take priority.

Place the rover on a flat surface and check body clearance, underside screw heads, spacers and line sensors. Approximately 20 mm is a body-clearance calculation, not the clearance of every underside component. Confirm all four wheels contact the surface normally. Then make a short low-speed run and check for rubbing, adapter movement and loose fasteners. No physical print, drive test or load rating has been completed for R1.

## 7. Evidence and editable files

The CAD review used the existing P1B chassis and board/servo carriers. All four placed adapters had zero positive-volume interference with those solids. The minimum modeled adapter-to-sidewall gap is 1.1 mm; the rear adapter-to-board-post gap is 1.0 mm. The keys have a minimum modeled 0.2 mm gap within the floor slots and end 0.7 mm above the chassis underside. The corrected full-length floor-screw check also passed at all four locations.

Both adapter variants and the spacer are valid single solids. Their STLs are closed manifold meshes. The final one-plate project preserves the source geometry and native settings/G-code, and the model/brim toolpaths clear the bed limits and startup calibration strokes. These checks do not include a certified physical motor or shaft envelope; the reference hardware model was not accurate enough for that purpose.

**Rover_Motor_Retrofit_R1_Design_Files.zip** contains the three individual STL parts, STEP solids, the CadQuery source, this guide, the actual-mesh preview, dimensional manifest and digital review reports. The Python source requires CadQuery 2.7 and regenerates geometry; it does not re-slice the Bambu project. Any geometry edit requires preparing and slicing a new project.

### Dimension provenance and references

- User measurements: A = 11 mm mounting offset front and rear; B approximately 24 mm vertical ground clearance; C = 14 mm current horizontal wheel/body gap with the wheel fully seated; D = 3 mm inner shaft/post gap; silver block 22 × 12 × 4 mm. The additional 52 mm and 40 mm measurements were retained as context and were not used as fixed hole coordinates because their endpoints were not fully defined.
- Existing Rover V2 P1B CAD: chassis floor thickness, floor-hole locations/pitch, sidewalls, board posts and carrier elevations. Exact measured hardware dimensions take priority over these nominal model dimensions.
- [Accu DIN 7991 M3 × 8 dimensional example: 6.0 mm head and 90° countersink](https://www.accu.co.uk/countersunk-socket-head-screws/495094-SSK-M3-8-10-9-Z).
- [Accu ISO 10642 M3 × 8 dimensional comparison: 6.72 mm maximum head](https://www.accu.co.uk/countersunk-socket-head-screws/5423-SSK-M3-8-A2).
- [Bambu Studio Quick Start Guide](https://wiki.bambulab.com/en/software/bambu-studio/studio-quick-start).
- [Bambu Handy: official remote-control and live-view features](https://bambulab.com/en/download/app).

The fastener links are dimensional references, not a claim of current stock or a requirement to buy from that vendor.
