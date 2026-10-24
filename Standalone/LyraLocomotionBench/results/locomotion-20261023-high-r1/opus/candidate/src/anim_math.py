"""Small math helpers shared by asset authoring and the controller.

Conventions (see INTERFACE.md):
* quaternions are stored as [x, y, z, w], Hamilton product, active rotation;
  ``qmul(a, b)`` composes parent ``a`` with local ``b``.
* character/actor space: +X forward, +Y right, +Z up. A positive yaw rotates
  +X toward +Y (right-handed rotation about +Z in these coordinates).
"""

from __future__ import annotations

import math
from typing import Sequence

Vec3 = Sequence[float]
Quat = Sequence[float]


def wrap_degrees(angle: float) -> float:
    """Map an angle to (-180, 180]."""
    a = math.fmod(angle, 360.0)
    if a <= -180.0:
        a += 360.0
    elif a > 180.0:
        a -= 360.0
    return a


def qmul(a: Quat, b: Quat) -> list:
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return [
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    ]


def qconj(q: Quat) -> list:
    return [-q[0], -q[1], -q[2], q[3]]


def qnormalize(q: Quat) -> list:
    n = math.sqrt(sum(c * c for c in q))
    if n <= 0.0 or not math.isfinite(n):
        raise ValueError("degenerate quaternion")
    return [c / n for c in q]


def qcanonical(q: Quat) -> list:
    """Return the hemisphere representative with w >= 0."""
    return [-c for c in q] if q[3] < 0.0 else list(q)


def qrotate(q: Quat, v: Vec3) -> list:
    p = [v[0], v[1], v[2], 0.0]
    r = qmul(qmul(q, p), qconj(q))
    return [r[0], r[1], r[2]]


def quat_from_yaw_degrees(yaw: float) -> list:
    h = math.radians(yaw) * 0.5
    return [0.0, 0.0, math.sin(h), math.cos(h)]


def yaw_degrees_from_quat(q: Quat) -> float:
    """Yaw (about +Z) of the rotated +X axis, in degrees."""
    fwd = qrotate(q, [1.0, 0.0, 0.0])
    return math.degrees(math.atan2(fwd[1], fwd[0]))


def quat_angle_degrees(a: Quat, b: Quat) -> float:
    d = abs(sum(x * y for x, y in zip(a, b)))
    return math.degrees(2.0 * math.acos(min(1.0, d)))


def mat_vec(m: Sequence[Sequence[float]], v: Vec3) -> list:
    return [sum(m[r][c] * v[c] for c in range(3)) for r in range(3)]


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def sample_curve(times: Sequence[float], values: Sequence[float], t: float) -> float:
    """Piecewise-linear sample with end clamping; ``times`` ascending."""
    if not times:
        raise ValueError("empty curve")
    if t <= times[0]:
        return values[0]
    if t >= times[-1]:
        return values[-1]
    lo, hi = 0, len(times) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if times[mid] <= t:
            lo = mid
        else:
            hi = mid
    span = times[hi] - times[lo]
    u = 0.0 if span <= 0 else (t - times[lo]) / span
    return lerp(values[lo], values[hi], u)


def invert_monotonic_curve(times: Sequence[float], values: Sequence[float], target: float) -> float:
    """Find the first time where a monotonic (non-strict) curve reaches ``target``.

    Works for increasing or decreasing curves; clamps to the curve range.
    This is the core of distance matching.
    """
    if not times:
        raise ValueError("empty curve")
    increasing = values[-1] >= values[0]
    sign = 1.0 if increasing else -1.0
    tgt = sign * target
    if tgt <= sign * values[0]:
        return times[0]
    for i in range(1, len(times)):
        v0, v1 = sign * values[i - 1], sign * values[i]
        if v1 >= tgt:
            if v1 == v0:
                return times[i]
            u = (tgt - v0) / (v1 - v0)
            return lerp(times[i - 1], times[i], clamp(u, 0.0, 1.0))
    return times[-1]
