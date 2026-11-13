# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""2.26 Тела по контуру со сводом: ядро crown.py и инструмент.

Квадрат 20 на 20 м с линейным сводом крутизной 0.5 - пирамида высотой
5 м и объёмом 400 * 5 / 3 = 666.7 м3. Сетка срезает край на полячейки,
поэтому объём чуть меньше.

Запуск:  python isoliner3d/tests/test_crown.py
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from isoliner3d import crown  # noqa: E402
from isoliner3d.cleanup import mesh_volume, shell_defects  # noqa: E402
from isoliner3d.mesh3d import bed_to_mesh_arrays  # noqa: E402
from isoliner3d.toolspec import Report, ToolError  # noqa: E402
from isoliner3d.tools import by_name  # noqa: E402

SQ = np.array([[0, 0, 100], [20, 0, 100], [20, 20, 100], [0, 20, 100],
               [0, 0, 100]], dtype=float)


def _body(**kw):
    top, bot, gt, info = crown.crown_grids(SQ, cell=0.25, **kw)
    v, f = bed_to_mesh_arrays(top, bot, gt)
    return v, f, info


def test_pyramid_volume_and_height():
    v, f, info = _body(steep=0.5)
    assert shell_defects(v, f)[0] == 0
    assert abs(info["rise"] - 5.0) < 0.2
    vol = mesh_volume(v, f)
    assert 600.0 < vol < 667.0, vol
    assert abs(v[:, 2].min() - 100.0) < 1e-9


def test_walls_add_a_prism_and_cap_flattens_the_crest():
    v0, f0, _i = _body(steep=0.5)
    v1, f1, _i = _body(steep=0.5, wall=2.0)
    dv = mesh_volume(v1, f1) - mesh_volume(v0, f0)
    assert 760.0 < dv < 800.0, dv          # 2 м на площадь ~ 400 м2
    v2, f2, info = _body(steep=0.5, rise_max=2.0)
    assert abs(info["rise"] - 2.0) < 1e-9
    assert mesh_volume(v2, f2) < mesh_volume(v0, f0)


def test_round_crown_holds_more_than_linear():
    vl, fl, il = _body(steep=0.5)
    vr, fr, ir = _body(steep=0.5, shape="round")
    assert abs(ir["rise"] - il["rise"]) < 0.2
    assert mesh_volume(vr, fr) > mesh_volume(vl, fl) * 1.3


def test_floor_follows_a_tilted_contour():
    tilt = SQ.copy()
    tilt[:, 2] = 100.0 + 0.1 * tilt[:, 0]
    a, b, c = crown.fit_plane(tilt[:-1])
    assert abs(a - 0.1) < 1e-9 and abs(b) < 1e-9 and abs(c - 100.0) < 1e-9


def test_distance_is_exact_to_the_segments():
    d = crown.boundary_distance(np.array([10.0, 1.0]), np.array([10.0, 5.0]),
                                SQ)
    assert np.allclose(d, [10.0, 1.0])


def _run(items, geom="polygon", **kw):
    spec = by_name("contour_crown")
    v = spec.defaults()
    v.update({"INPUT": items, "@INPUT": {"geometry": geom}})
    v.update(kw)
    return spec.run(v, Report())


def test_tool_builds_a_closed_body_per_contour():
    flat = SQ.copy()
    flat[:, 2] = np.nan
    items = [{"id": 7, "attrs": {"fz": 50.0}, "parts": [SQ]},
             {"id": 8, "attrs": {}, "parts": [flat + [100, 0, 0]]}]
    out = _run(items, FLOOR_FIELD="fz", FLOOR=10.0, STEEP=0.5,
               CELL=0.5)["OUTPUT"]
    assert out.keep_source == "INPUT" and len(out.features) == 2
    (g1, r1), (g2, r2) = out.features
    assert g1["source"] == 7 and abs(r1[2] - 50.0) < 1e-9   # zmin
    assert abs(r2[2] - 10.0) < 1e-9 and r1[5] == 1 and r2[5] == 1


def test_tool_skips_a_vertical_contour_and_refuses_lines():
    wall = np.array([[0, 0, 0], [20, 0, 0], [20, 0, 30], [0, 0, 30],
                     [0, 0, 0]], dtype=float)
    try:
        _run([{"id": 1, "attrs": {}, "parts": [wall]}])
    except ToolError:
        pass
    else:
        raise AssertionError("отвесный контур тела не даёт")
    try:
        _run([{"id": 1, "attrs": {}, "parts": [SQ]}], geom="line")
    except ToolError:
        pass
    else:
        raise AssertionError("линии - отказ")


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK", name)
            n += 1
    print("all crown tests passed (%d)" % n)
