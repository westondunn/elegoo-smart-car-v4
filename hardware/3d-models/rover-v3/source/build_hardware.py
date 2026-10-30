"""Reference hardware for the V3 full assembly; all dimensions are millimetres.

These are deliberately labelled envelopes, not reverse-engineered production
models. Only the user's measured bank/block/head dimensions and source mounting
patterns are treated as known. The printed interfaces are authored separately.
"""
from pathlib import Path
import json, hashlib, math
import cadquery as cq

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'cad' / 'generated_hardware'
ASSETS = OUT / 'assets'
IDENTITY = [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]
parts, joints, shapes = [], [], {}

def box(w,d,h,x=0,y=0,z=0,fillet=0):
    a = cq.Workplane('XY').box(w,d,h,centered=(True,True,False))
    if fillet:
        a = a.edges('|Z').fillet(fillet)
    return a.val().translate((x,y,z))

def cylinder(radius,length,start,axis=(0,0,1)):
    return cq.Solid.makeCylinder(radius,length,cq.Vector(*start),cq.Vector(*axis))

def combine(*items):
    return cq.Compound.makeCompound(list(items))

def holes_z(shape,xy,diameter,z0,length):
    for x,y in xy:
        shape = shape.cut(cylinder(diameter/2,length,(x,y,z0)))
    return shape

def add(pid,name,shape,category,color,fidelity,notes='',material='',source=None):
    assert shape.isValid(), pid
    solids = shape.Solids()
    assert solids and all(s.Volume()>0 for s in solids),pid
    ASSETS.mkdir(parents=True,exist_ok=True)
    path=ASSETS/(pid+'.step')
    cq.exporters.export(shape,str(path))
    cq.exporters.export(shape,str(ASSETS/(pid+'.stl')),tolerance=.12,angularTolerance=.15)
    b=shape.BoundingBox()
    part=dict(id=pid,name=name,step_file='assets/hardware/'+pid+'.step',category=category,
        color_rgba=list(color)+[255],transform_mm=IDENTITY,physical_material=material,
        fidelity=fidelity,notes=notes,quantity=1,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        source=source or 'Rover reference model; original installed hardware remains authoritative',
        source_asset=str(path),solid_count=len(solids),volume_mm3=shape.Volume(),
        bounds_mm=[[b.xmin,b.ymin,b.zmin],[b.xmax,b.ymax,b.zmax]])
    parts.append(part); shapes[pid]=shape
    return pid

def rigid(pid,parent):
    joints.append(dict(id='fix_'+pid,name='Installed - '+pid,type='rigid',part_a=parent,part_b=pid,enabled=True))

def revolute(pid,parent,origin,axis=(1,0,0),limits=None):
    j=dict(id='rotate_'+pid,name='Reference motion - '+pid,type='revolute',part_a=parent,part_b=pid,
           origin_mm=list(origin),axis=list(axis),enabled=True,
           notes='Nominal demonstration axis; confirm on the physical component before motion-envelope conclusions.')
    if limits:j['limits_deg']=limits
    joints.append(j)

def make_board(pid,name,w,d,center,z,holes,ports,notes,color=(38,132,87)):
    x,y=center
    board=holes_z(box(w,d,1.6,x,y,z,1.2),holes,2.9,z-.1,1.8)
    add(pid,name+' - PCB reference',board,'electronics',color,'Mounting pattern sourced; PCB outline nominal',notes,
        material={'name':'','basis':'Composite PCB; no single bulk material or mass assigned'})
    rigid(pid,'upper_deck')
    components=[]
    for q in ports:
        components.append(box(*q))
    if components:
        add(pid+'_connectors',name+' - connector envelopes',combine(*components),'electronics',(165,174,183),
            'Approximate connector envelopes','Connector locations are representative. Actual board revision is unconfirmed; existing cables remain authoritative.')
        rigid(pid+'_connectors',pid)
    return board

def build():
    layout=json.loads((ROOT/'source/assembly_layout.json').read_text())
    # The fixed bank size is from the user's latest explicit measurement.
    add('power_bank','Flat power bank - 69.85 x 146.05 x 12.7',box(69.85,146.05,12.7,0,0,4.5,2),
        'battery',(53,62,74),'User measured outer envelope','Ports intentionally not guessed. Open rail ends and straps retain the pack.',
        source='User: 2 3/4 x 5 3/4 x 1/2 inch; tray adds 1/16 inch on each side')
    rigid('power_bank','base')

    # Prior nominal motor-battery case. Its known spacing problem is accommodated
    # by the printed slot; the body and port locations are not measured claims.
    battery=box(86,52,22,0,-73,48.6,2)
    battery=holes_z(battery,[(-38,-73),(38,-73)],3.2,48.5,4.1)
    add('motor_battery','Motor battery - nominal case',battery,'battery',(40,45,53),
        'Nominal 86 x 52 x 22; not a measured case model','76 mm nominal mount pitch, adjustable printed range65–90 mm. Rear orientation is preferred; check actual plug engagement before tightening.')
    rigid('motor_battery','upper_deck')
    add('motor_battery_switch','Motor battery - rear switch reference',box(10,3,4,0,-100,56.6),
        'electronics',(66,73,81),'Approximate location and shape','Switch location conveys rear orientation only.')
    rigid('motor_battery_switch','motor_battery')

    pi_holes=[(x,y) for x in(-62.5,-13.5) for y in(0,58)]
    make_board('pi_board','Raspberry Pi format board',56,85,(-38,19),54.6,pi_holes,
        [(14,17,15,-25,-16.5,56.2),(16,21,15,-47,-15.5,56.2),(7,12,4,-65,31,56.2),
         (5,51,8,-13.5,27,56.2)],
        '58 x 49 mm mounting pattern. Exact Pi generation is unconfirmed; generic 85 x56 board outline and connector blocks are for packaging only.')
    add('pi_processor','Pi - processor reference',box(15,15,2,-38,24,56.2),
        'electronics',(61,66,73),'Approximate','No heatsink/fan assumption and no thermal simulation.')
    rigid('pi_processor','pi_board')

    uno_holes=[(20.297005,49.8),(48.164009,49.8),(15.8,-1.859792)]
    make_board('uno_board','ELEGOO Uno format board',53.4,68.6,(38,19),54.6,uno_holes,
        [(12,16,11,24,-11.5,56.2),(9,13,11,53,-10.5,56.2),
         (3,50,9,15.5,21,56.2),(3,50,9,60.5,21,56.2)],
        'Three-hole mount comes from the original OEM top plate; 68.6 x53.4 outer rectangle is a simplified reference.',(38,97,160))
    shield=box(53.4,54,1.6,38,27,65.2,1)
    add('motor_shield','ELEGOO motor shield - reference envelope',shield,'electronics',(42,106,169),
        'Nominal stacked board envelope','Actual shield revision not identified. OEM2020 DRV8835 schematic and New repository firmware are separate references.')
    rigid('motor_shield','uno_board')
    headers=combine(*[box(8,5,9,x,y,66.8) for x in(19,57) for y in(9,24,39)])
    add('shield_connectors','Motor shield - plug envelopes',headers,'electronics',(233,233,221),
        'Approximate','Existing plugs and routing remain authoritative.')
    rigid('shield_connectors','motor_shield')

    # The stock contact planes/pairs constrain the printed part. These separately
    # labelled motor and wheel envelopes do NOT establish print fit or joint axes.
    mx=layout['motor_holes']['x_mm'][1]
    for front,ymid in [('front',sum(layout['motor_holes']['front_pair_y_mm'])/2),
                       ('rear',sum(layout['motor_holes']['rear_pair_y_mm'])/2)]:
      direction=1 if front=='front' else -1
      for side,sign in [('left',-1),('right',1)]:
        p=f'{front}_{side}';x=sign*mx
        block=holes_z(box(22,12,4,x,ymid,4.5),[(x,ymid-3.9),(x,ymid+3.9)],3.2,4.4,4.2)
        add('block_'+p,'Silver motor block - '+p,block,'hardware',(186,192,200),
            'User outer22 x12 x4; OEM/C1 hole pattern','Block orientation/height in assembly is nominal; the base interface comes from the physically successful C1/C3 geometry.',material='Aluminum')
        rigid('block_'+p,'base')
        # Illustrative axis toward the wheel-relief middle, not a measurement.
        # The official archive contains plates only; moving this reference must
        # never move a printed motor hole or replace the user's physical fit test.
        axis_y=ymid-direction*20
        axis_z=19.5
        gearbox=box(18,37,22,x,axis_y+direction*12.5,8.5,3)
        add('motor_'+p,'TT motor gearbox reference - '+p,gearbox,'motor',(235,179,36),
            'Nominal TT envelope; shaft axis approximate','Axis is a motion demonstration only. OEM archive does not include motor geometry. Keep the stock motor and silver block assembly intact.',
            source='https://docs.sunfounder.com/projects/sf-components/en/latest/component_tt_motor.html (generic TT motor, not an identified ELEGOO part)')
        rigid('motor_'+p,'block_'+p)
        can=box(18,29,18,x,axis_y+direction*45.5,10.5,3)
        add('motor_can_'+p,'Motor can reference - '+p,can,'hardware',(165,170,178),
            'Nominal 70 mm total TT body length','Representative motor can envelope.',material='Steel')
        rigid('motor_can_'+p,'motor_'+p)
        # Place reference wheels wholly outboard of the preserved relief, with
        # a visible gap. This is NOT a measured assertion of user's wheel offset.
        relief=mx+21.5
        wheel_inner=relief+3.5
        width=26.; wheel_start=wheel_inner if sign>0 else -wheel_inner-width
        hub=cylinder(18,width,(wheel_start,axis_y,axis_z),(1,0,0))
        hub=hub.cut(cylinder(2.7,width+.2,(wheel_start-.1,axis_y,axis_z),(1,0,0)))
        add('wheel_hub_'+p,'Wheel hub reference - '+p,hub,'wheel',(226,180,45),
            'Nominal wheel envelope','Wheel model is illustrative; local motor-to-wheel clearance remains based on the successful physical fit, not this nominal solid.')
        revolute('wheel_hub_'+p,'motor_'+p,(sign*wheel_inner,axis_y,axis_z))
        tire=cylinder(32.5,width,(wheel_start,axis_y,axis_z),(1,0,0)).cut(cylinder(18,width+.2,(wheel_start-.1,axis_y,axis_z),(1,0,0)))
        add('tire_'+p,'Tire reference - '+p,tire,'wheel',(36,40,45),
            'Nominal 65 mm diameter x26 mm width','No claim of measured diameter, traction or clearance sweep.',material='Rubber')
        rigid('tire_'+p,'wheel_hub_'+p)
        shaft_start=x-17 if sign<0 else x-9
        shaft=cylinder(2.7,26,(shaft_start,axis_y,axis_z),(1,0,0))
        add('shaft_'+p,'Output shaft reference - '+p,shaft,'hardware',(214,218,222),
            'Approximate shaft envelope','Shaft projection not reverse engineered; rotation is kinematic only.')
        rigid('shaft_'+p,'wheel_hub_'+p)

    # Front scanning head: reuse original assembly. Only the printed interface is
    # sourced; the servo/sonar/camera shapes are representative packaging volumes.
    sx,sy=0.916,86.684
    servo=box(12,23,22,sx,sy,29,1.2)
    add('pan_servo','Stock pan servo - reference',servo,'electronics',(38,94,158),
        'Approximate SG90-type envelope','Head support uses source OEM front interface; original bracket/horn are reused.')
    rigid('pan_servo','upper_deck')
    horn=cylinder(7,2.5,(sx,sy,51))
    add('servo_horn','Stock servo horn - reference',horn,'hardware',(231,230,213),
        'Approximate','Do not use this reference model to print a replacement horn.')
    revolute('servo_horn','pan_servo',(sx,sy,52),(0,0,1),[-80,80])
    holder=box(48,6,39,sx,sy,54,1)
    add('sensor_head','Original head bracket - reference',holder,'hardware',(70,74,82),
        'Approximate','Retain the original complete camera/sonar bracket assembly.')
    rigid('sensor_head','servo_horn')
    sonar=box(45,1.6,20,sx,sy+4,58)
    add('ultrasonic_board','Ultrasonic sensor - reference',sonar,'electronics',(42,106,170),
        'Approximate 45 x20 board','Original sensor and bracket retained; no inferred mounting-hole or electrical pinout.')
    rigid('ultrasonic_board','sensor_head')
    speakers=combine(*[cylinder(8,12,(sx+dx,sy+4.8,68),(0,1,0)) for dx in(-13,13)])
    add('sonar_transducers','Ultrasonic transducers - reference',speakers,'electronics',(186,191,197),
        'Approximate','Representative sensing head, not acoustic or electrical simulation.')
    rigid('sonar_transducers','ultrasonic_board')
    camera=box(24,1.6,18,sx,sy+4,80)
    add('camera_board','ESP32/camera head - reference',camera,'electronics',(48,113,74),
        'Approximate envelope','Exact camera board and orientation unconfirmed. Original assembly is reused.')
    rigid('camera_board','sensor_head')
    lens=cylinder(4.5,6,(sx,sy+4.8,89),(0,1,0))
    add('camera_lens','Camera lens - reference',lens,'electronics',(40,44,49),'Approximate','Display reference only.')
    rigid('camera_lens','camera_board')

    tracker_holes=layout['line_tracker']['holes_xy_mm']
    tracker_y=sum(p[1] for p in tracker_holes)/4
    tracker=box(45,30,1.6,0,tracker_y,-4.6,1)
    tracker=holes_z(tracker,tracker_holes,3.2,-4.7,1.8)
    add('line_tracker','Original line tracker - reference',tracker,'electronics',(39,95,155),
        'Original OEM lower-plate mounting pattern','Sensor height is a provisional assembly position; adjust using the removable spacers and actual wheel/ground geometry.')
    rigid('line_tracker','base')
    sensors=combine(*[box(4,6,3,x,tracker_y,-7.6) for x in(-15,0,15)])
    add('tracker_sensors','Line sensors - reference',sensors,'electronics',(35,39,45),'Approximate','Actual road gap must be checked at assembly.')
    rigid('tracker_sensors','line_tracker')
    report=dict(format_version=1,units='mm',parts=parts,joints=joints,
       limitations=['Hardware solids are simplified reference envelopes; no reverse-engineered components claimed.',
       'No assembly mass/centre-of-gravity or thermal/strength prediction is claimed.',
       'Wheel/servo motion axes are nominal and must be checked before motion-clearance conclusions.'])
    (OUT/'hardware_manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'parts':len(parts),'joints':len(joints),'manifest':str(OUT/'hardware_manifest.json')},indent=2))

if __name__=='__main__':
    build()
