"""Bounded C4 acrylic geometry proposal; ordinary Python, no native execution.

Twelve existing longitudinal sectors are retained. Their clear portions become
continuous, non-staggered smooth channels (40% of each sector); the intervening
60% contains an explicit lattice of elongated rhombi. Each rhombus is a broad
panel surrounded by narrow planar bevel faces leading into shallow shared
diagonal valleys. No triangle receives an inward centroid or a star-shaped pit.
Panel boundaries are constructed as clipped rhombi, not sampled noise or bump.

At the equator, a complete diamond is about 8.4 mm wide and 16.1 mm tall for
D=.107 m. These are construction estimates, not measurements of the product.
The 12 sectors, 40% channel width, six vertical diamond repetitions, .4 times
the existing groove-depth valley, and 10% panel inset are finite recipe choices.
The clear channels have smooth .24 times groove-depth concavity. Pole bounds
remain +/- .45D and the inner sphere radius remains .92R. Shared vertices join
panels, clear channels, smooth inner surface, and annular end caps. This is a
closed hollow mesh, not overlapping decorative shells.

The immutable C3 recipe controls are inputs: diameter [.08,.13] m and groove
depth [0,.002] m. Returns (XYZ vertices, triangular index faces, smooth flags).
The mesh has no dependency on bpy, a texture, an external asset, or randomness.
Topology checks cannot establish visual accuracy or rule out every possible
self-intersection; independent native inspection and visual review remain due.
"""
from __future__ import annotations

import math


SECTORS = 12
CLEAR_FRACTION = .4
VERTICAL_STEPS = 48
DIAMOND_HALF_ROWS = 12
CLEAR_STEPS = 8


def _number(value, name, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be finite within {low}..{high}")
    return float(value)


def _clip(poly, axis, boundary, greater):
    result = []
    for a, b in zip(poly, poly[1:] + poly[:1]):
        ain = a[axis] >= boundary - 1e-12 if greater else a[axis] <= boundary + 1e-12
        bin = b[axis] >= boundary - 1e-12 if greater else b[axis] <= boundary + 1e-12
        if ain:
            result.append(a)
        if ain != bin:
            t = (boundary - a[axis]) / (b[axis] - a[axis])
            result.append(tuple(a[k] + t * (b[k] - a[k]) for k in range(2)))
    unique = []
    for p in result:
        if not unique or any(abs(p[k] - unique[-1][k]) > 1e-11 for k in range(2)):
            unique.append(p)
    if len(unique) > 1 and all(abs(unique[0][k] - unique[-1][k]) < 1e-11 for k in range(2)):
        unique.pop()
    return unique


def _area2(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _triangulate(poly):
    """Convex polygon ears, retaining collinear boundary subdivision vertices."""
    indices, triangles = list(range(len(poly))), []
    while len(indices) > 3:
        candidates = []
        for i in range(len(indices)):
            corners = (indices[i - 1], indices[i], indices[(i + 1) % len(indices)])
            a, b, c = (poly[k] for k in corners)
            area = _area2(a, b, c)
            # A diagonal may not jump over a retained collinear boundary vertex.
            occupied = any(all(x >= -1e-12 for x in (_area2(a, b, poly[k]),
                           _area2(b, c, poly[k]), _area2(c, a, poly[k])))
                           for k in indices if k not in corners)
            if area > 1e-12 and not occupied:
                candidates.append((area, i))
        if not candidates:
            raise ValueError("no nondegenerate polygon ear")
        area, i = max(candidates)
        if area <= 1e-12:
            raise ValueError("degenerate clipped diamond")
        triangles.append((indices[i - 1], indices[i], indices[(i + 1) % len(indices)]))
        indices.pop(i)
    if _area2(*(poly[i] for i in indices)) <= 1e-12:
        raise ValueError("degenerate final polygon triangle")
    return [*triangles, tuple(indices)]


def build_fluted_globe(diameter, groove_depth):
    diameter = _number(diameter, "diameter", .08, .13)
    depth = _number(groove_depth, "groove_depth", 0, .002)
    radius, pole = diameter / 2, diameter * .45
    vertices, uv, faces, smooth, lookup = [], [], [], [], {}

    def point(turn, t, inset):
        turn = round(turn % 1.0, 12)
        if turn == 1:
            turn = 0.0
        t = round(t, 12)
        key = (turn, t)
        z = -pole + 2 * pole * t / DIAMOND_HALF_ROWS
        radial = math.sqrt(radius * radius - z * z) - inset
        if key in lookup:
            index = lookup[key]
            old_r = math.hypot(*vertices[index][:2])
            if abs(old_r - radial) > 1e-9:
                raise ValueError("shared surface boundary disagrees")
            return index
        phi = turn * 2 * math.pi
        index = len(vertices)
        vertices.append((radial * math.cos(phi), radial * math.sin(phi), z))
        uv.append((turn, t))
        lookup[key] = index
        return index

    def face(indices, use_smooth):
        faces.append(tuple(indices))
        smooth.append(use_smooth)

    for sector in range(SECTORS):
        # Every row has identical angles: the clear lane cannot zigzag between rows.
        grid = []
        for row in range(VERTICAL_STEPS + 1):
            t = DIAMOND_HALF_ROWS * row / VERTICAL_STEPS
            grid.append([point((sector + CLEAR_FRACTION * col / CLEAR_STEPS) / SECTORS,
                               t, depth * .24 * math.sin(math.pi * col / CLEAR_STEPS) ** 2)
                         for col in range(CLEAR_STEPS + 1)])
        for row in range(VERTICAL_STEPS):
            for col in range(CLEAR_STEPS):
                a, b = grid[row][col:col + 2]
                d, c = grid[row + 1][col:col + 2]
                face((a, b, c), True)
                face((a, c, d), True)

        def cutpoint(p, valley):
            u, t = p
            # All shared longitudinal boundaries have exactly zero displacement.
            inset = depth * (.4 if valley else .04) * math.sin(math.pi * u) ** 2
            return point((sector + CLEAR_FRACTION + (1 - CLEAR_FRACTION) * u) / SECTORS, t, inset)

        # Explicit diamond lattice: half-width .25 band units, half-height 1 row.
        for row in range(-1, DIAMOND_HALF_ROWS + 2):
            for col in range(-1, 6):
                if (row + col) % 2:
                    continue
                u = col * .25
                polygon = [(u - .25, row), (u, row - 1), (u + .25, row), (u, row + 1)]
                for axis, bound, greater in ((0, 0, True), (0, 1, False),
                                              (1, 0, True), (1, DIAMOND_HALF_ROWS, False)):
                    polygon = _clip(polygon, axis, bound, greater)
                    if len(polygon) < 3:
                        break
                if len(polygon) < 3:
                    continue
                if abs(sum(p[0] * q[1] - q[0] * p[1] for p, q in zip(polygon, polygon[1:] + polygon[:1]))) < 1e-10:
                    continue
                # Match every quarter-row vertex at the smooth-lane boundary.
                split = []
                for a, b in zip(polygon, polygon[1:] + polygon[:1]):
                    split.append(a)
                    if abs(a[0] - b[0]) < 1e-12 and (abs(a[0]) < 1e-12 or abs(a[0] - 1) < 1e-12):
                        ticks = [k / 4 for k in range(4 * DIAMOND_HALF_ROWS + 1)
                                 if min(a[1], b[1]) + 1e-10 < k / 4 < max(a[1], b[1]) - 1e-10]
                        if b[1] < a[1]:
                            ticks.reverse()
                        split.extend((a[0], t) for t in ticks)
                polygon = split
                center = tuple(sum(p[k] for p in polygon) / len(polygon) for k in range(2))
                inner = [tuple(center[k] + .9 * (p[k] - center[k]) for k in range(2)) for p in polygon]
                outside, inside = [cutpoint(p, True) for p in polygon], [cutpoint(p, False) for p in inner]
                for i in range(len(polygon)):
                    j = (i + 1) % len(polygon)
                    face((outside[i], outside[j], inside[j]), False)
                    face((outside[i], inside[j], inside[i]), False)
                for triangle in _triangulate(inner):
                    face(tuple(inside[i] for i in triangle), False)

    outer_vertices, outer_faces = len(vertices), len(faces)
    # Identical shared topology on a smooth inner spherical surface.
    for turn, t in uv[:]:
        z = -pole + 2 * pole * t / DIAMOND_HALF_ROWS
        r = math.sqrt((radius * .92) ** 2 - z * z)
        phi = turn * 2 * math.pi
        vertices.append((r * math.cos(phi), r * math.sin(phi), z))
    for indices in faces[:outer_faces]:
        face(tuple(i + outer_vertices for i in indices[::-1]), True)
    for t, is_top in ((0, False), (DIAMOND_HALF_ROWS, True)):
        ring = sorted((turn, index) for index, (turn, row) in enumerate(uv) if row == t)
        for (_, a), (_, b) in zip(ring, ring[1:] + ring[:1]):
            cap = [(a, b, b + outer_vertices), (a, b + outer_vertices, a + outer_vertices)]
            for indices in cap:
                face(indices if is_top else indices[::-1], False)
    return vertices, faces, smooth
