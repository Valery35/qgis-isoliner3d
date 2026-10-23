# -*- coding: utf-8 -*-
"""Демонстрационная речная сеть: сток по рельефу и расходы.

Считается на голом NumPy, QGIS не нужен.
"""

import os
import sys

import numpy as np

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import demo_rivers as dr       # noqa: E402

_R = {}


def _demo():
    if "r" not in _R:
        _R["r"] = dr.demo(seed=3)
    return _R["r"]


def test_filled_dem_has_no_pits():
    """После заполнения у каждой ячейки внутри есть сток ниже неё."""
    z = dr.fill_pits(dr.make_dem(60, 50, seed=5))
    d = dr.flow_dirs(z, 50.0)
    inner = d[1:-1, 1:-1]
    assert (inner >= 0).all()


def test_water_runs_downhill():
    """По звену отметка не растёт: вода не течёт в гору."""
    r = _demo()
    for ln in r["links"]:
        dz = np.diff(ln["xyz"][:, 2])
        assert dz.max() <= 1e-6, dz.max()


def test_discharge_grows_downstream():
    """Ниже слияния расход не меньше суммы притоков."""
    r = _demo()
    links = r["links"]
    starts = {tuple(np.round(ln["xyz"][0, :2], 3)): i
              for i, ln in enumerate(links)}
    ups = {}
    for i, ln in enumerate(links):
        end = tuple(np.round(ln["xyz"][-1, :2], 3))
        j = starts.get(end)
        if j is not None and j != i:
            ups.setdefault(j, []).append(i)
    assert ups, "сеть не связана"
    for j, ii in ups.items():
        assert links[j]["q"] >= sum(links[i]["q"] for i in ii) - 1e-9
        orders = [links[i]["order"] for i in ii]
        top = max(orders)
        want = top + 1 if orders.count(top) > 1 else top
        assert links[j]["order"] == want


def test_discharge_spans_orders_of_magnitude():
    """Расходы различаются в десятки раз: толщине есть что показать."""
    q = [ln["q"] for ln in _demo()["links"]]
    assert max(q) / min(q) > 20, (min(q), max(q))
    assert max(ln["order"] for ln in _demo()["links"]) >= 3


def test_same_seed_same_network():
    a = dr.demo(seed=7, nx=60, ny=50)
    b = dr.demo(seed=7, nx=60, ny=50)
    assert len(a["links"]) == len(b["links"])
    assert np.allclose(a["dem"], b["dem"])


def test_lines_sit_on_the_relief():
    """Русло лежит над рельефом на подъём, а не висит и не тонет."""
    r = dr.demo(seed=3, lift=1.0)
    z, gt = r["dem"], r["gt"]
    for ln in r["links"]:
        p = ln["xyz"]
        c = ((p[:, 0] - gt[0]) / gt[1]).astype(int)
        rr = ((p[:, 1] - gt[3]) / gt[5]).astype(int)
        ok = (c >= 0) & (c < z.shape[1]) & (rr >= 0) & (rr < z.shape[0])
        gap = p[ok, 2] - z[rr[ok], c[ok]]
        assert gap.min() > -5.0 and gap.max() < 5.0, (gap.min(),
                                                      gap.max())


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all demo_rivers tests passed")


if __name__ == "__main__":
    _run()
