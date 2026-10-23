# -*- coding: utf-8 -*-
"""Разбивка колец без GEOS: треугольник как есть, малые кольца ушами.

На QGIS 4.2 перестройка сцены с вокселями из 2.04 роняла QGIS целиком
(нарушение доступа) внутри разбивки колец. Каждый треугольник тела
уходил в триангуляцию GEOS, десятки тысяч вызовов на слой. Теперь
треугольник берётся как есть, кольцо до двухсот вершин разбивается
своим отсечением ушей, а GEOS получает только большие и правильные
кольца.

Считается на голом NumPy, QGIS не нужен.
"""

import os
import sys

import numpy as np

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d.viewer_core import ear_clip   # noqa: E402


def _area(x, y):
    return 0.5 * abs(float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)))


def _tri_area(x, y, f):
    a = np.array([x[f[:, 0]], y[f[:, 0]]]).T
    b = np.array([x[f[:, 1]], y[f[:, 1]]]).T
    c = np.array([x[f[:, 2]], y[f[:, 2]]]).T
    return 0.5 * np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1])
                        - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0]))


def _check(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    f = ear_clip(x, y)
    assert f is not None
    assert len(f) == len(x) - 2, (len(f), len(x))
    assert abs(_tri_area(x, y, f).sum() - _area(x, y)) < 1e-9
    return f


def test_square_both_orientations():
    _check([0, 1, 1, 0], [0, 0, 1, 1])
    _check([0, 0, 1, 1], [0, 1, 1, 0])


def test_concave_l_shape_covers_exactly():
    _check([0, 2, 2, 1, 1, 0], [0, 0, 1, 1, 2, 2])


def test_collinear_vertices_of_merged_voxel_faces():
    """Грань вокселей с вершинами на сторонах: площадь покрыта целиком."""
    _check([0, 1, 2, 3, 3, 3, 2, 1, 0, 0],
           [0, 0, 0, 0, 1, 2, 2, 2, 2, 1])


def test_comb_with_many_notches():
    xs, ys = [0.0], [0.0]
    for i in range(10):
        xs += [2 * i + 1, 2 * i + 1, 2 * i + 2]
        ys += [0.0, 3.0, 0.0]
    xs += [21.0, 0.0]
    ys += [-1.0, -1.0]
    _check(xs, ys)


def test_random_star_polygons():
    """Звёздчатые кольца со случайными лучами: площадь сходится."""
    rng = np.random.default_rng(4)
    for _ in range(200):
        n = int(rng.integers(4, 60))
        # лучи вокруг начала с шагом меньше полуоборота: кольцо
        # звёздчатое и простое
        a = (np.arange(n) + rng.uniform(0.0, 0.9, n)) * 2 * np.pi / n
        r = rng.uniform(0.2, 1.0, n)
        _check(r * np.cos(a), r * np.sin(a))


def test_bow_tie_is_refused_not_guessed():
    """Самопересечение: ушей нет, решает вызывающий."""
    got = ear_clip([0, 2, 0, 2], [0, 2, 2, 0])
    assert got is None or len(got) == 2


def test_triangles_skip_geos_in_the_viewer():
    src = open(os.path.join(PKG, "viewer3d.py"), encoding="utf-8").read()
    i = src.index("def _tessellate_ring3d")
    body = src[i:src.index("\ndef ", i + 10)]
    assert body.index("if len(p) == 3:") < body.index("QgsGeometry")
    assert body.index("ear_clip(uu, ww)") < body.index("QgsGeometry")
    assert "isGeosValid()" in body


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all ear clip tests passed")


if __name__ == "__main__":
    _run()
