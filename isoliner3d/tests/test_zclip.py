# -*- coding: utf-8 -*-
"""Проверка обрезки по отметке.

Обрезка контуром и коридором работает в плане: она отбирает по X и Y
и к высоте не имеет отношения. Отбор по отметке это отдельная вещь,
и считается она здесь, на голом NumPy.
"""

import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
VIEWER = os.path.join(PKG, "viewer3d.py")


def _load():
    src = open(VIEWER, encoding="utf-8").read()
    a = src.index("def z_range_mask(")
    b = src.index("\ndef _map_order(")
    ns = {}
    exec(compile(src[a:b], "viewer3d", "exec"), ns)  # nosec
    return ns["z_range_mask"]


Z = np.array([-50.0, -20.0, 0.0, 20.0, 50.0])


def test_no_range_keeps_everything():
    """Пустой диапазон ничего не режет."""
    fn = _load()
    assert fn(Z, None, None).all()


def test_lower_bound_only():
    fn = _load()
    assert fn(Z, -20.0, None).tolist() == [False, True, True, True, True]


def test_upper_bound_only():
    fn = _load()
    assert fn(Z, None, 0.0).tolist() == [True, True, True, False, False]


def test_both_bounds():
    fn = _load()
    assert fn(Z, -20.0, 20.0).tolist() == [False, True, True, True, False]


def test_bounds_are_inclusive():
    """Отметка ровно на границе остаётся: иначе уровень куба пропадёт."""
    fn = _load()
    assert fn(np.array([-20.0, 20.0]), -20.0, 20.0).tolist() == [True, True]


def test_swapped_bounds_are_taken_as_written():
    """Перепутанные местами границы дают пусто, а не молча меняются.

    Молчаливая перестановка спрятала бы опечатку в поле, и человек
    искал бы причину пустой сцены в данных.
    """
    fn = _load()
    assert not fn(Z, 20.0, -20.0).any()


def test_gaps_are_dropped():
    """Пропуск в отметке не проходит отбор."""
    fn = _load()
    assert fn(np.array([np.nan, 0.0]), -10.0, 10.0).tolist() == [False, True]


def test_shape_is_kept():
    fn = _load()
    assert fn(np.zeros((3, 4)), -1.0, 1.0).shape == (3, 4)


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all zclip tests passed")


if __name__ == "__main__":
    _run()
