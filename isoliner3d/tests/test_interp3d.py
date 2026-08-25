# -*- coding: utf-8 -*-
"""Проверка модели содержаний для демонстрационных данных.

Считается на голом Python: QGIS для этого не нужен, а сама модель
должна вести себя предсказуемо, иначе на ней нельзя сравнивать методы
интерполяции.
"""

import os
import sys

import numpy as np

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))


from isoliner3d import interp3d   # noqa: E402
from isoliner3d.interp3d import grid_nodes   # noqa: E402
from isoliner3d.demo3d import demo_grade   # noqa: E402


def _load_grade():
    """Модель содержаний живёт в demo3d, QGIS для неё не нужен."""
    return demo_grade


def test_core_is_richest():
    """Середина линзы богаче краёв: иначе проверять нечего."""
    grade = _load_grade()
    core = grade(500, 500, -100)
    assert core > grade(800, 500, -100)
    assert core > grade(500, 500, -60)
    assert core > grade(0, 0, 0)


def test_lens_is_flatter_than_tall():
    """Линза шире, чем толще.

    Это и делает данные пригодными для проверки анизотропии: без неё
    ближайшей точкой окажется соседняя скважина, а не соседний замер.
    """
    grade = _load_grade()
    side = grade(500 + 200, 500, -100)      # 200 м по горизонтали
    up = grade(500, 500, -100 + 20)         # 20 м по вертикали
    assert side > up, (side, up)


def test_trend_exists():
    """Есть общий наклон содержаний, а не только линза."""
    grade = _load_grade()
    assert grade(1000, 1000, 0) - grade(0, 0, 0) > 0.5


def test_values_are_finite_everywhere():
    grade = _load_grade()
    for x in (0, 250, 500, 750, 1000):
        for z in (0, -50, -100, -150, -200):
            v = grade(x, x, z)
            assert v == v and abs(v) < 1e6


def test_linear_field_is_reproduced():
    """На линейном поле оба метода дают близкое к истине значение."""
    import numpy as np
    from isoliner3d.interp3d import interpolate
    rng = np.random.RandomState(0)
    pts = rng.uniform(0, 100, (400, 3))
    pts[:, 2] = rng.uniform(-50, 0, 400)
    val = 2.0 * pts[:, 0] + 3.0 * pts[:, 1] - pts[:, 2]
    node = np.array([[50.0, 50.0, -25.0]])
    truth = 2 * 50 + 3 * 50 + 25
    for method in ("nearest", "idw"):
        got = interpolate(pts, val, node, method=method, radius=60,
                          max_points=12)[0]
        assert abs(got - truth) / truth < 0.1, (method, got, truth)


def test_point_itself_is_exact():
    """В самой точке значение совпадает: иначе метод не интерполирует."""
    import numpy as np
    from isoliner3d.interp3d import interpolate
    rng = np.random.RandomState(1)
    pts = rng.uniform(0, 50, (60, 3))
    val = rng.uniform(0, 10, 60)
    got = interpolate(pts, val, pts[:1], method="idw", radius=40)[0]
    assert abs(got - val[0]) < 1e-9


def test_far_node_stays_empty():
    """Там, где точек в радиусе нет, остаётся пропуск."""
    import numpy as np
    from isoliner3d.interp3d import interpolate
    pts = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 0.0]])
    val = np.array([1.0, 2.0])
    got = interpolate(pts, val, np.array([[1000.0, 1000.0, 0.0]]),
                      method="idw", radius=10)
    assert not np.isfinite(got[0])


def test_anisotropy_changes_the_neighbour():
    """Анизотропия меняет, кто ближе: замер в скважине или соседняя.

    Замер на 10 м выше в той же точке плана должен побеждать точку
    в 100 м по горизонтали, если вертикаль сжата.
    """
    import numpy as np
    from isoliner3d.interp3d import interpolate
    pts = np.array([[0.0, 0.0, -10.0],      # тот же ствол, ниже
                    [100.0, 0.0, 0.0]])     # соседняя скважина
    val = np.array([1.0, 2.0])
    node = np.array([[0.0, 0.0, 0.0]])
    same = interpolate(pts, val, node, method="nearest", radius=500,
                       anisotropy=20.0)[0]
    other = interpolate(pts, val, node, method="nearest", radius=500,
                        anisotropy=0.05)[0]
    assert same == 1.0 and other == 2.0, (same, other)


def test_grid_nodes_are_ordered_by_level():
    """Узлы идут уровнями: так же лежат каналы куба."""
    import numpy as np
    from isoliner3d.interp3d import grid_nodes
    nodes = grid_nodes(0.0, 100.0, -50.0, 4, 4, 3, 25.0, 25.0, 10.0)
    assert len(nodes) == 48
    level = nodes[:16, 2]
    assert np.allclose(level, -50.0)
    assert np.allclose(nodes[16:32, 2], -40.0)


def test_cross_validation_reports_error():
    """Проверка с исключением по одной считает ошибку."""
    import numpy as np
    from isoliner3d.interp3d import cross_validate
    rng = np.random.RandomState(2)
    pts = rng.uniform(0, 100, (40, 3))
    val = 2.0 * pts[:, 0] + pts[:, 1]
    _res, mae, rmse = cross_validate(pts, val, method="idw", radius=80,
                                     max_points=8)
    assert mae == mae and rmse >= mae


def test_dense_path_matches_the_cell_index():
    """Блочный расчёт совпадает с поштучным.

    Быстрый путь включается сам при небольшом числе точек, и разойтись
    с медленным он не имеет права: это одна и та же задача.
    """
    rng = np.random.RandomState(4)
    pts = rng.uniform(0, 500, (400, 3))
    vals = rng.uniform(0, 10, 400)
    nodes = grid_nodes(0.0, 500.0, 0.0, 8, 8, 6, 60.0, 60.0, 40.0)
    for method in ("idw", "nearest"):
        keep = interp3d._DENSE_LIMIT
        try:
            interp3d._DENSE_LIMIT = 0
            slow = interp3d.interpolate(pts, vals, nodes, method=method,
                                        radius=200.0, max_points=8)
            interp3d._DENSE_LIMIT = 20000
            fast = interp3d.interpolate(pts, vals, nodes, method=method,
                                        radius=200.0, max_points=8)
        finally:
            interp3d._DENSE_LIMIT = keep
        assert (np.isfinite(slow) == np.isfinite(fast)).all()
        both = np.isfinite(slow)
        assert np.allclose(slow[both], fast[both], atol=1e-8), method


def test_dense_path_keeps_empty_nodes_empty():
    """Узел без точек в радиусе остаётся пропуском и в блочном пути."""
    pts = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]])
    vals = np.array([1.0, 2.0])
    nodes = np.array([[0.0, 0.0, 0.0], [1000.0, 1000.0, 0.0]])
    got = interp3d.interpolate(pts, vals, nodes, radius=50.0,
                               max_points=4)
    assert abs(got[0] - 1.0) < 1e-9
    assert not np.isfinite(got[1])


def _holes(n_side=5, step=200.0, sample=3.0, seed=0):
    """Вертикальные скважины: у каждой своё содержание.

    Опробование частое, сеть редкая - обычная разведочная картина.
    """
    rng = np.random.RandomState(seed)
    pts, val, hole = [], [], []
    k = 0
    for x in np.arange(n_side) * step + step / 2.0:
        for y in np.arange(n_side) * step + step / 2.0:
            v = float(rng.uniform(0.0, 10.0))
            for z in np.arange(-200.0, 0.0, sample):
                pts.append((x, y, z))
                val.append(v)
                hole.append(k)
            k += 1
    return (np.array(pts), np.array(val), np.array(hole))


def test_idw_does_not_degenerate_to_nearest():
    """Обратные расстояния не должны повторять ближайшего соседа.

    При анизотропии проба в стволе оказывается в сотни раз ближе
    соседней скважины, и все ближайшие точки берутся из одной
    скважины. Веса тогда считаются по одному значению, и вместо
    сглаженного поля выходят ячейки Вороного.
    """
    pts, val, _h = _holes()
    nodes = grid_nodes(0.0, 1000.0, -200.0, 30, 30, 10, 33.0, 33.0, 20.0)
    kw = dict(radius=None, anisotropy=20.0, max_points=16)
    idw = interp3d.interpolate(pts, val, nodes, method="idw", **kw)
    near = interp3d.interpolate(pts, val, nodes, method="nearest", **kw)
    ok = np.isfinite(idw) & np.isfinite(near)
    same = (np.abs(idw[ok] - near[ok]) < 0.05).mean()
    assert same < 0.6, "совпало с ближайшим соседом: %.0f%%" % (100 * same)


def test_neighbours_come_from_several_holes():
    """Соседи набираются из разных скважин, а не из одной."""
    pts, val, hole = _holes()
    node = np.array([[250.0, 250.0, -100.0]])
    got = interp3d.neighbour_ids(pts, node, radius=None, anisotropy=20.0,
                                 max_points=16)[0]
    got = [i for i in got if i >= 0]
    assert len(set(hole[got].tolist())) >= 3, sorted(hole[got].tolist())


def test_sectors_can_be_switched_off():
    """Один сектор это прежнее поведение: соседи из одной скважины."""
    pts, val, hole = _holes()
    node = np.array([[250.0, 250.0, -100.0]])
    got = interp3d.neighbour_ids(pts, node, radius=None, anisotropy=20.0,
                                 max_points=16, sectors=1)[0]
    got = [i for i in got if i >= 0]
    assert len(set(hole[got].tolist())) == 1


def test_sector_search_keeps_the_exact_point():
    """Узел в точке опробования получает её значение без изменений."""
    pts, val, _h = _holes()
    got = interp3d.interpolate(pts, val, pts[:20], method="idw",
                               anisotropy=20.0, max_points=16)
    assert np.allclose(got, val[:20])


def test_z_from_geometry():
    """Отметка из геометрии берётся как есть, пропуск остаётся пропуском."""
    z = interp3d.resolve_z("geom", gz=[10.0, np.nan], fz=None,
                           surf=None, depth=None)
    assert z[0] == 10.0 and not np.isfinite(z[1])


def test_z_from_field_beats_a_flat_layer():
    """У плоского слоя отметку даёт поле, а не ноль из геометрии.

    Плоский слой отдаёт нулевую Z у каждой точки. Если бы её брали
    как есть, все пробы легли бы в одну плоскость и куб вышел бы
    бессмысленным.
    """
    z = interp3d.resolve_z("field", gz=[0.0, 0.0, 0.0],
                           fz=[-12.0, -30.0, np.nan],
                           surf=None, depth=None)
    assert list(z[:2]) == [-12.0, -30.0]
    assert not np.isfinite(z[2])


def test_z_from_depth_below_the_surface():
    """Глубина отсчитывается вниз от поверхности.

    Почвенные пробы записывают глубину, а не отметку, и без поверхности
    перевести одно в другое нельзя.
    """
    z = interp3d.resolve_z("depth", gz=None, fz=None,
                           surf=[120.0, 118.0], depth=[0.2, 1.5])
    assert abs(z[0] - 119.8) < 1e-9
    assert abs(z[1] - 116.5) < 1e-9


def test_depth_without_a_surface_is_a_gap():
    """Без данных поверхности проба не садится на ноль, а выпадает."""
    z = interp3d.resolve_z("depth", gz=None, fz=None,
                           surf=[np.nan, 100.0], depth=[0.5, 0.5])
    assert not np.isfinite(z[0])
    assert abs(z[1] - 99.5) < 1e-9


def test_unknown_mode_is_refused():
    try:
        interp3d.resolve_z("что-то", gz=[1.0], fz=None, surf=None,
                           depth=None)
    except ValueError:
        return
    raise AssertionError("неизвестный источник отметки должен отвергаться")


def test_samples_at_one_place_differ_by_z():
    """Пробы в одной точке плана расходятся по отметке.

    Ровно случай почвенных проб: координаты те же, глубины разные,
    и без разбора отметки они схлопнулись бы в одну точку.
    """
    z = interp3d.resolve_z("depth", gz=None, fz=None,
                           surf=[100.0] * 3, depth=[0.1, 0.5, 1.2])
    assert len(set(np.round(z, 6).tolist())) == 3


def test_spacing_of_boreholes():
    """Замеряем сеть: шаг по стволу, шаг в плане, замеров на точку."""
    pts, _v, _h = _holes(n_side=4, step=200.0, sample=3.0)
    dz, dxy, per = interp3d.sampling_spacing(pts)
    assert abs(dz - 3.0) < 1e-6, dz
    assert abs(dxy - 200.0) < 1.0, dxy
    assert per > 50, per


def test_spacing_of_layered_samples():
    """У проб по уровням замеров на точку мало, и это главное отличие.

    Отношение шагов у скважин и у почвенных проб почти одинаковое,
    различает их число замеров в одной точке плана.
    """
    pts = []
    for x in (0.0, 400.0, 40.0, 420.0):
        for y in (0.0, 380.0):
            for z in (210.0, 215.0, 220.0):
                pts.append((x, y, z))
    dz, dxy, per = interp3d.sampling_spacing(np.array(pts))
    assert abs(dz - 5.0) < 1e-6, dz
    assert per == 3, per


def test_spacing_needs_repeated_places():
    """Без повторов в плане мерить нечего."""
    rng = np.random.RandomState(2)
    pts = rng.uniform(0, 500, (30, 3))
    assert interp3d.sampling_spacing(pts) is None


def test_too_many_points_smears_the_levels():
    """Соседей больше, чем уровней, и различие по глубине пропадает.

    Три уровня на площадку: если узел берёт шестнадцать точек, в среднее
    попадают все три уровня всех площадок, и аномалия по глубине
    сглаживается в ровное поле.
    """
    pts, vals = [], []
    for x in (0.0, 400.0):
        for y in (0.0, 400.0):
            for z, v in ((210.0, 8.0), (215.0, 15.0), (220.0, 8.0)):
                pts.append((x, y, z))
                vals.append(v)
    pts = np.array(pts)
    vals = np.array(vals)
    nodes = np.array([[200.0, 200.0, z] for z in (210.0, 215.0, 220.0)])
    kw = dict(anisotropy=1.0, method="idw", radius=1000.0)
    wide = interp3d.interpolate(pts, vals, nodes, max_points=16, **kw)
    tight = interp3d.interpolate(pts, vals, nodes, max_points=4, **kw)
    assert np.ptp(wide) < 0.5, np.ptp(wide)
    assert np.ptp(tight) > 3.0, np.ptp(tight)


def test_grid_advice_is_quiet_on_a_sane_grid():
    """Сетка соразмерна сети опробования: сказать нечего."""
    assert interp3d.grid_advice(60, 50, 40, cell=400.0, dxy=3700.0,
                                limit=20 * 10 ** 6) == []


def test_grid_advice_counts_the_nodes():
    """Слишком крупная сетка называется числом узлов, а не словами."""
    out = interp3d.grid_advice(1075, 807, 52, cell=25.0, dxy=3732.0,
                               limit=20 * 10 ** 6)
    assert any("45111300" in m for m in out), out


def test_grid_advice_notices_a_needlessly_fine_step():
    """Шаг много мельче сети опробования: узлы не несут данных.

    Между соседними площадками сто сорок девять ячеек, а данных
    между ними нет ни одной точки.
    """
    out = interp3d.grid_advice(200, 200, 10, cell=25.0, dxy=3732.0,
                               limit=20 * 10 ** 6)
    assert out and any("149" in m for m in out), out


def test_grid_advice_needs_a_spacing():
    """Без замера сети про шаг не судим, но про число узлов судим."""
    out = interp3d.grid_advice(1075, 807, 52, cell=25.0, dxy=None,
                               limit=20 * 10 ** 6)
    assert len(out) == 1


def test_auto_cell_from_the_plan_step():
    """Шаг в плане берётся долей расстояния между точками плана."""
    got = interp3d.auto_grid(dz=5.0, dxy=327.0, per=3)
    assert 50.0 <= got["cell"] <= 90.0, got


def test_auto_cellz_from_the_sampling_step():
    """Шаг по вертикали мельче шага опробования, иначе уровни сольются."""
    got = interp3d.auto_grid(dz=5.0, dxy=327.0, per=3)
    assert got["cellz"] < 5.0, got
    assert got["cellz"] > 0.0


def test_auto_points_follow_the_levels():
    """Соседей берём чуть больше, чем замеров в одной точке плана.

    Больше значит смешать уровни и сгладить различие по глубине,
    ровно та беда, из-за которой поле выходило ровным.
    """
    assert interp3d.auto_grid(5.0, 327.0, 3)["max_points"] == 4
    assert interp3d.auto_grid(3.0, 142.0, 64)["max_points"] == 16


def test_auto_points_have_a_floor():
    """Меньше четырёх соседей брать незачем даже при одном замере."""
    assert interp3d.auto_grid(5.0, 300.0, 1)["max_points"] >= 4


def test_auto_grid_survives_a_huge_site():
    """На площадке в двадцать семь километров сетка остаётся посильной.

    Двадцать пять метров на такой площадке давали сорок пять миллионов
    узлов, и это был не выбор человека, а умолчание.
    """
    got = interp3d.auto_grid(3.0, 3732.0, 66)
    nodes = (27000.0 / got["cell"]) * (20000.0 / got["cell"]) * 52
    assert nodes < 2 * 10 ** 6, (got, nodes)


def test_auto_grid_needs_a_measured_net():
    """Без замера сети подставлять нечего."""
    assert interp3d.auto_grid(None, None, None) is None


def test_cv_report_counts_what_matters():
    """Сводка по невязкам: сколько проверено, насколько промахнулись."""
    res = np.array([1.0, -1.0, 2.0, np.nan])
    val = np.array([10.0, 10.0, 10.0, 10.0])
    rep = interp3d.cv_report(res, val)
    assert rep["n"] == 3
    assert abs(rep["mae"] - 4.0 / 3.0) < 1e-9
    assert abs(rep["rmse"] - np.sqrt(6.0 / 3.0)) < 1e-9
    assert abs(rep["bias"] - 2.0 / 3.0) < 1e-9


def test_cv_report_share_of_spread():
    """Ошибка сопоставляется с размахом самих данных.

    Средняя ошибка в единицу мало что говорит, пока не видно, что
    данные меняются от нуля до десяти или от нуля до единицы.
    """
    res = np.array([1.0, -1.0])
    rep = interp3d.cv_report(res, np.array([0.0, 10.0]))
    assert abs(rep["mae_share"] - 0.1) < 1e-9


def test_cv_report_survives_all_gaps():
    """Если проверить не удалось ничего, сводка не падает."""
    rep = interp3d.cv_report(np.array([np.nan, np.nan]),
                             np.array([1.0, 2.0]))
    assert rep["n"] == 0
    assert rep["mae"] != rep["mae"]


def test_sectors_lower_the_error_on_boreholes():
    """Сектора уменьшают ошибку на скважинной сети.

    Это число из разбора: с одним сектором соседи берутся из одной
    скважины, и проверка исключением по одной это видит.
    """
    pts, val, _h = _holes(n_side=4, step=200.0, sample=5.0)
    kw = dict(method="idw", anisotropy=20.0, max_points=16)
    _r1, mae1, _s1 = interp3d.cross_validate(pts, val, sectors=1, **kw)
    _r8, mae8, _s8 = interp3d.cross_validate(pts, val, sectors=8, **kw)
    assert mae8 < mae1, (mae8, mae1)


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all interp3d tests passed")


if __name__ == "__main__":
    _run()
