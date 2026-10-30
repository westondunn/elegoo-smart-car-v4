#!/usr/bin/env python3
"""Rover V3 full PLA chassis, retaining the verified C1/C3 motor interface.

This script creates exact printable parts and separate assembly-coordinate STEP
instances. Hardware envelopes are deliberately not used to drive these solids.
Requires CadQuery 2.7, NumPy. All dimensions are millimetres.
"""
from pathlib import Path
from hashlib import sha256
import importlib.util
import json
import math
import sys
import cadquery as cq
import numpy as np
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box

ROOT=Path(__file__).resolve().parents[1]
SESSION=ROOT.parent
OUT=ROOT/'cad'/'generated'
OEM=json.loads((ROOT/'source/oem_geometry.json').read_text())
C3=ROOT/'cad/coupons/c3_motor_fit_integrated.step'
C3_SHA='f86d3f878bd29f0052a1b74c17d7689faf6fefa71729ee48e8d35ec580985735'
assert sha256(C3.read_bytes()).hexdigest()==C3_SHA
X0=10.19218024608248
Y0=-50.99487686157227
BASE_T=4.5
DECK_Z=45.0
DECK_T=3.6
DECK_TOP=48.6
P1=np.array([40.808039643857,55.722195278815])
P2=np.array([40.808039034374,63.522194224943])
PC=(P1+P2)/2
PITCH=float(np.linalg.norm(P2-P1))
OUTLINE=np.array(OEM['Bottom Plate.stl']['loops'][0]['vertices'],float)
SOURCE_W=float(OUTLINE[:,0].max()-OUTLINE[:,0].min())
OUTWARD=(230.0-SOURCE_W)/2
MOTOR_X=25.5+OUTWARD
FRONT_Y=float(PC[1])
REAR_Y=float(-np.mean([16.430927457456708,8.630927066873328])+Y0)
SUPPORTS=[(x,y) for y in [-88.0,0.0,88.0] for x in [-48.0,48.0]]
PI_HOLES=[(x,y) for y in [0.0,58.0] for x in [-62.5,-13.5]]
UNO_HOLES=[(20.29700537497455,49.8),(48.16400979738201,49.79999592934187),(15.8,-1.85979257687282)]
BANK_CLEAR_W=73.025
BANK_CLEAR_L=149.225
RAIL_Y=[-40.0,20.0,40.0]
RAIL_INNER=BANK_CLEAR_W/2
RAIL_HOLES=[(RAIL_INNER+7.4,y) for y in RAIL_Y]+[(-RAIL_INNER-7.4,-y) for y in RAIL_Y]
TRACKER_LOOPS=[OEM['Bottom Plate.stl']['loops'][i] for i in [13,14,23,24]]
TRACKER_HOLES=[(l['center_xy'][0]-X0,-l['center_xy'][1]+Y0) for l in TRACKER_LOOPS]
HEAD_HOLES=[(OEM['Top Plate.stl']['loops'][i]['center_xy'][0]-X0,-OEM['Top Plate.stl']['loops'][i]['center_xy'][1]+Y0) for i in [7,8,9]]
IDENTITY=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]
parts=[]
print_parts=[]
joints=[]
validation={}

def bounds(shape):
    b=Bnd_Box(); BRepBndLib.AddOptimal_s(shape.wrapped,b,False,False)
    q=cq.BoundBox(b)
    return {'min_mm':[q.xmin,q.ymin,q.zmin], 'max_mm':[q.xmax,q.ymax,q.zmax], 'size_mm':[q.xlen,q.ylen,q.zlen]}

def box(x,y,z,w,l,h):
    return cq.Workplane('XY',origin=(x,y,z)).box(w,l,h,centered=(False,False,False)).val()

def cyl(x,y,z,d,h):
    return cq.Workplane('XY',origin=(x,y,z)).circle(d/2).extrude(h).val()

def rounded_rect(cx,cy,z,w,l,h,r):
    p=cq.Workplane('XY',origin=(cx,cy,z)).rect(w,l).extrude(h)
    return p.edges('|Z').fillet(r).val()

def slot(x0,y0,x1,y1,z,w,h):
    pitch=math.hypot(x1-x0,y1-y0)
    if pitch<1e-9:return cyl(x0,y0,z,w,h)
    angle=math.degrees(math.atan2(y1-y0,x1-x0))
    return cq.Workplane('XY',origin=((x0+x1)/2,(y0+y1)/2,z)).slot2D(pitch+w,w,angle).extrude(h).val()

def hex_hole(x,y,z,af,h):
    return cq.Workplane('XY',origin=(x,y,z)).polygon(6,af/math.cos(math.pi/6)).extrude(h).val()

def ensure(shape,name):
    assert shape.isValid(),f'{name}: invalid CAD'
    assert len(shape.Solids())==1,f'{name}: {len(shape.Solids())} solids'
    return shape.Solids()[0]

def vol(shape):return sum(s.Volume() for s in shape.Solids())

def delta(a,b):return vol(a.cut(b))+vol(b.cut(a))

def normalized_xy(vertices):
    p=np.array(vertices,float)
    return np.column_stack([p[:,0]-X0,-p[:,1]+Y0])

def underside_label(shape,text,x,y,size=5.5,depth=.5,z=0):
    # Engraved from below: letter strokes are deliberately broad and shallow.
    # Rotating the text through 180 deg about Y makes it readable from below.
    t=cq.Workplane('XY').text(text,size,depth,font='DejaVu Sans',kind='bold',halign='center',valign='center',combine=False).val()
    t=t.rotate((0,0,0),(0,1,0),180).translate((x,y,z+depth))
    return shape.cut(t)

def top_label(shape,text,x,y,z,size=5.2,depth=.6):
    t=cq.Workplane('XY',origin=(x,y,z-depth)).text(text,size,depth+.01,font='DejaVu Sans',kind='bold',halign='center',valign='center',combine=False).val()
    return shape.cut(t)

def native_post(center,z,h,od,bore,shape,group):
    b=bounds(shape)
    return {'type':'round_post','center_mm':list(center),'base_z_mm':z,'height_mm':h,'outer_diameter_mm':od,'bore_diameter_mm':bore,
            'parameters':{'height':group+'_height','outer_diameter':group+'_outer_diameter','bore_diameter':group+'_bore_diameter'},
            'reference':{'bbox_min_mm':b['min_mm'],'bbox_max_mm':b['max_mm'],'volume_mm3':shape.Volume()}}

def instance(shape,pid,name,group,parent='base',native=None,notes=''):
    shape=ensure(shape,pid)
    p=OUT/'assembly'/f'{pid}.step'; shape.exportStep(str(p))
    rec={'id':pid,'name':name,'step_file':f'cad/generated/assembly/{pid}.step','transform_mm':IDENTITY,'sha256':sha256(p.read_bytes()).hexdigest(),
         'category':'printed_part','quantity':1,'bom_group':group,'physical_material':'PLA','color_rgba':[46,88,126,255],
         'fidelity':'Exact generated printable CAD. Full assembly has not been physically tested.','notes':notes,
         'bounds_mm':bounds(shape),'volume_mm3':shape.Volume()}
    if native:rec['native_recipe']=native
    parts.append(rec)
    if parent:joints.append({'id':pid+'_rigid','name':name+' attachment','type':'rigid','part_a':parent,'part_b':pid,'enabled':True})
    return shape

def printable(shape,pid,name,quantity):
    b=bounds(shape)
    shape=shape.translate(tuple(-v for v in b['min_mm']))
    # Remove harmless model tolerance values, so printable meshes start at Z0.
    shape=ensure(shape,pid)
    p=OUT/'print'/f'{pid}.stl'
    shape.exportStl(str(p),tolerance=.015,angularTolerance=.08,ascii=False,relative=False,parallel=True)
    print_parts.append({'id':pid,'name':name,'path':str(p.relative_to(ROOT)),'quantity':quantity,'bounds_mm':bounds(shape),
                        'sha256':sha256(p.read_bytes()).hexdigest(),'orientation':'Already print-oriented; flat side down; do not auto-orient.'})
    return p

def make_layout():
    d={'units':'mm','coordinate_frame':'X right, Y front, Z up; main base motor contact Z4.5; nominal underside Z0.',
       'status':'Approved CAD layout; hardware envelopes remain nominal until measured.',
       'base':{'width_mm':230,'source_length_mm':230.77959442138672,'thickness_mm':4.5,'head_rim_min_z_mm':-.6,'outward_translation_per_side_mm':OUTWARD},
       'motor_holes':{'x_mm':[-MOTOR_X,MOTOR_X],'front_pair_y_mm':[FRONT_Y-PITCH/2,FRONT_Y+PITCH/2],'rear_pair_y_mm':[REAR_Y-PITCH/2,REAR_Y+PITCH/2],
                      'diameter_mm':3.2,'floor_thickness_mm':1.8,'shared_head_pocket_width_mm':7.4,'shared_head_pocket_depth_mm':3.3},
       'upper_deck':{'bounds_xy_mm':[[-84,-103],[84,107]],'bottom_z_mm':45,'top_z_mm':48.6},
       'supports':{'centers_xy_mm':SUPPORTS,'bottom_z_mm':4.5,'height_mm':40.5,'outer_diameter_mm':12,'bore_mm':3.4},
       'flat_powerbank':{'nominal_body_mm':[69.85,146.05,12.7],'body_bottom_center_mm':[0,0,4.5],'clear_tray_mm':[73.025,149.225],
                         'rail_inner_x_mm':[-RAIL_INNER,RAIL_INNER],'rail_holes_xy_mm':RAIL_HOLES,'ends':'6mm corner stops leave61.025mm central port opening.'},
       'motor_battery':{'nominal_body_mm':[86,52,22],'body_bottom_center_mm':[0,-73,48.6],'fidelity':'Body envelope unmeasured prior nominal.',
                        'fixed_hole_mm':[-38,-73],'slot_centers_mm':[[27,-73],[52,-73]],'pitch_adjustment_mm':[65,90],
                        'bore_slot_width_mm':3.4,'head_pocket_width_mm':7.4,'head_pocket_depth_mm':3.3,'floor_mm':2.4,'rim_min_z_mm':42.9},
       'pi':{'nominal_board_size_xy_mm':[56,85],'board_bottom_center_mm':[-38,19,54.6],'model':'Unconfirmed; nominal85x56PCB only.','holes_xy_mm':PI_HOLES,
             'bore_diameter_mm':2.8,'post_outer_diameter_mm':8,'post_height_mm':6,'ports':'Rear -Y and outboard -X; reference orientation only.'},
       'uno':{'nominal_board_size_xy_mm':[53.4,68.6],'board_bottom_center_mm':[38,19,54.6],'holes_xy_mm':UNO_HOLES,
              'pattern_source':'Original Top Plate.stl 3-hole pattern, rigidly rotated/translated, no scale.','bore_diameter_mm':3.5,'post_bore_diameter_mm':3.4,'post_height_mm':6},
       'front_head':{'holes_xy_mm':HEAD_HOLES,'hole_diameter_mm':3.5,'mount_top_z_mm':48.6,'opening_vertices_xy_mm':normalized_xy(OEM['Top Plate.stl']['loops'][1]['vertices']).tolist(),
                     'instruction':'Reuse complete existing servo/camera/sonar head and original support bracket; source top-plate opening and3-hole pattern retained.'},
       'line_tracker':{'holes_xy_mm':TRACKER_HOLES,'bore_diameter_mm':3.2,'spacer_top_z_mm':0,'spacer_height_mm':3,
                       'nominal_board_top_z_mm':-3,'nominal_board_bottom_z_mm':-4.6,'note':'3mm spacers supplied; stock spacer hardware may be reused if actual sensor height requires it.'}}
    d['flat_powerbank']['strap_slots']={'centers_xy_mm':[(x,y) for x in [-43,43] for y in [-56,56]],'length_y_mm':14,'width_x_mm':3.4,'strap_quantity':2,'maximum_strap_width_mm':12,'suggested_strap_length_mm':[220,250]}
    (ROOT/'source/assembly_layout.json').write_text(json.dumps(d,indent=2)+'\n')
    return d

def build_base():
    p=normalized_xy(OUTLINE)
    p[:,0]+=np.where(p[:,0]<0,-OUTWARD,OUTWARD)
    base=cq.Workplane('XY').polyline(p.tolist()).close().extrude(BASE_T).val()
    assert base.isValid()
    imported=cq.importers.importStep(str(C3)).val().Solids()[0]
    # Exact patch includes the original bores, unchanged1.8mm bearing floor,
    # shared pocket and raised rim in an18x26mm neighborhood. The block
    # orientation is not measured; the surrounding base remains planar.
    clip=box(float(PC[0])-9,float(PC[1])-13,-.1,18,26,5.4)
    patch=imported.intersect(clip)
    right=patch.rotate((0,0,0),(0,1,0),180).translate((float(PC[0])+MOTOR_X,0,4.5))
    expected=[]
    for pos,y in [('front',FRONT_Y),('rear',REAR_Y)]:
        r=right.translate((0,y-FRONT_Y,0))
        l=r.rotate((0,y,0),(0,y,1),180)
        for side,q,x in [('right',r,MOTOR_X),('left',l,-MOTOR_X)]:
            region=box(x-9,y-13,-1,18,26,7)
            base=base.cut(region).fuse(q)
            expected.append((pos+'_'+side,q,region))
    for x,y in SUPPORTS:
        base=base.fuse(cyl(x,y,-.6,12.2,.6))
        base=base.cut(cyl(x,y,-1,3.4,7))
        base=base.cut(cyl(x,y,-.61,7.4,3.31))
    for x,y in RAIL_HOLES:
        base=base.cut(cyl(x,y,-1,3.4,7)).cut(hex_hole(x,y,-.01,5.8,2.41))
    for x,y in TRACKER_HOLES:base=base.cut(cyl(x,y,-1,3.2,7))
    for x in [-43,43]:
        for y in [-56,56]:
            # Overall capsule14mm long,3.4mm wide for a12mm strap.
            base=base.cut(slot(x,y-5.3,x,y+5.3,-.1,3.4,4.7))
    base=underside_label(base,'FRONT',0,110,size=5.5)
    base=underside_label(base,'ROVER V3',0,-105,size=6)
    for x,y,label in [(-MOTOR_X,35,'FL'),(MOTOR_X,35,'FR'),(-MOTOR_X,-35,'RL'),(MOTOR_X,-35,'RR')]:
        base=underside_label(base,label,x,y,size=5.8)
    base=ensure(base.clean(),'base')
    checks={}
    for name,ref,region in expected:
        d=delta(base.intersect(region),ref)
        assert d<1e-6,(name,d)
        checks[name]={'exact_C3_patch_symmetric_difference_mm3':d,'patch_size_xy_mm':[18,26],
                     'includes':'Two original bores, original1.8mm bearing floor, C3pocket and rim within18x26mm; block orientation unmeasured.'}
    validation['motor_interfaces']=checks
    validation['base_source_outline']={'method':'Official OEM boundary translated outward rigidly on each side and joined across the center; no scaling.','source_width_mm':SOURCE_W,'outward_translation_mm':OUTWARD,'final_width_mm':bounds(base)['size_mm'][0]}
    return base

def build_deck():
    deck=rounded_rect(0,2,45,168,210,3.6,8)
    # Battery face remains coplanar with deck top; recesses open below the deck.
    rail=rounded_rect(7,-73,42.9,110,18,2.1,3)
    deck=deck.fuse(rail)
    deck=deck.cut(cyl(-38,-73,42.8,3.4,6.1))
    deck=deck.cut(cyl(-38,-73,42.89,7.4,3.31))
    deck=deck.cut(slot(27,-73,52,-73,42.8,3.4,6.1))
    deck=deck.cut(slot(27,-73,52,-73,42.89,7.4,3.31))
    for x,y in SUPPORTS:deck=deck.cut(cyl(x,y,44.9,3.4,4))
    for x,y in PI_HOLES:deck=deck.cut(cyl(x,y,44.9,2.8,4))
    for x,y in UNO_HOLES:deck=deck.cut(cyl(x,y,44.9,3.5,4))
    for x,y in HEAD_HOLES:deck=deck.cut(cyl(x,y,44.9,3.5,4))
    aperture=normalized_xy(OEM['Top Plate.stl']['loops'][1]['vertices'])
    cut=cq.Workplane('XY',origin=(0,0,44.9)).polyline(aperture.tolist()).close().extrude(4).val()
    deck=deck.cut(cut)
    # Cable/strap windows and future mounting points sit clear of existing mounts.
    for x in [-59,59]:
        for y in [-52,-94]:deck=deck.cut(slot(x-5,y,x+5,y,44.9,3.4,4))
    for x in [-66,0,66]:
        deck=deck.cut(slot(x,-30,x,-20,44.9,3.4,4))
    # Broad service opening between the board bays, plus two forward cable slots.
    deck=deck.cut(rounded_rect(0,25,44.9,8,40,4,3))
    for x in [-49,49]:deck=deck.cut(slot(x-10,71,x+10,71,44.9,5,4))
    for txt,x,y in [('PI',-38,66),('UNO',38,61),('MOTOR BATTERY',0,-41),('FRONT',43,96)]:
        deck=top_label(deck,txt,x,y,48.6,size=5.5)
    deck=underside_label(deck,'65 - 90',3,-86,size=5,z=45)
    deck=ensure(deck.clean(),'upper_deck')
    for x,y in [(-38,-73),(27,-73),(52,-73)]:
        assert not deck.isInside((x,y,47.0),1e-7)
        assert deck.isInside((x,y+2.6,46.201),1e-7)
        assert not deck.isInside((x,y+2.6,46.199),1e-7)
    validation['battery_slide']={'fixed_center_mm':[-38,-73],'slot_end_centers_mm':[[27,-73],[52,-73]],'pitch_range_mm':[65,90],
                                 'pocket_width_mm':7.4,'pocket_depth_mm':3.3,'floor_mm':2.4,'motor_battery_contact_plane_mm':48.6,
                                 'pocket_floor_plane_mm':46.2,'head_rim_min_z_mm':42.9,'floor_probe_passed':True}
    return deck

def build_bank_rail():
    # Canonical right-side rail; a180deg rotation makes the matching left rail.
    half=BANK_CLEAR_L/2
    s=box(0,-half-2.4,0,2.4,BANK_CLEAR_L+4.8,7.2)
    for y in [-half-2.4,half]:s=s.fuse(box(-6,y,0,8.4,2.4,7.2))
    for y in RAIL_Y:
        flange=rounded_rect(6.2,y,0,12.4,14,6.3,3)
        s=s.fuse(flange).cut(cyl(7.4,y,-.1,3.4,6.5)).cut(cyl(7.4,y,3,7.4,3.4))
    # Enlarged labels are outside the powerbank-contact walls and bearing seats.
    return ensure(s.clean(),'bank_rail')

def post(od,h,bore):
    return cq.Workplane('XY').circle(od/2).circle(bore/2).extrude(h).val()

def main():
    layout=make_layout()
    # Publish the complete expected instance inventory before the expensive CAD
    # build so electronics and assembly integration can proceed independently.
    provisional={'units':'mm','parts':[{'id':'base','name':'Full lower chassis'},{'id':'upper_deck','name':'Upper service deck'},{'id':'bank_rail_right','name':'Powerbank rail right'},{'id':'bank_rail_left','name':'Powerbank rail left'}]+
                  [{'id':f'support_post_{i+1:02}','name':f'Deck support {i+1}'} for i in range(6)]+
                  [{'id':f'pi_standoff_{i+1:02}','name':f'Pi standoff {i+1}'} for i in range(4)]+
                  [{'id':f'uno_standoff_{i+1:02}','name':f'UNO standoff {i+1}'} for i in range(3)]+
                  [{'id':f'tracker_spacer_{i+1:02}','name':f'Tracker spacer {i+1}'} for i in range(4)]}
    for p in provisional['parts']:p['step_file']=f"cad/generated/assembly/{p['id']}.step"
    (OUT/'printed_parts_provisional.json').write_text(json.dumps(provisional,indent=2)+'\n')
    print('Layout and provisional inventory written.',flush=True)
    base=instance(build_base(),'base','Full lower chassis','base',parent=None,
                  notes='Exact C3 local motor interfaces; actual OEM front/rear spacing; widened230mm body. Print motor-contact face down.')
    printable(base.rotate((0,0,0),(0,1,0),180),'base','Full lower chassis',1)
    print('Base complete.',flush=True)
    deck=instance(build_deck(),'upper_deck','Upper service deck with battery slider','upper_deck',
                  notes='168x210mm deck; battery pocket integrated on underside; source front-head interface. Print top surface down.')
    printable(deck.rotate((0,0,0),(0,1,0),180),'upper_deck','Upper service deck',1)
    print('Deck complete.',flush=True)
    rail=build_bank_rail()
    instance(rail.translate((RAIL_INNER,0,4.5)),'bank_rail_right','Powerbank retaining rail right','bank_rail')
    instance(rail.rotate((0,0,0),(0,0,1),180).translate((-RAIL_INNER,0,4.5)),'bank_rail_left','Powerbank retaining rail left','bank_rail')
    printable(rail,'bank_rail','Powerbank retaining rail',2)
    configs=[('support_post',SUPPORTS,12,40.5,3.4,4.5,'base','Deck support post'),
             ('pi_standoff',PI_HOLES,8,6,2.8,48.6,'upper_deck','Pi board standoff'),
             ('uno_standoff',UNO_HOLES,8,6,3.4,48.6,'upper_deck','UNO board standoff'),
             ('tracker_spacer',TRACKER_HOLES,7,3,3.2,-3,'base','Line tracker spacer')]
    for group,centers,od,h,bore,z,parent,label in configs:
        local=ensure(post(od,h,bore),group)
        for i,(x,y) in enumerate(centers,1):
            s=local.translate((x,y,z)); pid=f'{group}_{i:02}'
            instance(s,pid,f'{label} {i}',group,parent,native_post((x,y),z,h,od,bore,s,group))
        printable(local,group,label,len(centers))
    print('All accessory CAD complete.',flush=True)
    # STEP round-trip each output and validate STL topology using the previously
    # established validation implementation, without modifying that source.
    spec=importlib.util.spec_from_file_location('c3_verify',ROOT/'source/c3_validation_source.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    for rec in parts:
        p=ROOT/rec['step_file'];s=cq.importers.importStep(str(p)).val()
        assert s.isValid() and len(s.Solids())==1
        assert abs(s.Volume()-rec['volume_mm3'])/rec['volume_mm3']<1e-8
    for rec in print_parts:
        p=ROOT/rec['path'];raw=p.read_bytes();n=int.from_bytes(raw[80:84],'little')
        a=np.frombuffer(raw,dtype=np.dtype([('n','<f4',(3,)),('v','<f4',(3,3)),('a','<u2')]),offset=84)['v']
        meshvol=float(np.einsum('ij,ij->i',a[:,0].astype(float),np.cross(a[:,1].astype(float),a[:,2].astype(float))).sum()/6)
        rec['mesh_validation']=mod.verify_stl(p,meshvol)
    validation['all_STEP_roundtrip_valid_single_solid']=True
    validation['printed_part_instances']=len(parts)
    validation['unique_print_meshes']=len(print_parts)
    validation['whole_assembly_physical_fit_tested']=False
    validation['printer_profile']='X1C0.4PLA,0.15mm layers,6walls,35%gyroid,6top/6bottom,2mmoutsidebrim,no supports; native slicing handled separately.'
    manifest={'format_version':1,'project_name':'Rover V3 full chassis PLA','units':'mm','grounded_part_id':'base','engineering_status':'Exact printable CAD with retained physically proven local motor interface; new whole-chassis assembly not physically tested.',
              'parts':parts,'joints':joints,'parameters':[], 'build_options':{'use_native_recipes':True}}
    (OUT/'printed_assembly_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (OUT/'print_inventory.json').write_text(json.dumps({'units':'mm','parts':print_parts},indent=2)+'\n')
    (OUT/'validation.json').write_text(json.dumps(validation,indent=2)+'\n')
    print(json.dumps({'instances':len(parts),'unique_STLs':len(print_parts),'output':str(OUT)},indent=2),flush=True)

if __name__=='__main__':main()
