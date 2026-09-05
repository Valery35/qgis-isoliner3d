# -*- coding: utf-8 -*-
"""Проверка опробования разрезов знаком.

Контур на разрезе лежит в вертикальной плоскости. Чтобы по нему
построить тело, плоскость опробуется знаком: внутри контура плюс,
снаружи минус. Ноль тогда и есть граница по построению.

Класть значение только на границу нельзя: вокруг пусто, и нулевой
уровень окажется где угодно. На эллипсоиде такая подмена дала объём
вчетверо с лишним больше настоящего.

Считается на голом NumPy, QGIS не нужен.
"""

import os
import sys

import numpy as np

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import section3d   # noqa: E402


def _square():
    """Квадрат в плоскости y = 0, от -10 до 10 по X и по Z."""
    return np.array([[-10.0, 0.0, -10.0], [10.0, 0.0, -10.0],
                     [10.0, 0.0, 10.0], [-10.0, 0.0, 10.0]])


def test_plane_of_a_ring():
    """Плоскость контура: направление вдоль и нормаль в плане."""
    got = section3d.ring_plane(_square())
    assert got is not None
    origin, along, normal = got
    assert abs(abs(along[0]) - 1.0) < 1e-9, along
    assert abs(along[2]) < 1e-9, "направление вдоль лежит в плане"
    assert abs(abs(normal[1]) - 1.0) < 1e-9, normal


def test_vertical_ring_is_refused():
    """У контура без протяжённости в плане плоскости нет.

    Такой контур это отрезок, и опробовать в нём нечего.
    """
    pts = np.array([[5.0, 5.0, 0.0], [5.0, 5.0, 10.0],
                    [5.0, 5.0, 20.0]])
    assert section3d.ring_plane(pts) is None


def test_sampling_marks_inside_and_outside():
    """Внутри контура плюс, снаружи минус."""
    pts, vals = section3d.sample_ring(_square(), step=2.0, pad=6.0)
    assert len(pts) == len(vals)
    assert vals.max() > 0 and vals.min() < 0
    inside = pts[vals > 0]
    assert np.abs(inside[:, 0]).max() <= 10.0 + 1e-9
    assert np.abs(inside[:, 2]).max() <= 10.0 + 1e-9
    assert (vals < 0).sum() > 0, "снаружи не опробовано"


def test_sampling_stays_in_the_plane():
    """Точки лежат в плоскости контура, а не рассыпаны в объёме."""
    pts, _v = section3d.sample_ring(_square(), step=2.0, pad=6.0)
    assert np.abs(pts[:, 1]).max() < 1e-9


def test_pad_widens_the_outside():
    """Запас наружу расширяет область минусов, а не тела."""
    a, va = section3d.sample_ring(_square(), step=2.0, pad=2.0)
    b, vb = section3d.sample_ring(_square(), step=2.0, pad=20.0)
    assert (vb < 0).sum() > (va < 0).sum()
    assert abs((va > 0).sum() - (vb > 0).sum()) <= 2


def test_step_controls_the_count():
    """Шаг опробования задаёт густоту, а не форму."""
    a, _ = section3d.sample_ring(_square(), step=4.0, pad=4.0)
    b, _ = section3d.sample_ring(_square(), step=2.0, pad=4.0)
    # ровно вчетверо не выйдет: по вертикали шаг свой, от мощности
    assert len(b) > 1.5 * len(a), (len(a), len(b))


def _bent_fence():
    """Забор по ломаной линии: на восток, потом на север."""
    spine = [(0.0, 0.0), (400.0, 0.0), (800.0, 0.0),
             (800.0, 400.0), (800.0, 800.0)]
    top = [(x, y, -95.0) for x, y in spine]
    bot = [(x, y, -105.0) for x, y in spine]
    return np.array(top + bot[::-1])


def test_bent_section_unfolds_along_the_path():
    """Забор по ломаной разворачивается по пути, а не проекцией.

    Проекция на одно прямое направление складывает изогнутый контур
    сам на себя: внутри оказываются две точки из восьмисот, максимум
    ровно ноль, и тела не выходит.
    """
    pts, vals = section3d.sample_ring(_bent_fence(), step=20.0,
                                      pad=100.0)
    n_in = int((vals > 0).sum())
    assert n_in > 30, n_in
    assert vals.max() > 1.0, vals.max()


def test_straight_section_still_works():
    """Прямой разрез не сломался от правки для ломаного."""
    pts, vals = section3d.sample_ring(_square(), step=2.0, pad=6.0)
    assert (vals > 0).sum() > 10
    inside = pts[vals > 0]
    assert np.abs(inside[:, 0]).max() <= 10.0 + 1e-9


def test_signed_distance_not_plus_minus():
    """Значение это расстояние до контура со знаком, а не плюс-минус.

    При одинаковом весе плюсов и минусов тонкий пласт пропадает:
    минусов вокруг него много больше, и они тянут поле вниз. Ноль
    тогда не переходится вовсе, и тела не выходит. Расстояние ставит
    ноль на границу по геометрии, а не по числу точек.
    """
    pts, vals = section3d.sample_ring(_square(), step=2.0, pad=8.0)
    assert len(set(np.round(vals, 3).tolist())) > 4, "значений мало"
    # у центра значение больше, чем у края
    d = np.hypot(pts[:, 0], pts[:, 2])
    inner = vals[d < 3.0]
    edge = vals[(d > 8.0) & (d < 11.0)]
    assert inner.max() > edge.max(), (inner.max(), edge.max())


def test_sign_still_marks_inside_and_outside():
    pts, vals = section3d.sample_ring(_square(), step=2.0, pad=8.0)
    # строго внутри плюс, строго снаружи минус; на самом контуре ноль,
    # и это верно: там и проходит граница
    deep = (np.abs(pts[:, 0]) < 9.0) & (np.abs(pts[:, 2]) < 9.0)
    out = (np.abs(pts[:, 0]) > 11.0) | (np.abs(pts[:, 2]) > 11.0)
    assert (vals[deep] > 0).all()
    assert (vals[out] < 0).all()


def test_thin_body_survives_the_fit():
    """Тонкий пласт даёт ноль в кубе, а не тонет в минусах."""
    from isoliner3d import mba
    rings = []
    for y0 in (-600.0, 0.0, 600.0):
        t = np.linspace(0, 1, 40)
        top = np.column_stack([-1200 + 2400 * t, np.full(40, y0),
                               np.full(40, -99.0)])
        bot = np.column_stack([1200 - 2400 * t, np.full(40, y0),
                               np.full(40, -101.0)])
        rings.append(np.vstack([top, bot]))
    P, V = [], []
    for r in rings:
        p, v = section3d.sample_ring(r, step=15.0, pad=75.0)
        P.append(p)
        V.append(v)
    P, V = np.vstack(P), np.concatenate(V)
    lat = mba.fit(P, V, lo=[-1300, -700, -200], hi=[1300, 700, 0],
                  grid=(11, 6, 2), levels=5)
    got = mba.evaluate(lat, P)
    assert got.max() > 0, got.max()


def test_bed_is_sampled_against_all_its_rings():
    """Знак считается по всем кускам пласта разом, а не по одному.

    Пласт нарезан на куски, и минусы вокруг одного ложатся туда, где
    соседний даёт плюс. На падающем пласте соседи затирают друг друга,
    и плюсов в слое решётки остаётся три процента: ноль в кубе
    не встречается вовсе.
    """
    # два куска одного пласта, разнесённые по падению
    a = np.array([[0.0, 0.0, 0.0], [100.0, 0.0, 0.0],
                  [100.0, 0.0, -6.0], [0.0, 0.0, -6.0]])
    b = np.array([[100.0, 0.0, -30.0], [200.0, 0.0, -30.0],
                  [200.0, 0.0, -36.0], [100.0, 0.0, -36.0]])
    pts, vals = section3d.sample_bed([a, b], step=5.0, pad=25.0)
    assert len(pts) == len(vals)
    n_in = int((vals > 0).sum())
    assert n_in > 20, n_in
    # точка в середине второго куска обязана быть плюсом
    mid = np.array([[150.0, 0.0, -33.0]])
    d = np.hypot(pts[:, 0] - 150.0, pts[:, 2] + 33.0)
    assert vals[np.argmin(d)] > 0, vals[np.argmin(d)]


def _fence(y0, ztop, zbot, x0=0.0, x1=100.0):
    """Кусок забора: верх вперёд, низ назад, замыкающая точка."""
    top = [(x0, y0, ztop), (x1, y0, ztop)]
    bot = [(x1, y0, zbot), (x0, y0, zbot)]
    return np.array(top + bot + [top[0]])


def test_roof_and_floor_of_a_hand_drawn_outline():
    """Кровля и подошва берутся как верх и низ контура в каждой точке.

    Делить кольцо пополам можно только у забора, где верх идёт
    вперёд, а низ назад. У нарисованного от руки контура порядок
    вершин произволен, и половинки оказываются вперемешку: мощность
    выходит нулевой там, где пласт есть.
    """
    # контур пласта, обведённый по чертежу: верх неровный, низ тоже,
    # и половинки не равны по числу вершин
    ring = np.array([[10.0, 0.0, -4.0], [30.0, 0.0, -3.2],
                     [55.0, 0.0, -3.6], [90.0, 0.0, -4.4],
                     [70.0, 0.0, -12.0], [20.0, 0.0, -11.0]])
    top, bot = section3d.roof_and_floor([ring])
    assert len(top) == len(bot) and len(top) > 3
    m = top[:, 2] - bot[:, 2]
    # у краёв контур сходится в точку, и мощность там мала - это
    # верно; смотрим на середину
    assert m.min() > 0.0, m.min()
    assert np.median(m) > 5.0, np.median(m)
    assert top[:, 2].max() <= -3.0 + 1e-6
    assert bot[:, 2].min() >= -13.0 - 1e-6


def test_roof_and_floor_are_split():
    """Кольцо разбирается на кровлю и подошву.

    У пласта есть кровля и подошва, и каждая - обычная поверхность.
    Интерполировать надо их, а не тело целиком: в объёме между
    разрезами данных нет, коэффициент остаётся нулевым, а ноль там
    и есть граница - «нет данных» и «здесь граница» становятся одним
    и тем же.
    """
    top, bot = section3d.roof_and_floor([_fence(0.0, -10.0, -16.0)])
    assert len(top) == len(bot) > 3, (len(top), len(bot))
    assert np.allclose(top[:, 2], -10.0)
    assert np.allclose(bot[:, 2], -16.0)
    # план у кровли и подошвы один: они берутся в одних точках
    assert np.allclose(top[:, 0], bot[:, 0])
    assert np.allclose(top[:, 1], bot[:, 1])


def test_roof_stays_above_the_floor():
    """Кровля выше подошвы, как бы ни было записано кольцо."""
    flipped = _fence(0.0, -16.0, -10.0)      # записано наоборот
    top, bot = section3d.roof_and_floor([flipped])
    assert (top[:, 2] >= bot[:, 2]).all()


def test_roof_and_floor_of_nothing():
    top, bot = section3d.roof_and_floor([])
    assert len(top) == 0 and len(bot) == 0


def test_crossing_disagreement_is_measured():
    """Расхождение разрезов на пересечении считается, а не молчит.

    Если границу пласта на двух разрезах провели по-разному,
    интерполяция усреднит расхождение молча, и выйдет модель, которая
    выглядит правдоподобно и неверна.
    """
    pts = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 0.0],
                    [50.0, 50.0, -10.0], [50.0, 50.0, -10.0]])
    vals = np.array([1.0, 1.0, 1.0, -1.0])
    n_bad, n_pairs = section3d.crossing_conflicts(pts, vals, snap=1.0)
    assert n_pairs >= 2, n_pairs
    assert n_bad == 1, n_bad


def test_no_conflicts_when_sections_agree():
    pts = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]])
    vals = np.array([1.0, 1.0])
    n_bad, _n = section3d.crossing_conflicts(pts, vals, snap=1.0)
    assert n_bad == 0


def _roof(x, y):
    """Кровля пласта в шурфе: -250 м с небольшим уклоном."""
    return -250.0 + 0.010 * np.asarray(x) - 0.005 * np.asarray(y)


def _pit_rings(thick=3.0):
    """Контуры пласта на четырёх стенках шурфа 60 на 40.

    Так и приходят настоящие данные: замеры лежат по периметру,
    внутри нет ни одной точки.
    """
    corners = [(0.0, 0.0), (60.0, 0.0), (60.0, 40.0), (0.0, 40.0)]
    rings = []
    for i in range(4):
        ax, ay = corners[i]
        bx, by = corners[(i + 1) % 4]
        t = np.linspace(0.0, 1.0, 41)
        xs, ys = ax + (bx - ax) * t, ay + (by - ay) * t
        zt = _roof(xs, ys)
        rings.append(np.vstack([
            np.column_stack([xs, ys, zt]),
            np.column_stack([xs[::-1], ys[::-1], zt[::-1] - thick])]))
    return rings


def _pit_surface(center):
    """Кровля по контурам шурфа тем же путём, что и в 2.08."""
    from isoliner3d import mba
    top, _bot = section3d.roof_and_floor(_pit_rings())
    cell = 60.0 / 200.0
    nx, ny = int(np.ceil(60.0 / cell)), int(np.ceil(40.0 / cell))
    gt = (0.0, cell, 0.0, 0.0 + ny * cell, 0.0, -cell)
    lat = mba.fit(top[:, :2], top[:, 2], lo=[0.0, 0.0], hi=[60.0, 40.0],
                  grid=(2, 2), levels=7, center=center)
    surf = mba.surface_on_grid(lat, gt, nx, ny)
    gx = 0.0 + cell * (np.arange(nx) + 0.5)
    gy = (0.0 + ny * cell) - cell * (np.arange(ny) + 0.5)
    mx, my = np.meshgrid(gx, gy)
    return surf, _roof(mx, my), top


def test_pit_roof_stays_where_the_contours_put_it():
    """Кровля по контурам шурфа: горбов и ям быть не должно.

    Замеры лежат только по периметру, разброс отметок восемьдесят
    сантиметров. Без снятия тренда поверхность уходила на четырнадцать
    метров, и число уровней этого не меняло: коэффициент решётки
    линеен по значению, и ошибка росла вместе с самой отметкой -250.
    """
    surf, true, top = _pit_surface("plane")
    assert abs(top[:, 2].max() - top[:, 2].min()) < 1.0
    off = np.abs(surf - true).max()
    assert off < 0.1, "отклонение от истинной кровли %.2f м" % off


def test_absolute_marks_without_centering_are_the_old_trouble():
    """Тот же расчёт без снятия тренда обязан быть заметно хуже.

    Тест держит причину: если однажды покажется, что снятие тренда
    ничего не даёт, сюда и надо смотреть.
    """
    surf, true, _top = _pit_surface(None)
    assert np.abs(surf - true).max() > 5.0


def test_mask_leaves_the_grid_only_where_it_is_told():
    """Обрезка маской: за её пределами грида быть не должно.

    Между разрезами данных нет, и поверхность там идёт туда, куда её
    провела интерполяция. Маска и говорит, докуда этому верить: без неё
    тело живёт на весь охват контуров, в том числе там, где ни одного
    замера нет.
    """
    from isoliner3d.mesh3d import polygon_mask
    surf, _true, _top = _pit_surface("plane")
    ny, nx = surf.shape
    cell = 60.0 / 200.0
    gt = (0.0, cell, 0.0, 0.0 + ny * cell, 0.0, -cell)
    ring = [(5.0, 5.0), (30.0, 5.0), (30.0, 35.0), (5.0, 35.0)]
    keep = polygon_mask([ring], gt, (ny, nx))
    out = np.where(keep, surf, np.nan)
    assert np.isfinite(out).sum() == int(keep.sum())
    assert 0 < int(keep.sum()) < surf.size
    assert not np.isfinite(out[~keep]).any()


def _two_beds(t0=0.0, t1=1.0):
    """Два пласта, у которых подошва верхнего и кровля нижнего - одно."""
    def zc(x, y):
        return (-252.0 + 0.006 * np.asarray(x) - 0.004 * np.asarray(y)
                + 0.4 * np.sin(np.asarray(x) / 13.0))

    def wall(a, b, zt, zb, s0, s1):
        t = np.linspace(s0, s1, 41)
        xs = a[0] + (b[0] - a[0]) * t
        ys = a[1] + (b[1] - a[1]) * t
        return np.vstack([
            np.column_stack([xs, ys, zt(xs, ys)]),
            np.column_stack([xs[::-1], ys[::-1],
                             zb(xs[::-1], ys[::-1])])])
    cor = [(0.0, 0.0), (60.0, 0.0), (60.0, 40.0), (0.0, 40.0)]
    up, low = [], []
    for i in range(4):
        a, b = cor[i], cor[(i + 1) % 4]
        up.append(wall(a, b, lambda x, y: zc(x, y) + 3.0, zc, 0.0, 1.0))
        low.append(wall(a, b, zc, lambda x, y: zc(x, y) - 2.0, t0, t1))
    _t, bot_up = section3d.roof_and_floor(up)
    top_low, _b = section3d.roof_and_floor(low)
    return bot_up, top_low


def _wall_ring(spans, x0=1425947.0, y=410388.0, along_y=False):
    """Прямоугольный контур на стенке: (s, z) по углам."""
    if along_y:
        return np.array([[x0, y + s, z] for s, z in spans], dtype=float)
    return np.array([[x0 + s, y, z] for s, z in spans], dtype=float)


def test_lens_inside_a_bed_does_not_touch_the_boundary():
    """Линза внутри пласта не должна тянуть кровлю к подошве.

    Контуры одного пласта опрашивались каждый сам по себе, и пробы
    сваливались в одну кучу: в облаке кровли оказывались и настоящая
    кровля 2.30, и верх линзы 2.20. Интерполяция получала в одной
    точке два ответа и проводила поверхность между ними.
    """
    main = _wall_ring([(0.0, 2.30), (2.0, 2.30), (2.0, 2.00), (0.0, 2.00)])
    lens = _wall_ring([(0.6, 2.20), (1.4, 2.20), (1.4, 2.10), (0.6, 2.10)])
    top, bot, whose = section3d.roof_and_floor([main, lens],
                                               with_ring=True)
    assert len(set(whose.tolist())) == 1, "одна плоскость разреза"
    assert abs(top[:, 2].min() - 2.30) < 1e-9, top[:, 2].min()
    assert abs(bot[:, 2].max() - 2.00) < 1e-9, bot[:, 2].max()


def test_lens_lands_where_it_is_drawn():
    """Линза влияет только на свой участок борта, а не на весь.

    Развёртка у каждого кольца своя: путь считается от его первой
    вершины, и у линзы, нарисованной в середине, ноль приходится
    на её начало. Сравнивая кольца в таких координатах, линзу кладёшь
    не на её место, и подошва уезжает там, где линзы нет вовсе.
    """
    main = _wall_ring([(0.0, 2.30), (20.0, 2.30), (20.0, 2.00),
                       (0.0, 2.00)])
    lens = _wall_ring([(12.0, 2.20), (16.0, 2.20), (16.0, 2.10),
                       (12.0, 2.10)])
    top, bot = section3d.roof_and_floor([main, lens])
    s = top[:, 0] - 1425947.0
    far = s < 8.0
    assert far.any()
    assert np.allclose(top[far, 2], 2.30, atol=1e-9)
    assert np.allclose(bot[far, 2], 2.00, atol=1e-9), bot[far, 2].min()
    # и на самой линзе граница тоже внешняя
    assert abs(top[:, 2].max() - 2.30) < 1e-9
    assert abs(bot[:, 2].min() - 2.00) < 1e-9


def test_two_walls_stay_two_planes():
    """Контуры разных разрезов не сливаются: там расхождение это данные."""
    a = _wall_ring([(0.0, 2.30), (2.0, 2.30), (2.0, 2.00), (0.0, 2.00)])
    b = _wall_ring([(0.0, 2.40), (2.0, 2.40), (2.0, 2.10), (0.0, 2.10)],
                   along_y=True)
    _t, _b, whose = section3d.roof_and_floor([a, b], with_ring=True)
    assert len(set(whose.tolist())) == 2


def test_a_bed_twice_along_one_wall_keeps_both_pieces():
    """Пласт, выходящий на стенке в двух местах, остаётся двумя кусками.

    Внешняя граница берётся только там, где контуры перекрываются
    в плане. Иначе разрыв между кусками затянулся бы телом.
    """
    left = _wall_ring([(0.0, 2.30), (0.8, 2.30), (0.8, 2.00), (0.0, 2.00)])
    right = _wall_ring([(1.2, 2.35), (2.0, 2.35), (2.0, 2.05), (1.2, 2.05)])
    top, bot = section3d.roof_and_floor([left, right])
    s = top[:, 0] - 1425947.0
    gap = (s > 0.85) & (s < 1.15)
    assert not gap.any(), "в разрыве проб быть не должно"
    assert len(top) == len(bot) and len(top) > 10


def test_convex_hull_ring_wraps_the_points():
    """Оболочка проб: замкнутое кольцо по крайним точкам."""
    pts = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 8.0], [0.0, 8.0],
                    [5.0, 4.0], [2.0, 1.0]])
    ring = section3d.convex_hull_ring(pts)
    assert ring[0] == ring[-1], "кольцо должно быть замкнутым"
    assert len(ring) == 5, ring
    inside = {(5.0, 4.0), (2.0, 1.0)}
    assert not inside & set(ring[:-1]), "внутренние точки в оболочку не идут"


def test_convex_hull_ring_refuses_a_line():
    """Точки на одной прямой площади не ограничивают."""
    pts = np.column_stack([np.linspace(0, 10, 9), np.zeros(9)])
    assert section3d.convex_hull_ring(pts) == []


def test_own_hull_limits_a_bed_with_fewer_sections():
    """Пласт с меньшим числом разрезов занимает меньшую площадь.

    Иначе интерполяция растягивает его на весь охват участка, где
    его никто не наблюдал.
    """
    def wall(a, b, z):
        t = np.linspace(0.0, 1.0, 21)
        xs = a[0] + (b[0] - a[0]) * t
        ys = a[1] + (b[1] - a[1]) * t
        return np.vstack([
            np.column_stack([xs, ys, np.full(21, z)]),
            np.column_stack([xs[::-1], ys[::-1], np.full(21, z - 1.0)])])

    cor = [(0.0, 0.0), (60.0, 0.0), (60.0, 40.0), (0.0, 40.0)]
    four = [wall(cor[i], cor[(i + 1) % 4], 2.0) for i in range(4)]
    two = four[:2]

    def area(rings_):
        top, bot = section3d.roof_and_floor(rings_)
        ring = section3d.convex_hull_ring(np.vstack([top, bot]))
        a = np.asarray(ring[:-1])
        x, y = a[:, 0], a[:, 1]
        return abs(float(np.dot(x, np.roll(y, -1))
                         - np.dot(y, np.roll(x, -1))) / 2.0)

    assert area(two) < 0.75 * area(four), (area(two), area(four))


def test_own_hull_cannot_make_a_dent():
    """Оболочка выпукла, и вогнутого ограничения из неё не выйдет.

    У пласта, встреченного на трёх стенках из четырёх, оболочка
    накроет весь прямоугольник: середина внутри неё лежит. Для таких
    случаев и нужна маска полигоном на пласт, поэтому обе возможности
    в инструменте есть.
    """
    ring = section3d.convex_hull_ring(
        np.array([[0.0, 0.0], [60.0, 0.0], [60.0, 40.0], [0.0, 40.0]]))
    a = np.asarray(ring[:-1])
    x, y = a[:, 0], a[:, 1]
    area = abs(float(np.dot(x, np.roll(y, -1))
                     - np.dot(y, np.roll(x, -1))) / 2.0)
    assert abs(area - 2400.0) < 1e-6, area


def test_a_lone_point_holds_the_surface():
    """Одиночный замер в пустом месте поверхность держит.

    Взвешивать его не надо: там, где сечений нет, спорить с ним
    некому, и мультисеточная подгонка идёт по нему. А рядом с сечением
    сотня вершин профиля перевешивает одну точку - это и правильно,
    но человеку надо об этом СКАЗАТЬ, потому что молчаливое
    игнорирование замера выглядит как ошибка.
    """
    from isoliner3d import mba
    from isoliner3d.mesh3d import sample_bilinear

    def design(x, y):
        d = np.abs(np.asarray(y) - 100.0)
        return np.where(d <= 8.0, 6.0 - 0.002 * np.asarray(x),
                        np.maximum(6.0 - 0.002 * np.asarray(x)
                                   - (d - 8.0) / 2.0, 0.0))

    prof = []
    for k in range(11):
        if k == 5:                      # в середине профиля нет
            continue
        ys = np.linspace(80.0, 120.0, 41)
        xs = np.full_like(ys, k * 100.0)
        prof.append(np.column_stack([xs, ys, design(xs, ys)]))
    pts = np.vstack(prof)
    x0, x1, y0, y1, cell = 0.0, 1000.0, 80.0, 120.0, 1.0
    nx, ny = int((x1 - x0) / cell), int((y1 - y0) / cell)
    gt = (x0, cell, 0.0, y0 + ny * cell, 0.0, -cell)

    def build(p):
        lat = mba.fit(p[:, :2], p[:, 2], lo=[x0, y0], hi=[x1, y1],
                      grid=(2, 2), levels=7, center="plane")
        return mba.surface_on_grid(lat, gt, nx, ny)

    px, py = 500.0, 100.0
    shot = float(design(px, py)) + 1.5
    s = build(np.vstack([pts, [[px, py, shot]]]))
    got = float(sample_bilinear(s, gt, np.array([px]), np.array([py]))[0])
    assert abs(got - shot) < 0.15, (got, shot)

    # а у профиля тот же замер перевешен, и это надо мерить
    px2, py2 = 300.0, 100.0
    shot2 = float(design(px2, py2)) + 1.5
    s2 = build(np.vstack([pts, [[px2, py2, shot2]]]))
    got2 = float(sample_bilinear(s2, gt, np.array([px2]),
                                 np.array([py2]))[0])
    assert abs(got2 - shot2) > 0.5, (got2, shot2)


def test_contact_of_two_beds_is_recognised():
    """Подошва верхнего и кровля нижнего опознаются как один контакт.

    Пробы двух пластов ложатся вдоль одной линии, но в разные места:
    шаг опробования у каждого контура свой. Поэтому контакт ищется
    сведением к сетке, а не поиском совпавших точек.
    """
    bot_up, top_low = _two_beds()
    joint = np.vstack([bot_up, top_low])
    side = np.concatenate([np.zeros(len(bot_up)), np.ones(len(top_low))])
    snap = max(section3d.sample_step(bot_up), 0.3)
    places, worst, where = section3d.crossing_spread(
        joint, joint[:, 2], snap=snap, owner=side)
    assert where is not None and len(where) == 2
    assert places > 0, "контакт не найден вовсе"
    assert worst < 0.01, worst


def test_glued_contact_gives_one_and_the_same_surface():
    """Склеенный контакт даёт две одинаковые границы, без щели.

    Порознь построенные поверхности между разрезами расходятся,
    и в модели между пластами встаёт щель или нахлёст, которых
    на разрезе нет.
    """
    from isoliner3d import mba
    bot_up, top_low = _two_beds(t0=0.06)
    cell = 0.3
    nx, ny = 200, 134
    gt = (0.0, cell, 0.0, ny * cell, 0.0, -cell)

    def surf(pts):
        lat = mba.fit(pts[:, :2], pts[:, 2], lo=[0.0, 0.0],
                      hi=[60.0, 40.0], grid=(2, 2), levels=7,
                      center="plane")
        return mba.surface_on_grid(lat, gt, nx, ny)

    s_up, s_low = surf(bot_up), surf(top_low)
    apart = float(np.abs(s_up - s_low).max())
    assert apart > 0.0, "порознь границы обязаны разойтись хоть немного"
    # склеенная граница строится один раз по обоим наборам точек и идёт
    # между ними, а не куда-то в сторону
    one = surf(np.vstack([bot_up, top_low]))
    assert float(np.abs(one - s_up).max()) <= 2.0 * apart
    assert float(np.abs(one - s_low).max()) <= 2.0 * apart
    # инструмент кладёт её в обе полосы, поэтому щель обращается в ноль
    assert float(np.abs(one - one).max()) == 0.0


def test_crossing_spread_measures_disagreement_in_metres():
    """Расхождение отметок считается размахом, а не сменой знака.

    У кровли на -250 м знак у всех проб один, и знаковая проверка
    молчала бы, как бы разрезы ни спорили.
    """
    pts = np.array([[0.0, 0.0], [0.0, 0.0], [50.0, 50.0], [50.0, 50.0]])
    vals = np.array([-250.0, -248.5, -260.0, -260.0])
    places, worst, where = section3d.crossing_spread(
        pts, vals, snap=1.0, owner=[0, 1, 0, 1])
    # адрес места нужен человеку: с одним числом идти некуда
    assert abs(where[0] - 0.0) < 1e-9 and abs(where[1] - 0.0) < 1e-9
    assert places == 2, places
    assert abs(worst - 1.5) < 1e-9, worst


def test_two_probes_of_one_section_are_not_a_crossing():
    """Соседние пробы одного разреза сходиться и не должны."""
    pts = np.array([[0.0, 0.0], [0.1, 0.0]])
    places, worst, _where = section3d.crossing_spread(
        pts, np.array([-250.0, -251.0]), snap=1.0, owner=[0, 0])
    assert places == 0 and worst == 0.0


def test_pit_corners_are_checked():
    """Углы шурфа: зарисовки соседних стенок обязаны сойтись.

    Одной сеткой сведения углы терялись целиком - пробы двух стенок
    ложились в соседние ячейки, и проверка молчала на любых данных.
    """
    ok = _pit_crossing(0.0)
    assert ok[0] >= 1, "угол не найден вовсе"
    assert ok[1] < 0.05, ok[1]
    bad = _pit_crossing(1.5)
    assert bad[0] >= 1
    assert abs(bad[1] - 1.5) < 0.05, bad[1]


def _pit_crossing(shift):
    """Расхождение по кровле в шурфе, одна стенка поднята на shift."""
    rings = _pit_rings()
    rings[0] = rings[0] + np.array([0.0, 0.0, shift])
    top, _bot, whose = section3d.roof_and_floor(rings, with_ring=True)
    snap = max(section3d.sample_step(top), 0.3)
    places, worst, _where = section3d.crossing_spread(
        top, top[:, 2], snap=snap, owner=whose)
    return places, worst


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all section3d tests passed")


if __name__ == "__main__":
    _run()
