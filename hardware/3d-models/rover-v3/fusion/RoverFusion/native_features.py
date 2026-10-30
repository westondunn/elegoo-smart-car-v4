"""Native, dimension-driven Fusion features for simple printed components.

The reference STEP remains in the package. A recipe is accepted only when its
initial native solid agrees with the independently exported STEP's bounding box
and volume. Construction locations are fixed assembly datums; named diameter,
width, length, height, corner-radius and cut-depth parameters drive features.
"""

from __future__ import annotations

import math

import adsk.core
import adsk.fusion


def _items(collection):
    for index in range(collection.count):
        yield collection.item(index)


def _point(x, y, z=0):
    return adsk.core.Point3D.create(x / 10.0, y / 10.0, z / 10.0)


def _parameter(design, name, millimetres, comment):
    existing = design.userParameters.itemByName(name)
    if existing:
        if abs(existing.value * 10.0 - millimetres) > 1e-5:
            raise ValueError(f"Shared parameter {name} conflicts with the native recipe's initial dimension")
        return name
    result = design.userParameters.add(name, adsk.core.ValueInput.createByString(f"{millimetres:.12g} mm"),
                                       "mm", "DRIVING NATIVE FEATURE: " + comment)
    if not result:
        raise RuntimeError(f"Cannot create native parameter {name}")
    return name


def _sketch(component, name, z_expression):
    plane_input = component.constructionPlanes.createInput()
    if not plane_input.setByOffset(component.xYConstructionPlane,
                                  adsk.core.ValueInput.createByString(z_expression)):
        raise RuntimeError(f"Cannot create parameter-driven plane for {name}")
    plane = component.constructionPlanes.add(plane_input)
    plane.name = name + " datum"
    plane.isLightBulbOn = False
    sketch = component.sketches.add(plane)
    sketch.name = name
    sketch.isLightBulbOn = False
    return sketch


def _circle(sketch, center, initial_diameter, diameter_expression):
    x, y = center
    circle = sketch.sketchCurves.sketchCircles.addByCenterRadius(_point(x, y), initial_diameter / 20.0)
    circle.centerSketchPoint.isFixed = True
    dimension = sketch.sketchDimensions.addDiameterDimension(
        circle, _point(x + initial_diameter, y + initial_diameter))
    dimension.parameter.expression = diameter_expression


def _rectangle(sketch, center, size, width_expression, length_expression):
    x, y = center
    width, length = size
    lines = sketch.sketchCurves.sketchLines.addTwoPointRectangle(
        _point(x - width / 2.0, y - length / 2.0),
        _point(x + width / 2.0, y + length / 2.0))
    # Anchor the rectangle at its centre so a width edit remains centred.
    diagonal = sketch.sketchCurves.sketchLines.addByTwoPoints(
        lines.item(0).startSketchPoint, lines.item(2).startSketchPoint)
    diagonal.isConstruction = True
    centre = sketch.sketchPoints.add(_point(x, y))
    centre.isFixed = True
    sketch.geometricConstraints.addMidPoint(centre, diagonal)
    horizontal = vertical = None
    for line in _items(lines):
        p1, p2 = line.startSketchPoint.geometry, line.endSketchPoint.geometry
        if abs(p1.y - p2.y) < 1e-8:
            horizontal = line
        if abs(p1.x - p2.x) < 1e-8:
            vertical = line
    if horizontal is None or vertical is None:
        raise RuntimeError("Rectangle did not produce horizontal and vertical edges")
    dimension = sketch.sketchDimensions.addDistanceDimension(
        horizontal.startSketchPoint, horizontal.endSketchPoint,
        adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation,
        _point(x, y - length / 2.0 - 4))
    dimension.parameter.expression = width_expression
    dimension = sketch.sketchDimensions.addDistanceDimension(
        vertical.startSketchPoint, vertical.endSketchPoint,
        adsk.fusion.DimensionOrientations.VerticalDimensionOrientation,
        _point(x + width / 2.0 + 4, y))
    dimension.parameter.expression = length_expression


def _extrude(component, sketch, depth_expression, name, body=None):
    if sketch.profiles.count != 1:
        raise RuntimeError(f"{name}: expected exactly one closed profile; got {sketch.profiles.count}")
    operation = (adsk.fusion.FeatureOperations.CutFeatureOperation if body else
                 adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    features = component.features.extrudeFeatures
    definition = features.createInput(sketch.profiles.item(0), operation)
    extent = adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByString(depth_expression))
    if not definition.setOneSideExtent(extent, adsk.fusion.ExtentDirections.PositiveExtentDirection):
        raise RuntimeError(f"Cannot define extrusion extent for {name}")
    if body:
        definition.participantBodies = [body]
    feature = features.add(definition)
    if not feature:
        raise RuntimeError(f"Cannot create native extrusion {name}")
    feature.name = name
    return feature


def _vertical_fillet(component, body, height_mm, expression, name):
    edges = adsk.core.ObjectCollection.create()
    for edge in _items(body.edges):
        if not edge.startVertex or not edge.endVertex:
            continue
        a, b = edge.startVertex.geometry, edge.endVertex.geometry
        if (abs(a.x - b.x) < 1e-8 and abs(a.y - b.y) < 1e-8
                and abs(abs(a.z - b.z) * 10.0 - height_mm) < 1e-5):
            edges.add(edge)
    if edges.count != 4:
        raise RuntimeError(f"{name}: expected four outside vertical rectangle edges")
    definitions = component.features.filletFeatures
    definition = definitions.createInput()
    definition.edgeSetInputs.addConstantRadiusEdgeSet(edges, adsk.core.ValueInput.createByString(expression), False)
    result = definitions.add(definition)
    if not result:
        raise RuntimeError(f"Cannot create native corner fillet {name}")
    result.name = name


def build_part(design, component, part):
    recipe = part["native_recipe"]
    pid = part["id"]
    kind = recipe["type"]
    parameter_names = []
    parameter_map = recipe.get("parameters", {})

    def param(key, value, description):
        name = parameter_map.get(key, f"{pid}_{key}")
        parameter_names.append(name)
        return _parameter(design, name, value, description)

    z = param("base_z", recipe["base_z_mm"], f"{pid} base datum Z")
    height = param("height", recipe["height_mm"], f"{pid} extrusion height")
    center = recipe["center_mm"]
    outline = _sketch(component, f"{pid} outer profile", z)
    if kind == "round_post":
        diameter = param("outer_diameter", recipe["outer_diameter_mm"], f"{pid} outside diameter")
        _circle(outline, center, recipe["outer_diameter_mm"], diameter)
    else:
        width = param("width", recipe["size_mm"][0], f"{pid} width about its fixed centre")
        length = param("length", recipe["size_mm"][1], f"{pid} length about its fixed centre")
        _rectangle(outline, center, recipe["size_mm"], width, length)
    feature = _extrude(component, outline, height, f"{pid} main extrusion")
    body = feature.bodies.item(0)
    body.name = part["name"]
    if recipe.get("corner_radius_mm", 0) > 0:
        radius = param("corner_radius", recipe["corner_radius_mm"], f"{pid} outside corner radius")
        _vertical_fillet(component, body, recipe["height_mm"], radius, f"{pid} corner rounds")

    cuts = list(recipe.get("cuts", []))
    if recipe.get("bore_diameter_mm", 0) > 0:
        cuts.insert(0, {"id": "bore", "type": "circle", "center_mm": center,
                        "diameter_mm": recipe["bore_diameter_mm"], "through": True})
    if recipe.get("counterbore_diameter_mm", 0) > 0:
        cuts.append({"id": "counterbore", "type": "circle", "center_mm": center,
                     "diameter_mm": recipe["counterbore_diameter_mm"], "through": False,
                     "depth_mm": recipe["counterbore_depth_mm"]})
    for cut in cuts:
        cid = cut["id"]
        through = cut.get("through", True)
        if through:
            plane_z, depth = z, height
        else:
            depth = param(f"{cid}_depth", cut["depth_mm"], f"{pid} {cid} pocket depth from top")
            plane_z = f"{z} + {height} - {depth}"
        if cut["type"] == "circle":
            diameter = param(f"{cid}_diameter", cut["diameter_mm"], f"{pid} {cid} diameter")
            sketch = _sketch(component, f"{pid} {cid} profile", plane_z)
            _circle(sketch, cut["center_mm"], cut["diameter_mm"], diameter)
            _extrude(component, sketch, depth, f"{pid} {cid} cut", body)
        elif cut["type"] == "rectangle":
            width = param(f"{cid}_width", cut["size_mm"][0], f"{pid} {cid} width")
            length = param(f"{cid}_length", cut["size_mm"][1], f"{pid} {cid} length")
            sketch = _sketch(component, f"{pid} {cid} profile", plane_z)
            _rectangle(sketch, cut["center_mm"], cut["size_mm"], width, length)
            _extrude(component, sketch, depth, f"{pid} {cid} cut", body)
        elif cut["type"] == "slot":
            # A capsule is exactly a rectangle plus two circular caps. Separate
            # native cuts make the same union without relying on undocumented
            # slot APIs. End-centre coordinates are fixed mounting datums.
            a, b = cut["centers_mm"]
            width = param(f"{cid}_width", cut["width_mm"], f"{pid} {cid} capsule width")
            dx, dy = abs(b[0] - a[0]), abs(b[1] - a[1])
            middle = [(a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0]
            sketch = _sketch(component, f"{pid} {cid} middle profile", plane_z)
            if dx > 1e-8 and dy < 1e-8:
                _rectangle(sketch, middle, [dx, cut["width_mm"]], f"{dx:.12g} mm", width)
            elif dy > 1e-8 and dx < 1e-8:
                _rectangle(sketch, middle, [cut["width_mm"], dy], width, f"{dy:.12g} mm")
            else:
                raise ValueError(f"{pid}: native capsule currently requires an axis-aligned slot")
            _extrude(component, sketch, depth, f"{pid} {cid} middle cut", body)
            for suffix, point in (("start", a), ("end", b)):
                sketch = _sketch(component, f"{pid} {cid} {suffix} profile", plane_z)
                _circle(sketch, point, cut["width_mm"], width)
                _extrude(component, sketch, depth, f"{pid} {cid} {suffix} cut", body)
        else:
            raise ValueError(f"Unsupported native cut type: {cut['type']}")

    design.computeAll()
    if component.bRepBodies.count != 1 or not body.isSolid or body.volume <= 0:
        raise RuntimeError(f"{pid}: native recipe did not produce one positive-volume solid")
    bounds = component.preciseBoundingBox
    minimum = [bounds.minPoint.x * 10.0, bounds.minPoint.y * 10.0, bounds.minPoint.z * 10.0]
    maximum = [bounds.maxPoint.x * 10.0, bounds.maxPoint.y * 10.0, bounds.maxPoint.z * 10.0]
    reference = recipe["reference"]
    bbox_error = max(abs(a - b) for actual, expected in
                     ((minimum, reference["bbox_min_mm"]), (maximum, reference["bbox_max_mm"]))
                     for a, b in zip(actual, expected))
    volume = body.volume * 1000.0
    volume_error = abs(volume - reference["volume_mm3"])
    tolerance = max(0.02, reference["volume_mm3"] * 1e-5)
    if bbox_error > 0.02 or volume_error > tolerance:
        raise RuntimeError(f"{pid}: native/STEP reference mismatch: bbox error {bbox_error:.6g} mm; "
                           f"volume error {volume_error:.6g} mm3")
    for feature in _items(component.features):
        if feature.healthState == adsk.fusion.FeatureHealthStates.ErrorFeatureHealthState:
            raise RuntimeError(f"{pid}: native feature error: {feature.errorOrWarningMessage}")
    return {"id": pid, "name": part["name"], "status": "created_native_parametric_solid",
            "native_recipe_type": kind, "driving_parameters": sorted(set(parameter_names)),
            "solid_body_count": 1, "geometry_volume_mm3": volume,
            "reference_equivalence": {"bbox_max_error_mm": bbox_error,
                                      "volume_error_mm3": volume_error,
                                      "volume_tolerance_mm3": tolerance,
                                      "status": "passed_bounding_box_and_volume"},
            "geometry_history": "Native sketches, dimensions, extrusion, cuts and optional corner fillets",
            "datum_behavior": "XY locations fixed; named size/depth parameters drive features; assembly placement remains as-built"}
