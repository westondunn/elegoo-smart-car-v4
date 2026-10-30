#!/usr/bin/env python3
"""Package exact rover inputs, a geometry-only assembly STEP and Fusion builder.

This script is for preparing the delivery outside Fusion. It never creates a
.f3d file. The only native-archive writer is RoverFusion.py running in Fusion.
"""
from __future__ import annotations

import argparse
import ast
import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import shutil
import sys
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCRIPT = HERE / "RoverFusion"
sys.path.insert(0, str(SCRIPT))
from manifest_tools import IDENTITY, bom_rows, load_and_preflight, sha256_file


def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _flatten_transform(transform):
    if isinstance(transform, list) and len(transform) == 4 and all(isinstance(row, list) and len(row) == 4 for row in transform):
        return [value for row in transform for value in row]
    return transform


def _copy_parts(records, group):
    result = []
    for original in records:
        part = dict(original)
        if group == "printed":
            source = ROOT / part["step_file"]
        else:
            source = Path(part["source_asset"])
        expected = part.get("sha256")
        actual = sha256_file(source)
        if expected and actual != expected:
            raise ValueError(f"Source hash mismatch for {part['id']}; regenerate its source manifest first")
        relative = Path("assets") / group / source.name
        destination = SCRIPT / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        part["step_file"] = relative.as_posix()
        part["sha256"] = actual
        part["transform_mm"] = _flatten_transform(part.get("transform_mm", IDENTITY))
        part.pop("source_asset", None)
        result.append(part)
    return result


def _reference_parameters():
    values = [
        ("ref_power_bank_width", 69.85, "User outer-envelope width"),
        ("ref_power_bank_length", 146.05, "User outer-envelope length"),
        ("ref_power_bank_height", 12.7, "User outer-envelope height"),
        ("ref_bank_clear_width", 73.025, "Clear width after 1/16 inch allowance on each side"),
        ("ref_bank_clear_length", 149.225, "Clear length after 1/16 inch allowance on each end"),
        ("ref_base_motor_contact_z", 4.5, "Assembly motor-contact face"),
        ("ref_deck_underside_z", 45.0, "As-built upper-deck underside"),
        ("ref_deck_nominal_thickness", 3.6, "Deck nominal sheet thickness, excluding local features"),
        ("ref_motor_hole_pitch", 7.799998946128, "Pitch retained from physically tested C1/C3 local motor interface"),
        ("ref_head_pocket_width", 7.4, "C3 washer/head pocket width"),
        ("ref_head_pocket_depth", 3.3, "C3 washer/head pocket depth"),
    ]
    return [{"name": name, "expression": f"{value:.12g} mm", "units": "mm",
             "role": "reference", "comment": comment} for name, value, comment in values]


def _native_formula_checks(manifest):
    results = []
    for part in manifest["parts"]:
        recipe = part.get("native_recipe")
        if not recipe:
            continue
        if recipe["type"] != "round_post" or recipe.get("cuts") or recipe.get("counterbore_diameter_mm", 0):
            raise ValueError("This delivery's independent native formula audit expects simple round posts only")
        x, y = recipe["center_mm"]
        radius = recipe["outer_diameter_mm"] / 2
        bore_radius = recipe.get("bore_diameter_mm", 0) / 2
        z, height = recipe["base_z_mm"], recipe["height_mm"]
        expected_volume = math.pi * (radius * radius - bore_radius * bore_radius) * height
        minimum, maximum = [x - radius, y - radius, z], [x + radius, y + radius, z + height]
        ref = recipe["reference"]
        volume_error = abs(expected_volume - ref["volume_mm3"])
        bbox_error = max(abs(a - b) for actual, recorded in
                         ((minimum, ref["bbox_min_mm"]), (maximum, ref["bbox_max_mm"]))
                         for a, b in zip(actual, recorded))
        if volume_error > 1e-6 or bbox_error > 1e-6:
            raise ValueError(f"Native post formula mismatch: {part['id']}")
        results.append({"part_id": part["id"], "volume_error_mm3": volume_error,
                        "bbox_error_mm": bbox_error, "status": "passed"})
    return {"status": "passed", "scope": "Analytic annular-cylinder recipe versus mechanical STEP reference metadata",
            "fusion_runtime_executed": False, "part_count": len(results), "parts": results}


def _export_step(manifest):
    import cadquery as cq
    assembly = cq.Assembly(name="Rover_V3_Complete_Assembly")
    total_volume = 0
    solid_count = 0
    for part in manifest["parts"]:
        wp = cq.importers.importStep(str(SCRIPT / part["step_file"]))
        objects = wp.vals()
        shape = objects[0] if len(objects) == 1 else cq.Compound.makeCompound(objects)
        if part["transform_mm"] != IDENTITY:
            values = part["transform_mm"]
            shape = shape.transformShape(cq.Matrix([values[i:i + 4] for i in (0, 4, 8, 12)]))
        solids = shape.Solids()
        if not shape.isValid() or not solids or any(s.Volume() <= 0 for s in solids):
            raise ValueError(f"Invalid exact STEP geometry: {part['id']}")
        total_volume += shape.Volume()
        solid_count += len(solids)
        color = cq.Color(*[channel / 255 for channel in part.get("color_rgba", [120, 140, 160, 255])])
        assembly.add(shape, name=part["id"], color=color)
    output = HERE / "Rover_V3_Complete_Assembly.step"
    assembly.save(str(output), "STEP", mode="default")
    imported = cq.importers.importStep(str(output)).val()
    volume_error = abs(imported.Volume() - total_volume)
    if not imported.isValid() or len(imported.Solids()) != solid_count or volume_error > max(1e-3, total_volume * 1e-8):
        raise ValueError("Combined assembly STEP round-trip failed")
    return {"status": "passed", "format": "STEP, geometry only; no Fusion joints or feature history",
            "component_count": len(manifest["parts"]), "solid_count": solid_count,
            "source_volume_mm3": total_volume, "reimported_volume_mm3": imported.Volume(),
            "volume_error_mm3": volume_error, "sha256": sha256_file(output),
            "bytes": output.stat().st_size, "cadquery_version": cq.__version__,
            "fusion_runtime_executed": False}


def _copy_mechanical_source():
    pairs = [
        "cad/source/build_printed_rover.py",
        "hardware/build_hardware.py",
        "mechanical_analysis/oem_geometry.json",
        "mechanical_analysis/assembly_layout.json",
        "baseline/Rover_V3_C3_Motor_Fit_Integrated.step",
        "baseline/C3_validation_source.py",
    ]
    for relative in pairs:
        destination = HERE / "mechanical_source" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    for filename in ("Rover_V3_C1_Motor_Fit.step", "Rover_V3_C1_X1C_PLA.3mf"):
        source = ROOT / "print_auxiliaries" / "CAD_Source" / "baseline" / filename
        shutil.copy2(source, HERE / "mechanical_source" / "baseline" / filename)
    (HERE / "mechanical_source" / "README_SOURCE.txt").write_text(
        "Mechanical master source supplied with the Fusion project.\n\n"
        "Requires Python with CadQuery 2.7 and NumPy. Run from this extracted source tree:\n"
        "  python cad/source/build_printed_rover.py\n"
        "  python hardware/build_hardware.py\n\n"
        "The printed generator recreates print parts and assembly-coordinate STEP instances\n"
        "from the retained C3 local interface and OEM outline/reference data. The hardware\n"
        "generator creates explicitly approximate packaging models. The generated STEP files\n"
        "do not update an already edited Fusion document automatically. Preserve manual\n"
        "Fusion edits before regenerating the project. These source scripts are separate\n"
        "from the dependency-free RoverFusion.py script that runs inside Fusion.\n\n"
        "The original user-supplied C1 motor STEP and C1 print 3MF are preserved in\n"
        "baseline for fit provenance. The C1 3MF is an earlier fit test, not the\n"
        "current full two-plate rover print project. The generator consumes C3.\n", encoding="utf-8")


def _write_catalog(manifest):
    rows = bom_rows(manifest)
    with (HERE / "Rover_V3_Component_Catalog.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with (HERE / "Fusion_Feature_Map.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(["part_id", "name", "intended_build_method", "native_dimensions", "runtime_status"])
        for part in manifest["parts"]:
            recipe = part.get("native_recipe")
            method = "Native circular sketch, extrusion, bore sketch and cut" if recipe else "Imported solid STEP BRep"
            dimensions = "Base Z, group outside diameter, group height, group bore diameter" if recipe else "No recovered source feature history"
            writer.writerow([part["id"], part["name"], method, dimensions,
                             "Desktop Fusion not run; inspect its generated report for actual result"])


def _copy_project_context():
    destination = HERE / "project_context"
    destination.mkdir(exist_ok=True)
    candidates = ["START_HERE.txt", "PROJECT_INSTRUCTIONS.txt", "QUICK_START.txt", "READ_ME_FIRST.txt",
                  "ASSEMBLY_GUIDE.txt", "HARDWARE_NOTES.txt", "PRINT_AND_ASSEMBLY_NOTES.txt",
                  "bambu/BAMBU_WORKFLOW.txt", "hardware/HARDWARE_REFERENCE_NOTES.txt",
                  "cad/hardware_and_assembly.json", "cad/printed_interference.json",
                  "hardware/reference_clearance_report.json", "previews/Rover_V3_Full_Assembly.png"]
    for relative in candidates:
        source = ROOT / relative
        if source.is_file():
            shutil.copy2(source, destination / source.name)


def _package(manifest):
    output = ROOT / "Rover_V3_Fusion_Personal_Project.zip"
    files = [path for path in HERE.rglob("*") if path.is_file()
             and "__pycache__" not in path.parts and "output" not in path.parts
             and path.suffix.lower() not in (".pyc", ".f3d")]
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=7) as archive:
        for path in sorted(files):
            archive.write(path, "Rover_V3_Fusion_Personal/" + path.relative_to(HERE).as_posix())
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError("Fusion project ZIP CRC check failed")
        archived_manifest = json.loads(archive.read("Rover_V3_Fusion_Personal/RoverFusion/assembly_manifest.json"))
        for part in archived_manifest["parts"]:
            data = archive.read("Rover_V3_Fusion_Personal/RoverFusion/" + part["step_file"])
            if sha256(data).hexdigest() != part["sha256"]:
                raise ValueError(f"Archived STEP hash mismatch: {part['id']}")
    return {"path": str(output), "bytes": output.stat().st_size, "sha256": sha256_file(output),
            "archive_member_count": len(files), "all_manifest_STEP_assets_verified_in_zip": True,
            "native_F3D_included": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-step", action="store_true", help="Do input validation only; no geometry assembly export")
    parser.add_argument("--package", action="store_true", help="Write the standalone delivery ZIP after preparation")
    parser.add_argument("--refresh-archive", action="store_true", help="Refresh context and ZIP after final geometry is already exported")
    args = parser.parse_args()
    if args.refresh_archive:
        manifest, preflight = load_and_preflight(SCRIPT / "assembly_manifest.json")
        for file in SCRIPT.glob("*.py"):
            ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        preflight.update(python_ast_valid=True, fusion_runtime_executed=False)
        _write_json(HERE / "bundle_preflight.json", preflight)
        readiness = json.loads((HERE / "FUSION_READINESS.json").read_text())
        for key, relative in (("printed_sha256", "cad/printed_assembly_manifest.json"),
                              ("hardware_sha256", "hardware/hardware_manifest.json")):
            if readiness["source_manifests"][key] != sha256_file(ROOT / relative):
                raise ValueError("Source geometry manifest changed; run a complete preparation before refreshing the ZIP")
        if not (HERE / "Rover_V3_Complete_Assembly.step").is_file():
            raise ValueError("Create and validate the assembly STEP before packaging")
        if sha256_file(HERE / "Rover_V3_Complete_Assembly.step") != readiness["geometry_STEP_roundtrip"]["sha256"]:
            raise ValueError("Assembly STEP changed after the recorded geometric round-trip validation")
        _copy_mechanical_source()
        _copy_project_context()
        package = _package(manifest)
        _write_json(ROOT / "fusion_delivery_receipt.json", package)
        print(json.dumps(package, indent=2))
        return
    printed = json.loads((ROOT / "cad/printed_assembly_manifest.json").read_text())
    hardware = json.loads((ROOT / "hardware/hardware_manifest.json").read_text())
    manifest = {key: value for key, value in printed.items() if key not in ("parts", "joints", "parameters")}
    manifest.update(project_name="Rover V3 Complete Assembly - PLA",
                    parts=_copy_parts(printed["parts"], "printed") + _copy_parts(hardware["parts"], "hardware"),
                    joints=printed.get("joints", []) + hardware.get("joints", []),
                    parameters=printed.get("parameters", []) + _reference_parameters(),
                    limitations=hardware.get("limitations", []),
                    coordinate_system="World millimetres; individual STEP solids already placed; identity occurrence transforms",
                    reference_sketches=[{"id": "bank_clear_envelope", "z_mm": 4.5,
                                         "rectangles": [{"min_mm": [-36.5125, -74.6125],
                                                         "max_mm": [36.5125, 74.6125]}]}])
    for joint in manifest["joints"]:
        if joint.get("part_b", "").startswith(("pi_standoff_", "uno_standoff_")):
            joint["part_a"] = "upper_deck"
        if joint["type"] != "rigid":
            joint.setdefault("fidelity", "Nominal demonstration axis; physical axis position and travel are unverified")
    _write_json(SCRIPT / "assembly_manifest.json", manifest)
    _, preflight = load_and_preflight(SCRIPT / "assembly_manifest.json")
    for file in SCRIPT.glob("*.py"):
        ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
    preflight.update(python_ast_valid=True, fusion_runtime_executed=False)
    _write_json(HERE / "bundle_preflight.json", preflight)
    native = _native_formula_checks(manifest)
    _write_json(HERE / "native_recipe_offline_checks.json", native)
    _write_catalog(manifest)
    _copy_mechanical_source()
    _copy_project_context()
    readiness = {"prepared_utc": datetime.now(timezone.utc).isoformat(),
                 "component_count": len(manifest["parts"]), "native_recipe_part_count": native["part_count"],
                 "joint_count": len(manifest["joints"]), "joint_types": preflight["joint_counts"],
                 "fusion_runtime_executed": False, "native_F3D_created": False,
                 "desktop_action": "Run RoverFusion from Scripts and Add-Ins to build and export native F3D",
                 "source_manifests": {"printed_sha256": sha256_file(ROOT / "cad/printed_assembly_manifest.json"),
                                      "hardware_sha256": sha256_file(ROOT / "hardware/hardware_manifest.json")}}
    if not args.skip_step:
        step = _export_step(manifest)
        _write_json(HERE / "assembly_STEP_validation.json", step)
        readiness["geometry_STEP_roundtrip"] = step
    _write_json(HERE / "FUSION_READINESS.json", readiness)
    if args.package:
        package = _package(manifest)
        _write_json(ROOT / "fusion_delivery_receipt.json", package)
        readiness["package"] = package
    print(json.dumps(readiness, indent=2))


if __name__ == "__main__":
    main()
