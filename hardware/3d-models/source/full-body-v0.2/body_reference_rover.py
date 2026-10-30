#!/usr/bin/env python3
"""ELEGOO V4 explorer reference assembly and modular PLA accessory kit.

Rebuild: Python 3.11+, cadquery==2.7.0, numpy; optional Matplotlib for renders.
Keep body_reference_parameters.json, body_reference_profiles.json and rover_3mf.py beside this file.
All dimensions are millimeters. Purchased hardware is simplified reference geometry.
No connection to Fusion, a printer, Home Assistant, or the network is made.
"""
from __future__ import annotations
import json, math, hashlib, argparse
from pathlib import Path
from dataclasses import dataclass
import numpy as np
import cadquery as cq
from rover_3mf import write_3mf, weld_mesh, mesh_stats, validate_with_lib3mf

HERE = Path(__file__).resolve().parent
P = json.loads((HERE / 'body_reference_parameters.json').read_text())
SOURCE = json.loads((HERE / 'body_reference_profiles.json').read_text())
BLUE = '#2587BA'
DARK = '#303941'
BLACK = '#181E24'
GREEN = '#226C51'
GOLD = '#DCA83A'
SILVER = '#ADB8C3'
WHITE = '#ECE8DC'
ORANGE = '#E78939'
PURPLE = '#8E6FB5'
parts = []
prints = {}

def color(hex_value):
    return cq.Color(*[int(hex_value[i:i+2],16)/255 for i in (1,3,5)])

def xyz_from_source(x, y, z):
    return (P['source_center_xy'][0]-x, P['source_center_xy'][1]-y,
            z-SOURCE['plates'][0]['source_z_min']+P['bottom_plate_underside_z'])

def source_xy(p):
    return tuple(np.array(P['source_center_xy'])-np.array(p))

Z_BOTTOM = P['bottom_plate_underside_z']
Z_BOTTOM_TOP = Z_BOTTOM + SOURCE['plates'][0]['thickness']
Z_TOP_BOTTOM = xyz_from_source(0,0,SOURCE['plates'][1]['source_z_min'])[2]
Z_TOP = Z_TOP_BOTTOM + SOURCE['plates'][1]['thickness']
Z_DECK = Z_TOP + P['deck_height_above_top']

def box(w, d, h, x=0, y=0, z=0, radius=0):
    q=cq.Workplane('XY').box(w,d,h,centered=(True,True,False))
    if radius:
        q=q.edges('|Z').fillet(radius)
    return q.val().translate((x,y,z))

def cyl(r,h,x=0,y=0,z=0,axis=(0,0,1)):
    return cq.Solid.makeCylinder(r,h,cq.Vector(x,y,z),cq.Vector(*axis))

def ring(ro,ri,h,x=0,y=0,z=0,axis=(0,0,1)):
    return cyl(ro,h,x,y,z,axis).cut(cyl(ri,h,x,y,z,axis))

def slot(length,width,height,x=0,y=0,z=0,angle=0):
    return cq.Workplane('XY').slot2D(length,width,angle).extrude(height).val().translate((x,y,z))

def bolt_z(x,y,z_head,shaft_length=10,diameter=3):
    shaft=cyl(diameter/2,shaft_length,x,y,z_head-shaft_length)
    head=cyl(diameter*.92,diameter*.8,x,y,z_head)
    return shaft.fuse(head).clean()

def nut_z(x,y,z,diameter=3):
    n=cq.Workplane('XY').polygon(6,6.35).extrude(2.4).val().translate((x,y,z))
    return n.cut(cyl(diameter/2+.05,3,x,y,z-.3))

def segment(a,b,r):
    a,b=np.array(a,float),np.array(b,float);v=b-a
    return cyl(r,float(np.linalg.norm(v)),*a,axis=tuple(v/np.linalg.norm(v)))

def cable(points,r=.7):
    q=segment(points[0],points[1],r)
    for i in range(1,len(points)-1):
        q=q.fuse(segment(points[i],points[i+1],r))
    return q.clean()

@dataclass
class Component:
    name: str
    shape: cq.Shape
    group: str
    color: str
    evidence: str
    variant: str = 'both'
    notes: str = ''

def add(name,shape,group='Stock_hardware_reference',c=SILVER,
        evidence='estimated_envelope',variant='both',notes=''):
    if not shape.isValid() or not shape.Solids():
        raise ValueError('Invalid component '+name)
    parts.append(Component(name,shape,group,c,evidence,variant,notes))
    return shape

def add_print(name,local,installed=None,quantity=1,c=BLUE,notes='',variant='explorer',
              print_rotation=None):
    if not local.isValid() or len(local.Solids())!=1:
        raise ValueError('Print must be exactly one valid solid: '+name)
    orient=local
    if print_rotation:
        a,b,deg=print_rotation; orient=orient.rotate(a,b,deg)
    bb=orient.BoundingBox();orient=orient.translate((-bb.xmin,-bb.ymin,-bb.zmin))
    bb=orient.BoundingBox()
    if max(bb.xlen,bb.ylen)>172.1:
        raise ValueError('Print exceeds portable 180mm envelope: '+name)
    prints[name]={'shape':orient,'quantity':quantity,'color':c,'notes':notes,
                  'design_shape':local}
    if installed is not None:
        add(name,installed,'PLA_accessories',c,'new_design',variant,notes)
    return local

def stock_plates():
    for data in SOURCE['plates']:
        outer=next(p for p in data['profiles'] if p['kind']=='outer')
        q=cq.Workplane('XY').polyline(outer['simplified_vertices_ordered_xy']).close().extrude(data['thickness'])
        holes=sorted([p for p in data['profiles'] if p['kind']=='hole'],key=lambda p:p['geometry']=='circle_fit')
        for h in holes:
            w=cq.Workplane('XY').workplane(offset=-1)
            if h['geometry']=='circle_fit':
                w=w.center(*h['center_source_xy']).circle(h['diameter_fit']/2)
            else:
                w=w.polyline(h['simplified_vertices_ordered_xy']).close()
            q=q.cut(w.extrude(data['thickness']+2))
        shape=q.val().translate((0,0,data['source_z_min']))
        shape=shape.rotate((0,0,0),(0,0,1),180).translate((
            *P['source_center_xy'],P['bottom_plate_underside_z']-SOURCE['plates'][0]['source_z_min']))
        variant='stock' if data['name']=='Dead Plate' else 'both'
        note='Supplied mid-section reconstructed; circle fits; outer simplification <=0.02mm at measured section vertices.'
        if variant=='stock':
            note+=' SOURCE POSE ONLY: supplied three-hole row does not match top plate. Not a fit-approved adapter.'
        add('OEM_'+data['name'].replace(' ','_'),shape,'OEM_chassis_from_supplied_meshes',DARK,
            'derived_from_supplied_STL',variant,note)

def stock_hardware():
    # Six source-derived pillar positions and the nominal 40mm hardware stack.
    # Use the supplied plate gap rather than silently moving source plates.
    mounts=SOURCE['matched_3_4mm_mounting_holes']
    for i,m in enumerate(mounts,1):
        x,y=m['top_center_target_xy']
        add(f'Frame_pillar_{i}_nominal_M3x40',ring(3.0,1.55,Z_TOP_BOTTOM-Z_BOTTOM_TOP,x,y,Z_BOTTOM_TOP),
            c=GOLD,evidence='documented_nominal_hardware',
            notes='Nominal M3x40 in manual; modeled length follows supplied39.705222mm gap.')
        add(f'Frame_bottom_screw_{i}',bolt_z(x,y,Z_BOTTOM,10).rotate((x,y,Z_BOTTOM),(x+1,y,Z_BOTTOM),180),
            evidence='documented_nominal_hardware')
        add(f'Frame_top_screw_{i}',bolt_z(x,y,Z_TOP,10),evidence='documented_nominal_hardware',variant='stock')

    r=P['reference_wheel_diameter']/2
    width=P['reference_wheel_width']
    for side in (-1,1):
        for end,y_axle in [('front',P['reference_front_axle_y']),('rear',P['reference_rear_axle_y'])]:
            label=('left' if side<0 else 'right')+'_'+end
            direction=1 if end=='front' else -1
            mx=side*36
            my=y_axle+direction*6
            gear=box(22,43,22,mx,my,Z_BOTTOM_TOP+1,radius=2)
            # Motor can at outer end of gearbox, axis along vehicle Y.
            motor=cyl(8,26,mx,my+direction*17,Z_BOTTOM_TOP+12,axis=(0,direction,0))
            shaft=cyl(2.8,39,side*43,y_axle,r,axis=(side,0,0))
            add('TT_gearbox_'+label,gear,c=GOLD,notes='Representative TT gearmotor; exact ELEGOO envelope unmeasured.')
            add('DC_motor_can_'+label,motor)
            add('Drive_shaft_'+label,shaft)
            clamp=box(8,16,22,side*25.5,my,Z_BOTTOM_TOP)
            clamp=clamp.cut(cyl(1.6,24,side*25.5,my-3.9,Z_BOTTOM_TOP-1))
            clamp=clamp.cut(cyl(1.6,24,side*25.5,my+3.9,Z_BOTTOM_TOP-1))
            add('Aluminum_motor_block_'+label,clamp)
            for k in (-1,1):
                add(f'Motor_through_bolt_{label}_{k}',cyl(1.5,30,side*21,my+k*5,Z_BOTTOM_TOP+12,axis=(side,0,0)),
                    evidence='documented_nominal_hardware')
            xstart=side*P['reference_wheel_center_x']-width/2
            tire=ring(r,r*.70,width,xstart,y_axle,r,axis=(1,0,0))
            # Shallow circumferential tread grooves, visual geometry only.
            for offset in (width*.29,width*.71):
                tire=tire.cut(ring(r+1,r-.7,1.4,xstart+offset,y_axle,r,axis=(1,0,0)))
            hub=cyl(r*.70,width-2,xstart+1,y_axle,r,axis=(1,0,0))
            for a in np.linspace(0,2*math.pi,5,endpoint=False):
                hub=hub.cut(cyl(4.4,width+2,xstart-1,y_axle+14*math.cos(a),r+14*math.sin(a),axis=(1,0,0)))
            add('Tire_'+label,tire,c=BLACK,notes='65x26mm representative wheel; confirm actual diameter/width.')
            add('Wheel_hub_'+label,hub,c=GOLD)
            add('Wheel_M2_fastener_'+label,cyl(2,2,side*(P['reference_wheel_center_x']+width/2),y_axle,r,axis=(side,0,0)),
                evidence='documented_nominal_hardware')

    # UNO three mounting points come from the supplied top-plate holes.
    top=SOURCE['plates'][1]
    uno_holes=[h for h in top['profiles'] if h['index'] in (6,7,8)]
    for i,h in enumerate(uno_holes,1):
        x,y=source_xy(h['center_source_xy'])
        add(f'UNO_spacer_{i}',ring(3,1.8,5,x,y,Z_TOP),c=WHITE,
            notes='5mm spacer height is an envelope assumption.')
        add(f'UNO_M3_screw_{i}',bolt_z(x,y,Z_TOP+6.6,14),evidence='documented_nominal_hardware')
    ux,uy=P['reference_uno_center_xy']
    uw,ud,ut=P['reference_uno_size']
    uno=box(uw,ud,ut,ux,uy,Z_TOP+5,radius=2)
    for h in uno_holes:
        x,y=source_xy(h['center_source_xy']);uno=uno.cut(cyl(1.8,4,x,y,Z_TOP+4))
    add('UNO_R3_PCB',uno,c=GREEN,evidence='nominal_board_envelope_with_source_mount_centers',
        notes='68.6x53.4mm nominal UNO board. Local board details simplified, not a PCB fabrication model.')
    add('UNO_USB_B_connector',box(16,12,11,ux+25,uy+8,Z_TOP+6.6),c=SILVER)
    add('UNO_barrel_connector',box(13,9,11,ux+25,uy-14,Z_TOP+6.6),c=BLACK)
    for sy in (-1,1):
        add('UNO_header_'+str(sy),box(52,3,8.5,ux-4,uy+sy*23,Z_TOP+6.6),c=BLACK)
    add('UNO_ATmega_reference',box(32,7,4,ux-6,uy,Z_TOP+6.6),c=BLACK)
    sz=Z_TOP+17
    shield=box(69,53,1.6,ux,uy,sz,radius=2)
    add('SmartRobot_motor_expansion_shield_PCB',shield,c=GREEN,
        notes='Board outline/connector locations estimated from manual; no complete mechanical drawing supplied.')
    for i,(x,y) in enumerate([(-11,-13),(2,-13),(15,-13),(28,-13),(-11,4),(2,4),(15,4),(28,4)]):
        add(f'Shield_XH_connector_{i+1}',box(8,7,7,ux+x-8,uy+y,sz+1.6),c=WHITE)
    add('Shield_IR_receiver',box(6,4,8,ux+27,uy+21,sz+1.6),c=BLACK)
    add('Shield_mode_button',cyl(3,3,ux+18,uy+18,sz+1.6),c=ORANGE)
    add('Shield_RGB_LED',box(5,5,2,ux-22,uy+16,sz+1.6),c=WHITE)
    add('Shield_motor_driver_reference',box(8,6,2,ux-4,uy+13,sz+1.6),c=BLACK)
    # Original manual revision has a separate GY-521 module.
    add('GY521_MPU6050_module_PCB',box(20,15,1.6,ux-19,uy+12,sz+10),c=BLUE,
        notes='Original20201116 manual revision; some V4 shield revisions differ.')
    add('GY521_sensor_package',box(4,4,1.5,ux-19,uy+12,sz+11.6),c=BLACK)
    add('GY521_M3x11_pillar',ring(2.6,1.5,9,ux-25,uy+12,sz+1.6),c=GOLD,
        evidence='documented_nominal_hardware')

    bx,by=P['reference_battery_center_xy'];bw,bd,bh=P['reference_battery_size']
    batt=box(bw,bd,bh,bx,by,Z_TOP,radius=3)
    for sx in (-1,1):
        batt=batt.fuse(ring(5,1.75,3,sx*38.0,by,Z_TOP))
        add('Battery_M3_screw_'+str(sx),bolt_z(sx*38,by,Z_TOP+3,12),evidence='documented_nominal_hardware')
    add('Battery_enclosure_LiIon_reference',batt,c=BLACK,
        notes='Estimated70x52x22mm case; internal cells not modeled. Check enclosure, charging port and switch on your kit.')
    add('Battery_power_switch',box(8,2.5,5,20,by-bd/2-1,Z_TOP+8),c=ORANGE)
    add('Battery_charge_port',box(8,2.5,4,-15,by-bd/2-1,Z_TOP+7),c=SILVER)

    # Lower line-sensor PCB uses the four matching source hole positions.
    lower=SOURCE['plates'][0]
    line_h=[h for h in lower['profiles'] if h['index'] in (15,16,23,24)]
    line=box(48,32,1.6,0,93,Z_BOTTOM-6.6,radius=2)
    for h in line_h:
        x,y=source_xy(h['center_source_xy'])
        line=line.cut(cyl(1.8,4,x,y,Z_BOTTOM-7.6))
        add('Line_sensor_spacer_'+str(h['index']),ring(3,1.75,5,x,y,Z_BOTTOM-5),c=WHITE)
    add('Line_tracking_PCB',line,c=GREEN,notes='Board perimeter estimated; source lower mounting row used.')
    for i,x in enumerate((-16,0,16),1):
        add(f'Line_sensor_{i}_ITR20001',box(6,5,6,x,103,Z_BOTTOM-12.6),c=BLACK)

def servo_and_camera(explorer=False):
    # Each configuration has a distinct head placement and no duplicated overlaid boards.
    variant='explorer' if explorer else 'stock'
    if explorer:
        sx,sy=-.900185,86.689175
        mount_z=Z_TOP
        plate_t=3.2
    else:
        sx,sy=source_xy([9.328976,-141.329094])
        mount_z=xyz_from_source(0,0,SOURCE['plates'][2]['source_z_min'])[2]
        plate_t=2.6
    top=mount_z+plate_t
    group='Head_'+variant
    add('SG90_body_'+variant,box(12.2,23,23,sx,sy,top-23,radius=.8),group,BLUE,
        'nominal_component_envelope',variant,'Body passes through mounting plate; exact servo mounting geometry unmeasured.')
    flange=box(12.2,32,2.0,sx,sy,top)
    flange=flange.cut(cyl(1.2,4,sx,sy-14.2,top-1)).cut(cyl(1.2,4,sx,sy+14.2,top-1))
    add('SG90_mounting_ears_'+variant,flange,group,BLUE,'nominal_component_envelope',variant)
    axis_y=sy-5.5
    add('SG90_output_boss_'+variant,cyl(4,5,sx,axis_y,top+2),group,BLUE,'estimated_envelope',variant)
    add('Servo_horn_'+variant,cyl(8,2,sx,axis_y,top+7),group,WHITE,'estimated_envelope',variant)
    # L bracket rises behind sonar; nothing is added to its scan envelope by the body kit.
    bracket=box(42,19,3,sx,axis_y,top+9)
    bracket=bracket.fuse(box(42,3,34,sx,axis_y-8,top+9))
    add('OEM_sonar_head_bracket_'+variant,bracket,group,BLACK,'estimated_envelope',variant)
    pcb_z=top+17
    add('HC_SR04_PCB_'+variant,box(45.5,1.6,20,sx,axis_y-5.5,pcb_z),group,BLUE,
        'nominal_component_envelope',variant)
    for sign in (-1,1):
        add(f'Ultrasonic_transducer_{sign}_{variant}',ring(8,6.5,12,sx+sign*13,axis_y-4.7,pcb_z+10,axis=(0,1,0)),
            group,SILVER,'nominal_component_envelope',variant)
        add(f'Ultrasonic_mesh_{sign}_{variant}',cyl(6.5,.6,sx+sign*13,axis_y+6.7,pcb_z+10,axis=(0,1,0)),
            group,DARK,'estimated_envelope',variant)
    cam_w,cam_h,cam_t=P['reference_camera_pcb_size']
    cam_bottom=top+41
    cam_support=box(34,3,cam_h+5,sx,axis_y-9,top+38)
    cam_support=cam_support.cut(box(23,5,42,sx,axis_y-9,top+42))
    add('Camera_support_bracket_'+variant,cam_support,group,BLACK,'estimated_envelope',variant)
    add('ESP32_camera_PCB_'+variant,box(cam_w,cam_t,cam_h,sx,axis_y-5,cam_bottom),group,GREEN,
        'estimated_envelope',variant,'Complete camera-board envelope estimated; ESP32 radio datasheet is not a camera PCB drawing.')
    add('ESP32_WROVER_radio_module_'+variant,box(18,3,24,sx,axis_y-7.5,cam_bottom+3),group,SILVER,
        'estimated_envelope',variant)
    add('Camera_lens_'+variant,cyl(4.5,8,sx,axis_y-4,cam_bottom+cam_h-9,axis=(0,1,0)),group,BLACK,
        'estimated_envelope',variant)
    add('Camera_XH_connector_'+variant,box(12,7,5,sx,axis_y-4,cam_bottom),group,WHITE,
        'estimated_envelope',variant)
    # Schematic cable runs are reference curves only, not harness manufacturing lengths.
    add('Head_cable_route_'+variant,cable([(sx,axis_y-10,top+12),(sx,60,Z_TOP+17),(10,33,Z_TOP+28),(10,20,Z_TOP+25)],.9),
        'Cable_routes_reference',BLACK,'schematic_route',variant)

def addons():
    # Mounting locations use the top plate; source top/bottom centers are not averaged.
    deck_mounts=[m['top_center_target_xy'] for m in SOURCE['matched_3_4mm_mounting_holes'] if m['top_center_target_xy'][1]<10]
    d=P['deck_thickness'];clear=P['m3_clearance']
    deck=box(P['deck_width'],P['deck_length'],d,0,P['deck_center_y'],0,radius=5)
    # Open service window over the controller stack.
    deck=deck.cut(box(80,39,d+2,7,-8,-1,radius=4))
    # Rear ventilation / adaptable mounting slots.
    for x in (-32,-16,0,16,32):
        deck=deck.cut(slot(40,3.5,d+2,x,-60,-1,90))
    for x,y in deck_mounts:
        deck=deck.cut(slot(5,clear,d+2,x,y,-1,0))
    # Side-shell, Pi-tray, and universal accessory interfaces are all through-fastened.
    for x in (-57,57):
        for y in (-62,-28):
            deck=deck.cut(cyl(clear/2,d+2,x,y,-1))
    for x in (-44,44):
        for y in (-74.5,-43.5):
            deck=deck.cut(cyl(clear/2,d+2,x,y,-1))
    for x in (-12,12):
        deck=deck.cut(cyl(clear/2,d+2,x,-88,-1))
    add_print('01_slotted_deck',deck,deck.translate((0,0,Z_DECK)),
        notes='Four slots match the rear/middle source top-plate mounts. Service opening over UNO, M3 accessory interfaces.')
    spacer=ring(5,clear/2,P['deck_height_above_top'])
    add_print('02_deck_spacer_36mm',spacer,quantity=4,
        notes='Print4 upright. M3 clearance tube; use long metal through-screws, no printed threads.')
    for i,(x,y) in enumerate(deck_mounts,1):
        add('Deck_spacer_'+str(i),spacer.translate((x,y,Z_TOP)),'PLA_accessories',BLUE,'new_design','explorer')
        add('Deck_M3x50_screw_'+str(i),bolt_z(x,y,Z_DECK+d,50),'Added_fasteners_reference',SILVER,
            'proposed_hardware','explorer','Check actual pillar thread depth. Nominal6.3mm engagement at modeled stack.')
    # Side guards: an L section that can lie on its broad outer face for printing.
    for side in (-1,1):
        shell=box(2.8,66,28,side*62.0,-43,0)
        shell=shell.fuse(box(9.5,66,3.2,side*58.65,-43,24.8))
        for y in (-62,-28):
            shell=shell.cut(cyl(clear/2,5,side*57,y,24))
        # Windows through vertical wall, leaving a structural perimeter and ribs.
        for y in (-66,-50,-34,-18):
            shell=shell.cut(box(15,10,13,side*61,y,6,radius=1))
        name='03_side_guard_left' if side<0 else '04_side_guard_right'
        # Place top flange immediately beneath deck, without intersecting it.
        installed=shell.translate((0,0,Z_DECK-28))
        add_print(name,shell,installed,notes='Ventilated removable PLA guard. Print broad outer face down; no snap-fit spring.',
            print_rotation=((0,0,0),(0,1,0),90*side))
        for j,y in enumerate((-62,-28),1):
            add(f'Side_guard_screw_{side}_{j}',bolt_z(side*57,y,Z_DECK+d,10),
                'Added_fasteners_reference',SILVER,'proposed_hardware','explorer')
            add(f'Side_guard_nut_{side}_{j}',nut_z(side*57,y,Z_DECK-5.6),
                'Added_fasteners_reference',SILVER,'proposed_hardware','explorer')

    # Rigid front guard. This is NOT a collision switch or spring bumper.
    front=[m['top_center_target_xy'] for m in SOURCE['matched_3_4mm_mounting_holes'] if m['top_center_target_xy'][1]>70]
    guard=box(170,9,14,.25,126,0,radius=3)
    for x,y in front:
        arm=box(14,134-y,4,x,(118+y)/2,0,radius=3)
        guard=guard.fuse(arm)
        guard=guard.cut(slot(5,clear,6,x,y,-1,90))
    # Two mounting pairs for optional whisker/switch brackets; no sensing claim.
    for x in (-30,30):
        foot=box(22,10,4,x,117,0,radius=2)
        guard=guard.fuse(foot)
        for dx in (-6,6):guard=guard.cut(cyl(clear/2,6,x+dx,117,-1))
    guard=guard.clean()
    add_print('05_front_guard',guard,guard.translate((0,0,Z_TOP+4)),c=ORANGE,
        notes='Rigid PLA contact guard; apply foam tape. No automatic contact detection. Front attachment uses4mm spacers.')
    shim=ring(4.7,clear/2,4)
    add_print('06_front_guard_spacer_4mm',shim,quantity=2,notes='Print2; raises guard above stock wheel envelope.')
    for i,(x,y) in enumerate(front,1):
        # Arm slot is centered on the measured top-plate mounting hole.
        add('Guard_spacer_'+str(i),shim.translate((x,y,Z_TOP)),'PLA_accessories',BLUE,'new_design','explorer')
        add('Guard_M3x20_screw_'+str(i),bolt_z(x,y,Z_TOP+8,20),'Added_fasteners_reference',SILVER,
            'proposed_hardware','explorer')

    # Floor-facing sensor carriers under the front guard, forward of the stock wheel contact area.
    floor_carrier=box(33,37,3,0,0,0,radius=3)
    for x in (-6,6):floor_carrier=floor_carrier.cut(cyl(clear/2,5,x,-13,-1))
    for x in (-13,13):floor_carrier=floor_carrier.cut(slot(17,2.5,5,x,4,-1,90))
    floor_carrier=floor_carrier.cut(box(17,10,5,0,6.5,-1,radius=2))
    add_print('12_downward_sensor_carrier',floor_carrier,quantity=2,
        notes='Print2 only when adding floor-facing sensors. Strap exact PCB beneath carrier, optics down. Optical center nominalY136.5mm; bracket alone gives no stair protection.')
    for side in (-1,1):
        add('Downward_carrier_'+str(side),floor_carrier.translate((side*30,130,Z_TOP+1)),
            'PLA_accessories',BLUE,'new_design','explorer')
        for dx in (-6,6):
            add(f'Downward_carrier_screw_{side}_{dx}',bolt_z(side*30+dx,117,Z_TOP+8,10),
                'Added_fasteners_reference',SILVER,'proposed_hardware','explorer')
            add(f'Downward_carrier_nut_{side}_{dx}',nut_z(side*30+dx,117,Z_TOP-1.4),
                'Added_fasteners_reference',SILVER,'proposed_hardware','explorer')

    # Rear generic carrier: optional sensor uses straps; board-specific holes must be checked.
    carrier=box(34,14,3,0,0,0,radius=2)
    carrier=carrier.fuse(box(34,3,30,0,-5.5,0))
    for x in (-12,12):carrier=carrier.cut(cyl(clear/2,5,x,0,-1))
    for x in (-11,11):
        carrier=carrier.cut(box(3.2,6,17,x,-5.5,8,radius=1))
    add_print('07_rear_sensor_carrier',carrier,carrier.translate((0,-88,Z_DECK+d)),
        notes='Universal strap/slot carrier. Match exact sensor PCB before drilling extra holes. Optical face points rearward.')
    # Cable saddle: closed strap slots keep PLA out of a repeated flexure role.
    saddle=box(23,12,3,0,0,0,radius=2)
    saddle=saddle.cut(cyl(clear/2,5,0,0,-1))
    for x in (-8,8):saddle=saddle.cut(slot(7,2.4,5,x,0,-1,90))
    add_print('08_cable_tie_saddle',saddle,quantity=4,
        notes='Print4; M3 center fixing plus two cable-tie slots. Retain full head cable movement.')

    # Corrected optional servo plate is fitted to SOURCE TOP PLATE, not guessed Dead Plate alignment.
    adapter=box(37,43,3.2,5.5,86.6892,0,radius=3)
    adapter=adapter.cut(box(12.8,24.6,5,-.900185,86.689175,-1))
    for x,y in [(17.900215,86.689224),(17.899915,101.839124),(17.899915,71.539124)]:
        adapter=adapter.cut(cyl(clear/2,5,x,y,-1))
    for y in (72.439175,100.939175):
        adapter=adapter.cut(cyl(1.2,5,-.900185,y,-1))
    add_print('09_optional_servo_adapter',adapter,adapter.translate((0,0,Z_TOP)),
        notes='Optional replacement: remove stock Dead Plate. Top-plate3-hole row is sourced; SG90 opening/ear fit must be physically checked first.')

    # A Pi4 adapter uses standard board nominal hole coordinates; exact case not assumed.
    tray=box(96,65,2.8,0,-59,0,radius=4)
    tray=tray.cut(box(59,34,5,-4,-59,-1,radius=3))
    for x in (-39,19):
        for y in (-83.5,-34.5):
            tray=tray.fuse(cyl(3.5,6,x,y,2.8))
            tray=tray.cut(cyl(1.45,11,x,y,-1))
    for x in (-44,44):
        for y in (-74.5,-43.5):tray=tray.cut(cyl(clear/2,5,x,y,-1))
    add_print('10_optional_pi4_tray',tray,tray.translate((0,0,Z_DECK+d+4)),c=PURPLE,
        notes='Optional Pi4B board adapter,85x56mm board and58x49mm hole pitch, holes offset toward left of board. No electrical power system included.')
    short=ring(3.8,clear/2,4)
    add_print('11_pi_tray_spacer_4mm',short,quantity=4,notes='Print4 only if using optional Pi tray.')
    for i,(x,y) in enumerate([(x,y) for x in (-44,44) for y in (-74.5,-43.5)],1):
        add('Pi_tray_spacer_'+str(i),short.translate((x,y,Z_DECK+d)),
            'PLA_accessories',PURPLE,'new_design','explorer')
        add('Pi_tray_M3_screw_'+str(i),bolt_z(x,y,Z_DECK+d+6.8,14),
            'Added_fasteners_reference',SILVER,'proposed_hardware','explorer')
        add('Pi_tray_M3_nut_'+str(i),nut_z(x,y,Z_DECK-2.4),
            'Added_fasteners_reference',SILVER,'proposed_hardware','explorer')

    # Slim four-point fit frame reproduces the SOURCE TOP mounting pattern.
    # Test at final deck height on the4 printed spacers; a flat gauge at stock plate height
    # would cross the battery/controller. Replace only the4 top bolts, one at a time.
    gauge=box(122,6,2,0,-82.6668,0,radius=2)
    gauge=gauge.fuse(box(6,87,2,-55.456,-42.0,0,radius=2))
    gauge=gauge.fuse(box(6,87,2,56.544,-42.0,0,radius=2))
    gauge=gauge.fuse(box(118,6,2,.5,-2.16,0,radius=2))
    for x,y in deck_mounts:
        gauge=gauge.fuse(cyl(4.5,2,x,y,0)).cut(cyl(clear/2,4,x,y,-1))
    # Isolated calibration row connects to rear bar.
    cal=box(42,15,2,0,-90,0,radius=2)
    gauge=gauge.fuse(cal)
    for x,diam in [(-14,3.1),(-7,3.3),(0,3.5),(7,3.7),(14,3.9)]:
        gauge=gauge.cut(cyl(diam/2,4,x,-91,-1))
    add_print('00_mount_fit_gauge',gauge,notes='Print first WITH4deck spacers. Fit at36mm above top plate using loose long screws; do not seat this gauge on the battery or UNO. Hole ladder3.1,3.3,3.5,3.7,3.9mm left-to-right.')

def optional_hardware():
    # Optional payload is a reference assembly only, excluded from printable3MFs.
    z=Z_DECK+P['deck_thickness']+4+8.8
    pcb=box(85,56,1.6,0,-59,z,radius=2)
    for x in (-39,19):
        for y in (-83.5,-34.5):pcb=pcb.cut(cyl(1.45,4,x,y,z-1))
    add('OPTIONAL_Pi4B_PCB',pcb,'Optional_purchased_hardware',GREEN,'nominal_board_envelope','explorer')
    add('OPTIONAL_Pi4B_USB_stack',box(17,30,15,34,-65,z+1.6),'Optional_purchased_hardware',SILVER,
        'estimated_envelope','explorer')
    add('OPTIONAL_Pi4B_Ethernet',box(21,16,13,32,-39,z+1.6),'Optional_purchased_hardware',SILVER,
        'estimated_envelope','explorer')
    add('OPTIONAL_Pi4B_GPIO_header',box(51,5,8.5,-12,-82,z+1.6),'Optional_purchased_hardware',BLACK,
        'estimated_envelope','explorer')
    add('OPTIONAL_Pi4B_CPU',box(15,15,2,0,-57,z+1.6),'Optional_purchased_hardware',SILVER,
        'estimated_envelope','explorer')
    sensor=box(27,1.6,18,0,-97,Z_DECK+P['deck_thickness']+8)
    add('OPTIONAL_rear_ToF_board',sensor,'Optional_purchased_hardware',GREEN,'estimated_envelope','explorer',
        'Illustrative generic sensor PCB; carrier uses straps/slots, not claimed board-specific mounting.')
    add('OPTIONAL_ToF_optical_package',box(5,2,3,0,-99,Z_DECK+P['deck_thickness']+20),
        'Optional_purchased_hardware',BLACK,'estimated_envelope','explorer')
    for side in (-1,1):
        add('OPTIONAL_floor_ToF_board_'+str(side),box(27,18,1.6,side*30,136.5,Z_TOP-2.6),
            'Optional_purchased_hardware',GREEN,'estimated_envelope','explorer',
            'Illustrative board beneath carrier, tied through carrier slots; exact optical position and clearance need verification.')
        add('OPTIONAL_floor_ToF_optic_'+str(side),box(5,3,2,side*30,136.5,Z_TOP-4.6),
            'Optional_purchased_hardware',BLACK,'estimated_envelope','explorer')

def make_assembly(variant):
    asm=cq.Assembly(name='ELEGOO_V4_'+variant+'_mm')
    groups={}
    for p in parts:
        if p.variant not in ('both',variant):continue
        if p.group not in groups:groups[p.group]=cq.Assembly(name=p.group)
        groups[p.group].add(p.shape,name=p.name,color=color(p.color))
    for k,g in groups.items():asm.add(g,name=k)
    return asm

def tess(shape,tolerance=.06):
    vv,ff=shape.tessellate(tolerance,.15)
    v=np.array([p.toTuple() for p in vv],float);f=np.array(ff,np.int64)
    v,f,report=weld_mesh(v,f,tolerance=1e-6)
    return v,f

def export_geometry(output):
    output.mkdir(parents=True,exist_ok=True)
    for variant,name in [('stock','elegoo_v4_stock_reference.step'),('explorer','elegoo_v4_explorer.step')]:
        print('Export',name,flush=True)
        make_assembly(variant).export(str(output/name),exportType='STEP',mode='default')
    # Printable-only CAD uses separated objects laid flat. Useful for Fusion edits or slicer STEP import.
    printable_asm=cq.Assembly(name='ELEGOO_printable_parts_only_mm')
    for i,(name,item) in enumerate(prints.items()):
        x=(i%4)*190;y=(i//4)*190
        printable_asm.add(item['shape'].translate((x,y,0)),name=name,color=color(item['color']))
        cq.exporters.export(item['shape'],str(output/(name+'.stl')),tolerance=.04,angularTolerance=.12)
    printable_asm.export(str(output/'explorer_printable_parts.step'),exportType='STEP')

    # Separate generic3MF files are simple, portable, and cannot contain stock hardware by mistake.
    packs={
      '00_fit_check.3mf':['00_mount_fit_gauge','02_deck_spacer_36mm'],
      '01_deck.3mf':['01_slotted_deck'],
      '02_body_and_guard.3mf':['05_front_guard','03_side_guard_left','04_side_guard_right'],
      '03_mounts_and_spacers.3mf':['06_front_guard_spacer_4mm','07_rear_sensor_carrier','08_cable_tie_saddle','12_downward_sensor_carrier'],
      '04_optional_pi_tray.3mf':['10_optional_pi4_tray','11_pi_tray_spacer_4mm'],
      '05_optional_servo_adapter.3mf':['09_optional_servo_adapter'],
    }
    reports={}
    for filename,names in packs.items():
        print('Export',filename,flush=True)
        objects=[];x=4;y=4;row_height=0
        for name in names:
            item=prints[name];bb=item['shape'].BoundingBox()
            for n in range(item['quantity']):
                if x+bb.xlen>176:
                    x=4;y+=row_height+5;row_height=0
                if y+bb.ylen>176:
                    raise ValueError('Pack too large: '+filename)
                v,f=tess(item['shape'])
                v=v+np.array([x,y,0]);
                objects.append({'name':name+(f'_{n+1}' if item['quantity']>1 else ''),
                                'vertices':v,'faces':f,'color':item['color']})
                x+=bb.xlen+5;row_height=max(row_height,bb.ylen)
        report=write_3mf(output/filename,objects,title='ELEGOO V4 '+filename,
            description='PLA geometry only; millimeters; select your printer and filament in Bambu Studio. No G-code/profile.')
        reports[filename]=report
    (output/'mesh_export_validation.json').write_text(json.dumps(reports,indent=2))

def manifest(output):
    inventory=[]
    for p in parts:
        bb=p.shape.BoundingBox()
        inventory.append({'name':p.name,'group':p.group,'variant':p.variant,'evidence':p.evidence,
            'notes':p.notes,'bbox_mm':[bb.xmin,bb.ymin,bb.zmin,bb.xmax,bb.ymax,bb.zmax],
            'solid_count':len(p.shape.Solids()),'volume_mm3':p.shape.Volume(),'brep_valid':p.shape.isValid()})
    print_inventory=[]
    for name,p in prints.items():
        bb=p['shape'].BoundingBox();v,f=tess(p['shape'])
        print_inventory.append({'name':name,'quantity':p['quantity'],'bbox_mm':[bb.xlen,bb.ylen,bb.zlen],
            'solid_volume_mm3':p['shape'].Volume(),'notes':p['notes'],'brep_valid':p['shape'].isValid(),
            'mesh':mesh_stats(v,f),'part_file':name+'.stl'})
    data={'model_version':P['version'],'units':'millimeter','coordinate_convention':'X transverse; +Y front; +Z up. Ground is Z=0 for nominal65mm wheels.',
        'source_to_model':{'rotation_z_degrees':180,'source_center_xy':P['source_center_xy'],
            'z_translation':P['bottom_plate_underside_z']-SOURCE['plates'][0]['source_z_min']},
        'stock_plate_gap_preserved_mm':Z_TOP_BOTTOM-Z_BOTTOM_TOP,'top_surface_z_mm':Z_TOP,
        'limitations':['Reference hardware is simplified; do not use purchased-part envelopes as production drawings.',
            'Source Dead Plate hole pattern mismatches source Top Plate. Explorer variant shows a separate optional replacement adapter.',
            'STEP preserves separated solid geometry and names, not a native Fusion parametric timeline or joints.',
            'No application-level Fusion/Bambu opening or physical print test has been performed.',
            'Electrical power, wiring lengths, stair safety and autonomous navigation are outside this mechanical deliverable.'],
        'components':inventory,'printable_parts':print_inventory}
    (output/'component_manifest.json').write_text(json.dumps(data,indent=2))

def render(output):
    """Render actual BRep geometry using a display-independent Matplotlib backend."""
    from render_previews import render_views
    return render_views(parts, output)

def build():
    parts.clear();prints.clear()
    stock_plates();stock_hardware();servo_and_camera(False);servo_and_camera(True);addons();optional_hardware()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=HERE);parser.add_argument('--render',action='store_true');parser.add_argument('--manifest-only',action='store_true')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    build();print('Built',len(parts),'components;',len(prints),'print designs',flush=True)
    manifest(args.output)
    if not args.manifest_only:export_geometry(args.output)
    if args.render:render(args.output)

if __name__=='__main__':main()
