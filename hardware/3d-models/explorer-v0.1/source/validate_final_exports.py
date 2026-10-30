"""Independent final checks for the ELEGOO explorer delivery folder.

Reads assets only. Writes one JSON report (default beside this script). No CAD
regeneration, mesh repair, material/profile injection, slicing, or device action.
Requires NumPy, VTK and CadQuery/OCP; optional lib3mf must be installed to pass.
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

from rover_3mf import (
    CORE, MODEL_PART, RELS, read_3mf, transform_vertices,
    validate_3mf, validate_with_lib3mf,
)


HERE = Path(__file__).resolve().parent
EXPECTED_PACKS = {
    "00_fit_check.3mf": {"00_mount_fit_gauge": 1, "02_deck_spacer_36mm": 4},
    "01_deck.3mf": {"01_slotted_deck": 1},
    "02_body_and_guard.3mf": {
        "05_front_guard": 1, "03_side_guard_left": 1, "04_side_guard_right": 1,
    },
    "03_mounts_and_spacers.3mf": {
        "06_front_guard_spacer_4mm": 2,
        "07_rear_sensor_carrier": 1, "08_cable_tie_saddle": 4,
        "12_downward_sensor_carrier": 2,
    },
    "04_optional_pi_tray.3mf": {
        "10_optional_pi4_tray": 1, "11_pi_tray_spacer_4mm": 4,
    },
    "05_optional_servo_adapter.3mf": {"09_optional_servo_adapter": 1},
}
EXPECTED_STEP_FILES = {
    "stock_reference_assembly.step": "stock",
    "explorer_assembly.step": "explorer",
    "printable_parts.step": "printable",
}
PLACEMENT_TOL_MM = 1e-4
STL_BOUNDS_TOL_MM = 0.08
STL_VOLUME_REL_TOL = 0.005
STEP_BOUNDS_TOL_MM = 0.001
STEP_VOLUME_REL_TOL = 1e-6


def expected_object_names(parts: dict[str, int]) -> list[str]:
    return [name if quantity == 1 else f"{name}_{n + 1}"
            for name, quantity in parts.items() for n in range(quantity)]


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


def validate_pack(path: Path, expected: dict[str, int] | None, bed_mm: float) -> dict:
    result = file_identity(path)
    result["errors"] = []
    result["core_validation"] = validate_3mf(path)
    if not result["core_validation"]["valid"]:
        result["errors"].extend(result["core_validation"]["errors"])
    result["independent_lib3mf"] = validate_with_lib3mf(path)
    if not result["independent_lib3mf"]["valid"]:
        result["errors"].extend(result["independent_lib3mf"]["errors"])
    if result["independent_lib3mf"]["reader_warnings"]:
        result["errors"].append("Independent strict import emitted reader warnings")
    result["pure_model_package"] = check_pure_model_package(path)
    result["errors"].extend(result["pure_model_package"]["errors"])

    content = read_3mf(path)
    names = [obj["name"] for obj in content["objects"]]
    expected_names = expected_object_names(expected) if expected else []
    result.update(expected_names=expected_names, actual_names=names,
                  expected_count=len(expected_names), actual_count=len(names))
    if expected is None:
        result["errors"].append("Unexpected 3MF file with no approved pack inventory")
    elif Counter(names) != Counter(expected_names):
        result["errors"].append("Named build-item inventory differs from expected part quantities")

    bounds = []
    for obj in content["objects"]:
        world = transform_vertices(obj["vertices"], obj["transform"])
        low, high = world.min(axis=0), world.max(axis=0)
        within = bool(np.all(low >= -PLACEMENT_TOL_MM)
                      and high[0] <= bed_mm + PLACEMENT_TOL_MM
                      and high[1] <= bed_mm + PLACEMENT_TOL_MM)
        on_bed = abs(float(low[2])) <= PLACEMENT_TOL_MM
        bounds.append({"name": obj["name"], "minimum_mm": low.tolist(), "maximum_mm": high.tolist(),
                       "inside_bed_xy_and_nonnegative_z": within, "touches_z0": on_bed})
        if not within:
            result["errors"].append(f"{obj['name']}: transformed geometry is outside the {bed_mm:g} mm bed or below Z=0")
        if not on_bed:
            result["errors"].append(f"{obj['name']}: object is floating above the bed")
    result["transformed_object_bounds"] = bounds
    result["valid"] = not result["errors"]
    return result


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


def validate_stl(path: Path, expected: dict | None, bed_mm: float) -> dict:
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
    if regions != 1:
        errors.append(f"Expected one connected printable surface; found {regions}")
    if volume <= 0:
        errors.append("Imported mesh does not have positive volume")
    if np.any(low < -PLACEMENT_TOL_MM) or abs(low[2]) > PLACEMENT_TOL_MM:
        errors.append("Individual print mesh is below the origin or does not contact Z=0")
    if high[0] > bed_mm + PLACEMENT_TOL_MM or high[1] > bed_mm + PLACEMENT_TOL_MM:
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


def step_expectations(variant: str, manifest: dict) -> dict:
    if variant == "printable":
        root_name = "ELEGOO_printable_parts_only_mm"
        names = [p["name"] for p in manifest["printable_parts"]]
        low = np.zeros(3)
        high = np.zeros(3)
        for i, part in enumerate(manifest["printable_parts"]):
            pos = np.array([(i % 4) * 190, (i // 4) * 190, 0])
            high = np.maximum(high, pos + part["bbox_mm"])
        return {"solids": len(manifest["printable_parts"]),
                "volume_mm3": sum(p["solid_volume_mm3"] for p in manifest["printable_parts"]),
                "bounds_mm": [*low, *high],
                "named_hierarchy": {"root": root_name, "groups": [], "components": names,
                                    "edges": [[root_name, name] for name in names]}}
    parts = [p for p in manifest["components"] if p["variant"] in ("both", variant)]
    root_name = "ELEGOO_V4_" + variant + "_mm"
    groups = sorted({p["group"] for p in parts})
    bounds = np.array([p["bbox_mm"] for p in parts])
    return {"solids": sum(p["solid_count"] for p in parts),
            "volume_mm3": sum(p["volume_mm3"] for p in parts),
            "bounds_mm": [*bounds[:, :3].min(axis=0), *bounds[:, 3:].max(axis=0)],
            "named_hierarchy": {"root": root_name, "groups": groups,
                                "components": [p["name"] for p in parts],
                                "edges": [[root_name, group] for group in groups]
                                         + [[p["group"], p["name"]] for p in parts]}}


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
    if not explicit_mm:
        errors.append("No explicit millimeter SI length unit found in STEP")
    if "named_hierarchy" in expected:
        result["named_assembly_structure"] = validate_step_structure(text, expected["named_hierarchy"])
        errors.extend(result["named_assembly_structure"]["errors"])
    result.update(valid=not errors, errors=errors, expected=expected, solid_count=len(solids),
                  valid_solid_count=sum(valid_solids), total_volume_mm3=total_volume,
                  volume_relative_error=relative_volume_error, bounds_mm=actual_bounds,
                  explicit_millimeter_unit=explicit_mm, cadquery_version=cq.__version__)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deliverables", type=Path, default=HERE.parent / "deliverables")
    parser.add_argument("--report", type=Path, default=HERE.parent / "verification" / "final_validation.json")
    parser.add_argument("--bed-mm", type=float, default=180.0)
    args = parser.parse_args(argv)
    started = time.monotonic()
    folder = args.deliverables.resolve()
    manifest_path = folder / "component_manifest.json"
    report = {"created_utc": datetime.now(timezone.utc).isoformat(), "deliverables": str(folder),
              "valid": False, "errors": [], "print_packs": [], "stl_parts": [], "step_assemblies": [],
              "tolerances": {"placement_mm": PLACEMENT_TOL_MM, "bed_xy_mm": [args.bed_mm, args.bed_mm],
                             "stl_bounds_mm": STL_BOUNDS_TOL_MM, "stl_volume_relative": STL_VOLUME_REL_TOL,
                             "step_bounds_mm": STEP_BOUNDS_TOL_MM, "step_volume_relative": STEP_VOLUME_REL_TOL},
              "limits": ["No actual Fusion 360 or Bambu Studio application import was performed.",
                         "No slicer toolpath was generated or checked; no print was sent.",
                         "Minimum wall thickness, self-intersections, and mechanical hardware fit are not certified.",
                         "STEP reimport uses the OpenCascade kernel through CadQuery."]}

    def save():
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if not manifest_path.exists():
        report["errors"].append("Missing component_manifest.json; exports are not ready")
        save()
        print(report["errors"][0], file=sys.stderr)
        return 2
    manifest = json.loads(manifest_path.read_text())
    report["component_manifest"] = file_identity(manifest_path)
    part_by_file = {part["part_file"]: part for part in manifest["printable_parts"]}
    expected_files = set(EXPECTED_PACKS) | set(EXPECTED_STEP_FILES) | set(part_by_file)
    missing = sorted(name for name in expected_files if not (folder / name).is_file())
    if missing:
        report["errors"].append("Exports are not ready: required files are missing")
        report["missing_files"] = missing
        save()
        print("Exports not ready; missing " + ", ".join(missing), file=sys.stderr)
        return 2

    expected_inventory = Counter()
    for pack in EXPECTED_PACKS.values():
        expected_inventory.update(pack)
    manifest_inventory = Counter({part["name"]: part["quantity"] for part in manifest["printable_parts"]})
    if manifest_inventory != expected_inventory:
        report["errors"].append(f"Manifest print inventory differs from the independently specified {len(expected_inventory)} designs / {sum(expected_inventory.values())} copies")
    if manifest.get("units") != "millimeter":
        report["errors"].append("CAD component manifest units are not millimeters")

    def run(section, path, function, *function_args):
        print("Validate", path.name, flush=True)
        try:
            outcome = function(path, *function_args)
        except Exception as exc:
            outcome = {"file": path.name, "valid": False, "errors": [str(exc)],
                       "exception": traceback.format_exc(limit=5)}
        report[section].append(outcome)
        if not outcome["valid"]:
            report["errors"].extend(f"{path.name}: {error}" for error in outcome["errors"])

    for path in sorted(folder.glob("*.3mf")):
        run("print_packs", path, validate_pack, EXPECTED_PACKS.get(path.name), args.bed_mm)
    for path in sorted(folder.glob("*.stl")):
        run("stl_parts", path, validate_stl, part_by_file.get(path.name), args.bed_mm)
    for name, variant in EXPECTED_STEP_FILES.items():
        run("step_assemblies", folder / name, validate_step, step_expectations(variant, manifest))
    unexpected_steps = sorted(p.name for p in folder.glob("*.step") if p.name not in EXPECTED_STEP_FILES)
    if unexpected_steps:
        report["errors"].append("Unexpected STEP exports need validation expectations: " + ", ".join(unexpected_steps))

    report["totals"] = {
        "expected_3mf_files": len(EXPECTED_PACKS), "actual_3mf_files": len(report["print_packs"]),
        "expected_named_build_items": sum(expected_inventory.values()),
        "actual_named_build_items": sum(p.get("actual_count", 0) for p in report["print_packs"]),
        "expected_unique_stl_parts": len(expected_inventory), "actual_stl_parts": len(report["stl_parts"]),
        "expected_step_assemblies": len(EXPECTED_STEP_FILES), "actual_step_assemblies": len(report["step_assemblies"]),
    }
    report["valid"] = not report["errors"]
    save()
    print(json.dumps({"valid": report["valid"], "totals": report["totals"],
                      "errors": report["errors"], "report": str(args.report.resolve())}, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
