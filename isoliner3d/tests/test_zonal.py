# -*- coding: utf-8 -*-
"""Статистика атрибута внутри тела для 2.14 (zonal.py).

Просьба Василия: кроме суммы среднее, разброс и квантили. Сумма годится
для металла блоков, для содержания нужно среднее, а у интервалов
опробования оно взвешено по длине внутри тела.
"""

import os
import sys

import numpy as np

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import zonal                    # noqa: E402

ALL = zonal.KEYS


def test_equal_weights_match_numpy():
    v = [3.0, 1.0, 4.0, 1.0, 5.0, 9.0, 2.0, 6.0]
    got = zonal.stats(v, [1.0] * len(v), ALL)
    assert np.isclose(got["_sum"], sum(v))
    assert np.isclose(got["_mean"], np.mean(v))
    assert got["_min"] == 1.0 and got["_max"] == 9.0
    assert np.isclose(got["_std"], np.std(v))
    assert np.isclose(got["_med"], np.median(v))
    # квантиль по Хазену при равных весах
    assert np.isclose(got["_p25"], np.percentile(v, 25,
                                                 method="hazen"))
    assert np.isclose(got["_p90"], np.percentile(v, 90,
                                                 method="hazen"))


def test_length_weights_pull_the_mean():
    # два интервала: 1 г/т на 9 м внутри тела и 10 г/т на 1 м
    got = zonal.stats([1.0, 10.0], [9.0, 1.0], ("mean", "sum", "med"))
    assert np.isclose(got["_mean"], 1.9)
    assert np.isclose(got["_sum"], 11.0)        # сумма без весов
    assert got["_med"] < 2.0


def test_empty_values_are_skipped_not_zero():
    got = zonal.stats([None, 4.0, float("nan"), 6.0], [1, 1, 1, 1], ALL)
    assert np.isclose(got["_mean"], 5.0)
    assert got["_min"] == 4.0
    assert np.isclose(got["_sum"], 10.0)


def test_body_without_values():
    got = zonal.stats([], [], ALL)
    assert got["_sum"] == 0.0
    assert all(got[k] is None for k in got if k != "_sum")
    got = zonal.stats([None], [1.0], ("mean",))
    assert got["_mean"] is None


def test_suffix_order_and_labels():
    assert zonal.suffixes(("sum",)) == ["_sum"]
    assert zonal.suffixes(("decile", "mean", "quart")) == [
        "_mean", "_p25", "_p75", "_p10", "_p90"]
    from isoliner3d import fields
    for suf in zonal.suffixes(ALL):
        lab = fields.label_for("au" + suf)
        assert lab and (lab % "au").startswith("au: ")
