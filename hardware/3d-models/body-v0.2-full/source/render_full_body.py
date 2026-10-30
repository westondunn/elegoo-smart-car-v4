#!/usr/bin/env python3
"""Render an actual full-body CAD assembly without OpenGL or a display server.

Public entry point::

    render_views(parts, output_dir, body_names=body_names,
                 explode_offsets={"roof": (0, 0, 80)}, print_parts=prints)

``parts`` contains components with shape, name, group, color, and variant
attributes. It should already represent the intended assembly; optional
``variant`` filtering keeps that variant and ``both``. No CAD dimensions or
shapes are changed. Exploded translations apply only to copied render meshes.
All surfaces are tessellated from BRep CAD; this is not an illustrative model.
"""

from __future__ import annotations

import argparse
import importlib.util
import math
import sys
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgb
from matplotlib.patches import Patch
from mpl_toolkits.mplot3d import proj3d
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np


BG = "#FAFBFC"
INK = "#172B3A"
SECONDARY = "#5D6C79"
BODY_BLUE = "#304D69"
BODY_GRAY = "#606C78"
ORANGE = "#E78939"

DEFAULT_BODY_OFFSETS = {
    "body_01_left_side": (-60, 0, 5),
    "body_02_right_side": (60, 0, 5),
    "body_03_rear_panel": (0, -64, 6),
    "body_04_front_bulkhead": (0, 96, 90),
    "body_05_removable_roof": (0, 0, 65),
    "body_06_front_cowl": (0, 52, 14),
}


def _triangles(shape, tolerance: float, angular_tolerance: float, *, uniform=False):
    """Tessellate exact surfaces, then subdivide broad coplanar triangles.

    The original explorer renderer subdivided every long triangle four ways.
    Longest-edge bisection preserves the exact planes while avoiding excessive
    triangle growth around the body's long, narrow ventilation openings.
    """
    vertices, faces = shape.tessellate(tolerance, angular_tolerance)
    vertices = np.asarray([v.toTuple() for v in vertices], dtype=float)
    faces = np.asarray(faces, dtype=np.int64)
    if not len(vertices) or not len(faces):
        raise ValueError("A component returned no BRep tessellation")
    triangles = vertices[faces]
    for _ in range(24):
        lengths_squared = np.sum(
            (triangles - np.roll(triangles, -1, axis=1)) ** 2, axis=2
        )
        split = lengths_squared.max(axis=1) > 8.0**2
        if not split.any():
            break
        large = triangles[split]
        if uniform:
            a, b, c = large[:, 0], large[:, 1], large[:, 2]
            ab, bc, ca = (a + b) / 2, (b + c) / 2, (c + a) / 2
            children = np.concatenate((np.stack((a, ab, ca), axis=1),
                                       np.stack((ab, b, bc), axis=1),
                                       np.stack((ca, bc, c), axis=1),
                                       np.stack((ab, bc, ca), axis=1)))
        else:
            longest = lengths_squared[split].argmax(axis=1)
            rows = np.arange(len(large))
            a = large[rows, longest]
            b = large[rows, (longest + 1) % 3]
            c = large[rows, (longest + 2) % 3]
            midpoint = (a + b) / 2
            children = np.concatenate((np.stack((a, midpoint, c), axis=1),
                                       np.stack((midpoint, b, c), axis=1)))
        triangles = np.concatenate((triangles[~split], children))
    normals = np.cross(triangles[:, 1] - triangles[:, 0],
                       triangles[:, 2] - triangles[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    valid = lengths > 1e-12
    triangles, normals, lengths = triangles[valid], normals[valid], lengths[valid]
    if not len(triangles):
        raise ValueError("A component returned only degenerate triangles")
    return triangles, normals / lengths[:, None]


def _face_colors(normals, color):
    key = np.array([0.36, 0.44, 0.82])
    fill = np.array([-0.68, -0.25, 0.69])
    key /= np.linalg.norm(key)
    fill /= np.linalg.norm(fill)
    strength = (0.52 + 0.40 * np.clip(normals @ key, 0, 1)
                + 0.16 * np.clip(normals @ fill, 0, 1))
    rgb = np.asarray(to_rgb(color))
    colors = np.clip(rgb[None, :] * strength[:, None] + 0.015, 0, 1)
    return np.column_stack((colors, np.ones(len(colors))))


def _body_component(component, body_names):
    if body_names is not None:
        return component.name in body_names
    group = component.group.casefold()
    return group.startswith(("pla_body", "full_body", "body_"))


def _default_offset(component):
    if component.name in DEFAULT_BODY_OFFSETS:
        return np.asarray(DEFAULT_BODY_OFFSETS[component.name], dtype=float)
    name = component.name.casefold()
    if any(word in name for word in ("lid", "roof", "hatch", "cover")):
        return np.array([0.0, 0.0, 95.0])
    if any(word in name for word in ("left", "port")):
        return np.array([-66.0, 0.0, 24.0])
    if any(word in name for word in ("right", "starboard")):
        return np.array([66.0, 0.0, 24.0])
    if any(word in name for word in ("nose", "front")):
        return np.array([0.0, 72.0, 25.0])
    if any(word in name for word in ("rear", "tail", "back")):
        return np.array([0.0, -72.0, 25.0])
    if any(word in name for word in ("mount", "bracket", "rail", "frame", "sill")):
        return np.array([0.0, 0.0, 22.0])
    return np.array([0.0, 0.0, 55.0])


def _friendly_name(name):
    name = name.replace("_", " ")
    words = name.split()
    while words and (words[0].isdigit() or words[0].casefold() in ("pla", "body", "full")):
        words.pop(0)
    return " ".join(words).capitalize() or name


def _camera(elevation, azimuth):
    elev_r, azim_r = np.deg2rad([elevation, azimuth])
    return np.array([np.cos(elev_r) * np.cos(azim_r),
                     np.cos(elev_r) * np.sin(azim_r), np.sin(elev_r)])


def _axes(fig, rect, bounds, *, elevation=26, azimuth=51, zoom=1.2):
    minimum, maximum = bounds
    span = np.maximum(maximum - minimum, 1.0)
    center = (minimum + maximum) / 2
    padded_span = span * np.array([1.10, 1.10, 1.11])
    ax = fig.add_axes(rect, projection="3d")
    ax.set_facecolor(BG)
    ax.set_proj_type("ortho")
    ax.view_init(elev=elevation, azim=azimuth, roll=0)
    ax.set_xlim(center[0] - padded_span[0] / 2, center[0] + padded_span[0] / 2)
    ax.set_ylim(center[1] - padded_span[1] / 2, center[1] + padded_span[1] / 2)
    ax.set_zlim(center[2] - padded_span[2] / 2, center[2] + padded_span[2] / 2)
    ax.set_box_aspect(padded_span, zoom=zoom)
    ax.set_axis_off()
    return ax


def _collection(ax, triangles, colors):
    collection = Poly3DCollection(
        triangles, facecolors=colors, edgecolors="none", linewidths=0,
        antialiased=False, zsort="average",
    )
    ax.add_collection3d(collection)
    return collection


def _tighten_scene(fig, ax, vertices, target_rect, *, padding=0.025):
    """Fit projected model into the reserved figure rectangle without distortion.

    Only camera zoom and axes placement change. Using projected surface points
    gives much tighter framing than fitting the bounding cube alone.
    """
    # Projection does not require drawing every polygon. Updating the axes
    # aspect is enough to obtain its final transform and avoids a second full
    # scene render before each PNG (and repeated renders of prior sheet cells).
    ax.apply_aspect()
    x, y, _ = proj3d.proj_transform(vertices[:, 0], vertices[:, 1], vertices[:, 2], ax.get_proj())
    pixel_xy = ax.transData.transform(np.column_stack((x, y)))
    xy = fig.transFigure.inverted().transform(pixel_xy)
    lo, hi = xy.min(axis=0), xy.max(axis=0)
    left, bottom, width, height = target_rect
    available = np.array([width, height]) * (1 - 2 * padding)
    scale = float(np.min(available / np.maximum(hi - lo, 1e-9)))
    position = ax.get_position()
    old_rect = np.array([position.x0, position.y0, position.width, position.height])
    target_center = np.array([left + width / 2, bottom + height / 2])
    scene_center = (lo + hi) / 2
    # Scaling the Axes rectangle uniformly preserves both world scale and view.
    # mplot3d may enforce a square active box, so scale the already active box.
    new_size = old_rect[2:] * scale
    new_corner = target_center + (old_rect[:2] - scene_center) * scale
    ax.set_position([*new_corner, *new_size], which="both")


def _header(fig, title, subtitle, detail=None):
    fig.text(0.055, 0.957, "ELEGOO V4  /  " + title,
             ha="left", va="top", fontsize=19, fontweight="semibold", color=INK)
    fig.text(0.055, 0.918, subtitle,
             ha="left", va="top", fontsize=9.8, color=SECONDARY)
    if detail:
        fig.text(0.055, 0.890, detail,
                 ha="left", va="top", fontsize=8.8, color=SECONDARY)


def _legend(fig):
    fig.legend(
        handles=[
            Patch(facecolor=BODY_BLUE, label="PLA body panels"),
            Patch(facecolor=BODY_GRAY, label="PLA mounts / structure"),
            Patch(facecolor=ORANGE, label="Front guard"),
            Patch(facecolor="#89939A", label="Purchased hardware — reference"),
        ],
        loc="lower center", bbox_to_anchor=(0.5, 0.043), ncol=4,
        frameon=False, fontsize=8.8, handlelength=1.3, columnspacing=1.9,
    )
    fig.text(0.055, 0.026,
             "Actual CAD surfaces  |  Orthographic view  |  +Y front, +Z up  |  Model units: mm",
             ha="left", va="bottom", fontsize=8.4, color="#73808C")


def _render_scene(meshes, target, body_names, explode_offsets, *, exploded, dpi):
    elevation, azimuth = (26, 51) if not exploded else (24, 51)
    to_camera = _camera(elevation, azimuth)
    scene_triangles, scene_colors, all_bounds = [], [], []
    labels = []
    count = 0
    for component, triangles, normals, colors in meshes:
        if exploded and component.group in (
            "Body_fasteners_reference", "Added_fasteners_reference"
        ):
            continue
        is_body = _body_component(component, body_names)
        offset = np.zeros(3)
        if exploded and component.name in explode_offsets:
            offset = np.asarray(explode_offsets[component.name], dtype=float)
        elif exploded and is_body:
            offset = _default_offset(component)
        shifted = triangles + offset
        lo, hi = shifted.min(axis=(0, 1)), shifted.max(axis=(0, 1))
        all_bounds.extend([lo, hi])
        visible = normals @ to_camera > 1e-9
        scene_triangles.append(shifted[visible])
        scene_colors.append(colors[visible])
        if exploded and is_body and np.linalg.norm(offset) > 1e-6:
            labels.append((component.name, (lo + hi) / 2, lo, hi))
        count += 1
    triangles, colors = np.concatenate(scene_triangles), np.concatenate(scene_colors)
    bounds = np.asarray(all_bounds)
    fig = plt.figure(figsize=(1700 / dpi, 1350 / dpi), dpi=dpi, facecolor=BG)
    body_rect = [0.055, 0.13, 0.89, 0.70]
    ax = _axes(fig, body_rect, [bounds.min(axis=0), bounds.max(axis=0)],
               elevation=elevation, azimuth=azimuth)
    _collection(ax, triangles, colors)
    _tighten_scene(fig, ax, triangles.reshape(-1, 3), body_rect,
                   padding=0.055 if exploded else 0.018)
    if exploded:
        title = "Full body — exploded assembly"
        subtitle = "Removable printed panels separated around the assembled rover for inspection."
        detail = "Exploded offsets are display-only; added fasteners are omitted. Purchased hardware is simplified reference geometry."
        # Compact numbered callouts remain tied to the actual separated pieces.
        # Keep the key outside the CAD region, avoiding labels on small openings.
        if len(labels) <= 12:
            label_names = []
            for number, (name, center, lo, hi) in enumerate(labels, 1):
                position = center.copy()
                position[2] = hi[2] + 4.0
                ax.text(*position, str(number), ha="center", va="center",
                        fontsize=8.0, color=INK, zorder=100,
                        bbox={"boxstyle": "round,pad=0.23", "fc": "white",
                              "ec": "#C8D1D9", "lw": 0.6, "alpha": 0.95})
                label_names.append(f"{number}. {_friendly_name(name)}")
            lines = []
            line = []
            for label in label_names:
                line.append(label)
                if len(line) == 3:
                    lines.append("    ·    ".join(line))
                    line = []
            if line:
                lines.append("    ·    ".join(line))
            if lines:
                fig.text(0.5, 0.10, "\n".join(lines), ha="center", va="center",
                         fontsize=8.1, color=SECONDARY, linespacing=1.5)
    else:
        title = "Full body explorer"
        subtitle = "Modular PLA shell on the ELEGOO V4 reference chassis."
        detail = "Purchased hardware uses simplified reference geometry. Physical fit and clearances require verification on the rover."
    _header(fig, title, subtitle, detail)
    _legend(fig)
    fig.savefig(target, dpi=dpi, facecolor=BG,
                metadata={"Title": "ELEGOO V4 " + title,
                          "Description": "Actual BRep CAD render; purchased hardware is simplified reference geometry."})
    plt.close(fig)
    print(f"Rendered {target.name}: {count} components / {len(triangles):,} visible triangles", flush=True)


def _print_record(value):
    if isinstance(value, dict):
        return value["shape"], value.get("color", BODY_BLUE), value.get("quantity", 1)
    return value, BODY_BLUE, 1


def _render_parts(print_parts, target, *, tolerance, angular_tolerance, dpi):
    records = list(print_parts.items())
    if not records:
        return
    columns = min(3, len(records))
    rows = math.ceil(len(records) / columns)
    width_px = 1800 if columns == 3 else 1500
    height_px = max(1000, 180 + rows * 430)
    fig = plt.figure(figsize=(width_px / dpi, height_px / dpi), dpi=dpi, facecolor=BG)
    fig.text(0.045, 0.97, "ELEGOO V4  /  Full body print parts",
             ha="left", va="top", fontsize=19, fontweight="semibold", color=INK)
    fig.text(0.045, 0.935, "Actual print-oriented CAD geometry. Individual views are scaled to fit; dimensions are in millimeters.",
             ha="left", va="top", fontsize=9.2, color=SECONDARY)
    grid_left, grid_right = 0.035, 0.965
    grid_bottom, grid_top = 0.070, 0.885
    cell_width = (grid_right - grid_left) / columns
    cell_height = (grid_top - grid_bottom) / rows
    to_camera = _camera(31, 49)
    for index, (name, value) in enumerate(records):
        shape, color, quantity = _print_record(value)
        triangles, normals = _triangles(shape, tolerance, angular_tolerance)
        colors = _face_colors(normals, color)
        visible = normals @ to_camera > 1e-9
        lo, hi = triangles.min(axis=(0, 1)), triangles.max(axis=(0, 1))
        col, row = index % columns, index // columns
        left = grid_left + col * cell_width
        bottom = grid_top - (row + 1) * cell_height
        rect = [left + 0.010, bottom + 0.14 * cell_height,
                cell_width - 0.020, cell_height * 0.69]
        ax = _axes(fig, rect, [lo, hi], elevation=31, azimuth=49, zoom=1.1)
        _collection(ax, triangles[visible], colors[visible])
        _tighten_scene(fig, ax, triangles.reshape(-1, 3), rect, padding=0.055)
        title = textwrap.fill(f"{index + 1:02d}  {_friendly_name(name)}", width=39)
        fig.text(left + cell_width / 2, bottom + cell_height * 0.955, title,
                 ha="center", va="top", fontsize=10.0, fontweight="semibold", color=INK,
                 linespacing=1.3)
        dimensions = " × ".join(f"{v:.1f}" for v in hi - lo)
        fig.text(left + cell_width / 2, bottom + cell_height * 0.062,
                 f"{dimensions} mm   ·   Print {quantity}",
                 ha="center", va="bottom", fontsize=9.1, color=SECONDARY)
    fig.text(0.045, 0.028,
             "Separate modular pieces  |  PLA prototype  |  Use the matching 3MF packs for print layouts",
             ha="left", va="bottom", fontsize=8.4, color="#73808C")
    fig.savefig(target, dpi=dpi, facecolor=BG,
                metadata={"Title": "ELEGOO V4 full body printable parts",
                          "Description": "Print-oriented BRep CAD geometry with part dimensions."})
    plt.close(fig)
    print(f"Rendered {target.name}: {len(records)} unique print designs", flush=True)


def render_views(parts, output_dir, *, body_names=None, explode_offsets=None,
                 print_parts=None, variant=None, tolerance=0.13,
                 angular_tolerance=0.18, dpi=140):
    """Write assembled, exploded and optionally parts-sheet PNGs.

    Explicit ``body_names`` is preferred over group-based inference. Optional
    ``explode_offsets`` maps component names to (X, Y, Z) millimeter offsets.
    ``print_parts`` is a name-to-shape mapping or the generator's print records
    containing shape, color and quantity. It should contain the new body kit
    designs only. Components and records are read, never mutated.
    """
    parts = [p for p in parts if variant is None or p.variant in ("both", variant)]
    if not parts:
        raise ValueError("No full-body assembly components to render")
    body_names = set(body_names) if body_names is not None else None
    explode_offsets = dict(explode_offsets or {})
    # The first generator wrapper used this exact legacy display translation,
    # which moved the bulkhead into the camera head. Upgrade that known offset
    # locally, leaving the reviewed geometry-generation source unchanged.
    legacy_bulkhead = explode_offsets.get("body_04_front_bulkhead")
    if legacy_bulkhead is not None and tuple(legacy_bulkhead) == (0, 32, 35):
        explode_offsets["body_04_front_bulkhead"] = DEFAULT_BODY_OFFSETS["body_04_front_bulkhead"]
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    meshes = []
    for component in parts:
        triangles, normals = _triangles(component.shape, tolerance, angular_tolerance,
                                       uniform=component.group.startswith("Head_"))
        meshes.append((component, triangles, normals,
                       _face_colors(normals, component.color)))
    print(f"Tessellated {len(meshes)} components / "
          f"{sum(len(t) for _, t, _, _ in meshes):,} triangles", flush=True)
    rendered = []
    for filename, exploded in (("full_body_preview.png", False),
                               ("full_body_exploded.png", True)):
        target = output_dir / filename
        _render_scene(meshes, target, body_names, explode_offsets,
                      exploded=exploded, dpi=dpi)
        rendered.append(target)
    if print_parts:
        target = output_dir / "full_body_parts.png"
        _render_parts(print_parts, target, tolerance=tolerance,
                      angular_tolerance=angular_tolerance, dpi=dpi)
        rendered.append(target)
    return rendered


def main():
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=here / "build_full_body.py")
    parser.add_argument("--output", type=Path, default=here / "output")
    args = parser.parse_args()
    model_path = args.model.resolve()
    sys.path.insert(0, str(model_path.parent))
    spec = importlib.util.spec_from_file_location("_full_body_preview_model", model_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import generator {model_path}")
    model = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = model
    spec.loader.exec_module(model)
    model.build()
    render_views(model.parts, args.output,
                 body_names=getattr(model, "BODY_COMPONENT_NAMES", getattr(model, "body_names", None)),
                 explode_offsets=getattr(model, "EXPLODE_OFFSETS", None),
                 print_parts=getattr(model, "prints", None))


if __name__ == "__main__":
    main()
