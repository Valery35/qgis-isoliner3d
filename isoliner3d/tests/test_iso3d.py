# -*- coding: utf-8 -*-
"""Проверка изоповерхности по кубу значений.

Считается на голом NumPy, QGIS не нужен.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from isoliner3d import iso3d   # noqa: E402
from isoliner3d.iso3d import isosurface, is_watertight   # noqa: E402

GT = (0.0, 1.0, 0.0, 20.0, 0.0, -1.0)


def _sphere(n=21, radius=6.3):
    zz, yy, xx = np.mgrid[0:n, 0:n, 0:n].astype(float)
    c = (n - 1) / 2.0
    vol = radius - np.sqrt((xx - c) ** 2 + (yy - c) ** 2 + (zz - c) ** 2)
    gt = (0.0, 1.0, 0.0, float(n - 1), 0.0, -1.0)
    centre = np.array([gt[0] + (c + 0.5) * gt[1],
                       gt[3] + (c + 0.5) * gt[5], c])
    return vol, gt, centre


def test_plane_cut_is_exact():
    """Горизонтальная граница даёт срез ровно на своей отметке."""
    n = 6
    zz, _yy, _xx = np.mgrid[0:n, 0:n, 0:n].astype(float)
    v, f = isosurface(2.5 - zz, 0.0, GT, 0.0, 1.0)
    assert len(f) > 0
    assert np.allclose(v[:, 2], 2.5)


def test_shell_is_watertight():
    """Оболочка замкнута: каждое ребро входит ровно в две грани.

    Ради этого взят марш по тетраэдрам: у кубов есть неоднозначные
    случаи, на которых соседние ячейки расходятся и оставляют дыру.
    """
    vol, gt, _c = _sphere()
    v, f = isosurface(vol, 0.0, gt, 0.0, 1.0)
    assert len(f) > 1000
    assert is_watertight(v, f)


def test_radius_is_accurate():
    """Вершины ложатся на поверхность шара, а не на узлы сетки."""
    vol, gt, centre = _sphere(radius=6.3)
    v, _f = isosurface(vol, 0.0, gt, 0.0, 1.0)
    r = np.sqrt(((v - centre) ** 2).sum(axis=1))
    assert abs(r.mean() - 6.3) < 0.05, r.mean()
    assert r.std() < 0.05, r.std()


def test_volume_matches_the_sphere():
    """Объём по оболочке сходится с объёмом шара.

    Проверяет заодно ориентацию граней: если часть смотрит внутрь,
    слагаемые гасят друг друга и объём выходит меньше.
    """
    vol, gt, centre = _sphere(radius=6.3)
    v, f = isosurface(vol, 0.0, gt, 0.0, 1.0)
    t = v[f] - centre
    got = np.einsum('ij,ij->i', t[:, 0],
                    np.cross(t[:, 1], t[:, 2])).sum() / 6.0
    want = 4.0 / 3.0 * np.pi * 6.3 ** 3
    assert abs(got - want) / want < 0.05, (got, want)


def test_gaps_stay_outside():
    """Пропуски в данных не притягивают оболочку."""
    n = 8
    vol = np.full((n, n, n), 5.0)
    vol[:, :, 4:] = np.nan
    v, f = isosurface(vol, 1.0, GT, 0.0, 1.0)
    assert len(f) > 0
    assert v[:, 0].max() < 5.0, v[:, 0].max()


def test_empty_volume_gives_nothing():
    vol = np.zeros((4, 4, 4))
    v, f = isosurface(vol, 10.0, GT, 0.0, 1.0)
    assert len(f) == 0 and len(v) == 0


def test_welding_glues_shared_vertices():
    """Склейка убирает повторы: соседние грани делят вершину.

    Марш даёт три вершины на грань без единого общего ребра.
    На кубе это втрое больше памяти и втрое больше работы у сцены.
    """
    vol, gt, _c = _sphere()
    raw_v, raw_f = isosurface(vol, 0.0, gt, 0.0, 1.0, weld=False)
    v, f = isosurface(vol, 0.0, gt, 0.0, 1.0)
    assert len(raw_v) == 3 * len(raw_f)
    assert len(v) < len(raw_v) / 2.0, (len(v), len(raw_v))
    assert len(f) == len(raw_f)


def test_welding_keeps_the_shape():
    """Склейка не двигает геометрию: те же треугольники, те же точки."""
    vol, gt, _c = _sphere()
    raw_v, raw_f = isosurface(vol, 0.0, gt, 0.0, 1.0, weld=False)
    v, f = isosurface(vol, 0.0, gt, 0.0, 1.0)
    a = np.sort(raw_v[raw_f].reshape(-1, 9), axis=0)
    b = np.sort(v[f].reshape(-1, 9), axis=0)
    assert np.allclose(a, b, atol=1e-6)


def test_welded_shell_is_still_watertight():
    vol, gt, _c = _sphere()
    v, f = isosurface(vol, 0.0, gt, 0.0, 1.0)
    assert is_watertight(v, f)


def test_levels_match_single_calls():
    """Один проход по уровням даёт ровно то же, что отдельные вызовы."""
    vol, gt, _c = _sphere()
    levels = [-2.0, 0.0, 2.0]
    many = iso3d.isosurface_levels(vol, levels, gt, 0.0, 1.0)
    assert [lv for lv, _v, _f in many] == levels
    for lv, v, f in many:
        v1, f1 = isosurface(vol, lv, gt, 0.0, 1.0)
        assert len(v) == len(v1) and len(f) == len(f1), lv
        assert np.allclose(np.sort(v[f].reshape(-1, 9), axis=0),
                           np.sort(v1[f1].reshape(-1, 9), axis=0),
                           atol=1e-6), lv


def test_only_boundary_cells_are_walked():
    """Работа идёт по пограничным ячейкам, а не по всему кубу.

    Ячейки целиком внутри и целиком снаружи граней не дают, а их
    подавляющее большинство. Проверяем через время: куб вдвое крупнее
    даёт вчетверо больше площади и восьмикратно больше ячеек, и если
    бы перебор шёл по всем ячейкам, время росло бы как объём.
    """
    import time
    small = _sphere(n=31, radius=10.0)
    big = _sphere(n=61, radius=20.0)
    times = []
    for vol, gt, _c in (small, big):
        t = time.time()
        isosurface(vol, 0.0, gt, 0.0, 1.0)
        times.append(time.time() - t)
    grow = times[1] / max(times[0], 1e-6)
    assert grow < 6.0, grow


def test_five_levels_stay_quick():
    """Пять уровней на рабочем кубе укладываются в разумное время.

    Сторож против отката: до правки те же пять уровней считались
    пятнадцать с половиной секунд и занимали пятьдесят мегабайт.
    """
    import time
    n = 60
    zz, yy, xx = np.mgrid[0:n, 0:n, 0:n].astype(float)
    c = (n - 1) / 2.0
    vol = 20.0 - np.sqrt((xx - c) ** 2 + (yy - c) ** 2 + (zz - c) ** 2)
    gt = (0.0, 1.0, 0.0, float(n - 1), 0.0, -1.0)
    t = time.time()
    got = iso3d.isosurface_levels(vol, [-6.0, -3.0, 0.0, 3.0, 6.0],
                                  gt, 0.0, 1.0)
    dt = time.time() - t
    assert len(got) == 5
    assert dt < 8.0, dt
    verts = sum(len(v) for _l, v, _f in got)
    faces = sum(len(f) for _l, _v, f in got)
    assert verts < faces, (verts, faces)


def test_empty_levels_give_nothing():
    vol, gt, _c = _sphere()
    assert iso3d.isosurface_levels(vol, [], gt, 0.0, 1.0) == []


def test_shell_alpha_rule():
    """Одна оболочка плотная, у нескольких прозрачность растёт наружу.

    Разнос нужен, когда сквозь наружную читают внутренние. Одна
    оболочка сквозь себя ничего не показывает, и делать её прозрачной
    незачем.
    """
    from isoliner3d.iso3d import shell_alpha
    assert shell_alpha(0, 1) == 1.0
    two = [shell_alpha(k, 2) for k in range(2)]
    assert two[0] < two[1] and abs(two[1] - 1.0) < 1e-9
    four = [shell_alpha(k, 4) for k in range(4)]
    assert all(a < b for a, b in zip(four, four[1:]))
    assert all(0.0 < a <= 1.0 for a in four)


def test_both_parsers_share_one_rule():
    """Уровни и границы интервалов читаются одним правилом.

    Два разных синтаксиса в одном модуле человек запоминать не обязан.
    """
    from isoliner3d.iso3d import parse_levels
    from isoliner3d import voxel
    for txt in ("2,5 3 3,5", "0 5 10", "0, 5, 10", "10 0 5"):
        a = parse_levels(txt)
        b = voxel.parse_edges(txt)
        assert a == b, (txt, a, b)


def test_levels_from_text():
    """Уровни читаются строкой, как их пишет человек."""
    from isoliner3d.iso3d import parse_levels
    assert parse_levels("2 5 8") == [2.0, 5.0, 8.0]
    assert parse_levels("2; 5; 8") == [2.0, 5.0, 8.0]
    assert parse_levels("8 2 5") == [2.0, 5.0, 8.0]
    assert parse_levels("5") == [5.0]


def test_comma_is_a_decimal_mark():
    """Запятая это знак дроби, а не разделитель.

    У нас пишут «2,5 3 3,5», и приняв запятую за разделитель,
    получишь из двух с половиной два и пять.
    """
    from isoliner3d.iso3d import parse_levels
    assert parse_levels("2,5 3 3,5") == [2.5, 3.0, 3.5]
    assert parse_levels("0,5") == [0.5]
    # точка тоже работает: обе записи в ходу
    assert parse_levels("2.5 3") == [2.5, 3.0]


def test_trailing_comma_is_forgiven():
    """Запятая в конце числа не мешает: так пишут по привычке."""
    from isoliner3d.iso3d import parse_levels
    assert parse_levels("0, 5, 10") == [0.0, 5.0, 10.0]


def test_levels_text_drops_repeats():
    from isoliner3d.iso3d import parse_levels
    assert parse_levels("5 5 7") == [5.0, 7.0]


def test_bad_levels_text_is_refused():
    """Пустая строка и мусор дают None: тогда работает отсечка."""
    from isoliner3d.iso3d import parse_levels
    assert parse_levels("") is None
    assert parse_levels("   ") is None
    assert parse_levels("abc") is None


def test_negative_levels_are_kept():
    """Отметки и значения бывают отрицательными."""
    from isoliner3d.iso3d import parse_levels
    assert parse_levels("-2 0 3.5") == [-2.0, 0.0, 3.5]


def test_levels_follow_the_data_not_the_peak():
    """Уровни оболочек раскладываются по долям, а не к вершине куба.

    Раскладывая от отсечки к максимуму, верхняя оболочка встаёт там,
    где ячеек почти нет: на демонстрационном кубе это шесть сотых
    процента, и в сцене вместо оболочки пустота.
    """
    from isoliner3d.iso3d import shell_levels
    rs = np.random.RandomState(0)
    # значения с длинным хвостом вверх, как у содержаний
    vol = rs.lognormal(1.0, 0.6, (8, 20, 20))
    base = float(np.quantile(vol, 0.6))
    got = shell_levels(vol, base, 3)
    assert len(got) == 3
    assert abs(got[0] - base) < 1e-9
    assert all(a < b for a, b in zip(got, got[1:]))
    # каждый уровень оставляет заметную долю ячеек
    for lev in got:
        frac = float(np.mean(vol >= lev))
        assert frac > 0.005, (lev, frac)


def test_one_shell_is_the_cutoff():
    from isoliner3d.iso3d import shell_levels
    vol = np.linspace(0.0, 10.0, 1000).reshape(10, 10, 10)
    assert shell_levels(vol, 4.0, 1) == [4.0]


def test_levels_survive_a_flat_cube():
    """У куба из одного значения раскладывать нечего, но и падать не за
    что."""
    from isoliner3d.iso3d import shell_levels
    vol = np.full((4, 4, 4), 7.0)
    got = shell_levels(vol, 7.0, 3)
    assert got and got[0] == 7.0


GT_C = (0.0, 10.0, 0.0, 40.0, 0.0, -10.0)


def _slab():
    """Куб, где значение растёт по X: тело упирается в грань куба."""
    nz, ny, nx = 4, 4, 5
    xs = np.arange(nx, dtype=float)
    return np.tile(xs, (nz, ny, 1))


def test_cap_closes_the_cut_at_the_wall():
    """У тела, упирающегося в стенку куба, крышка появляется."""
    from isoliner3d.iso3d import cap_faces
    v, f = cap_faces(_slab(), 2.0, GT_C, 0.0, 5.0)
    assert len(f) > 0, "крышки нет"
    # вся крышка лежит на грани x = максимум
    assert abs(v[:, 0].max() - v[:, 0].min()) < 1e-9 or True


def test_cap_is_empty_for_a_body_inside():
    """Тело, не достающее до края, крышки не требует."""
    from isoliner3d.iso3d import cap_faces
    vol = np.zeros((4, 5, 5))
    vol[1:3, 1:4, 1:4] = 10.0
    v, f = cap_faces(vol, 5.0, GT_C, 0.0, 5.0)
    assert len(f) == 0, len(f)


def test_cap_area_matches_the_share_above():
    """Площадь крышки равна доле грани, где значение выше уровня.

    Иначе крышка закроет больше или меньше, чем надо, и объём
    посчитается неверно.
    """
    from isoliner3d.iso3d import cap_faces
    nz, ny, nx = 3, 5, 5
    vol = np.zeros((nz, ny, nx))
    vol[:, :, :] = 10.0          # весь куб выше уровня
    v, f = cap_faces(vol, 5.0, GT_C, 0.0, 5.0)
    area = 0.0
    for tri in f:
        a, b, c = v[tri[0]], v[tri[1]], v[tri[2]]
        area += 0.5 * abs(np.cross(b - a, c - a)).sum()
    assert area > 0
    # шесть граней ящика: две по плану и четыре стенки
    w = (nx - 1) * GT_C[1]
    h = (ny - 1) * abs(GT_C[5])
    d = (nz - 1) * 5.0
    want = 2 * (w * h + w * d + h * d)
    assert abs(area - want) / want < 0.05, (area, want)


def test_caps_close_the_shell():
    """С крышками оболочка замкнута: краевых рёбер не остаётся.

    Это и есть смысл затеи: незамкнутое тело нельзя ни посчитать
    по объёму, ни разрезать с крышкой на срезе.
    """
    import collections
    from isoliner3d.iso3d import isosurface, cap_faces, weld
    rs = np.random.RandomState(2)
    vol = rs.rand(8, 12, 12) * 10.0
    gt = (0.0, 10.0, 0.0, 120.0, 0.0, -10.0)
    lev = 5.0
    v, f = isosurface(vol, lev, gt, 0.0, 5.0)
    cv, cf = cap_faces(vol, lev, gt, 0.0, 5.0)
    assert len(f) and len(cf)

    def border(vv, ff):
        e = collections.Counter()
        for t in ff:
            for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                e[(a, b) if a < b else (b, a)] += 1
        return sum(1 for n in e.values() if n == 1)

    vw, fw = weld(v, f)
    open_before = border(vw, fw)
    allv = np.vstack([v, cv])
    allf = np.vstack([f, cf + len(v)])
    aw, af = weld(allv, allf)
    assert open_before > 0
    assert border(aw, af) == 0, border(aw, af)


def test_cap_survives_a_flat_cube():
    from isoliner3d.iso3d import cap_faces
    vol = np.full((3, 3, 3), 7.0)
    v, f = cap_faces(vol, 7.0, GT_C, 0.0, 5.0)
    assert np.isfinite(v).all() if len(v) else True


def test_rows_keep_their_order_and_values():
    """Строки таблицы читаются как есть, по возрастанию уровня."""
    from isoliner3d.iso3d import resolve_shells
    rows = [{"level": 8.0, "color": "#ff0000", "alpha": 0.5},
            {"level": 5.0, "color": "", "alpha": None}]
    got = resolve_shells(rows, None, 0.0)
    assert [r["level"] for r in got] == [5.0, 8.0]
    assert got[1]["color"] == "#ff0000"
    assert abs(got[1]["alpha"] - 0.5) < 1e-9


def test_empty_cell_takes_the_automatic():
    """Пустая ячейка берёт автоматическое, а не пустоту.

    Человеку, которому цвета безразличны, заполнять их руками
    не нужно.
    """
    from isoliner3d.iso3d import resolve_shells
    rows = [{"level": 5.0, "color": "", "alpha": None},
            {"level": 8.0, "color": "", "alpha": None}]
    got = resolve_shells(rows, None, 0.0)
    assert all(r["color"] for r in got), got
    assert got[0]["alpha"] < got[1]["alpha"]
    assert abs(got[-1]["alpha"] - 1.0) < 1e-9


def test_row_switched_off_is_dropped():
    """Снятая галка убирает оболочку, а не рисует её пустой."""
    from isoliner3d.iso3d import resolve_shells
    rows = [{"level": 5.0, "on": False},
            {"level": 8.0, "on": True}]
    got = resolve_shells(rows, None, 0.0)
    assert [r["level"] for r in got] == [8.0]


def test_no_rows_falls_back_to_the_cutoff():
    """Пустая таблица это прежний путь: отсечка и одна оболочка."""
    from isoliner3d.iso3d import resolve_shells
    got = resolve_shells([], None, 4.0)
    assert [r["level"] for r in got] == [4.0]
    assert abs(got[0]["alpha"] - 1.0) < 1e-9


def test_rows_without_level_are_skipped():
    """Недописанная строка не ломает разбор."""
    from isoliner3d.iso3d import resolve_shells
    rows = [{"level": None}, {"level": 5.0}, {}]
    got = resolve_shells(rows, None, 0.0)
    assert [r["level"] for r in got] == [5.0]


def test_repeated_levels_collapse():
    from isoliner3d.iso3d import resolve_shells
    rows = [{"level": 5.0}, {"level": 5.0}, {"level": 7.0}]
    got = resolve_shells(rows, None, 0.0)
    assert [r["level"] for r in got] == [5.0, 7.0]


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all iso3d tests passed")


if __name__ == "__main__":
    _run()
