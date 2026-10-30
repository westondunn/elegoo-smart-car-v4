"""Small, printer-neutral 3MF Core mesh writer and validation helpers.

Only NumPy and the Python standard library are needed. All coordinates are mm.
Every input mesh is an independent, named object and build item. No print profile,
filament assignment, G-code, network destination, or machine setting is written.

API::

    report = write_3mf("parts.model.3mf", [
        {"name": "sensor_bracket", "vertices": vertices, "faces": triangles,
         "color": "#F2B705", "transform": np.eye(4)}
    ])
    parts = read_3mf("parts.model.3mf")["objects"]
    report = validate_3mf("parts.model.3mf")

Input transforms are conventional 4x4 matrices with translation in the last
column, so world_xyz = local_xyz @ transform[:3, :3].T + transform[:3, 3].
The writer converts this to the row-vector 12-number serialization in 3MF.

Specification: https://github.com/3MFConsortium/spec_core/blob/master/3MF%20Core%20Specification.md
Scope: core mesh resources, optional core base display colors, build transforms.
The reader deliberately rejects component assemblies and required extensions:
it is a validator for this exporter, not a general-purpose 3MF implementation.
Mesh checks do not certify self-intersection, minimum walls, slicer acceptance,
printer fit, mechanical fit, or safety of a physical assembly.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
from typing import Any, Iterable, Mapping
import xml.etree.ElementTree as ET
import zipfile

import numpy as np

CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
TYPES = "http://schemas.openxmlformats.org/package/2006/content-types"
START_REL = "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"
MODEL_TYPE = "application/vnd.ms-package.3dmanufacturing-3dmodel+xml"
MODEL_PART = "3D/3dmodel.model"
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")
_XML_CONTROL_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\uD800-\uDFFF\uFFFE\uFFFF]")


class ValidationError(ValueError):
    """Invalid input geometry or unsupported/invalid 3MF package."""


def _text(value: Any, label: str) -> str:
    value = str(value)
    if _XML_CONTROL_RE.search(value):
        raise ValidationError(f"{label} contains a character forbidden in XML 1.0")
    return value


def _number(value: float) -> str:
    # 17 significant digits preserve IEEE float64 round trips; locale independent.
    return "0" if value == 0 else format(float(value), ".17g")


def _arrays(vertices: Any, faces: Any) -> tuple[np.ndarray, np.ndarray]:
    v = np.asarray(vertices, dtype=np.float64)
    raw_f = np.asarray(faces)
    if v.ndim != 2 or v.shape[1:] != (3,) or len(v) < 4:
        raise ValidationError("vertices must have shape (N, 3), N >= 4")
    if raw_f.ndim != 2 or raw_f.shape[1:] != (3,) or len(raw_f) < 4:
        raise ValidationError("faces must have shape (M, 3), M >= 4")
    if not np.isfinite(v).all():
        raise ValidationError("vertices contain NaN or infinity")
    if raw_f.dtype.kind not in "iu":
        try:
            numeric_f = raw_f.astype(np.float64)
        except (TypeError, ValueError) as exc:
            raise ValidationError("triangle indices must be integers") from exc
        if not np.isfinite(numeric_f).all() or not np.equal(numeric_f, np.floor(numeric_f)).all():
            raise ValidationError("triangle indices must be finite integers")
        raw_f = numeric_f
    if np.any(raw_f < 0) or np.any(raw_f >= len(v)):
        raise ValidationError("triangle index is outside the vertex array")
    if len(v) >= 2**31 or len(raw_f) >= 2**31:
        raise ValidationError("3MF core resource index limit exceeded")
    return np.ascontiguousarray(v), np.ascontiguousarray(raw_f, dtype=np.int64)


def _transform(value: Any = None) -> np.ndarray:
    m = np.eye(4) if value is None else np.asarray(value, dtype=np.float64)
    if m.shape != (4, 4) or not np.isfinite(m).all():
        raise ValidationError("transform must be a finite 4x4 affine matrix")
    if not np.allclose(m[3], [0, 0, 0, 1], atol=1e-12, rtol=0):
        raise ValidationError("transform last row must be [0, 0, 0, 1]")
    if abs(np.linalg.det(m[:3, :3])) < 1e-12:
        raise ValidationError("transform is singular or nearly singular")
    return m.copy()


def transform_vertices(vertices: Any, transform: Any = None) -> np.ndarray:
    """Apply a conventional column-vector affine transform to Nx3 vertices."""
    m = _transform(transform)
    return np.asarray(vertices, dtype=np.float64) @ m[:3, :3].T + m[:3, 3]


def _color(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        if not _COLOR_RE.fullmatch(value):
            raise ValidationError("color must be #RRGGBB or #RRGGBBAA")
        return value.upper()
    a = np.asarray(value)
    if a.shape not in ((3,), (4,)) or not np.isfinite(a.astype(float)).all():
        raise ValidationError("color must contain three or four finite channels")
    if a.dtype.kind == "f" and np.all((a >= 0) & (a <= 1)):
        a = np.rint(a * 255)
    if not np.equal(a, np.floor(a)).all() or np.any(a < 0) or np.any(a > 255):
        raise ValidationError("color channels must be float 0..1 or integer 0..255")
    return "#" + "".join(f"{int(c):02X}" for c in a)


def weld_mesh(vertices: Any, faces: Any, tolerance: float = 1e-6) -> tuple[np.ndarray, np.ndarray, dict]:
    """Merge near-coincident vertices; do not silently delete or flip faces.

    Coordinates are rounded to a tolerance-sized grid to form deterministic
    vertex groups. A group uses its first original coordinate, so exact source
    coordinates are retained. This is quantized welding, not a radius search:
    neighboring grid cells can contain points closer than tolerance. Always run
    mesh_stats after welding. A too-large tolerance can collapse thin features.
    """
    v, f = _arrays(vertices, faces)
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise ValidationError("weld tolerance must be finite and > 0 mm")
    scaled = v / tolerance
    if np.max(np.abs(scaled)) >= np.iinfo(np.int64).max - 1:
        raise ValidationError("coordinates are too large for this weld tolerance")
    keys = np.rint(scaled).astype(np.int64)
    _, first, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    welded = v[first]
    remapped = inverse[f]
    return welded, remapped, {
        "input_vertices": len(v), "output_vertices": len(welded),
        "merged_vertices": len(v) - len(welded), "tolerance_mm": tolerance,
        "faces_removed": 0, "method": "quantized_grid_first_coordinate",
    }


def _component_faces(f: np.ndarray, edge_order: np.ndarray, counts: np.ndarray) -> list[list[int]]:
    parent = np.arange(len(f), dtype=np.int64)

    def root(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = int(parent[a])
        return a

    # The raw edge array is [all AB, all BC, all CA].
    start = 0
    for count in counts:
        edge_faces = edge_order[start:start + int(count)] % len(f)
        if count > 1:
            r = root(int(edge_faces[0]))
            for b in edge_faces[1:]:
                parent[root(int(b))] = r
        start += int(count)
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(f)):
        groups[root(i)].append(i)
    return list(groups.values())


def _nonmanifold_vertices(f: np.ndarray) -> list[int]:
    # A closed 2-manifold has one connected cycle in every vertex's link graph.
    links: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for a, b, c in f.tolist():
        links[a].append((b, c))
        links[b].append((c, a))
        links[c].append((a, b))
    bad = []
    for vertex, edges in links.items():
        adjacent: dict[int, list[int]] = defaultdict(list)
        for a, b in edges:
            adjacent[a].append(b)
            adjacent[b].append(a)
        if any(len(neighbors) != 2 for neighbors in adjacent.values()):
            bad.append(vertex)
            continue
        remaining = set(adjacent)
        stack = [next(iter(remaining))]
        while stack:
            current = stack.pop()
            if current not in remaining:
                continue
            remaining.remove(current)
            stack.extend(adjacent[current])
        if remaining:
            bad.append(vertex)
    return bad


def mesh_stats(vertices: Any, faces: Any, *, check_vertex_manifold: bool = True) -> dict:
    """Check indexed topology, winding, degeneracy, finite extent, and volume.

    Errors fail strict export. Multiple disconnected surface shells are reported
    but are not by themselves invalid (e.g. enclosed cavities). Negative-volume
    shells are warnings because a valid enclosed cavity has inward-facing normals
    relative to its own surface. Containment/self-intersections are not checked.
    """
    v, f = _arrays(vertices, faces)
    errors: list[str] = []
    warnings: list[str] = []
    bbox = np.array([v.min(axis=0), v.max(axis=0)])
    centered = v - bbox.mean(axis=0)
    tri = centered[f]
    twice_area = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    area_threshold = max(1e-18, float(np.max(bbox[1] - bbox[0]))**2 * 1e-14)
    degenerate = int(np.count_nonzero(twice_area <= area_threshold))
    if degenerate:
        errors.append(f"{degenerate} zero-area or near-zero-area triangles")
    canonical_faces = np.sort(f, axis=1)
    duplicate_faces = len(f) - len(np.unique(canonical_faces, axis=0))
    if duplicate_faces:
        errors.append(f"{duplicate_faces} duplicate triangles (including opposite winding)")

    directed = np.concatenate((f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]))
    undirected = np.sort(directed, axis=1)
    _, inverse, counts = np.unique(undirected, axis=0, return_inverse=True, return_counts=True)
    edge_order = np.argsort(inverse, kind="stable")
    boundary = int(np.count_nonzero(counts == 1))
    nonmanifold = int(np.count_nonzero(counts > 2))
    signed = np.where(directed[:, 0] < directed[:, 1], 1, -1)
    balance = np.bincount(inverse, weights=signed, minlength=len(counts))
    inconsistent = int(np.count_nonzero((counts == 2) & (balance != 0)))
    if boundary:
        errors.append(f"{boundary} open boundary edges")
    if nonmanifold:
        errors.append(f"{nonmanifold} edges incident to more than two triangles")
    if inconsistent:
        errors.append(f"{inconsistent} edges with inconsistent triangle winding")

    bad_vertices = _nonmanifold_vertices(f) if check_vertex_manifold else []
    if bad_vertices:
        errors.append(f"{len(bad_vertices)} vertices with a disconnected or noncyclic link")
    unused = len(v) - len(np.unique(f))
    if unused:
        warnings.append(f"{unused} vertices are not referenced by any triangle")

    per_face_volume = np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])) / 6.0
    volume = float(per_face_volume.sum())
    if volume <= 0:
        errors.append("signed mesh volume is not positive")
    components = _component_faces(f, edge_order, counts)
    component_volumes = [float(per_face_volume[g].sum()) for g in components]
    if len(components) > 1:
        warnings.append(f"{len(components)} edge-connected surface shells; shell containment is not checked")
    if any(x < 0 for x in component_volumes):
        warnings.append("negative-volume shell present; verify that it defines an enclosed cavity")
    return {
        "valid": not errors, "vertices": len(v), "triangles": len(f),
        "edges": len(counts), "boundary_edges": boundary,
        "nonmanifold_edges": nonmanifold, "inconsistent_winding_edges": inconsistent,
        "nonmanifold_vertices": len(bad_vertices) if check_vertex_manifold else None,
        "degenerate_triangles": degenerate, "duplicate_triangles": int(duplicate_faces),
        "unused_vertices": int(unused), "connected_surface_shells": len(components),
        "surface_shell_signed_volumes_mm3": component_volumes,
        "signed_volume_mm3": volume, "surface_area_mm2": float(twice_area.sum() / 2),
        "bounds_mm": bbox.tolist(), "size_mm": (bbox[1] - bbox[0]).tolist(),
        "errors": errors, "warnings": warnings,
        "self_intersection_check": "not_performed",
    }


def _xml_bytes(element: ET.Element, namespace: str) -> bytes:
    ET.register_namespace("", namespace)
    return ET.tostring(element, encoding="utf-8", xml_declaration=True)


def write_3mf(
    path: str | Path,
    objects: Iterable[Mapping[str, Any]],
    *,
    title: str = "ELEGOO rover parts",
    description: str = "Independent model objects; millimeters; select printer and PLA settings in the slicer.",
    strict: bool = True,
) -> dict:
    """Write a printer-neutral core 3MF; re-read and validate before returning.

    Required object keys: name, vertices, faces. Optional: color, transform.
    No automatic welding, mesh repair, bed placement, scaling, or face flipping.
    strict=True rejects errors before writing and any read-back validation errors.
    """
    prepared = []
    names = set()
    for supplied in objects:
        name = _text(supplied.get("name", ""), "object name").strip()
        if not name or name in names:
            raise ValidationError("objects require unique, nonempty names")
        names.add(name)
        v, f = _arrays(supplied["vertices"], supplied["faces"])
        stats = mesh_stats(v, f)
        if strict and stats["errors"]:
            raise ValidationError(f"{name}: " + "; ".join(stats["errors"]))
        prepared.append({"name": name, "vertices": v, "faces": f,
                         "color": _color(supplied.get("color")),
                         "transform": _transform(supplied.get("transform"))})
    if not prepared:
        raise ValidationError("at least one build object is required")

    q = lambda local: f"{{{CORE}}}{local}"
    model = ET.Element(q("model"), {"unit": "millimeter", "{http://www.w3.org/XML/1998/namespace}lang": "en-US"})
    for key, value in (("Title", title), ("Description", description), ("Application", "rover_3mf.py / Python NumPy")):
        ET.SubElement(model, q("metadata"), {"name": key}).text = _text(value, key)
    resources = ET.SubElement(model, q("resources"))
    palette = list(dict.fromkeys(p["color"] for p in prepared if p["color"] is not None))
    next_id = 1
    if palette:
        materials = ET.SubElement(resources, q("basematerials"), {"id": "1"})
        for index, c in enumerate(palette):
            ET.SubElement(materials, q("base"), {"name": f"Display color {index + 1} {c}", "displaycolor": c})
        next_id += 1
    build_ids = []
    for p in prepared:
        attributes = {"id": str(next_id), "type": "model", "name": p["name"], "partnumber": p["name"]}
        if p["color"] is not None:
            attributes.update(pid="1", pindex=str(palette.index(p["color"])))
        obj = ET.SubElement(resources, q("object"), attributes)
        mesh = ET.SubElement(obj, q("mesh"))
        vertices = ET.SubElement(mesh, q("vertices"))
        for x, y, z in p["vertices"]:
            ET.SubElement(vertices, q("vertex"), {"x": _number(x), "y": _number(y), "z": _number(z)})
        triangles = ET.SubElement(mesh, q("triangles"))
        for a, b, c in p["faces"]:
            ET.SubElement(triangles, q("triangle"), {"v1": str(a), "v2": str(b), "v3": str(c)})
        build_ids.append(next_id)
        next_id += 1
    build = ET.SubElement(model, q("build"))
    for object_id, p in zip(build_ids, prepared):
        # Standard column-vector transform -> 3MF row-vector first-three-columns.
        values = p["transform"].T[:, :3].reshape(-1)
        ET.SubElement(build, q("item"), {"objectid": str(object_id), "partnumber": p["name"],
                                        "transform": " ".join(_number(x) for x in values)})

    types = ET.Element(f"{{{TYPES}}}Types")
    ET.SubElement(types, f"{{{TYPES}}}Default", {"Extension": "rels", "ContentType": "application/vnd.openxmlformats-package.relationships+xml"})
    ET.SubElement(types, f"{{{TYPES}}}Default", {"Extension": "model", "ContentType": MODEL_TYPE})
    rels = ET.Element(f"{{{RELS}}}Relationships")
    ET.SubElement(rels, f"{{{RELS}}}Relationship", {"Target": "/" + MODEL_PART, "Id": "rel-1", "Type": START_REL})
    payload = {
        "[Content_Types].xml": _xml_bytes(types, TYPES),
        "_rels/.rels": _xml_bytes(rels, RELS),
        MODEL_PART: _xml_bytes(model, CORE),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Stable ZIP member time enables repeatable exports from the same geometry.
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as package:
        for member, data in payload.items():
            info = zipfile.ZipInfo(member, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            package.writestr(info, data)
    report = validate_3mf(path)
    if strict and not report["valid"]:
        raise ValidationError("Written 3MF failed read-back validation: " + "; ".join(report["errors"]))
    reread = read_3mf(path)
    for before, after in zip(prepared, reread["objects"]):
        if before["name"] != after["name"] or not np.array_equal(before["vertices"], after["vertices"]) or not np.array_equal(before["faces"], after["faces"]) or not np.array_equal(before["transform"], after["transform"]):
            raise ValidationError("3MF round trip did not preserve geometry/name/placement exactly")
    report["round_trip_geometry_exact"] = True
    return report


def _parse_xml(data: bytes, label: str) -> ET.Element:
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValidationError(f"{label}: DTD/entity declarations are forbidden")
    try:
        data.decode("utf-8", errors="strict")
        return ET.fromstring(data)
    except (ET.ParseError, UnicodeDecodeError) as exc:
        raise ValidationError(f"{label}: invalid UTF-8 XML: {exc}") from exc


def _read_transform(text: str | None) -> np.ndarray:
    if text is None:
        return np.eye(4)
    try:
        values = np.array([float(x) for x in text.split()])
        if values.shape != (12,):
            raise ValidationError("3MF item transform must contain twelve numbers")
        row_matrix = np.eye(4)
        row_matrix[:, :3] = values.reshape(4, 3)
        return _transform(row_matrix.T)
    except ValueError as exc:
        raise ValidationError(f"invalid 3MF item transform: {exc}") from exc


def read_3mf(path: str | Path) -> dict:
    """Read this exporter's Core mesh subset without changing coordinates.

    Return dict with unit, objects (one per build item), metadata, package_parts.
    Objects contain vertices/faces/transform NumPy arrays and optional color.
    External relationships, duplicate IDs, missing parts, unsupported geometry,
    invalid materials and dangling build references are rejected.
    """
    with zipfile.ZipFile(path) as package:
        names = package.namelist()
        if len(set(names)) != len(names):
            raise ValidationError("duplicate part names in ZIP package")
        if package.testzip() is not None:
            raise ValidationError("3MF package CRC check failed")
        if "[Content_Types].xml" not in names or "_rels/.rels" not in names:
            raise ValidationError("missing OPC content-types or package relationships part")
        types = _parse_xml(package.read("[Content_Types].xml"), "content types")
        rels = _parse_xml(package.read("_rels/.rels"), "relationships")
        if types.tag != f"{{{TYPES}}}Types" or rels.tag != f"{{{RELS}}}Relationships":
            raise ValidationError("incorrect OPC root element/namespace")
        starts = [r for r in rels if r.get("Type") == START_REL]
        if len(starts) != 1:
            raise ValidationError("exactly one primary 3MF StartPart relationship is required")
        if starts[0].get("TargetMode", "Internal") != "Internal":
            raise ValidationError("external 3MF payloads are not supported")
        target = starts[0].get("Target", "").lstrip("/")
        if ".." in PurePosixPath(target).parts or target not in names:
            raise ValidationError("StartPart target is missing or invalid")
        defaults = {t.get("Extension"): t.get("ContentType") for t in types if t.tag == f"{{{TYPES}}}Default"}
        overrides = {t.get("PartName"): t.get("ContentType") for t in types if t.tag == f"{{{TYPES}}}Override"}
        content_type = overrides.get("/" + target, defaults.get(target.rsplit(".", 1)[-1]))
        if content_type != MODEL_TYPE:
            raise ValidationError("model part has missing or incorrect OPC content type")
        model = _parse_xml(package.read(target), "model")

    q = lambda name: f"{{{CORE}}}{name}"
    if model.tag != q("model"):
        raise ValidationError("unsupported model XML namespace/root")
    if model.get("requiredextensions", "").strip():
        raise ValidationError("required extensions are outside this validator's core-mesh scope")
    unit = model.get("unit", "millimeter")
    resources = model.find(q("resources"))
    build = model.find(q("build"))
    if resources is None or build is None:
        raise ValidationError("model requires resources and build sections")
    ids: set[int] = set()
    materials: dict[int, list[str]] = {}
    mesh_resources: dict[int, dict] = {}
    for element in resources:
        try:
            resource_id = int(element.get("id", "0"))
        except ValueError as exc:
            raise ValidationError("resource id must be an integer") from exc
        if not 0 < resource_id < 2**31 or resource_id in ids:
            raise ValidationError("resource IDs must be unique positive 31-bit integers")
        ids.add(resource_id)
        if element.tag == q("basematerials"):
            colors = []
            for base in element:
                if base.tag != q("base") or base.get("name") is None:
                    raise ValidationError("invalid base material resource")
                colors.append(_color(base.get("displaycolor", "")))
            if not colors:
                raise ValidationError("empty base material group")
            materials[resource_id] = colors
            continue
        if element.tag != q("object") or element.get("type", "model") != "model":
            raise ValidationError("only Core mesh objects of type model are supported")
        mesh = element.find(q("mesh"))
        if mesh is None or element.find(q("components")) is not None:
            raise ValidationError("component assemblies are outside this validator's mesh-only scope")
        vx, tx = mesh.find(q("vertices")), mesh.find(q("triangles"))
        if vx is None or tx is None:
            raise ValidationError("mesh requires vertices and triangles")
        try:
            vertices = np.array([[float(n.attrib[a]) for a in ("x", "y", "z")] for n in vx])
            faces = np.array([[int(n.attrib[a]) for a in ("v1", "v2", "v3")] for n in tx], dtype=np.int64)
        except (KeyError, ValueError) as exc:
            raise ValidationError(f"invalid vertex/triangle attribute: {exc}") from exc
        vertices, faces = _arrays(vertices, faces)
        if any(n.tag != q("vertex") for n in vx) or any(n.tag != q("triangle") for n in tx):
            raise ValidationError("unsupported vertex/triangle element")
        if any(any(a in n.attrib for a in ("pid", "p1", "p2", "p3")) for n in tx):
            raise ValidationError("per-triangle material assignments are outside this exporter's scope")
        color = None
        if "pid" in element.attrib or "pindex" in element.attrib:
            try:
                pid = int(element.attrib["pid"])
                pindex = int(element.attrib["pindex"])
                if pindex < 0:
                    raise IndexError("negative material index")
                color = materials[pid][pindex]
            except (KeyError, IndexError, ValueError) as exc:
                raise ValidationError("missing, invalid, or forward material reference") from exc
        mesh_resources[resource_id] = {"name": element.get("name", f"object_{resource_id}"),
                                       "object_id": resource_id, "vertices": vertices,
                                       "faces": faces, "color": color}
    objects = []
    for item in build:
        if item.tag != q("item"):
            raise ValidationError("unsupported build element")
        try:
            object_id = int(item.attrib["objectid"])
            obj = mesh_resources[object_id].copy()
        except (KeyError, ValueError) as exc:
            raise ValidationError("missing or dangling build object reference") from exc
        obj["transform"] = _read_transform(item.get("transform"))
        objects.append(obj)
    if not objects:
        raise ValidationError("empty build section")
    return {
        "unit": unit, "unit_explicit": "unit" in model.attrib,
        "objects": objects, "resource_objects": len(mesh_resources),
        "metadata": {n.get("name"): n.text for n in model.findall(q("metadata"))},
        "package_parts": names, "model_part": target,
    }


def validate_3mf(path: str | Path, *, expected_unit: str = "millimeter") -> dict:
    """Re-read OPC/XML and independently recalculate each build item's topology."""
    path = Path(path)
    result: dict[str, Any] = {
        "path": str(path.resolve()), "valid": False, "errors": [], "warnings": [],
        "validation_scope": ["OPC package/CRC", "core XML resource/build references",
                             "explicit millimeter units", "indexed mesh topology",
                             "edge/vertex manifoldness", "triangle winding", "degeneracy",
                             "signed volume", "build transforms", "bounding boxes"],
        "not_validated": ["XML XSD schema (unless separately checked)", "self-intersections",
                          "shell containment", "minimum wall thickness", "physical fit",
                          "printer profile", "toolpaths", "actual slicer import"],
    }
    try:
        content = read_3mf(path)
        result.update(unit=content["unit"], build_items=len(content["objects"]),
                      resource_objects=content["resource_objects"], package_parts=content["package_parts"])
        if not content["unit_explicit"]:
            result["errors"].append("The exporter contract requires explicit model units")
        if content["unit"] != expected_unit:
            result["errors"].append(f"Expected {expected_unit} units, found {content['unit']}")
        reports = []
        bounds = []
        for obj in content["objects"]:
            stats = mesh_stats(obj["vertices"], obj["faces"])
            world = transform_vertices(obj["vertices"], obj["transform"])
            bbox = np.array([world.min(axis=0), world.max(axis=0)])
            stats.update(name=obj["name"], object_id=obj["object_id"],
                         transform=obj["transform"].tolist(), build_bounds_mm=bbox.tolist(),
                         build_size_mm=(bbox[1] - bbox[0]).tolist(),
                         build_volume_mm3=stats["signed_volume_mm3"] * abs(float(np.linalg.det(obj["transform"][:3, :3]))))
            reports.append(stats)
            bounds.append(bbox)
            result["errors"].extend(f"{obj['name']}: {s}" for s in stats["errors"])
            result["warnings"].extend(f"{obj['name']}: {s}" for s in stats["warnings"])
        all_bounds = np.array([np.min(np.array(bounds)[:, 0], axis=0), np.max(np.array(bounds)[:, 1], axis=0)])
        result.update(objects=reports, build_bounds_mm=all_bounds.tolist(),
                      build_size_mm=(all_bounds[1] - all_bounds[0]).tolist(),
                      sha256=hashlib.sha256(path.read_bytes()).hexdigest(), bytes=path.stat().st_size)
        if np.any(all_bounds[0] < -1e-7):
            result["warnings"].append("Build extends outside the positive octant; arrange/reposition before slicing")
        result["valid"] = not result["errors"]
    except (ValidationError, zipfile.BadZipFile, OSError, ValueError) as exc:
        result["errors"].append(str(exc))
    return result


def validate_with_lib3mf(path: str | Path) -> dict:
    """Optional independent import check with 3MF Consortium's lib3mf.

    Install the optional dependency with `python -m pip install lib3mf` or place
    it in `_validation_vendor` beside this module. This does not invoke a slicer.
    lib3mf uses float32 mesh coordinates; geometry comparisons allow 0.0001 mm.
    """
    import importlib
    import sys

    try:
        lib3mf = importlib.import_module("lib3mf")
    except ImportError:
        vendor = Path(__file__).resolve().parent / "_validation_vendor"
        if vendor.is_dir():
            sys.path.insert(0, str(vendor))
        try:
            lib3mf = importlib.import_module("lib3mf")
        except ImportError as exc:
            raise ValidationError("Optional lib3mf dependency is not installed") from exc
    content = read_3mf(path)
    wrapper = lib3mf.get_wrapper()
    model = wrapper.CreateModel()
    reader = model.QueryReader("3mf")
    reader.SetStrictModeActive(True)
    reader.ReadFromFile(str(Path(path).resolve()))
    errors = []
    warnings = [reader.GetWarning(i) for i in range(reader.GetWarningCount())]
    if model.GetUnit() != lib3mf.ModelUnit.MilliMeter:
        errors.append("lib3mf did not read millimeter units")
    by_name = {o["name"]: o for o in content["objects"]}
    mesh_reports = []
    iterator = model.GetMeshObjects()
    while iterator.MoveNext():
        mesh = iterator.GetCurrentMeshObject()
        name = mesh.GetName()
        actual_v = np.array([list(v.Coordinates) for v in mesh.GetVertices()])
        actual_f = np.array([list(f.Indices) for f in mesh.GetTriangleIndices()])
        expected = by_name.get(name)
        geometry_matches = expected is not None and actual_v.shape == expected["vertices"].shape and actual_f.shape == expected["faces"].shape
        if geometry_matches:
            geometry_matches = bool(np.allclose(actual_v, expected["vertices"], atol=1e-4, rtol=1e-7) and np.array_equal(actual_f, expected["faces"]))
        mesh_report = {"name": name, "vertices": mesh.GetVertexCount(), "triangles": mesh.GetTriangleCount(),
                       "is_valid": mesh.IsValid(), "is_manifold_and_oriented": mesh.IsManifoldAndOriented(),
                       "geometry_matches": geometry_matches}
        if not all(mesh_report[k] for k in ("is_valid", "is_manifold_and_oriented", "geometry_matches")):
            errors.append(f"lib3mf rejected or changed mesh {name}")
        mesh_reports.append(mesh_report)
    build_reports = []
    iterator = model.GetBuildItems()
    while iterator.MoveNext():
        item = iterator.GetCurrent()
        values = np.array([list(row) for row in item.GetObjectTransform().Fields])
        row_transform = np.eye(4)
        row_transform[:, :3] = values
        name = item.GetPartNumber()
        expected = by_name.get(name)
        matches = expected is not None and bool(np.allclose(row_transform.T, expected["transform"], atol=1e-4, rtol=1e-7))
        build_reports.append({"partnumber": name, "object_id": item.GetObjectResourceID(),
                              "transform_matches": matches})
        if not matches:
            errors.append(f"lib3mf build placement mismatch for {name}")
    if len(build_reports) != len(content["objects"]):
        errors.append("lib3mf build item count mismatch")
    if len(mesh_reports) != content["resource_objects"]:
        errors.append("lib3mf mesh resource count mismatch")
    box = model.GetOutbox()
    return {
        "validator": "3MF Consortium lib3mf", "version": list(wrapper.GetLibraryVersion()),
        "strict_reader": reader.GetStrictModeActive(), "valid": not errors,
        "unit": "millimeter" if model.GetUnit() == lib3mf.ModelUnit.MilliMeter else int(model.GetUnit()),
        "reader_warnings": warnings, "errors": errors,
        "objects": mesh_reports, "build_items": build_reports,
        "bounds_mm": [list(box.MinCoordinate), list(box.MaxCoordinate)],
        "actual_slicer_import": "not_performed",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate a printer-neutral Core mesh 3MF")
    parser.add_argument("file", type=Path)
    parser.add_argument("--report", type=Path, help="Optional JSON report destination")
    args = parser.parse_args()
    report = validate_3mf(args.file)
    rendered = json.dumps(report, indent=2)
    if args.report:
        args.report.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    raise SystemExit(0 if report["valid"] else 1)
