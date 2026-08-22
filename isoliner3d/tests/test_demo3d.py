# -*- coding: utf-8 -*-
"""Проверка демонстрационной залежи и разбуривания.

Считается на голом NumPy, QGIS не нужен. Смысл проверок в том, что
на этих данных потом сравнивают методы интерполяции: если модель
вырождается или тело не разбурено, сравнивать нечего.
"""

import os
import sys

import numpy as np

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import demo3d   # noqa: E402


def _model(kind="bed"):
    return demo3d.make_model(kind, 0.0, 0.0, 1000.0, 1000.0, 0.0, 200.0)


def _drill(kind="bed", holes=36, seed=1, **kw):
    m = _model(kind)
    rng = np.random.RandomState(seed)
    xs, ys, collar, length = demo3d.hole_layout(m, holes, rng)
    data = demo3d.hole_samples(m, xs, ys, collar, length, rng, **kw)
    return m, xs, ys, collar, length, data


def test_boundary_matches_cutoff():
    """На границе тела содержание равно отсечке.

    Иначе отсечка по половине ядра резала бы не там, где заложено,
    и проверять построенное тело было бы не с чем.
    """
    for kind in demo3d.KINDS:
        m = demo3d.make_model(kind, 0, 0, 1000, 1000, 0, 200,
                              core=8.0, back=0.3)
        val = demo3d._profile(1.0)
        assert abs(val - 0.5) < 1e-12, (kind, val)
        assert abs(demo3d.cutoff_for(m) - (0.3 + 4.0)) < 1e-12


def test_profile_is_flat_on_top_and_falls_fast():
    """Плоская вершина и быстрый спад: тело выходит с чёткой границей."""
    assert demo3d._profile(0.0) == 1.0
    assert demo3d._profile(0.5) > 0.98
    assert demo3d._profile(1.5) < 0.10
    assert demo3d._profile(2.0) < 0.02


def test_bed_dips_and_folds():
    """У пласта есть и падение, и складка.

    Без падения горизонтальные уровни куба совпадут с залежью,
    и главный недостаток послойной интерполяции не проявится.
    """
    m = _model("bed")
    west = demo3d.bed_roof(50.0, 500.0, m)
    east = demo3d.bed_roof(950.0, 500.0, m)
    assert west - east > 0.2 * m["depth"], (west, east)
    ys = np.linspace(0, 1000, 40)
    line = demo3d.bed_roof(np.full(40, 500.0), ys, m)
    assert line.max() - line.min() > 0.1 * m["depth"]


def test_bed_thickness_varies_and_never_vanishes():
    m = _model("bed")
    xx, yy = np.meshgrid(np.linspace(0, 1000, 25), np.linspace(0, 1000, 25))
    t = demo3d.bed_thickness(xx, yy, m)
    assert t.min() > 0.0
    assert t.max() / t.min() > 1.5


def test_level_cuts_the_bed_partly():
    """Горизонтальный уровень пересекает пласт не по всей площади.

    Это и есть то, что должно быть видно на кубе: уровень режет
    наклонную залежь поперёк.
    """
    m = _model("bed")
    xx, yy = np.meshgrid(np.linspace(0, 1000, 60), np.linspace(0, 1000, 60))
    z = np.full(xx.shape, m["top"] - m["depth"] * 0.45)
    inside = np.abs(demo3d.body_coord(xx, yy, z, m)) <= 1.0
    share = inside.mean()
    assert 0.02 < share < 0.75, share


def test_vein_is_steeper_than_bed():
    """У жилы тело вытянуто по вертикали, у пласта по горизонтали."""
    zs = np.linspace(-190, -10, 60)
    xs = np.full(60, 500.0)
    ys = np.full(60, 500.0)
    bed = np.abs(demo3d.body_coord(xs, ys, zs, _model("bed"))) <= 1.0
    vein = np.abs(demo3d.body_coord(xs, ys, zs, _model("vein"))) <= 1.0
    assert vein.sum() > bed.sum(), (int(vein.sum()), int(bed.sum()))


def test_grade_is_finite_and_positive():
    for kind in demo3d.KINDS:
        m = _model(kind)
        xx, yy = np.meshgrid(np.linspace(0, 1000, 20),
                             np.linspace(0, 1000, 20))
        for z in (-10.0, -60.0, -110.0, -190.0):
            g = demo3d.grade_field(xx, yy, np.full(xx.shape, z), m,
                                   trend=0.15)
            assert np.isfinite(g).all()
            assert g.min() >= 0.0


def test_richness_varies_inside_the_body():
    """Содержание внутри тела не постоянно: иначе методы не разойдутся."""
    m = _model("bed")
    xx, yy = np.meshgrid(np.linspace(0, 1000, 40), np.linspace(0, 1000, 40))
    mid = demo3d.bed_roof(xx, yy, m) - demo3d.bed_thickness(xx, yy, m) / 2.0
    g = demo3d.grade_field(xx, yy, mid, m)
    assert g.max() / max(g.min(), 1e-9) > 1.8


def test_holes_differ_in_collar_and_length():
    """Устья по рельефу, глубины разные, часть скважин недобурена."""
    _m, xs, ys, collar, length, _d = _drill()
    assert xs.size == 36 and ys.size == 36
    assert collar.max() - collar.min() > 1.0
    assert length.max() / length.min() > 1.5


def test_holes_stay_inside_the_site():
    m, xs, ys, _c, _l, _d = _drill()
    assert xs.min() >= m["x0"] - 1e-9
    assert xs.max() <= m["x0"] + m["w"] + 1e-9
    assert ys.min() >= m["y0"] - 1e-9
    assert ys.max() <= m["y0"] + m["h"] + 1e-9


def test_intervals_are_continuous():
    """Интервалы стыкуются встык, без пропусков и нахлёстов."""
    _m, _x, _y, _c, _l, d = _drill(sample=2.0)
    hole = d["hole"]
    for k in np.unique(hole)[:5]:
        sel = hole == k
        f = d["from_m"][sel]
        t = d["to_m"][sel]
        assert np.allclose(t[:-1], f[1:])
        assert abs(f[0]) < 1e-9


def test_body_is_actually_drilled():
    """Пробы внутри тела есть у всех трёх типов, но тело не всё поле."""
    for kind in demo3d.KINDS:
        _m, _x, _y, _c, _l, d = _drill(kind=kind)
        share = d["zone"].mean()
        assert 0.01 < share < 0.6, (kind, share)


def test_noise_keeps_grade_positive_and_unbiased():
    """Логнормальный шум не даёт отрицательных содержаний."""
    _m, _x, _y, _c, _l, d = _drill(noise=0.25)
    assert d["grade"].min() > 0.0
    rel = d["grade"].mean() / d["truth"].mean()
    assert 0.9 < rel < 1.1, rel


def test_zero_noise_reproduces_truth():
    _m, _x, _y, _c, _l, d = _drill(noise=0.0)
    assert np.allclose(d["grade"], d["truth"])


def test_seed_is_reproducible():
    a = _drill(seed=7)[5]
    b = _drill(seed=7)[5]
    c = _drill(seed=8)[5]
    assert np.array_equal(a["grade"], b["grade"])
    assert not np.array_equal(a["grade"][:50], c["grade"][:50])


def test_inclined_holes_move_off_the_collar():
    """Наклонный ствол уходит в сторону от устья."""
    _m, xs, _y, _c, _l, d = _drill(incline=20.0)
    first = d["hole"] == 1
    dx = d["x"][first] - d["x"][first][0]
    assert np.abs(dx).max() > 1.0


def test_unknown_kind_is_refused():
    try:
        demo3d.make_model("что-то")
    except ValueError:
        return
    raise AssertionError("неизвестный тип залежи должен отвергаться")


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all demo3d tests passed")


if __name__ == "__main__":
    _run()
