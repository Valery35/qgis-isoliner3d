# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Замкнуто ли кольцо, решается точным сравнением вершин.

np.allclose сравнивает с относительным допуском 1e-5. В метрах
проекции (восток 435 000, север 6 062 000) это 4 и 60 м: последняя
вершина незамкнутого квадрата 20 x 20 м «совпадала» с первой, и
замыкающая сторона пропадала. 2.26 строил свод так, будто стороны
нет (802.75 м3 вместо 660.25), центр полигона в 2.25 смещался,
разбивка кольца теряла вершину. Нашла сессия RustGIS при переносе.

Запуск:  python isoliner3d/tests/test_ring_closure.py
"""
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import crown, density3d                 # noqa: E402
from isoliner3d import viewer3d as v3                    # noqa: E402
from isoliner3d.mesh3d import bed_to_mesh_arrays         # noqa: E402
from isoliner3d.cleanup import mesh_volume               # noqa: E402

E, N = 435000.0, 6062000.0
# квадрат 20 x 20 м без замыкающей вершины
OPEN = np.array([[0, 0, 100], [20, 0, 100], [20, 20, 100], [0, 20, 100]],
                dtype=float)


def _volume(ring):
    top, bot, gt, _info = crown.crown_grids(ring, steep=0.5, cell=1.0)
    v, f = bed_to_mesh_arrays(top, bot, gt)
    return abs(mesh_volume(v, f))


def test_crown_body_does_not_move_with_the_coordinates():
    far = OPEN + [E, N, 0.0]
    assert abs(_volume(far) - _volume(OPEN)) < 1e-6, (
        _volume(far), _volume(OPEN))


def test_crown_distance_keeps_the_closing_side():
    far = OPEN + [E, N, 0.0]
    # точка у замыкающей стороны x = 0, в 1 м от неё
    d = crown.boundary_distance(np.array([E + 1.0]), np.array([N + 10.0]),
                                far)
    assert abs(d[0] - 1.0) < 1e-9, d


def test_polygon_centre_does_not_move_with_the_coordinates():
    far = OPEN + [E, N, 0.0]
    got = density3d._anchor("polygon", [far])
    assert np.allclose(got[:2], (E + 10.0, N + 10.0), rtol=0, atol=1e-9), got


def test_ring_split_keeps_the_last_vertex():
    far = OPEN + [E, N, 0.0]
    v, f = v3._tessellate_ring3d(far)
    assert len(v) == 4 and len(f) == 2, (len(v), len(f))


def test_vertical_wall_is_not_closed_by_its_plan():
    # стенка: первая и последняя вершины одна точка плана, но не одна
    wall = np.array([[0, 0, 0], [20, 0, 0], [20, 0, 30], [0, 0, 30]],
                    dtype=float)
    v, f = v3._tessellate_ring3d(wall)
    assert len(v) == 4, len(v)


def test_no_relative_tolerance_on_ring_ends():
    """Ни в одном модуле концы кольца не сравниваются через allclose."""
    pat = re.compile(r"allclose\(\s*(\w+)\[0\]\s*,\s*\1\[-1\]")
    bad = []
    for root, dirs, files in os.walk(PKG):
        dirs[:] = [d for d in dirs if d not in ("libs", "tests")]
        for name in files:
            if name.endswith(".py"):
                path = os.path.join(root, name)
                if pat.search(open(path, encoding="utf-8").read()):
                    bad.append(os.path.relpath(path, PKG))
    assert not bad, bad


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
