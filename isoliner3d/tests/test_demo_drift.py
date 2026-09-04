# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Демонстрационная выработка: проверяем, что в наборе лежит то,
ради чего он собран. Без этих проверок демонстрация тихо перестанет
показывать нужные случаи, а заметят это на уроке.

Запуск: python -m pytest isoliner3d/tests/test_demo_drift.py -q
"""
import os
import sys

import numpy as np

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import demo_drift as dd     # noqa: E402
from isoliner3d import section3d            # noqa: E402


def _rings(model, walls):
    out = []
    for w in walls:
        for bed in dd.BEDS:
            r = dd.wall_ring(model, bed, w)
            if r is not None:
                out.append((bed, r))
    return out


def test_contact_of_kr2_and_ab_is_one_line():
    """Подошва КрII и кровля АБ - одна и та же поверхность.

    Ради этого случая набор и собран: склейка контактов должна их
    узнать. Если формулы разойдутся, демонстрация начнёт показывать
    щель между пластами.
    """
    m = dd.make_model()
    x = np.linspace(10.0, 190.0, 25)
    y = np.full_like(x, 2.0)
    floor_kr = dd.floor_of(m, "КрII", x, y)
    roof_ab = dd.roof_of(m, "АБ", x, y)
    assert np.allclose(floor_kr, roof_ab, atol=1e-9)


def test_parting_separates_ab_and_v():
    """Между АБ и В лежит пропласток, и контакта там нет."""
    m = dd.make_model()
    x = np.linspace(10.0, 100.0, 20)
    y = np.full_like(x, 2.0)
    gap = dd.floor_of(m, "АБ", x, y) - dd.roof_of(m, "В", x, y)
    assert gap.min() > 0.25, gap.min()


def test_bed_v_pinches_out_before_the_far_crosscut():
    """Пласт В на дальнюю сбойку не выходит вовсе.

    На нём и проверяется обрезка по своим разрезам: без неё
    интерполяция растянет В на всю площадь участка.
    """
    m = dd.make_model()
    walls = dd.walls(m, crosscuts=2)
    absent = [w[0] for w in walls if dd.wall_ring(m, "В", w) is None]
    assert len(absent) == 2, absent
    assert all("сбойка 2" in nm for nm in absent), absent
    # на бортах штрека он есть
    assert dd.wall_ring(m, "В", walls[0]) is not None


def test_lens_stays_inside_the_bed():
    """Линза целиком внутри АБ: она не должна трогать границу тела."""
    m = dd.make_model()
    w = dd.walls(m)[0]
    ring = dd.lens_ring(m, "АБ", w)
    assert ring is not None
    x, y, z = ring[:, 0], ring[:, 1], ring[:, 2]
    assert (z < dd.roof_of(m, "АБ", x, y) - 1e-6).all()
    assert (z > dd.floor_of(m, "АБ", x, y) + 1e-6).all()


def test_walls_of_the_drift_and_crosscuts_cross():
    """Сбойки пересекают штрек: есть места, где отметки обязаны сойтись."""
    m = dd.make_model()
    walls = dd.walls(m, crosscuts=2)
    assert len(walls) == 6
    top, _bot, whose = section3d.roof_and_floor(
        [r for b, r in _rings(m, walls) if b == "КрII"], with_ring=True)
    snap = max(section3d.sample_step(top), 1.0)
    places, worst, where = section3d.crossing_spread(
        top, top[:, 2], snap=snap, owner=whose)
    assert places > 0, "пересечений не нашлось"
    assert worst < 0.1, worst
    assert where is not None


def test_grades_are_tied_in_reverse():
    """KCl и нерастворимый остаток связаны обратно."""
    m = dd.make_model()
    x = np.linspace(10.0, 190.0, 40)
    y = np.full_like(x, 2.0)
    z = dd.roof_of(m, "КрII", x, y) - 0.5
    kcl, no = dd.grades_at(m, "КрII", x, y, z)
    assert np.corrcoef(kcl, no)[0, 1] < -0.9


def test_grade_changes_across_the_thickness():
    """По мощности содержание меняется: делить борозду не зря."""
    m = dd.make_model()
    x = np.full(9, 80.0)
    y = np.full(9, 2.0)
    top = dd.roof_of(m, "АБ", x, y)
    th = dd.thickness_of(m, "АБ", x, y)
    z = top - np.linspace(0.05, 0.95, 9) * th
    kcl, _no = dd.grades_at(m, "АБ", x, y, z)
    assert kcl.max() - kcl.min() > 3.0, (kcl.min(), kcl.max())


def test_noise_keeps_grades_positive():
    """Шум логнормальный: отрицательных содержаний он не даёт."""
    rng = np.random.default_rng(7)
    v = dd.noisy(rng, np.full(2000, 5.0), 0.5)
    assert v.min() > 0.0
    assert abs(float(np.median(v)) - 5.0) < 0.5


def test_samples_carry_truth_and_noise_apart():
    """У проб есть и замер с шумом, и истина без него."""
    m = dd.make_model()
    rng = np.random.default_rng(3)
    h = dd.fan_holes(m, rng, stations=3, per_fan=3, noise=0.1)
    assert len(h["x"]) > 50
    assert not np.allclose(h["kcl"], h["kcl_t"])
    # шум в десять процентов оставляет связь с истиной, но не тождество
    assert np.corrcoef(h["kcl"], h["kcl_t"])[0, 1] > 0.8
    assert set(h["bed"]) <= set(dd.BEDS)


def test_grooves_cover_the_whole_thickness():
    """Борозда бьётся от кровли до подошвы, без пропусков."""
    m = dd.make_model()
    rng = np.random.default_rng(3)
    g = dd.grooves(m, rng, stations=2, sample=0.25)
    ids = sorted(set(g["groove"].tolist()))
    assert ids
    for gid in ids[:5]:
        sel = g["groove"] == gid
        assert abs(float(g["from_m"][sel].min())) < 1e-9
        assert abs(float(g["to_m"][sel].max())
                   - float(g["thick"][sel][0])) < 1e-6


def test_true_volume_matches_mean_thickness():
    """Истинный объём считается прямым суммированием и им проверяется."""
    m = dd.make_model()
    vol = dd.true_volume(m, "КрII", 0.0, 200.0, -10.0, 14.0, step=0.5)
    x = np.linspace(0.25, 199.75, 400)
    y = np.linspace(-9.75, 13.75, 48)
    gx, gy = np.meshgrid(x, y)
    want = float(dd.thickness_of(m, "КрII", gx, gy).mean()) * 200.0 * 24.0
    assert abs(vol - want) / want < 0.01, (vol, want)


def test_demo_prints_the_walkthrough():
    """Порядок показа лежит в самом инструменте, а не в отдельном файле.

    Отдельный файл с уроком расходится с кодом на первой же правке
    и теряется у того, кому его переслали. Журнал прогона - там же,
    где числа, и всегда той версии, что запущена.
    """
    import os
    pkg = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(pkg, "algorithms.py"),
               encoding="utf-8").read()
    i = src.index("class DemoDriftAlgorithm")
    seg = src[i:src.index("\nclass ", i + 10)]
    assert "Порядок показа" in seg
    for mark in ("2.08", "1.02", "2.05", "kcl_truth",
                 "Только этот пласт"):
        assert mark in seg, mark


if __name__ == "__main__":
    for nm, fn in sorted(globals().items()):
        if nm.startswith("test_") and callable(fn):
            fn()
            print("OK", nm)
    print("all demo_drift tests passed")
