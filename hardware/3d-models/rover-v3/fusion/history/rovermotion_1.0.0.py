"""Rover V3 presentation companion for Autodesk Fusion.

Run with the completed Rover V3 assembly active. A separate direct-design
document receives independent BRep copies. Original geometry, joints and
materials are never edited. This is live Design-workspace playback, not a
native Animation-workspace storyboard or a physical simulation.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sys
import tempfile
import threading
import time
import traceback
import uuid

import adsk.core
import adsk.fusion

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import motion_math as mm
import motion_plan as plan

VERSION = "1.0.0"
GROUP = "RoverMotion"
PALETTE_ID = "RoverV3_Motion_Palette_v1"
DURATION = 8.0
_session = None
_handlers = []


def items(collection):
    for i in range(collection.count):
        yield collection.item(i)


def attr(entity, key, group=GROUP):
    value = entity.attributes.itemByName(group, key)
    return value.value if value else None


def put_attr(entity, key, value):
    if not isinstance(value, str):
        value = json.dumps(value, separators=(",", ":"))
    entity.attributes.add(GROUP, key, value)


def from_fusion(matrix):
    """Fusion cm -> pure row-major mm, without ambiguous array ordering."""
    result = [matrix.getCell(r, c) for r in range(4) for c in range(4)]
    for index in (3, 7, 11):
        result[index] *= 10.0
    return mm.validate_rigid(result)


def to_fusion(values):
    """Pure row-major mm -> Fusion cm, converted exactly once."""
    values = list(mm.validate_rigid(values))
    for index in (3, 7, 11):
        values[index] /= 10.0
    matrix = adsk.core.Matrix3D.create()
    for r in range(4):
        for c in range(4):
            if not matrix.setCell(r, c, values[r*4+c]):
                raise RuntimeError("Fusion rejected a rigid placement matrix")
    return matrix


def output_folder():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    folder = HERE / "output" / stamp
    try:
        folder.mkdir(parents=True)
        return folder
    except OSError:
        return Path(tempfile.mkdtemp(prefix="RoverMotion_"))


def part_id(component, catalog):
    """Use stored identity first; exact labels support the delivered STEP too."""
    known = set(plan.PART_IDS)
    for candidate in (attr(component, "id", "RoverV3"), component.partNumber):
        if candidate in known:
            return candidate
    aliases = {p["name"]: p["id"] for p in catalog.values()}
    aliases.update({pid: pid for pid in known})
    label = re.sub(r":\d+$", "", component.name.strip())
    return aliases.get(label)


def find_source_parts(root, catalog):
    found = {}

    def walk(component, parent, depth):
        if depth > 40:
            raise RuntimeError("Assembly nesting exceeds the supported depth")
        # component.occurrences returns native local placements. Explicit
        # composition avoids mixing proxy and native assembly contexts.
        for occurrence in items(component.occurrences):
            world = mm.multiply(parent, from_fusion(occurrence.transform2))
            child = occurrence.component
            pid = part_id(child, catalog)
            if pid:
                if pid in found:
                    raise RuntimeError("Duplicate rover part ID: " + pid)
                found[pid] = {"component": child, "home": world}
                # A STEP child can repeat its wrapper name. The wrapper owns
                # that complete geometry subtree; do not match it a second time.
            else:
                walk(child, world, depth + 1)

    walk(root, mm.identity(), 0)
    missing = sorted(set(plan.PART_IDS) - set(found))
    if missing:
        raise RuntimeError(
            "This is not the completed Rover V3 assembly. Missing components:\n"
            + ", ".join(missing)
            + "\nOpen the finished RoverFusion design or the delivered complete STEP and run again.")
    return found


def capture_bodies(component, manager, relative=None, depth=0):
    """Copy native bodies into wrapper-local coordinates without editing source."""
    if depth > 40:
        raise RuntimeError("Geometry nesting exceeds the supported depth")
    relative = mm.identity() if relative is None else relative
    records = []
    for body in items(component.bRepBodies):
        if not body.isSolid or body.volume <= 0:
            raise RuntimeError("Rover geometry includes an open or empty body: " + body.name)
        temporary = manager.copy(body)
        if not temporary or not manager.transform(temporary, to_fusion(relative)):
            raise RuntimeError("Could not copy body: " + body.name)
        records.append({"body": temporary, "name": body.name,
                        "volume_cm3": body.volume, "appearance": body.appearance})
    for occurrence in items(component.occurrences):
        local = mm.multiply(relative, from_fusion(occurrence.transform2))
        records.extend(capture_bodies(occurrence.component, manager, local, depth + 1))
    return records


class FrameClock(threading.Thread):
    """Only fireCustomEvent touches Fusion from this scheduler thread."""
    def __init__(self, app, event_id):
        super().__init__(name="RoverMotionClock", daemon=True)
        self.app, self.event_id = app, event_id
        self.stopping = threading.Event()
        self.playing = threading.Event()
        self.pending = threading.Event()

    def run(self):
        while not self.stopping.wait(1.0 / 24.0):
            if self.playing.is_set() and not self.pending.is_set():
                self.pending.set()
                try:
                    if not self.app.fireCustomEvent(self.event_id):
                        self.pending.clear()
                except Exception:
                    self.pending.clear()
                    self.playing.clear()

    def finish(self):
        self.playing.clear()
        self.stopping.set()
        if self.is_alive():
            self.join(timeout=0.25)


class Session:
    def __init__(self, app, folder):
        self.app, self.ui, self.folder = app, app.userInterface, folder
        self.document = self.design = self.palette = self.clock = None
        self.custom_event = None
        self.event_id = "RoverMotion_" + uuid.uuid4().hex
        self.occurrences, self.home, self.marker_bodies = {}, {}, []
        self.mode, self.progress = "full", 0.0
        self.framed_mode = None
        self.markers, self.closing = True, False
        self.status = "Assembled. Choose a view, then Play or move the slider."
        self.report = {"version": VERSION, "native_runtime": "Autodesk Fusion",
                       "source_modified_by_script": False, "warnings": [], "stage": "start"}
        self.catalog = {p["id"]: p for p in json.loads((HERE / "part_catalog.json").read_text("utf-8"))["parts"]}

    def write_report(self):
        (self.folder / "rover_motion_report.json").write_text(
            json.dumps(self.report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def create_or_resume(self, source):
        plan.validate_plan(self.catalog)
        if attr(source.rootComponent, "presentation_version"):
            self.resume(source)
            return
        self.report["stage"] = "identify_source"
        self.report["source_document"] = self.app.activeDocument.name
        found = find_source_parts(source.rootComponent, self.catalog)
        manager = adsk.fusion.TemporaryBRepManager.get()
        self.report["stage"] = "capture_source_geometry"
        # Capture all geometry before any new document is created.
        for pid in plan.PART_IDS:
            found[pid]["bodies"] = capture_bodies(found[pid]["component"], manager)
            if not found[pid]["bodies"]:
                raise RuntimeError("No solid geometry found for " + pid)
        self.report["source_body_count"] = sum(len(x["bodies"]) for x in found.values())
        self.report["stage"] = "create_presentation_document"
        self.document = self.app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        self.design = adsk.fusion.Design.cast(self.document.products.itemByProductType("DesignProductType"))
        if not self.design:
            raise RuntimeError("The new document has no Fusion Design product")
        self.design.designType = adsk.fusion.DesignTypes.DirectDesignType
        try:
            self.document.name = "Rover V3 - Motion and Assembly Views"
        except Exception as exc:
            self.report["warnings"].append("Document title unchanged: " + str(exc))
        root = self.design.rootComponent
        put_attr(root, "presentation_version", VERSION)
        put_attr(root, "source_document", self.report["source_document"])
        put_attr(root, "purpose", "Presentation copy; not printable manufacturing geometry or native animation timeline")
        appearance_cache = {}
        part_units = {pid: unit for unit, ids in plan.BOUGHT_UNITS.items() for pid in ids}
        self.report["stage"] = "populate_presentation_geometry"
        copied_count = 0
        for pid in plan.PART_IDS:
            self.report["current_part"] = pid
            record = found[pid]
            occurrence = root.occurrences.addNewComponent(to_fusion(record["home"]))
            if not occurrence:
                raise RuntimeError("Could not create presentation component " + pid)
            occurrence.isGrounded = False
            if hasattr(occurrence, "isGroundToParent"):
                occurrence.isGroundToParent = False
            component = occurrence.component
            category = "PRINTED" if pid in plan.PRINTED_PART_IDS else "BOUGHT " + part_units[pid]
            component.name = category + " | " + self.catalog[pid]["name"]
            component.partNumber = pid
            component.description = "Presentation reference; " + category
            put_attr(component, "source_id", pid)
            put_attr(component, "home_matrix_mm", record["home"])
            self.occurrences[pid], self.home[pid] = occurrence, tuple(record["home"])
            for b in record["bodies"]:
                copied = component.bRepBodies.add(b["body"])
                if not copied or not copied.isSolid:
                    raise RuntimeError("Fusion could not persist solid for " + pid)
                if abs(copied.volume - b["volume_cm3"]) > max(1e-8, b["volume_cm3"] * 1e-6):
                    raise RuntimeError("Copied solid volume differs for " + pid)
                copied.name = b["name"]
                copied_count += 1
                appearance = b["appearance"]
                if appearance:
                    try:
                        key = appearance.id
                        if key not in appearance_cache:
                            appearance_cache[key] = self.design.appearances.addByCopy(
                                appearance, "Rover motion - " + appearance.name)
                        copied.appearance = appearance_cache[key]
                    except Exception as exc:
                        self.report["warnings"].append(pid + ": colour copy failed: " + str(exc))
            component.isOriginFolderLightBulbOn = False
            component.isSketchFolderLightBulbOn = False
            component.isConstructionFolderLightBulbOn = False
        self.report.pop("current_part", None)
        self.report["copied_body_count"] = copied_count
        if copied_count != self.report["source_body_count"]:
            raise RuntimeError("Body count changed during presentation copy")
        self.add_markers(manager)
        put_attr(root, "complete", "true")
        self.report.update(stage="ready", component_count=len(self.occurrences),
                           printed_components=21, purchased_units=10,
                           visual_marker_count=len(self.marker_bodies))
        self.app.activeViewport.fit()
        self.app.activeViewport.refresh()
        self.write_report()

    def add_markers(self, manager):
        # Current wheels are rotationally symmetric reference solids. Small
        # visible dots show spin; they are tagged, toggleable presentation aids.
        marker_appearance = None
        try:
            seed = next(iter(items(self.design.appearances)), None)
            if seed:
                marker_appearance = self.design.appearances.addByCopy(seed, "Visual wheel marker - yellow")
                for prop in items(marker_appearance.appearanceProperties):
                    colour = adsk.core.ColorProperty.cast(prop)
                    if colour:
                        colour.value = adsk.core.Color.create(255, 218, 58, 255)
                        break
        except Exception as exc:
            self.report["warnings"].append("Marker colour: " + str(exc))
        for corner, group in plan.WHEEL_GROUPS.items():
            try:
                x, y, z = group["origin_mm"]
                x += -27.2 if corner.endswith("left") else 27.2
                temporary = manager.createSphere(adsk.core.Point3D.create(x/10, (y+23)/10, z/10), 0.12)
                body = self.occurrences["wheel_hub_" + corner].component.bRepBodies.add(temporary)
                if not body:
                    raise RuntimeError("No marker body")
                body.name = "VISUAL ONLY - wheel rotation marker"
                put_attr(body, "role", "wheel_rotation_marker")
                if marker_appearance:
                    body.appearance = marker_appearance
                self.marker_bodies.append(body)
            except Exception as exc:
                self.report["warnings"].append(corner + ": marker unavailable: " + str(exc))

    def resume(self, design):
        root = design.rootComponent
        if attr(root, "complete") != "true":
            raise RuntimeError("This presentation copy was not completed. Open the original assembly and run again.")
        if design.designType != adsk.fusion.DesignTypes.DirectDesignType:
            raise RuntimeError("This presentation copy has been converted to parametric history. Open the original rover and regenerate it.")
        self.document, self.design = self.app.activeDocument, design
        for occurrence in items(root.occurrences):
            pid = attr(occurrence.component, "source_id")
            if pid in plan.PART_IDS:
                if pid in self.occurrences:
                    raise RuntimeError("Duplicate saved presentation part: " + pid)
                self.occurrences[pid] = occurrence
                self.home[pid] = mm.validate_rigid(json.loads(attr(occurrence.component, "home_matrix_mm")))
                for body in items(occurrence.component.bRepBodies):
                    if attr(body, "role") == "wheel_rotation_marker":
                        self.marker_bodies.append(body)
        if set(self.occurrences) != set(plan.PART_IDS):
            raise RuntimeError("Saved presentation is missing components; regenerate from the original assembly")
        self.report.update(stage="resume", source_document=attr(root, "source_document"),
                           component_count=64, visual_marker_count=len(self.marker_bodies))
        self.apply_pose("home", 0, check_command=False)
        self.set_markers(True)
        self.write_report()

    def ensure_active(self, check_command=True):
        if not self.document or not self.document.isValid or not self.design or not self.design.isValid:
            raise RuntimeError("The presentation document has closed. Run RoverMotion again on your assembly.")
        if self.app.activeDocument != self.document:
            raise RuntimeError("Playback paused. Activate the Rover motion presentation tab, then press Play.")
        workspace = self.ui.activeWorkspace
        if not workspace or workspace.id != "FusionSolidEnvironment":
            raise RuntimeError("Playback paused. Switch this presentation to the Design workspace, then press Play.")
        if any(not occurrence.isValid for occurrence in self.occurrences.values()):
            raise RuntimeError("A presentation component was deleted. Regenerate the copy from the original assembly.")
        if check_command and self.ui.activeCommand != "SelectCommand":
            raise RuntimeError("Playback paused. Finish the active Fusion command, then press Play.")

    def apply_pose(self, mode, progress, check_command=True):
        self.ensure_active(check_command)
        matrices = mm.pose_matrices(mode, progress, self.home)
        # Fixed components are skipped; every changed component still derives
        # from home. No per-frame snapshots or timeline features are created.
        for pid, values in matrices.items():
            current = from_fusion(self.occurrences[pid].transform2)
            if max(abs(a-b) for a, b in zip(current, values)) > 1e-10:
                self.occurrences[pid].transform2 = to_fusion(values)
        self.app.activeViewport.refresh()

    def restore(self):
        """Best-effort complete restore; try every part even after one failure."""
        errors = []
        if not self.document or not self.document.isValid:
            return errors
        if self.app.activeDocument != self.document:
            return ["Presentation tab is inactive; reactivate it and run RoverMotion to restore."]
        if self.ui.activeCommand != "SelectCommand":
            return ["Finish the active Fusion command, then run RoverMotion on this presentation to restore."]
        workspace = self.ui.activeWorkspace
        if not workspace or workspace.id != "FusionSolidEnvironment":
            return ["Return to the Design workspace and run RoverMotion on this presentation to restore."]
        for pid, occurrence in self.occurrences.items():
            try:
                if not occurrence.isValid:
                    raise RuntimeError("component is no longer valid")
                occurrence.transform2 = to_fusion(self.home[pid])
            except Exception as exc:
                errors.append(pid + ": " + str(exc))
        if not errors:
            self.progress = 0
        self.app.activeViewport.refresh()
        return errors

    def frame_mode(self):
        """Fit the full exploded extent once, so playback stays in the view."""
        if self.framed_mode == self.mode:
            return
        if self.mode in plan.EXPLODE_PHASES:
            self.apply_pose(self.mode, 1.)
            self.app.activeViewport.fit()
            self.apply_pose(self.mode, self.progress)
        else:
            self.app.activeViewport.fit()
        self.framed_mode = self.mode

    def set_markers(self, visible):
        self.markers = bool(visible)
        for body in self.marker_bodies:
            if body.isValid:
                body.isLightBulbOn = self.markers
        self.app.activeViewport.refresh()

    def state(self):
        if self.palette and self.palette.isValid:
            self.palette.sendInfoToHTML("state", json.dumps({
                "mode": self.mode, "progress": self.progress,
                "playing": bool(self.clock and self.clock.playing.is_set()),
                "status": self.status, "markers": self.markers,
                "document_name": self.document.name if self.document and self.document.isValid else "Presentation closed",
                "counts": {"printed": 21, "bought": 10}}))

    def pause(self):
        if self.clock:
            self.clock.playing.clear()

    def tick(self):
        if self.closing or not self.clock or not self.clock.playing.is_set():
            return
        try:
            progress = self.play_start_progress + self.direction * (time.monotonic() - self.play_started) / DURATION
            self.progress = max(0., min(1., progress))
            self.apply_pose(self.mode, self.progress)
            if progress >= 1 or progress <= 0:
                self.pause()
                self.status = "Playback complete. Use Reverse or Assembled to return."
            self.state()
        except Exception as exc:
            self.pause()
            self.status = str(exc)
            self.state()

    def save_output(self, image):
        self.pause()
        self.ensure_active()
        dialog = self.ui.createFileDialog()
        dialog.title = "Save rover presentation image" if image else "Save rover presentation pose"
        dialog.filter = "PNG image (*.png)" if image else "Fusion archive (*.f3d)"
        dialog.initialDirectory = str(self.folder)
        dialog.filename = "Rover_V3_" + self.mode + (".png" if image else ".f3d")
        if dialog.showSave() != adsk.core.DialogResults.DialogOK:
            self.status = "Save canceled. Current pose remains available."
            return
        if image:
            success = self.app.activeViewport.saveAsImageFile(dialog.filename, 1920, 1080)
        else:
            put_attr(self.design.rootComponent, "saved_pose", {"mode": self.mode, "progress": self.progress})
            options = self.design.exportManager.createFusionArchiveExportOptions(dialog.filename, self.design.rootComponent)
            success = self.design.exportManager.execute(options)
        if not success:
            raise RuntimeError("Fusion did not complete the export")
        self.status = "Saved: " + dialog.filename
        self.report.setdefault("exports", []).append({"path": dialog.filename, "kind": "PNG" if image else "presentation_f3d"})
        self.write_report()

    def dispatch(self, data):
        operation = data.get("op")
        if operation == "ready":
            self.state()
            return
        if operation == "close":
            self.close(terminate=True)
            return
        self.pause()
        self.ensure_active()
        if operation == "mode":
            mode = data.get("mode")
            if mode not in ("drive", "turn", "pan", *plan.EXPLODE_PHASES):
                raise ValueError("Unknown mode")
            self.mode, self.progress = mode, 0.
            self.apply_pose(mode, 0)
            self.frame_mode()
            self.status = "Ready. Press Play or move the progress slider."
        elif operation == "scrub":
            progress = float(data.get("progress", 0))
            if not math.isfinite(progress):
                raise ValueError("Invalid slider progress")
            self.progress = max(0., min(1., progress))
            self.frame_mode()
            self.apply_pose(self.mode, self.progress)
            self.status = "Paused at {:.0f}%.".format(100*self.progress)
        elif operation == "play":
            self.direction = -1 if data.get("direction") == -1 else 1
            if self.direction > 0 and self.progress >= 1:
                self.progress = 0.
            elif self.direction < 0 and self.progress <= 0:
                self.progress = 1.
            self.frame_mode()
            self.apply_pose(self.mode, self.progress)
            self.play_start_progress, self.play_started = self.progress, time.monotonic()
            self.clock.playing.set()
            self.status = "Playing. You can pause or scrub at any time."
        elif operation == "pause":
            self.status = "Paused."
        elif operation == "home":
            errors = self.restore()
            if errors:
                raise RuntimeError("Some components could not restore:\n" + "\n".join(errors))
            self.app.activeViewport.fit()
            self.framed_mode = None
            self.status = "Assembled. Every component is back at its saved starting placement."
        elif operation == "markers":
            self.set_markers(data.get("visible", True))
            self.status = "Wheel markers are presentation aids only."
        elif operation in ("image", "save"):
            self.save_output(operation == "image")
        else:
            raise ValueError("Unknown control action: " + str(operation))
        self.state()

    def open_controls(self):
        previous = self.ui.palettes.itemById(PALETTE_ID)
        if previous:
            previous.deleteMe()
        self.custom_event = self.app.registerCustomEvent(self.event_id)
        handler = TickHandler(self)
        self.custom_event.add(handler)
        _handlers.append(handler)
        self.clock = FrameClock(self.app, self.event_id)
        self.clock.start()
        # Hidden until its event handlers are attached, so ready cannot race.
        self.palette = self.ui.palettes.add(PALETTE_ID, "Rover motion and assembly", str(HERE / "palette.html"),
                                           False, True, True, 370, 780)
        incoming, closed = HTMLHandler(self), CloseHandler(self)
        self.palette.incomingFromHTML.add(incoming)
        self.palette.closed.add(closed)
        _handlers.extend((incoming, closed))
        self.palette.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateRight
        self.palette.isVisible = True
        self.state()

    def error(self, exc):
        self.pause()
        self.status = "Error: " + str(exc)
        self.report.setdefault("errors", []).append({"message": str(exc), "traceback": traceback.format_exc()})
        self.write_report()
        self.state()

    def close(self, terminate=False):
        if self.closing:
            return
        self.closing = True
        self.pause()
        restore_errors = self.restore()
        if restore_errors:
            self.report["restore_warnings"] = restore_errors
        self.release_controls()
        self.report["stage"] = "closed"
        self.write_report()
        if restore_errors:
            self.ui.messageBox("Motion stopped. The original assembly is unchanged.\n\n"
                               + "\n".join(restore_errors)
                               + "\n\nReport: " + str(self.folder / "rover_motion_report.json"), "Rover motion")
        if terminate:
            adsk.terminate()

    def release_controls(self):
        """Idempotent cleanup, also usable after a partial startup failure."""
        self.closing = True
        if self.clock:
            self.clock.finish()
        if self.custom_event:
            try:
                self.app.unregisterCustomEvent(self.event_id)
            except Exception as exc:
                self.report["warnings"].append("Custom event cleanup: " + str(exc))
            self.custom_event = None
        if self.palette:
            try:
                if self.palette.isValid:
                    self.palette.deleteMe()
            except Exception as exc:
                self.report["warnings"].append("Palette cleanup: " + str(exc))
            self.palette = None


class HTMLHandler(adsk.core.HTMLEventHandler):
    def __init__(self, session):
        super().__init__()
        self.session = session

    def notify(self, args):
        try:
            event = adsk.core.HTMLEventArgs.cast(args)
            if event.action == "rover" and not self.session.closing:
                self.session.dispatch(json.loads(event.data))
        except Exception as exc:
            self.session.error(exc)


class CloseHandler(adsk.core.UserInterfaceGeneralEventHandler):
    def __init__(self, session):
        super().__init__()
        self.session = session

    def notify(self, args):
        self.session.close(terminate=True)


class TickHandler(adsk.core.CustomEventHandler):
    def __init__(self, session):
        super().__init__()
        self.session = session

    def notify(self, args):
        try:
            self.session.tick()
        finally:
            if self.session.clock:
                self.session.clock.pending.clear()


def run(context):
    global _session
    app = adsk.core.Application.get()
    ui = app.userInterface
    try:
        if _session and not _session.closing:
            _session.close()
        _handlers.clear()
        document = app.activeDocument
        source = adsk.fusion.Design.cast(document.products.itemByProductType("DesignProductType")) if document else None
        if not source:
            raise RuntimeError("Open the finished Rover V3 Fusion design or its complete STEP assembly first.")
        workspace = ui.workspaces.itemById("FusionSolidEnvironment")
        if workspace and not workspace.isActive:
            workspace.activate()
        _session = Session(app, output_folder())
        _session.create_or_resume(source)
        _session.open_controls()
        adsk.autoTerminate(False)
    except Exception as exc:
        report_path = "No report created"
        if _session:
            _session.report.update(stage="failed", error=str(exc), traceback=traceback.format_exc())
            _session.release_controls()
            _session.write_report()
            report_path = str(_session.folder / "rover_motion_report.json")
        ui.messageBox("Rover motion needs attention.\n\n" + str(exc)
                      + "\n\nThe original rover geometry was not modified."
                      + "\nReport: " + report_path, "Rover motion")


def stop(context):
    global _session
    if _session:
        _session.close()
    _session = None
    _handlers.clear()
