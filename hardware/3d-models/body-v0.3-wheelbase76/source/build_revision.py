#!/usr/bin/env python3
"""Build the 76.2 mm-wheelbase body revision, preserving validated interfaces.

  python source/build_revision.py --output rebuilt
All dimensions in mm. No flashing, network, slicer or printer operation.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys

import cadquery as cq
import numpy as np
import trimesh
import build_full_body as body
import review_body_geometry as review
from rover_3mf import write_3mf, validate_3mf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BODY_CHANGED = {'body_01_left_side','body_02_right_side',
                'body_04_front_bulkhead','body_06_front_cowl'}
DRIVE_PREFIXES = ('Tire_','Wheel_hub_','Wheel_M2_fastener_', 'TT_gearbox_',
                  'DC_motor_can_','Drive_shaft_','Aluminum_motor_block_',
                  'Motor_through_bolt_')


def bounds(s):
    b = s.BoundingBox()
    return [b.xmin,b.ymin,b.zmin,b.xmax,b.ymax,b.zmax]


def color_hex(c):
    return '#' + ''.join(f'{round(v*255):02X}' for v in c.toTuple()[:3])


def load_reference(path):
    a = cq.Assembly.importStep(str(path))
    return {name.split('/')[-1]:(shape.moved(loc), color)
            for shape,name,loc,color in a}


def make_gauges():
    """Low-material templates using the same deck-tab mounting stack as sides.

    The underside of the rail is the actual Z=74 wheel-bay ceiling.
    Two V notches are nominal axle-center markers, not measured datums.
    """
    result={}
    for side,label in [(-1,'left'),(1,'right')]:
        x=side*69.8
        q=body.box(2.4,166,6,x,-7,74)  # rear -90 / front +76
        # Rear edge checks the bay's -90mm rear stop. No center separator.
        q=q.fuse(body.box(2.4,6,20,x,-87,54))
        for y in [-62.0,-28.0]:
            q=q.fuse(body.box(2.4,8,body.base.Z_DECK-80,x,y,80))
            tab=body.box(20,12,3.2,side*60,y,body.base.Z_DECK-3.2)
            tab=tab.cut(body.cyl(1.75,8,side*57,y,body.base.Z_DECK-5))
            q=q.fuse(tab)
        # Engraved triangular tick notches in top of rail.
        for y in [body.base.P['reference_rear_axle_y'],body.base.P['reference_front_axle_y']]:
            tool=(cq.Workplane('YZ').polyline([(y-1.3,80.1),(y+1.3,80.1),(y,78.7)])
                  .close().extrude(240,both=True).val())
            q=q.cut(tool)
        q=q.clean()
        if not q.isValid() or len(q.Solids()) != 1:
            raise RuntimeError('Invalid fit gauge: '+label)
        rotated=q.rotate((0,0,0),(0,1,0),90*side)
        b=rotated.BoundingBox()
        rotated=rotated.translate((-b.xmin,-b.ymin,-b.zmin))
        result['wheel_bay_fit_gauge_'+label] = {
            'shape':rotated, 'design_shape':q, 'color':'#EFA83E','quantity':1,
            'notes':'Fit template only; remove before powered operation. Same M3 deck tabs. Rail bottom matches bay Z74; V marks are inferred axle positions.'}
    return result


def build(reference=None):
    body.build()
    proposed={p.name:p for p in body.parts}
    reference = reference or ROOT/'reference'/'previous_rover_roof_snap_v2.step'
    previous=load_reference(reference)
    parts=[]; changed=[]; preserved=[]
    for n,(s,c) in previous.items():
        p=proposed.get(n)
        replace=n in BODY_CHANGED or n.startswith(DRIVE_PREFIXES)
        if replace:
            if p is None: raise RuntimeError('Missing replacement '+n)
            parts.append(p); changed.append(n)
        else:
            parts.append(body.Component(n,s,p.group if p else 'Battery_snap_v2_UNCHANGED',
                         color_hex(c) if c else '#83929B',
                         p.evidence if p else 'preserved_previous_snapshot',
                         notes='Preserved directly from prior STEP snapshot. '+(p.notes if p else '')))
            preserved.append(n)
    if len(parts)!=len(previous): raise RuntimeError('Assembly component lost')
    printables={n:body.prints[n] for n in BODY_CHANGED}
    printables.update(make_gauges())
    return parts, printables, previous, {'changed_names':sorted(changed),
                                       'preserved_names':sorted(preserved)}


def export_step(parts,path,name):
    a,meta=body.assembly(parts,name)
    a.export(str(path),exportType='STEP',mode='default')
    # Verify installed poses and labels on import, not only a flat compound.
    imported=load_reference(path)
    expected={p.name:p.shape for p in parts}
    if set(imported)!=set(expected):raise RuntimeError('STEP component naming mismatch: '+path.name)
    for n,s in expected.items():
        got=imported[n][0]
        if not got.isValid(): raise RuntimeError('STEP invalid: '+n)
        if abs(got.Volume()-s.Volume())>max(1e-4,1e-7*s.Volume()):raise RuntimeError('STEP volume: '+n)
        if not np.allclose(bounds(got),bounds(s),atol=2e-5,rtol=0):raise RuntimeError('STEP bounds: '+n)
    meta['filename']=path.name;meta['roundtrip_names_bounds_volume_validity']=True
    return meta


def export_prints(printables,out):
    reports=[]
    for n,item in sorted(printables.items()):
        s=item['shape'];b=s.BoundingBox()
        if max(b.xlen,b.ylen)+8>180.0001:raise RuntimeError('Print area '+n)
        stl=out/'print'/f'{n}.stl'
        cq.exporters.export(s,str(stl),tolerance=.03,angularTolerance=.10)
        mesh=trimesh.load_mesh(stl,process=True)
        report={'name':n,'size_xyz_mm':[b.xlen,b.ylen,b.zlen],
                'solid_volume_mm3':s.Volume(),'watertight':bool(mesh.is_watertight),
                'consistent_winding':bool(mesh.is_winding_consistent),
                'connected_meshes':len(mesh.split(only_watertight=False)),
                'volume_error_ratio':abs(mesh.volume-s.Volume())/s.Volume(),
                'bed_180_with_4mm_brim':True}
        if not report['watertight'] or not report['consistent_winding'] or report['connected_meshes']!=1:
            raise RuntimeError('Mesh topology '+n)
        if report['volume_error_ratio']>.001:raise RuntimeError('Mesh volume '+n)
        step=out/'cad'/f'{n}.step'
        cq.exporters.export(s,str(step))
        got=cq.importers.importStep(str(step)).val()
        if not got.isValid() or abs(got.Volume()-s.Volume())>1e-4:raise RuntimeError('Part STEP '+n)
        reports.append(report)
    packs={'00_wheel_bay_fit_checks.3mf':['wheel_bay_fit_gauge_left','wheel_bay_fit_gauge_right'],
           '01_left_side_v3.3mf':['body_01_left_side'],
           '02_right_side_v3.3mf':['body_02_right_side'],
           '04_front_bulkhead_v3.3mf':['body_04_front_bulkhead'],
           '06_front_cowl_v3.3mf':['body_06_front_cowl']}
    pack_reports=[]
    for filename,names in packs.items():
        objects=[];px=4.0
        for n in names:
            v,f=body.tess(printables[n]['shape'])
            transform=np.eye(4);transform[:3,3]=[px,4,0]
            objects.append({'name':n,'vertices':v,'faces':f,
                            'transform':transform,'color':printables[n]['color']})
            px+=printables[n]['shape'].BoundingBox().xlen+5
        path=out/'print'/filename
        own=write_3mf(path,objects,title='ELEGOO V4 measured-wheelbase body v0.3',
               description='Millimeters, geometry only. Select printer and PLA profile; no G-code.')
        validate_3mf(path)
        scene=trimesh.load(path,force='scene')
        if len(scene.geometry)!=len(names):raise RuntimeError('3MF independent object count')
        if not all(g.is_watertight for g in scene.geometry.values()):raise RuntimeError('3MF open mesh')
        sizes=scene.bounds[1]-scene.bounds[0]
        if max(scene.bounds[1,:2])>176.001 or min(scene.bounds[0,:2])<3.999 or abs(scene.bounds[0,2])>1e-5:
            raise RuntimeError('3MF placement '+filename)
        pack_reports.append({'filename':filename,'objects':names,'independent_trimesh_read':True,
                             'bounds_mm':scene.bounds.tolist(),'core_validation':True})
    return reports,pack_reports


def tolerance_envelope(parts):
    # Conservative swept cylinders: +3mm radius (diameter/edge uncertainty),
    # +/-8mm pair placement in Y, +/-2mm axle height, and +3mm per X face.
    # The entire rectangular YZ envelope is checked, so all intermediate
    # translations are included, not just a small set of sampled poses.
    r=body.base.P['reference_wheel_diameter']/2
    w=body.base.P['reference_wheel_width']
    xm=body.base.P['reference_wheel_center_x']
    probes=[]
    for side in [-1,1]:
        for label,cy in [('front',body.base.P['reference_front_axle_y']),('rear',body.base.P['reference_rear_axle_y'])]:
            # Conservative bounding box includes the full swept cylinder.
            rr=r+3
            probe=body.box(w+6,2*(rr+8),2*(rr+2),side*xm,cy,r-rr-2)
            probes.append((f'{side}_{label}',probe))
    selected=[p for p in parts if p.name in body.body_names]
    entries=[]
    for n,q in probes:
        for p in selected:
            ov=q.intersect(p.shape).Volume() if review.bbox_overlap(q,p.shape) else 0
            gap=q.distance(p.shape)
            entries.append({'envelope':n,'body':p.name,'intersection_volume_mm3':ov,'gap_mm':gap})
    if any(e['intersection_volume_mm3']>.01 or e['gap_mm']<1 for e in entries):
        raise RuntimeError('Conservative body envelope check failed: '+str(entries))
    return {'scope':'Body panels versus conservative BOX bounding all tire translations in declared allowances. Not actual measured tolerances.',
            'extra_radius_mm':3,'pair_translation_y_mm':8,'axle_height_z_mm':2,'extra_each_x_face_mm':3,
            'minimum_gap_mm':min(e['gap_mm'] for e in entries),'checks':entries}


def interface_report(parts,previous,change):
    now={p.name:p.shape for p in parts}
    result=[]
    # Exact preserved shapes, plus local blocks containing each changed-part interface.
    for n in ['01_slotted_deck','10_optional_pi4_tray','body_05_removable_roof','body_03_rear_panel',
              'PRINT_roof_tray_v2','PRINT_slotted_snap_lid_v2']+['Deck_spacer_'+str(i) for i in range(1,5)]:
        old=previous[n][0];new=now[n]
        # Same original BRep reference reused, not rebuilt with guessed dimensions.
        delta=abs(old.Volume()-new.Volume())
        if delta>1e-5 or not np.allclose(bounds(old),bounds(new),atol=1e-7):raise RuntimeError('Preserved part '+n)
        result.append({'part':n,'action':'unchanged snapshot geometry and installed position','volume_delta':delta})
    interfaces=[]
    for side,label in [(-1,'left'),(1,'right')]:
        n='body_01_left_side' if side<0 else 'body_02_right_side'
        probes=[]
        for y in [-62,-28]:probes.append(('deck',body.box(25,14,6,side*59,y,body.base.Z_DECK-4)))
        for y in [-104,30]:probes.append(('roof',body.box(22,16,8,side*61,y,136.5)))
        for y in [-115.6,41.6]:
            for z in [85,132]:probes.append(('end_panel',body.box(23,10,12,side*61,y,z-6)))
        for typ,q in probes:
            a=previous[n][0].intersect(q);b=now[n].intersect(q)
            delta=a.cut(b).Volume()+b.cut(a).Volume()
            if delta>.001:raise RuntimeError('Interface changed '+n+' '+typ+' '+str(delta))
            interfaces.append({'part':n,'interface':typ,'symmetric_difference_mm3':delta})
    return {'preserved_components':len(change['preserved_names']),'preserved_checks':result,
            'changed_panel_mount_interfaces':interfaces}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,default=ROOT)
    ap.add_argument('--reference',type=Path,default=ROOT/'reference'/'previous_rover_roof_snap_v2.step')
    args=ap.parse_args();out=args.output
    for d in ['cad','print','verification','preview']:(out/d).mkdir(parents=True,exist_ok=True)
    parts,printables,previous,changes=build(args.reference)
    print('Built corrected assembly',len(parts),'components;',len(printables),'printable designs',flush=True)
    interfaces=interface_report(parts,previous,changes)
    fit=review.review(parts,body.body_names,printables)
    if fit['positive_volume_intersections']:raise RuntimeError('Body intersections '+str(fit['positive_volume_intersections']))
    if any(x['intersections'] for x in fit['nominal_service_and_sensor_access']):raise RuntimeError('Service clearance')
    if any(x['intersection_volume_mm3']>.01 for x in fit['head_sweep_bound']['body_clearances']):raise RuntimeError('Head sweep')
    envelope=tolerance_envelope(parts)
    # Check fit templates against the open rover, excluding panels and roof-mounted payload.
    retained=[p for p in parts if p.name not in body.body_names and p.group!='Body_fasteners_reference'
              and p.group!='Battery_snap_v2_UNCHANGED']
    gauge_checks=[]
    for n,item in printables.items():
        if not n.startswith('wheel_bay_fit_gauge_'):continue
        gp=body.Component(n,item['design_shape'],'Fit_gauge',item['color'])
        for rp in retained:
            ov=review.overlap_record(gp,rp)
            if ov:raise RuntimeError('Gauge collision '+str(ov))
        gauge_checks.append({'name':n,'positive_volume_intersections':[]})
    print('Geometry and preserved-interface checks passed',flush=True)
    print_reports,packs=export_prints(printables,out)
    steps=[]
    for filename,name,selected in [
        ('rover_body_v3_with_snap_battery.step','ELEGOO_V4_76p2mm_WB_body_v3',parts),
        ('body_shell_v3.step','ELEGOO_V4_body_shell_v3',[p for p in parts if p.name in body.body_names]),
        ('open_rover_v3_reference.step','ELEGOO_V4_open_rover_measured_WB',
         [p for p in parts if p.name not in body.body_names and p.group!='Body_fasteners_reference'
          and p.group!='Battery_snap_v2_UNCHANGED'])]:
        print('Export',filename,flush=True)
        steps.append(export_step(selected,out/'cad'/filename,name))
    manifest={'version':'0.3.0','units':'mm','parameters':body.P,'wheel_reference':body.base.P,
       'changes':changes,'printables':print_reports,'packs':packs,'step_exports':steps,
       'reference_sha256':hashlib.sha256(args.reference.read_bytes()).hexdigest(),
       'reference_filename':args.reference.name,
       'not_verified':['Physical fit','Printed strength','Actual Fusion/Bambu GUI opening','Slicing','Camera FOV','Wires/cables','Payload/thermal performance'],
       'components':[{'name':p.name,'group':p.group,'color':p.color,'bounds_mm':bounds(p.shape),'volume_mm3':p.shape.Volume()} for p in parts]}
    for n,r in [('manifest.json',manifest),('geometry_checks.json',fit),('preserved_interfaces.json',interfaces),
                ('tolerance_envelope.json',envelope),('gauge_checks.json',gauge_checks)]:
        (out/'verification'/n).write_text(json.dumps(r,indent=2)+'\n')
    print('PASS all build, mesh, STEP, interface and envelope checks.',flush=True)

if __name__=='__main__':main()
