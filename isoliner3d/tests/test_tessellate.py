# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Разбивка полигона на треугольники с сохранением вершинных отметок.

Пояс между изолиниями идёт частью по нижнему уровню, частью по верхнему,
и поверхность его должна выходить скатом. До правки было два обрыва:
`_flat_z` судил о фигуре по первым 4096 вершинам и объявлял такой пояс
плоским, а переменная Z уходила на веерную триангуляцию, которая тянет
лучи через фигуру и теряет внутренние кольца.

QGIS не требуется: геометрия подменяется двойниками с тем же набором
методов, какие вызывает viewer3d.

Запуск:  python isoliner3d/tests/test_tessellate.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(PKG))

import numpy as np                       # noqa: E402
from isoliner3d import viewer3d as v3    # noqa: E402


class FakeVertex(object):
    def __init__(self, x, y, z):
        self._x, self._y, self._z = x, y, z

    def x(self):
        return self._x

    def y(self):
        return self._y

    def z(self):
        return self._z


class FakeRing(object):
    """Кольцо вершин: и внешнее кольцо полигона, и треугольник."""

    def __init__(self, pts):
        self._pts = list(pts)

    def vertices(self):
        return [FakeVertex(*p) for p in self._pts]


class FakePart(object):
    def __init__(self, outer, inners=()):
        self._outer = FakeRing(outer)
        self._inners = [FakeRing(r) for r in inners]
        self._all = list(outer)
        for r in inners:
            self._all.extend(r)

    def exteriorRing(self):
        return self._outer

    def numInteriorRings(self):
        return len(self._inners)

    def interiorRing(self, i):
        return self._inners[i]

    def vertices(self):
        return [FakeVertex(*p) for p in self._all]


class FakeGeom(object):
    """Двойник QgsGeometry: только то, что зовёт viewer3d."""

    def __init__(self, parts, tris=None, strict=True):
        self._parts = list(parts)
        self._tris = tris          # что вернёт триангуляция
        self._strict = strict

    def constParts(self):
        return list(self._parts)

    def constGet(self):
        return self._parts[0]

    def isEmpty(self):
        return not self._parts

    def _tri_geom(self):
        if self._tris is None:
            return None
        return FakeGeom([FakePart(t) for t in self._tris])

    def constrainedDelaunayTriangulation(self):
        return self._tri_geom() if self._strict else None

    def delaunayTriangulation(self):
        return self._tri_geom()


def _band():
    """Пояс-прямоугольник: низ на 110, верх на 120, разбит на два
    треугольника. Отметки в триангуляции потеряны (NaN), как их теряет
    GEOS в части сборок."""
    ring = [(0.0, 0.0, 110.0), (10.0, 0.0, 110.0),
            (10.0, 5.0, 120.0), (0.0, 5.0, 120.0), (0.0, 0.0, 110.0)]
    nan = float("nan")
    tris = [[(0.0, 0.0, nan), (10.0, 0.0, nan), (10.0, 5.0, nan)],
            [(0.0, 0.0, nan), (10.0, 5.0, nan), (0.0, 5.0, nan)]]
    return FakeGeom([FakePart(ring[:-1])], tris)


def test_band_keeps_two_levels():
    """Скат: у пояса остаются обе отметки, а не одна на всю фигуру."""
    verts, faces = v3._tessellate(_band())
    assert faces.shape == (2, 3)
    assert verts.shape == (6, 3)
    zs = sorted(set(np.round(verts[:, 2], 6)))
    assert zs == [110.0, 120.0]
    # низ фигуры несёт нижний уровень, верх - верхний
    for x, y, z in verts:
        assert z == (110.0 if y < 2.5 else 120.0)


def test_zfix_flattens():
    """С заданной отметкой вся фигура ложится на неё."""
    verts, _f = v3._tessellate(_band(), zfix=42.0)
    assert np.allclose(verts[:, 2], 42.0)


def test_fill_z_nearest_for_added_point():
    """Точку, добавленную триангуляцией, спасает ближайшая исходная."""
    src = [(0.0, 0.0, 110.0), (10.0, 0.0, 110.0), (10.0, 5.0, 120.0)]
    nan = float("nan")
    tris = [[(0.0, 0.0, nan), (10.0, 0.0, nan), (9.9, 4.9, nan)]]
    verts, miss = v3._fill_z(tris, src)
    assert miss == 1
    assert np.allclose(verts[:, 2], [110.0, 110.0, 120.0])


def test_flat_z_sees_beyond_first_thousands():
    """Расхождение отметок ловится и на двадцатой тысяче вершин."""
    pts = [(float(i), 0.0, 110.0) for i in range(20000)]
    assert v3._flat_z(FakeGeom([FakePart(pts)])) == 110.0
    pts.append((0.0, 1.0, 120.0))
    assert v3._flat_z(FakeGeom([FakePart(pts)])) is None


def test_flat_z_ignores_nan():
    pts = [(0.0, 0.0, 110.0), (1.0, 0.0, float("nan")), (1.0, 1.0, 110.0)]
    assert v3._flat_z(FakeGeom([FakePart(pts)])) == 110.0


def test_hole_survives():
    """Внутреннее кольцо доходит до разбивки: веер его терял."""
    outer = [(0.0, 0.0, 110.0), (10.0, 0.0, 110.0),
             (10.0, 10.0, 120.0), (0.0, 10.0, 120.0)]
    inner = [(4.0, 4.0, 115.0), (6.0, 4.0, 115.0), (6.0, 6.0, 115.0)]
    g = FakeGeom([FakePart(outer, [inner])])
    src = []
    for part in v3._parts_xyz(g):
        src.extend(part)
    assert len(src) == 7
    assert 115.0 in [p[2] for p in src]


class FakeFeature(object):
    def __init__(self, n):
        self._n = n

    def geometry(self):
        return self

    def constGet(self):
        return self

    def nCoordinates(self):
        return self._n


def test_body_budget_counts_vertices():
    """Тысяча мелких поясов проходит, десяток кварталов-гигантов нет."""
    small = [FakeFeature(300) for _ in range(1174)]
    assert len(v3._body_budget(small, 1)[0]) == 1174
    huge = [FakeFeature(200000) for _ in range(10)]
    assert len(v3._body_budget(huge, 1)[0]) == 3
    # хотя бы один объект берётся всегда, каким бы тяжёлым он ни был
    assert len(v3._body_budget([FakeFeature(10 ** 7)], 1)[0]) == 1


def test_body_budget_object_ceiling():
    tiny = [FakeFeature(1) for _ in range(v3._MAX_BODIES + 50)]
    assert len(v3._body_budget(tiny, 1)[0]) == v3._MAX_BODIES


def test_body_budget_reports_what_it_spent():
    """Возвращаются и набранные вершины, и сам бюджет.

    Без этих чисел сообщение об урезании читается как нехватка
    памяти, а крутить пользователю нечего.
    """
    feats = [FakeFeature(1000) for _ in range(10)]
    keep, used, budget = v3._body_budget(feats, 1)
    assert len(keep) == 10
    assert used == 10000
    assert budget == v3.MAX_VERTS_SCENE


def test_body_budget_divisor_changes_what_fits():
    """Делитель бюджета решает, влезет слой целиком или нет.

    Ровно этот случай и наблюдался: 279 тел по 1300 вершин влезают
    при делителе один и обрезаются при двух.
    """
    feats = [FakeFeature(1300) for _ in range(279)]
    assert len(v3._body_budget(feats, 1)[0]) == 279
    assert len(v3._body_budget(feats, 2)[0]) < 279


def test_body_budget_cap_can_be_raised():
    """Поднятый потолок пропускает то, что не влезало."""
    feats = [FakeFeature(1300) for _ in range(279)]
    assert len(v3._body_budget(feats, 2)[0]) < 279
    assert len(v3._body_budget(feats, 2, cap=1200000)[0]) == 279


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK", name)
    print("all tessellate tests passed")
