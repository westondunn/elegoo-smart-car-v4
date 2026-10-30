#!/usr/bin/env python3
"""Apply the C3 motor pocket directly to Weston's exact uploaded C1 STEP.

Requires CadQuery 2.7 and NumPy. Units are millimetres.
    python c3_validation_source.py --baseline ../cad/coupons/c1_motor_fit.step

Also locates ../cad/coupons/c1_motor_fit.step in the repository layout.
The baseline is read only and hash checked.

The motor-contact face, existing bores, outer footprint and C1 engraving are
preserved. Only the shared head/washer pocket and its 0.6 mm raised rim change.
This is an optional motor-fit reference, not a complete rover chassis.
"""

from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
import math
from pathlib import Path
import struct

import cadquery as cq
import numpy as np
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box


PREFIX = "Rover_V3_C3_Motor_Fit_Integrated"
BASELINE_SHA256 = "698fe5649ae5dc2c85b03735ee15082d6d2aaa577dbce6ca10e1f0e0332c684b"
P1 = (40.808039643857, 55.722195278815)
P2 = (40.808039034374, 63.522194224943)
PITCH = math.dist(P1, P2)
ANGLE_DEG = math.degrees(math.atan2(P2[1] - P1[1], P2[0] - P1[0]))
FLOOR_Z = 1.8
BASELINE_TOP_Z = 4.5
NEW_TOP_Z = 5.1
POCKET_WIDTH = 7.4
BOSS_WIDTH = 12.2


def exact_bounds(shape: cq.Shape) -> dict:
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped, box, False, False)
    b = cq.BoundBox(box)
    return {"min_mm": [b.xmin, b.ymin, b.zmin],
            "max_mm": [b.xmax, b.ymax, b.zmax],
            "size_mm": [b.xlen, b.ylen, b.zlen]}


def capsule(width: float, z: float, height: float) -> cq.Solid:
    return (cq.Workplane("XY", origin=((P1[0] + P2[0]) / 2,
                                       (P1[1] + P2[1]) / 2, z))
            .slot2D(PITCH + width, width, ANGLE_DEG)
            .extrude(height).val())


def volume(shape: cq.Shape) -> float:
    return sum(s.Volume() for s in shape.Solids())


def symmetric_difference_volume(a: cq.Shape, b: cq.Shape) -> float:
    return volume(a.cut(b)) + volume(b.cut(a))


def find_baseline(argument: str | None) -> Path:
    here = Path(__file__).resolve().parent
    candidates = ([Path(argument)] if argument else [
        here.parent / "cad" / "coupons" / "c1_motor_fit.step",
        here / "c1_motor_fit.step",
    ])
    for candidate in candidates:
        if candidate.is_file():
            actual = sha256(candidate.read_bytes()).hexdigest()
            if actual != BASELINE_SHA256:
                raise ValueError(f"Baseline SHA256 mismatch: {candidate}: {actual}")
            return candidate.resolve()
    raise FileNotFoundError("Pass --baseline with the original C1 motor-fit STEP (cad/coupons/c1_motor_fit.step)")


def build(baseline: cq.Solid) -> tuple[cq.Solid, dict]:
    assert baseline.isValid() and len(baseline.Solids()) == 1
    pocket_tool = capsule(POCKET_WIDTH, FLOOR_Z, NEW_TOP_Z - FLOOR_Z + 0.2)
    boss_tool = capsule(BOSS_WIDTH, BASELINE_TOP_Z, NEW_TOP_Z - BASELINE_TOP_Z)
    modified = baseline.fuse(boss_tool).cut(pocket_tool).clean()
    assert modified.isValid() and len(modified.Solids()) == 1
    result = modified.Solids()[0]

    # Prove every material change lies in the agreed mechanical envelopes.
    added = result.cut(baseline)
    removed = baseline.cut(result)
    allowed_removal = capsule(POCKET_WIDTH, FLOOR_Z, BASELINE_TOP_Z - FLOOR_Z)
    allowed_addition = boss_tool.cut(pocket_tool)
    added_outside = volume(added.cut(allowed_addition))
    removed_outside = volume(removed.cut(allowed_removal))
    added_shape_delta = symmetric_difference_volume(added, allowed_addition)
    expected_removed = baseline.intersect(allowed_removal)
    removed_shape_delta = symmetric_difference_volume(removed, expected_removed)
    for value in [added_outside, removed_outside,
                  added_shape_delta, removed_shape_delta]:
        assert value < 1e-6, f"Unexpected geometry change: {value} mm^3"

    # Original motor-contact structure through Z=1.8 must be unchanged.
    bb = exact_bounds(baseline)
    low_box = (cq.Workplane("XY", origin=(bb["min_mm"][0] - 1,
                                          bb["min_mm"][1] - 1, -1))
               .box(bb["size_mm"][0] + 2, bb["size_mm"][1] + 2,
                    FLOOR_Z + 1, centered=(False, False, False)).val())
    floor_diff = symmetric_difference_volume(baseline.intersect(low_box),
                                             result.intersect(low_box))
    assert floor_diff < 1e-6

    # The raised ring sits entirely above existing solid, excluding every
    # other through-hole, original engraving and the outer silhouette.
    support_ring = capsule(BOSS_WIDTH, 4.49, 0.01).cut(capsule(POCKET_WIDTH, 4.48, 0.03))
    unsupported = volume(support_ring.cut(baseline))
    assert unsupported < 1e-6, "Boss would bridge another feature or leave outline"

    # Check unobstructed original bores without recutting or reparametrizing.
    for p in [P1, P2]:
        for z in [0.1, 1.0, 1.79, 1.81, 4.49, 4.8, 5.09]:
            assert not result.isInside((p[0], p[1], z), 1e-7)
    normal = (-(P2[1] - P1[1]) / PITCH, (P2[0] - P1[0]) / PITCH)
    for p in [P1, P2, ((P1[0] + P2[0]) / 2, (P1[1] + P2[1]) / 2)]:
        x, y = p[0] + normal[0] * 2.5, p[1] + normal[1] * 2.5
        assert result.isInside((x, y, 1.799), 1e-7)
        assert not result.isInside((x, y, 1.801), 1e-7)
    return result, {
        "baseline_valid": True,
        "revised_valid": True,
        "solid_count": 1,
        "actual_added_volume_mm3": volume(added),
        "actual_removed_volume_mm3": volume(removed),
        "added_volume_outside_allowed_boss_ring_mm3": added_outside,
        "removed_volume_outside_allowed_pocket_mm3": removed_outside,
        "added_vs_expected_ring_symmetric_difference_mm3": added_shape_delta,
        "removed_vs_expected_pocket_expansion_symmetric_difference_mm3": removed_shape_delta,
        "motor_floor_and_contact_structure_symmetric_difference_mm3": floor_diff,
        "boss_support_missing_from_baseline_mm3": unsupported,
        "original_bores_unobstructed": True,
        "washer_floor_plane_confirmed_z_mm": FLOOR_Z,
        "other_holes_outer_footprint_and_C1_engraving_preserved": True,
        "change_scope": "Only expanded shared pocket at Z>=1.8 and raised ring at Z4.5..5.1",
    }


def verify_stl(path: Path, cad_volume: float) -> dict:
    raw = path.read_bytes()
    n = struct.unpack_from("<I", raw, 80)[0]
    assert len(raw) == 84 + 50 * n and n > 0
    dtype = np.dtype([("normal", "<f4", (3,)), ("vertices", "<f4", (3, 3)),
                      ("attribute", "<u2")])
    xyz = np.frombuffer(raw, dtype=dtype, offset=84)["vertices"].astype(float)
    verts, indices = np.unique(np.round(xyz.reshape(-1, 3), 5),
                               axis=0, return_inverse=True)
    faces = indices.reshape(-1, 3)
    edges = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    undirected = np.sort(edges, axis=1)
    _, counts = np.unique(undirected, axis=0, return_counts=True)
    assert np.all(counts == 2)
    directed_counts = Counter(map(tuple, edges.tolist()))
    assert all(directed_counts[(b, a)] == c for (a, b), c in directed_counts.items())
    assert np.all(np.linalg.norm(np.cross(xyz[:, 1] - xyz[:, 0],
                                         xyz[:, 2] - xyz[:, 0]), axis=1) > 1e-12)
    parents = list(range(len(verts)))

    def find(a: int) -> int:
        while parents[a] != a:
            parents[a] = parents[parents[a]]
            a = parents[a]
        return a

    for a, b in undirected:
        ra, rb = find(int(a)), find(int(b))
        if ra != rb:
            parents[rb] = ra
    components = len({find(i) for i in range(len(verts))})
    assert components == 1
    mesh_volume = float(np.einsum("ij,ij->i", xyz[:, 0],
                                  np.cross(xyz[:, 1], xyz[:, 2])).sum() / 6)
    assert mesh_volume > 0
    error = abs(mesh_volume - cad_volume) / cad_volume
    assert error < 0.002
    return {"triangles": int(n), "connected_components": components,
            "watertight_two_faces_per_edge": True, "consistent_outward_winding": True,
            "no_degenerate_triangles": True, "volume_mm3": mesh_volume,
            "relative_volume_error": error,
            "bounds_mm": {"min": xyz.min(axis=(0, 1)).tolist(),
                          "max": xyz.max(axis=(0, 1)).tolist()}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    baseline_path = find_baseline(args.baseline)
    args.out.mkdir(parents=True, exist_ok=True)
    baseline = cq.importers.importStep(str(baseline_path)).val().Solids()[0]
    result, checks = build(baseline)
    step_path = args.out / f"{PREFIX}.step"
    stl_path = args.out / f"{PREFIX}.stl"
    result.exportStep(str(step_path))
    result.exportStl(str(stl_path), tolerance=0.015, angularTolerance=0.08,
                     ascii=False, relative=False, parallel=True)
    reopened = cq.importers.importStep(str(step_path)).val()
    assert reopened.isValid() and len(reopened.Solids()) == 1
    step_delta = abs(reopened.Volume() - result.Volume())
    assert step_delta / result.Volume() < 1e-8
    checks["STEP_roundtrip"] = {"valid": True, "solid_count": 1,
                                "absolute_volume_delta_mm3": step_delta}
    checks["STL"] = verify_stl(stl_path, result.Volume())
    record = {
        "part": PREFIX, "revision": "C3", "units": "mm",
        "baseline": {"filename": baseline_path.name, "sha256": BASELINE_SHA256,
                     "volume_mm3": baseline.Volume(), "bounds": exact_bounds(baseline)},
        "dimensions": {
            "original_bore_diameter_mm": 3.2,
            "bore_centers_xy_mm": [P1, P2], "pitch_mm": PITCH,
            "capsule_angle_degrees": ANGLE_DEG,
            "shared_pocket_width_mm": POCKET_WIDTH,
            "shared_pocket_overall_length_mm": PITCH + POCKET_WIDTH,
            "shared_pocket_depth_mm": NEW_TOP_Z - FLOOR_Z,
            "washer_seat_plane_z_mm": FLOOR_Z,
            "motor_contact_plane_z_mm": 0,
            "unchanged_body_thickness_mm": BASELINE_TOP_Z,
            "boss_top_plane_z_mm": NEW_TOP_Z,
            "boss_added_height_mm": NEW_TOP_Z - BASELINE_TOP_Z,
            "boss_outer_width_mm": BOSS_WIDTH,
            "boss_overall_length_mm": PITCH + BOSS_WIDTH,
            "boss_wall_mm": (BOSS_WIDTH - POCKET_WIDTH) / 2,
            "boss_bounds": exact_bounds(capsule(BOSS_WIDTH, BASELINE_TOP_Z,
                                                NEW_TOP_Z - BASELINE_TOP_Z)),
        },
        "geometry": {"bounds": exact_bounds(result), "volume_mm3": result.Volume(),
                     "solid_equivalent_mass_g_at_assumed_PLA_1_24_g_cm3": result.Volume() / 1000 * 1.24},
        "checks": checks,
        "notes": [
            "Exact uploaded C1 solid is modified directly; no reconstruction of the original outer profile or other holes.",
            "Original C1 engraving is retained as a baseline marking. No new text changes the geometry.",
            "The motor-contact face and Z1.8 washer seat remain fixed, preserving screw grip thickness.",
            "This optional fit reference is not a full chassis and does not require repeating a previously successful fit test.",
            "CAD and mesh validation do not constitute a new physical fit test or load rating.",
            "Illustrative solid-equivalent mass uses an assumed density; actual sliced mass depends on print settings and filament.",
        ],
        "exports": {p.name: {"bytes": p.stat().st_size,
                              "sha256": sha256(p.read_bytes()).hexdigest()}
                    for p in [step_path, stl_path]},
    }
    (args.out / f"{PREFIX}_dimensions.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"output": str(args.out), "geometry": record["geometry"],
                      "checks": checks}, indent=2))


if __name__ == "__main__":
    main()
