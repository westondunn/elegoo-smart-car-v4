#!/usr/bin/env python3
"""Six-panel full body for the ELEGOO V4 explorer reference assembly.

Uses the delivered rover reference geometry without changing the original files.
Build: python build_full_body.py --output rebuilt [--render]
All dimensions are millimeters. No printer, network, or firmware action occurs.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import cadquery as cq
import numpy as np

import body_reference_rover as base
from rover_3mf import write_3mf, weld_mesh, mesh_stats

HERE = Path(__file__).resolve().parent
P = json.loads((HERE / 'full_body_parameters.json').read_text())
BODY_BLUE = '#365D78'
BODY_GRAY = '#647887'
ROOF_GRAY = '#A9B7C1'
ORANGE = '#E78939'
SILVER = '#ADB8C3'
parts = []
prints = {}
body_names = []
interfaces = []

box = base.box
cyl = base.cyl
slot = base.slot


@dataclass
class Component:
    name: str
    shape: cq.Shape
    group: str
    color: str
    evidence: str = 'new_design'
    variant: str = 'full_body'
    notes: str = ''


def bounds(shape):
    bb = shape.BoundingBox()
    return [bb.xmin, bb.ymin, bb.zmin, bb.xmax, bb.ymax, bb.zmax]


def add(name, shape, group='PLA_body', color=BODY_BLUE, evidence='new_design', notes=''):
    shape = shape.clean()
    if not shape.isValid() or len(shape.Solids()) != 1:
        raise ValueError(f'{name}: expected one valid solid')
    parts.append(Component(name, shape, group, color, evidence, notes=notes))
    return shape


def printable(name, installed, *, rotation=None, quantity=1, color=BODY_BLUE,
              notes='', include=True, group='PLA_body'):
    installed = installed.clean()
    if not installed.isValid() or len(installed.Solids()) != 1:
        raise ValueError(f'{name}: invalid printable body')
    oriented = installed
    if rotation:
        axis, degrees = rotation
        oriented = oriented.rotate((0, 0, 0), axis, degrees)
    bb = oriented.BoundingBox()
    oriented = oriented.translate((-bb.xmin, -bb.ymin, -bb.zmin))
    bb = oriented.BoundingBox()
    if bb.xlen > 172.0 + 1e-5 or bb.ylen > 172.0 + 1e-5:
        raise ValueError(f'{name}: too large for the 180 mm bed and margin')
    prints[name] = {'shape': oriented, 'design_shape': installed,
                   'quantity': quantity, 'color': color, 'notes': notes}
    if include:
        add(name, installed, group=group, color=color, notes=notes)
        body_names.append(name)
    return installed


def window_x(length_y, height_z, y, z, radius=1.5):
    q = cq.Workplane('XY').box(200, length_y, height_z, centered=(True, True, False))
    if radius:
        q = q.edges('|X').fillet(radius)
    return q.val().translate((0, y, z))


def window_y(width_x, height_z, x, z, radius=1.5):
    q = cq.Workplane('XY').box(width_x, 320, height_z, centered=(True, True, False))
    if radius:
        q = q.edges('|Y').fillet(radius)
    return q.val().translate((x, 0, z))


def hole_y(x, z):
    return cyl(P['m3_clearance']/2, 320, x, -160, z, axis=(0, 1, 0))


def tire_clearance_cutters():
    return [cyl(P['wheel_arch_radius'], 220, -110, y,
                base.P['reference_wheel_diameter']/2, axis=(1, 0, 0))
            for y in (base.P['reference_front_axle_y'], base.P['reference_rear_axle_y'])]


def bolt_y(x, y, z, length, inside_direction):
    return base.bolt_z(0, 0, 0, length).rotate((0, 0, 0), (1, 0, 0),
                                             90*inside_direction).translate((x, y, z))


def nut_y(x, y, z, inside_direction):
    return base.nut_z(0, 0, 0).rotate((0, 0, 0), (1, 0, 0),
                                     -90*inside_direction).translate((x, y, z))


def side_panels():
    half = P['outer_half_width']; wall = P['wall_thickness']
    rear = P['cabin_rear_y']; front = P['cabin_front_y']
    low = P['skirt_bottom_z']; high = P['roof_underside_z']
    clearance = P['panel_seam_clearance']; mx = P['roof_mount_x']
    rear_tab_outer = rear + wall
    front_tab_outer = front - wall
    for side, label in [(-1, 'left'), (1, 'right')]:
        panel = box(wall, front-rear, high-low,
                    side*(half-wall/2), (front+rear)/2, low)
        for tool in tire_clearance_cutters():
            panel = panel.cut(tool)
        # Port access and ventilation do not serve as structural interfaces.
        if side == 1:
            panel = panel.cut(window_x(74, 24, -57, 116, 3))
            panel = panel.cut(window_x(56, 27, 9, 71, 3))
        else:
            for y in (-82, -70, -58, -46, -34):
                panel = panel.cut(window_x(6, 22, y, 116, 2))
            for y in (-11, 1, 13, 25):
                panel = panel.cut(window_x(6, 19, y, 75, 2))
            panel = panel.cut(window_x(24, 16, -103, 75, 2))
        for y in (-10, 0, 10):
            panel = panel.cut(window_x(4.5, 25, y, 29, 1.5))
        # Retain the original side-guard/deck fastening locations and stack.
        for y in (-62.0, -28.0):
            tab = box(20, 12, 3.2, side*60.0, y, base.Z_DECK-3.2)
            tab = tab.cut(cyl(P['m3_clearance']/2, 8, side*57, y, base.Z_DECK-5))
            panel = panel.fuse(tab)
            interfaces.append({'type': 'deck', 'side': label, 'center_xy': [side*57, y],
                               'tab_z': [base.Z_DECK-3.2, base.Z_DECK],
                               'screw': 'retained M3x10 + M3 nut'})
        # Local corner tabs: end-panel screws run along Y through the two parts.
        for end, cy in [('rear', rear_tab_outer+2), ('front', front_tab_outer-2)]:
            for z in P['end_panel_mount_z']:
                tab = box(18, 4, 10, side*mx, cy, z-5)
                tab = tab.cut(hole_y(side*mx, z))
                panel = panel.fuse(tab)
        # Slide-in hex-nut channels retain roof nuts vertically when the lid is removed.
        for y in P['roof_mount_y']:
            tab = box(18, 12, 6, side*mx, y, high-6)
            tab = tab.cut(cyl(P['m3_clearance']/2, 10, side*mx, y, high-8))
            pocket = cq.Workplane('XY').polygon(6, 6.8).extrude(2.8).val().translate((side*mx, y, high-4.2))
            entry = box(10, 5.9, 2.8, side*(mx-5), y, high-4.2)
            tab = tab.cut(pocket.fuse(entry))
            panel = panel.fuse(tab)
        printable(f'body_{1 if side == -1 else 2:02d}_{label}_side', panel, rotation=((0, 1, 0), 90*side),
                  notes='Print broad exterior face down. Replaces the original short side guard. '
                        'Wheel arches use a nominal 4 mm radial allowance; physical tire fit is unverified.')


def end_panels():
    half = P['outer_half_width']; wall = P['wall_thickness']
    rear = P['cabin_rear_y']; front = P['cabin_front_y']
    low = P['skirt_bottom_z']; high = P['roof_underside_z']
    gap = P['panel_seam_clearance']; mx = P['roof_mount_x']
    width = 2*(half-wall-gap)
    back = box(width, wall, high-low, 0, rear+wall/2, low)
    back = back.cut(window_y(82, 27, 0, 68, 3))
    back = back.cut(window_y(64, 30, 0, 110, 3))
    for z in (30, 40, 50, 60):
        back = back.cut(window_y(90, 4, 0, z, 1.2))
    front_low = base.Z_TOP+1.5
    bulkhead = box(width, wall, high-front_low, 0, front-wall/2, front_low)
    bulkhead = bulkhead.cut(window_y(42, 32, 8, 77, 3))
    for x in (-47, -38, -29, 40, 48):
        bulkhead = bulkhead.cut(window_y(4.5, 34, x, 88, 1.5))
    for side in (-1, 1):
        for z in P['end_panel_mount_z']:
            back = back.cut(hole_y(side*mx, z))
            bulkhead = bulkhead.cut(hole_y(side*mx, z))
    printable('body_03_rear_panel', back, rotation=((1, 0, 0), 90), color=BODY_GRAY,
              notes='Battery/switch opening and broad rear-sensor aperture. Four M3x12 screws/nuts. '
                    'Remove the rear panel and roof for battery service; wiring is not modeled.')
    printable('body_04_front_bulkhead', bulkhead, rotation=((1, 0, 0), -90), color=BODY_GRAY,
              notes='Cabin front behind the camera/sonar head. Central cable relief. '
                    'Four M3x12 screws/nuts; lower edge clears the source top plate by 1.5 mm.')
    for end, face_y, inside, tab_inner in [
        ('rear', rear, 1, rear+wall+4),
        ('front', front, -1, front-wall-4),
    ]:
        for side in (-1, 1):
            for j, z in enumerate(P['end_panel_mount_z'], 1):
                key = f'{end}_{side}_{j}'
                add('Body_end_M3x12_'+key, bolt_y(side*mx, face_y, z, 12, inside),
                    group='Body_fasteners_reference', color=SILVER, evidence='proposed_hardware')
                add('Body_end_M3_nut_'+key, nut_y(side*mx, tab_inner, z, inside),
                    group='Body_fasteners_reference', color=SILVER, evidence='proposed_hardware')
                interfaces.append({'type': end+'_panel', 'center_xyz': [side*mx, face_y, z],
                                   'axis': 'Y', 'wall_mm': wall, 'clamped_gap_mm': 0,
                                   'perimeter_seam_mm': gap, 'tab_mm': 4,
                                   'screw': 'M3x12', 'nut': 'M3'})


def roof_panel():
    half = P['outer_half_width']; rear = P['cabin_rear_y']; front = P['cabin_front_y']
    z = P['roof_underside_z']; thick = P['roof_thickness']; mx = P['roof_mount_x']
    roof = box(2*half, front-rear, thick, 0, (front+rear)/2, z, radius=1.0)
    # Vents above the optional computer. Mounting land stays solid around edges.
    for y in (-88, -79, -70, -61, -52, -43, -34, -25):
        roof = roof.cut(slot(84, 4.5, thick+2, 0, y, z-1))
    # Generic 40 x 20 mm mount grid for a future lightweight payload adapter.
    for x in (-20, 20):
        for y in (-5, 15):
            roof = roof.cut(cyl(P['m3_clearance']/2, thick+2, x, y, z-1))
    for side in (-1, 1):
        for j, y in enumerate(P['roof_mount_y'], 1):
            roof = roof.cut(cyl(P['m3_clearance']/2, thick+2, side*mx, y, z-1))
            add(f'Body_roof_M3x10_{side}_{j}', base.bolt_z(side*mx, y, z+thick, 10),
                group='Body_fasteners_reference', color=SILVER, evidence='proposed_hardware')
            add(f'Body_roof_M3_nut_{side}_{j}', base.nut_z(side*mx, y, z-3.8),
                group='Body_fasteners_reference', color=SILVER, evidence='proposed_hardware')
            interfaces.append({'type': 'roof', 'center_xy': [side*mx, y], 'axis': 'Z',
                               'roof_mm': thick, 'tab_mm': 6, 'screw': 'M3x10', 'nut': 'M3',
                               'nut_pocket_z': [z-4.2, z-1.4], 'nut_slot_width_mm': 5.9,
                               'nut_retention': 'Slide nut outward from cabin interior; pocket restrains rotation and vertical loss.'})
    printable('body_05_removable_roof', roof, rotation=((0, 1, 0), 180), color=ROOF_GRAY,
              notes='Print outside face down. Four M3x10 screws into slide-in retained M3 nuts; open ventilation slots. '
                    'The 40x20 mm hole grid is generic, not a sensor-specific mount. '
                    'No gasket, weather seal or thermal qualification.')


def nose_cowl():
    half = P['outer_half_width']; wall = P['wall_thickness']; low = P['skirt_bottom_z']
    rear = P['nose_rear_y']; front = P['nose_front_y']
    under = base.Z_TOP+8.0; thick = P['nose_roof_thickness']
    head_xy = (-0.900185, 81.189175)
    cowl = box(2*half, front-rear, thick, 0, (front+rear)/2, under, radius=1)
    # Low side fenders extend down around the front tires; they remain below sonar.
    for side in (-1, 1):
        cheek = box(wall, front-rear, under-low, side*(half-wall/2), (front+rear)/2, low)
        cowl = cowl.fuse(cheek)
    face = box(2*half, wall, under-low, 0, front-wall/2, low)
    # Open-bottom service passages clear both the original guard arms and floor carriers.
    for side in (-1, 1):
        face = face.cut(box(49, wall+4, under-low+2, side*37.0, front-wall/2, low-1))
    cowl = cowl.fuse(face)
    for tool in tire_clearance_cutters():
        cowl = cowl.cut(tool)
    cowl = cowl.cut(cyl(P['head_opening_radius'], 180, *head_xy, 0))
    # Open rounded access notches for the four existing floor-carrier screw heads.
    # Closed holes here would leave fragile slivers at the nearby front edge.
    for x in (-36, -24, 24, 36):
        tool = cyl(4, thick+2, x, 117, under-1)
        tool = tool.fuse(box(8, 10, thick+2, x, 122, under-1))
        cowl = cowl.cut(tool)
    front_mounts = [m['top_center_target_xy'] for m in base.SOURCE['matched_3_4mm_mounting_holes']
                    if m['top_center_target_xy'][1] > 70]
    for i, (x, y) in enumerate(front_mounts, 1):
        cowl = cowl.cut(cyl(P['m3_clearance']/2, thick+2, x, y, under-1))
        add(f'Body_nose_M3x20_{i}', base.bolt_z(x, y, under+thick, 20),
            group='Body_fasteners_reference', color=SILVER, evidence='proposed_hardware',
            notes='Reuses the guard/pillar M3x20 screw raised by the bonnet thickness; '
                  'nominal pillar engagement 5.1 mm at default dimensions. Check real thread depth.')
        interfaces.append({'type': 'nose_to_front_guard', 'center_xy': [x, y],
                           'screw': 'retained M3x20 moved above cowl',
                           'nominal_pillar_engagement_mm': 20-(4.5+4+4+thick)})
    printable('body_06_front_cowl', cowl, rotation=((0, 1, 0), 180), color=BODY_BLUE,
              notes='Print the bonnet top face on the bed so skirts grow upward. '
                    'R31 head opening; front passages clear floor carriers/guard arms. '
                    'Four open 8 mm notches clear existing floor-carrier screw heads. '
                    'Sits on existing front guard arms and reuses two M3x20 screws. '
                    'Existing 4 mm guard shims are retained.')


def joint_samples():
    # Cut real geometry around one rear joint; coupons are not installed in the rover.
    side = next(p.shape for p in parts if p.name == 'body_02_right_side')
    rear = next(p.shape for p in parts if p.name == 'body_03_rear_panel')
    sample_side = side.intersect(box(22, 24, 22, 61, -108, 122))
    sample_rear = rear.intersect(box(18, 8, 22, 61, -120, 122))
    printable('body_00_joint_side_sample', sample_side, rotation=((0, 1, 0), 90),
              include=False, color=ORANGE,
              notes='Small actual corner-tab sample; pair with rear-panel sample and one M3x12/nut. '
                    'Also includes the real slide-in roof-nut pocket for fit testing. '
                    'Checks printed hole/joint fit, not mounting coordinates or tire clearance.')
    printable('body_00_joint_rear_sample', sample_rear, rotation=((1, 0, 0), 90),
              include=False, color=ORANGE,
              notes='Pair with side sample; same 2.4 mm panel, 0.5 mm nominal seam and M3 hole as full body.')


def build():
    parts.clear(); prints.clear(); body_names.clear(); interfaces.clear()
    base.build()
    replaced = {'03_side_guard_left', '04_side_guard_right',
                'Guard_M3x20_screw_1', 'Guard_M3x20_screw_2'}
    for p in base.parts:
        if p.variant in ('both', 'explorer') and p.name not in replaced:
            parts.append(Component(p.name, p.shape, p.group, p.color, p.evidence,
                                   notes=p.notes))
    side_panels(); end_panels(); roof_panel(); nose_cowl(); joint_samples()
    return parts, prints


def tess(shape):
    vv, ff = shape.tessellate(0.045, 0.12)
    v = np.array([p.toTuple() for p in vv], float)
    f = np.array(ff, np.int64)
    v, f, _ = weld_mesh(v, f, tolerance=1e-6)
    return v, f


def assembly(selected, root):
    a = cq.Assembly(name=root)
    groups = {}
    for p in selected:
        if p.group not in groups:
            groups[p.group] = cq.Assembly(name=p.group)
        groups[p.group].add(p.shape, name=p.name, color=base.color(p.color))
    for name, group in groups.items():
        a.add(group, name=name)
    all_shapes = cq.Compound.makeCompound([p.shape for p in selected])
    return a, {'solid_count': sum(len(p.shape.Solids()) for p in selected),
               'volume_mm3': sum(p.shape.Volume() for p in selected),
               'bbox_mm': bounds(all_shapes),
               'named_hierarchy': {'root': root, 'groups': list(groups),
                   'components': [p.name for p in selected],
                   'edges': [[root, g] for g in groups] + [[p.group, p.name] for p in selected]}}


def export_and_manifest(output, export=True):
    output.mkdir(parents=True, exist_ok=True)
    manifest = {
        'version': P['version'], 'units': 'millimeter', 'bed_mm': P['bed_mm'],
        'coordinate_convention': 'Original explorer coordinates: +Y front, +Z up; nominal ground Z=0.',
        'base_geometry': 'Source-derived chassis; nominal/estimated purchased hardware; see component evidence.',
        'replaces': ['03_side_guard_left', '04_side_guard_right'],
        'retains': 'Original deck, four deck spacers, front guard, guard shims, optional trays/carriers.',
        'body_components': body_names.copy(), 'interfaces': interfaces.copy(),
        'limitations': [
            'Physical fit and printer/application-level import have not been tested.',
            'Wheel/connector/camera dimensions are nominal or estimated hardware envelopes.',
            'Exposed sensor head has mechanical sweep clearance; peripheral optical/acoustic fields need physical checks.',
            'Open vents/seams/underbody are not weather sealed. No thermal, impact, or payload capacity certification.',
            'Roof clearance excludes unmodeled coolers, HATs, connectors and cable bends.',
        ],
        'components': [], 'printable_parts': [], 'print_packs': [], 'step_exports': [],
    }
    for p in parts:
        manifest['components'].append({'name': p.name, 'group': p.group, 'evidence': p.evidence,
                                      'notes': p.notes, 'bbox_mm': bounds(p.shape),
                                      'volume_mm3': p.shape.Volume(), 'brep_valid': p.shape.isValid()})
    for name, item in prints.items():
        bb = item['shape'].BoundingBox()
        v, f = tess(item['shape'])
        manifest['printable_parts'].append({'name': name, 'quantity': item['quantity'],
             'part_file': name+'.stl', 'bbox_mm': [bb.xlen, bb.ylen, bb.zlen],
             'solid_volume_mm3': item['shape'].Volume(), 'notes': item['notes'],
             'brep_valid': item['shape'].isValid(), 'mesh': mesh_stats(v, f)})
        if export:
            cq.exporters.export(item['shape'], str(output/(name+'.stl')), tolerance=.04, angularTolerance=.12)

    selected_body = [p for p in parts if p.name in body_names]
    flat = [Component(name, item['shape'].translate(((i%3)*190, (i//3)*190, 0)),
                      'Print_designs', item['color']) for i, (name, item) in enumerate(prints.items())]
    for name, root, selected in [
        ('elegoo_v4_full_body_assembly.step', 'ELEGOO_V4_full_body_mm', parts),
        ('elegoo_v4_body_shell_only.step', 'ELEGOO_V4_body_shell_mm', selected_body),
        ('full_body_printable_parts.step', 'ELEGOO_V4_body_print_designs_mm', flat),
    ]:
        a, expected = assembly(selected, root)
        expected['file'] = name
        manifest['step_exports'].append(expected)
        if export:
            print('Export', name, flush=True)
            a.export(str(output/name), exportType='STEP', mode='default')

    packs = {
        'body_00_joint_check.3mf': ['body_00_joint_side_sample', 'body_00_joint_rear_sample'],
        'body_01_left_side.3mf': ['body_01_left_side'],
        'body_02_right_side.3mf': ['body_02_right_side'],
        'body_03_rear_panel.3mf': ['body_03_rear_panel'],
        'body_04_front_bulkhead.3mf': ['body_04_front_bulkhead'],
        'body_05_roof.3mf': ['body_05_removable_roof'],
        'body_06_front_cowl.3mf': ['body_06_front_cowl'],
    }
    mesh_reports = {}
    for filename, names in packs.items():
        manifest['print_packs'].append({'file': filename,
            'parts': {n: prints[n]['quantity'] for n in names}, 'bed_mm': P['bed_mm'],
            'edge_margin_mm': 4, 'minimum_spacing_mm': 5})
        if not export:
            continue
        objects = []; px = 4; py = 4; row_h = 0
        for name in names:
            item = prints[name]; bb = item['shape'].BoundingBox()
            for n in range(item['quantity']):
                if px+bb.xlen > P['bed_mm'][0]-4:
                    px = 4; py += row_h+5; row_h = 0
                if py+bb.ylen > P['bed_mm'][1]-4:
                    raise ValueError('Pack exceeds bed: '+filename)
                v, f = tess(item['shape'])
                transform = np.eye(4); transform[:3, 3] = [px, py, 0]
                objects.append({'name': name if item['quantity']==1 else f'{name}_{n+1}',
                                'vertices': v, 'faces': f, 'color': item['color'], 'transform': transform})
                px += bb.xlen+5; row_h = max(row_h, bb.ylen)
        print('Export', filename, flush=True)
        mesh_reports[filename] = write_3mf(output/filename, objects,
            title='ELEGOO V4 full body '+filename,
            description='PLA body geometry only. Millimeters. Select the actual printer/filament before slicing.')
    manifest['new_body_solid_volume_mm3'] = sum(p.shape.Volume() for p in selected_body)
    manifest['source_files_sha256'] = {n: hashlib.sha256((HERE/n).read_bytes()).hexdigest() for n in
        ['build_full_body.py', 'full_body_parameters.json', 'body_reference_rover.py',
         'body_reference_parameters.json', 'body_reference_profiles.json']}
    (output/'body_manifest.json').write_text(json.dumps(manifest, indent=2))
    if export:
        (output/'body_mesh_export_validation.json').write_text(json.dumps(mesh_reports, indent=2))
    return manifest


def render(output):
    from render_full_body import render_views
    offsets = {
        'body_01_left_side': (-60, 0, 5),
        'body_02_right_side': (60, 0, 5),
        'body_03_rear_panel': (0, -64, 6),
        'body_04_front_bulkhead': (0, 32, 35),
        'body_05_removable_roof': (0, 0, 65),
        'body_06_front_cowl': (0, 52, 14),
    }
    return render_views(parts, output, body_names=body_names,
                        explode_offsets=offsets, print_parts=prints)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE)
    parser.add_argument('--manifest-only', action='store_true')
    parser.add_argument('--render', action='store_true')
    args = parser.parse_args()
    build()
    print(f'Built {len(parts)} components; {len(body_names)} body panels; {len(prints)} print designs', flush=True)
    export_and_manifest(args.output, export=not args.manifest_only)
    if args.render:
        render(args.output)


if __name__ == '__main__':
    main()
