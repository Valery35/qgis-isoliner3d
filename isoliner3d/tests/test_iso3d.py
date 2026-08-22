# -*- coding: utf-8 -*-
"""Проверка изоповерхности по кубу значений.

Считается на голом NumPy, QGIS не нужен.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

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


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all iso3d tests passed")


if __name__ == "__main__":
    _run()
