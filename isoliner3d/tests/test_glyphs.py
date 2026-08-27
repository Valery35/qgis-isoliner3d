# -*- coding: utf-8 -*-
"""Проверка чертёжных цифр: подписи линиями.

В GLB текста как такового не бывает: либо геометрия букв, либо картинка
на плоскости. Плоская картинка при повороте встаёт ребром и пропадает,
поэтому цифры рисуются отрезками, как на чертеже.

Считается на голом NumPy, QGIS не нужен.
"""

import os
import sys

import numpy as np

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import glyphs   # noqa: E402


def test_every_digit_has_strokes():
    """У каждой цифры есть штрихи, иначе подпись выйдет с дырой."""
    for ch in "0123456789":
        assert glyphs.STROKES.get(ch), ch


def test_minus_and_dot_are_there():
    """Отметки бывают отрицательными и дробными."""
    assert glyphs.STROKES.get("-")
    assert glyphs.STROKES.get(".") is not None


def test_unknown_character_is_skipped():
    """Незнакомый знак пропускается, а не роняет подпись."""
    segs = glyphs.text_segments("1@2", 1.0)
    assert segs
    for a, b in segs:
        assert len(a) == 2 and len(b) == 2


def test_text_grows_to_the_right():
    """Знаки идут слева направо и не наезжают друг на друга."""
    one = glyphs.text_segments("1", 1.0)
    two = glyphs.text_segments("11", 1.0)
    assert len(two) == 2 * len(one)
    x_one = max(max(a[0], b[0]) for a, b in one)
    x_two = max(max(a[0], b[0]) for a, b in two)
    assert x_two > x_one


def test_height_follows_the_size():
    """Высота знака равна заданному размеру."""
    for size in (1.0, 25.0):
        segs = glyphs.text_segments("8", size)
        ys = [q[1] for a, b in segs for q in (a, b)]
        assert abs((max(ys) - min(ys)) - size) < 1e-6, size


def test_empty_text_gives_nothing():
    assert glyphs.text_segments("", 1.0) == []


def test_label_is_placed_in_space():
    """Подпись ставится в точку и лежит в заданной плоскости."""
    segs = glyphs.label_3d("12", (100.0, 200.0, -50.0), 10.0,
                           plane="xz")
    assert segs
    for a, b in segs:
        assert abs(a[1] - 200.0) < 1e-9 and abs(b[1] - 200.0) < 1e-9
    segs2 = glyphs.label_3d("12", (100.0, 200.0, -50.0), 10.0,
                            plane="xy")
    for a, b in segs2:
        assert abs(a[2] + 50.0) < 1e-9


def test_size_fits_the_axis():
    """Размер знака считается по своей оси, а не по общему охвату.

    У площадки двенадцать километров и отметок двести метров общий
    охват задаёт знак в двести метров: по вертикали такая подпись
    больше всего диапазона и накрывает короб целиком.
    """
    lo, hi = (24000.0, 22000.0, -200.0), (36000.0, 30000.0, 0.0)
    for axis in (0, 1, 2):
        size = glyphs.label_size(lo, hi, axis)
        span = hi[axis] - lo[axis]
        assert size <= span * 0.25, (axis, size, span)
        assert size > 0


def test_size_is_not_vanishing():
    """У короткой оси знак не сходит в точку: его должно быть видно."""
    lo, hi = (0.0, 0.0, -1.0), (10000.0, 10000.0, 0.0)
    size = glyphs.label_size(lo, hi, 2)
    assert size >= (hi[2] - lo[2]) * 0.05, size


def test_size_is_same_for_plan_axes():
    """По плану знак один и тот же: разнобой читается хуже."""
    lo, hi = (0.0, 0.0, -200.0), (12000.0, 4000.0, 0.0)
    assert abs(glyphs.label_size(lo, hi, 0)
               - glyphs.label_size(lo, hi, 1)) < 1e-9


def test_ribbon_makes_triangles():
    """Штрих превращается в полоску из двух треугольников.

    У линий в glTF нет толщины: её задаёт просмотрщик, и обычно это
    один пиксель. Полоска даёт настоящую толщину, в метрах.
    """
    segs = [((0.0, 0.0, 0.0), (10.0, 0.0, 0.0))]
    v, f = glyphs.ribbon(segs, width=1.0, plane="xz")
    assert len(v) == 4 and len(f) == 2
    assert f.max() < len(v)


def test_ribbon_width_is_real():
    """Толщина полоски равна заданной."""
    segs = [((0.0, 0.0, 0.0), (10.0, 0.0, 0.0))]
    v, _f = glyphs.ribbon(segs, width=2.0, plane="xz")
    assert abs((v[:, 2].max() - v[:, 2].min()) - 2.0) < 1e-9, v


def test_ribbon_thickens_across_the_stroke():
    """Полоска шире поперёк штриха, а не вдоль него."""
    segs = [((0.0, 0.0, 0.0), (0.0, 0.0, 10.0))]
    v, _f = glyphs.ribbon(segs, width=2.0, plane="xz")
    assert abs((v[:, 0].max() - v[:, 0].min()) - 2.0) < 1e-9
    assert abs((v[:, 2].max() - v[:, 2].min()) - 10.0) < 1e-9


def test_ribbon_skips_a_zero_stroke():
    """Штрих нулевой длины пропускается, а не делит на ноль."""
    v, f = glyphs.ribbon([((1.0, 1.0, 1.0), (1.0, 1.0, 1.0))],
                         width=1.0)
    assert len(f) == 0


def test_ribbon_indexes_are_per_segment():
    """У каждого штриха свои вершины: соседние не слипаются."""
    segs = [((0.0, 0.0, 0.0), (5.0, 0.0, 0.0)),
            ((5.0, 0.0, 0.0), (5.0, 0.0, 5.0))]
    v, f = glyphs.ribbon(segs, width=1.0, plane="xz")
    assert len(v) == 8 and len(f) == 4


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all glyph tests passed")


if __name__ == "__main__":
    _run()
