# -*- coding: utf-8 -*-
"""Проверка объёмной заливки: передаточная функция значение - цвет.

Считается на голом NumPy, QGIS не нужен. Рендер объёма умеет одно:
показать четырёхмерный массив цвета с прозрачностью. Всё остальное
решает передаточная функция, и проверяется здесь именно она.
"""

import os
import sys

import numpy as np

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import volume   # noqa: E402


def _cube():
    """Куб 4 на 3 на 2, значение равно номеру уровня."""
    nz, ny, nx = 2, 3, 4
    vol = np.zeros((nz, ny, nx))
    vol[1] = 1.0
    return vol


def test_shape_and_type_fit_the_renderer():
    """Рендер объёма ждёт массив (x, y, z, RGBA) из байтов.

    Куб у нас лежит как (уровень, строка, столбец), и порядок осей
    надо развернуть: иначе заливка выйдет перевёрнутой.
    """
    got = volume.rgba(_cube(), cutoff=None)
    assert got.shape == (4, 3, 2, 4), got.shape
    assert got.dtype == np.uint8, got.dtype


def test_alpha_grows_with_value():
    """Чем больше значение, тем плотнее заливка."""
    vol = np.array([[[0.0, 0.5, 1.0]]])
    got = volume.rgba(vol, cutoff=None)
    a = got[:, 0, 0, 3].astype(int)
    assert a[0] < a[1] < a[2], a


def test_below_cutoff_is_invisible():
    """Ниже отсечки заливки нет вовсе.

    Без отсечки виден весь ящик целиком, и тело в тумане не разглядеть:
    показывать надо то, что выше неё.
    """
    vol = np.array([[[0.0, 1.0, 2.0, 3.0]]])
    got = volume.rgba(vol, cutoff=2.0)
    a = got[:, 0, 0, 3].astype(int)
    assert a[0] == 0 and a[1] == 0, a
    assert a[3] > 0, a


def test_gaps_are_invisible():
    """Пропуск в данных не заливается: пустота это не ноль."""
    vol = np.array([[[np.nan, 1.0]]])
    got = volume.rgba(vol, cutoff=None)
    assert int(got[0, 0, 0, 3]) == 0
    assert int(got[1, 0, 0, 3]) > 0


def test_density_scales_the_alpha():
    """Плотность правит непрозрачность целиком."""
    vol = np.array([[[0.0, 1.0]]])
    thin = volume.rgba(vol, cutoff=None, density=0.2)
    thick = volume.rgba(vol, cutoff=None, density=1.0)
    assert int(thin[1, 0, 0, 3]) < int(thick[1, 0, 0, 3])


def test_density_zero_hides_everything():
    vol = np.array([[[0.0, 1.0]]])
    got = volume.rgba(vol, cutoff=None, density=0.0)
    assert int(got[:, :, :, 3].max()) == 0


def test_colour_comes_from_the_ramp():
    """Цвет берётся из шкалы, а не из серого: заливка читается по цвету."""
    vol = np.array([[[0.0, 1.0]]])
    got = volume.rgba(vol, cutoff=None)
    lo = got[0, 0, 0, :3].astype(int)
    hi = got[1, 0, 0, :3].astype(int)
    assert list(lo) != list(hi), (lo, hi)


def test_flat_cube_does_not_divide_by_zero():
    """Куб из одного значения не роняет расчёт."""
    got = volume.rgba(np.full((2, 2, 2), 5.0), cutoff=None)
    assert np.isfinite(got.astype(float)).all()


def test_empty_cube_gives_nothing():
    assert volume.rgba(np.full((2, 2, 2), np.nan), cutoff=None) is None


def test_size_is_capped():
    """Слишком крупный куб не берётся: память кончится раньше пользы."""
    big = np.zeros((300, 300, 300))
    assert volume.rgba(big, cutoff=None, max_cells=1000) is None


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all volume tests passed")


if __name__ == "__main__":
    _run()
