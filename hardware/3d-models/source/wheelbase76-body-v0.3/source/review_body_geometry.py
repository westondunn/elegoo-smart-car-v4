#!/usr/bin/env python3
"""Independent mechanical review helpers for the full-body accessory.

Call ``review(parts, body_names, prints)`` with the assembled Component objects.
This module neither changes the design nor assumes native Fusion availability.
"""
from __future__ import annotations

import math
from pathlib import Path
import json
import argparse
import hashlib
import importlib.util
import sys

import cadquery as cq


def bounds(shape):
    b = shape.BoundingBox()
    return [b.xmin, b.ymin, b.zmin, b.xmax, b.ymax, b.zmax]


def bbox_overlap(a, b):
    aa, bb = bounds(a), bounds(b)
    return all(min(aa[i+3], bb[i+3])-max(aa[i], bb[i]) > 1e-5 for i in range(3))


def cylinder(radius, length, start, direction):
    return cq.Solid.makeCylinder(radius, length, cq.Vector(*start), cq.Vector(*direction))


def box_from_bounds(b):
    return cq.Solid.makeBox(b[3]-b[0], b[4]-b[1], b[5]-b[2], cq.Vector(*b[:3]))


def overlap_record(a, b):
    if not bbox_overlap(a.shape, b.shape):
        return None
    common = a.shape.intersect(b.shape)
    volume = common.Volume()
    if volume <= .01:
        return None
    return {'part_a': a.name, 'part_b': b.name, 'intersection_volume_mm3': volume,
            'intersection_bounds_mm': bounds(common),
            'part_b_evidence': getattr(b, 'evidence', 'unspecified')}


def probe_check(name, probe, body, notes):
    collisions = []
    for p in body:
        if not bbox_overlap(probe, p.shape):
            continue
        common = probe.intersect(p.shape)
        volume = common.Volume()
        if volume > .01:
            collisions.append({'body_part': p.name, 'intersection_volume_mm3': volume,
                               'intersection_bounds_mm': bounds(common)})
    return {'name': name, 'probe_bounds_mm': bounds(probe), 'intersections': collisions, 'scope': notes}


def review(parts, body_names, prints):
    """Check exact constructed solids, and explicit nominal hardware probes."""
    body_names = set(body_names)
    body = [p for p in parts if p.name in body_names]
    if not body:
        raise ValueError('No body components selected')
    if len(body) != len(body_names):
        raise ValueError(f'Body names missing from assembly: {body_names - {p.name for p in body}}')
    collisions = []
    seen = set()
    for a in body:
        for b in parts:
            key = tuple(sorted((a.name, b.name)))
            if a.name == b.name or key in seen:
                continue
            seen.add(key)
            found = overlap_record(a, b)
            if found:
                collisions.append(found)

    tires = [p for p in parts if p.name.startswith('Tire_')]
    tire_clearances = []
    for p in body:
        closest = min((p.shape.distance(t.shape), t.name) for t in tires)
        tire_clearances.append({'body_part': p.name, 'nearest_nominal_tire': closest[1],
                                'distance_mm': closest[0]})

    rotating = [p for p in parts if getattr(p, 'group', '') == 'Head_explorer'
                and not p.name.startswith('SG90_')]
    boss = next(p for p in parts if p.name == 'SG90_output_boss_explorer')
    boss_bounds = bounds(boss.shape)
    ax, ay = (boss_bounds[0]+boss_bounds[3])/2, (boss_bounds[1]+boss_bounds[4])/2
    radial, zmin, zmax = 0.0, math.inf, -math.inf
    for p in rotating:
        bb = bounds(p.shape)
        radial = max(radial, *(math.hypot(x-ax, y-ay) for x in [bb[0], bb[3]] for y in [bb[1], bb[4]]))
        zmin, zmax = min(zmin, bb[2]), max(zmax, bb[5])
    swept = cylinder(radial, zmax-zmin, (ax, ay, zmin), (0, 0, 1))
    sweep_results = []
    for p in body:
        v = swept.intersect(p.shape).Volume() if bbox_overlap(swept, p.shape) else 0.0
        sweep_results.append({'body_part': p.name, 'conservative_distance_mm': swept.distance(p.shape),
                              'intersection_volume_mm3': v})

    footprint = []
    for name, data in prints.items():
        shape = data['shape']
        bb = shape.BoundingBox()
        footprint.append({'part': name, 'valid_brep': shape.isValid(), 'solid_count': len(shape.Solids()),
                          'size_xyz_mm': [bb.xlen, bb.ylen, bb.zlen], 'z_min_mm': bb.zmin,
                          'fits_180mm_xy': max(bb.xlen, bb.ylen) <= 180.0001,
                          'fits_180mm_xy_with_4mm_brim': max(bb.xlen, bb.ylen)+8 <= 180.0001})

    by_name = {p.name: p for p in parts}
    probes = []
    for name, radius in [('Battery_charge_port', 5.0), ('Battery_power_switch', 5.0)]:
        p = by_name.get(name)
        if p:
            bb = bounds(p.shape)
            center = ((bb[0]+bb[3])/2, bb[1]-.01, (bb[2]+bb[5])/2)
            probe = cylinder(radius, 40, center, (0, -1, 0))
            probes.append(probe_check(name+'_nominal_rear_access', probe, body,
                'Illustrative straight rear approach, 10mm diameter; physical plug size/angle and finger reach remain unmeasured.'))
    for name, margin in [('UNO_USB_B_connector', 1.0), ('UNO_barrel_connector', 1.0),
                         ('OPTIONAL_Pi4B_USB_stack', 2.0), ('OPTIONAL_Pi4B_Ethernet', 2.0)]:
        p = by_name.get(name)
        if p:
            bb = bounds(p.shape)
            probe = box_from_bounds([bb[3]+.01, bb[1]-margin, bb[2]-margin,
                                     max(85, bb[3]+40), bb[4]+margin, bb[5]+margin])
            probes.append(probe_check(name+'_nominal_right_access', probe, body,
                f'Nominal connector envelope projected to +X with {margin}mm edge allowance; actual connector faces and cables must be checked on rover.'))
    optic = by_name.get('OPTIONAL_ToF_optical_package')
    if optic:
        bb = bounds(optic.shape)
        probe = box_from_bounds([bb[0]-2, -145, bb[2]-2, bb[3]+2, bb[1]-.01, bb[5]+2])
        probes.append(probe_check('rear_ToF_straight_optical_exit', probe, body,
            'Straight rear exit about nominal optical package with 2mm allowance; this is not a calibrated ToF field-of-view proof.'))

    return {
        'review_scope': 'Independent BRep checks against generated source-derived plates and nominal hardware; not physical-fit certification.',
        'active_component_count': len(parts), 'body_component_count': len(body),
        'body_components': [{'name': p.name, 'bounds_mm': bounds(p.shape), 'volume_mm3': p.shape.Volume()} for p in body],
        'positive_volume_intersections': collisions,
        'nominal_wheel_clearances': tire_clearances,
        'head_sweep_bound': {'axis_xy_mm': [ax, ay], 'radius_mm': radial, 'z_range_mm': [zmin, zmax],
                            'scope': 'Full360deg conservative bound of moving rigid head parts; includes +/-90deg. Excludes flexible cable travel and field of view.',
                            'body_clearances': sweep_results},
        'print_checks': footprint,
        'nominal_service_and_sensor_access': probes,
        'limitations': ['Purchased hardware geometry is nominal or estimated.',
                        'Camera and ultrasonic FOV are not established by the supplied CAD.',
                        'Mechanical sweep clearance alone does not prove unobstructed peripheral camera view or acoustic response.',
                        'Arches use nominal wheel diameter and center positions; check tire tolerances and fastener head clearance physically.',
                        'No physical print, thermal test or live wiring/connector installation has been performed.'],
    }


def write_report(report, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2)+'\n')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', type=Path,
                        default=Path(__file__).resolve().parent.parent/'deliverables')
    parser.add_argument('--output', type=Path,
                        default=Path(__file__).resolve().parent/'body_fit_review.json')
    args = parser.parse_args()
    model_dir = args.model_dir.resolve()
    model_path = model_dir/'build_full_body.py'
    reviewed_inputs = [model_path, model_dir/'full_body_parameters.json',
                       model_dir/'body_reference_rover.py', model_dir/'body_reference_parameters.json',
                       model_dir/'body_reference_profiles.json']
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in reviewed_inputs}
    sys.path.insert(0, str(model_dir))
    spec = importlib.util.spec_from_file_location('build_full_body', model_path)
    model = importlib.util.module_from_spec(spec)
    sys.modules['build_full_body'] = model
    spec.loader.exec_module(model)
    model.build()
    report = review(model.parts, model.body_names, model.prints)
    final_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in reviewed_inputs}
    if hashes != final_hashes:
        raise RuntimeError('Model inputs changed during review; repeat against a stable source snapshot')
    report['reviewed_build_sha256'] = hashes[model_path.name]
    report['reviewed_input_sha256'] = hashes
    report['reviewed_full_body_parameters'] = model.P
    report['passed'] = not report['positive_volume_intersections'] \
        and all(not p['intersections'] for p in report['nominal_service_and_sensor_access']) \
        and all(p['intersection_volume_mm3'] <= .01 for p in report['head_sweep_bound']['body_clearances']) \
        and all(p['valid_brep'] and p['solid_count'] == 1 and p['fits_180mm_xy_with_4mm_brim']
                for p in report['print_checks'])
    write_report(report, args.output)
    print(json.dumps({'passed': report['passed'], 'report': str(args.output),
                      'body_intersections': len(report['positive_volume_intersections']),
                      'nominal_access_probe_failures': sum(bool(p['intersections']) for p in report['nominal_service_and_sensor_access']),
                      'smallest_tire_clearance_mm': min(p['distance_mm'] for p in report['nominal_wheel_clearances']),
                      'smallest_rigid_head_sweep_clearance_mm': min(p['conservative_distance_mm'] for p in report['head_sweep_bound']['body_clearances'])}, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
