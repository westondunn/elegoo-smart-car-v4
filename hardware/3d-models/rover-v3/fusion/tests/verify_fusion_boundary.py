"""Focused API-double checks; Autodesk Fusion itself is not executed.

These doubles verify millimetre/centimetre conversion, nested native component
placement, non-mutating geometry capture, identity selection, and best-effort
restoration. They do not emulate Autodesk's geometry kernel or event runtime.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "RoverMotion"))
import motion_math as mm
import motion_plan as plan


class Matrix:
    def __init__(self, values=None):
        self.values = list(mm.identity() if values is None else values)

    @staticmethod
    def create():
        return Matrix()

    def getCell(self, row, col):
        return self.values[4 * row + col]

    def setCell(self, row, col, value):
        self.values[4 * row + col] = value
        return True


def load_script():
    adsk = types.ModuleType("adsk")
    core, fusion = types.ModuleType("adsk.core"), types.ModuleType("adsk.fusion")
    core.Matrix3D = Matrix
    for name in ("HTMLEventHandler", "UserInterfaceGeneralEventHandler", "CustomEventHandler"):
        setattr(core, name, type(name, (), {}))
    adsk.core, adsk.fusion = core, fusion
    sys.modules.update({"adsk": adsk, "adsk.core": core, "adsk.fusion": fusion})
    spec = importlib.util.spec_from_file_location("RoverMotionBoundaryTestSubject", PROJECT / "RoverMotion" / "RoverMotion.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = load_script()


class Collection:
    def __init__(self, values=()):
        self.values = list(values)

    @property
    def count(self):
        return len(self.values)

    def item(self, index):
        return self.values[index]


class Attributes:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def itemByName(self, group, name):
        value = self.values.get((group, name))
        return types.SimpleNamespace(value=value) if value is not None else None

    def add(self, group, name, value):
        self.values[(group, name)] = value


class Component:
    def __init__(self, name, pid=None, occurrences=(), bodies=()):
        self.name, self.partNumber = name, pid or ""
        self.attributes = Attributes({("RoverV3", "id"): pid} if pid else {})
        self.occurrences, self.bRepBodies = Collection(occurrences), Collection(bodies)


class Occurrence:
    def __init__(self, component, matrix=None, fail=False):
        self.component = component
        self._matrix = matrix or Matrix()
        self.isValid = True
        self.fail = fail
        self.writes = 0

    @property
    def transform2(self):
        return self._matrix

    @transform2.setter
    def transform2(self, value):
        self.writes += 1
        if self.fail:
            raise RuntimeError("Injected restore failure")
        self._matrix = value


class Body:
    def __init__(self, name, point_cm):
        self.name, self.point_cm = name, tuple(point_cm)
        self.isSolid, self.volume, self.appearance = True, 5.7, None


class TemporaryManager:
    def __init__(self):
        self.copied = []

    def copy(self, body):
        result = Body(body.name, body.point_cm)
        self.copied.append(result)
        return result

    def transform(self, body, matrix):
        # Independent affine evaluation in Fusion centimetres.
        p = body.point_cm
        body.point_cm = tuple(sum(matrix.getCell(r, c) * p[c] for c in range(3))
                              + matrix.getCell(r, 3) for r in range(3))
        return True


class BoundaryTests(unittest.TestCase):
    def assertMatrixAlmostEqual(self, actual, expected, places=11):
        for a, e in zip(actual, expected):
            self.assertAlmostEqual(a, e, places=places)

    def test_mm_to_cm_once_and_roundtrip_keeps_rotation(self):
        pure = mm.multiply(mm.translation_mm((13., -27., 84.)),
                           mm.rotation_mm((0., 0., 0.), (0., 1., 0.), 37.))
        native = script.to_fusion(pure)
        self.assertEqual(native.getCell(0, 3), 1.3)
        self.assertEqual(native.getCell(1, 3), -2.7)
        self.assertEqual(native.getCell(2, 3), 8.4)
        self.assertEqual(native.getCell(0, 0), pure[0])
        self.assertMatrixAlmostEqual(script.from_fusion(native), pure)

    def test_nested_source_placement_and_wrapper_ownership(self):
        catalog = {pid: {"id": pid, "name": "Name for " + pid} for pid in plan.PART_IDS}
        parts = []
        for pid in plan.PART_IDS:
            children = ()
            if pid == "base":
                # Imported child repeats its wrapper ID; finder must not treat
                # that body-owner component as a second rover part.
                children = (Occurrence(Component("base", "base")),)
            part = Component("User display name " + pid, pid, children)
            parts.append(Occurrence(part, script.to_fusion(mm.translation_mm((20., 0., 0.)))))
        parent = mm.multiply(mm.translation_mm((40., -10., 30.)),
                             mm.rotation_mm((0., 0., 0.), (0., 0., 1.), 90.))
        assembly = Component("Imported assembly wrapper", occurrences=parts)
        root = Component("Root", occurrences=(Occurrence(assembly, script.to_fusion(parent)),))
        found = script.find_source_parts(root, catalog)
        self.assertEqual(set(found), set(plan.PART_IDS))
        expected = mm.multiply(parent, mm.translation_mm((20., 0., 0.)))
        for record in found.values():
            self.assertMatrixAlmostEqual(record["home"], expected)
        self.assertTrue(all(occurrence.writes == 0 for occurrence in parts))

    def test_ambiguous_or_incomplete_source_is_rejected_before_copy(self):
        catalog = {pid: {"id": pid, "name": pid} for pid in plan.PART_IDS}
        with self.assertRaisesRegex(RuntimeError, "Missing components"):
            script.find_source_parts(Component("Root"), catalog)
        duplicate = Component("Root", occurrences=(Occurrence(Component("base", "base")),
                                                    Occurrence(Component("base", "base"))))
        with self.assertRaisesRegex(RuntimeError, "Duplicate rover part ID"):
            script.find_source_parts(duplicate, catalog)

    def test_nested_body_geometry_is_baked_only_into_wrapper_local_space(self):
        root_body = Body("root body", (2., 3., 4.))
        child_body = Body("child body", (1., 0., 0.))
        grandchild_body = Body("grandchild body", (1., 0., 0.))
        grandchild = Component("grandchild", bodies=(grandchild_body,))
        grandchild_occ = Occurrence(grandchild, script.to_fusion(mm.translation_mm((0., 20., 0.))))
        child = Component("child", occurrences=(grandchild_occ,), bodies=(child_body,))
        local = mm.multiply(mm.translation_mm((10., 0., 0.)),
                            mm.rotation_mm((0., 0., 0.), (0., 0., 1.), 90.))
        child_occ = Occurrence(child, script.to_fusion(local))
        wrapper = Component("wrapper", occurrences=(child_occ,), bodies=(root_body,))
        manager = TemporaryManager()
        records = script.capture_bodies(wrapper, manager)
        by_name = {record["name"]: record["body"].point_cm for record in records}
        self.assertMatrixAlmostEqual(by_name["root body"], (2., 3., 4.))
        self.assertMatrixAlmostEqual(by_name["child body"], (1., 1., 0.))
        self.assertMatrixAlmostEqual(by_name["grandchild body"], (-1., 1., 0.))
        self.assertEqual(root_body.point_cm, (2., 3., 4.))
        self.assertEqual(child_body.point_cm, (1., 0., 0.))
        self.assertEqual(grandchild_body.point_cm, (1., 0., 0.))
        self.assertEqual(child_occ.writes + grandchild_occ.writes, 0)
        self.assertEqual(len(records), 3)

    def test_copy_startup_names_new_document_without_renaming_locked_root(self):
        class LockedRoot(Component):
            def __setattr__(self, name, value):
                if name == "name" and hasattr(self, "name"):
                    raise RuntimeError("root component name cannot be changed")
                super().__setattr__(name, value)

        source_parts = [Occurrence(Component(pid, pid, bodies=(Body(pid, (1., 2., 3.)),)))
                        for pid in plan.PART_IDS]
        source_root = Component("Source Root", occurrences=source_parts)
        source = types.SimpleNamespace(rootComponent=source_root)
        new_root = LockedRoot("Fusion-managed root name")

        def new_occurrence(matrix):
            component = Component("New component")
            def add_body(body):
                component.bRepBodies.values.append(body)
                return body
            component.bRepBodies.add = add_body
            occurrence = Occurrence(component, matrix)
            new_root.occurrences.values.append(occurrence)
            return occurrence

        new_root.occurrences.addNewComponent = new_occurrence
        design = types.SimpleNamespace(rootComponent=new_root, designType=None,
                                       appearances=Collection())
        document = types.SimpleNamespace(name="Untitled", products=types.SimpleNamespace(
            itemByProductType=lambda kind: design if kind == "DesignProductType" else None))
        app = types.SimpleNamespace(activeDocument=types.SimpleNamespace(name="Original rover"),
                                    userInterface=types.SimpleNamespace(),
                                    activeViewport=types.SimpleNamespace(fit=lambda: None, refresh=lambda: None))
        def add_document(kind):
            app.activeDocument = document
            return document
        app.documents = types.SimpleNamespace(add=add_document)
        script.adsk.core.DocumentTypes = types.SimpleNamespace(FusionDesignDocumentType=1)
        script.adsk.fusion.Design = types.SimpleNamespace(cast=lambda value: value)
        script.adsk.fusion.DesignTypes = types.SimpleNamespace(DirectDesignType="direct")
        manager = TemporaryManager()
        script.adsk.fusion.TemporaryBRepManager = types.SimpleNamespace(get=lambda: manager)
        with tempfile.TemporaryDirectory(prefix="rover_motion_test_") as folder:
            session = script.Session(app, Path(folder))
            # Markers are optional presentation aids, outside this startup check.
            session.add_markers = lambda manager: None
            session.create_or_resume(source)
            self.assertEqual(document.name, "Rover V3 - Motion and Assembly Views")
            self.assertEqual(new_root.name, "Fusion-managed root name")
            self.assertEqual(design.designType, "direct")
            self.assertEqual(session.report["source_body_count"], 60)
            self.assertEqual(session.report["copied_body_count"], 60)
            self.assertEqual(len(session.occurrences), 60)
            self.assertEqual(new_root.attributes.itemByName("RoverMotion", "complete").value, "true")
            self.assertTrue(all(occurrence.writes == 0 for occurrence in source_parts))
            self.assertEqual(source_root.name, "Source Root")

    def session_for_restore(self, active=True):
        session = script.Session.__new__(script.Session)
        session.document = types.SimpleNamespace(isValid=True)
        session.design = types.SimpleNamespace(isValid=True)
        session.ui = types.SimpleNamespace(activeCommand="SelectCommand",
                                           activeWorkspace=types.SimpleNamespace(id="FusionSolidEnvironment"))
        session.progress = .8
        session.app = types.SimpleNamespace(
            activeDocument=session.document if active else object(),
            activeViewport=types.SimpleNamespace(refresh=lambda: None),
        )
        session.home = {pid: mm.translation_mm((index * 10., 0., 0.))
                        for index, pid in enumerate(("base", "upper_deck", "uno_board"))}
        session.occurrences = {pid: Occurrence(Component(pid)) for pid in session.home}
        return session

    def test_restore_continues_after_one_component_failure(self):
        session = self.session_for_restore()
        session.occurrences["base"].fail = True
        errors = session.restore()
        self.assertEqual(len(errors), 1)
        self.assertIn("base", errors[0])
        for pid in ("upper_deck", "uno_board"):
            self.assertEqual(session.occurrences[pid].writes, 1)
            self.assertMatrixAlmostEqual(script.from_fusion(session.occurrences[pid].transform2), session.home[pid])
        self.assertEqual(session.progress, .8)

    def test_restore_never_changes_an_inactive_document(self):
        session = self.session_for_restore(active=False)
        warnings = session.restore()
        self.assertTrue(warnings)
        self.assertTrue(all(occurrence.writes == 0 for occurrence in session.occurrences.values()))

    def test_restore_defers_while_another_fusion_command_is_active(self):
        session = self.session_for_restore()
        session.ui.activeCommand = "Extrude"
        warnings = session.restore()
        self.assertTrue(warnings)
        self.assertTrue(all(occurrence.writes == 0 for occurrence in session.occurrences.values()))

    def test_no_model_placement_changes_outside_design_workspace(self):
        session = self.session_for_restore()
        for workspace in (None, types.SimpleNamespace(id="AnimationEnvironment")):
            session.ui.activeWorkspace = workspace
            warnings = session.restore()
            self.assertTrue(warnings)
            with self.assertRaisesRegex(RuntimeError, "Design"):
                session.ensure_active()
        self.assertTrue(all(occurrence.writes == 0 for occurrence in session.occurrences.values()))

    def test_control_cleanup_releases_partial_startup_resources_once(self):
        session = script.Session.__new__(script.Session)
        session.closing = False
        session.report = {"warnings": [], "stage": "failed"}
        events, deleted = [], []
        session.event_id = "test_event"
        session.app = types.SimpleNamespace(unregisterCustomEvent=lambda event: events.append(event))
        session.custom_event = object()
        session.clock = types.SimpleNamespace(finish=lambda: None)
        session.palette = types.SimpleNamespace(isValid=True, deleteMe=lambda: deleted.append(True))
        session.release_controls()
        session.release_controls()
        self.assertEqual(events, ["test_event"])
        self.assertEqual(deleted, [True])
        self.assertTrue(session.closing)
        self.assertIsNone(session.palette)
        self.assertIsNone(session.custom_event)
        self.assertEqual(session.report["stage"], "failed")


def main():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(BoundaryTests)
    names = [test.id().split(".")[-1] for test in suite]
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {
        "test_scope": "Focused API doubles for units, source hierarchy, independent copy, and restoration.",
        "fusion_runtime_executed": False,
        "geometry_kernel_executed": False,
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "status": "passed" if result.wasSuccessful() else "failed",
        "checks": names,
        "failed_checks": [test.id().split(".")[-1] for test, _ in result.failures + result.errors],
    }
    (PROJECT.parent / "verification" / "fusion_boundary_validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
