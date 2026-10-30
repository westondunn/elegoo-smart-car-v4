"""Independently validate named STEP assemblies and portable STL/3MF print assets.

Inputs are read-only. Required inventories and CAD expectations come from JSON,
not hardcoded file names. Output is a separate JSON report with asset hashes.
Requires NumPy, VTK, CadQuery/OCP and lib3mf (strict reader, no warnings).
The sibling rover_3mf helper is reused unchanged from the earlier rover package.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import traceback
import xml.etree.ElementTree as ET
import zipfile

import numpy as np

HERE = Path(__file__).resolve().parent
# Local installation normally suffices. This fallback is workspace validation only.
for candidate in (HERE / "_validation_vendor", HERE.parents[1] / "export-tools/_validation_vendor"):
    if candidate.is_dir():
        sys.path.insert(0, str(candidate))
        break

from rover_3mf import (CORE, MODEL_PART, read_3mf, transform_vertices,
                       validate_3mf, validate_with_lib3mf)

PLACEMENT_TOL_MM = 1e-4
STL_BOUNDS_TOL_MM = 0.08
STL_VOLUME_REL_TOL = 0.005
STEP_BOUNDS_TOL_MM = 0.001
STEP_VOLUME_REL_TOL = 1e-6


def file_identity(path: Path) -> dict:
    return {"file": path.name, "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def check_pure_model_package(path: Path) -> dict:
    """Enforce this export contract: exactly core XML parts, no settings/toolpath."""
    errors = []
    allowed = {"[Content_Types].xml", "_rels/.rels", MODEL_PART}
    with zipfile.ZipFile(path) as package:
        members = package.namelist()
        if set(members) != allowed or len(members) != len(allowed):
            errors.append("Package is not limited to the three expected core model XML parts")
        model = ET.fromstring(package.read(MODEL_PART))
        if any(not element.tag.startswith("{" + CORE + "}") for element in model.iter()):
            errors.append("Non-Core extension element present in model XML")
        allowed_tags = {"model", "metadata", "resources", "basematerials", "base",
                        "object", "mesh", "vertices", "vertex", "triangles", "triangle", "build", "item"}
        if any(element.tag.split("}")[-1] not in allowed_tags for element in model.iter()):
            errors.append("Unexpected model element could carry non-geometry data")
        expected_metadata = {"Title", "Description", "Application"}
        metadata_names = [element.get("name") for element in model.findall(f"{{{CORE}}}metadata")]
        if set(metadata_names) != expected_metadata:
            errors.append("Unexpected or missing model-level metadata field")
        rels = ET.fromstring(package.read("_rels/.rels"))
        if len(rels) != 1 or any(r.get("TargetMode", "Internal") != "Internal" for r in rels):
            errors.append("Unexpected relationship or external reference in package")
    return {"valid": not errors, "parts": members, "errors": errors,
            "printer_profile_present": False if not errors else "not_certified",
            "gcode_present": False if not errors else "not_certified",
            "filament_mapping_present": False if not errors else "not_certified"}


def vtk_feature_edge_count(polydata, boundary: bool = False, nonmanifold: bool = False) -> int:
    import vtk
    edges = vtk.vtkFeatureEdges()
    edges.SetInputData(polydata)
    edges.FeatureEdgesOff()
    edges.ManifoldEdgesOff()
    edges.SetBoundaryEdges(boundary)
    edges.SetNonManifoldEdges(nonmanifold)
    edges.Update()
    return edges.GetOutput().GetNumberOfCells()


def vtk_vertex_link_failures(polydata) -> list[int]:
    """Use VTK point/cell adjacency to test every vertex's single-cycle link."""
    import vtk
    polydata.BuildLinks()
    cells = vtk.vtkIdList()
    failures = []
    for point_id in range(polydata.GetNumberOfPoints()):
        polydata.GetPointCells(point_id, cells)
        adjacent = {}
        for i in range(cells.GetNumberOfIds()):
            cell = polydata.GetCell(cells.GetId(i))
            others = [cell.GetPointId(k) for k in range(cell.GetNumberOfPoints()) if cell.GetPointId(k) != point_id]
            if len(others) != 2:
                failures.append(point_id)
                break
            a, b = others
            adjacent.setdefault(a, []).append(b)
            adjacent.setdefault(b, []).append(a)
        else:
            if not adjacent or any(len(neighbors) != 2 for neighbors in adjacent.values()):
                failures.append(point_id)
                continue
            unseen = set(adjacent)
            stack = [next(iter(unseen))]
            while stack:
                current = stack.pop()
                if current in unseen:
                    unseen.remove(current)
                    stack.extend(adjacent[current])
            if unseen:
                failures.append(point_id)
    return failures


def vtk_orientation_changes(polydata) -> int:
    """Count cell-normal reversals VTK needs to make a closed mesh consistent."""
    import vtk
    from vtk.util.numpy_support import vtk_to_numpy
    normals = []
    for repair in (False, True):
        filt = vtk.vtkPolyDataNormals()
        filt.SetInputData(polydata)
        filt.SplittingOff()
        filt.ComputePointNormalsOff()
        filt.ComputeCellNormalsOn()
        filt.SetConsistency(repair)
        filt.SetAutoOrientNormals(repair)
        filt.Update()
        normals.append(vtk_to_numpy(filt.GetOutput().GetCellData().GetNormals()).copy())
    return int(np.count_nonzero(np.einsum("ij,ij->i", normals[0], normals[1]) < -0.5))


def validate_stl(path: Path, expected: dict | None, bed_mm: list[float]) -> dict:
    import vtk
    result = file_identity(path)
    errors = []
    reader = vtk.vtkSTLReader()
    reader.SetFileName(str(path))
    reader.MergingOn()
    reader.Update()
    if reader.GetErrorCode():
        raise ValueError(f"VTK STL read error {reader.GetErrorCode()}")
    data = reader.GetOutput()
    raw = path.read_bytes()
    declared_triangles = int.from_bytes(raw[80:84], "little") if len(raw) >= 84 else None
    if declared_triangles is not None and len(raw) == 84 + 50 * declared_triangles:
        if declared_triangles != data.GetNumberOfCells():
            errors.append("VTK changed the binary STL triangle count on import")
        result["binary_stl_declared_triangles"] = declared_triangles
    if not data.GetNumberOfCells() or not data.GetNumberOfPoints():
        raise ValueError("VTK read an empty STL")
    if data.GetNumberOfPolys() != data.GetNumberOfCells():
        errors.append("STL contains non-polygonal cells")
    bounds = np.array(data.GetBounds()).reshape(3, 2)
    low, high = bounds[:, 0], bounds[:, 1]
    size = high - low
    boundary = vtk_feature_edge_count(data, boundary=True)
    nonmanifold = vtk_feature_edge_count(data, nonmanifold=True)
    vertex_failures = vtk_vertex_link_failures(data)
    changed_normals = vtk_orientation_changes(data)
    connectivity = vtk.vtkPolyDataConnectivityFilter()
    connectivity.SetInputData(data)
    connectivity.SetExtractionModeToAllRegions()
    connectivity.Update()
    regions = connectivity.GetNumberOfExtractedRegions()
    mass = vtk.vtkMassProperties()
    mass.SetInputData(data)
    mass.Update()
    volume = float(mass.GetVolume())
    if boundary or nonmanifold or vertex_failures:
        errors.append("VTK imported mesh is not a closed edge/vertex manifold")
    if changed_normals:
        errors.append(f"VTK needs to reverse {changed_normals} triangle normals for outward consistency")
    expected_surfaces = int((expected or {}).get("connected_surfaces", 1))
    if regions != expected_surfaces:
        errors.append(f"Expected {expected_surfaces} connected printable surfaces; found {regions}")
    if volume <= 0:
        errors.append("Imported mesh does not have positive volume")
    if np.any(low < -PLACEMENT_TOL_MM) or abs(low[2]) > PLACEMENT_TOL_MM:
        errors.append("Individual print mesh is below the origin or does not contact Z=0")
    if high[0] > bed_mm[0] + PLACEMENT_TOL_MM or high[1] > bed_mm[1] + PLACEMENT_TOL_MM:
        errors.append("Individual print mesh exceeds the portable bed dimensions")
    if expected is None:
        errors.append("Unexpected STL absent from printable-parts manifest")
    else:
        if not np.allclose(size, expected["bbox_mm"], atol=STL_BOUNDS_TOL_MM, rtol=0):
            errors.append("VTK STL dimensions differ from CAD manifest beyond mesh tolerance")
        expected_volume = float(expected["solid_volume_mm3"])
        volume_relative_error = abs(volume - expected_volume) / expected_volume
        if volume_relative_error > STL_VOLUME_REL_TOL:
            errors.append("VTK STL volume differs from CAD manifest by more than 0.5%")
        result.update(expected_bounds_size_mm=expected["bbox_mm"], expected_volume_mm3=expected_volume,
                      volume_relative_error=volume_relative_error)
    result.update(valid=not errors, errors=errors, vtk_version=vtk.vtkVersion.GetVTKVersion(),
                  vertices=data.GetNumberOfPoints(), triangles=data.GetNumberOfCells(),
                  minimum_mm=low.tolist(), maximum_mm=high.tolist(), size_mm=size.tolist(),
                  boundary_edges=boundary, nonmanifold_edges=nonmanifold,
                  nonmanifold_vertices=len(vertex_failures), connected_surfaces=regions,
                  triangle_normals_requiring_reversal=changed_normals,
                  volume_mm3=volume, surface_area_mm2=float(mass.GetSurfaceArea()))
    return result


def validate_step_structure(text: str, expected: dict) -> dict:
    """Resolve the actual STEP PRODUCT/definition/assembly occurrence graph.

    This intentionally recognizes the simple entity forms emitted by the local
    STEP exporter, not every possible STEP application protocol representation.
    Names must exist as products AND be connected beneath their expected parent.
    A string appearing only in a header/comment cannot pass this check.
    """
    quoted = r"'((?:[^']|'')*)'"
    product_pattern = rf"#(\d+)\s*=\s*PRODUCT\s*\(\s*{quoted}\s*,\s*{quoted}\s*,"
    products = {entity: product_name.replace("''", "'")
                for entity, _product_id, product_name in re.findall(product_pattern, text)}
    formation_pattern = rf"#(\d+)\s*=\s*PRODUCT_DEFINITION_FORMATION\s*\(\s*{quoted}\s*,\s*{quoted}\s*,\s*#(\d+)"
    formations = {entity: product for entity, _id, _desc, product in re.findall(formation_pattern, text)}
    definition_pattern = rf"#(\d+)\s*=\s*PRODUCT_DEFINITION\s*\(\s*{quoted}\s*,\s*{quoted}\s*,\s*#(\d+)"
    definitions = {entity: formation for entity, _id, _desc, formation in re.findall(definition_pattern, text)}
    usage_pattern = (rf"#(\d+)\s*=\s*NEXT_ASSEMBLY_USAGE_OCCURRENCE\s*\(\s*{quoted}\s*,\s*{quoted}"
                     rf"\s*,\s*{quoted}\s*,\s*#(\d+)\s*,\s*#(\d+)\s*,")
    usages = re.findall(usage_pattern, text)
    errors = []
    edges = []
    named_occurrences = []
    for entity, occurrence_id, instance_name, _desc, parent_def, child_def in usages:
        try:
            parent_name = products[formations[definitions[parent_def]]]
            child_name = products[formations[definitions[child_def]]]
        except KeyError:
            errors.append(f"STEP occurrence #{entity} has an unresolved product-definition chain")
            continue
        edges.append((parent_name, child_name))
        if instance_name:
            named_occurrences.append(instance_name.replace("''", "'"))
    expected_products = Counter([expected["root"], *expected["groups"], *expected["components"]])
    actual_products = Counter(products.values())
    expected_edges = Counter(tuple(edge) for edge in expected["edges"])
    actual_edges = Counter(edges)
    missing_products = list((expected_products - actual_products).elements())
    extra_products = list((actual_products - expected_products).elements())
    missing_edges = [list(edge) for edge in (expected_edges - actual_edges).elements()]
    extra_edges = [list(edge) for edge in (actual_edges - expected_edges).elements()]
    if missing_products or extra_products:
        errors.append("STEP named product inventory differs from the expected assembly components/groups")
    if missing_edges or extra_edges:
        errors.append("STEP assembly occurrence hierarchy differs from the expected named parent/child structure")
    named_occurrence_counts = Counter(named_occurrences)
    missing_component_instances = [name for name in expected["components"] if named_occurrence_counts[name] != 1]
    if missing_component_instances:
        errors.append("One or more leaf components lack their expected unique named STEP assembly occurrence")
    return {
        "valid": not errors, "errors": errors, "root": expected["root"],
        "expected_component_count": len(expected["components"]),
        "matched_component_products": sum(actual_products[name] == 1 for name in expected["components"]),
        "matched_named_component_occurrences": sum(named_occurrence_counts[name] == 1 for name in expected["components"]),
        "product_count": len(products), "assembly_occurrence_count": len(usages),
        "group_names": expected["groups"], "missing_product_names": missing_products,
        "unexpected_product_names": extra_products, "missing_hierarchy_edges": missing_edges,
        "unexpected_hierarchy_edges": extra_edges, "missing_named_component_occurrences": missing_component_instances,
    }


def validate_step(path: Path, expected: dict) -> dict:
    import cadquery as cq
    from OCP.BRepCheck import BRepCheck_Analyzer
    result = file_identity(path)
    errors = []
    imported = cq.importers.importStep(str(path))
    compound = cq.Compound.makeCompound(imported.vals())
    solids = compound.Solids()
    valid_solids = [BRepCheck_Analyzer(s.wrapped).IsValid() for s in solids]
    volumes = [s.Volume() for s in solids]
    total_volume = sum(volumes)
    bb = compound.BoundingBox()
    actual_bounds = [bb.xmin, bb.ymin, bb.zmin, bb.xmax, bb.ymax, bb.zmax]
    if len(solids) != expected["solids"]:
        errors.append(f"STEP reimport has {len(solids)} solids; expected {expected['solids']}")
    if not all(valid_solids) or not compound.isValid():
        errors.append("One or more STEP solids/assembly shapes failed BRep validity")
    if any(volume <= 0 for volume in volumes):
        errors.append("STEP contains a nonpositive-volume solid")
    relative_volume_error = abs(total_volume - expected["volume_mm3"]) / expected["volume_mm3"]
    if relative_volume_error > STEP_VOLUME_REL_TOL:
        errors.append("STEP reimport volume differs from source CAD manifest beyond 1e-6 relative tolerance")
    if not np.allclose(actual_bounds, expected["bounds_mm"], atol=STEP_BOUNDS_TOL_MM, rtol=0):
        errors.append("STEP reimport bounds differ from source CAD manifest by more than 0.001 mm")
    text = path.read_text(encoding="ascii", errors="replace")
    explicit_mm = bool(re.search(r"SI_UNIT\s*\(\s*\.MILLI\.\s*,\s*\.METRE\.\s*\)", text))
    length_units = re.findall(r"#\d+\s*=\s*\(\s*LENGTH_UNIT\(\)\s*NAMED_UNIT\(\*\)\s*SI_UNIT\(\s*([^,]+)\s*,\s*\.METRE\.\s*\)\s*\)", text)
    if not explicit_mm or not length_units or any(prefix.strip() != ".MILLI." for prefix in length_units):
        errors.append("STEP length-unit entities are not uniformly explicit millimeters")
    result["length_unit_entity_count"] = len(length_units)
    if "named_hierarchy" in expected:
        result["named_assembly_structure"] = validate_step_structure(text, expected["named_hierarchy"])
        errors.extend(result["named_assembly_structure"]["errors"])
    result.update(valid=not errors, errors=errors, expected=expected, solid_count=len(solids),
                  valid_solid_count=sum(valid_solids), total_volume_mm3=total_volume,
                  volume_relative_error=relative_volume_error, bounds_mm=actual_bounds,
                  explicit_millimeter_unit=explicit_mm, cadquery_version=cq.__version__)
    return result


def named_build_items(parts: dict[str, int]) -> dict[str, str]:
    """Map unique exported object names to unique printable-design names."""
    result = {}
    for name, quantity in parts.items():
        for i in range(quantity):
            instance = name if quantity == 1 else f"{name}_{i + 1}"
            if instance in result:
                raise ValueError(f"Ambiguous pack object name: {instance}")
            result[instance] = name
    return result


def validate_pack(path: Path, expected: dict, part_by_name: dict, default_bed: list[float]) -> dict:
    result = file_identity(path)
    errors = []
    result["core_validation"] = validate_3mf(path)
    errors.extend(result["core_validation"]["errors"])
    result["independent_lib3mf"] = validate_with_lib3mf(path)
    errors.extend(result["independent_lib3mf"]["errors"])
    if result["independent_lib3mf"]["reader_warnings"]:
        errors.append("Independent strict lib3mf import emitted reader warnings")
    result["pure_model_package"] = check_pure_model_package(path)
    errors.extend(result["pure_model_package"]["errors"])

    content = read_3mf(path)
    build_names = named_build_items(expected["parts"])
    actual_names = [obj["name"] for obj in content["objects"]]
    if Counter(actual_names) != Counter(list(build_names)):
        errors.append("Named build-item inventory differs from the specified pack quantities")
    stats = {obj["name"]: obj for obj in result["core_validation"].get("objects", [])}
    bed = np.asarray(expected.get("bed_mm", default_bed), dtype=float)
    edge_margin = float(expected.get("edge_margin_mm", 0))
    minimum_spacing = float(expected.get("minimum_spacing_mm", 0))
    bounds = []
    for obj in content["objects"]:
        world = transform_vertices(obj["vertices"], obj["transform"])
        low, high = world.min(axis=0), world.max(axis=0)
        on_bed = bool(abs(float(low[2])) <= PLACEMENT_TOL_MM)
        within = bool(np.all(low >= -PLACEMENT_TOL_MM)
                      and np.all(high[:2] <= bed + PLACEMENT_TOL_MM))
        margin_ok = bool(np.all(low[:2] >= edge_margin - PLACEMENT_TOL_MM)
                         and np.all(high[:2] <= bed - edge_margin + PLACEMENT_TOL_MM))
        rotation = obj["transform"][:3, :3]
        rigid_transform = bool(np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-8, rtol=0))
        item = {"name": obj["name"], "minimum_mm": low.tolist(), "maximum_mm": high.tolist(),
                "inside_bed_xy_and_nonnegative_z": within, "touches_z0": on_bed,
                "edge_margin_satisfied": margin_ok, "unscaled_rigid_transform": rigid_transform}
        if not within:
            errors.append(f"{obj['name']}: transformed geometry exceeds its bed or lies below Z=0")
        if not on_bed:
            errors.append(f"{obj['name']}: object does not touch Z=0")
        if not margin_ok:
            errors.append(f"{obj['name']}: print layout violates the specified {edge_margin:g} mm edge margin")
        if not rigid_transform:
            errors.append(f"{obj['name']}: build transform introduces scaling or shear")
        design_name = build_names.get(obj["name"])
        part = part_by_name.get(design_name)
        if part is None:
            errors.append(f"{obj['name']}: cannot resolve the expected printable CAD design")
        elif obj["name"] in stats:
            mesh = stats[obj["name"]]
            mesh_volume = float(mesh["build_volume_mm3"])
            cad_volume = float(part["solid_volume_mm3"])
            relative_error = abs(mesh_volume - cad_volume) / cad_volume
            local_size = obj["vertices"].max(axis=0) - obj["vertices"].min(axis=0)
            dims_match = bool(np.allclose(local_size, part["bbox_mm"], atol=STL_BOUNDS_TOL_MM, rtol=0))
            item.update(design_name=design_name, modeled_volume_mm3=cad_volume,
                        mesh_volume_mm3=mesh_volume, volume_relative_error=relative_error,
                        local_size_mm=local_size.tolist(), modeled_size_mm=part["bbox_mm"],
                        local_dimensions_match_cad=dims_match)
            if relative_error > STL_VOLUME_REL_TOL:
                errors.append(f"{obj['name']}: mesh volume differs from modeled CAD by more than 0.5%")
            if not dims_match:
                errors.append(f"{obj['name']}: local mesh dimensions differ from modeled CAD beyond 0.08 mm")
        bounds.append(item)

    # Row/column packed print objects are conservatively separated using XY AABBs.
    # AABB overlap is rejected even if interlocking geometry would fit physically.
    pair_clearances = []
    for i, a in enumerate(bounds):
        for b in bounds[i + 1:]:
            alo, ahi = np.asarray(a["minimum_mm"]), np.asarray(a["maximum_mm"])
            blo, bhi = np.asarray(b["minimum_mm"]), np.asarray(b["maximum_mm"])
            signed_gaps = np.maximum(blo[:2] - ahi[:2], alo[:2] - bhi[:2])
            separate = bool(np.max(signed_gaps) >= -PLACEMENT_TOL_MM)
            distance = float(np.linalg.norm(np.maximum(signed_gaps, 0)))
            gap_ok = separate and distance >= minimum_spacing - PLACEMENT_TOL_MM
            pair_clearances.append({"names": [a["name"], b["name"]],
                                    "aabb_xy_distance_mm": distance,
                                    "aabbs_do_not_overlap_xy": separate,
                                    "minimum_spacing_satisfied": bool(gap_ok)})
            if not gap_ok:
                errors.append(f"{a['name']} / {b['name']}: XY bounding boxes overlap or violate the {minimum_spacing:g} mm spacing")
    result.update(valid=not errors, errors=errors, expected_names=list(build_names),
                  actual_names=actual_names, expected_count=len(build_names), actual_count=len(actual_names),
                  bed_xy_mm=bed.tolist(), edge_margin_mm=edge_margin,
                  minimum_spacing_mm=minimum_spacing, transformed_object_bounds=bounds,
                  pair_clearances=pair_clearances)
    return result


def export_entries(value, label: str) -> dict[str, dict]:
    """Accept either a list with file fields or a mapping from filename to fields."""
    if isinstance(value, dict):
        value = [dict(entry, file=name) for name, entry in value.items()]
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list of exports or filename-keyed object")
    output = {}
    for entry in value:
        name = entry["file"]
        if not isinstance(name, str) or Path(name).name != name or name in output:
            raise ValueError(f"{label} has an invalid or duplicate filename: {name}")
        output[name] = entry
    return output


def step_expectations(entry: dict) -> dict:
    """Normalize an explicitly measured source-CAD export record."""
    result = {"solids": int(entry.get("solid_count", entry.get("solids", 0))),
              "volume_mm3": float(entry["volume_mm3"]),
              "bounds_mm": entry.get("bbox_mm", entry.get("bounds_mm"))}
    if result["solids"] < 1 or not np.isfinite(result["volume_mm3"]) or result["volume_mm3"] <= 0:
        raise ValueError(f"{entry['file']}: expected positive CAD solids and volume")
    bounds = np.asarray(result["bounds_mm"], dtype=float)
    if bounds.shape != (6,) or not np.isfinite(bounds).all() or np.any(bounds[3:] <= bounds[:3]):
        raise ValueError(f"{entry['file']}: bounds must be six finite values with positive extent")
    if "named_hierarchy" not in entry:
        raise ValueError(f"{entry['file']}: named_hierarchy is required to validate assembly names")
    result["named_hierarchy"] = entry["named_hierarchy"]
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deliverables", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, help="Defaults to body_manifest.json in deliverables")
    parser.add_argument("--expectations", type=Path, help="Optional separate print_packs/step_exports JSON")
    parser.add_argument("--report", type=Path, default=HERE.parent / "verification" / "body_export_validation.json")
    args = parser.parse_args(argv)
    started = time.monotonic()
    folder = args.deliverables.resolve()
    manifest_path = args.manifest or folder / "body_manifest.json"
    report = {"created_utc": datetime.now(timezone.utc).isoformat(), "deliverables": str(folder),
              "valid": False, "errors": [], "print_packs": [], "stl_parts": [], "step_assemblies": [],
              "validator": file_identity(Path(__file__).resolve()),
              "tolerances": {"placement_mm": PLACEMENT_TOL_MM,
                             "mesh_bounds_mm": STL_BOUNDS_TOL_MM,
                             "mesh_volume_relative": STL_VOLUME_REL_TOL,
                             "step_bounds_mm": STEP_BOUNDS_TOL_MM,
                             "step_volume_relative": STEP_VOLUME_REL_TOL},
              "limits": ["No actual Fusion 360 or Bambu Studio application import was performed.",
                         "No slicer toolpath was generated or checked; no print was sent.",
                         "Minimum wall thickness, self-intersections, and mechanical hardware fit are not certified.",
                         "STEP reimport uses the OpenCascade kernel through CadQuery.",
                         "Print-pack spacing is checked conservatively using XY bounding boxes.",
                         "STL has no units field; scale is checked against the millimeter CAD manifest."]}

    def save():
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    try:
        if not manifest_path.exists():
            report["errors"].append(f"Manifest is not ready: {manifest_path}")
            save()
            return 2
        manifest = json.loads(manifest_path.read_text())
        report["component_manifest"] = file_identity(manifest_path)
        expectations = manifest
        if args.expectations:
            expectations = json.loads(args.expectations.read_text())
            report["expectations_manifest"] = file_identity(args.expectations)
        if manifest.get("units") != "millimeter":
            raise ValueError("CAD component manifest units must be millimeter")
        packs = export_entries(expectations["print_packs"], "print_packs")
        steps = export_entries(expectations["step_exports"], "step_exports")
        normalized_steps = {name: step_expectations(entry) for name, entry in steps.items()}
        bed = manifest.get("bed_mm", [180.0, 180.0])
        if len(bed) != 2 or not np.isfinite(bed).all() or min(bed) <= 0:
            raise ValueError("bed_mm must have two finite positive dimensions")
        part_by_file, part_by_name = {}, {}
        for part in manifest["printable_parts"]:
            name, filename = part["name"], part["part_file"]
            quantity = part["quantity"]
            if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
                raise ValueError(f"{name}: quantity must be a positive integer")
            if name in part_by_name or filename in part_by_file or Path(filename).name != filename:
                raise ValueError(f"Duplicate or invalid printable name/file: {name} / {filename}")
            dims = np.asarray(part["bbox_mm"], dtype=float)
            volume = float(part["solid_volume_mm3"])
            if dims.shape != (3,) or not np.isfinite(dims).all() or np.any(dims <= 0):
                raise ValueError(f"{name}: bbox_mm must have three finite positive dimensions")
            if not np.isfinite(volume) or volume <= 0:
                raise ValueError(f"{name}: solid_volume_mm3 must be finite and positive")
            part_by_file[filename], part_by_name[name] = part, part
        expected_inventory = Counter()
        for pack in packs.values():
            if not isinstance(pack["parts"], dict) or not pack["parts"]:
                raise ValueError(f"{pack['file']}: pack parts must be a nonempty quantity mapping")
            for name, quantity in pack["parts"].items():
                if name not in part_by_name or not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
                    raise ValueError(f"{pack['file']}: unrecognized design or invalid quantity: {name}")
            pack_bed = np.asarray(pack.get("bed_mm", bed), dtype=float)
            if pack_bed.shape != (2,) or not np.isfinite(pack_bed).all() or np.any(pack_bed <= 0):
                raise ValueError(f"{pack['file']}: bed_mm must have two finite positive dimensions")
            for field in ("edge_margin_mm", "minimum_spacing_mm"):
                value = float(pack.get(field, 0))
                if not np.isfinite(value) or value < 0:
                    raise ValueError(f"{pack['file']}: {field} must be finite and nonnegative")
            named_build_items(pack["parts"])
            expected_inventory.update(pack["parts"])
        manifest_inventory = Counter({p["name"]: p["quantity"] for p in part_by_name.values()})
        if manifest_inventory != expected_inventory:
            raise ValueError("Combined print-pack inventory differs from the printable-design quantities")
    except Exception as exc:
        report["errors"].append(f"Invalid validation inputs: {exc}")
        report["exception"] = traceback.format_exc(limit=3)
        save()
        print(json.dumps({"valid": False, "errors": report["errors"]}, indent=2), file=sys.stderr)
        return 1

    expected_files = set(packs) | set(steps) | set(part_by_file)
    missing = sorted(name for name in expected_files if not (folder / name).is_file())
    if missing:
        report.update(missing_files=missing)
        report["errors"].append("Exports are not ready: required files are missing")
        save()
        print("Exports not ready; missing " + ", ".join(missing), file=sys.stderr)
        return 2
    actual_files = {p.name for p in folder.iterdir() if p.is_file() and p.suffix.lower() in (".stl", ".3mf", ".step", ".stp")}
    unexpected = sorted(actual_files - expected_files)
    if unexpected:
        report["errors"].append("Unexpected exports lack validation expectations: " + ", ".join(unexpected))

    def run(section, path, function, *function_args):
        print("Validate", path.name, flush=True)
        try:
            outcome = function(path, *function_args)
        except Exception as exc:
            outcome = {**file_identity(path), "valid": False, "errors": [str(exc)],
                       "exception": traceback.format_exc(limit=5)}
        report[section].append(outcome)
        if not outcome["valid"]:
            report["errors"].extend(f"{path.name}: {error}" for error in outcome["errors"])

    for name, expected in packs.items():
        run("print_packs", folder / name, validate_pack, expected, part_by_name, bed)
    for name, expected in part_by_file.items():
        run("stl_parts", folder / name, validate_stl, expected, expected.get("bed_mm", bed))
    for name, expected in normalized_steps.items():
        run("step_assemblies", folder / name, validate_step, expected)
    report["totals"] = {
        "expected_3mf_files": len(packs), "actual_3mf_files": len(report["print_packs"]),
        "expected_named_build_items": sum(expected_inventory.values()),
        "actual_named_build_items": sum(p.get("actual_count", 0) for p in report["print_packs"]),
        "expected_unique_stl_parts": len(part_by_name), "actual_stl_parts": len(report["stl_parts"]),
        "expected_step_assemblies": len(steps), "actual_step_assemblies": len(report["step_assemblies"]),
        "lib3mf_reader_warning_count": sum(len(p.get("independent_lib3mf", {}).get("reader_warnings", [])) for p in report["print_packs"]),
    }
    report["valid"] = not report["errors"]
    save()
    print(json.dumps({"valid": report["valid"], "totals": report["totals"],
                      "errors": report["errors"], "report": str(args.report.resolve())}, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


