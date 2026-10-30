#!/usr/bin/env python3
"""Exercise unit conversion, archive integrity and assembly constraint checks.

These are portable input checks. No test in this file runs Autodesk Fusion or
validates a CAD kernel's geometric result.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "RoverFusion"))
from manifest_tools import (IDENTITY, ManifestError, fusion_matrix_values,
                            preflight, safe_asset_path, validate_native_recipe,
                            validate_transform)


def fixture():
    return {"units": "mm", "grounded_part_id": "base", "parts": [
        {"id": "base", "name": "Base", "step_file": "parts/base.step",
         "fidelity": "Test fixture", "physical_material": "PLA"},
        {"id": "wheel", "name": "Wheel", "step_file": "parts/wheel.step",
         "fidelity": "Test fixture", "physical_material": None}],
        "joints": [{"id": "wheel_axle", "type": "revolute", "part_a": "base",
                    "part_b": "wheel", "origin_mm": [80, 45, 20], "axis": [1, 0, 0],
                    "fidelity": "Test fixture"}]}


class PortableChecks(unittest.TestCase):
    def test_connected_tree(self):
        report = preflight(fixture(), HERE, check_files=False)
        self.assertTrue(report["active_joint_graph_is_tree"])
        self.assertEqual(report["joint_counts"]["revolute"], 1)

    def test_mm_to_cm_preserves_rotation(self):
        matrix = [0, -1, 0, 120, 1, 0, 0, -30, 0, 0, 1, 4.5, 0, 0, 0, 1]
        actual = fusion_matrix_values(matrix)
        self.assertEqual([actual[i] for i in (3, 7, 11)], [12, -3, 0.45])
        self.assertEqual([actual[i] for i in (0, 1, 4, 5, 10)], [0, -1, 1, 0, 1])

    def test_proper_180_degree_flip_allowed(self):
        matrix = [-1, 0, 0, 0, 0, 1, 0, 0, 0, 0, -1, 4.5, 0, 0, 0, 1]
        self.assertEqual(validate_transform(matrix), matrix)

    def test_scale_and_reflection_rejected(self):
        for x in (2, -1):
            matrix = list(IDENTITY)
            matrix[0] = x
            with self.assertRaises(ManifestError):
                validate_transform(matrix)

    def test_zero_axis_rejected(self):
        model = fixture()
        model["joints"][0]["axis"] = [0, 0, 0]
        with self.assertRaises(ManifestError):
            preflight(model, HERE, check_files=False)

    def test_disconnected_or_only_suppressed_joint_rejected(self):
        model = fixture()
        model["joints"][0]["enabled"] = False
        with self.assertRaises(ManifestError):
            preflight(model, HERE, check_files=False)

    def test_conflicting_active_joints_rejected(self):
        model = fixture()
        second = deepcopy(model["joints"][0])
        second.update(id="bad_fixed_wheel", type="rigid")
        model["joints"].append(second)
        with self.assertRaises(ManifestError):
            preflight(model, HERE, check_files=False)

    def test_suppressed_study_with_active_rigid_is_allowed(self):
        model = fixture()
        model["joints"][0].update(type="slider", enabled=False, limits_mm=[0, 25])
        model["joints"].append({"id": "installed", "type": "rigid", "part_a": "base", "part_b": "wheel"})
        report = preflight(model, HERE, check_files=False)
        self.assertEqual(report["joint_counts"]["suppressed"], 1)

    def test_reversed_limits_rejected(self):
        model = fixture()
        model["joints"][0].update(type="slider", limits_mm=[25, 0])
        with self.assertRaises(ManifestError):
            preflight(model, HERE, check_files=False)

    def test_asset_escape_rejected(self):
        for name in ("../outside.step", "/tmp/outside.step", "C:\\outside.step"):
            with self.assertRaises(ManifestError):
                safe_asset_path(HERE, name)

    def test_asset_hash_and_nonempty_header_gate(self):
        # This is a parser fixture, deliberately not claimed as valid CAD.
        raw = b"ISO-10303-21;\nHEADER;\n" + b"/* portable parser fixture */\n" * 5
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "parts").mkdir()
            model = fixture()
            for part in model["parts"]:
                (root / part["step_file"]).write_bytes(raw)
                part["sha256"] = hashlib.sha256(raw).hexdigest()
            self.assertEqual(preflight(model, root)["status"], "passed")
            (root / "parts/wheel.step").write_bytes(raw + b"changed")
            with self.assertRaises(ManifestError):
                preflight(model, root)

    def test_native_tube_recipe_and_invalid_bore(self):
        volume = math.pi * (6 ** 2 - 1.7 ** 2) * 40.5
        recipe = {"type": "round_post", "center_mm": [0, 0], "base_z_mm": 4.5,
                  "height_mm": 40.5, "outer_diameter_mm": 12, "bore_diameter_mm": 3.4,
                  "reference": {"bbox_min_mm": [-6, -6, 4.5], "bbox_max_mm": [6, 6, 45],
                                "volume_mm3": volume}}
        validate_native_recipe(recipe, "post")
        recipe["bore_diameter_mm"] = 13
        with self.assertRaises(ManifestError):
            validate_native_recipe(recipe, "post")

    def test_native_diagonal_slot_rejected(self):
        recipe = {"type": "plate", "center_mm": [0, 0], "base_z_mm": 45,
                  "height_mm": 3.6, "size_mm": [150, 180],
                  "cuts": [{"id": "bad_slot", "type": "slot", "centers_mm": [[0, 0], [2, 3]], "width_mm": 3.4}],
                  "reference": {"bbox_min_mm": [-75, -90, 45], "bbox_max_mm": [75, 90, 48.6],
                                "volume_mm3": 95000}}
        with self.assertRaises(ManifestError):
            validate_native_recipe(recipe, "deck")


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PortableChecks)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {"status": "passed" if result.wasSuccessful() else "failed",
              "tests_run": result.testsRun, "failures": len(result.failures),
              "errors": len(result.errors), "fusion_runtime_executed": False,
              "scope": "Portable manifest constraints, mm/cm conversion, asset integrity and recipe schema checks"}
    (HERE / "offline_code_checks.json").write_text(json.dumps(report, indent=2) + "\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)
