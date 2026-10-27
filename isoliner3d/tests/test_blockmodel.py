# -*- coding: utf-8 -*-
"""Блочная модель в куб и узнавание полей по имени.

Считается на голом NumPy, QGIS не нужен.
"""

import os
import sys

import numpy as np

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import blockmodel as bm        # noqa: E402
from isoliner3d import colnames                # noqa: E402


def _cube_blocks(vol, x0=1000.0, y1=5000.0, z0=100.0, c=(10.0, 10.0, 5.0)):
    """Блоки по ячейкам куба, как их отдаёт 2.03: центр и значение."""
    nz, ny, nx = vol.shape
    k, i, j = np.nonzero(np.isfinite(vol))
    x = x0 + (j + 0.5) * c[0]
    y = y1 - (i + 0.5) * c[1]
    z = z0 + k * c[2]
    return x, y, z, vol[k, i, j]


def test_regular_blocks_come_back_as_the_same_cube():
    rng = np.random.default_rng(1)
    vol = rng.lognormal(0.0, 1.0, (4, 6, 7))
    vol[0, 0, :] = np.nan          # пустой ряд внутри
    x, y, z, v = _cube_blocks(vol)
    r = bm.blocks_to_cube(x, y, z, v)
    assert r["gt"][1] == 10.0 and r["dz"] == 5.0
    got = r["vol"][0]
    # охват по занятым блокам: куб совпадает с исходным
    assert got.shape == vol.shape
    assert np.allclose(got, vol, equal_nan=True)
    assert abs(r["z0"] - 100.0) < 1e-9
    assert r["n_multi"] == 0


def test_sub_blocks_average_by_volume():
    """Блок 10 м разбит на 8 подблоков по 5 м, ячейка 10 м.

    Значение ячейки - среднее подблоков, а металл (значение x объём)
    тот же, что по подблокам.
    """
    c = np.array([[sx, sy, sz] for sx in (2.5, 7.5) for sy in (2.5, 7.5)
                  for sz in (2.5, 7.5)])
    v = np.arange(1.0, 9.0)
    s = np.full(8, 5.0)
    r = bm.blocks_to_cube(c[:, 0], c[:, 1], c[:, 2], v, s, s, s,
                          cell=(10.0, 10.0, 10.0))
    assert r["vol"].shape == (1, 1, 1, 1)
    assert abs(r["vol"][0, 0, 0, 0] - v.mean()) < 1e-12
    metal = bm.cube_metal(r["vol"][0], r["cover"], r["gt"], r["dz"])
    assert abs(metal - (v * 125.0).sum()) < 1e-9


def test_mixed_parent_and_sub_blocks():
    """Родительский блок 10 м рядом с подблоками 5 м: ячейка 5 м.

    Родитель ложится на восемь ячеек своим значением, подблоки
    каждый в свою.
    """
    x = [5.0, 12.5, 17.5]
    y = [5.0, 2.5, 7.5]
    z = [5.0, 2.5, 2.5]
    s = [10.0, 5.0, 5.0]
    r = bm.blocks_to_cube(x, y, z, [3.0, 1.0, 9.0], s, s, s)
    assert r["gt"][1] == 5.0
    vol = r["vol"][0]
    assert vol.shape == (2, 2, 4)
    assert np.allclose(vol[:, :, :2], 3.0)
    assert r["n_multi"] == 1
    # подблок у Y 2.5 лежит в нижнем ряду растра
    assert vol[0, 1, 2] == 1.0 and vol[0, 0, 3] == 9.0
    assert np.isnan(vol[1, :, 2:]).all()


def test_sizes_are_inferred_from_the_centres():
    """Без полей размера шаг берётся по разносу центров, дыры пусты."""
    x = np.array([0.0, 20.0, 40.0, 0.0, 40.0])
    y = np.array([0.0, 0.0, 0.0, 20.0, 20.0])
    z = np.zeros(5)
    r = bm.blocks_to_cube(x, y, z, np.ones(5))
    assert r["gt"][1] == 20.0 and r["gt"][5] == -20.0
    vol = r["vol"][0, 0]
    assert vol.shape == (2, 3)
    assert np.isnan(vol[0, 1]) and np.isfinite(vol).sum() == 5


def test_partial_cover_stays_empty():
    """Блок задел ячейку на четверть: при пороге 0.5 она пуста."""
    r = bm.blocks_to_cube([5.0, 12.5], [5.0, 5.0], [5.0, 5.0], [1.0, 2.0],
                          [10.0, 5.0], [10.0, 10.0], [10.0, 10.0],
                          cell=(10.0, 10.0, 10.0))
    vol = r["vol"][0, 0, 0]
    assert vol[0] == 1.0 and vol[1] == 2.0     # ровно половина - берём
    r = bm.blocks_to_cube([5.0, 11.25], [5.0, 5.0], [5.0, 5.0],
                          [1.0, 2.0], [10.0, 2.5], [10.0, 10.0],
                          [10.0, 10.0], cell=(10.0, 10.0, 10.0))
    assert np.isnan(r["vol"][0, 0, 0, 1])
    assert abs(r["cover"][0, 0, 1] - 0.25) < 1e-12


def test_several_fields_and_gaps_in_values():
    x, y, z = [5.0, 15.0], [5.0, 5.0], [5.0, 5.0]
    v = np.array([[1.0, np.nan], [2.0, 7.0]])
    r = bm.blocks_to_cube(x, y, z, v)
    assert r["vol"].shape == (2, 1, 1, 2)
    assert np.isnan(r["vol"][1, 0, 0, 0]) and r["vol"][1, 0, 0, 1] == 7.0


def test_too_fine_a_cell_is_refused():
    try:
        bm.blocks_to_cube([50.0], [50.0], [50.0], [1.0], [100.0], [100.0],
                          [100.0], cell=(1.0, 1.0, 1.0))
    except ValueError:
        return
    raise AssertionError("ячейка в 1 м под блок 100 м должна отказать")


def test_micromine_and_datamine_names():
    mm = ["EAST", "NORTH", "RL", "_EAST", "_NORTH", "_RL", "AU"]
    assert colnames.guess(mm, "bx") == "EAST"
    assert colnames.guess(mm, "sx") == "_EAST"
    assert colnames.guess(mm, "sz") == "_RL"
    dm = ["XC", "YC", "ZC", "XINC", "YINC", "ZINC", "AU"]
    assert colnames.guess(dm, "by") == "YC"
    assert colnames.guess(dm, "sy") == "YINC"
    assert colnames.guess(["x", "y", "z", "Au"], "sx") is None
    col = ["HOLE", "EAST", "NORTH", "RL", "DEPTH"]
    assert colnames.guess(col, "hole") == "HOLE"
    assert colnames.guess(col, "eoh") == "DEPTH"
    sv = ["BHID", "AT", "BRG", "DIP"]
    assert colnames.guess(sv, "s_depth") == "AT"
    assert colnames.guess(sv, "s_azi") == "BRG"
    assert colnames.resolve("dip", sv, "s_angle") == "DIP"
    assert colnames.resolve("DIP", sv, "s_angle") == "DIP"


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all blockmodel tests passed")


if __name__ == "__main__":
    _run()
