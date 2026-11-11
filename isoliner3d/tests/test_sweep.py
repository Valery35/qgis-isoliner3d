# -*- coding: utf-8 -*-
"""Тело вдоль оси выработки (sweep.py, 2.24)."""
import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from isoliner3d import sweep  # noqa: E402
from isoliner3d.cleanup import shell_defects  # noqa: E402


def test_rect_drift_volume_is_exact():
    prof = sweep.profile("rect", 4.0, 3.0)
    v, f, length, turn = sweep.sweep([(0, 0, -300), (100, 0, -300)], prof)
    assert abs(length - 100.0) < 1e-9 and turn == 0.0
    assert abs(sweep.signed_volume(v, f) - 1200.0) < 1e-6
    assert shell_defects(v, f)[0] == 0


def test_floor_anchor_puts_the_axis_on_the_sole():
    prof = sweep.profile("rect", 4.0, 3.0)
    v, _f, _l, _t = sweep.sweep([(0, 0, -300), (50, 0, -300)], prof)
    assert abs(v[:, 2].min() + 300.0) < 1e-9
    assert abs(v[:, 2].max() + 297.0) < 1e-9
    v, _f, _l, _t = sweep.sweep([(0, 0, -300), (50, 0, -300)], prof,
                                anchor="centre")
    assert abs(v[:, 2].min() + 301.5) < 1e-9


def test_right_angle_bend_keeps_the_width():
    prof = sweep.profile("rect", 4.0, 3.0)
    axis = [(0, 0, 0), (50, 0, 0), (50, 50, 0)]
    v, f, length, turn = sweep.sweep(axis, prof)
    assert abs(turn - 90.0) < 1e-6
    assert shell_defects(v, f)[0] == 0
    # с косым стыком объём - площадь на длину по оси
    assert abs(sweep.signed_volume(v, f) - 12.0 * 100.0) < 1e-6


def test_circle_area_and_volume():
    prof = sweep.profile("circle", 5.0, segments=64)
    area = sweep.section_area(prof)
    assert abs(area - math.pi * 6.25) / (math.pi * 6.25) < 0.01
    v, f, length, _t = sweep.sweep([(0, 0, 0), (0, 80, 0)], prof)
    assert abs(sweep.signed_volume(v, f) - area * 80.0) < 1e-6


def test_arch_is_taller_than_its_walls():
    prof = sweep.profile("arch", 5.0, 2.5, rise=1.0, segments=20)
    assert abs(prof[:, 1].max() - 3.5) < 1e-9
    assert abs(prof[:, 0].max() - 2.5) < 1e-9
    rect = sweep.section_area(sweep.profile("rect", 5.0, 2.5))
    assert sweep.section_area(prof) > rect
    # полуциркульный свод по умолчанию: подъём - половина ширины
    semi = sweep.profile("arch", 4.0, 2.0)
    assert abs(semi[:, 1].max() - 4.0) < 1e-9


def test_inclined_drift_keeps_walls_vertical_across():
    prof = sweep.profile("rect", 4.0, 3.0)
    axis = [(0, 0, 0), (100, 0, -20)]
    _p, us, vs, _k, _a = sweep.frames(axis)
    assert abs(us[0][2]) < 1e-12        # поперёк - горизонтально
    assert vs[0][2] > 0.9               # верх сечения смотрит вверх
    v, f, _l, _t = sweep.sweep(axis, prof)
    assert sweep.signed_volume(v, f) > 0
    assert shell_defects(v, f)[0] == 0


def test_vertical_shaft():
    prof = sweep.profile("circle", 6.0, segments=24)
    v, f, length, _t = sweep.sweep([(10, 10, 0), (10, 10, -400)], prof)
    assert abs(length - 400) < 1e-9
    assert shell_defects(v, f)[0] == 0
    area = sweep.section_area(prof)
    assert abs(sweep.signed_volume(v, f) - area * 400) < 1e-6


def test_repeated_vertices_are_ignored():
    prof = sweep.profile("rect", 2.0, 2.0)
    v, f, length, _t = sweep.sweep([(0, 0, 0), (0, 0, 0), (10, 0, 0),
                                    (10, 0, 0)], prof)
    assert abs(length - 10) < 1e-9
    assert abs(sweep.signed_volume(v, f) - 40.0) < 1e-9


def test_bad_input_is_refused():
    with pytest.raises(ValueError):
        sweep.sweep([(0, 0, 0)], sweep.profile("rect", 1, 1))
    with pytest.raises(ValueError):
        sweep.profile("rect", 0, 1)
    with pytest.raises(ValueError):
        sweep.profile("oval", 1, 1)


def test_sharp_turn_is_reported():
    prof = sweep.profile("rect", 2.0, 2.0)
    _v, _f, _l, turn = sweep.sweep([(0, 0, 0), (10, 0, 0), (0, 1, 0)],
                                   prof)
    assert turn > sweep.MAX_TURN


def test_multi_vertex_curve_is_closed():
    t = np.linspace(0, math.pi, 30)
    axis = np.column_stack([100 * np.cos(t), 100 * np.sin(t),
                            -200 + 5 * t])
    v, f, _l, turn = sweep.sweep(axis, sweep.profile("arch", 4, 2.5))
    assert turn < 10
    assert shell_defects(v, f)[0] == 0
    assert sweep.signed_volume(v, f) > 0
