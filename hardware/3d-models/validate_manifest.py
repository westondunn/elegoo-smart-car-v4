#!/usr/bin/env python3
"""Validate hardware/3d-models/manifest.json against the files in the repository.

Default checks (standard library only, a few seconds):
  * every manifest asset exists, with matching byte size and SHA-256;
  * every file under hardware/3d-models is either a manifest asset or a
    maintained support file (README, manifest, this script, .gitattributes,
    reference/, validation/);
  * relative Markdown links in hardware/3d-models and docs/hardware resolve.

--geometry adds format checks (numpy optional, used when present):
  * STEP: declared length unit, PRODUCT and MANIFOLD_SOLID_BREP counts,
    approximate bounding box from CARTESIAN_POINT extents;
  * 3MF: model unit, object/mesh counts, mesh bounding box, edge-manifold and
    consistent-orientation test, Bambu project/G-code presence;
  * STL: binary header parse, triangle count, bounding box, edge-manifold and
    orientation test, signed volume. STL encodes no units.

Nothing here opens Fusion or a slicer. Passing these checks says the files are
intact and parse; it does not prove printability or physical fit.

Usage:
  python hardware/3d-models/validate_manifest.py
  python hardware/3d-models/validate_manifest.py --geometry --report out.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
import zipfile
from collections import Counter
from pathlib import Path
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
MANIFEST = HERE / "manifest.json"
SUPPORT_FILES = {"README.md", "manifest.json", "validate_manifest.py", ".gitattributes"}
SUPPORT_DIRS = {"reference", "validation"}
DOC_DIRS = [HERE, REPO / "docs" / "hardware"]
NS = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ----------------------------------------------------------------------------- manifest
def check_manifest(problems: list[str]) -> dict:
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for key in ("schema_version", "recommended_revision", "families", "assets", "not_imported"):
        if key not in m:
            problems.append(f"manifest missing key: {key}")
    if m.get("recommended_revision") not in m.get("families", {}):
        problems.append("recommended_revision is not a listed family")
    seen = set()
    for a in m.get("assets", []):
        rel = a.get("repo_path", "")
        p = REPO / rel
        if rel in seen:
            problems.append(f"duplicate manifest entry: {rel}")
        seen.add(rel)
        for key in ("sha256", "bytes", "family", "role", "validation_status"):
            if key not in a:
                problems.append(f"{rel}: missing field {key}")
        if a.get("family") not in m.get("families", {}):
            problems.append(f"{rel}: unknown family {a.get('family')}")
        if not p.is_file():
            problems.append(f"missing file: {rel}")
            continue
        if p.stat().st_size != a.get("bytes"):
            problems.append(f"size mismatch: {rel} ({p.stat().st_size} != {a.get('bytes')})")
        if sha256(p) != a.get("sha256"):
            problems.append(f"sha256 mismatch: {rel}")
    for f in sorted(HERE.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(REPO).as_posix()
        top = f.relative_to(HERE).parts[0]
        if rel in seen or f.name in SUPPORT_FILES and f.parent == HERE or top in SUPPORT_DIRS:
            continue
        problems.append(f"file not listed in manifest: {rel}")
    return m


def check_links(problems: list[str]) -> int:
    count = 0
    # Imported package documentation under source/ is kept verbatim and is not link-checked.
    files = [p for d in DOC_DIRS for p in d.rglob("*.md") if "source" not in p.relative_to(REPO).parts] + [REPO / "README.md"]
    for md in files:
        text = md.read_text(encoding="utf-8", errors="replace")
        for raw in LINK_RE.findall(text):
            if raw.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = raw.split("#", 1)[0]
            if not target:
                continue
            resolved = (md.parent / target).resolve()
            count += 1
            if not resolved.exists():
                problems.append(f"broken link in {md.relative_to(REPO).as_posix()}: {raw}")
    return count


# ----------------------------------------------------------------------------- geometry
def _mesh_checks(tris) -> dict:
    """tris: iterable of (i0,i1,i2) vertex index triples. Returns manifold stats."""
    edges: Counter[tuple[int, int]] = Counter()
    directed: Counter[tuple[int, int]] = Counter()
    n = 0
    for a, b, c in tris:
        n += 1
        for u, v in ((a, b), (b, c), (c, a)):
            directed[(u, v)] += 1
            edges[(u, v) if u < v else (v, u)] += 1
    non_manifold = sum(1 for e, k in edges.items() if k != 2)
    inconsistent = sum(1 for (u, v), k in directed.items() if directed.get((v, u), 0) != k)
    return {"triangles": n, "edges": len(edges), "edges_not_shared_by_exactly_two": non_manifold,
            "inconsistently_oriented_edge_pairs": inconsistent,
            "closed_and_consistent": non_manifold == 0 and inconsistent == 0}


def _signed_volume(verts, tris) -> float:
    vol = 0.0
    for a, b, c in tris:
        x0, y0, z0 = verts[a]
        x1, y1, z1 = verts[b]
        x2, y2, z2 = verts[c]
        vol += (x0 * (y1 * z2 - z1 * y2) - y0 * (x1 * z2 - z1 * x2) + z0 * (x1 * y2 - y1 * x2))
    return vol / 6.0


def _bbox(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    return [round(min(xs), 3), round(min(ys), 3), round(min(zs), 3), round(max(xs), 3), round(max(ys), 3), round(max(zs), 3)]


def check_step(p: Path) -> dict:
    data = p.read_bytes().decode("latin1")
    unit = re.search(r"SI_UNIT\s*\(\s*(\.\w+\.|\$)\s*,\s*\.(METRE|INCH)\.", data)
    products = re.findall(r"\bPRODUCT\s*\(\s*'([^']*)'", data)
    solids = len(re.findall(r"MANIFOLD_SOLID_BREP", data))
    pts = re.findall(r"CARTESIAN_POINT\s*\(\s*'[^']*'\s*,\s*\(\s*([-+0-9.Ee]+)\s*,\s*([-+0-9.Ee]+)\s*,\s*([-+0-9.Ee]+)\s*\)", data)
    out = {"format": "STEP AP214" if "AUTOMOTIVE_DESIGN" in data[:4000] else "STEP",
           "length_unit": ("mm" if unit and unit.groups() == (".MILLI.", "METRE") else (unit.group(0) if unit else "not found")),
           "product_entities": len(products), "manifold_solids": solids,
           "cartesian_point_count": len(pts),
           "approx_bbox_from_points_mm": _bbox([(float(x), float(y), float(z)) for x, y, z in pts]) if pts else None,
           "note": "bounding box from CARTESIAN_POINT entities (control points/vertices) is approximate; no B-rep kernel used"}
    out["ok"] = out["length_unit"] == "mm" and solids > 0
    return out


def check_stl(p: Path) -> dict:
    raw = p.read_bytes()
    if len(raw) < 84:
        return {"ok": False, "error": "file too small for binary STL"}
    n = struct.unpack("<I", raw[80:84])[0]
    if 84 + n * 50 != len(raw):
        return {"ok": False, "error": "size does not match binary STL triangle count (ASCII STL not handled)"}
    verts: dict[tuple[float, float, float], int] = {}
    tris: list[tuple[int, int, int]] = []
    points: list[tuple[float, float, float]] = []
    for i in range(n):
        off = 84 + i * 50 + 12
        tri = []
        for k in range(3):
            v = struct.unpack("<3f", raw[off + 12 * k: off + 12 * k + 12])
            idx = verts.get(v)
            if idx is None:
                idx = len(points)
                verts[v] = idx
                points.append(v)
            tri.append(idx)
        tris.append((tri[0], tri[1], tri[2]))
    out: dict = {"format": "binary STL", "units": "not encoded", "vertices_after_weld": len(points),
                 "bbox": _bbox(points), "signed_volume": round(_signed_volume(points, tris), 3)}
    out.update(_mesh_checks(tris))
    out["ok"] = bool(out["closed_and_consistent"]) and out["signed_volume"] > 0
    return out


def check_3mf(p: Path) -> dict:
    z = zipfile.ZipFile(p)
    names = z.namelist()
    out: dict = {"entries": len(names), "gcode_files": sum(1 for n in names if n.endswith(".gcode")),
                 "bambu_project_settings": "Metadata/project_settings.config" in names, "models": []}
    units: set[str | None] = set()
    all_ok = True
    for n in names:
        if not n.endswith(".model"):
            continue
        root = ET.fromstring(z.read(n))
        units.add(root.get("unit"))
        for o in root.iter(NS + "object"):
            mesh = o.find(NS + "mesh")
            if mesh is None:
                continue
            vs = mesh.find(NS + "vertices")
            ts = mesh.find(NS + "triangles")
            points = [(float(v.get("x", "0")), float(v.get("y", "0")), float(v.get("z", "0"))) for v in vs] if vs is not None else []
            tris = [(int(t.get("v1", "0")), int(t.get("v2", "0")), int(t.get("v3", "0"))) for t in ts] if ts is not None else []
            rec: dict = {"model_file": n, "object_id": o.get("id"), "name": o.get("name"), "vertices": len(points)}
            if points and tris:
                rec["bbox"] = _bbox(points)
                rec["signed_volume"] = round(_signed_volume(points, tris), 3)
                rec.update(_mesh_checks(tris))
                rec["ok"] = bool(rec["closed_and_consistent"]) and rec["signed_volume"] > 0
            else:
                rec["ok"] = False
                rec["error"] = "empty mesh"
            all_ok = all_ok and bool(rec["ok"])
            out["models"].append(rec)
    if "Metadata/project_settings.config" in names:
        cfg = json.loads(z.read("Metadata/project_settings.config"))
        out["printer_model"] = cfg.get("printer_model")
        out["print_settings_id"] = cfg.get("print_settings_id")
        out["filament_type"] = cfg.get("filament_type")
        out["curr_bed_type"] = cfg.get("curr_bed_type")
    if "Metadata/slice_info.config" in names:
        s = z.read("Metadata/slice_info.config").decode("utf8", "replace")
        out["sliced_plates"] = len(re.findall(r"<plate>", s))
        out["predicted_seconds"] = [int(x) for x in re.findall(r'key="prediction" value="(\d+)"', s)]
        out["filament_grams"] = [float(x) for x in re.findall(r'key="weight" value="([\d.]+)"', s)]
    out["units"] = "/".join(sorted(u for u in units if u))
    out["ok"] = all_ok and out["units"] == "millimeter" and bool(out["models"])
    return out


def check_geometry(m: dict, problems: list[str]) -> dict:
    results = {}
    for a in m["assets"]:
        rel = a["repo_path"]
        p = REPO / rel
        ext = p.suffix.lower()
        try:
            if ext == ".step":
                r = check_step(p)
            elif ext == ".stl":
                r = check_stl(p)
            elif ext == ".3mf":
                r = check_3mf(p)
            else:
                continue
        except Exception as exc:  # noqa: BLE001 - report, do not abort
            r = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        results[rel] = r
        if not r.get("ok"):
            problems.append(f"geometry check failed: {rel}: {r.get('error', 'see report')}")
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--geometry", action="store_true", help="also parse STEP/3MF/STL files")
    ap.add_argument("--report", type=Path, help="write a JSON report here")
    args = ap.parse_args()
    problems: list[str] = []
    m = check_manifest(problems)
    links = check_links(problems)
    report = {"manifest_assets": len(m.get("assets", [])), "links_checked": links, "problems": problems}
    if args.geometry:
        report["geometry"] = check_geometry(m, problems)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"assets: {report['manifest_assets']}  links checked: {links}  problems: {len(problems)}")
    for p in problems:
        print("  -", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
