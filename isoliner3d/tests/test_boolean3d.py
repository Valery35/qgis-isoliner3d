# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Булевы операции через занятость ячеек: два куба с известным ответом.

Запуск: python -m pytest isoliner3d/tests/test_boolean3d.py -q
"""
import os
import sys

import numpy as np

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import boolean3d as b3      # noqa: E402
from isoliner3d.cleanup import mesh_volume, shell_defects   # noqa: E402


def _box(x0, y0, z0, s):
    """Куб стороной s: восемь вершин, двенадцать треугольников."""
    p = np.array([[x0, y0, z0], [x0 + s, y0, z0],
                  [x0 + s, y0 + s, z0], [x0, y0 + s, z0],
                  [x0, y0, z0 + s], [x0 + s, y0, z0 + s],
                  [x0 + s, y0 + s, z0 + s], [x0, y0 + s, z0 + s]],
                 dtype=float)
    f = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
                  [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
                  [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]],
                 dtype=np.int64)
    return p, f


def _bounds(v):
    return (float(v[:, 0].min()), float(v[:, 0].max()),
            float(v[:, 1].min()), float(v[:, 1].max()),
            float(v[:, 2].min()), float(v[:, 2].max()))


def _volume(op, cell):
    a_v, a_f = _box(0.0, 0.0, 0.0, 10.0)
    b_v, b_f = _box(5.0, 0.0, 0.0, 10.0)
    gt, z0, dz, shape = b3.common_box(_bounds(a_v), _bounds(b_v),
                                      cell, op)
    oa = b3.shell_occupancy(a_v, a_f, gt, z0, dz, shape)
    ob = b3.shell_occupancy(b_v, b_f, gt, z0, dz, shape)
    occ = b3.combine(oa, ob, op)
    return float(occ.sum()) * abs(gt[1] * gt[5]) * dz


def test_the_test_cubes_are_closed():
    """Проверочные кубы замкнуты, иначе проверять нечего."""
    v, f = _box(0.0, 0.0, 0.0, 10.0)
    assert shell_defects(v, f)[0] == 0
    assert abs(mesh_volume(v, f) - 1000.0) < 1e-6


def test_three_operations_give_the_known_answer():
    """Два куба со сдвигом: пересечение 500, объединение 1500,
    вычитание 500 кубометров.
    """
    for op, want in (("intersection", 500.0), ("union", 1500.0),
                     ("difference", 500.0)):
        got = _volume(op, 0.25)
        assert abs(got - want) / want < 0.05, (op, got)


def test_the_error_falls_with_the_cell():
    """Ошибка идёт по площади поверхности и убывает вместе с ячейкой.

    Это и есть цена вокселей, и знать её надо числом, а не на слово.
    """
    err = [abs(_volume("intersection", c) - 500.0) / 500.0
           for c in (1.0, 0.5, 0.25)]
    assert err[0] > err[1] > err[2], err
    assert err[2] < 0.03, err[2]


def test_a_hole_in_the_roof_empties_the_body():
    """У незамкнутой сверху оболочки внутренности не остаётся.

    Луч идёт вверх, и без крышки в колонке остаётся одно пересечение:
    правило чётности пары из него не составляет, и ячейки пустуют.
    """
    v, f = _box(0.0, 0.0, 0.0, 10.0)
    no_roof = f[[0, 1, 4, 5, 6, 7, 8, 9, 10, 11]]
    assert shell_defects(v, no_roof)[0] > 0
    gt, z0, dz, shape = b3.common_box(_bounds(v), _bounds(v), 1.0,
                                      "union")
    full = b3.shell_occupancy(v, f, gt, z0, dz, shape).sum()
    torn = b3.shell_occupancy(v, no_roof, gt, z0, dz, shape).sum()
    # Не ровно ноль: по самому краю луч задевает боковые грани
    # и изредка составляет из них пару. Это единицы ячеек из тысячи.
    assert full > 900 and torn < full / 50.0, (full, torn)


def test_a_hole_in_a_wall_is_invisible_to_the_ray():
    """Дыра в БОКОВОЙ стенке лучу вверх не мешает вовсе.

    Вертикальная грань луч не пересекает, и заливка её отсутствия
    не замечает. Поэтому замкнутость проверяется отдельно, счётом
    рёбер, а не тем, что заливка «сработала»: положиться на неё
    значило бы считать объём по дырявому телу и не узнать об этом.
    """
    v, f = _box(0.0, 0.0, 0.0, 10.0)
    no_wall = f[[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]]
    assert shell_defects(v, no_wall)[0] > 0, "стенки нет, дыры есть"
    gt, z0, dz, shape = b3.common_box(_bounds(v), _bounds(v), 1.0,
                                      "union")
    full = b3.shell_occupancy(v, f, gt, z0, dz, shape).sum()
    torn = b3.shell_occupancy(v, no_wall, gt, z0, dz, shape).sum()
    assert torn == full


def test_difference_keeps_the_extent_of_the_first_body():
    """У вычитания охват берётся по первому телу.

    Того, чего в нём нет, результату не принадлежит, и раздувать куб
    на второе тело незачем.
    """
    a = (0.0, 10.0, 0.0, 10.0, 0.0, 10.0)
    b = (100.0, 120.0, 0.0, 10.0, 0.0, 10.0)
    gt_d, _z, _c, shape_d = b3.common_box(a, b, 1.0, "difference")
    gt_u, _z2, _c2, shape_u = b3.common_box(a, b, 1.0, "union")
    assert b3.cell_budget(shape_d) < b3.cell_budget(shape_u) / 5


def test_unknown_operation_is_refused():
    o = np.zeros((2, 2, 2), dtype=bool)
    try:
        b3.combine(o, o, "магия")
    except ValueError:
        return
    raise AssertionError("неизвестная операция должна отвергаться")


def test_points_inside_a_shell_are_exact():
    """Отбор точек оболочкой точен: ячейки для него не нужны.

    Луч пускается из самой точки, и ответ не зависит ни от какого
    шага - в отличие от булевых операций, где точность ограничена
    ячейкой.
    """
    v, f = _box(0.0, 0.0, 0.0, 10.0)
    rng = np.random.default_rng(0)
    p = rng.uniform(-2.0, 12.0, size=(20000, 3))
    got = b3.points_inside(v, f, p)
    want = np.all((p > 0.0) & (p < 10.0), axis=1)
    assert int((got != want).sum()) == 0
    assert 0 < int(want.sum()) < len(p)


def test_points_inside_handles_an_empty_input():
    v, f = _box(0.0, 0.0, 0.0, 10.0)
    assert b3.points_inside(v, f, np.zeros((0, 3))).shape == (0,)


def test_points_inside_a_hollow_shell_skip_the_hole():
    """Полость внутри тела: точки в ней снаружи оболочки.

    Правило чётности само разбирается с вложенными поверхностями:
    над точкой в полости оболочка пересекается дважды.
    """
    outer_v, outer_f = _box(0.0, 0.0, 0.0, 10.0)
    inner_v, inner_f = _box(4.0, 4.0, 4.0, 2.0)
    v = np.vstack([outer_v, inner_v])
    f = np.vstack([outer_f, inner_f + len(outer_v)])
    p = np.array([[5.0, 5.0, 5.0],       # в полости
                  [1.0, 1.0, 1.0],       # в теле
                  [20.0, 5.0, 5.0]])     # снаружи
    got = b3.points_inside(v, f, p)
    assert list(got) == [False, True, False], got


def test_a_point_on_a_face_diagonal_is_still_inside():
    """Точка на диагонали грани не должна выпадать из тела.

    Диагональ - общее ребро двух треугольников грани, и точка на ней
    засчитывалась обоим. Чётность от этого ломалась, и точка
    объявлялась снаружи. У правильной сетки на такой диагонали лежит
    каждая вторая точка.
    """
    v, f = _box(0.0, 0.0, 0.0, 10.0)
    on_diag = np.array([[1.0, 1.0, 1.0], [5.0, 5.0, 5.0],
                        [9.0, 9.0, 9.0]])
    assert b3.points_inside(v, f, on_diag).all()


def test_the_cell_fill_survives_the_same_diagonal():
    """То же и у заливки ячеек: куб не должен выйти пустым."""
    v, f = _box(0.0, 0.0, 0.0, 10.0)
    gt, z0, dz, shape = b3.common_box(_bounds(v), _bounds(v), 1.0,
                                      "union")
    occ = b3.shell_occupancy(v, f, gt, z0, dz, shape)
    assert occ.sum() > 900, int(occ.sum())


if __name__ == "__main__":
    for nm, fn in sorted(globals().items()):
        if nm.startswith("test_") and callable(fn):
            fn()
            print("OK", nm)
    print("all boolean3d tests passed")
