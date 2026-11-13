# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""2.25 3D-плотность: ядро density3d.py и инструмент density_3d.

Запуск:  python isoliner3d/tests/test_density3d.py
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from isoliner3d import density3d as d3  # noqa: E402
from isoliner3d.toolspec import Report, ToolError  # noqa: E402
from isoliner3d.tools import by_name  # noqa: E402


def _lat():
    # сетка 4 x 3 x 2 ячейки по 10 м от (0, 0, 0)
    return d3.Lattice(0.0, 0.0, 0.0, 10.0, 10.0, 10.0, 4, 3, 2)


def test_points_are_counted_where_they_lie():
    pts = [[np.array([[5.0, 5.0, 5.0]])], [np.array([[6.0, 4.0, 3.0]])],
           [np.array([[35.0, 25.0, 15.0]])], [np.array([[99.0, 5.0, 5.0]])]]
    cubes, s = d3.density(pts, "point", _lat(), [1.0, 3.0, 10.0, 7.0])
    c = cubes["count"]
    assert c.shape == (2, 3, 4)
    assert c[0, 0, 0] == 2 and c[1, 2, 3] == 1 and c.sum() == 3
    assert cubes["sum"][0, 0, 0] == 4.0 and cubes["mean"][0, 0, 0] == 2.0
    assert np.isnan(cubes["mean"][0, 1, 1]) and c[0, 1, 1] == 0
    assert s["objects"] == 4 and s["inside"] == 3


def test_line_length_is_split_exactly_by_cells():
    """Длина по ячейкам сходится с длиной линии внутри сетки."""
    lat = _lat()
    p = np.array([[1.0, 1.0, 1.0], [38.0, 27.0, 19.0], [2.0, 29.0, 3.0]])
    cubes, s = d3.density([[p]], "line", lat)
    full = float(np.sum(np.linalg.norm(np.diff(p, axis=0), axis=1)))
    assert abs(s["len_all"] - full) < 1e-9
    assert abs(cubes["length"].sum() - full) < 1e-6
    # отрезок вдоль оси по одной строке ячеек
    q = np.array([[0.0, 5.0, 5.0], [40.0, 5.0, 5.0]])
    cubes, _s = d3.density([[q]], "line", lat)
    assert np.allclose(cubes["length"][0, 0, :], 10.0)
    assert abs(cubes["length"].sum() - 40.0) < 1e-9


def test_line_outside_the_grid_keeps_only_the_inside_part():
    lat = _lat()
    q = np.array([[-20.0, 5.0, 5.0], [20.0, 5.0, 5.0]])
    cubes, s = d3.density([[q]], "line", lat)
    assert abs(cubes["length"].sum() - 20.0) < 1e-9
    assert abs(s["len_all"] - 40.0) < 1e-9


def test_object_is_counted_once_at_its_middle():
    lat = _lat()
    q = np.array([[1.0, 5.0, 5.0], [39.0, 5.0, 5.0]])     # середина x=20
    poly = np.array([[11.0, 11.0, 2.0], [19.0, 11.0, 2.0],
                     [19.0, 19.0, 2.0], [11.0, 19.0, 2.0], [11.0, 11.0, 2.0]])
    c_line, _s = d3.density([[q]], "line", lat)
    c_poly, _s = d3.density([[poly]], "polygon", lat)
    assert c_line["count"].sum() == 1 and c_line["count"][0, 0, 2] == 1
    assert c_poly["count"].sum() == 1 and c_poly["count"][0, 1, 1] == 1


def test_lattice_around_covers_the_data_with_round_steps():
    lat = d3.Lattice.around([3.0, 7.0, -12.0], [503.0, 207.0, 88.0], 0, 0)
    assert lat.step[0] == 10.0 and lat.step[2] == 5.0
    _ijk, ok = lat.index(np.array([[3.0, 7.0, -12.0], [503.0, 207.0, 88.0]]))
    assert ok.all()
    try:
        d3.Lattice.around([0, 0, 0], [1e5, 1e5, 1e3], 1.0, 1.0)
    except ValueError:
        pass
    else:
        raise AssertionError("огромная сетка должна дать отказ")


def _values(items, geom, **kw):
    spec = by_name("density_3d")
    v = spec.defaults()
    v.update({"INPUT": items, "@INPUT": {"geometry": geom}})
    v.update(kw)
    return spec, v


def test_tool_writes_a_cube_with_z_marks():
    items = [{"id": i, "attrs": {"w": w},
              "parts": [np.array([[x, y, z]])]}
             for i, (x, y, z, w) in enumerate(
                 [(5, 5, 5, 1.0), (5, 25, 5, 2.0), (15, 5, 15, 4.0)])]
    spec, v = _values(items, "point", CELL_XY=10.0, CELL_Z=10.0,
                      METRIC=1, ATTR="w", OUTPUT_CELLS=True)
    out = spec.run(v, Report())
    g = out["OUTPUT"].grid
    z0, dz = float(g.meta["Z0"]), float(g.meta["DZ"])
    assert dz == 10.0 and z0 == 5.0        # центр нижнего уровня
    # первая строка растра - север: точка (5, 25) в верхней строке
    b1 = g.band(1)
    x0, sx, _r, y0, _r2, sy = g.transform
    row = int((25.0 - y0) / sy)
    col = int((5.0 - x0) / sx)
    assert b1[row, col] == 2.0
    assert sum(np.nansum(b) for b in g.bands()) == 7.0
    cells = out["OUTPUT_CELLS"]
    assert len(cells.features) == 3
    assert sum(vals[1] for _g, vals in cells.features) == 7.0


def test_tool_refuses_what_it_cannot_count():
    pt = [{"id": 0, "attrs": {}, "parts": [np.array([[1.0, 1.0, 1.0]])]}]
    spec, v = _values(pt, "point", METRIC=3)
    try:
        spec.run(v, Report())
    except ToolError:
        pass
    else:
        raise AssertionError("длина по точкам - отказ")
    spec, v = _values(pt, "point", METRIC=1)
    try:
        spec.run(v, Report())
    except ToolError:
        pass
    else:
        raise AssertionError("сумма без атрибута - отказ")
    flat = [{"id": 0, "attrs": {},
             "parts": [np.array([[1.0, 1.0, np.nan]])]}]
    spec, v = _values(flat, "point")
    try:
        spec.run(v, Report())
    except ToolError:
        pass
    else:
        raise AssertionError("без Z - отказ")


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK", name)
            n += 1
    print("all density tests passed (%d)" % n)
