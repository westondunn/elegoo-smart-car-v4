#!/usr/bin/env python3
"""Render the modeled ELEGOO solids without a display server or OpenGL.

The reusable entry point is render_views(parts, output_dir).  ``parts`` is the
Component list produced by build_explorer.build(); no generator is imported
until the standalone command-line main runs.  All visible components are
tessellated from their actual BRep shapes.  The single combined triangle
collection permits face-level depth sorting across component boundaries.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgb
from matplotlib.patches import Patch
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np


VIEW_SPECS = (
    ("explorer", "explorer_preview.png", False, "Explorer assembly"),
    ("stock", "stock_reference_preview.png", False, "Stock reference assembly"),
    ("explorer", "explorer_exploded.png", True, "Exploded explorer layout"),
)


def _triangles(shape, tolerance: float, angular_tolerance: float):
    vertices, faces = shape.tessellate(tolerance, angular_tolerance)
    vertices = np.asarray([vertex.toTuple() for vertex in vertices], dtype=float)
    faces = np.asarray(faces, dtype=np.int64)
    if not len(vertices) or not len(faces):
        raise ValueError("A component returned no BRep tessellation")
    triangles = vertices[faces]
    # OCC leaves broad planar faces as a few large triangles. Painter sorting
    # those triangles can expose a rear PCB through the front PCB even though
    # the solids do not intersect. Subdivision preserves the surface exactly
    # while making cross-component depth ordering substantially more local.
    for _ in range(8):
        lengths_squared = np.sum((triangles - np.roll(triangles, -1, axis=1))**2, axis=2)
        split = lengths_squared.max(axis=1) > 8.0**2
        if not split.any():
            break
        large = triangles[split]
        a, b, c = large[:, 0], large[:, 1], large[:, 2]
        ab, bc, ca = (a+b)/2, (b+c)/2, (c+a)/2
        children = np.concatenate((np.stack((a, ab, ca), axis=1),
                                   np.stack((ab, b, bc), axis=1),
                                   np.stack((ca, bc, c), axis=1),
                                   np.stack((ab, bc, ca), axis=1)))
        triangles = np.concatenate((triangles[~split], children))
    normals = np.cross(triangles[:, 1] - triangles[:, 0],
                       triangles[:, 2] - triangles[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    valid = lengths > 1e-12
    if not np.all(valid):
        triangles, normals, lengths = triangles[valid], normals[valid], lengths[valid]
    if not len(triangles):
        raise ValueError("A component returned only degenerate triangles")
    normals /= lengths[:, None]
    return triangles, normals


def _face_colors(normals, color):
    # A broad key above the front-right camera and a weaker rear-left fill.
    # Ambient illumination keeps black reference hardware legible.
    key = np.array([0.36, 0.44, 0.82])
    key /= np.linalg.norm(key)
    fill = np.array([-0.68, -0.25, 0.69])
    fill /= np.linalg.norm(fill)
    strength = (0.50 + 0.40 * np.clip(normals @ key, 0, 1)
                + 0.16 * np.clip(normals @ fill, 0, 1))
    rgb = np.asarray(to_rgb(color))
    colors = np.clip(rgb[None, :] * strength[:, None] + 0.015, 0, 1)
    return np.column_stack((colors, np.ones(len(colors))))


def _decorate(fig, variant, exploded, title):
    fig.text(0.055, 0.955, "ELEGOO V4  /  " + title,
             ha="left", va="top", fontsize=18, fontweight="semibold", color="#172B3A")
    subtitle = "Modeled solid geometry; purchased hardware is shown as simplified reference components."
    fig.text(0.055, 0.922, subtitle, ha="left", va="top", fontsize=9.2, color="#596775")
    if exploded:
        fig.text(0.055, 0.894,
                 "PLA components +55 mm vertically; optional purchased hardware +90 mm. Added fasteners omitted.",
                 ha="left", va="top", fontsize=8.5, color="#596775")

    if variant == "explorer":
        handles = [
            Patch(facecolor="#2587BA", edgecolor="none", label="PLA accessories"),
            Patch(facecolor="#E78939", edgecolor="none", label="Front guard"),
            Patch(facecolor="#8E6FB5", edgecolor="none", label="Optional Pi tray"),
            Patch(facecolor="#59656D", edgecolor="none", label="Purchased hardware (reference)"),
        ]
    else:
        handles = [
            Patch(facecolor="#303941", edgecolor="none", label="Chassis / mechanical reference"),
            Patch(facecolor="#226C51", edgecolor="none", label="Electronics reference"),
            Patch(facecolor="#DCA83A", edgecolor="none", label="Pillars / hardware reference"),
        ]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 0.043),
               frameon=False, ncol=len(handles), fontsize=8.3,
               handlelength=1.25, handleheight=1.0, columnspacing=2.0)
    fig.text(0.055, 0.028, "Orthographic front-right view  |  +Y front, +Z up  |  Model units: mm",
             ha="left", va="bottom", fontsize=8.0, color="#75818A")


def render_views(parts, output_dir, *, tolerance=0.13, angular_tolerance=0.18,
                 dpi=140):
    """Save the three standard previews and return their Paths.

    Geometry is never modified. Exploded offsets are applied to copied mesh
    vertices for rendering only. Each Component shape is tessellated once.
    ``parts`` entries must have shape, name, color, variant and group fields.
    """
    parts = list(parts)
    if not parts:
        raise ValueError("No assembly components to render")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    meshes = []
    for component in parts:
        triangles, normals = _triangles(component.shape, tolerance, angular_tolerance)
        meshes.append((component, triangles, normals, _face_colors(normals, component.color)))
    print(f"Tessellated {len(meshes)} components / "
          f"{sum(len(t) for _, t, _, _ in meshes):,} triangles", flush=True)

    rendered = []
    for variant, filename, exploded, title in VIEW_SPECS:
        scene_triangles, scene_colors = [], []
        elevation = 26 if not exploded else 24
        azimuth = 51
        elev_r, azim_r = np.deg2rad([elevation, azimuth])
        to_camera = np.array([np.cos(elev_r)*np.cos(azim_r),
                              np.cos(elev_r)*np.sin(azim_r), np.sin(elev_r)])
        count = 0
        bounds_triangles = []
        for component, triangles, normals, colors in meshes:
            if component.variant not in ("both", variant):
                continue
            offset_z = 0.0
            if exploded:
                if component.group == "Added_fasteners_reference":
                    continue
                if component.group == "PLA_accessories":
                    offset_z = 55.0
                elif component.group == "Optional_purchased_hardware":
                    offset_z = 90.0
            shifted = triangles + np.array([0.0, 0.0, offset_z])
            bounds_triangles.append(np.stack((shifted.min(axis=(0, 1)),
                                              shifted.max(axis=(0, 1)))))
            # Opaque closed solids cannot expose their back-facing surfaces.
            # Culling reduces both painter artifacts and rendering memory.
            visible = normals @ to_camera > 1e-9
            scene_triangles.append(shifted[visible])
            scene_colors.append(colors[visible])
            count += 1
        if not scene_triangles:
            raise ValueError(f"No components for variant {variant}")
        triangles = np.concatenate(scene_triangles)
        colors = np.concatenate(scene_colors)
        bounds = np.concatenate(bounds_triangles)
        bounds_min = bounds.min(axis=0)
        bounds_max = bounds.max(axis=0)
        span = bounds_max - bounds_min
        center = (bounds_min + bounds_max) / 2

        fig = plt.figure(figsize=(1700 / dpi, 1400 / dpi), dpi=dpi,
                         facecolor="#FAFBFC")
        ax = fig.add_axes([0.045, 0.105, 0.91, 0.775], projection="3d")
        ax.set_facecolor("#FAFBFC")
        ax.set_proj_type("ortho")
        ax.view_init(elev=elevation, azim=azimuth, roll=0)
        # Equal physical scale on all three axes. Pad limits rather than
        # stretching the robot into a visually convenient aspect ratio.
        padded_span = np.maximum(span, 1.0) * np.array([1.12, 1.12, 1.13])
        ax.set_xlim(center[0] - padded_span[0]/2, center[0] + padded_span[0]/2)
        ax.set_ylim(center[1] - padded_span[1]/2, center[1] + padded_span[1]/2)
        ax.set_zlim(center[2] - padded_span[2]/2, center[2] + padded_span[2]/2)
        ax.set_box_aspect(padded_span, zoom=1.11)
        ax.set_axis_off()

        # One collection is essential: separate collections are sorted only
        # as whole objects by mplot3d, incorrectly hiding intersecting parts.
        collection = Poly3DCollection(triangles, facecolors=colors,
                                     edgecolors="none", linewidths=0,
                                     antialiased=False, zsort="average")
        ax.add_collection3d(collection)
        _decorate(fig, variant, exploded, title)
        target = output_dir / filename
        fig.savefig(target, dpi=dpi, facecolor=fig.get_facecolor(),
                    metadata={"Title": "ELEGOO V4 " + title,
                              "Description": "BRep tessellation render; simplified purchased hardware."})
        plt.close(fig)
        rendered.append(target)
        print(f"Rendered {target.name}: {count} components / {len(triangles):,} triangles",
              flush=True)
    return rendered


def main():
    here = Path(__file__).resolve().parent
    default_model = here / "build_explorer.py"
    if not default_model.exists():
        default_model = here.parent / "deliverables" / "build_explorer.py"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=default_model)
    parser.add_argument("--output", type=Path, default=here / "output")
    args = parser.parse_args()
    model_path = args.model.resolve()
    sys.path.insert(0, str(model_path.parent))
    spec = importlib.util.spec_from_file_location("_explorer_preview_model", model_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import generator {model_path}")
    model = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = model
    spec.loader.exec_module(model)
    model.build()
    print(f"Built {len(model.parts)} components / {len(model.prints)} print designs", flush=True)
    render_views(model.parts, args.output)


if __name__ == "__main__":
    main()
