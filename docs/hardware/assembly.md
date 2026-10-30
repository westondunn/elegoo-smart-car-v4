# Assembly (Rover V3)

Source: [`rover-v3/docs/start_here.txt`](../../hardware/3d-models/rover-v3/docs/start_here.txt)
and [`rover-v3/docs/hardware_and_assembly.json`](../../hardware/3d-models/rover-v3/docs/hardware_and_assembly.json).
The full V3 chassis has not been assembled physically; this order is the
project's documented plan. Keep the existing wiring, power separation,
firmware and Pi-to-UNO serial link exactly as they are.

## Parts

Printed (21 pieces): 1 lower chassis, 1 upper deck, 2 power-bank rails,
6 deck posts (Ø12 × 40.5), 4 Pi standoffs (Ø8 × 6, bore 2.8), 3 UNO standoffs
(Ø8 × 6, bore 3.4), 4 line-tracker spacers (Ø7 × 3, bore 3.2).

Reused kit hardware: four motor/block/wheel groups with their tested screws
and 6 mm washers, battery pack and its fasteners, complete servo/camera/sonar
head and bracket, UNO + shield, line-tracker board and hardware.

Non-kit items the printed parts are designed around: Raspberry Pi (58 × 49 mm
pattern) and a flat power bank (69.85 × 146.05 × 12.7 mm per the project
record). Their reference models are not in this repository.

## Fasteners (from the project record, nominal stacks assumed)

| Use | Qty | Fastener | Nuts / washers |
| --- | --- | --- | --- |
| Deck posts | 6 | M3 × 50 low/button-head hex (head ≤ 2 mm) | 6 M3 nuts, 12 washers Ø6 × 0.5 |
| Power-bank rails | 6 | M3 × 8 low/button-head hex | 6 M3 nuts in the underside hex pockets, 6 washers Ø6 |
| Pi board | 4 | M2.5 × 16 | 4 M2.5 nuts, 8 thin washers |
| UNO board | 3 | M3 × 16 | 3 M3 nuts, 6 thin washers |
| Power bank retention | 2 | hook-and-loop strap, 12 mm wide, 220–250 mm | — |
| Motors | reuse | original motor-block screws (4 mm head, 2 mm high) + Ø6 washers | pocket 7.4 wide × 3.3 deep, 1.8 mm floor |
| Motor battery | reuse | original lugs/screws; required length = lug thickness + about 5.8 mm | 2.4 mm deck floor |

Use 50 mm post screws, not 55 mm: with the stated washer/nut stack the tips
finish 2.4 mm below the nominal board underside.

## Order

1. Identify FRONT on the lower chassis. The broad flat motor-contact face is
   up when installed; the head/washer recesses face down (the print
   orientation is the reverse).
2. Drop the six rail nuts into the underside hex pockets. Fit both rails,
   rotating one 180° so the end stops face inward.
3. Thread the two straps through the four base slots, fit the centred power
   bank, check connector access, close the straps without squeezing it.
4. Install the four motor/block/wheel groups in their matching front and rear
   hole pairs. Keep the stock group intact.
5. Fit the line tracker underneath with the 3 mm spacers (or the stock
   spacers if they give the right sensor-to-floor distance).
6. Install the six 40.5 mm posts. Prepare the deck (motor battery, standoffs,
   front head) while both sides are reachable.
7. Set the motor-battery slot to the real mounting pitch (65–90 mm slot;
   76 mm is the OEM nominal, not a measurement of your pack). Route the
   existing wiring through the service windows, fasten the deck with the
   50 mm screws. Keep cables clear of shafts and wheels.
8. Tighten all six post nuts **before** fitting the Pi and UNO. The post at
   X48, Y0 sits under the UNO envelope.
9. Power off, lift the rover, turn each wheel a full turn. Check screw tips
   and plug seating before first power-up.

## Older revisions

* Explorer deck and v0.2 / v0.3 body: order and fasteners in
  `explorer-v0.1/docs/start_here.txt` (follow-up PR),
  `body-v0.2-full/docs/start_here.txt` (follow-up PR),
  `body-v0.3-wheelbase76/docs/start_here.md` (follow-up PR).
* V2 P1B motor retrofit: `motor-retrofit-r1/docs/motor_adapters_r1_guide.md` (follow-up PR)
  (needs 8 × M3 × 8 countersunk screws with heads ≤ 6.2 mm, 4 × M3 × 10, 4 M3 nuts).
* V2 P1 chassis and the roof-battery/service-hatch parts have no assembly
  documentation on record.
