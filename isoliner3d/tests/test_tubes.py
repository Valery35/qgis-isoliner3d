# -*- coding: utf-8 -*-
"""Линии трубами: геометрия трубы и толщина по значению.

Считается на голом NumPy, QGIS не нужен.
"""

import os
import sys

import numpy as np

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import tubes                   # noqa: E402
from isoliner3d.cleanup import mesh_volume, shell_defects   # noqa: E402


def _dist_to_polyline(q, p):
    best = np.full(len(q), np.inf)
    for a, b in zip(p[:-1], p[1:]):
        ab = b - a
        t = np.clip(((q - a) @ ab) / (ab @ ab), 0.0, 1.0)
        best = np.minimum(best, np.linalg.norm(q - (a + t[:, None] * ab),
                                               axis=1))
    return best


def test_straight_tube_has_the_given_radius_and_volume():
    """Прямая труба: стенка на радиусе, объём как у призмы на кольце."""
    p = np.array([[0.0, 0.0, 0.0], [100.0, 0.0, 0.0]])
    v, f = tubes.tube_mesh(p, 2.0, sides=24)
    ring = v[:-2]
    d = np.hypot(ring[:, 1], ring[:, 2])
    assert np.allclose(d, 2.0), d
    holes, _pinch = shell_defects(v, f)
    assert holes == 0
    # 24-угольник с радиусом описанной окружности 2
    area = 0.5 * 24 * 4.0 * np.sin(2 * np.pi / 24)
    assert abs(mesh_volume(v, f) - area * 100.0) < 1e-6


def _dist_to_line(q, a, b):
    u = (b - a) / np.linalg.norm(b - a)
    w = q - a
    return np.linalg.norm(w - (w @ u)[:, None] * u, axis=1)


def test_bend_keeps_the_wall_thickness():
    """На изломе стенка держит радиус: ни щели, ни сужения.

    Кольцо на изломе лежит в биссекторной плоскости и растянуто
    ровно настолько, чтобы каждая его точка была на радиусе от оси
    и входящего, и выходящего звена. Тогда стенки двух звеньев
    встречаются на кольце без щели и без врезки.
    """
    p = np.array([[0.0, 0.0, 0.0], [50.0, 0.0, 0.0], [50.0, 50.0, 10.0],
                  [0.0, 80.0, 10.0]])
    r = 1.5
    v, f = tubes.tube_mesh(p, r, sides=16)
    rings = v[:-2].reshape(len(p), 16, 3)
    for i in range(1, len(p) - 1):
        d_in = _dist_to_line(rings[i], p[i - 1], p[i])
        d_out = _dist_to_line(rings[i], p[i], p[i + 1])
        assert np.allclose(d_in, r, rtol=1e-6), (i, d_in)
        assert np.allclose(d_out, r, rtol=1e-6), (i, d_out)
    holes, _pinch = shell_defects(v, f)
    assert holes == 0


def test_rings_do_not_twist_along_a_curve():
    """Кольца не проворачиваются: стенка не скручивается жгутом.

    На спирали соседние кольца сдвинуты вдоль оси, но не повёрнуты:
    одна и та же вершина кольца у соседних вершин ломаной
    почти не сдвигается поперёк оси.
    """
    t = np.linspace(0, 4 * np.pi, 200)
    p = np.column_stack([30 * np.cos(t), 30 * np.sin(t), 5 * t])
    sides = 8
    v, _f = tubes.tube_mesh(p, 1.0, sides=sides, caps=False)
    rings = v.reshape(len(p), sides, 3)
    jump = np.linalg.norm(np.diff(rings[:, 0, :], axis=0), axis=1)
    step = np.linalg.norm(np.diff(p, axis=0), axis=1)
    assert (jump < step + 0.3).all(), float((jump - step).max())


def test_radius_per_vertex():
    p = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [20.0, 0.0, 0.0]])
    v, _f = tubes.tube_mesh(p, [1.0, 2.0, 3.0], sides=12, caps=False)
    rings = v.reshape(3, 12, 3)
    for k, r in enumerate((1.0, 2.0, 3.0)):
        assert np.allclose(np.hypot(rings[k, :, 1], rings[k, :, 2]), r)


def test_degenerate_lines_give_nothing():
    """Повтор вершин выбрасывается, точка трубы не даёт."""
    p = np.array([[1.0, 2.0, 3.0], [1.0, 2.0, 3.0]])
    v, f = tubes.tube_mesh(p, 1.0)
    assert not len(v) and not len(f)
    p = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [5.0, 0.0, 0.0]])
    v, f = tubes.tube_mesh(p, 1.0, sides=6)
    assert len(f) == 2 * 6 + 2 * 6


def test_hairpin_does_not_blow_up():
    """Разворот на шпильке не протыкает сцену шипом."""
    p = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.0, 0.1, 0.0]])
    v, _f = tubes.tube_mesh(p, 1.0, sides=8)
    d = _dist_to_polyline(v, p)
    assert d.max() <= 1.0 * tubes.MAX_MITER + 1e-6


def test_many_tubes_keep_owners():
    a = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]])
    b = np.array([[0.0, 5.0, 0.0], [10.0, 5.0, 0.0], [10.0, 9.0, 0.0]])
    empty = np.array([[3.0, 3.0, 3.0]])
    v, f, own = tubes.many_tubes([a, empty, b], [1.0, 1.0, 2.0], sides=6)
    assert len(own) == len(v)
    assert set(own.tolist()) == {0, 2}
    assert f.max() < len(v)
    assert np.allclose(v[own == 2][:, 1].mean(), 6.0, atol=2.0)


def test_value_to_diameter_by_area_and_linear():
    """По площади: площадь сечения пропорциональна значению."""
    vals = [0.0, 50.0, 100.0, np.nan]
    d = tubes.value_to_diameter(vals, 1.0, 5.0, "area")
    assert d[0] == 1.0 and d[2] == 5.0
    assert abs(d[1] ** 2 - 0.5 * (1.0 + 25.0)) < 1e-9
    assert d[3] == 1.0                # пусто - наименьший диаметр
    lin = tubes.value_to_diameter(vals, 1.0, 5.0, "linear")
    assert abs(lin[1] - 3.0) < 1e-12
    same = tubes.value_to_diameter([7.0, 7.0], 1.0, 5.0)
    assert (same == 5.0).all()
    cut = tubes.value_to_diameter([0.0, 200.0], 1.0, 5.0, "linear",
                                  vmin=0.0, vmax=100.0)
    assert cut[1] == 5.0              # выше шкалы - упор в наибольший


def test_sides_fit_the_budget():
    assert tubes.sides_for(100, 1e6) == 12
    assert tubes.sides_for(200000, 1e6) == 5
    assert tubes.sides_for(10 ** 7, 1e6) == 4


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all tubes tests passed")


if __name__ == "__main__":
    _run()
