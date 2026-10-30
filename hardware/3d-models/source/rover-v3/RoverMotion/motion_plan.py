"""Deterministic presentation motion for the existing Rover V3 assembly.

All vectors are in millimetres in the source assembly's world coordinates.
Explosions separate printed parts from complete purchased units. Connector,
processor, motor-can, and wheel reference components are never disassembled
from their purchased unit during an explosion. Wheel/head rotation is a
separate display action with its own rotation groups.

This is an illustration plan, not a physical removal procedure, wiring model,
collision simulation, or recovered full-detail hardware model.
"""
from __future__ import annotations

from math import isfinite


PLAN_VERSION = "1.0.0"

PRINTED_PART_IDS = (
    "base", "upper_deck", "bank_rail_right", "bank_rail_left",
    *(f"support_post_{i:02d}" for i in range(1, 7)),
    *(f"pi_standoff_{i:02d}" for i in range(1, 5)),
    *(f"uno_standoff_{i:02d}" for i in range(1, 4)),
    *(f"tracker_spacer_{i:02d}" for i in range(1, 5)),
)

# The Uno and plugged-in shield stay together as one installed purchased unit.
# This deliberately avoids desoldering or PCB-package separation imagery.
BOUGHT_UNITS = {
    "power_bank": ("power_bank",),
    "motor_battery": ("motor_battery", "motor_battery_switch"),
    "pi": ("pi_board", "pi_board_connectors", "pi_processor"),
    "uno": ("uno_board", "uno_board_connectors", "motor_shield", "shield_connectors"),
    **{
        "motor_" + corner: tuple(prefix + corner for prefix in (
            "block_", "motor_", "motor_can_", "wheel_hub_", "tire_", "shaft_"))
        for corner in ("front_left", "front_right", "rear_left", "rear_right")
    },
    "front_head": (
        "pan_servo", "servo_horn", "sensor_head", "ultrasonic_board",
        "sonar_transducers", "camera_board", "camera_lens",
    ),
    "line_tracker": ("line_tracker", "tracker_sensors"),
}

BOUGHT_PART_IDS = tuple(pid for members in BOUGHT_UNITS.values() for pid in members)
PART_IDS = PRINTED_PART_IDS + BOUGHT_PART_IDS
PI_STANDOFFS = tuple(f"pi_standoff_{i:02d}" for i in range(1, 5))
UNO_STANDOFFS = tuple(f"uno_standoff_{i:02d}" for i in range(1, 4))

# These origins and axes are the exact nominal axes from assembly_manifest.json.
# Both left and right axes are +X, so a common signed angle gives rolling
# consistency. Positive forward travel is +Y: forward wheel angle is negative.
WHEEL_GROUPS = {
    corner: {
        "ids": tuple(prefix + corner for prefix in ("wheel_hub_", "tire_", "shaft_")),
        "origin_mm": (
            -99.238555 if corner.endswith("left") else 99.238555,
            39.622194751879 if corner.startswith("front") else -43.52580412373729,
            19.5,
        ),
        "axis": (1.0, 0.0, 0.0),
        "forward_angle_sign": -1.0,
        # Positive rotation about rover +Z: left side reverses, right advances.
        "turn_angle_sign": 1.0 if corner.endswith("left") else -1.0,
        "joint_id": "rotate_wheel_hub_" + corner,
        "fidelity": "Nominal reference axis; no rolling-contact or traction simulation",
    }
    for corner in ("front_left", "front_right", "rear_left", "rear_right")
}

PAN_GROUP = {
    "ids": ("servo_horn", "sensor_head", "ultrasonic_board", "sonar_transducers",
            "camera_board", "camera_lens"),
    "origin_mm": (0.916, 86.684, 52.0),
    "axis": (0.0, 0.0, 1.0),
    "limits_deg": (-80.0, 80.0),
    "demo_limits_deg": (-45.0, 45.0),
    "joint_id": "rotate_servo_horn",
    "fidelity": "Nominal display axis and limits; actual servo travel is unmeasured",
}


def _offsets(ids, vector):
    return {pid: tuple(float(value) for value in vector) for pid in ids}


def _phase(name, start, end, offsets):
    return {"name": name, "start": float(start), "end": float(end), "offsets_mm": offsets}


_DECK_MOUNTED = (
    "upper_deck", *PI_STANDOFFS, *UNO_STANDOFFS,
    *BOUGHT_UNITS["pi"], *BOUGHT_UNITS["uno"],
    *BOUGHT_UNITS["motor_battery"], *BOUGHT_UNITS["front_head"],
)

_LOWER = {
    **_offsets(BOUGHT_UNITS["power_bank"], (0, 0, 35)),
    "bank_rail_right": (30.0, 0.0, 0.0),
    "bank_rail_left": (-30.0, 0.0, 0.0),
    **_offsets(tuple(f"support_post_{i:02d}" for i in range(1, 7)), (0, 0, 32)),
    **_offsets(tuple(f"tracker_spacer_{i:02d}" for i in range(1, 5)), (0, 0, -18)),
    **_offsets(BOUGHT_UNITS["line_tracker"], (0, 0, -40)),
}
for _corner in WHEEL_GROUPS:
    _LOWER.update(_offsets(BOUGHT_UNITS["motor_" + _corner], (
        -50 if _corner.endswith("left") else 50,
        20 if _corner.startswith("front") else -20,
        0,
    )))

_UPPER = {
    **_offsets(BOUGHT_UNITS["pi"], (-65, 0, 55)),
    **_offsets(PI_STANDOFFS, (-65, 0, 20)),
    **_offsets(BOUGHT_UNITS["uno"], (65, 0, 55)),
    **_offsets(UNO_STANDOFFS, (65, 0, 20)),
    **_offsets(BOUGHT_UNITS["motor_battery"], (0, -60, 45)),
    **_offsets(BOUGHT_UNITS["front_head"], (0, 55, 45)),
}


def _electronics_phases(units):
    lift, spread, separate = {}, {}, {}
    for unit in units:
        board = BOUGHT_UNITS[unit]
        stands = PI_STANDOFFS if unit == "pi" else UNO_STANDOFFS
        x = -65 if unit == "pi" else 65
        lift.update(_offsets(board, (0, 0, 55)))
        lift.update(_offsets(stands, (0, 0, 15)))
        spread.update(_offsets(board + stands, (x, 0, 0)))
        separate.update(_offsets(board, (0, 0, 30)))
        separate.update(_offsets(stands, (0, 0, 15)))
    return (
        _phase("Lift complete electronics units and their printed standoffs", 0, 0.40, lift),
        _phase("Spread the installed units for inspection", 0.35, 0.80, spread),
        _phase("Separate printed standoffs from complete purchased boards", 0.70, 1, separate),
    )


EXPLODE_PHASES = {
    "full": (
        _phase("Lift service deck with its complete mounted units", 0, 0.35,
               _offsets(_DECK_MOUNTED, (0, 0, 90))),
        _phase("Separate lower printed parts and whole motor/wheel modules", 0.28, 0.70, _LOWER),
        _phase("Separate purchased units from their printed deck and standoffs", 0.62, 1, _UPPER),
    ),
    "electronics": _electronics_phases(("pi", "uno")),
    "pi": _electronics_phases(("pi",)),
    "uno": _electronics_phases(("uno",)),
}

MODE_LABELS = {
    "full": "Full rover — printed parts and complete purchased units",
    "electronics": "Pi and Uno assemblies with printed standoffs",
    "pi": "Complete Pi assembly with printed standoffs",
    "uno": "Complete Uno/shield assembly with printed standoffs",
}


def smoothstep(value):
    """Cubic ease with exact 0 and 1 endpoints."""
    value = min(1.0, max(0.0, float(value)))
    return value * value * (3.0 - 2.0 * value)


def explode_offsets(mode, progress):
    """Return an independent complete part-ID map of world translations in mm.

    ``progress`` is 0..1; values outside that range are clamped. A reverse
    animation feeds the same progress values in descending order, so restore
    does not integrate accumulated transforms and returns exact zero offsets.
    The caller composes these offsets with each saved home transform.
    """
    if mode not in EXPLODE_PHASES:
        raise ValueError(f"Unknown explode mode: {mode}")
    progress = float(progress)
    if not isfinite(progress):
        raise ValueError("Explode progress must be finite")
    progress = min(1.0, max(0.0, progress))
    result = {pid: [0.0, 0.0, 0.0] for pid in PART_IDS}
    for phase in EXPLODE_PHASES[mode]:
        local = (progress - phase["start"]) / (phase["end"] - phase["start"])
        amount = smoothstep(local)
        for pid, vector in phase["offsets_mm"].items():
            for axis in range(3):
                result[pid][axis] += amount * vector[axis]
    return {pid: tuple(vector) for pid, vector in result.items()}


def storyboard_phases(mode, duration_seconds=8.0):
    """Return fresh phase records with timings for a supported timeline caller.

    This supplies timing data only; it does not claim to create a Fusion
    Animation storyboard or require that workspace to be available.
    """
    if mode not in EXPLODE_PHASES:
        raise ValueError(f"Unknown explode mode: {mode}")
    duration = float(duration_seconds)
    if not isfinite(duration) or duration <= 0:
        raise ValueError("Duration must be positive and finite")
    return tuple({
        "name": phase["name"],
        "start_seconds": phase["start"] * duration,
        "end_seconds": phase["end"] * duration,
        "offsets_mm": dict(phase["offsets_mm"]),
        "easing": "smoothstep",
    } for phase in EXPLODE_PHASES[mode])


def validate_plan(expected_part_ids=None):
    """Validate group coverage, invariants, axes, and finite complete poses."""
    expected = set(PART_IDS if expected_part_ids is None else expected_part_ids)
    if len(PART_IDS) != 64 or len(set(PART_IDS)) != 64 or set(PART_IDS) != expected:
        raise ValueError("Motion plan must match all 64 unique Rover V3 component IDs")
    if len(PRINTED_PART_IDS) != 21 or len(BOUGHT_PART_IDS) != 43 or len(BOUGHT_UNITS) != 10:
        raise ValueError("Expected 21 printed components and 43 reference components in 10 complete bought units")
    if len(set(BOUGHT_PART_IDS)) != 43 or set(PRINTED_PART_IDS) & set(BOUGHT_PART_IDS):
        raise ValueError("Printed/bought grouping is not a disjoint partition")
    for mode, phases in EXPLODE_PHASES.items():
        for phase in phases:
            if not (0 <= phase["start"] < phase["end"] <= 1):
                raise ValueError(f"Invalid phase range in {mode}")
            if not set(phase["offsets_mm"]) <= expected:
                raise ValueError(f"Unknown component in {mode}")
            for vector in phase["offsets_mm"].values():
                if len(vector) != 3 or not all(isfinite(value) for value in vector):
                    raise ValueError(f"Invalid translation vector in {mode}")
            # This structural check proves identical group offsets for every
            # progress value, beyond the representative samples below.
            for members in BOUGHT_UNITS.values():
                vectors = {phase["offsets_mm"].get(pid, (0.0, 0.0, 0.0)) for pid in members}
                if len(vectors) != 1:
                    raise ValueError(f"Purchased unit split during {mode}: {members}")
        for progress in (0, .1, .28, .35, .5, .62, .7, .8, 1):
            pose = explode_offsets(mode, progress)
            if set(pose) != expected or pose["base"] != (0.0, 0.0, 0.0):
                raise ValueError("A complete pose must preserve the base at its home position")
            for members in BOUGHT_UNITS.values():
                if len({pose[pid] for pid in members}) != 1:
                    raise ValueError("A purchased unit was split")
        if any(vector != (0.0, 0.0, 0.0) for vector in explode_offsets(mode, 0).values()):
            raise ValueError("Assembled endpoint must be exactly zero")
    moving = set()
    for corner, group in WHEEL_GROUPS.items():
        ids = set(group["ids"])
        if len(ids) != 3 or not ids <= set(BOUGHT_UNITS["motor_" + corner]) or moving & ids:
            raise ValueError("Wheel rotation groups must be independent hub/tire/shaft subsets")
        if group["axis"] != (1.0, 0.0, 0.0):
            raise ValueError("Wheel axes must match source +X references")
        moving.update(ids)
    if not set(PAN_GROUP["ids"]) < set(BOUGHT_UNITS["front_head"]) or "pan_servo" in PAN_GROUP["ids"]:
        raise ValueError("Head pan must preserve its fixed servo body")
    return {"status": "passed", "part_count": 64, "printed_part_count": 21,
            "bought_reference_component_count": 43, "complete_bought_unit_count": 10,
            "explode_modes": tuple(EXPLODE_PHASES), "wheel_rotation_groups": 4,
            "purchased_units_remain_whole_at_all_progress_values": True,
            "fusion_runtime_executed": False}


validate_plan()
