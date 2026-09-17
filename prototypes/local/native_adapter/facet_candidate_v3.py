"""Proposed Arlette method change: ordered triangle cuts, not a sampled groove field.

This pure-math helper does not import bpy, open scenes, or execute native jobs.
It is an unselected construction proposal until the supervising controller
accepts it after the current candidate's independent review.

The outer surface uses 48 samples around each of 21 staggered rings (20 rows).
Alternate rings rotate half a cell. Each inter-ring strip is split into two
regular opposing triangles per cell, producing a repeated lozenge arrangement.
Within the first 72% of each of 12 longitudinal sectors, a triangle receives
one inward-displaced centroid and three PLANAR cut faces. The remaining wider
longitudinal bands retain smooth faces. This explicitly aligns topology with
the repeating cuts. There is no high-frequency sampled V-groove function.

Boundary vertices are shared by adjacent triangles. A smooth inner surface
at .92 times the outer sphere radius uses the same ring topology. Annular
triangle caps connect the two surfaces at pole Z = +/-.45 times the diameter.
No duplicate overlapping shells, floating facets, or disconnected decorative
edges are generated. A shallow 24-flute radial profile runs along longitude;
its maximum indentation is .12 times groove_depth. The original spherical
radius is never exceeded. Outer centers are displaced inward by groove_depth
from their parent triangle's barycenter; cut faces are flat-shaded.

Returns (vertices, triangle_faces, smooth_flags), where each vertex is XYZ in
metres, each face has three shared integer indices, and smooth_flags has one
boolean per face. Only diameter [.08,.13] and groove_depth [0,.002] are inputs.
Pole dimensions and mounting positions therefore retain the existing recipe.
Geometry regularity is a method proposal, not a visual acceptance verdict.

Run this module with Python for independent topological/numerical checks:
every undirected edge must have exactly two incident faces, oriented uses
must cancel, every triangle must have positive area, vertices must be finite,
all vertices must participate, and the oriented closed-shell volume must be
positive. These checks do not establish absence of all self-intersections or
native render quality.
"""
from __future__ import annotations

from collections import Counter
import json
import math


ANGULAR_CELLS = 48
VERTICAL_ROWS = 20


def _sub(a, b):
    return tuple(a[i] - b[i] for i in range(3))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def _unit(a):
    length = math.sqrt(_dot(a, a))
    if length == 0:
        raise ValueError("zero displacement direction")
    return tuple(v / length for v in a)


def _number(value, label, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{label} must be finite within {low}..{high}")
    return float(value)


def build_faceted_globe(diameter: float, groove_depth: float):
    diameter = _number(diameter, "diameter", .08, .13)
    groove_depth = _number(groove_depth, "groove_depth", 0, .002)
    radius = diameter / 2
    inner_radius = radius * .92
    pole_z = diameter * .45
    around, rows = ANGULAR_CELLS, VERTICAL_ROWS
    vertices, faces, smooth = [], [], []
    for layer in range(2):
        for row in range(rows + 1):
            z = -pole_z + 2 * pole_z * row / rows
            radial = math.sqrt((radius if layer == 0 else inner_radius) ** 2 - z * z)
            stagger = .5 if row % 2 else 0
            for cell in range(around):
                phi = 2 * math.pi * (cell + stagger) / around
                r = radial
                if layer == 0:
                    r -= groove_depth * .12 * (.5 - .5 * math.cos(24 * phi))
                vertices.append((r * math.cos(phi), r * math.sin(phi), z))
    layer_vertices = around * (rows + 1)

    def triangles(row, cell, offset=0):
        nxt = (cell + 1) % around
        lower = offset + row * around
        upper = lower + around
        if row % 2 == 0:
            return ((lower + cell, lower + nxt, upper + cell),
                    (lower + nxt, upper + nxt, upper + cell))
        return ((lower + cell, lower + nxt, upper + nxt),
                (lower + cell, upper + nxt, upper + cell))

    for row in range(rows):
        for cell in range(around):
            for triangle_index, triangle in enumerate(triangles(row, cell)):
                center = tuple(sum(vertices[index][axis] for index in triangle) / 3 for axis in range(3))
                # Integer topology phase avoids diameter-dependent floating-point
                # classification at sector boundaries; every repeated sector agrees.
                half_cell_offset = 1 if triangle_index == row % 2 else 2
                sector = ((2 * cell + half_cell_offset) % 8) / 8
                if sector < .72:
                    # Radial inset of the barycenter creates three shared-edge planar cut faces.
                    radial_direction = _unit(center)
                    inset = tuple(center[axis] - groove_depth * radial_direction[axis] for axis in range(3))
                    midpoint = len(vertices)
                    vertices.append(inset)
                    a, b, c = triangle
                    faces.extend(((a, b, midpoint), (b, c, midpoint), (c, a, midpoint)))
                    smooth.extend((False, False, False))
                else:
                    faces.append(triangle)
                    smooth.append(True)
            for triangle in triangles(row, cell, layer_vertices):
                faces.append(triangle[::-1])
                smooth.append(True)
    for cell in range(around):
        nxt = (cell + 1) % around
        # Bottom cap, outward normal -Z.
        faces.extend(((cell, layer_vertices + cell, layer_vertices + nxt),
                      (cell, layer_vertices + nxt, nxt)))
        # Top cap, outward normal +Z.
        top = rows * around
        faces.extend(((top + cell, top + nxt, layer_vertices + top + nxt),
                      (top + cell, layer_vertices + top + nxt, layer_vertices + top + cell)))
        smooth.extend((False, False, False, False))
    return vertices, faces, smooth


def check_mesh(vertices, faces, smooth_flags):
    """Independent topology predicates; no assumptions about how triangles were authored."""
    if len(smooth_flags) != len(faces) or not all(type(flag) is bool for flag in smooth_flags):
        raise AssertionError("face/smoothing cardinality or type mismatch")
    if not vertices or not all(len(v) == 3 and all(math.isfinite(x) for x in v) for v in vertices):
        raise AssertionError("nonfinite or missing vertices")
    edges, oriented, used = Counter(), Counter(), set()
    smallest_area, volume = math.inf, 0.0
    for face in faces:
        if len(face) != 3 or len(set(face)) != 3 or any(type(i) is not int or not 0 <= i < len(vertices) for i in face):
            raise AssertionError("invalid triangle")
        a, b, c = (vertices[i] for i in face)
        cross = _cross(_sub(b, a), _sub(c, a))
        area = math.sqrt(_dot(cross, cross)) / 2
        if area <= 1e-14:
            raise AssertionError("degenerate triangle")
        smallest_area = min(smallest_area, area)
        volume += _dot(a, _cross(b, c)) / 6
        used.update(face)
        for a_index, b_index in zip(face, face[1:] + face[:1]):
            edge = tuple(sorted((a_index, b_index)))
            edges[edge] += 1
            oriented[edge] += 1 if a_index < b_index else -1
    bad = [edge for edge, count in edges.items() if count != 2]
    if bad:
        raise AssertionError(f"nonmanifold edge count: {len(bad)}")
    if any(oriented.values()):
        raise AssertionError("inconsistent adjacent face winding")
    if len(used) != len(vertices):
        raise AssertionError("unused vertices")
    if volume <= 0:
        raise AssertionError("nonpositive oriented closed volume")
    return {"vertices": len(vertices), "triangles": len(faces), "edges": len(edges),
            "edge_incidence_exactly_two": True, "consistent_winding": True,
            "minimum_triangle_area_m2": smallest_area, "oriented_volume_m3": volume,
            "flat_faces": sum(not flag for flag in smooth_flags),
            "smooth_faces": sum(smooth_flags),
            "bounds_m": {"min": [min(v[i] for v in vertices) for i in range(3)],
                         "max": [max(v[i] for v in vertices) for i in range(3)]}}


def _static_checks():
    records = []
    for diameter, depth in ((.107, .0012), (.107, 0), (.08, .002), (.13, .002)):
        mesh = build_faceted_globe(diameter, depth)
        checks = check_mesh(*mesh)
        assert abs(checks["bounds_m"]["min"][2] + diameter * .45) < 1e-12
        assert abs(checks["bounds_m"]["max"][2] - diameter * .45) < 1e-12
        assert checks["bounds_m"]["max"][0] <= diameter / 2 + 1e-12
        records.append({"diameter_m": diameter, "groove_depth_m": depth, **checks})
    vertices, faces, smooth = build_faceted_globe(.107, .0012)
    negative_controls = {}
    for name, bad_faces, bad_flags in (("removed_face", faces[:-1], smooth[:-1]),
                                       ("reversed_face", [faces[0][::-1], *faces[1:]], smooth)):
        try:
            check_mesh(vertices, bad_faces, bad_flags)
        except AssertionError as error:
            negative_controls[name] = str(error)
        else:
            raise AssertionError("negative topology control failed to detect " + name)
    return {"kind": "pure_math_static_geometry", "native_executed": False,
            "proposal_selected": False, "cases": records, "negative_controls_detected": negative_controls,
            "unverified": ["all self intersections", "Blender readback", "render appearance", "independent visual acceptance"]}


if __name__ == "__main__":
    print(json.dumps(_static_checks(), sort_keys=True, indent=2))
