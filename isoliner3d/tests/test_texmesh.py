# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Чистая часть наложения текстуры: координаты, размер, демо-карта.

Сам рендер проверить headless нельзя, для него нужны OpenGL и живое окно.
А вот арифметика, на которой чаще всего и ошибаются (переворот по оси V,
пропорции, попадание углов), проверяется обычным Python.

Запуск:  python isoliner3d/tests/test_texmesh.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(PKG))

import numpy as np                          # noqa: E402
from isoliner3d import texmesh as tm        # noqa: E402
from isoliner3d.demo_map import demo_map     # noqa: E402

CORNERS = np.array([[0.0, 0.0, 0.0], [100.0, 0.0, 0.0],
                    [0.0, 50.0, 0.0], [100.0, 50.0, 0.0]])


def test_texcoords_map_corners_to_unit_square():
    uv = tm.texcoords(CORNERS, 0.0, 100.0, 0.0, 50.0)
    assert uv.shape == (4, 2) and uv.dtype == np.float32
    assert np.allclose(uv[0], [0.0, 0.0])
    assert np.allclose(uv[1], [1.0, 0.0])
    assert np.allclose(uv[2], [0.0, 1.0])
    assert np.allclose(uv[3], [1.0, 1.0])


def test_texcoords_v_grows_northward():
    """Ось V смотрит на север: у северной вершины V больше."""
    v = np.array([[50.0, 10.0, 0.0], [50.0, 40.0, 0.0]])
    uv = tm.texcoords(v, 0.0, 100.0, 0.0, 50.0)
    assert uv[1][1] > uv[0][1]


def test_texcoords_survive_degenerate_extent():
    """Нулевой охват не должен давать деление на ноль."""
    v = np.array([[5.0, 5.0, 0.0]])
    uv = tm.texcoords(v, 5.0, 5.0, 5.0, 5.0)
    assert np.isfinite(uv).all()


def test_texture_size_keeps_aspect():
    w, h = tm.fit_texture_size(1000.0, 250.0, 2048)
    assert w == 2048 and abs(h - 512) <= 1
    w, h = tm.fit_texture_size(250.0, 1000.0, 2048)
    assert h == 2048 and abs(w - 512) <= 1


def test_texture_size_respects_cap_and_floor():
    w, h = tm.fit_texture_size(100.0, 100.0, 99999, cap=4096)
    assert w == 4096 and h == 4096
    w, h = tm.fit_texture_size(100.0, 100.0, 1)
    assert w >= 64 and h >= 64


def test_demo_map_shape_and_corners():
    img = demo_map(nx=400, ny=200, cells=8)
    assert img.shape == (200, 400, 3) and img.dtype == np.uint8
    # четыре угла помечены четырьмя разными цветами
    marks = [tuple(img[5, 5]), tuple(img[5, -5]),
             tuple(img[-5, -5]), tuple(img[-5, 5])]
    assert len(set(marks)) == 4, marks


def test_demo_map_graticule_is_square():
    """Клетки сетки одинаковы по обеим осям: перекос будет видно глазом."""
    img = demo_map(nx=400, ny=200, cells=8)
    grid = np.array([40, 40, 40], dtype=np.uint8)
    rows = [y for y in range(img.shape[0])
            if (img[y] == grid).all(axis=1).mean() > 0.9]
    cols = [x for x in range(img.shape[1])
            if (img[:, x] == grid).all(axis=1).mean() > 0.9]
    assert len(rows) >= 2 and len(cols) >= 2
    assert np.diff(rows[:3]).tolist() == np.diff(cols[:3]).tolist()


def test_demo_map_is_not_flat():
    """На карте должны быть поля, линии и метки, а не одна заливка."""
    img = demo_map(nx=256, ny=256)
    assert len(np.unique(img.reshape(-1, 3), axis=0)) >= 8


def test_polyline_dists_accumulate():
    d = tm.polyline_dists([(0, 0), (30, 40), (30, 140)])
    assert np.allclose(d, [0.0, 50.0, 150.0])


def test_polyline_dists_short_input():
    assert np.allclose(tm.polyline_dists([(1, 1)]), [0.0])
    assert tm.polyline_dists([]).size == 0


def test_ribbon_texcoords_pairs_bottom_and_top():
    uv = tm.ribbon_texcoords([0.0, 50.0, 150.0])
    assert uv.shape == (6, 2)
    assert np.allclose(uv[0::2, 1], 0.0), "чётные вершины - низ ленты"
    assert np.allclose(uv[1::2, 1], 1.0), "нечётные - верх"
    # U одинаков в паре и растёт вдоль линии
    assert np.allclose(uv[0, 0], uv[1, 0])
    assert uv[0, 0] == 0.0 and uv[-1, 0] == 1.0
    assert np.allclose(uv[2, 0], 1.0 / 3.0)


def test_ribbon_texcoords_zero_length():
    """Вырожденная линия не должна давать деления на ноль."""
    uv = tm.ribbon_texcoords([0.0, 0.0])
    assert np.isfinite(uv).all()


def section_extent(length, zmin, zmax, vex, ox, oy):
    """Охват чертежа разреза по полям определения (как во вьювере)."""
    return (ox, ox + length, zmin * vex + oy, zmax * vex + oy)


def test_section_extent_accounts_for_vex():
    """Без учёта vex чертёж растянулся бы по вертикали."""
    ext = section_extent(1000.0, -200.0, 100.0, 5.0, 0.0, 0.0)
    assert ext == (0.0, 1000.0, -1000.0, 500.0)
    plain = section_extent(1000.0, -200.0, 100.0, 1.0, 0.0, 0.0)
    assert plain[3] - plain[2] == 300.0
    assert (ext[3] - ext[2]) == 5.0 * (plain[3] - plain[2])


def test_section_extent_shifts_by_layout():
    """Смещение раскладки переносит охват, не меняя размеров."""
    a = section_extent(800.0, 0.0, 100.0, 2.0, 0.0, 0.0)
    b = section_extent(800.0, 0.0, 100.0, 2.0, 5000.0, -300.0)
    assert (b[1] - b[0]) == (a[1] - a[0])
    assert (b[3] - b[2]) == (a[3] - a[2])
    assert b[0] - a[0] == 5000.0 and b[2] - a[2] == -300.0


def test_section_texture_aspect_matches_ribbon():
    """Пропорции картинки должны совпадать с пропорциями чертежа."""
    length, zmin, zmax, vex = 1200.0, -150.0, 50.0, 4.0
    ext = section_extent(length, zmin, zmax, vex, 0.0, 0.0)
    w, h = tm.fit_texture_size(ext[1] - ext[0], ext[3] - ext[2], 2048)
    want = (ext[1] - ext[0]) / (ext[3] - ext[2])
    assert abs((w / float(h)) / want - 1.0) < 0.01, (w, h, want)


class _FakeLayer(object):
    """Двойник слоя: только идентификатор, без QGIS."""

    def __init__(self, lid):
        self._id = lid

    def id(self):
        return self._id


def test_texture_key_is_stable_and_rounds_extent():
    a = tm.texture_key((0.0, 100.0, 0.0, 50.0), 512, 256,
                       [_FakeLayer("l1")])
    b = tm.texture_key((1e-9, 100.0, 0.0, 50.0), 512, 256,
                       [_FakeLayer("l1")])
    assert a == b, "дрожание границ в микрон не должно ломать кэш"


def test_texture_key_separates_size_and_layers():
    base = (0.0, 100.0, 0.0, 50.0)
    k1 = tm.texture_key(base, 512, 256, [_FakeLayer("l1")])
    k2 = tm.texture_key(base, 1024, 512, [_FakeLayer("l1")])
    k3 = tm.texture_key(base, 512, 256, [_FakeLayer("l2")])
    k4 = tm.texture_key(base, 512, 256, [_FakeLayer("l1"),
                                         _FakeLayer("l2")])
    assert len({k1, k2, k3, k4}) == 4


def test_texture_cache_eviction_and_clear():
    tm.texture_cache_clear()
    saved = tm._TEX_LIMIT
    try:
        tm._TEX_LIMIT = 4096
        img = np.zeros((32, 32, 4), dtype=np.uint8)     # 4 КБ
        for k in range(4):
            tm._tex_put(("k%d" % k,), img.copy())
        count, nbytes = tm.texture_cache_size()
        assert nbytes <= tm._TEX_LIMIT, (count, nbytes)
        tm.texture_cache_clear()
        assert tm.texture_cache_size() == (0, 0)
    finally:
        tm._TEX_LIMIT = saved
        tm.texture_cache_clear()


if __name__ == "__main__":
    ok = 0
    for nm, fn in sorted(globals().items()):
        if nm.startswith("test_") and callable(fn):
            fn()
            print("OK", nm)
            ok += 1
    print("all texmesh tests passed (%d)" % ok)
