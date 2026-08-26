# -*- coding: utf-8 -*-
"""Проверка чистки поверхности: сглаживание и отброс мелочи.

Маршевая поверхность идёт ступенями по ячейкам, и мелкие обрывки на ней
шумят. Лечится это прямо на поверхности: сгладить вершины и выбросить
куски мельче заданного числа граней. Сшивать изолинии между уровнями
для этого не нужно.

Считается на голом NumPy, QGIS не нужен.
"""

import os
import sys

import numpy as np

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import cleanup   # noqa: E402


def _two_parts():
    """Большой квадрат и крохотный треугольник в стороне."""
    v = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0],
                  [0.0, 1.0, 0.0],
                  [9.0, 9.0, 0.0], [9.1, 9.0, 0.0], [9.0, 9.1, 0.0]])
    f = np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6]])
    return v, f


def test_small_part_is_dropped():
    """Кусок мельче порога выбрасывается целиком."""
    v, f = _two_parts()
    _v2, f2 = cleanup.drop_small(v, f, min_faces=2)
    assert len(f2) == 2, len(f2)


def test_big_part_survives():
    v, f = _two_parts()
    _v2, f2 = cleanup.drop_small(v, f, min_faces=1)
    assert len(f2) == 3


def test_dropping_everything_is_refused():
    """Порог выше всего оставляет поверхность как была.

    Пустая сцена вместо тела это не чистка, а потеря: лучше показать
    как есть и дать человеку убавить порог.
    """
    v, f = _two_parts()
    _v2, f2 = cleanup.drop_small(v, f, min_faces=100)
    assert len(f2) == len(f)


def test_parts_are_counted():
    v, f = _two_parts()
    assert cleanup.count_parts(v, f) == 2


def test_smoothing_pulls_a_spike_in():
    """Ступень сглаживается: выброс тянется к соседям.

    Выброс берём внутренним: краевая вершина стоит на месте
    по построению, и на ней сглаживания не увидеть.
    """
    xs, ys = np.meshgrid(np.arange(3.0), np.arange(3.0))
    v = np.column_stack([xs.ravel(), ys.ravel(),
                         np.zeros(9)])
    v[4, 2] = 5.0                      # середина поднята
    f = []
    for r in range(2):
        for c in range(2):
            a = r * 3 + c
            f += [[a, a + 1, a + 4], [a, a + 4, a + 3]]
    f = np.array(f, dtype=np.int64)
    v2 = cleanup.smooth(v, f, rounds=3, strength=0.5)
    assert v2[4, 2] < 2.0, v2[4, 2]


def test_smoothing_keeps_the_border():
    """Края не двигаются: иначе срез перестанет лежать в плоскости.

    Крышка на срезе строится по краевым рёбрам, и стоит их сдвинуть,
    как она перестанет сходиться с телом.
    """
    v = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0],
                  [0.0, 1.0, 0.0], [0.5, 0.5, 3.0]])
    f = np.array([[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]])
    v2 = cleanup.smooth(v, f, rounds=5, strength=1.0)
    assert np.allclose(v2[:4], v[:4]), v2[:4]
    assert v2[4, 2] < 3.0


def test_smoothing_zero_rounds_changes_nothing():
    v, f = _two_parts()
    assert np.allclose(cleanup.smooth(v, f, rounds=0), v)


def test_smoothing_survives_an_empty_mesh():
    v = np.zeros((0, 3))
    f = np.zeros((0, 3), dtype=np.int64)
    assert len(cleanup.smooth(v, f, rounds=2)) == 0
    assert len(cleanup.drop_small(v, f, 3)[1]) == 0


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all cleanup tests passed")


if __name__ == "__main__":
    _run()
