# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""1.09 Отчёт по горизонтам: ядро benches.py и инструмент bench_report.

Запуск:  python isoliner3d/tests/test_benches.py
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from isoliner3d import benches  # noqa: E402
from isoliner3d.toolspec import Report, ToolError  # noqa: E402
from isoliner3d.tools import by_name  # noqa: E402


def test_bench_edges_cover_the_range_top_down():
    e = benches.bench_edges([93.0], [127.0], 10.0)
    assert e == [(130.0, 120.0), (120.0, 110.0), (110.0, 100.0),
                 (100.0, 90.0)]
    e = benches.bench_edges([95.0], [105.0], 10.0, base=5.0)
    assert e == [(105.0, 95.0)]


def test_tall_block_is_split_between_benches():
    # блок 10 м на уступах по 5 м: половина в каждый
    rows, tot = benches.report([100.0], [110.0], [1000.0], [2.0], [2.5],
                               5.0)
    assert len(rows) == 2
    assert all(abs(r["vol"] - 500.0) < 1e-9 for r in rows)
    assert abs(tot["ton"] - 2500.0) < 1e-9
    # блок без высоты целиком в уступ центра
    rows, _t = benches.report([107.0], [107.0], [1000.0], [2.0], [2.5], 5.0)
    assert len(rows) == 1 and rows[0]["z_top"] == 110.0


def test_ore_waste_metal_and_money():
    # два блока по 100 т: 2 % - руда, 0.5 % - вскрыша при борту 1 %
    rows, tot = benches.report([0.0, 0.0], [10.0, 10.0], [40.0, 40.0],
                               [2.0, 0.5], 2.5, 10.0, cutoff=1.0,
                               unit=0.01, price=1000.0, recovery=0.9,
                               mine_cost=2.0, proc_cost=10.0)
    r = rows[0]
    assert r["ton"] == 200.0 and r["ore_t"] == 100.0 and r["waste_t"] == 100.0
    assert abs(r["metal"] - 2.0) < 1e-12 and abs(r["grade"] - 2.0) < 1e-12
    assert r["strip"] == 1.0
    assert abs(r["revenue"] - 2.0 * 0.9 * 1000.0) < 1e-9
    assert abs(r["cost"] - (200.0 * 2.0 + 100.0 * 10.0)) < 1e-9
    assert abs(r["margin"] - (r["revenue"] - r["cost"])) < 1e-9
    assert tot["metal"] == r["metal"]


def test_grams_per_tonne_give_grams():
    rows, _t = benches.report([0.0], [10.0], [40.0], [3.0], 2.5, 10.0,
                              unit=1.0)
    assert abs(rows[0]["metal"] - 300.0) < 1e-9     # 100 т * 3 г/т
    assert abs(rows[0]["grade"] - 3.0) < 1e-12


def test_block_without_grade_is_waste():
    rows, _t = benches.report([0.0, 0.0], [10.0, 10.0], [40.0, 40.0],
                              [np.nan, 2.0], 2.5, 10.0)
    assert rows[0]["ore_t"] == 100.0 and rows[0]["waste_t"] == 100.0


def _blocks(rows):
    return [{"id": i, "xyz": np.array([0.0, 0.0, z]), "attrs": a}
            for i, (z, a) in enumerate(rows)]


def _run(blocks, fields, **kw):
    spec = by_name("bench_report")
    v = spec.defaults()
    v.update({"BLOCKS": blocks, "@BLOCKS": {"fields": fields}})
    v.update(kw)
    return spec.run(v, Report())


def test_tool_reads_1_03_fields_and_ends_with_a_total():
    blocks = _blocks([(105.0, {"z_from": 110.0, "z_to": 100.0, "vol": 400.0,
                               "dens": 2.5, "g": 2.0}),
                      (95.0, {"z_from": 100.0, "z_to": 90.0, "vol": 400.0,
                              "dens": 2.5, "g": 0.2})])
    out = _run(blocks, ["z_from", "z_to", "vol", "dens", "g"], GRADE="g",
               HEIGHT=10.0, CUTOFF=1.0)["OUTPUT"]
    assert out.geometry == "none"
    feats = out.features
    assert len(feats) == 3 and feats[-1][1][0] == "Итого"
    names = [n for n, _t in out.fields]
    ton = names.index("ton")
    ore = names.index("ore_t")
    assert feats[0][1][ton] == 1000.0 and feats[0][1][ore] == 1000.0
    assert feats[1][1][ore] == 0.0
    assert feats[-1][1][ton] == 2000.0


def test_tool_uses_dz_around_the_point_and_constant_density():
    blocks = _blocks([(105.0, {"vol": 400.0, "dz": 10.0, "g": 2.0})])
    out = _run(blocks, ["vol", "dz", "g"], GRADE="g", HEIGHT=5.0,
               DENSITY=2.0)["OUTPUT"]
    assert len(out.features) == 3      # два уступа и итог
    names = [n for n, _t in out.fields]
    assert out.features[0][1][names.index("ton")] == 400.0


def test_tool_refuses_without_grade_or_volume():
    blocks = _blocks([(105.0, {"g": 2.0})])
    for kw in ({}, {"GRADE": "g"}):
        try:
            _run(blocks, ["g"], **kw)
        except ToolError:
            continue
        raise AssertionError("без содержания или объёма - отказ")


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK", name)
            n += 1
    print("all bench tests passed (%d)" % n)
