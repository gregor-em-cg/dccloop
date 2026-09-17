"""Independent predicates for the proposed geometry; no Blender invocation.

These tests fail on missing/reversed/degenerate faces, a staggered lane, changed
pole/envelope bounds, invalid numeric input, or nondeterminism. They make no
photo-quality claim and do not replace native mesh inspection.
"""
import math
import unittest

from native_adapter.fluted_candidate_v4 import build_fluted_globe
from native_adapter.facet_candidate_v3 import check_mesh


class FlutedCandidateV4Tests(unittest.TestCase):
    def test_closed_positive_surface_and_envelope(self):
        for diameter, depth in ((.107, .0012), (.107, 0), (.08, .002), (.13, .002)):
            with self.subTest(diameter=diameter, depth=depth):
                vertices, faces, smooth = build_fluted_globe(diameter, depth)
                measured = check_mesh(vertices, faces, smooth)
                for axis in (0, 1):
                    self.assertAlmostEqual(measured['bounds_m']['max'][axis], diameter / 2, places=9)
                    self.assertAlmostEqual(measured['bounds_m']['min'][axis], -diameter / 2, places=9)
                self.assertAlmostEqual(measured['bounds_m']['max'][2], .45 * diameter, places=12)
                self.assertAlmostEqual(measured['bounds_m']['min'][2], -.45 * diameter, places=12)
                self.assertGreater(measured['flat_faces'], 0)
                self.assertGreater(measured['smooth_faces'], 0)

    def test_every_clear_lane_boundary_is_continuous_and_aligned(self):
        vertices, faces, _ = build_fluted_globe(.107, .0012)
        edges = {tuple(sorted((a, b))) for f in faces for a, b in zip(f, f[1:] + f[:1])}
        # Frozen independent design expectations: twelve sectors and 49 pole-to-pole
        # boundary points. Outer boundary is spherical, without row-dependent phase.
        for sector in range(12):
            target = 2 * math.pi * sector / 12
            points = []
            for index, (x, y, z) in enumerate(vertices):
                phase = math.atan2(y, x)
                distance = abs(math.atan2(math.sin(phase - target), math.cos(phase - target)))
                if distance < 1e-9 and abs(math.sqrt(x*x + y*y + z*z) - .0535) < 1e-10:
                    points.append((z, index))
            points.sort()
            self.assertEqual(len(points), 49)
            self.assertTrue(all(tuple(sorted((a[1], b[1]))) in edges for a, b in zip(points, points[1:])))

    def test_deterministic_without_stochastic_texture(self):
        self.assertEqual(build_fluted_globe(.107, .0012), build_fluted_globe(.107, .0012))

    def test_negative_topology_controls_are_detected(self):
        vertices, faces, smooth = build_fluted_globe(.107, .0012)
        cases = ((faces[:-1], smooth[:-1]), ([faces[0][::-1], *faces[1:]], smooth),
                 ([(faces[0][0], faces[0][0], faces[0][2]), *faces[1:]], smooth))
        for changed, flags in cases:
            with self.assertRaises(AssertionError):
                check_mesh(vertices, changed, flags)

    def test_invalid_numbers_rejected(self):
        for diameter, depth in ((True, .001), (.107, float('nan')), (.107, -.1), (.2, .001)):
            with self.assertRaises(ValueError):
                build_fluted_globe(diameter, depth)


if __name__ == '__main__':
    unittest.main()
