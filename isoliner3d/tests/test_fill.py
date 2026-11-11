# -*- coding: utf-8 -*-
"""Заполнение тела до объёма (fill.py, 2.23)."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from isoliner3d import boolean3d, fill  # noqa: E402


def _box(x0, y0, z0, dx, dy, dz):
    v = np.array([[x0, y0, z0], [x0 + dx, y0, z0], [x0 + dx, y0 + dy, z0],
                  [x0, y0 + dy, z0], [x0, y0, z0 + dz],
                  [x0 + dx, y0, z0 + dz], [x0 + dx, y0 + dy, z0 + dz],
                  [x0, y0 + dy, z0 + dz]], dtype=float)
    f = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
                  [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
                  [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]])
    return v, f


def _cuts(v, f, cell=0.0, max_cols=4000):
    b = (v[:, 0].min(), v[:, 0].max(), v[:, 1].min(), v[:, 1].max())
    gt, ny, nx, step = fill.plan_grid(b, cell, max_cols)
    col, zc = boolean3d.column_cuts(v, f, gt, (ny, nx))
    cols, lo, hi = fill.intervals(col, zc)
    return cols, lo, hi, step * step, gt, ny, nx


def test_box_volume_by_columns_is_exact():
    v, f = _box(100, 200, -50, 10, 20, 5)
    _c, lo, hi, area, *_r = _cuts(v, f, cell=1.0)
    assert abs(fill.total_volume(lo, hi, area) - 1000.0) < 1e-6


def test_level_from_below():
    v, f = _box(100, 200, -50, 10, 20, 5)
    _c, lo, hi, area, *_r = _cuts(v, f, cell=1.0)
    h, got = fill.level_for_volume(lo, hi, area, 300.0)
    assert abs(h - (-48.5)) < 1e-4
    assert abs(got - 300.0) < 1e-2


def test_level_from_the_top():
    v, f = _box(100, 200, -50, 10, 20, 5)
    _c, lo, hi, area, *_r = _cuts(v, f, cell=1.0)
    h, got = fill.level_for_volume(lo, hi, area, 300.0, from_top=True)
    assert abs(h - (-46.5)) < 1e-4
    assert abs(got - 300.0) < 1e-2


def test_more_than_the_body_gives_the_whole_body():
    v, f = _box(0, 0, 0, 2, 2, 2)
    _c, lo, hi, area, *_r = _cuts(v, f, cell=0.5)
    h, got = fill.level_for_volume(lo, hi, area, 1e9)
    assert abs(h - 2.0) < 1e-4 and abs(got - 8.0) < 1e-6
    h, got = fill.level_for_volume(lo, hi, area, 0.0)
    assert abs(h - 0.0) < 1e-4 and got < 1e-6


def test_two_stacked_bodies_fill_the_lower_first():
    va, fa = _box(0, 0, 0, 2, 2, 1)
    vb, fb = _box(0, 0, 3, 2, 2, 1)
    v = np.vstack([va, vb])
    f = np.vstack([fa, fb + len(va)])
    _c, lo, hi, area, *_r = _cuts(v, f, cell=0.5)
    assert abs(fill.total_volume(lo, hi, area) - 8.0) < 1e-6
    h, _g = fill.level_for_volume(lo, hi, area, 4.0)
    # нижнее тело заполнено целиком, пустота между телами не в счёт
    assert 1.0 - 1e-4 <= h <= 3.0 + 1e-4
    h, _g = fill.level_for_volume(lo, hi, area, 6.0)
    assert abs(h - 3.5) < 1e-4


def test_filled_cube_has_a_flat_lid_on_the_level():
    v, f = _box(0, 0, 0, 4, 4, 4)
    cols, lo, hi, area, gt, ny, nx = _cuts(v, f, cell=1.0)
    h, _g = fill.level_for_volume(lo, hi, area, 24.0)
    assert abs(h - 1.5) < 1e-4
    occ, z0, dz = fill.filled_occupancy(cols, lo, hi, gt, ny, nx, h, 0.25)
    top_edge = z0 + (occ.shape[0] - 0.5) * dz
    assert abs(top_edge - h) < 1e-9
    assert abs(occ.sum() * area * dz - 24.0) < 1e-6


def test_plan_grid_respects_the_column_budget():
    gt, ny, nx, step = fill.plan_grid((0, 1000, 0, 1000), 0.1, 10000)
    assert ny * nx <= 10404
    assert abs(step - 10.0) < 1e-9
    gt, ny, nx, step = fill.plan_grid((0, 10, 0, 10), 2.0, 10000)
    assert step == 2.0 and nx == 5 and ny == 5


def test_empty_body_is_refused():
    import pytest
    with pytest.raises(ValueError):
        fill.level_for_volume([], [], 1.0, 5.0)
