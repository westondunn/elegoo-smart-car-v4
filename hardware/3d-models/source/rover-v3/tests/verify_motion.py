"""Offline contract checks for RoverMotion; this is not a Fusion runtime test.

Run from any directory:
    python tests/verify_motion.py --manifest /path/to/assembly_manifest.json

The manifest comes from the original Rover V3 Fusion builder. Comparing with
that independent assembly description catches wrong IDs, axes, or hardware
membership without importing Autodesk's runtime.
"""
from __future__ import annotations

import argparse
import importlib
import json
import math
from pathlib import Path
import random
import sys
import unittest


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "RoverMotion"))
import motion_plan as plan
import motion_math as mm

MANIFEST = None


class PlanContractTests(unittest.TestCase):
    def test_complete_assembly_partition_matches_independent_manifest(self):
        ids = [part["id"] for part in MANIFEST["parts"]]
        printed = {part["id"] for part in MANIFEST["parts"]
                   if part["category"] == "printed_part"}
        self.assertEqual(len(ids), 64)
        self.assertCountEqual(plan.PART_IDS, ids)
        self.assertEqual(set(plan.PRINTED_PART_IDS), printed)
        bought = [pid for members in plan.BOUGHT_UNITS.values() for pid in members]
        self.assertEqual(len(bought), len(set(bought)))
        self.assertEqual(set(bought), set(ids) - printed)

    def test_user_requested_bought_units_remain_whole_at_every_phase(self):
        # Phase structure proves the invariant throughout each smooth interval;
        # randomized evaluation also detects accidental accumulation bugs.
        required = {
            "pi": {"pi_board", "pi_board_connectors", "pi_processor"},
            "uno": {"uno_board", "uno_board_connectors", "motor_shield", "shield_connectors"},
            "motor_battery": {"motor_battery", "motor_battery_switch"},
            "front_head": {"pan_servo", "servo_horn", "sensor_head", "ultrasonic_board",
                           "sonar_transducers", "camera_board", "camera_lens"},
            "line_tracker": {"line_tracker", "tracker_sensors"},
        }
        for corner in ("front_left", "front_right", "rear_left", "rear_right"):
            required["motor_" + corner] = {
                prefix + corner for prefix in
                ("block_", "motor_", "motor_can_", "wheel_hub_", "tire_", "shaft_")
            }
        for unit, members in required.items():
            self.assertEqual(set(plan.BOUGHT_UNITS[unit]), members)
        rng = random.Random(4907)
        for mode, phases in plan.EXPLODE_PHASES.items():
            for phase in phases:
                for unit, members in required.items():
                    with self.subTest(mode=mode, phase=phase["name"], unit=unit):
                        values = {phase["offsets_mm"].get(pid, (0., 0., 0.)) for pid in members}
                        self.assertEqual(len(values), 1)
            for progress in [0., 1.] + [rng.random() for _ in range(67)]:
                pose = plan.explode_offsets(mode, progress)
                for unit, members in required.items():
                    with self.subTest(mode=mode, progress=progress, unit=unit):
                        self.assertEqual(len({pose[pid] for pid in members}), 1)

    def test_home_is_exact_and_unaffected_by_prior_poses(self):
        for mode in plan.EXPLODE_PHASES:
            initial = plan.explode_offsets(mode, 0.)
            # Deliberately mutate a returned mapping; future poses must own data.
            changed = plan.explode_offsets(mode, .73)
            changed["pi_board"] = (999999., 999999., 999999.)
            for progress in (.93, .18, 1., .52, 0.):
                plan.explode_offsets(mode, progress)
            restored = plan.explode_offsets(mode, 0.)
            self.assertEqual(restored, initial)
            self.assertTrue(all(v == (0., 0., 0.) for v in restored.values()))

    def test_focus_modes_only_remove_the_selected_units_and_printed_supports(self):
        for mode, units, supports in (
            ("pi", ("pi",), plan.PI_STANDOFFS),
            ("uno", ("uno",), plan.UNO_STANDOFFS),
            ("electronics", ("pi", "uno"), plan.PI_STANDOFFS + plan.UNO_STANDOFFS),
        ):
            expected = set(supports)
            for unit in units:
                expected.update(plan.BOUGHT_UNITS[unit])
            moved = {pid for pid, offset in plan.explode_offsets(mode, 1.).items()
                     if offset != (0., 0., 0.)}
            self.assertEqual(moved, expected)

    def test_motion_axes_match_existing_assembly_joints(self):
        joints = {joint["id"]: joint for joint in MANIFEST["joints"]}
        for group in list(plan.WHEEL_GROUPS.values()) + [plan.PAN_GROUP]:
            joint = joints[group["joint_id"]]
            self.assertEqual(joint["type"], "revolute")
            self.assertEqual(tuple(joint["origin_mm"]), group["origin_mm"])
            self.assertEqual(tuple(joint["axis"]), group["axis"])
        self.assertEqual(tuple(joints[plan.PAN_GROUP["joint_id"]]["limits_deg"]),
                         plan.PAN_GROUP["limits_deg"])

    def test_spin_groups_exclude_motor_cases_and_pan_excludes_fixed_servo(self):
        seen = set()
        for corner, group in plan.WHEEL_GROUPS.items():
            self.assertEqual(set(group["ids"]),
                             {prefix + corner for prefix in ("wheel_hub_", "tire_", "shaft_")})
            self.assertFalse(seen & set(group["ids"]))
            seen.update(group["ids"])
        self.assertNotIn("pan_servo", plan.PAN_GROUP["ids"])
        self.assertEqual(set(plan.PAN_GROUP["ids"]) | {"pan_servo"},
                         set(plan.BOUGHT_UNITS["front_head"]))

    def test_forward_spin_has_consistent_ground_contact_velocity(self):
        # At a wheel's lower contact point r=(0,0,-R), omega x r has
        # v_y=omega_x*R. Forward rover travel is +Y, so rotation is -Y there.
        for group in plan.WHEEL_GROUPS.values():
            omega_x = group["axis"][0] * group["forward_angle_sign"]
            self.assertLess(omega_x * 32.5, 0.)
        for axle in ("front", "rear"):
            left = plan.WHEEL_GROUPS[axle + "_left"]
            right = plan.WHEEL_GROUPS[axle + "_right"]
            self.assertEqual(left["forward_angle_sign"], right["forward_angle_sign"])
            self.assertEqual(left["turn_angle_sign"], -right["turn_angle_sign"])

    def test_invalid_inputs_and_clamped_endpoints(self):
        for mode in plan.EXPLODE_PHASES:
            self.assertEqual(plan.explode_offsets(mode, -10.), plan.explode_offsets(mode, 0.))
            self.assertEqual(plan.explode_offsets(mode, 10.), plan.explode_offsets(mode, 1.))
            for progress in (math.nan, math.inf, -math.inf):
                with self.assertRaises(ValueError):
                    plan.explode_offsets(mode, progress)
        with self.assertRaises(ValueError):
            plan.explode_offsets("disassemble_motor_internals", .5)


class TransformContractTests(unittest.TestCase):
    def assertVectorAlmostEqual(self, actual, expected, places=10):
        self.assertEqual(len(actual), len(expected))
        for a, e in zip(actual, expected):
            self.assertAlmostEqual(a, e, places=places)

    def test_known_right_hand_rotation_about_offset_pivot(self):
        pivot = (14., -27., 8.)
        matrix = mm.rotation_mm(pivot, (1., 0., 0.), 90.)
        self.assertVectorAlmostEqual(mm.transform_point(matrix, pivot), pivot)
        self.assertVectorAlmostEqual(mm.transform_point(matrix, (14., -26., 8.)),
                                     (14., -27., 9.))
        self.assertVectorAlmostEqual(mm.transform_point(matrix, (14., -27., 9.)),
                                     (14., -28., 8.))
        mm.validate_rigid(matrix)

    def test_composition_order_and_mm_length_contract(self):
        translation = mm.translation_mm((10., 20., 30.))
        rotation = mm.rotation_mm((0., 0., 0.), (0., 0., 1.), 90.)
        matrix = mm.multiply(translation, rotation)
        self.assertVectorAlmostEqual(mm.transform_point(matrix, (1., 0., 0.)),
                                     (10., 21., 30.))
        self.assertVectorAlmostEqual(mm.transform_vector(matrix, (1., 0., 0.)),
                                     (0., 1., 0.))
        self.assertEqual(translation[3], 10.)
        self.assertEqual(translation[7], 20.)
        self.assertEqual(translation[11], 30.)

    def test_home_returns_exact_saved_matrices_after_arbitrary_pose_sequence(self):
        home = {
            pid: mm.multiply(mm.translation_mm((index * 1.3, -index * .4, index * .17)),
                             mm.rotation_mm((0., 0., 0.), (0., 0., 1.), index * 2.7))
            for index, pid in enumerate(plan.PART_IDS)
        }
        unchanged = dict(home)
        for mode in ("full", "drive", "pan", "pi", "turn", "uno", "electronics"):
            for progress in (.89, .31, .01, .999, .72):
                mm.pose_matrices(mode, progress, home)
            self.assertEqual(mm.pose_matrices("home", .79, home), unchanged)
            self.assertEqual(mm.pose_matrices(mode, 0., home), unchanged)
        self.assertEqual(home, unchanged)
        for mode in ("drive", "turn", "pan"):
            self.assertEqual(mm.pose_matrices(mode, 1., home), unchanged)

    def test_explode_follows_rover_orientation_without_reapplying_its_translation(self):
        frame = mm.multiply(mm.translation_mm((170., -41., 28.)),
                            mm.rotation_mm((0., 0., 0.), (0., 0., 1.), 90.))
        home = {pid: frame for pid in plan.PART_IDS}
        pose = mm.pose_matrices("full", 1., home)
        self.assertEqual(pose["base"], frame)
        offsets = plan.explode_offsets("full", 1.)
        for pid in plan.PART_IDS:
            delta = mm.transform_vector(frame, offsets[pid])
            expected = tuple(a + b for a, b in zip(mm.transform_point(frame, (0., 0., 0.)), delta))
            self.assertVectorAlmostEqual(mm.transform_point(pose[pid], (0., 0., 0.)), expected)

    def test_whole_unit_relative_placements_survive_nonidentity_home(self):
        home = {
            pid: mm.multiply(mm.translation_mm((index * 1.4, index * -.8, index * .3)),
                             mm.rotation_mm((0., 0., 0.), (1., 2., 3.), index * .7))
            for index, pid in enumerate(plan.PART_IDS)
        }
        for mode in plan.EXPLODE_PHASES:
            for progress in (.07, .43, .81, 1.):
                poses = mm.pose_matrices(mode, progress, home)
                for members in plan.BOUGHT_UNITS.values():
                    deltas = []
                    for pid in members:
                        before = mm.transform_point(home[pid], (1.7, -2.4, 9.1))
                        after = mm.transform_point(poses[pid], (1.7, -2.4, 9.1))
                        deltas.append(tuple(b - a for a, b in zip(before, after)))
                    for delta in deltas[1:]:
                        self.assertVectorAlmostEqual(delta, deltas[0])

    def test_spinning_wheels_preserve_axles_and_stationary_motor_cases(self):
        common = mm.multiply(mm.translation_mm((23., 47., -11.)),
                             mm.rotation_mm((0., 0., 0.), (0., 0., 1.), 30.))
        home = {pid: common for pid in plan.PART_IDS}
        for mode in ("drive", "turn"):
            poses = mm.pose_matrices(mode, .125, home)
            moving = {pid for group in plan.WHEEL_GROUPS.values() for pid in group["ids"]}
            for pid in set(plan.PART_IDS) - moving:
                self.assertEqual(poses[pid], home[pid])
            for corner, group in plan.WHEEL_GROUPS.items():
                pivot = group["origin_mm"]
                axis_point = tuple(a + b * 20. for a, b in zip(pivot, group["axis"]))
                for pid in group["ids"]:
                    self.assertVectorAlmostEqual(mm.transform_point(poses[pid], pivot),
                                                 mm.transform_point(home[pid], pivot))
                    self.assertVectorAlmostEqual(mm.transform_point(poses[pid], axis_point),
                                                 mm.transform_point(home[pid], axis_point))

    def test_demo_rotation_is_visible_and_directionally_correct(self):
        home = {pid: mm.identity() for pid in plan.PART_IDS}
        drive = mm.pose_matrices("drive", .125, home)
        turn = mm.pose_matrices("turn", .125, home)
        for corner, group in plan.WHEEL_GROUPS.items():
            pivot = group["origin_mm"]
            bottom = (pivot[0], pivot[1], pivot[2] - 32.5)
            pid = group["ids"][0]
            spun = mm.transform_point(drive[pid], bottom)
            self.assertAlmostEqual(spun[1], pivot[1] - 32.5, places=10)
            self.assertAlmostEqual(spun[2], pivot[2], places=10)
            turned = mm.transform_point(turn[pid], bottom)
            expected_sign = 1. if corner.endswith("left") else -1.
            self.assertAlmostEqual(turned[1], pivot[1] + expected_sign * 32.5, places=10)

    def test_pan_moves_only_head_and_preserves_pan_axis(self):
        home = {pid: mm.identity() for pid in plan.PART_IDS}
        poses = mm.pose_matrices("pan", .25, home)
        pivot = plan.PAN_GROUP["origin_mm"]
        for pid in plan.PART_IDS:
            if pid not in plan.PAN_GROUP["ids"]:
                self.assertEqual(poses[pid], home[pid])
            else:
                self.assertVectorAlmostEqual(mm.transform_point(poses[pid], pivot), pivot)
        self.assertNotEqual(poses["sensor_head"], home["sensor_head"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path,
                        default=PROJECT / "verification" / "assembly_reference.json")
    parser.add_argument("--report", type=Path,
                        default=PROJECT / "offline_validation.json")
    args = parser.parse_args()
    global MANIFEST
    MANIFEST = json.loads(args.manifest.read_text(encoding="utf-8"))
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    def test_names(node):
        if isinstance(node, unittest.TestSuite):
            return [name for child in node for name in test_names(child)]
        return [node.id().split(".")[-1]]
    checks = test_names(suite)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {
        "test_scope": "Offline assembly contract and motion math; Autodesk Fusion was not run.",
        "fusion_runtime_executed": False,
        "manifest": args.manifest.name,
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "status": "passed" if result.wasSuccessful() else "failed",
        "checks": checks,
        "failed_checks": [test.id().split(".")[-1] for test, _ in result.failures + result.errors],
    }
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
