#!/usr/bin/env python3
"""Regression checks against exported delivery files; no hardware required."""
from pathlib import Path
import json,unittest,zipfile,xml.etree.ElementTree as ET
import cadquery as cq
import numpy as np
import trimesh
from PIL import Image

SOURCE_ROOT=Path(__file__).resolve().parent.parent
ROOT=SOURCE_ROOT

def load_step(p):
    return {n.split('/')[-1]:s.moved(l) for s,n,l,c in cq.Assembly.importStep(str(p))}

def bb(s):
    b=s.BoundingBox();return np.array([b.xmin,b.ymin,b.zmin,b.xmax,b.ymax,b.zmax])

class RevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.current=load_step(ROOT/'cad/rover_body_v3_with_snap_battery.step')
        cls.old=load_step(SOURCE_ROOT/'reference/previous_rover_roof_snap_v2.step')
        cls.m=json.loads((ROOT/'verification/manifest.json').read_text())

    def test_01_assembly_names_and_count(self):
        self.assertEqual(len(self.current),206);self.assertEqual(set(self.current),set(self.old))

    def test_02_tire_dimensions(self):
        for n,s in self.current.items():
            if n.startswith('Tire_'):
                b=bb(s);np.testing.assert_allclose(b[3:]-b[:3],[27.94,64.77,64.77],atol=1e-4)

    def test_03_wheelbase(self):
        for side in ['left','right']:
            a,b=(bb(self.current['Tire_'+side+'_'+end]) for end in ['front','rear'])
            self.assertAlmostEqual((a[1]+a[4]-b[1]-b[4])/2,76.2,places=5)

    def test_04_tire_gap(self):
        for side in ['left','right']:
            a,b=(bb(self.current['Tire_'+side+'_'+end]) for end in ['front','rear'])
            self.assertAlmostEqual(a[1]-b[4],11.43,places=5)

    def test_05_all_preserved_parts(self):
        names=self.m['changes']['preserved_names'];self.assertEqual(len(names),166)
        for n in names:
            old,new=self.old[n],self.current[n]
            np.testing.assert_allclose(bb(new),bb(old),atol=2e-5,rtol=0)
            self.assertAlmostEqual(old.Volume(),new.Volume(),delta=max(1e-4,old.Volume()*1e-7))
            self.assertEqual(len(old.Faces()),len(new.Faces()))

    def test_06_body_single_valid_solids(self):
        shell=load_step(ROOT/'cad/body_shell_v3.step');self.assertEqual(len(shell),6)
        for s in shell.values():self.assertTrue(s.isValid());self.assertEqual(len(s.Solids()),1)

    def test_07_open_between_tires(self):
        # Side-wall material formerly between front and rear tires must be absent.
        for side,n in [(-1,'body_01_left_side'),(1,'body_02_right_side')]:
            q=cq.Solid.makeBox(3,10,40,cq.Vector(side*69.8-1.5,-7,20))
            self.assertLess(self.current[n].intersect(q).Volume(),.001)

    def test_08_printed_meshes(self):
        paths=list((ROOT/'print').glob('*.stl'));self.assertEqual(len(paths),6)
        for p in paths:
            m=trimesh.load_mesh(p,process=True)
            self.assertTrue(m.is_watertight,p.name);self.assertTrue(m.is_winding_consistent,p.name)
            self.assertEqual(len(m.split(only_watertight=False)),1,p.name)
            self.assertLess(abs(m.bounds[0,2]),1e-5,p.name)
            self.assertLessEqual(max(m.extents[:2])+8,180.001,p.name)

    def test_09_3mf_format_and_positions(self):
        paths=list((ROOT/'print').glob('*.3mf'));self.assertEqual(len(paths),5)
        for p in paths:
            with zipfile.ZipFile(p) as z:
                self.assertIsNone(z.testzip());root=ET.fromstring(z.read('3D/3dmodel.model'))
                self.assertEqual(root.attrib.get('unit'),'millimeter')
                self.assertFalse(any(n.endswith(('.gcode','.gcode.3mf')) for n in z.namelist()))
            scene=trimesh.load(p,force='scene')
            self.assertGreaterEqual(scene.bounds[0,:2].min(),3.999)
            self.assertLessEqual(scene.bounds[1,:2].max(),176.001)

    def test_10_conservative_geometry_review(self):
        r=json.loads((ROOT/'verification/tolerance_envelope.json').read_text())
        self.assertGreaterEqual(r['minimum_gap_mm'],4.22)
        self.assertEqual(len(r['checks']),24)
        self.assertTrue(all(x['intersection_volume_mm3']<.01 for x in r['checks']))

    def test_11_mount_interfaces(self):
        r=json.loads((ROOT/'verification/preserved_interfaces.json').read_text())
        self.assertEqual(len(r['changed_panel_mount_interfaces']),16)
        self.assertTrue(all(x['symmetric_difference_mm3']<.001 for x in r['changed_panel_mount_interfaces']))

    def test_12_previews_not_blank(self):
        for p in (ROOT/'preview').glob('*.png'):
            im=np.array(Image.open(p).convert('RGB'));center=im[180:-100,100:-100]
            self.assertGreater(center.std(),20,p.name)
            self.assertGreater((center>50).mean(),.5,p.name)

if __name__=='__main__':
    import argparse,sys
    ap=argparse.ArgumentParser(add_help=False)
    ap.add_argument('--root',type=Path,default=ROOT)
    args,remaining=ap.parse_known_args()
    ROOT=args.root.resolve()
    unittest.main(argv=[sys.argv[0],*remaining],verbosity=2)

