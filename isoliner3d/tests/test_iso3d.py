# -*- coding: utf-8 -*-
"""Проверка изоповерхности по кубу значений.

Считается на голом NumPy, QGIS не нужен.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from isoliner3d import iso3d   # noqa: E402
from isoliner3d.iso3d import isosurface, is_watertight   # noqa: E402

GT = (0.0, 1.0, 0.0, 20.0, 0.0, -1.0)


def _sphere(n=21, radius=6.3):
    zz, yy, xx = np.mgrid[0:n, 0:n, 0:n].astype(float)
    c = (n - 1) / 2.0
    vol = radius - np.sqrt((xx - c) ** 2 + (yy - c) ** 2 + (zz - c) ** 2)
    gt = (0.0, 1.0, 0.0, float(n - 1), 0.0, -1.0)
    centre = np.array([gt[0] + (c + 0.5) * gt[1],
                       gt[3] + (c + 0.5) * gt[5], c])
    return vol, gt, centre


def test_plane_cut_is_exact():
    """Горизонтальная граница даёт срез ровно на своей отметке."""
    n = 6
    zz, _yy, _xx = np.mgrid[0:n, 0:n, 0:n].astype(float)
    v, f = isosurface(2.5 - zz, 0.0, GT, 0.0, 1.0)
    assert len(f) > 0
    assert np.allclose(v[:, 2], 2.5)


def test_shell_is_watertight():
    """Оболочка замкнута: каждое ребро входит ровно в две грани.

    Ради этого взят марш по тетраэдрам: у кубов есть неоднозначные
    случаи, на которых соседние ячейки расходятся и оставляют дыру.
    """
    vol, gt, _c = _sphere()
    v, f = isosurface(vol, 0.0, gt, 0.0, 1.0)
    assert len(f) > 1000
    assert is_watertight(v, f)


def test_radius_is_accurate():
    """Вершины ложатся на поверхность шара, а не на узлы сетки."""
    vol, gt, centre = _sphere(radius=6.3)
    v, _f = isosurface(vol, 0.0, gt, 0.0, 1.0)
    r = np.sqrt(((v - centre) ** 2).sum(axis=1))
    assert abs(r.mean() - 6.3) < 0.05, r.mean()
    assert r.std() < 0.05, r.std()


def test_volume_matches_the_sphere():
    """Объём по оболочке сходится с объёмом шара.

    Проверяет заодно ориентацию граней: если часть смотрит внутрь,
    слагаемые гасят друг друга и объём выходит меньше.
    """
    vol, gt, centre = _sphere(radius=6.3)
    v, f = isosurface(vol, 0.0, gt, 0.0, 1.0)
    t = v[f] - centre
    got = np.einsum('ij,ij->i', t[:, 0],
                    np.cross(t[:, 1], t[:, 2])).sum() / 6.0
    want = 4.0 / 3.0 * np.pi * 6.3 ** 3
    assert abs(got - want) / want < 0.05, (got, want)


def test_gaps_stay_outside():
    """Пропуски в данных не притягивают оболочку."""
    n = 8
    vol = np.full((n, n, n), 5.0)
    vol[:, :, 4:] = np.nan
    v, f = isosurface(vol, 1.0, GT, 0.0, 1.0)
    assert len(f) > 0
    assert v[:, 0].max() < 5.0, v[:, 0].max()


def test_empty_volume_gives_nothing():
    vol = np.zeros((4, 4, 4))
    v, f = isosurface(vol, 10.0, GT, 0.0, 1.0)
    assert len(f) == 0 and len(v) == 0


def test_welding_glues_shared_vertices():
    """Склейка убирает повторы: соседние грани делят вершину.

    Марш даёт три вершины на грань без единого общего ребра.
    На кубе это втрое больше памяти и втрое больше работы у сцены.
    """
    vol, gt, _c = _sphere()
    raw_v, raw_f = isosurface(vol, 0.0, gt, 0.0, 1.0, weld=False)
    v, f = isosurface(vol, 0.0, gt, 0.0, 1.0)
    assert len(raw_v) == 3 * len(raw_f)
    assert len(v) < len(raw_v) / 2.0, (len(v), len(raw_v))
    assert len(f) == len(raw_f)


def test_welding_keeps_the_shape():
    """Склейка не двигает геометрию: те же треугольники, те же точки."""
    vol, gt, _c = _sphere()
    raw_v, raw_f = isosurface(vol, 0.0, gt, 0.0, 1.0, weld=False)
    v, f = isosurface(vol, 0.0, gt, 0.0, 1.0)
    a = np.sort(raw_v[raw_f].reshape(-1, 9), axis=0)
    b = np.sort(v[f].reshape(-1, 9), axis=0)
    assert np.allclose(a, b, atol=1e-6)


def test_welded_shell_is_still_watertight():
    vol, gt, _c = _sphere()
    v, f = isosurface(vol, 0.0, gt, 0.0, 1.0)
    assert is_watertight(v, f)


def test_levels_match_single_calls():
    """Один проход по уровням даёт ровно то же, что отдельные вызовы."""
    vol, gt, _c = _sphere()
    levels = [-2.0, 0.0, 2.0]
    many = iso3d.isosurface_levels(vol, levels, gt, 0.0, 1.0)
    assert [lv for lv, _v, _f in many] == levels
    for lv, v, f in many:
        v1, f1 = isosurface(vol, lv, gt, 0.0, 1.0)
        assert len(v) == len(v1) and len(f) == len(f1), lv
        assert np.allclose(np.sort(v[f].reshape(-1, 9), axis=0),
                           np.sort(v1[f1].reshape(-1, 9), axis=0),
                           atol=1e-6), lv


def test_only_boundary_cells_are_walked():
    """Работа идёт по пограничным ячейкам, а не по всему кубу.

    Ячейки целиком внутри и целиком снаружи граней не дают, а их
    подавляющее большинство. Проверяем через время: куб вдвое крупнее
    даёт вчетверо больше площади и восьмикратно больше ячеек, и если
    бы перебор шёл по всем ячейкам, время росло бы как объём.
    """
    import time
    small = _sphere(n=31, radius=10.0)
    big = _sphere(n=61, radius=20.0)
    times = []
    for vol, gt, _c in (small, big):
        t = time.time()
        isosurface(vol, 0.0, gt, 0.0, 1.0)
        times.append(time.time() - t)
    grow = times[1] / max(times[0], 1e-6)
    assert grow < 6.0, grow


def test_five_levels_stay_quick():
    """Пять уровней на рабочем кубе укладываются в разумное время.

    Сторож против отката: до правки те же пять уровней считались
    пятнадцать с половиной секунд и занимали пятьдесят мегабайт.
    """
    import time
    n = 60
    zz, yy, xx = np.mgrid[0:n, 0:n, 0:n].astype(float)
    c = (n - 1) / 2.0
    vol = 20.0 - np.sqrt((xx - c) ** 2 + (yy - c) ** 2 + (zz - c) ** 2)
    gt = (0.0, 1.0, 0.0, float(n - 1), 0.0, -1.0)
    t = time.time()
    got = iso3d.isosurface_levels(vol, [-6.0, -3.0, 0.0, 3.0, 6.0],
                                  gt, 0.0, 1.0)
    dt = time.time() - t
    assert len(got) == 5
    assert dt < 8.0, dt
    verts = sum(len(v) for _l, v, _f in got)
    faces = sum(len(f) for _l, _v, f in got)
    assert verts < faces, (verts, faces)


def test_empty_levels_give_nothing():
    vol, gt, _c = _sphere()
    assert iso3d.isosurface_levels(vol, [], gt, 0.0, 1.0) == []


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all iso3d tests passed")


if __name__ == "__main__":
    _run()
