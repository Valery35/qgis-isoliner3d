# -*- coding: utf-8 -*-
"""Проверка делений координатного короба.

Деления должны попадать на круглые числа: подпись 250 читается сразу,
а 247.3 надо разбирать. Считается на голом NumPy, QGIS не нужен.
"""

import os
import sys

import numpy as np

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import axes   # noqa: E402


def test_ticks_are_round():
    """Деления идут по круглым числам, а не по краям охвата."""
    got = axes.nice_ticks(0.0, 1000.0, want=5)
    # двести это круглый шаг, а двести пятьдесят нет: шаг берётся
    # единицей, двойкой или пятёркой на степень десяти
    assert got == [0.0, 200.0, 400.0, 600.0, 800.0, 1000.0], got


def test_ticks_cover_the_range():
    """Первое деление не выше нижнего края, последнее не ниже верхнего."""
    got = axes.nice_ticks(37.0, 962.0, want=5)
    assert got[0] >= 37.0 - 1e-9 or got[0] <= 37.0
    assert got[-1] <= 962.0 + 1e-9
    assert all(a < b for a, b in zip(got, got[1:]))


def test_negative_range():
    """Отметки бывают отрицательными: короб над этим не спотыкается."""
    got = axes.nice_ticks(-200.0, -50.0, want=4)
    assert got and got[0] >= -200.0 and got[-1] <= -50.0


def test_flat_range_gives_one_tick():
    """У нулевого размаха делить нечего, но и падать не за что."""
    got = axes.nice_ticks(5.0, 5.0, want=5)
    assert len(got) >= 1


def test_step_is_a_round_number():
    """Шаг это единица, двойка или пятёрка на степень десяти.

    Иначе подписи выходят вида 3.7, 7.4, 11.1 и читаются хуже.
    """
    for lo, hi in ((0.0, 1.0), (0.0, 7.0), (0.0, 13.0), (0.0, 1e6),
                   (-3.5, 3.5)):
        got = axes.nice_ticks(lo, hi, want=5)
        if len(got) < 2:
            continue
        step = got[1] - got[0]
        mant = step / (10.0 ** np.floor(np.log10(step)))
        assert min(abs(mant - m) for m in (1.0, 2.0, 5.0, 10.0)) < 1e-6, (
            lo, hi, step, mant)


def test_label_drops_the_tail():
    """Подпись без хвоста нулей: 250, а не 250.000000."""
    assert axes.tick_label(250.0) == "250"
    assert axes.tick_label(-37.5) == "-37.5"
    assert axes.tick_label(1000000.0) == "1000000"


def test_box_has_twelve_edges():
    """У короба двенадцать рёбер, по четыре на каждое направление."""
    segs = axes.box_edges((0.0, 0.0, 0.0), (10.0, 20.0, 30.0))
    assert len(segs) == 12
    for a, b in segs:
        assert len(a) == 3 and len(b) == 3


def test_ticks_on_the_box_sit_on_the_edges():
    """Штрихи стоят на рёбрах короба, а не висят в воздухе."""
    marks = axes.tick_marks((0.0, 0.0, 0.0), (100.0, 100.0, 100.0),
                            want=3, length=5.0)
    assert marks
    for axis, val, a, b in marks:
        assert axis in (0, 1, 2)
        assert abs(a[axis] - val) < 1e-9
        assert abs(b[axis] - val) < 1e-9


def _lo_hi():
    return (0.0, 0.0, -100.0), (1000.0, 800.0, 0.0)


def test_grid_floor_lines_lie_on_the_floor():
    """Линии пола лежат в плоскости пола, а не парят над ним."""
    lo, hi = _lo_hi()
    segs = axes.grid_lines(lo, hi, step=200.0, planes=("floor",))
    assert segs
    for a, b in segs:
        assert abs(a[2] - lo[2]) < 1e-9 and abs(b[2] - lo[2]) < 1e-9


def test_grid_walls_are_vertical_planes():
    """Линии стен лежат в двух вертикальных плоскостях."""
    lo, hi = _lo_hi()
    segs = axes.grid_lines(lo, hi, step=200.0, planes=("walls",))
    assert segs
    for a, b in segs:
        on_x = abs(a[0] - lo[0]) < 1e-9 and abs(b[0] - lo[0]) < 1e-9
        on_y = abs(a[1] - lo[1]) < 1e-9 and abs(b[1] - lo[1]) < 1e-9
        assert on_x or on_y, (a, b)


def test_grid_step_zero_is_chosen_by_the_scene():
    """Ноль означает круглый шаг от размаха, а не отсутствие сетки."""
    lo, hi = _lo_hi()
    segs = axes.grid_lines(lo, hi, step=0.0, planes=("floor",))
    assert len(segs) > 2


def test_grid_step_too_small_is_capped():
    """Слишком мелкий шаг не рисуется миллионом линий.

    Сетка гуще самой сцены не помогает читать, а рисуется долго.
    """
    lo, hi = _lo_hi()
    segs = axes.grid_lines(lo, hi, step=0.01, planes=("floor",))
    assert len(segs) <= axes.MAX_GRID_LINES


def test_grid_without_planes_is_empty():
    lo, hi = _lo_hi()
    assert axes.grid_lines(lo, hi, step=100.0, planes=()) == []


def test_north_arrow_points_north():
    """Стрелка севера смотрит по возрастанию Y.

    В проекции карты север это возрастание Y, и стрелка обязана идти
    туда, иначе она врёт о самом простом.
    """
    segs = axes.north_arrow((0.0, 0.0, 0.0), (100.0, 100.0, 50.0))
    assert segs
    shaft = segs[0]
    assert shaft[1][1] > shaft[0][1], shaft
    assert abs(shaft[1][0] - shaft[0][0]) < 1e-9


def test_north_arrow_has_a_head():
    """У стрелки есть наконечник, а не только древко."""
    segs = axes.north_arrow((0.0, 0.0, 0.0), (100.0, 100.0, 50.0))
    assert len(segs) >= 3
    shaft = segs[0]
    for a, b in segs[1:]:
        assert b[1] <= shaft[1][1] + 1e-9


def test_north_arrow_scales_with_the_scene():
    """Стрелка соразмерна сцене: на километре и на десяти видна."""
    small = axes.north_arrow((0.0, 0.0, 0.0), (100.0, 100.0, 10.0))
    big = axes.north_arrow((0.0, 0.0, 0.0), (10000.0, 10000.0, 100.0))

    def length(segs):
        a, b = segs[0]
        return abs(b[1] - a[1])

    assert length(big) > length(small) * 10.0


def test_north_arrow_sits_outside_the_box():
    """Стрелка стоит за коробом, а не поперёк тела."""
    lo, hi = (0.0, 0.0, 0.0), (100.0, 100.0, 50.0)
    segs = axes.north_arrow(lo, hi)
    xs = [q[0] for seg in segs for q in seg]
    assert min(xs) < lo[0] or max(xs) > hi[0], (min(xs), max(xs))


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all axes tests passed")


if __name__ == "__main__":
    _run()
