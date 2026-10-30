"""Build the Rover V3 assembly inside Autodesk Fusion desktop.

Run with Utilities > Scripts and Add-Ins > Scripts. This is a script, not an
add-in. No external Python packages, account credentials or network operations
are used. The source STEP solids remain the geometry authority; native Fusion
components, construction geometry, parameters, materials and joints are added.

Offline syntax/preflight validation is distinct from running this script in
Fusion. Only a successful desktop run can produce the native .f3d archive.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sys
import tempfile
import traceback

import adsk.core
import adsk.fusion

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from manifest_tools import (IDENTITY, bom_rows, fusion_matrix_values,
                            load_and_preflight, normalized_axis,
                            safe_asset_path, sha256_file)
import native_features


ATTRIBUTE_GROUP = "RoverV3"
BUILD_REVISION = "3.0.1"
MATERIAL_ALIASES = {
    "pla": ["PLA", "Polylactic Acid", "Polylactic acid (PLA)", "Polylactide"],
    "steel": ["Steel", "Steel, Mild", "Mild Steel", "Steel, Carbon"],
    "aluminum": ["Aluminum", "Aluminium"],
    "aluminium": ["Aluminum", "Aluminium"],
    "rubber": ["Rubber"],
}
DEFAULT_COLORS = {
    "printed": [37, 104, 150, 255], "printed_part": [37, 104, 150, 255],
    "electronics": [32, 114, 76, 255], "electronics_reference": [32, 114, 76, 255],
    "motor": [236, 187, 49, 255], "wheel": [43, 48, 54, 255],
    "battery": [74, 78, 88, 255], "hardware": [170, 179, 190, 255],
    "reference": [161, 122, 64, 255],
}


def _items(collection):
    for index in range(collection.count):
        yield collection.item(index)


def _attribute(entity, key, value):
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    entity.attributes.add(ATTRIBUTE_GROUP, key, value)


def _description(part):
    fidelity = part.get("fidelity", "Unspecified geometry fidelity")
    if not isinstance(fidelity, str):
        fidelity = json.dumps(fidelity, ensure_ascii=False, sort_keys=True)
    return " | ".join(x for x in [fidelity, part.get("notes", "")] if x)


def _walk_occurrences(occurrence):
    yield occurrence
    for child in _items(occurrence.childOccurrences):
        yield from _walk_occurrences(child)


def _all_bodies(occurrence):
    for member in _walk_occurrences(occurrence):
        for body in _items(member.component.bRepBodies):
            yield body


def _transform(values):
    matrix = adsk.core.Matrix3D.create()
    values = fusion_matrix_values(values)
    for row in range(4):
        for col in range(4):
            if not matrix.setCell(row, col, values[row * 4 + col]):
                raise RuntimeError("Fusion rejected an occurrence transform")
    return matrix


def _output_folder():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    preferred = HERE / "output" / stamp
    try:
        preferred.mkdir(parents=True, exist_ok=False)
        return preferred
    except OSError:
        return Path(tempfile.mkdtemp(prefix="RoverFusion_"))


def _write_report(folder, report):
    (folder / "fusion_build_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _set_document_name(document, name, report):
    """Name the new document; the root component's name is host-controlled."""
    report["document_title"] = {"requested": name}
    try:
        # Document.name is writable before the document's first save. Naming
        # is cosmetic and must not prevent geometry creation if a host rejects it.
        document.name = name
        report["document_title"]["status"] = "assigned"
    except Exception as exc:
        report["document_title"].update(status="not_assigned", error=str(exc))
        report["warnings"].append(
            f"Document title was not changed: {exc}. Choose the name when saving in Fusion.")


def _write_bom(folder, manifest):
    rows = bom_rows(manifest)
    with (folder / "Rover_V3_BOM.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _normal_name(name):
    return re.sub(r"[^a-z0-9]", "", name.casefold())


class MaterialManager:
    """Assign only a named, available physical material; report all gaps."""

    def __init__(self, app, design, report):
        self.app = app
        self.design = design
        self.report = report
        self.material_cache = {}
        self.appearance_cache = {}
        self.material_index = {}
        self.appearance_seed = None
        self.appearance_seed_property = None
        for library in _items(app.materialLibraries):
            for material in _items(library.materials):
                self.material_index.setdefault(_normal_name(material.name), (material, library.name))

    def _physical_material(self, intent):
        if not intent:
            return None, {"status": "not_assigned_composite_or_unspecified"}
        if isinstance(intent, str):
            name, supplied_aliases = intent, []
            basis = "Manifest material intent; actual hardware composition not independently verified"
        else:
            name = intent.get("name", "")
            supplied_aliases = intent.get("aliases", [])
            basis = intent.get("basis", "Manifest material intent")
        if not name:
            return None, {"status": "not_assigned_composite_or_unspecified"}
        key = _normal_name(name)
        if key in self.material_cache:
            material, info = self.material_cache[key]
            return material, dict(info, basis=basis)
        names = [name] + list(supplied_aliases) + MATERIAL_ALIASES.get(name.casefold(), [])
        for candidate in names:
            match = self.material_index.get(_normal_name(candidate))
            if match:
                source, library_name = match
                material = self.design.materials.addByCopy(source, f"Rover - {name}")
                if not material:
                    raise RuntimeError(f"Cannot copy physical material {source.name}")
                info = {"status": "assigned_from_loaded_library", "intended": name,
                        "library": library_name, "library_material": source.name,
                        "design_material": material.name, "basis": basis}
                self.material_cache[key] = material, info
                return material, info
        info = {"status": "unresolved_material_intent", "intended": name,
                "basis": basis, "tried_names": names,
                "action": "Assign a matching physical material in Fusion. Display colour does not set density."}
        self.material_cache[key] = None, info
        return None, info

    def _find_color_property(self, appearance):
        for pid in ("generic_diffuse", "opaque_albedo", "metal_f0"):
            prop = appearance.appearanceProperties.itemById(pid)
            if prop:
                color = adsk.core.ColorProperty.cast(prop)
                if color and not color.isReadOnly:
                    return color
        for prop in _items(appearance.appearanceProperties):
            color = adsk.core.ColorProperty.cast(prop)
            if color and not color.isReadOnly and not color.hasMultipleValues:
                return color
        return None

    def _appearance(self, name, rgba):
        cache_key = (name, tuple(rgba))
        if cache_key in self.appearance_cache:
            return self.appearance_cache[cache_key]
        if self.appearance_seed is None:
            preferences = ["Plastic - Matte (White)", "Plastic - Glossy (White)",
                           "Paint - Enamel Glossy (White)", "Paint - Enamel Glossy (Grey)"]
            candidates = []
            libraries = list(_items(self.app.materialLibraries))
            for wanted in preferences:
                for library in libraries:
                    seed = library.appearances.itemByName(wanted)
                    if seed:
                        candidates.append(seed)
            for library in libraries:
                candidates.extend(_items(library.appearances))
            # Test a design copy; the source library appearance is read-only.
            for seed in candidates:
                copy = self.design.appearances.addByCopy(seed, "Rover colour template")
                if copy and self._find_color_property(copy):
                    self.appearance_seed = copy
                    break
                if copy:
                    copy.deleteMe()
        if self.appearance_seed is None:
            raise RuntimeError("No editable colour appearance was found in loaded Fusion libraries")
        result = self.design.appearances.addByCopy(self.appearance_seed, name)
        color = self._find_color_property(result)
        if not color:
            raise RuntimeError(f"Appearance {name} has no writable colour property")
        color.value = adsk.core.Color.create(*[int(channel) for channel in rgba])
        self.appearance_cache[cache_key] = result
        return result

    def apply(self, occurrence, part):
        try:
            material, material_info = self._physical_material(part.get("physical_material"))
            if material:
                for member in _walk_occurrences(occurrence):
                    member.component.material = material
                for body in _all_bodies(occurrence):
                    body.material = material
        except Exception as exc:
            # A library or assignment problem must remain explicit without
            # discarding otherwise usable geometry and joints.
            material_info = {"status": "assignment_failed_or_partial",
                             "intended": part.get("physical_material"),
                             "error": str(exc),
                             "action": "Review and assign physical materials manually before using mass properties"}
            self.report["warnings"].append(f"{part['id']}: physical material assignment failed: {exc}")
        _attribute(occurrence.component, "physical_material_status", material_info)
        if material_info["status"] == "unresolved_material_intent":
            self.report["warnings"].append(
                f"{part['id']}: {material_info['intended']} physical material unavailable; intent retained as metadata")
        category = part.get("category", "reference")
        rgba = part.get("color_rgba", DEFAULT_COLORS.get(category, [130, 145, 160, 255]))
        appearance_info = {"rgba": rgba, "status": "unassigned"}
        try:
            appearance = self._appearance(f"Rover - {category} - {'_'.join(map(str, rgba))}", rgba)
            for body in _all_bodies(occurrence):
                body.appearance = appearance
            if rgba[3] < 255:
                occurrence.component.opacity = rgba[3] / 255.0
            appearance_info.update(status="assigned", name=appearance.name)
        except Exception as exc:
            appearance_info["error"] = str(exc)
            self.report["warnings"].append(f"{part['id']}: colour appearance assignment failed: {exc}")
        return material_info, appearance_info


def _new_occurrence(root, part):
    occurrence = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    if not occurrence:
        raise RuntimeError(f"Cannot create component {part['id']}")
    occurrence.isGrounded = False
    if hasattr(occurrence, "isGroundToParent"):
        occurrence.isGroundToParent = False
    component = occurrence.component
    component.name = part["name"]
    component.partNumber = part["id"]
    component.description = _description(part)
    return occurrence


def _part_metadata(occurrence, part, path, history):
    for key in ("id", "category", "fidelity", "notes", "physical_material", "source"):
        if key in part:
            _attribute(occurrence.component, key, part[key])
    _attribute(occurrence.component, "source_step", part["step_file"])
    _attribute(occurrence.component, "source_step_sha256", sha256_file(path))
    _attribute(occurrence.component, "geometry_history", history)


def _import_part(app, root, part, bundle):
    occurrence = _new_occurrence(root, part)
    component = occurrence.component
    path = safe_asset_path(bundle, part["step_file"])
    options = app.importManager.createSTEPImportOptions(str(path))
    options.isViewFit = False
    imported = app.importManager.importToTarget2(options, component)
    if imported is None or imported.count == 0:
        raise RuntimeError(f"Fusion did not import STEP objects for {part['id']}")
    bodies = list(_all_bodies(occurrence))
    if not bodies or any(not body.isSolid for body in bodies):
        raise RuntimeError(f"{part['id']}: expected solid BRep geometry in STEP")
    if any(body.volume <= 0 for body in bodies):
        raise RuntimeError(f"{part['id']}: imported body has zero or negative volume")
    occurrence.transform2 = _transform(part.get("transform_mm", IDENTITY))
    # A STEP with nested subcomponents still represents one supplied rigid part.
    descendants = list(_walk_occurrences(occurrence))
    if len(descendants) > 1:
        members = adsk.core.ObjectCollection.create()
        for child in descendants:
            if child != occurrence:
                child.isGrounded = False
                if hasattr(child, "isGroundToParent"):
                    child.isGroundToParent = False
            members.add(child)
        group = root.rigidGroups.add(members, True)
        if not group:
            raise RuntimeError(f"Cannot rigidly group nested STEP bodies in {part['id']}")
        group.name = f"Internal rigidity - {part['id']}"
    _part_metadata(occurrence, part, path, "Imported STEP BRep; original sketch/feature history not encoded in STEP")
    return occurrence, {"id": part["id"], "name": component.name,
                        "solid_body_count": len(bodies),
                        "geometry_volume_mm3": sum(body.volume for body in bodies) * 1000.0,
                        "status": "imported_solid_BRep"}


def _make_part(app, design, root, part, bundle, report, use_native):
    if not use_native or "native_recipe" not in part:
        return _import_part(app, root, part, bundle)
    occurrence = _new_occurrence(root, part)
    before_parameters = {parameter.name for parameter in _items(design.userParameters)}
    try:
        record = native_features.build_part(design, occurrence.component, part)
        occurrence.transform2 = _transform(part.get("transform_mm", IDENTITY))
        _part_metadata(occurrence, part, safe_asset_path(bundle, part["step_file"]), record["geometry_history"])
        _attribute(occurrence.component, "native_recipe", part["native_recipe"])
        return occurrence, record
    except Exception as exc:
        # Preserve a complete, faithful assembly if an installed Fusion version
        # rejects an optional feature recipe. This is recorded as STEP fallback.
        detail = traceback.format_exc()
        if not occurrence.deleteMe():
            raise RuntimeError(f"Cannot clean up failed native component {part['id']}") from exc
        for parameter in list(_items(design.userParameters)):
            if parameter.name not in before_parameters:
                name = parameter.name
                try:
                    parameter.deleteMe()
                except Exception as cleanup_error:
                    report["warnings"].append(f"{part['id']}: parameter cleanup for {name}: {cleanup_error}")
                # Autodesk documents that deleteMe may return True even if a
                # referenced parameter remains. Inspect the collection again.
                remaining = design.userParameters.itemByName(name)
                if remaining:
                    remaining.comment = "NATIVE BUILD FELL BACK TO STEP: this parameter does not drive the imported body"
        report["warnings"].append(f"{part['id']}: native recipe used STEP fallback: {exc}")
        occurrence, record = _import_part(app, root, part, bundle)
        record["native_recipe_status"] = "failed_and_fell_back_to_reference_STEP"
        record["native_recipe_error"] = detail
        _attribute(occurrence.component, "native_recipe_status", record["native_recipe_status"])
        return occurrence, record


def _offset_sketch(component, name, z_cm):
    plane = component.xYConstructionPlane
    if abs(z_cm) > 1e-12:
        plane_input = component.constructionPlanes.createInput()
        if not plane_input.setByOffset(plane, adsk.core.ValueInput.createByReal(z_cm)):
            raise RuntimeError(f"Cannot define datum plane for {name}")
        plane = component.constructionPlanes.add(plane_input)
        plane.name = f"{name} - plane"
        plane.isLightBulbOn = False
    sketch = component.sketches.add(plane)
    sketch.name = name
    sketch.isLightBulbOn = False
    return sketch


def _anchor_point(component, name, point_cm):
    sketch = _offset_sketch(component, name, point_cm.z)
    point = sketch.sketchPoints.add(sketch.modelToSketchSpace(point_cm))
    point.isFixed = True
    return point


def _joint_geometry(occurrence, joint):
    origin = joint["origin_mm"]
    axis = normalized_axis(joint["axis"])
    # A 10 mm native datum axis is enough to establish direction unambiguously.
    first = adsk.core.Point3D.create(*[value / 10.0 for value in origin])
    second = adsk.core.Point3D.create(*[(origin[i] + 10.0 * axis[i]) / 10.0 for i in range(3)])
    inverse = occurrence.transform2.copy()
    if not inverse.invert():
        raise RuntimeError(f"Cannot invert owner transform for joint {joint['id']}")
    first.transformBy(inverse)
    second.transformBy(inverse)
    p1 = _anchor_point(occurrence.component, f"{joint['id']} - origin", first)
    p2 = _anchor_point(occurrence.component, f"{joint['id']} - direction", second)
    axis_input = occurrence.component.constructionAxes.createInput()
    if not axis_input.setByTwoPoints(p1, p2):
        raise RuntimeError(f"Cannot define axis for joint {joint['id']}")
    axis_entity = occurrence.component.constructionAxes.add(axis_input)
    axis_entity.name = f"{joint['id']} - axis"
    axis_entity.isLightBulbOn = False
    origin_proxy = p1.createForAssemblyContext(occurrence)
    axis_proxy = axis_entity.createForAssemblyContext(occurrence)
    geometry = adsk.fusion.JointGeometry.createByPoint(origin_proxy)
    if not geometry or not axis_proxy:
        raise RuntimeError(f"Cannot create joint context for {joint['id']}")
    return geometry, axis_proxy


def _build_joint(root, occurrences, definition):
    a = occurrences[definition["part_a"]]
    b = occurrences[definition["part_b"]]
    kind = definition["type"]
    geometry, axis = (None, None) if kind == "rigid" else _joint_geometry(a, definition)
    joint_input = root.asBuiltJoints.createInput(a, b, geometry)
    if not joint_input:
        raise RuntimeError(f"Cannot create joint input {definition['id']}")
    if kind == "revolute":
        success = joint_input.setAsRevoluteJointMotion(adsk.fusion.JointDirections.CustomJointDirection, axis)
    elif kind == "slider":
        success = joint_input.setAsSliderJointMotion(adsk.fusion.JointDirections.CustomJointDirection, axis)
    else:
        success = joint_input.setAsRigidJointMotion()
    if not success:
        raise RuntimeError(f"Cannot set {kind} motion for {definition['id']}")
    joint = root.asBuiltJoints.add(joint_input)
    if not joint:
        raise RuntimeError(f"Cannot add joint {definition['id']}")
    joint.name = definition.get("name", definition["id"])
    _attribute(joint, "definition", definition)
    if kind == "slider" and "limits_mm" in definition:
        motion = adsk.fusion.SliderJointMotion.cast(joint.jointMotion)
        limits = motion.slideLimits
        limits.minimumValue = definition["limits_mm"][0] / 10.0
        limits.maximumValue = definition["limits_mm"][1] / 10.0
        limits.isMinimumValueEnabled = True
        limits.isMaximumValueEnabled = True
    elif kind == "revolute" and "limits_deg" in definition:
        motion = adsk.fusion.RevoluteJointMotion.cast(joint.jointMotion)
        limits = motion.rotationLimits
        limits.minimumValue = math.radians(definition["limits_deg"][0])
        limits.maximumValue = math.radians(definition["limits_deg"][1])
        limits.isMinimumValueEnabled = True
        limits.isMaximumValueEnabled = True
    joint.isSuppressed = not definition.get("enabled", True)
    joint.isLightBulbOn = False
    return joint, {"id": definition["id"], "type": kind,
                   "suppressed": joint.isSuppressed,
                   "part_a": definition["part_a"], "part_b": definition["part_b"],
                   "origin_mm": definition.get("origin_mm"),
                   "axis": definition.get("axis"),
                   "fidelity": definition.get("fidelity", "Assembly constraint; moving axes need hardware confirmation"),
                   "notes": definition.get("notes", ""),
                   "status": "created_native_as_built_joint"}


def _reference_sketch(root, definition):
    sketch = _offset_sketch(root, f"REFERENCE - {definition['id']}", definition.get("z_mm", 0) / 10.0)
    for circle in definition.get("circles", []):
        x, y = circle["center_mm"]
        entity = sketch.sketchCurves.sketchCircles.addByCenterRadius(
            adsk.core.Point3D.create(x / 10.0, y / 10.0, 0), circle["diameter_mm"] / 20.0)
        entity.isConstruction = True
        entity.isFixed = True
    for rectangle in definition.get("rectangles", []):
        lo, hi = rectangle["min_mm"], rectangle["max_mm"]
        lines = sketch.sketchCurves.sketchLines.addTwoPointRectangle(
            adsk.core.Point3D.create(lo[0] / 10.0, lo[1] / 10.0, 0),
            adsk.core.Point3D.create(hi[0] / 10.0, hi[1] / 10.0, 0))
        for line in _items(lines):
            line.isConstruction = True
            line.isFixed = True
    _attribute(sketch, "purpose", "Reference construction geometry; does not resize the imported STEP bodies")
    return sketch


def _check_health(root, joints, report):
    errors = []
    for joint in joints:
        if joint.isSuppressed:
            continue
        timeline = joint.timelineObject
        if timeline is None:
            errors.append(f"{joint.name}: expected parametric timeline object is missing")
            continue
        state = timeline.healthState
        message = timeline.errorOrWarningMessage
        if state == adsk.fusion.FeatureHealthStates.ErrorFeatureHealthState:
            errors.append(f"{joint.name}: {message}")
        elif state == adsk.fusion.FeatureHealthStates.WarningFeatureHealthState:
            report["warnings"].append(f"Joint {joint.name}: {message}")
    report["joint_runtime_health_errors"] = errors
    report["top_level_component_count"] = root.occurrences.count
    report["all_component_occurrence_count"] = root.allOccurrences.count
    if errors:
        raise RuntimeError("Fusion reported joint errors: " + "; ".join(errors))


def run(context):
    ui = None
    output = None
    report = {"format_version": 1, "status": "starting", "fusion_runtime_executed": True,
              "builder_revision": BUILD_REVISION, "stage": "preflight",
              "created_utc": datetime.now(timezone.utc).isoformat(),
              "parts": [], "joints": [], "warnings": [],
              "geometry_history": "Exact STEP solids plus selected native parametric recipes; per-part status is recorded",
              "mass_and_strength_status": "No calibrated assembled mass, printed density or structural simulation claimed"}
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        report["fusion_version"] = app.version
        manifest_path = HERE / "assembly_manifest.json"
        manifest, preflight_report = load_and_preflight(manifest_path)
        report["preflight"] = preflight_report
        report["manifest_sha256"] = sha256_file(manifest_path)
        report["warnings"].extend(preflight_report["warnings"])
        output = _output_folder()
        _write_bom(output, manifest)
        _write_report(output, report)

        report["stage"] = "create_document"
        document = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        if not document:
            raise RuntimeError("A Fusion document could not be created")
        design = adsk.fusion.Design.cast(
            document.products.itemByProductType("DesignProductType"))
        if not design:
            raise RuntimeError("A Fusion design document could not be created")
        design.designType = adsk.fusion.DesignTypes.ParametricDesignType
        design.fusionUnitsManager.distanceDisplayUnits = adsk.fusion.DistanceUnits.MillimeterDistanceUnits
        root = design.rootComponent
        _set_document_name(document, manifest.get("project_name", "Rover V3 Full Assembly"), report)
        _attribute(root, "manifest", manifest)
        _attribute(root, "engineering_status", manifest.get("engineering_status", "Fit and clearance review required"))
        _attribute(root, "geometry_history", report["geometry_history"])

        report["stage"] = "create_reference_parameters"
        for definition in manifest.get("parameters", []):
            comment = definition.get("comment", "")
            if definition.get("role", "reference") == "reference":
                comment = "REFERENCE: does not resize imported STEP. " + comment
            parameter = design.userParameters.add(
                definition["name"], adsk.core.ValueInput.createByString(definition["expression"]),
                definition.get("units", "mm"), comment)
            if not parameter:
                raise RuntimeError(f"Cannot create user parameter {definition['name']}")

        report["stage"] = "initialize_materials"
        materials = MaterialManager(app, design, report)
        occurrences = {}
        report["stage"] = "build_components"
        for part in manifest["parts"]:
            report["current_part_id"] = part["id"]
            occurrence, record = _make_part(app, design, root, part, manifest_path.parent, report,
                                             manifest.get("build_options", {}).get("use_native_recipes", True))
            occurrences[part["id"]] = occurrence
            material_info, appearance_info = materials.apply(occurrence, part)
            record.update(physical_material=material_info, appearance=appearance_info,
                          fidelity=part.get("fidelity"), notes=part.get("notes", ""))
            report["parts"].append(record)
            _write_report(output, report)
            adsk.doEvents()

        report.pop("current_part_id", None)
        report["stage"] = "create_reference_geometry"
        # Capture installed transforms before constraining the moving components.
        if design.snapshots.hasPendingSnapshot:
            design.snapshots.add()
        occurrences[manifest["grounded_part_id"]].isGrounded = True
        for definition in manifest.get("reference_sketches", []):
            _reference_sketch(root, definition)
        joints = []
        # Suppressed study joints are created first, then suppressed immediately;
        # their installed rigid counterpart can then be created without a clash.
        definitions = sorted(manifest.get("joints", []), key=lambda item: item.get("enabled", True))
        report["stage"] = "create_joints"
        for definition in definitions:
            report["current_joint_id"] = definition["id"]
            joint, record = _build_joint(root, occurrences, definition)
            joints.append(joint)
            report["joints"].append(record)
            _write_report(output, report)
            adsk.doEvents()
        report.pop("current_joint_id", None)
        report["stage"] = "check_joint_health"
        design.computeAll()
        _check_health(root, joints, report)
        report["native_parametric_parts"] = [part["id"] for part in report["parts"]
                                            if part["status"] == "created_native_parametric_solid"]
        report["imported_STEP_parts"] = [part["id"] for part in report["parts"]
                                        if part["status"] == "imported_solid_BRep"]
        root.isOriginFolderLightBulbOn = False
        root.isConstructionFolderLightBulbOn = False
        root.isSketchFolderLightBulbOn = False
        root.isJointsFolderLightBulbOn = False
        for occurrence in occurrences.values():
            occurrence.component.isOriginFolderLightBulbOn = False
            occurrence.component.isSketchFolderLightBulbOn = False
            occurrence.component.isConstructionFolderLightBulbOn = False
        app.activeViewport.fit()
        app.activeViewport.refresh()

        report["stage"] = "export_archive"
        archive_path = output / "Rover_V3_Full_Assembly.f3d"
        options = design.exportManager.createFusionArchiveExportOptions(str(archive_path))
        if not options or not design.exportManager.execute(options):
            raise RuntimeError("Fusion archive export failed")
        if not archive_path.is_file() or archive_path.stat().st_size == 0:
            raise RuntimeError("Fusion reported export success but the local F3D is missing or empty")
        report["native_archive"] = {"path": str(archive_path), "bytes": archive_path.stat().st_size,
                                    "sha256": sha256_file(archive_path), "exported_by_fusion": True}
        report["status"] = "completed_with_warnings" if report["warnings"] else "completed"
        report["stage"] = "complete"
        report["completed_utc"] = datetime.now(timezone.utc).isoformat()
        _write_report(output, report)
        ui.messageBox(
            f"Rover assembly created in a new Fusion design. Builder {BUILD_REVISION}.\n\n"
            f"Native F3D, component CSV and build report:\n{output}\n\n"
            f"Imported components: {len(occurrences)}\nNative joints: {len(joints)}\n"
            f"Warnings: {len(report['warnings'])}\n\n"
            "Review the report for material availability and reference-model fidelity. "
            "Use Save in Fusion to add this design to your selected project. "
            "Driving parameters resize native recipe parts; reference parameters do not resize imported STEP bodies.",
            "Rover V3 assembly complete")
    except Exception:
        report["status"] = "failed"
        report["error"] = traceback.format_exc()
        if output is None:
            output = _output_folder()
        _write_report(output, report)
        if ui:
            ui.messageBox(
                "The Fusion build stopped. Any partially created design remains open for inspection.\n\n"
                f"Builder: {BUILD_REVISION}\nStage: {report.get('stage', 'unknown')}\n\n"
                f"Report: {output / 'fusion_build_report.json'}\n\n{report['error']}",
                "Rover V3 build needs attention")


def stop(context):
    pass
