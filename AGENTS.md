# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## What this is

Arduino Uno firmware (v2.1.2) for the ELEGOO Smart Robot Car Kit V4.0. A single flat sketch directory: one `.ino` plus paired `.h/.cpp` files. No tests, no linter, no package manager. All source comments are bilingual English / Chinese (`English / 中文`); keep that convention when adding comments.

## Build and flash

Board FQBN is `arduino:avr:uno`. Serial baud is 9600.

```bash
arduino-cli compile --fqbn arduino:avr:uno .
arduino-cli upload -p COM3 --fqbn arduino:avr:uno .    # replace COM3
arduino-cli monitor -p COM3 -c baudrate=9600
```

Required libraries, with the versions CI pins and the firmware is verified against:

```bash
arduino-cli lib install FastLED@3.9.20 IRremote@4.7.1 Servo@1.3.0 MPU6050@1.4.5
```

`MPU6050` is the Electronic Cats package of the jrowberg i2cdevlib driver and bundles `I2Cdev`. `Wire` ships with the core. ArduinoJson is vendored as `ArduinoJson-v6.11.1.h` and must not be installed separately or you get duplicate-symbol errors.

**FastLED must stay on 3.9.x.** FastLED 3.10.0 and later define `ISR(TIMER1_COMPA_vect)` unconditionally for ATmega inside the library's own sources, which collides with `Servo` at link time (`multiple definition of __vector_11`). A sketch-level define cannot disable it. Last verified build: 29658 B flash (91%), 1334 B RAM (65%).

The `.ino` must keep the same name as the repo folder (`ELEGOO-Smart-Robot-Car-Kit-V4.0-New.ino`) or the Arduino toolchain refuses to build. The README refers to it as `SmartRobotCarV4.0.ino` and lists an `addLibrary/` folder and `README.txt` that do not exist in this repo; the README is stale on those points.

Resource budget: Uno has 2 KB RAM and 32 KB flash. `DECODE_NEC` is defined before including IRremote specifically to shrink the binary; the JSON document is `StaticJsonDocument<100>` and the serial message cap is 128 bytes. Check `arduino-cli compile` output for RAM/flash usage after any change that adds globals or strings; use `F()` for literal strings.

## CI

`.github/workflows/firmware-ci.yml` compiles the sketch with arduino-cli on every push and pull request. Because the sketch folder must be named `ELEGOO-Smart-Robot-Car-Kit-V4.0-New` but the GitHub repo is `elegoo-smart-car-v4`, the workflow checks out into an explicitly named path and builds the base commit from a `git worktree` created under the same folder name. Keep both if you edit the checkout or delta steps.

Two matrix legs:
- **pinned** (required): `arduino:avr@1.8.8` and the library versions listed above. Fails on compile error or when flash exceeds 95% or global RAM exceeds 80% of the Uno's limits. Uploads the `.hex` as an artifact.
- **latest** (informational, `continue-on-error`): newest core and libraries, to warn early that an upstream update will break the build. Expected to fail while FastLED 3.10+ is current.

`.github/scripts/firmware_report.py` turns `arduino-cli compile --format json` output into the step summary: flash/RAM table, deltas against the base commit, and warnings that originate in sketch files. It can be run locally against a saved JSON file. To bump a library, change `LIBS_PINNED` in the workflow and the install command above, then confirm the pinned leg still passes.

## Architecture

Strict top-down layering. Each layer only talks to the one below it:

1. **`ELEGOO-Smart-Robot-Car-Kit-V4.0-New.ino`** – `setup()` inits the app and enables a 4 s watchdog. `loop()` is a cooperative scheduler: `wdt_reset()` then `updateSensorData` → `processKeyCommand` → `processIRCommand` → `updateTimer` → `checkState`. `serialEvent()` (called by the AVR core after each `loop()` when bytes are pending) frames a `{...}` message, parses JSON, and calls `analyzeSerialData`.
2. **`ApplicationFunctionSet`** – the state machine and command dispatcher. Owns the `State` enum (`Standby, TraceBased, Follow, ObstacleAvoidance, Rocker, DoNothing`) and the one-shot software timer used by timed serial commands. All nine `DeviceDriverSet_*` hardware objects are file-scope globals in `ApplicationFunctionSet.cpp` and are injected by reference into `MotionControl` and `RgbControl`.
3. **`MotionControl`** / **`RgbControl`** – behaviour. `MotionControl` holds every autonomous algorithm (yaw-PID straight driving, line tracking PD, obstacle-avoidance state machine, follow mode) and all tuning constants. `RgbControl` maps state + low-battery flag to LED colour/effect.
4. **`DeviceDriverSet`** – one thin class per peripheral with pin constants as `static constexpr` members. Pin map lives here, not in a config header.
5. **`Utils`** – `NonBlockingTimer` and `Utils::delayWithWatchdog`.

There is a deliberate header cycle: `RgbControl.h` includes `ApplicationFunctionSet.h` only to see the `State` enum.

### Non-blocking discipline

The watchdog resets the board if `loop()` stalls for 4 s. Every subsystem self-throttles with `millis()` (sensors 10 ms, motion PID 10 ms, RGB 100 ms, obstacle distance checks 50 ms). Any blocking wait longer than a few ms must go through `Utils::delayWithWatchdog`. The servo has two APIs: `control()` blocks (used at init and when entering Standby), while `controlMultiple()` + `update()` is a non-blocking state machine driven from `checkState()` (used by serial command N=106). `HandleFollowMode` still contains two raw `delay(100)` calls; treat them as known debt, not a pattern to copy.

### State transitions and input sources

Three inputs can change `currentState`:
- **Button** (D2, external interrupt 0, 500 ms debounce in ISR) cycles 0→1→2→3 = Standby, TraceBased, ObstacleAvoidance, Follow.
- **IR remote** (NEC only). Arrow keys enter `Rocker` and set `carDirection`; held keys arrive as repeat codes. If no IR frame arrives for 150 ms while in IR-driven Rocker mode, the car drops back to `Standby` (this is the stop-on-release behaviour). Keys 4/5/6 adjust `motionControl.TrackingDetection_THRESHOLD`, 7/8/9 adjust `rockerCarSpeed`.
- **Serial JSON**. Any direct-control command (N=1,2,3,4,5,7,8,21,22,23,110) sets `State::DoNothing` so `checkState()` stops driving the motors and the raw command sticks.

Autonomous modes (`TraceBased`, `ObstacleAvoidance`, `Follow`) are gated on `isOnGround`, which is false when all three line sensors read above `ApplicationFunctionSet::TRACKING_DETECTION_THRESHOLD` (950). Lifting the car silently freezes those modes.

### Two different "tracking thresholds"

`ApplicationFunctionSet::TRACKING_DETECTION_THRESHOLD` (950) is the lifted-off-ground detector. `MotionControl::TrackingDetection_THRESHOLD` (400, IR-adjustable) is the black/white line decision used by `calculateErrorByTable`. Do not conflate them.

### Serial protocol details that differ from the README

Fields: `N` command, `H` reply tag, `D1..D4` params, `T` duration ms. Replies are `{<H>_ok}` or `{<H>_<data>}`, written with raw `Serial.write`.

- **N=2** is the *timed* car move (uses `T`, replies `_ok` when the timer fires and stops the car). **N=3** is untimed and replies immediately. The README example attaches `T` to N=3, where it is ignored.
- **N=7** is the *timed* lighting command; **N=8** is untimed. Again the README example has these inverted.
- N=4 (independent L/R speed) always forces both directions to forward unless both speeds are 0.
- N=5 divides `D2` by 10 before writing the Z servo, so callers send degrees×10.
- N=106 servo nudges move in units of 10° with Y clamped to 30–110° and Z to 10–170°.

### Sensor conventions

- Ultrasonic `getDistance` returns cm; `0` means under 2 cm, `150` means timeout or beyond range. Obstacle avoidance treats `0` as "far" (200) before comparing, so a reading of 0 never triggers a stop.
- Line sensors are raw `analogRead` 0–1023; higher = lighter surface.
- `DeviceDriverSet_Voltage::getVoltage()` applies a fixed 0.0375 V/count scale plus 8 % compensation. Low-battery flag needs 50 consecutive sub-7.00 V samples (0.5 s) before `RgbControl` starts the red blink.
- MPU6050 yaw is pure gyro-Z integration with a 100-sample startup offset; it drifts and is only used relative to a `TargetYaw` captured when direction changes or the car is set back on the ground.

### Motor direction mapping

`DeviceDriverSet_Motor::control(dirRight, speedRight, dirLeft, speedLeft)`, `true` = forward. `Left` turn is left-forward/right-backward (in-place pivot). Diagonal directions subtract 60 from the inner wheel and are not clamped, so speeds under 60 underflow the `uint8_t`. STBY is driven LOW automatically when both speeds are 0.
