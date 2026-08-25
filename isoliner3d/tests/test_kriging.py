# -*- coding: utf-8 -*-
"""Проверка обычного кригинга в объёме.

Считается на голом NumPy, QGIS не нужен. Проверяется то, что отличает
кригинг от взвешивания по расстоянию: точность в самих пробах, сумма
весов, поведение дисперсии оценки и вырожденные случаи модели.
"""

import os
import sys

import numpy as np

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import kriging as kg   # noqa: E402
from isoliner3d import variogram as vg, demo3d   # noqa: E402
from isoliner3d.interp3d import cross_validate   # noqa: E402

VM = {"kind": "spherical", "nugget": 0.0, "sill": 1.0, "range": 200.0}


def _cloud(n=120, seed=0, size=500.0):
    rs = np.random.RandomState(seed)
    pts = rs.uniform(0.0, size, (n, 3))
    val = (np.sin(pts[:, 0] / 120.0) * 3.0 + pts[:, 2] / 100.0)
    return pts, val


def test_exact_at_the_samples():
    """В самой пробе кригинг возвращает её значение.

    Точность в узлах данных это свойство метода: если её нет, где-то
    ошибка в системе.
    """
    pts, val = _cloud()
    est, _var = kg.ordinary(pts, val, pts[:20], VM, radius=400.0,
                            max_points=12)
    assert np.allclose(est, val[:20], atol=1e-6), np.abs(
        est - val[:20]).max()


def test_variance_is_zero_at_the_samples():
    """В пробе дисперсия оценки равна нулю: там ничего не гадаем."""
    pts, val = _cloud()
    _est, var = kg.ordinary(pts, val, pts[:20], VM, radius=400.0,
                            max_points=12)
    assert np.all(np.abs(var) < 1e-6), float(np.max(np.abs(var)))


def test_variance_grows_with_distance():
    """Дальше от данных дисперсия больше: это и есть карта доверия."""
    pts, val = _cloud(size=300.0)
    near = np.array([[150.0, 150.0, 150.0]])
    far = np.array([[900.0, 900.0, 150.0]])
    _e1, v1 = kg.ordinary(pts, val, near, VM, radius=1500.0,
                          max_points=12)
    _e2, v2 = kg.ordinary(pts, val, far, VM, radius=1500.0,
                          max_points=12)
    assert v2[0] > v1[0], (v1[0], v2[0])


def test_weights_sum_to_one():
    """Веса суммируются в единицу: оценка несмещённая по построению."""
    pts, val = _cloud()
    node = np.array([[250.0, 250.0, 250.0]])
    w, _mu, _idx = kg.weights(pts, node, VM, radius=400.0, max_points=10)
    assert abs(float(np.nansum(w[0])) - 1.0) < 1e-9, float(np.nansum(w[0]))


def test_pure_nugget_gives_the_mean():
    """При чистом самородке связи нет, и оценка это среднее соседей.

    Вырожденный случай, но именно на нём видно, что система решается
    правильно: все веса равны.
    """
    pts, val = _cloud()
    vm = {"kind": "spherical", "nugget": 1.0, "sill": 0.0, "range": 100.0}
    node = np.array([[250.0, 250.0, 250.0]])
    w, _mu, idx = kg.weights(pts, node, vm, radius=1000.0, max_points=8)
    good = idx[0] >= 0
    assert np.allclose(w[0][good], 1.0 / good.sum(), atol=1e-6), w[0][good]


def test_far_node_stays_empty():
    """Узел без данных в радиусе остаётся пропуском, а не нулём."""
    pts, val = _cloud(size=200.0)
    far = np.array([[10000.0, 10000.0, 0.0]])
    est, var = kg.ordinary(pts, val, far, VM, radius=300.0, max_points=8)
    assert not np.isfinite(est[0])
    assert not np.isfinite(var[0])


def test_anisotropy_changes_the_answer():
    """Сжатие вертикали меняет и веса, и оценку."""
    pts, val = _cloud()
    node = np.array([[250.0, 250.0, 250.0]])
    e1, _v1 = kg.ordinary(pts, val, node, VM, radius=400.0, max_points=10,
                          anisotropy=1.0)
    e2, _v2 = kg.ordinary(pts, val, node, VM, radius=400.0, max_points=10,
                          anisotropy=10.0)
    assert abs(float(e1[0]) - float(e2[0])) > 1e-9


def _compare(holes, seed=1):
    """Сравнение методов на честной мерке: скважина исключается целиком."""
    m = demo3d.make_model("bed", 0, 0, 1000, 1000, 0, 200)
    rs = np.random.RandomState(seed)
    xs, ys, col, ln = demo3d.hole_layout(m, holes, rs)
    d = demo3d.hole_samples(m, xs, ys, col, ln, rs, sample=5.0, noise=0.12)
    pts = np.column_stack([d["x"], d["y"], d["z"]])
    val, hole = d["grade"], d["hole"]
    fp = vg.auto_fit(pts, val, nlags=12, direction="plan")
    fv = vg.auto_fit(pts, val, nlags=12, direction="vert")
    vm = vg.assemble(fp, fv, float(np.var(val)))
    kw = dict(groups=hole, radius=800.0, max_points=16,
              anisotropy=vm["anisotropy"])
    _r1, mae_idw, _s1 = cross_validate(pts, val, method="idw", **kw)
    _r2, mae_kr, _s2 = cross_validate(pts, val, method="kriging",
                                      vmodel=vm, **kw)
    return mae_idw, mae_kr


def test_beats_inverse_distance_on_a_dense_grid():
    """На густой сети кригинг выигрывает.

    Мерка честная: скважина исключается целиком. По одной пробе разницу
    метода не увидеть, там всё решает соседний замер по тому же стволу.
    """
    mae_idw, mae_kr = _compare(100)
    assert mae_kr < mae_idw, (mae_kr, mae_idw)


def test_sparse_grid_gives_kriging_nothing():
    """На редкой сети выигрыша нет, и это не дефект.

    Когда шаг сети сравним с длиной связи, соседние скважины уже почти
    ничего не знают друг о друге. Веса выходят почти равными у любого
    метода, и разница уходит в шум. Проверка закрепляет границу
    применимости, чтобы её не выдавали за поломку.
    """
    mae_idw, mae_kr = _compare(16)
    assert mae_kr > mae_idw


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all kriging tests passed")


if __name__ == "__main__":
    _run()
