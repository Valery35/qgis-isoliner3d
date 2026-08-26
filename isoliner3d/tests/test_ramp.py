# -*- coding: utf-8 -*-
"""Проверка раскраски по шкале слоя.

Разбор оформления требует QGIS, а сама раскраска нет: она вырезается
из модуля и считается на голом NumPy. Проверяется то, ради чего всё
и делалось - расцветка в сцене должна совпадать с картой, а не быть
похожей на неё.
"""

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(PKG))

VIEWER = os.path.join(PKG, "viewer3d.py")


def _load():
    """Раньше здесь вырезался кусок исходника: импорт окна тянул QGIS.

    Расчётная часть вынесена в отдельный модуль, и теперь она просто
    импортируется.
    """
    from isoliner3d import viewer_core
    return viewer_core.ramp_colors


BREAKS = [0.0, 50.0, 100.0]
COLS = [[0.0, 0.0, 1.0, 1.0],
        [0.0, 1.0, 0.0, 1.0],
        [1.0, 0.0, 0.0, 1.0]]


def test_ends_match_the_ramp_exactly():
    """На концах шкалы цвет ровно тот, что задан."""
    fn = _load()
    got = fn([0.0, 100.0], BREAKS, COLS)
    assert np.allclose(got[0], COLS[0])
    assert np.allclose(got[1], COLS[2])


def test_middle_is_interpolated():
    """Между точками цвет тянется, как на карте."""
    fn = _load()
    got = fn([25.0], BREAKS, COLS)[0]
    assert np.allclose(got, [0.0, 0.5, 0.5, 1.0])


def test_outside_clamps_to_the_ends():
    """Значения вне шкалы прижимаются к её концам, а не заворачиваются."""
    fn = _load()
    got = fn([-500.0, 5000.0], BREAKS, COLS)
    assert np.allclose(got[0], COLS[0])
    assert np.allclose(got[1], COLS[2])


def test_gaps_are_grey_not_data():
    """Пропуск красится серым: пустое место не должно выглядеть данными."""
    fn = _load()
    got = fn([np.nan], BREAKS, COLS)[0]
    assert np.allclose(got, [0.6, 0.6, 0.6, 1.0])


def test_discrete_takes_the_first_break_not_below():
    """Ступенчатая шкала отдаёт цвет первой точки, которая не меньше."""
    fn = _load()
    got = fn([10.0, 50.0, 70.0], BREAKS, COLS, kind="discrete")
    assert np.allclose(got[0], COLS[1])
    assert np.allclose(got[1], COLS[1])
    assert np.allclose(got[2], COLS[2])


def test_exact_paints_only_matches():
    """Точная шкала красит совпадения, остальное уходит серым."""
    fn = _load()
    got = fn([50.0, 51.0], BREAKS, COLS, kind="exact")
    assert np.allclose(got[0], COLS[1])
    assert np.allclose(got[1], [0.6, 0.6, 0.6, 1.0])


def test_alpha_from_the_ramp_survives():
    """Прозрачность из шкалы не теряется по дороге."""
    fn = _load()
    cols = [[0.0, 0.0, 1.0, 0.0], [1.0, 0.0, 0.0, 1.0]]
    got = fn([0.0, 1.0, 0.5], [0.0, 1.0], cols)
    assert abs(got[0][3] - 0.0) < 1e-9
    assert abs(got[1][3] - 1.0) < 1e-9
    assert abs(got[2][3] - 0.5) < 1e-9


def test_empty_ramp_gives_grey():
    """Пустая шкала не роняет сборку."""
    fn = _load()
    got = fn([1.0, 2.0], [], [])
    assert got.shape == (2, 4)
    assert np.allclose(got[0], [0.6, 0.6, 0.6, 1.0])


def test_shape_follows_the_input():
    fn = _load()
    got = fn(np.zeros((3, 5)), BREAKS, COLS)
    assert got.shape == (3, 5, 4)


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all ramp tests passed")


if __name__ == "__main__":
    _run()
