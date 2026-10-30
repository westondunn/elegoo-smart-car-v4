"""Rover P1B motor mounting retrofit R1 -- a physical-fit prototype.

Units: mm. Requires CadQuery 2.7. Run this script to regenerate the two handed
STLs, the screw spacer, STEP solids, and a dimensional manifest in this folder.
The Bambu project is prepared separately; running this script does not slice.

Local assembly axes: +X toward the wheel, +Y toward that chassis end, Z=0 at
the original inside floor. Original floor slots have centers (0, -3.9/+3.9).
The silver block's bottom mounting pair is translated +11 along Y. Lateral
slot center travel is 0..18, to be set from the actual freely rotating module.
Slot travel is NOT a claim that the motor can physically move that full range.

User measurements: A=11; current chassis ground clearance B~24; current
fully seated wheel/body gap C=14; inner shaft/post gap D=3; block22x12x4.
Block axes are inferred as22 high,12 along Y,4 across X. The existing floor
slot pitch7.8, floor thickness4.5 and carrier elevation27.5 above that floor
come from the existing P1B CAD. Actual motor/shaft geometry is not invented.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import math
import cadquery as cq
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib

HERE = Path(__file__).resolve().parent
P = {
    "revision": "R1", "plate_thickness": 4.0, "endward_offset": 11.0,
    "floor_pitch": 7.8, "floor_thickness": 4.5,
    "slide_min": 0.0, "slide_max": 18.0,
    "clearance_diameter": 3.4, "countersink_diameter": 6.4,
    "nut_pocket_af": 5.8, "nut_seat_z": 1.0,
    "assumed_nut_thickness": 2.4,
    "key_radius": 1.5, "key_arc_y": 3.1, "key_end_y": 3.6,
    "key_depth": 3.8,
    "xmin": -5.2, "xmax": 23.2, "ymin": -8.1, "ymax": 20.1,
    "outline_radius": 1.8,
    "rear_post_local_x": -6.5, "rear_post_local_y": -12.26291025,
    "rear_post_keepout_radius": 5.2,
    "floor_screw_length": 10.0, "floor_spacer_thickness": 1.6,
    "floor_spacer_od": 8.0, "block_screw_total_length": 8.0,
    "reported_ground_clearance": 24.0, "reported_side_gap": 14.0,
    "reported_inner_shaft_post_gap": 3.0,
    "block_height": 22.0, "block_length": 12.0, "block_thickness": 4.0,
    "carrier_underside_above_floor": 27.5,
    "mesh_tolerance": 0.015, "mesh_angular_tolerance": 0.06,
}


def box_between(x0, x1, y0, y1, z0, z1):
    return (cq.Workplane("XY").box(x1-x0, y1-y0, z1-z0)
            .translate(((x0+x1)/2, (y0+y1)/2, (z0+z1)/2)).val())


def cyl(d, h, x=0, y=0, z=0):
    return cq.Solid.makeCylinder(d/2, h, cq.Vector(x, y, z))


def pill(length, width, h, x, y, z=0, angle=0):
    return (cq.Workplane("XY").center(x, y).slot2D(length, width, angle)
            .extrude(h).translate((0, 0, z)).val())


def countersink_trough(y):
    travel = P["slide_max"] - P["slide_min"]
    cx = (P["slide_max"] + P["slide_min"])/2
    wide, small = P["countersink_diameter"], P["clearance_diameter"]
    depth = (wide-small)/2  # 90 degree included angle.
    cone = (cq.Workplane("XY").center(cx, y).slot2D(travel+wide, wide)
            .workplane(offset=depth).slot2D(travel+small, small).loft().val())
    return cone.fuse(pill(travel+wide, wide, 0.12, cx, y, -0.12)).clean()


def make_key():
    r, cy, end = P["key_radius"], P["key_arc_y"], P["key_end_y"]
    # Half circle follows the rounded inner end of the existing floor slot.
    outline = (cq.Workplane("XY").moveTo(-r, end).lineTo(-r, cy)
               .threePointArc((0, cy-r), (r, cy)).lineTo(r, end).close())
    key = outline.extrude(P["key_depth"]).translate((0, 0, -P["key_depth"])).val()
    # A small lead-in only at the entering end, while retaining a full root.
    key = cq.Workplane(obj=key).edges("<Z").chamfer(0.2).val()
    return key


def bare_adapter():
    w, l = P["xmax"]-P["xmin"], P["ymax"]-P["ymin"]
    s = (cq.Workplane("XY").box(w, l, P["plate_thickness"], centered=(True, True, False))
         .edges("|Z").fillet(P["outline_radius"])
         .translate(((P["xmin"]+P["xmax"])/2, (P["ymin"]+P["ymax"])/2, 0)).val())
    s = s.fuse(make_key()).clean()
    # Common relief also clears the rear Pi post when the handed plate rotates.
    s = s.cut(cyl(2*P["rear_post_keepout_radius"], 6,
                  P["rear_post_local_x"], P["rear_post_local_y"], -0.1)).clean()
    fy = -P["floor_pitch"]/2
    s = s.cut(cyl(P["clearance_diameter"], 10, 0, fy, -4.2))
    hex_pocket = (cq.Workplane("XY").polygon(6, P["nut_pocket_af"]/math.cos(math.pi/6))
                  .extrude(4.2-P["nut_seat_z"]).rotate((0,0,0),(0,0,1),30)
                  .translate((0, fy, P["nut_seat_z"])).val())
    s = s.cut(hex_pocket)
    for y in (P["endward_offset"]-P["floor_pitch"]/2,
              P["endward_offset"]+P["floor_pitch"]/2):
        travel = P["slide_max"]-P["slide_min"]
        cx = (P["slide_max"]+P["slide_min"])/2
        s = s.cut(pill(travel+P["clearance_diameter"], P["clearance_diameter"],
                       4.3, cx, y, -0.1))
        s = s.cut(countersink_trough(y))
    return s.clean()


def labeled_adapter(hand="A"):
    s = bare_adapter()
    outward = 1 if hand == "A" else -1
    if outward < 0:
        s = s.mirror("YZ")
    # Recessed labels live on the chassis-facing underside, never on the seat.
    plane = cq.Plane(origin=(outward*10.5, -0.1, 0.36), xDir=(1,0,0), normal=(0,0,-1))
    label = cq.Workplane(plane).text(hand, 3.8, 0.42, font="DejaVu Sans", kind="bold", combine=False).val()
    s = s.cut(label)
    x = outward*17.2
    arrow = (box_between(x-0.4, x+0.4, -2.0, 1.2, -0.05, 0.36)
             .fuse(cq.Workplane("XY").polyline([(x-1.4,1.0),(x+1.4,1.0),(x,3.0)])
                   .close().extrude(0.41).translate((0,0,-0.05)).val()))
    return s.cut(arrow).clean()


def make_spacer():
    return cyl(P["floor_spacer_od"], P["floor_spacer_thickness"]).cut(
        cyl(P["clearance_diameter"], P["floor_spacer_thickness"]+0.2, z=-0.1)).clean()


def exact_bounds(shape):
    b = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped, b, False, False)
    return b.Get()


def for_print(shape, adapter=True):
    if adapter:
        shape = shape.rotate((0,0,0), (1,0,0), 180).translate((0,0,P["plate_thickness"]))
    b = exact_bounds(shape)
    return shape.translate((-b[0], -b[1], -b[2]))


def report_shape(s):
    b = exact_bounds(s)
    return {"valid": bool(s.isValid()), "solid_count": len(s.Solids()),
            "volume_mm3": s.Volume(), "bbox_mm": [b[3]-b[0],b[4]-b[1],b[5]-b[2]]}


def build():
    HERE.mkdir(parents=True, exist_ok=True)
    parts = {"Adapter_A_FR_RL_R1": labeled_adapter("A"),
             "Adapter_B_FL_RR_R1": labeled_adapter("B"),
             "Floor_Screw_Spacer_1p6_R1": make_spacer()}
    manifest = {"parameters": P, "status": "Digitally checked fit prototype; physical fit pending", "parts": {}}
    for name, shape in parts.items():
        assert shape.isValid() and len(shape.Solids()) == 1, name
        printed = for_print(shape, name.startswith("Adapter"))
        cq.exporters.export(shape, str(HERE/(name+".step")))
        cq.exporters.export(printed, str(HERE/(name+".stl")), tolerance=P["mesh_tolerance"],
                            angularTolerance=P["mesh_angular_tolerance"])
        info = report_shape(printed)
        info["sha256_stl"] = hashlib.sha256((HERE/(name+".stl")).read_bytes()).hexdigest()
        info["quantity"] = 4 if "Spacer" in name else 2
        manifest["parts"][name] = info
    tip = P["floor_screw_length"]-P["floor_thickness"]-P["floor_spacer_thickness"]
    manifest["nominal_stack_checks"] = {
        "floor_screw_tip_above_original_floor": tip,
        "nut_top_above_original_floor": P["nut_seat_z"]+P["assumed_nut_thickness"],
        "screw_tip_below_motor_seat": P["plate_thickness"]-tip,
        "block_screw_engagement": P["block_screw_total_length"]-P["plate_thickness"],
        "new_reported_body_ground_clearance": P["reported_ground_clearance"]-P["plate_thickness"],
        "block_to_carrier_gap": P["carrier_underside_above_floor"]-P["block_height"]-P["plate_thickness"],
        "slot_head_outer_ligament": P["xmax"]-P["slide_max"]-P["countersink_diameter"]/2,
        "key_to_countersink_gap": P["endward_offset"]-P["floor_pitch"]/2-P["countersink_diameter"]/2-P["key_end_y"],
    }
    (HERE/"geometry_manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    build()
