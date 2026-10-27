# -*- coding: utf-8 -*-
"""Стволы по инклинометрии и интервалы по стволу.

Проверки на стволах с известной геометрией: отвесный, наклонный
прямой, дуга четверти окружности. Минимальная кривизна на дуге
окружности точна, поэтому дуга обязана лечь на окружность, а не
около неё.

Считается на голом NumPy, QGIS не нужен.
"""

import os
import sys

import numpy as np

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import wells                   # noqa: E402


def test_vertical_hole_without_survey():
    p, m = wells.desurvey((10.0, 20.0, 300.0), [], [], [], max_depth=120)
    assert np.allclose(p[-1], (10.0, 20.0, 180.0))
    assert abs(m[-1] - 120.0) < 1e-9


def test_straight_inclined_hole():
    """Угол -60 на восток, 100 м по стволу: 50 м в сторону, 86.6 вниз."""
    p, _m = wells.desurvey((0.0, 0.0, 0.0), [0.0], [90.0], [-60.0],
                           max_depth=100.0)
    assert np.allclose(p[-1], (50.0, 0.0, -100.0 * np.sin(np.radians(60))),
                       atol=1e-9)


def test_conventions_agree():
    a = wells.desurvey((0, 0, 0), [0, 50], [30, 40], [-70, -60], 100)[0]
    b = wells.desurvey((0, 0, 0), [0, 50], [30, 40], [70, 60], 100,
                       convention="dip_down_pos")[0]
    c = wells.desurvey((0, 0, 0), [0, 50], [30, 40], [20, 30], 100,
                       convention="zenith")[0]
    assert np.allclose(a, b) and np.allclose(a, c)


def test_quarter_arc_lies_on_the_circle():
    """От отвеса до горизонтали на длине четверти окружности R = 100.

    Забой ровно в (100, 0, -100), каждый узел ствола на расстоянии R
    от центра (100, 0, 0).
    """
    L = 0.5 * np.pi * 100.0
    p, m = wells.desurvey((0.0, 0.0, 0.0), [0.0, L], [90.0, 90.0],
                          [-90.0, 0.0], step=2.0)
    assert np.allclose(p[-1], (100.0, 0.0, -100.0), atol=1e-6)
    r = np.linalg.norm(p - np.array([100.0, 0.0, 0.0]), axis=1)
    assert np.allclose(r, 100.0, atol=1e-6), (r.min(), r.max())
    assert abs(m[-1] - L) < 1e-9


def test_point_at_depth_on_the_arc():
    """Середина дуги: угол 45 градусов на окружности."""
    L = 0.5 * np.pi * 100.0
    p, m = wells.desurvey((0.0, 0.0, 0.0), [0.0, L], [90.0, 90.0],
                          [-90.0, 0.0], step=0.5)
    q = wells.at_depth(p, m, [L / 2])[0]
    want = (100.0 - 100.0 * np.cos(np.radians(45)), 0.0,
            -100.0 * np.sin(np.radians(45)))
    assert np.allclose(q, want, atol=0.01), (q, want)


def test_extends_straight_past_the_last_survey():
    p, _m = wells.desurvey((0, 0, 0), [0.0, 50.0], [0.0, 0.0],
                           [-90.0, -45.0], max_depth=150.0)
    seg = p[-1] - wells.at_depth(p, _m, [50.0])[0]
    d = seg / np.linalg.norm(seg)
    assert np.allclose(d, wells.tangent(45.0, 0.0), atol=1e-9)


def test_short_hole_is_the_start_of_the_long_one():
    """Забой между замерами: короткий ствол совпадает с началом
    длинного, а не уходит по касательной последнего взятого замера."""
    sv = ([0.0, 40.0, 90.0], [10.0, 40.0, 80.0], [-85.0, -60.0, -40.0])
    pl, ml = wells.desurvey((0, 0, 0), *sv, max_depth=120.0, step=0.5)
    ps, _ms = wells.desurvey((0, 0, 0), *sv, max_depth=60.0, step=0.5)
    assert np.allclose(ps[-1], wells.at_depth(pl, ml, [60.0])[0],
                       atol=1e-3)


def test_survey_is_sorted_and_deduplicated():
    d, inc, a = wells.clean_survey([50, 0, 50, np.nan], [10, 0, 20, 5],
                                   [-80, -90, -70, -60])
    assert list(d) == [0, 50]
    assert list(a) == [0, 20]          # повтор - последний замер
    assert np.allclose(inc, [0, 20])


def test_segment_ends_where_asked():
    p, m = wells.desurvey((0, 0, 0), [0], [0], [-90], 100)
    s = wells.segment(p, m, 12.5, 37.5)
    assert np.allclose(s[0], (0, 0, -12.5)) and np.allclose(s[-1],
                                                           (0, 0, -37.5))


def test_equal_intervals_keep_the_short_tail():
    iv = wells.equal_intervals(10.5, 2.0)
    assert iv.shape == (6, 2)
    assert np.allclose(iv[-1], (10.0, 10.5))
    assert np.allclose(wells.equal_intervals(10.0, 2.0)[-1], (8.0, 10.0))


def test_composite_is_length_weighted():
    """Проба 0-1 по 10 г/т и 1-4 по 2 г/т в композит 0-4: 4 г/т.

    Простое среднее дало бы 6 - это и есть ошибка, ради которой
    композитируют по длине.
    """
    iv, v, cov = wells.composite([0.0, 1.0], [1.0, 4.0], [10.0, 2.0], 4.0)
    assert iv.shape == (1, 2)
    assert abs(v[0, 0] - 4.0) < 1e-12
    assert cov[0] == 1.0


def test_composite_marks_gaps_not_zeros():
    iv, v, cov = wells.composite([0.0, 6.0], [2.0, 8.0], [1.0, 3.0], 2.0)
    assert np.isnan(v[1, 0]) and cov[1] == 0.0
    assert abs(v[3, 0] - 3.0) < 1e-12
    iv, v, cov = wells.composite([0.0], [1.0], [5.0], 2.0, end=2.0)
    assert abs(cov[0] - 0.5) < 1e-12 and v[0, 0] == 5.0


def test_demo_assays_end_at_the_collar_depth():
    """Демо: пробы не глубже забоя из устья, и жилу встречает каждая."""
    d = wells.demo(seed=1)
    eoh = {c[0]: c[4] for c in d["collars"]}
    assert all(a[2] <= eoh[a[0]] + 1e-9 for a in d["assays"])
    rich = {a[0] for a in d["assays"] if a[3] >= 1.0}
    assert len(rich) >= 0.8 * len(eoh)

def test_collar_direction_starts_the_hole():
    """Наклон из паспорта: ствол идёт под ним от устья до замера.

    Устье -60 на восток, первый замер на 50 м такой же: ствол прямой,
    а без паспорта он шёл бы до 50 м по замеру и совпал бы. Замер на
    50 м круче - до него дуга от паспортного направления.
    """
    d, a, g = wells.with_collar([50.0], [90.0], [-60.0], 90.0, -60.0)
    assert d == [0.0, 50.0]
    p, _m = wells.desurvey((0, 0, 0), d, a, g, max_depth=100.0)
    assert np.allclose(p[-1], (50.0, 0.0, -100.0 * np.sin(np.radians(60))),
                       atol=1e-9)
    # свой замер на устье важнее паспорта
    assert wells.with_collar([0.0, 50.0], [10.0, 10.0], [-80.0, -80.0],
                             90.0, -60.0)[1] == [10.0, 10.0]
    # пустой паспорт ничего не меняет
    assert wells.with_collar([5.0], [1.0], [-89.0], None, -60.0)[0] == [5.0]


def test_upward_hole_from_underground():
    """Скважина вверх из выработки: угол +45 от горизонта."""
    d, a, g = wells.with_collar([], [], [], 0.0, 45.0)
    p, _m = wells.desurvey((0, 0, -300.0), d, a, g, max_depth=100.0)
    assert np.allclose(p[-1], (0.0, 100 / np.sqrt(2), -300 + 100 / np.sqrt(2)),
                       atol=1e-9)

def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all wells tests passed")


if __name__ == "__main__":
    _run()
