"""Portable, dependency-free preflight for the Rover Fusion assembly.

This module deliberately does not import Autodesk modules. Lengths in the input
are millimetres. Fusion uses centimetres internally; conversion happens in the
desktop builder, never in the STEP payload itself.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re


IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ManifestError(ValueError):
    pass


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ManifestError(f"{label} must be a finite number")
    if not math.isfinite(value):
        raise ManifestError(f"{label} must be finite")
    return float(value)


def vector(value, length, label):
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise ManifestError(f"{label} must have {length} entries")
    return [_number(v, f"{label}[{i}]") for i, v in enumerate(value)]


def normalized_axis(value, label="axis"):
    axis = vector(value, 3, label)
    size = math.sqrt(sum(x * x for x in axis))
    if size < 1e-12:
        raise ManifestError(f"{label} cannot be zero")
    return [x / size for x in axis]


def validate_transform(value):
    """Check a row-major proper rigid transform, with translation in mm."""
    m = vector(value, 16, "transform_mm")
    if max(abs(a - b) for a, b in zip(m[12:16], [0, 0, 0, 1])) > 1e-8:
        raise ManifestError("transform_mm must end with [0, 0, 0, 1]")
    rows = [m[0:3], m[4:7], m[8:11]]
    for i in range(3):
        for j in range(3):
            expected = 1 if i == j else 0
            if abs(sum(a * b for a, b in zip(rows[i], rows[j])) - expected) > 1e-6:
                raise ManifestError("transform_mm must be orthonormal; scaling is not allowed")
    a, b, c = rows
    determinant = (a[0] * (b[1] * c[2] - b[2] * c[1])
                   - a[1] * (b[0] * c[2] - b[2] * c[0])
                   + a[2] * (b[0] * c[1] - b[1] * c[0]))
    if abs(determinant - 1) > 1e-6:
        raise ManifestError("transform_mm must be a proper rotation; reflection is not allowed")
    return m


def fusion_matrix_values(value):
    m = validate_transform(value)
    for index in (3, 7, 11):
        m[index] /= 10.0
    return m


def safe_asset_path(bundle, relative):
    if not isinstance(relative, str) or not relative.strip():
        raise ManifestError("step_file must be a non-empty relative path")
    p = Path(relative)
    if p.is_absolute() or "\\" in relative or ":" in relative:
        raise ManifestError(f"Asset path must use portable relative slash notation: {relative}")
    base = Path(bundle).resolve()
    result = (base / p).resolve()
    if base not in result.parents:
        raise ManifestError(f"Asset path escapes the script bundle: {relative}")
    if result.suffix.lower() not in (".step", ".stp"):
        raise ManifestError(f"Expected a STEP asset: {relative}")
    return result


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _identifier(value, label):
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ManifestError(f"{label} must use letters, digits and underscores and start with a letter or underscore")
    return value


def validate_native_recipe(recipe, part_id):
    if not isinstance(recipe, dict) or recipe.get("type") not in ("round_post", "rectangular_post", "plate"):
        raise ManifestError(f"{part_id}: unsupported native recipe")
    kind = recipe["type"]
    vector(recipe.get("center_mm"), 2, f"{part_id}.native_recipe.center_mm")
    _number(recipe.get("base_z_mm"), "native base_z_mm")
    height = _number(recipe.get("height_mm"), "native height_mm")
    if height <= 0:
        raise ManifestError(f"{part_id}: native extrusion height must be positive")
    if kind == "round_post":
        width = length = _number(recipe.get("outer_diameter_mm"), "native outer_diameter_mm")
    else:
        width, length = vector(recipe.get("size_mm"), 2, "native size_mm")
    if min(width, length) <= 0:
        raise ManifestError(f"{part_id}: native outside dimensions must be positive")
    radius = _number(recipe.get("corner_radius_mm", 0), "native corner_radius_mm")
    if radius < 0 or radius >= min(width, length) / 2 or (kind == "round_post" and radius):
        raise ManifestError(f"{part_id}: invalid native outside corner radius")
    bore = _number(recipe.get("bore_diameter_mm", 0), "native bore_diameter_mm")
    if bore < 0 or bore >= min(width, length):
        raise ManifestError(f"{part_id}: native bore must fit within the outside profile")
    cb = _number(recipe.get("counterbore_diameter_mm", 0), "native counterbore_diameter_mm")
    if cb:
        depth = _number(recipe.get("counterbore_depth_mm"), "native counterbore_depth_mm")
        if cb <= bore or cb >= min(width, length) or not 0 < depth < height:
            raise ManifestError(f"{part_id}: invalid native counterbore")
    for name in recipe.get("parameters", {}).values():
        _identifier(name, "native parameter name")
    cut_ids = set()
    for cut in recipe.get("cuts", []):
        cid = _identifier(cut.get("id"), "native cut id")
        if cid in cut_ids or cid in ("bore", "counterbore"):
            raise ManifestError(f"{part_id}: native cut id is duplicated or reserved: {cid}")
        cut_ids.add(cid)
        kind = cut.get("type")
        if kind in ("circle", "rectangle"):
            vector(cut.get("center_mm"), 2, "native cut center_mm")
            dims = ([cut.get("diameter_mm")] if kind == "circle" else cut.get("size_mm"))
            dimensions = vector(dims, 1 if kind == "circle" else 2, "native cut dimensions")
        elif kind == "slot":
            ends = cut.get("centers_mm")
            if not isinstance(ends, list) or len(ends) != 2:
                raise ManifestError("Native slot needs two centre points")
            a = vector(ends[0], 2, "native slot first centre")
            b = vector(ends[1], 2, "native slot second centre")
            dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
            if (dx < 1e-8) == (dy < 1e-8):
                raise ManifestError("Native slot must have distinct, axis-aligned end centres")
            dimensions = [_number(cut.get("width_mm"), "native slot width_mm")]
        else:
            raise ManifestError(f"{part_id}: unsupported native cut type")
        if min(dimensions) <= 0:
            raise ManifestError("Native cut dimensions must be positive")
        if not cut.get("through", True):
            depth = _number(cut.get("depth_mm"), "native pocket depth_mm")
            if not 0 < depth < height:
                raise ManifestError("Native pocket depth must be within the part")
    reference = recipe.get("reference", {})
    lo = vector(reference.get("bbox_min_mm"), 3, "native reference bbox_min_mm")
    hi = vector(reference.get("bbox_max_mm"), 3, "native reference bbox_max_mm")
    if any(hi[i] <= lo[i] for i in range(3)) or _number(reference.get("volume_mm3"), "native reference volume_mm3") <= 0:
        raise ManifestError("Native STEP reference must have positive dimensions and volume")


def preflight(manifest, bundle, check_files=True):
    """Return a machine-readable report or raise ManifestError before CAD edits."""
    if not isinstance(manifest, dict):
        raise ManifestError("The manifest must be a JSON object")
    if manifest.get("format_version", 1) != 1:
        raise ManifestError("Unsupported assembly manifest version")
    if manifest.get("units", "mm") != "mm":
        raise ManifestError("This builder requires millimetre manifest coordinates")
    parts = manifest.get("parts")
    if not isinstance(parts, list) or not parts:
        raise ManifestError("parts must be a non-empty list")
    part_ids = set()
    warnings = []
    asset_records = []
    for part in parts:
        if not isinstance(part, dict):
            raise ManifestError("Each part must be an object")
        pid = _identifier(part.get("id"), "part id")
        if pid in part_ids:
            raise ManifestError(f"Duplicate part id: {pid}")
        part_ids.add(pid)
        if not isinstance(part.get("name"), str) or not part["name"].strip():
            raise ManifestError(f"{pid}: name is required")
        validate_transform(part.get("transform_mm", IDENTITY))
        if "native_recipe" in part:
            validate_native_recipe(part["native_recipe"], pid)
        if "color_rgba" in part:
            rgba = vector(part["color_rgba"], 4, f"{pid}.color_rgba")
            if any(x < 0 or x > 255 or int(x) != x for x in rgba):
                raise ManifestError(f"{pid}: color channels must be integers from 0 to 255")
        path = safe_asset_path(bundle, part.get("step_file"))
        record = {"part_id": pid, "step_file": part["step_file"]}
        if check_files:
            if not path.is_file() or path.stat().st_size < 100:
                raise ManifestError(f"{pid}: missing or empty STEP asset: {part['step_file']}")
            header = path.read_bytes()[:500]
            if b"ISO-10303-21" not in header:
                raise ManifestError(f"{pid}: STEP file does not have an ISO-10303-21 header")
            actual_sha = sha256_file(path)
            if part.get("sha256") and actual_sha != part["sha256"].lower():
                raise ManifestError(f"{pid}: STEP hash mismatch")
            record.update(bytes=path.stat().st_size, sha256=actual_sha)
        asset_records.append(record)
        if not part.get("fidelity"):
            warnings.append(f"{pid}: no geometry fidelity note")
        if "physical_material" not in part:
            warnings.append(f"{pid}: no material intent specified")

    grounded = manifest.get("grounded_part_id")
    if grounded not in part_ids:
        raise ManifestError("grounded_part_id must name a part in the manifest")
    parameter_ids = set()
    for parameter in manifest.get("parameters", []):
        name = _identifier(parameter.get("name"), "parameter name")
        if name in parameter_ids:
            raise ManifestError(f"Duplicate parameter: {name}")
        parameter_ids.add(name)
        if not isinstance(parameter.get("expression"), str):
            raise ManifestError(f"{name}: parameter expression must be a string")
        if parameter.get("units", "mm") not in ("mm", "cm", "in", "deg", "rad", ""):
            raise ManifestError(f"{name}: unsupported parameter units")

    joint_ids = set()
    adjacency = {pid: set() for pid in part_ids}
    joint_counts = {"rigid": 0, "revolute": 0, "slider": 0, "suppressed": 0}
    active_pairs = set()
    for joint in manifest.get("joints", []):
        jid = _identifier(joint.get("id"), "joint id")
        if jid in joint_ids:
            raise ManifestError(f"Duplicate joint id: {jid}")
        joint_ids.add(jid)
        kind = joint.get("type")
        if kind not in ("rigid", "revolute", "slider"):
            raise ManifestError(f"{jid}: unsupported joint type {kind}")
        a, b = joint.get("part_a"), joint.get("part_b")
        if a not in part_ids or b not in part_ids or a == b:
            raise ManifestError(f"{jid}: joint must connect two distinct declared parts")
        if kind != "rigid":
            vector(joint.get("origin_mm"), 3, f"{jid}.origin_mm")
            normalized_axis(joint.get("axis"), f"{jid}.axis")
            if not joint.get("fidelity"):
                warnings.append(f"{jid}: moving-joint origin is a reference datum until confirmed against actual hardware")
        limit_key = "limits_mm" if kind == "slider" else "limits_deg"
        if limit_key in joint:
            limits = vector(joint[limit_key], 2, f"{jid}.{limit_key}")
            if limits[0] > limits[1]:
                raise ManifestError(f"{jid}: lower joint limit exceeds upper limit")
        if not isinstance(joint.get("enabled", True), bool):
            raise ManifestError(f"{jid}: enabled must be boolean")
        joint_counts[kind] += 1
        if joint.get("enabled", True):
            pair = tuple(sorted((a, b)))
            if pair in active_pairs:
                raise ManifestError(f"{jid}: multiple active joints between the same two parts")
            active_pairs.add(pair)
            adjacency[a].add(b)
            adjacency[b].add(a)
        else:
            joint_counts["suppressed"] += 1

    visited, pending = set(), [grounded]
    while pending:
        pid = pending.pop()
        if pid not in visited:
            visited.add(pid)
            pending.extend(adjacency[pid] - visited)
    disconnected = sorted(part_ids - visited)
    if disconnected:
        raise ManifestError("Unconstrained parts with no active path to the grounded base: "
                            + ", ".join(disconnected))
    active_edges = len(active_pairs)
    if active_edges > len(part_ids) - 1:
        warnings.append("Active joint graph contains loops; inspect for redundant constraints in Fusion")
    for sketch in manifest.get("reference_sketches", []):
        _identifier(sketch.get("id"), "reference sketch id")
        _number(sketch.get("z_mm", 0), "reference sketch z_mm")
        for circle in sketch.get("circles", []):
            vector(circle.get("center_mm"), 2, "reference circle center_mm")
            if _number(circle.get("diameter_mm"), "reference circle diameter_mm") <= 0:
                raise ManifestError("Reference circle diameter must be positive")
        for rectangle in sketch.get("rectangles", []):
            lo = vector(rectangle.get("min_mm"), 2, "reference rectangle min_mm")
            hi = vector(rectangle.get("max_mm"), 2, "reference rectangle max_mm")
            if any(hi[i] <= lo[i] for i in (0, 1)):
                raise ManifestError("Reference rectangle dimensions must be positive")

    return {"status": "passed", "validation_scope": "Portable input and asset preflight; Fusion runtime has not run",
            "part_count": len(parts), "grounded_part_id": grounded,
            "joint_counts": joint_counts, "active_joint_graph_connected": True,
            "active_joint_graph_is_tree": active_edges == len(part_ids) - 1,
            "native_recipe_part_count": sum("native_recipe" in part for part in parts),
            "parameter_count": len(parameter_ids), "warnings": warnings,
            "assets": asset_records}


def load_and_preflight(path, check_files=True):
    path = Path(path).resolve()
    with path.open("r", encoding="utf-8") as stream:
        manifest = json.load(stream)
    return manifest, preflight(manifest, path.parent, check_files)


def bom_rows(manifest):
    rows = []
    for part in manifest["parts"]:
        material = part.get("physical_material")
        if isinstance(material, dict):
            material = material.get("name", "")
        fidelity = part.get("fidelity", "Unspecified")
        if not isinstance(fidelity, str):
            fidelity = json.dumps(fidelity, ensure_ascii=False, sort_keys=True)
        rows.append({"part_id": part["id"], "name": part["name"], "quantity": 1,
                     "category": part.get("category", ""),
                     "material_intent": material or "Composite/reference or unspecified",
                     "geometry_fidelity": fidelity,
                     "step_file": part["step_file"], "notes": part.get("notes", "")})
    return rows
