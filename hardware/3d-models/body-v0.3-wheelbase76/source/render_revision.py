#!/usr/bin/env python3
"""Render actual STEP geometry with VTK. No AI-generated geometry or printer access."""
from pathlib import Path
import argparse,json
import numpy as np
import cadquery as cq
import vtk
from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parent.parent

def rgb(h):return tuple(int(h[i:i+2],16)/255 for i in (1,3,5))

def actor(shape,color):
    vv,ff=shape.tessellate(.12,.22)
    v=np.array([p.toTuple() for p in vv],float);f=np.array(ff,dtype=np.int64)
    pts=vtk.vtkPoints();pts.SetData(numpy_to_vtk(v,deep=True))
    cells=vtk.vtkCellArray();cells.ImportLegacyFormat(numpy_to_vtkIdTypeArray(np.column_stack([np.full(len(f),3),f]).ravel(),deep=True))
    pd=vtk.vtkPolyData();pd.SetPoints(pts);pd.SetPolys(cells)
    normal=vtk.vtkPolyDataNormals();normal.SetInputData(pd);normal.SetFeatureAngle(35);normal.SplittingOn();normal.ConsistencyOn();normal.AutoOrientNormalsOn();normal.Update()
    mapper=vtk.vtkPolyDataMapper();mapper.SetInputConnection(normal.GetOutputPort())
    a=vtk.vtkActor();a.SetMapper(mapper);a.GetProperty().SetColor(*rgb(color));a.GetProperty().SetAmbient(.30);a.GetProperty().SetDiffuse(.65);a.GetProperty().SetSpecular(.12);a.GetProperty().SetSpecularPower(25)
    return a

def font(n,bold=False):
    return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans'+('-Bold' if bold else '')+'.ttf',n)

def render(shapes,path,*,side=False,title='',subtitle='',dimension=False):
    ren=vtk.vtkRenderer();ren.SetBackground(.963,.973,.983);ren.SetUseFXAA(False)
    for shape,color in shapes:ren.AddActor(actor(shape,color))
    rw=vtk.vtkRenderWindow();rw.AddRenderer(ren);rw.SetSize(1760,1220);rw.SetOffScreenRendering(1);rw.SetMultiSamples(0)
    camera=ren.GetActiveCamera()
    camera.SetFocalPoint(0,0,100)
    camera.SetPosition(*((-520,0,100) if side else (-370,470,310)))
    camera.SetViewUp(0,0,1);camera.ParallelProjectionOn();camera.SetParallelScale(133 if side else 155)
    ren.ResetCameraClippingRange();rw.Render()
    w=vtk.vtkWindowToImageFilter();w.SetInput(rw);w.SetInputBufferTypeToRGB();w.ReadFrontBufferOff();w.Update()
    writer=vtk.vtkPNGWriter();writer.SetFileName(str(path));writer.SetInputConnection(w.GetOutputPort());writer.Write()
    im=Image.open(path).convert('RGB')
    if np.asarray(im)[120:-80,100:-100].std()<10: raise RuntimeError('Blank rendering buffer')
    d=ImageDraw.Draw(im)
    d.rectangle((0,0,1760,112),fill=(245,248,251))
    d.text((50,25),title,font=font(35,True),fill='#173143')
    d.text((50,73),subtitle,font=font(23),fill='#536879')
    if dimension:
        cfg=json.loads((ROOT/'source'/'body_reference_parameters.json').read_text())
        def project(p):
            ren.SetWorldPoint(*p,1);ren.WorldToDisplay();x,y,_=ren.GetDisplayPoint();return x,1220-y
        coords=[]
        for cy in [cfg['reference_front_axle_y'],cfg['reference_rear_axle_y']]:
            x,y=project((-87,cy,64.77/2));coords.append((x,y))
            d.ellipse((x-6,y-6,x+6,y+6),fill='#E58C2F',outline='white',width=1)
        x1,y1=coords[0];x2,y2=coords[1];basey=max(y1,y2)+202
        for x,y in coords:d.line((x,y+12,x,basey+9),fill='#536879',width=2)
        d.line((x1,basey,x2,basey),fill='#173143',width=3)
        for x,sgn in [(x1,1),(x2,-1)]:d.polygon([(x,basey),(x+sgn*14,basey-7),(x+sgn*14,basey+7)],fill='#173143')
        text='76.2 mm wheelbase';bb=d.textbbox((0,0),text,font=font(24,True));tw=bb[2]
        cx=(x1+x2)/2;d.rectangle((cx-tw/2-10,basey-18,cx+tw/2+10,basey+20),fill=(245,248,251));d.text((cx-tw/2,basey-15),text,font=font(24,True),fill='#173143')
    d.rectangle((0,1153,1760,1220),fill=(232,239,245))
    d.text((50,1167),'CAD reference only  |  Approximate measured tires: 64.77 x 27.94 mm  |  Print fit templates first',font=font(21),fill='#334F63')
    im.save(path);rw.Finalize()


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=ROOT);args=ap.parse_args();r=args.root
    manifest=json.loads((r/'verification'/'manifest.json').read_text());colors={p['name']:p['color'] for p in manifest['components']}
    a=cq.Assembly.importStep(str(r/'cad'/'rover_body_v3_with_snap_battery.step'))
    shapes=[(s.moved(l),colors.get(n.split('/')[-1],'#617689')) for s,n,l,c in a]
    render(shapes,r/'preview'/'revised_rover_v3.png',title='ELEGOO V4 | wheelbase-corrected body',subtitle='Open wheel bays • existing deck, Pi tray, roof and snap-lid battery mount retained')
    render(shapes,r/'preview'/'revised_side_view.png',side=True,dimension=True,title='Side view | no body strip between the tires',subtitle='Front is left. Continuous wheel bay replaces the two tightly fitted arches.')
    import build_revision as build
    gauges=build.make_gauges()
    a=cq.Assembly.importStep(str(r/'cad'/'open_rover_v3_reference.step'))
    shapes=[(s.moved(l),colors.get(n.split('/')[-1],'#617689')) for s,n,l,c in a]
    shapes.extend((x['design_shape'],x['color']) for x in gauges.values())
    render(shapes,r/'preview'/'fit_templates_installed.png',side=True,dimension=True,title='Print these first | temporary wheel-clearance templates',subtitle='Orange rail bolts under the existing deck; its lower edge matches the new wheel opening.')
    print('Rendered 3 views from actual STEP/BRep geometry')

if __name__=='__main__':main()
