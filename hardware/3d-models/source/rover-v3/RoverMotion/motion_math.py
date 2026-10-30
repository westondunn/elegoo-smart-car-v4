"""Small deterministic rigid-transform layer, independent of Fusion.

All lengths, including translation cells in matrices, are MILLIMETRES here.
Matrices are row-major, act on column vectors, and compose as parent * child.
Only RoverMotion.py converts to/from Fusion's centimetre API boundary.
"""
from __future__ import annotations

import math

from motion_plan import PART_IDS, WHEEL_GROUPS, PAN_GROUP, EXPLODE_PHASES, explode_offsets


def identity():
    return (1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1.)


def validate_rigid(matrix):
    if len(matrix) != 16 or not all(math.isfinite(v) for v in matrix):
        raise ValueError("Expected a finite 4 by 4 matrix")
    if max(abs(matrix[12 + i] - v) for i, v in enumerate((0, 0, 0, 1))) > 1e-7:
        raise ValueError("Invalid homogeneous matrix")
    rows = [matrix[0:3], matrix[4:7], matrix[8:11]]
    for i in range(3):
        for j in range(3):
            if abs(sum(x * y for x, y in zip(rows[i], rows[j])) - (i == j)) > 1e-6:
                raise ValueError("Only rigid placement transforms are supported")
    a, b, c = rows
    det = (a[0] * (b[1]*c[2] - b[2]*c[1])
           - a[1] * (b[0]*c[2] - b[2]*c[0])
           + a[2] * (b[0]*c[1] - b[1]*c[0]))
    if abs(det - 1) > 1e-6:
        raise ValueError("Reflected or scaled occurrences are not supported")
    return tuple(float(v) for v in matrix)


def multiply(a, b):
    return tuple(sum(a[r*4+k] * b[k*4+c] for k in range(4))
                 for r in range(4) for c in range(4))


def transform_point(matrix, point):
    return tuple(sum(matrix[r*4+c] * point[c] for c in range(3)) + matrix[r*4+3]
                 for r in range(3))


def transform_vector(matrix, vector):
    return tuple(sum(matrix[r*4+c] * vector[c] for c in range(3)) for r in range(3))


def translation_mm(offset):
    if len(offset) != 3 or not all(math.isfinite(v) for v in offset):
        raise ValueError("Translation must be a finite three-vector in mm")
    result = list(identity())
    result[3], result[7], result[11] = map(float, offset)
    return tuple(result)


def rotation_mm(origin, axis, degrees):
    if len(origin) != 3 or len(axis) != 3 or not all(
            math.isfinite(v) for v in (*origin, *axis, degrees)):
        raise ValueError("Rotation inputs must be finite")
    size = math.sqrt(sum(v*v for v in axis))
    if size < 1e-12:
        raise ValueError("Rotation axis cannot be zero")
    degrees = math.remainder(degrees, 360.0)
    if abs(degrees) < 1e-12:
        return identity()
    x, y, z = (v / size for v in axis)
    angle = math.radians(degrees)
    c, s = math.cos(angle), math.sin(angle)
    t = 1 - c
    result = [t*x*x+c, t*x*y-s*z, t*x*z+s*y, 0.,
              t*x*y+s*z, t*y*y+c, t*y*z-s*x, 0.,
              t*x*z-s*y, t*y*z+s*x, t*z*z+c, 0.,
              0., 0., 0., 1.]
    rotated = transform_vector(result, origin)
    for r in range(3):
        result[r*4+3] = origin[r] - rotated[r]
    return tuple(result)


def pose_matrices(mode, progress, home_by_id, world_frame=None):
    """Build each pose from saved home; never integrate the previous frame.

    A complete purchased unit receives the same WORLD translation for every
    member in exploded modes, including members with different home matrices.
    Rotation demos are separate and use the existing nominal hardware axes.
    """
    if set(home_by_id) != set(PART_IDS):
        raise ValueError("Home map must contain all and only the 64 rover IDs")
    if mode not in ("home", "drive", "turn", "pan", *EXPLODE_PHASES):
        raise ValueError("Unknown motion mode: " + str(mode))
    progress = float(progress)
    if not math.isfinite(progress):
        raise ValueError("Progress must be finite")
    progress = max(0., min(1., progress))
    result = {pid: tuple(m) for pid, m in home_by_id.items()}
    if mode == "home" or progress == 0 or (mode in ("drive", "turn", "pan") and progress == 1):
        return result
    frame = home_by_id["base"] if world_frame is None else world_frame
    if mode in EXPLODE_PHASES:
        for pid, offset in explode_offsets(mode, progress).items():
            if any(offset):
                delta = translation_mm(transform_vector(frame, offset))
                result[pid] = multiply(delta, home_by_id[pid])
    elif mode in ("drive", "turn"):
        for group in WHEEL_GROUPS.values():
            wheel_home = home_by_id[group["ids"][0]]
            origin = transform_point(wheel_home, group["origin_mm"])
            axis = transform_vector(wheel_home, group["axis"])
            sign = group["forward_angle_sign"] if mode == "drive" else group["turn_angle_sign"]
            delta = rotation_mm(origin, axis, sign * 720. * progress)
            for pid in group["ids"]:
                result[pid] = multiply(delta, home_by_id[pid])
    elif mode == "pan":
        head_home = home_by_id["servo_horn"]
        origin = transform_point(head_home, PAN_GROUP["origin_mm"])
        axis = transform_vector(head_home, PAN_GROUP["axis"])
        delta = rotation_mm(origin, axis, 45. * math.sin(2. * math.pi * progress))
        for pid in PAN_GROUP["ids"]:
            result[pid] = multiply(delta, home_by_id[pid])
    return result
