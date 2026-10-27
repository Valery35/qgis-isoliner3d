# -*- coding: utf-8 -*-
"""Разрез 2D-инверсии ячейками вдоль профиля.

Считается на голом NumPy, QGIS не нужен.
"""

import os
import sys

import numpy as np

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import section2d as s2       # noqa: E402


def _grid(xs, ys, zs):
    X = np.repeat(xs, len(zs))
    Y = np.repeat(ys, len(zs))
    Z = np.tile(zs, len(xs))
    return X, Y, Z


def test_straight_profile_tiles_the_section():
    """Прямой профиль по диагонали: ячейки покрывают разрез без щелей.

    Шаг вдоль профиля 10 м, по высоте 5 м, десять точек на восемь
    отметок. Площадь всех ячеек - длина профиля плюс полшага с каждой
    стороны, на высоту.
    """
    t = np.arange(10) * 10.0
    xs, ys = 1000 + t * 0.6, 2000 + t * 0.8
    zs = np.arange(8) * -5.0 + 100
    X, Y, Z = _grid(xs, ys, zs)
    rng = np.random.default_rng(3)
    p = rng.permutation(len(X))           # порядок строк не важен
    c = s2.cells(X[p], Y[p], Z[p])
    assert all(len(f) == 1 for f in c)
    total = sum(s2.area(f) for f in c)
    assert abs(total - 100.0 * 40.0) < 1e-6
    f = c[int(np.argmin(np.hypot(X[p] - xs[4], Y[p] - ys[4])
                        + np.abs(Z[p] - zs[3])))][0]
    assert np.allclose(f[:, 2].min(), zs[3] - 2.5)
    assert np.allclose(np.hypot(f[1, 0] - f[0, 0], f[1, 1] - f[0, 1]), 10)


def test_bent_profile_has_two_faces_at_the_bend():
    xs = np.array([0.0, 10.0, 20.0, 20.0, 20.0])
    ys = np.array([0.0, 0.0, 0.0, 10.0, 20.0])
    c = s2.cells(xs, ys, np.zeros(5))
    assert len(c[2]) == 2 and len(c[1]) == 1
    # грани у излома сходятся в точке профиля
    assert np.allclose(c[2][0][1, :2], (20.0, 0.0))
    assert np.allclose(c[2][1][0, :2], (20.0, 0.0))
    assert abs(sum(s2.area(f) for f in c) - 50.0) < 1e-9


def test_gap_in_the_profile_is_not_bridged():
    xs = np.array([0.0, 10.0, 20.0, 200.0, 210.0])
    c = s2.cells(xs, np.zeros(5), np.zeros(5))
    # точка у разрыва тянется на полшага, а не до середины дыры
    f = c[2][0]
    assert np.allclose(f[:, 0].max(), 25.0)
    assert np.allclose(c[3][0][:, 0].min(), 195.0)


def test_variable_cell_height():
    xs = np.repeat([0.0, 10.0], 3)
    z = np.tile([-1.0, -4.0, -11.0], 2)
    dz = np.tile([2.0, 4.0, 10.0], 2)
    c = s2.cells(xs, np.zeros(6), z, dz)
    lo = [f[0][:, 2].min() for f in c[:3]]
    hi = [f[0][:, 2].max() for f in c[:3]]
    assert np.allclose(lo, [-2, -6, -16]) and np.allclose(hi, [0, -2, -6])


def test_vertical_step_and_stations():
    xy, st = s2.stations([1.0, 1.0004, 5.0], [2.0, 2.0, 2.0])
    assert len(xy) == 2 and st[0] == st[1]
    assert s2.vertical_step([10, 5, 0, 10, 5]) == 5.0


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all section2d tests passed")


if __name__ == "__main__":
    _run()
