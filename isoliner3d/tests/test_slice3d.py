# -*- coding: utf-8 -*-
"""Проверка среза куба плоскостью.

Считается на голом NumPy, QGIS не нужен. Срез это вертикальная стенка
вдоль ломаной: узлы стенки берут значение из куба, и по ним строится
меш с раскраской.
"""

import os
import sys

import numpy as np

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import slice3d   # noqa: E402

# Куб 10 на 10 на 5, ячейка 10 м, уровни через 2 м от нуля.
GT = (0.0, 10.0, 0.0, 100.0, 0.0, -10.0)
Z0, DZ = 0.0, 2.0


def _linear():
    """Куб, в котором значение равно X: по нему видно любую ошибку."""
    nz, ny, nx = 5, 10, 10
    xs = GT[0] + (np.arange(nx) + 0.5) * GT[1]
    vol = np.repeat(xs[None, None, :], ny, axis=1)
    return np.repeat(vol, nz, axis=0)


def test_sampling_is_exact_on_a_linear_cube():
    """На линейном кубе выборка возвращает само значение."""
    vol = _linear()
    x = np.array([15.0, 55.0, 95.0])
    y = np.full(3, 50.0)
    z = np.full(3, 4.0)
    got = slice3d.sample_cube(vol, GT, Z0, DZ, x, y, z)
    assert np.allclose(got, x, atol=1e-6), got


def test_sampling_outside_is_a_gap():
    """За краями куба выборка даёт пропуск, а не край."""
    vol = _linear()
    got = slice3d.sample_cube(vol, GT, Z0, DZ,
                              np.array([-50.0, 500.0, 50.0]),
                              np.array([50.0, 50.0, -80.0]),
                              np.array([4.0, 4.0, 4.0]))
    assert not np.isfinite(got[0])
    assert not np.isfinite(got[1])
    assert not np.isfinite(got[2])


def test_sampling_above_and_below_levels_is_a_gap():
    """Выше верхнего и ниже нижнего уровня данных нет."""
    vol = _linear()
    got = slice3d.sample_cube(vol, GT, Z0, DZ, np.array([50.0, 50.0]),
                              np.array([50.0, 50.0]),
                              np.array([-5.0, 40.0]))
    assert not np.isfinite(got).any()


def test_section_follows_the_line():
    """Стенка идёт вдоль ломаной, длина равна сумме отрезков."""
    line = [(0.0, 0.0), (300.0, 0.0), (300.0, 400.0)]
    xy, s = slice3d.walk(line, step=50.0)
    assert abs(s[-1] - 700.0) < 50.0, s[-1]
    assert abs(xy[0][0]) < 1e-9 and abs(xy[0][1]) < 1e-9
    assert abs(xy[-1][1] - 400.0) < 50.0


def test_section_mesh_is_a_wall():
    """Меш это стенка: все узлы лежат на вертикальной ломаной."""
    vol = _linear()
    line = [(5.0, 50.0), (95.0, 50.0)]
    v, f, val = slice3d.section_mesh(vol, GT, Z0, DZ, line, step=10.0)
    assert len(f) > 0
    assert np.allclose(v[:, 1], 50.0, atol=1e-6)
    assert len(val) == len(v)


def test_section_values_follow_the_cube():
    """Значения на стенке те же, что в кубе под ней."""
    vol = _linear()
    line = [(5.0, 50.0), (95.0, 50.0)]
    v, _f, val = slice3d.section_mesh(vol, GT, Z0, DZ, line, step=10.0)
    ok = np.isfinite(val)
    assert np.allclose(val[ok], v[ok, 0], atol=1e-6)


def test_faces_reference_real_vertices():
    vol = _linear()
    v, f, _val = slice3d.section_mesh(vol, GT, Z0, DZ,
                                      [(5.0, 50.0), (95.0, 50.0)],
                                      step=10.0)
    assert f.min() >= 0 and f.max() < len(v)


def test_gaps_drop_the_triangle():
    """Треугольник с пропуском в узле не строится.

    Иначе у стенки появился бы кусок из ничего, и на глаз он выглядел
    бы данными.
    """
    vol = _linear().copy()
    vol[:, :, :5] = np.nan
    v, f, val = slice3d.section_mesh(vol, GT, Z0, DZ,
                                     [(5.0, 50.0), (95.0, 50.0)],
                                     step=10.0)
    assert len(f) > 0
    assert np.isfinite(val[f]).all()


def test_short_line_is_refused():
    vol = _linear()
    try:
        slice3d.section_mesh(vol, GT, Z0, DZ, [(0.0, 0.0)], step=10.0)
    except ValueError:
        return
    raise AssertionError("на одной точке стенку не построить")


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all slice tests passed")


if __name__ == "__main__":
    _run()
