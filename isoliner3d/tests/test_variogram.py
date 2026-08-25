# -*- coding: utf-8 -*-
"""Проверка вариограммы: замер и подбор модели.

Считается на голом NumPy, QGIS не нужен. Проверяется главное: на данных,
построенных по известной модели, подбор её и находит. Без этого
подобранная вариограмма ничем не отличается от выдуманной, а на ней
потом стоит весь кригинг.
"""

import os
import sys

import numpy as np

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import variogram as vg   # noqa: E402


def _field(n=1400, rng_len=200.0, sill=1.0, nugget=0.2, seed=0, size=900.0):
    """Поле с заданной длиной связи: сумма гладких волн плюс шум.

    Точная вариограмма у такого поля не сферическая, но длина связи
    задана построением, и подбор обязан её найти.
    """
    rs = np.random.RandomState(seed)
    pts = rs.uniform(0.0, size, (n, 3))
    val = np.zeros(n)
    for _ in range(60):
        k = rs.normal(size=3) / rng_len
        ph = rs.uniform(0.0, 2 * np.pi)
        val += np.cos(pts @ k + ph)
    val *= np.sqrt(sill) / np.std(val)
    val += rs.normal(scale=np.sqrt(nugget), size=n)
    return pts, val


def test_experimental_starts_low_and_grows():
    """Замер растёт от нуля к порогу: близкие точки похожи."""
    pts, val = _field()
    h, g, cnt = vg.experimental(pts, val, nlags=12)
    assert len(h) == len(g) == len(cnt)
    assert (cnt > 0).all()
    assert g[0] < g[-1], (g[0], g[-1])
    assert h[0] < h[-1]


def test_experimental_plateau_is_the_variance():
    """На больших расстояниях замер выходит на разброс данных."""
    pts, val = _field()
    _h, g, _c = vg.experimental(pts, val, nlags=14)
    assert abs(g[-1] / np.var(val) - 1.0) < 0.35, (g[-1], np.var(val))


def test_pure_noise_is_all_nugget():
    """У чистого шума связи нет: замер плоский с самого начала.

    Самородковый эффект это и есть та часть разброса, которая
    не убывает с расстоянием.
    """
    rs = np.random.RandomState(3)
    pts = rs.uniform(0.0, 500.0, (900, 3))
    val = rs.normal(size=900)
    _h, g, _c = vg.experimental(pts, val, nlags=10)
    assert abs(g[0] / g[-1] - 1.0) < 0.25, (g[0], g[-1])
    fit = vg.fit(*vg.experimental(pts, val, nlags=10)[:3], kind="spherical")
    assert fit["nugget"] > 0.5 * (fit["nugget"] + fit["sill"]), fit


def _fitted_range(rng_len, seed=0):
    pts, val = _field(rng_len=rng_len, seed=seed, size=2400.0, n=1600)
    h, g, c = vg.experimental(pts, val, nlags=16)
    return vg.fit(h, g, c, kind="spherical")["range"]


def test_fit_follows_the_length_of_connection():
    """Длиннее связь в данных - длиннее подобранная.

    Точное значение зависит от того, как построено поле, а вот эта
    зависимость обязана держаться: иначе подбор меряет не то.
    """
    short = _fitted_range(150.0)
    long_ = _fitted_range(450.0)
    assert long_ > short * 1.6, (short, long_)


def test_fit_range_is_of_the_right_size():
    """Подобранная длина одного порядка с заложенной, а не в разы мимо."""
    got = _fitted_range(300.0)
    assert 100.0 < got < 900.0, got


def test_fit_separates_nugget_from_sill():
    """Шум уходит в самородок, а не в порог."""
    pts, val = _field(sill=1.0, nugget=0.4, seed=5)
    h, g, c = vg.experimental(pts, val, nlags=14)
    fit = vg.fit(h, g, c, kind="spherical")
    assert 0.15 < fit["nugget"] < 0.75, fit
    assert fit["sill"] > fit["nugget"], fit


def test_model_shape_is_right():
    """Модель начинается с самородка и выходит на порог."""
    for kind in vg.MODELS:
        y = vg.model(np.array([0.0, 50.0, 1e6]), 0.2, 1.0, 100.0, kind)
        assert abs(y[0] - 0.2) < 1e-9, kind
        assert abs(y[-1] - 1.2) < 1e-6, kind
        assert 0.2 < y[1] < 1.2, kind


def test_model_never_falls():
    """Вариограмма не убывает: иначе дальние точки похожее ближних."""
    h = np.linspace(0.0, 400.0, 200)
    for kind in vg.MODELS:
        y = vg.model(h, 0.1, 1.0, 120.0, kind)
        assert (np.diff(y) >= -1e-12).all(), kind


def test_auto_picks_a_model():
    """Автоподбор возвращает вид модели и её параметры."""
    pts, val = _field()
    fit = vg.auto_fit(pts, val, nlags=14)
    assert fit["kind"] in vg.MODELS
    assert fit["sill"] > 0 and fit["range"] > 0
    assert fit["n_pairs"] > 0


def test_anisotropy_changes_the_measurement():
    """Сжатие вертикали меняет замер: расстояния считаются иначе.

    У скважин по вертикали данных на порядок больше, и без сжатия
    вариограмма меряет одно вертикальное строение.
    """
    pts, val = _field()
    _h1, g1, _c1 = vg.experimental(pts, val, nlags=10, anisotropy=1.0)
    _h2, g2, _c2 = vg.experimental(pts, val, nlags=10, anisotropy=20.0)
    assert not np.allclose(g1, g2)


def test_pairs_are_capped():
    """Число пар ограничено: на десятке тысяч проб их сто миллионов."""
    rs = np.random.RandomState(1)
    pts = rs.uniform(0, 500, (4000, 3))
    val = rs.normal(size=4000)
    _h, _g, cnt = vg.experimental(pts, val, nlags=10, max_pairs=50000)
    assert cnt.sum() <= 50000, cnt.sum()


def test_too_few_points_is_refused():
    pts = np.zeros((3, 3))
    try:
        vg.experimental(pts, np.zeros(3), nlags=10)
    except ValueError:
        return
    raise AssertionError("на трёх точках вариограмму строить нельзя")


def _layered(n=1200, seed=2):
    """Скважинная картина: по вертикали связь короткая, в плане длинная.

    Так устроен пласт: содержание меняется поперёк залежи быстро,
    а вдоль неё медленно. Одной вариограммой это не описать.
    """
    rs = np.random.RandomState(seed)
    pts = rs.uniform(0.0, 1000.0, (n, 3))
    pts[:, 2] = rs.uniform(-100.0, 0.0, n)
    val = (np.sin(pts[:, 0] / 400.0) + np.cos(pts[:, 1] / 400.0)
           + 3.0 * np.sin(pts[:, 2] / 8.0))
    return pts, val + rs.normal(scale=0.05, size=n)


def test_direction_splits_plan_from_vertical():
    """Замер в плане и по вертикали различает строение.

    У пласта поперёк залежи содержание меняется быстро, а вдоль неё
    медленно. Общая вариограмма усредняет эти два строения в одно
    и не описывает ни того, ни другого.
    """
    pts, val = _layered()
    hp, gp, _cp = vg.experimental(pts, val, nlags=12, direction="plan")
    hv, gv, _cv = vg.experimental(pts, val, nlags=12, direction="vert")
    fp = vg.fit(hp, gp, _cp, kind="spherical")
    fv = vg.fit(hv, gv, _cv, kind="spherical")
    assert fp["range"] > 5.0 * fv["range"], (fp["range"], fv["range"])


def test_direction_keeps_only_its_pairs():
    """В плановый замер не попадают вертикальные пары и наоборот."""
    pts, val = _layered()
    _h, _g, cp = vg.experimental(pts, val, nlags=10, direction="plan")
    _h2, _g2, cv = vg.experimental(pts, val, nlags=10, direction="vert")
    _h3, _g3, ca = vg.experimental(pts, val, nlags=10)
    assert cp.sum() < ca.sum()
    assert cv.sum() < ca.sum()


def test_unknown_direction_is_refused():
    pts, val = _layered()
    try:
        vg.experimental(pts, val, nlags=10, direction="куда-то")
    except ValueError:
        return
    raise AssertionError("неизвестное направление должно отвергаться")


def test_assemble_takes_nugget_from_the_vertical():
    """Самородок берётся из вертикального замера, а не из планового.

    В плане пар ближе шага сети нет вовсе: скважины стоят через сто
    сорок метров, и первый интервал начинается там же. Самородок
    из такого замера это продолжение прямой к нулю через пустоту,
    и он выходит завышенным в разы. По стволу пары есть с трёх метров.
    """
    plan = {"kind": "spherical", "nugget": 2.7, "sill": 4.5,
            "range": 330.0}
    vert = {"kind": "spherical", "nugget": 0.1, "sill": 9.4,
            "range": 48.0}
    got = vg.assemble(plan, vert, variance=6.2)
    assert abs(got["nugget"] - 0.1) < 1e-9, got
    assert abs(got["range"] - 330.0) < 1e-9, got
    assert abs(got["nugget"] + got["sill"] - 6.2) < 1e-9, got


def test_assemble_gives_the_anisotropy():
    """Отношение длин связи и есть анизотропия, а не догадка."""
    plan = {"kind": "spherical", "nugget": 0.0, "sill": 1.0,
            "range": 300.0}
    vert = {"kind": "spherical", "nugget": 0.0, "sill": 1.0,
            "range": 40.0}
    got = vg.assemble(plan, vert, variance=1.0)
    assert abs(got["anisotropy"] - 40.0 / 300.0) < 1e-9, got


def test_assemble_survives_a_flat_vertical():
    """Если вертикального замера нет, берём плановый как есть."""
    plan = {"kind": "spherical", "nugget": 0.3, "sill": 1.0,
            "range": 200.0}
    got = vg.assemble(plan, None, variance=1.3)
    assert abs(got["nugget"] - 0.3) < 1e-9
    assert abs(got["anisotropy"] - 1.0) < 1e-9


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all variogram tests passed")


if __name__ == "__main__":
    _run()
