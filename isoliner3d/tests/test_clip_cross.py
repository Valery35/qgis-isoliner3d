# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Грани, сквозь которые проходит граница обрезки (viewer_core).

Обрезка окна решала по вершинам, и длинная грань, обе вершины которой
вне контура, выбрасывалась целиком, хотя контур её пересекает: штрек
из демо пропадал при «оставить внутри» и не резался при «убрать
внутри». boundary_crossing находит такие грани, а окно их режет.
Живая проверка в QGIS - tools/qgis_check/run_clip.py.

Запуск:  python isoliner3d/tests/test_clip_cross.py
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from isoliner3d.viewer_core import (  # noqa: E402
    boundary_crossing, cut_z, ring_start_shift)


def _square(x0, x1, y0, y1):
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    return np.array([[pts[i], pts[i + 1]] for i in range(4)], dtype=float)


def _tri(*xyz):
    return np.array(xyz, dtype=float)


def test_long_face_with_both_ends_outside_is_crossed():
    """Грань во всю длину колена: контур посередине, вершины снаружи."""
    tv = np.array([_tri((0, 0, 0), (100, 0, 0), (100, 5, 0))])
    got = boundary_crossing(tv, [False], _square(30, 60, -10, 10))
    assert got.tolist() == [True]


def test_face_inside_or_away_is_not_crossed():
    tv = np.array([_tri((40, 0, 0), (50, 0, 0), (50, 5, 0)),
                   _tri((200, 0, 0), (210, 0, 0), (210, 5, 0))])
    got = boundary_crossing(tv, [False, False], _square(30, 60, -10, 10))
    assert got.tolist() == [False, False]


def test_small_contour_inside_a_big_face():
    """Контур целиком внутри грани: сторону он не режет, но вершина
    границы лежит внутри грани."""
    tv = np.array([_tri((0, 0, 0), (100, 0, 0), (0, 100, 0))])
    got = boundary_crossing(tv, [False], _square(10, 20, 10, 20))
    assert got.tolist() == [True]


def test_vertical_wall_is_checked_by_its_plan_segment():
    """Отвесная стена в плане - отрезок: проверяется он."""
    wall = _tri((0, 0, -10), (100, 0, -10), (100, 0, 0))
    away = _tri((0, 50, -10), (100, 50, -10), (100, 50, 0))
    tv = np.array([wall, away])
    got = boundary_crossing(tv, [True, True], _square(30, 60, -10, 10))
    assert got.tolist() == [True, False]


def test_empty_inputs():
    assert boundary_crossing(np.zeros((0, 3, 3)), [], _square(0, 1, 0, 1)) \
        .tolist() == []
    tv = np.array([_tri((0, 0, 0), (1, 0, 0), (0, 1, 0))])
    assert boundary_crossing(tv, [False], np.zeros((0, 2, 2))).tolist() \
        == [False]


def test_many_faces_in_chunks():
    """Деление на куски не теряет граней."""
    xs = np.arange(0, 1000, 10.0)
    tv = np.array([_tri((x, -50, 0), (x + 10, -50, 0), (x, 50, 0))
                   for x in xs])
    got = boundary_crossing(tv, np.zeros(len(tv), bool),
                            _square(-5, 2000, -1, 1), chunk=7)
    assert got.all()


def test_cut_point_on_a_shared_edge_gets_one_height():
    """Крутая узкая грань и её соседка ставят точку на общем ребре
    на одну высоту: иначе вершины не сшиваются и в теле щель."""
    edge_a, edge_b = (0.05, 2.5, -297.0), (117.5, 2.5, -302.0)
    sliver = _tri(edge_a, (117.56, 2.56, -299.0), edge_b)
    wide = _tri(edge_a, edge_b, (60.0, -40.0, -310.0))
    x = np.array([30.0])
    y = np.array([2.5])
    want = -297.0 + (30.0 - 0.05) / (117.5 - 0.05) * (-5.0)
    assert abs(cut_z(sliver, x, y)[0] - want) < 1e-9
    assert abs(cut_z(wide, x, y)[0] - want) < 1e-9


def test_cut_point_inside_takes_the_plane():
    tri = _tri((0, 0, 0), (10, 0, 10), (0, 10, 0))
    assert abs(cut_z(tri, np.array([2.0]), np.array([3.0]))[0] - 2.0) \
        < 1e-12


def test_ring_start_moves_off_the_cut():
    """Кольцо коридора начинается во внутреннем углу, на самом срезе:
    точки среза у конца кольца и у его начала. Начало отсчёта уходит
    в самый большой пустой промежуток, и срез идёт подряд."""
    s = [499.6, 499.9, 0.0, 20.7, 82.0, 82.04]
    spans = [(499.6, 499.9), (499.9, 0.0), (0.0, 20.7), (20.7, 82.0)]
    s0 = ring_start_shift(s, 501.09, spans)
    assert 82.04 < s0 < 499.6
    moved = sorted((x - s0) % 501.09 for x in s)
    # после сдвига срез идёт одним куском, без скачка через длину кольца
    assert moved[-1] - moved[0] < 101.0


def test_ring_start_stays_when_the_cut_is_away():
    assert ring_start_shift([100.0, 150.0, 160.0], 1000.0) == 0.0
    assert ring_start_shift([5.0], 1000.0) == 0.0


def test_ring_start_does_not_split_a_long_edge():
    """Самый большой промежуток перекрыт одним ребром среза: туда
    начало не ставится, берётся следующий по величине."""
    s = [0.0, 10.0, 400.0, 420.0]
    spans = [(10.0, 400.0, 200.0)]       # середина ребра - на 200 м
    s0 = ring_start_shift(s, 500.0, spans)
    assert not (10.0 < s0 < 400.0)
    assert 420.0 < s0 < 500.0 or s0 == 0.0
    # то же ребро, но идущее через начало кольца: середина на 480 м
    s0 = ring_start_shift(s, 500.0, [(10.0, 400.0, 480.0)])
    assert 10.0 < s0 < 400.0


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK", name)
            n += 1
    print("all clip-cross tests passed (%d)" % n)
