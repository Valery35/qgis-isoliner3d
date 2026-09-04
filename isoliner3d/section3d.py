# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Опробование контуров на разрезах: из зарисовки в точки со знаком.

Геолог рисует границы пластов на разрезе. Контур лежит в вертикальной
плоскости и имеет настоящие координаты, значит это уже данные в объёме -
не хватает только перевода в вид, понятный интерполяции.

Перевод такой: плоскость разреза опробуется знаком. Внутри контура
плюс, снаружи минус. Нулевой уровень тогда и есть граница тела
по построению, а между разрезами он перетекает плавно.

Класть значение только на границу контура нельзя. Вокруг пусто,
интерполяция даёт единицу у контура и ноль вдали, и нулевой уровень
оказывается где угодно: на проверочном эллипсоиде такая подмена дала
объём вчетверо с лишним больше настоящего.

Считается на голом NumPy.
"""

import numpy as np


def ring_plane(pts):
    """Плоскость контура: начало, направление вдоль и нормаль.

    Разрез вертикален, поэтому плоскость задаётся направлением
    в плане. Оно берётся по наибольшему размаху точек, а не
    по первому ребру: у ломаной первое ребро может смотреть куда
    угодно.

    Возвращает None у контура без протяжённости в плане - такой
    контур это отрезок, опробовать в нём нечего.
    """
    p = np.asarray(pts, dtype=float)
    if len(p) < 3:
        return None
    xy = p[:, :2]
    d = xy.max(axis=0) - xy.min(axis=0)
    if float(np.hypot(*d)) < 1e-9:
        return None
    # направление вдоль: от самой дальней пары в плане
    i0 = int(np.argmin(xy[:, 0] * d[0] + xy[:, 1] * d[1]))
    i1 = int(np.argmax(xy[:, 0] * d[0] + xy[:, 1] * d[1]))
    v = xy[i1] - xy[i0]
    ln = float(np.hypot(*v))
    if ln < 1e-9:
        return None
    along = np.array([v[0] / ln, v[1] / ln, 0.0])
    normal = np.array([-along[1], along[0], 0.0])
    return p[i0].copy(), along, normal


def spine_of(pts):
    """Линия разреза в плане: ход вперёд, без обратного пути.

    Забор идёт по линии и возвращается обратно, поэтому в плане путь
    проходит её дважды. Первая половина и есть линия.
    """
    p = np.asarray(pts, dtype=float)
    xy = p[:, :2]
    step = np.hypot(*(xy[1:] - xy[:-1]).T)
    walk = np.concatenate([[0.0], np.cumsum(step)])
    total = float(walk[-1])
    if total <= 0.0:
        return xy[:1], np.zeros(1)
    keep = walk <= total * 0.5 + 1e-9
    line = xy[keep]
    at = walk[keep]
    # Повторы по пути делают опорную сетку двузначной: разные места
    # ложатся в одно, и значения в них спорят между собой.
    if len(at) > 1:
        good = np.concatenate([[True], np.diff(at) > 1e-9])
        line, at = line[good], at[good]
    if len(line) < 2:
        return xy, walk
    return line, at


def along_spine(line, at, s):
    """Точка в плане по пути вдоль линии.

    Сетку опробования нельзя класть на прямую плоскость: у ломаного
    разреза она уедет мимо самой линии, и опробование окажется
    не там, где рисовал геолог.
    """
    line = np.asarray(line, dtype=float)
    at = np.asarray(at, dtype=float)
    if len(line) < 2:
        return np.repeat(line[:1], len(s), axis=0)
    x = np.interp(s, at, line[:, 0])
    y = np.interp(s, at, line[:, 1])
    # За концами линию продолжаем, а не прижимаем точки к краю:
    # прижатые точки сваливаются в одно место, и запас наружу
    # перестаёт быть запасом.
    # Направление всегда наружу от конца: взяв его наоборот, точки
    # за началом лягут внутрь линии, и в одном месте окажутся две
    # разные точки с разными знаками.
    for side, i0, i1 in ((s < at[0], 0, 1), (s > at[-1], -1, -2)):
        if not side.any():
            continue
        d = line[i1] - line[i0] if i0 == 0 else line[i0] - line[i1]
        ln = float(np.hypot(*d))
        if ln < 1e-12:
            continue
        over = s[side] - at[i0]
        x[side] = line[i0, 0] + d[0] / ln * over
        y[side] = line[i0, 1] + d[1] / ln * over
    return np.column_stack([x, y])


def unfold(pts, origin, along):
    """Путь вдоль линии разреза для каждой вершины контура.

    Проекцией на одно прямое направление изогнутый разрез не развернуть:
    на повороте контур складывается сам на себя, внутри не остаётся
    почти ни одной точки, и тела не выходит.

    Забор идёт по линии вперёд и возвращается обратно, поэтому путь
    в плане проходит её дважды. Первая половина пути это ход вперёд,
    вторая - тот же ход назад, и её отсчитываем от конца.

    У прямого контура ответ совпадает с проекцией, так что случай
    один на оба.
    """
    p = np.asarray(pts, dtype=float)
    xy = p[:, :2]
    step = np.hypot(*(xy[1:] - xy[:-1]).T)
    walk = np.concatenate([[0.0], np.cumsum(step)])
    total = float(walk[-1])
    if total <= 0.0:
        return (p - origin) @ along
    half = total * 0.5
    out = np.where(walk <= half, walk, total - walk)
    # Прямой контур: путь и проекция дают одно и то же с точностью
    # до сдвига. Если развёртка вышла вырожденной, берём проекцию.
    if float(np.ptp(out)) < 1e-9:
        return (p - origin) @ along
    return out


def _inside(poly_s, poly_z, s, z):
    """Точки внутри многоугольника, лучевым способом.

    Многоугольник задан в плоскости разреза: путь вдоль линии
    и отметка.
    """
    n = len(poly_s)
    res = np.zeros(len(s), dtype=bool)
    j = n - 1
    for i in range(n):
        si, zi = poly_s[i], poly_z[i]
        sj, zj = poly_s[j], poly_z[j]
        hit = (zi > z) != (zj > z)
        if hit.any():
            dz = zj - zi
            t = np.where(np.abs(dz) < 1e-30, 0.0, (z - zi) / dz)
            cross = si + t * (sj - si)
            res ^= hit & (s < cross)
        j = i
    return res


def sample_ring(pts, step=10.0, pad=None):
    """Опробовать плоскость контура знаком.

    `step` - шаг сетки опробования в метрах, `pad` - запас наружу
    от контура. Запас нужен: без минусов вокруг интерполяция не знает,
    где тело кончается, и растянет его до края куба.

    Возвращает точки (N, 3) и значения: плюс внутри, минус снаружи.
    """
    got = ring_plane(pts)
    if got is None:
        return np.zeros((0, 3)), np.zeros(0)
    origin, along, _normal = got
    p = np.asarray(pts, dtype=float)
    ps = unfold(p, origin, along)
    pz = p[:, 2]
    step = max(float(step), 1e-6)
    if pad is None:
        pad = step * 3.0
    pad = float(pad)
    # Шаг по вертикали берётся от мощности контура, а не от шага
    # по горизонтали. Пласт бывает тоньше шага в плане, и тогда ни
    # одна точка не попадает внутрь: все ложатся ровно на границу,
    # где значение ноль. В журнале это выглядит как «куб доходит
    # до -0.000», а тела не выходит вовсе.
    thick = float(pz.max() - pz.min())
    stepz = min(step, thick / 6.0) if thick > 0 else step
    stepz = max(stepz, 1e-6)
    ss = np.arange(ps.min() - pad, ps.max() + pad + step, step)
    # Мелкий шаг нужен только у самого пласта. Растянув его на весь
    # запас, получишь десятки тысяч точек там, где и так всё минус.
    near = np.arange(pz.min() - stepz, pz.max() + 2 * stepz, stepz)
    far = np.arange(pz.min() - pad, pz.max() + pad + step, step)
    zz = np.unique(np.concatenate([near, far]))
    S, Z = np.meshgrid(ss, zz)
    S, Z = S.ravel(), Z.ravel()
    ins = _inside(ps, pz, S, Z)
    # Значение это расстояние до контура со знаком, а не плюс-минус.
    # При одинаковом весе плюсов и минусов тонкий пласт пропадает:
    # минусов вокруг него много больше, и они тянут поле вниз. Ноль
    # тогда не переходится вовсе. Расстояние ставит ноль на границу
    # по геометрии, а не по числу точек.
    d = _dist_to_ring(ps, pz, S, Z)
    d = np.minimum(d, pad)          # дальше запаса всё едино
    line, at = spine_of(p)
    xy = along_spine(line, at, S)
    xyz = np.column_stack([xy[:, 0], xy[:, 1], Z])
    return xyz, np.where(ins, d, -d)


def _dist_to_ring(poly_s, poly_z, s, z):
    """Расстояние от точек до ломаной контура, в плоскости разреза."""
    n = len(poly_s)
    best = np.full(len(s), np.inf)
    for i in range(n):
        j = (i + 1) % n
        ax, ay = poly_s[i], poly_z[i]
        bx, by = poly_s[j], poly_z[j]
        vx, vy = bx - ax, by - ay
        ln = vx * vx + vy * vy
        if ln < 1e-30:
            best = np.minimum(best, np.hypot(s - ax, z - ay))
            continue
        t = np.clip(((s - ax) * vx + (z - ay) * vy) / ln, 0.0, 1.0)
        best = np.minimum(best, np.hypot(s - (ax + t * vx),
                                         z - (ay + t * vy)))
    return best


def crossing_conflicts(pts, vals, snap=1.0):
    """Сколько раз разрезы разошлись в одной точке.

    Где разрезы пересекаются, границы пласта на них должны сойтись.
    Если на одном разрезе граница проведена выше, чем на другом,
    интерполяция усреднит расхождение молча, и выйдет модель, которая
    выглядит правдоподобно и неверна.

    Точки сводятся к сетке с шагом `snap`; в ячейке, где встретились
    и плюс, и минус, разрезы противоречат друг другу.

    Возвращает пару: сколько ячеек с расхождением и сколько ячеек
    с несколькими значениями вообще.
    """
    p = np.asarray(pts, dtype=float)
    v = np.asarray(vals, dtype=float)
    if not len(p):
        return 0, 0
    snap = max(float(snap), 1e-9)
    key = np.round(p / snap).astype(np.int64)
    _u, inv, cnt = np.unique(key, axis=0, return_inverse=True,
                             return_counts=True)
    many = cnt > 1
    if not many.any():
        return 0, 0
    lo = np.full(len(cnt), np.inf)
    hi = np.full(len(cnt), -np.inf)
    np.minimum.at(lo, inv, v)
    np.maximum.at(hi, inv, v)
    bad = many & (lo < 0) & (hi > 0)
    return int(bad.sum()), int(many.sum())


def convex_hull_ring(pts):
    """Выпуклая оболочка точек в плане, замкнутым кольцом.

    Пласт, встреченный на трёх стенках из четырёх, интерполяция
    растягивает на всю площадь охвата: за пределами своих разрезов его
    не наблюдали, и поверхность там - выдумка. Оболочка своих же проб
    и есть та область, где о пласте что-то известно.

    Обход Эндрю: сортировка и два прохода. Стороннего кода не нужно,
    а точек здесь тысячи, не миллионы.
    """
    p = np.unique(np.asarray(pts, dtype=float)[:, :2], axis=0)
    if len(p) < 3:
        return []
    p = p[np.lexsort((p[:, 1], p[:, 0]))]

    def half(seq):
        out = []
        for q in seq:
            while len(out) >= 2:
                a, b = out[-2], out[-1]
                if ((b[0] - a[0]) * (q[1] - a[1])
                        - (b[1] - a[1]) * (q[0] - a[0])) > 0:
                    break
                out.pop()
            out.append(q)
        return out

    hull = half(p)[:-1] + half(p[::-1])[:-1]
    if len(hull) < 3:
        return []
    ring = [(float(x), float(y)) for x, y in hull]
    ring.append(ring[0])
    return ring


def sample_step(pts):
    """Шаг опробования: медиана расстояния между соседними пробами.

    Нужен для сведения проб к одной точке. Брать для этого ячейку
    грида нельзя: она мельче шага опробования, и пробы двух разрезов
    у самого их пересечения ложатся в РАЗНЫЕ ячейки. Тогда проверка
    молчит всегда, чего бы ни было в данных.

    Медиана, а не среднее: между кусками пробы идут подряд, и на
    стыке кусков расстояние скачет.
    """
    p = np.asarray(pts, dtype=float)
    if len(p) < 2:
        return 0.0
    d = np.hypot(*np.diff(p[:, :2], axis=0).T)
    d = d[d > 0]
    return float(np.median(d)) if d.size else 0.0


def _spread_pass(p, v, own, snap, shift):
    """Один проход сведения: сетка, сдвинутая на долю ячейки.

    Возвращает (мест, наибольший размах, где он).
    """
    key = np.round(p / snap + shift).astype(np.int64)
    _u, inv, cnt = np.unique(key, axis=0, return_inverse=True,
                             return_counts=True)
    inv = np.asarray(inv).ravel()
    many = cnt > 1
    if own is not None:
        o_lo = np.full(len(cnt), np.inf)
        o_hi = np.full(len(cnt), -np.inf)
        np.minimum.at(o_lo, inv, own)
        np.maximum.at(o_hi, inv, own)
        many = many & (o_hi > o_lo)
    if not many.any():
        return 0, 0.0, None
    lo = np.full(len(cnt), np.inf)
    hi = np.full(len(cnt), -np.inf)
    np.minimum.at(lo, inv, v)
    np.maximum.at(hi, inv, v)
    d = hi - lo
    cell = int(np.argmax(np.where(many, d, -np.inf)))
    # Место называем координатами пробы, а не центром ячейки сведения:
    # человеку идти искать его в свой слой, и адрес должен быть тот же.
    where = p[inv == cell].mean(axis=0)
    return int(many.sum()), float(d[cell]), (float(where[0]),
                                             float(where[1]))


def crossing_spread(pts, vals, snap=1.0, owner=None):
    """Насколько разошлись ОТМЕТКИ там, где разрезы сошлись в плане.

    `crossing_conflicts` считает знаковое поле: ячейка плоха, если в ней
    встретились плюс и минус. К отметкам это неприменимо - у кровли
    на -250 м знак у всех один, и расхождения не находится никогда,
    сколько бы разрезы ни спорили.

    Здесь пробы сводятся к сетке с шагом `snap`, и в каждой ячейке
    берётся размах значений. Он и есть расхождение: два разреза провели
    границу на разных отметках, а интерполяция усреднит их молча.

    Сводятся четырежды, сеткой со сдвигом на половину ячейки по каждой
    оси. Одной сеткой пара, лежащая по разные стороны границы ячеек,
    не находится вовсе: у шурфа так терялись все четыре угла, где
    зарисовки соседних стенок как раз и обязаны сойтись. Со сдвигами
    пара ближе половины шага попадает в общую ячейку хотя бы в одном
    проходе.

    `owner` - номер контура у каждой пробы. С ним считаются только
    места, где сошлись РАЗНЫЕ контуры: без него в ячейку попадают две
    соседние пробы одного разреза, и счёт раздувается.

    Возвращает (мест, наибольший размах, где он в плане). Число мест -
    НЕ МЕНЬШЕ чем: одно место разные проходы находят разными ячейками,
    и сложить их нельзя, поэтому берётся лучший проход. Наибольший
    размах точен: он берётся по всем проходам.

    Координаты нужны не для красоты. Само число расхождения говорит
    только, что где-то беда; идти с ним человеку некуда. С адресом он
    открывает своё место в слое и видит съехавшую вершину.
    """
    p = np.asarray(pts, dtype=float)[:, :2]
    v = np.asarray(vals, dtype=float)
    if not len(p):
        return 0, 0.0, None
    own = None if owner is None else np.asarray(owner, dtype=float).ravel()
    snap = max(float(snap), 1e-9)
    places, worst, where = 0, 0.0, None
    for shift in ((0.0, 0.0), (0.5, 0.0), (0.0, 0.5), (0.5, 0.5)):
        n, d, w = _spread_pass(p, v, own, snap, np.asarray(shift))
        places = max(places, n)
        if d > worst:
            worst, where = d, w
    return places, worst, where


def sample_bed(rings, step=10.0, pad=None, progress=None):
    """Опробовать пласт целиком, по всем его кускам разом.

    Забор нарезан на куски, по одному на звено линии разреза. Считая
    знак по каждому куску отдельно, ставишь минусы вокруг него - и они
    ложатся туда, где соседний кусок того же пласта даёт плюс.

    На падающем пласте это губительно: пласт тонкий, шесть метров,
    а падает на семьдесят пять по площади, и соседи затирают друг
    друга. Плюсов в слое решётки остаётся три процента, ноль в кубе
    не встречается вовсе, и тела не выходит.

    Здесь точка внутри, если она внутри ЛЮБОГО куска, а расстояние
    берётся до ближайшего. Тогда соседи складываются, а не спорят.
    """
    rings = [np.asarray(r, dtype=float) for r in rings if len(r) >= 3]
    if not rings:
        return np.zeros((0, 3)), np.zeros(0)
    step = max(float(step), 1e-6)
    if pad is None:
        pad = step * 3.0
    pad = float(pad)

    # сетки от каждого куска, но знак и расстояние - по всем
    grids, planes = [], []
    for r in rings:
        got = ring_plane(r)
        if got is None:
            continue
        origin, along, _n = got
        ps = unfold(r, origin, along)
        pz = r[:, 2]
        thick = float(pz.max() - pz.min())
        stepz = min(step, thick / 6.0) if thick > 0 else step
        stepz = max(stepz, 1e-6)
        ss = np.arange(ps.min() - pad, ps.max() + pad + step, step)
        near = np.arange(pz.min() - stepz, pz.max() + 2 * stepz, stepz)
        far = np.arange(pz.min() - pad, pz.max() + pad + step, step)
        zz = np.unique(np.concatenate([near, far]))
        S, Z = np.meshgrid(ss, zz)
        S, Z = S.ravel(), Z.ravel()
        line, at = spine_of(r)
        xy = along_spine(line, at, S)
        grids.append(np.column_stack([xy[:, 0], xy[:, 1], Z]))
        planes.append((ps, pz, origin, along))
    if not grids:
        return np.zeros((0, 3)), np.zeros(0)
    pts = np.vstack(grids)

    ins = np.zeros(len(pts), dtype=bool)
    dist = np.full(len(pts), np.inf)
    for k, (ps, pz, origin, along) in enumerate(planes):
        # точку кладём в плоскость этого куска: путь вдоль линии
        # и отметка, как при опробовании
        s_here = (pts[:, :2] - origin[None, :2]) @ along[:2]
        z_here = pts[:, 2]
        ins |= _inside(ps, pz, s_here, z_here)
        dist = np.minimum(dist, _dist_to_ring(ps, pz, s_here, z_here))
        if progress is not None and (k % 32) == 0:
            progress(k, len(planes))
    dist = np.minimum(dist, pad)
    return pts, np.where(ins, dist, -dist)


def plane_groups(rings, step=None):
    """Кольца, лежащие в одной плоскости разреза, одной группой.

    Пласт на одном разрезе бывает нарисован не одним контуром. Внутри
    него рисуют линзу или пропласток, и у них тот же номер пласта.
    Опрашивая такие кольца порознь и сваливая пробы в одну кучу,
    в облаке кровли получаешь и настоящую кровлю, и верх линзы -
    два разных ответа в одной точке. Интерполяция проводит поверхность
    между ними, и кровля ныряет к подошве там, где линза.

    Поэтому кольца одной плоскости разбираются вместе, по внешней
    границе. Кольца РАЗНЫХ разрезов не объединяются никогда: там
    расхождение в одной точке плана - это данные, и его надо
    показывать, а не прятать взятием крайнего.

    Плоскость задаётся направлением в плане и перпендикулярным
    отстоянием. Допуск берётся от шага опробования: разрез, нарисованный
    от руки, не бывает идеально плоским.

    Возвращает список списков номеров колец.
    """
    planes = []
    groups = []
    for ri, r in enumerate(rings):
        p = np.asarray(r, dtype=float)
        got = ring_plane(p) if len(p) >= 3 and p.shape[1] >= 3 else None
        if got is None:
            continue
        origin, along, normal = got
        ps = unfold(p, origin, along)
        span = float(ps.max() - ps.min())
        if span <= 0:
            continue
        st = float(step) if step else max(span / 60.0, 1e-12)
        off = float(origin[:2] @ normal[:2])
        for gi, (g_along, g_off, g_st) in enumerate(planes):
            par = abs(float(g_along[0] * along[1]
                            - g_along[1] * along[0]))
            if par > 1e-3:
                continue
            if abs(off - g_off) > 0.5 * max(st, g_st):
                continue
            groups[gi].append(ri)
            break
        else:
            planes.append((along, off, st))
            groups.append([ri])
    return groups


def roof_and_floor(rings, step=None, with_ring=False):
    """Кровля и подошва пласта из контуров на разрезах.

    В каждой точке вдоль линии разреза берётся верх и низ контура.
    Делить кольцо пополам нельзя: так устроен только забор, где верх
    идёт вперёд, а низ назад. У нарисованного от руки контура порядок
    вершин произволен, и половинки оказываются вперемешку - мощность
    выходит нулевой там, где пласт есть.

    Контуры одной плоскости разреза разбираются вместе, по внешней
    границе: кровля это верх самого верхнего из них, подошва - низ
    самого нижнего. Линза, нарисованная внутри пласта тем же номером,
    границу тела не трогает (см. `plane_groups`).

    Интерполировать надо именно эти две поверхности, а не тело
    целиком: в объёме между разрезами данных нет, и поле там остаётся
    нулевым, а ноль в таком поле и есть граница.

    Возвращает две матрицы (N, 3), кровля всегда выше подошвы.
    С `with_ring` идёт и третий массив: номер ПЛОСКОСТИ РАЗРЕЗА,
    из которой взята каждая проба. По нему видно, сошлись ли в одной
    точке разные разрезы или это две соседние пробы одного и того же.
    """
    tops, bots, owner = [], [], []
    for gi, idx in enumerate(plane_groups(rings, step)):
        parts = []
        for ri in idx:
            p = np.asarray(rings[ri], dtype=float)
            got = ring_plane(p)
            if got is None:
                continue
            origin, along, _n = got
            parts.append((p, origin, along))
        if not parts:
            continue
        # Ведущее кольцо группы - самое протяжённое в плане: по нему
        # идёт линия опробования, к нему приводятся остальные.
        def _span(q):
            u = unfold(q[0], q[1], q[2])
            return float(u.max() - u.min())

        lead = max(parts, key=_span)
        p0, origin, along = lead
        many = len(parts) > 1
        if many:
            # Развёртка у каждого кольца своя: путь считается от его
            # ПЕРВОЙ вершины, и у линзы, нарисованной в середине борта,
            # ноль приходится на её начало, а не на начало борта.
            # Сравнивать два кольца на общих сечениях в таких
            # координатах нельзя - линза ложится не на своё место.
            # Внутри одной плоскости разрез прямой (иначе кольца
            # в группу и не попали бы), поэтому берём проекцию:
            # она у всех колец общая.
            def _pos(p):
                return (p[:, :2] - origin[:2]) @ along[:2]
        else:
            def _pos(p):
                return unfold(p, origin, along)
        ps0 = _pos(p0)
        span = float(ps0.max() - ps0.min())
        if span <= 0:
            continue
        st = float(step) if step else max(span / 60.0, 1e-12)
        cuts = np.arange(ps0.min() + st * 0.5, ps0.max(), st)
        if not len(cuts):
            cuts = np.array([(ps0.min() + ps0.max()) * 0.5])
        hi = np.full(len(cuts), np.nan)
        lo = np.full(len(cuts), np.nan)
        for p, _o, _a in parts:
            ps = _pos(p)
            pz = p[:, 2]
            h = _cut_extreme(ps, pz, cuts, high=True)
            ll = _cut_extreme(ps, pz, cuts, high=False)
            # Кольцо отвечает только за свой участок борта. Опрос
            # за его пределами продолжает крайнее ребро, и линза
            # тянула бы подошву по всей длине.
            own = (cuts >= ps.min() - 1e-9) & (cuts <= ps.max() + 1e-9)
            ok = np.isfinite(h) & np.isfinite(ll) & own
            hi[ok] = np.fmax(hi[ok], h[ok])
            lo[ok] = np.fmin(lo[ok], ll[ok])
        good = np.isfinite(hi) & np.isfinite(lo) & (hi > lo)
        if not good.any():
            continue
        if many:
            sel = cuts[good][:, None]
            xy = origin[:2][None, :] + sel * along[:2][None, :]
        else:
            line, at = spine_of(p0)
            xy = along_spine(line, at, cuts[good])
        tops.append(np.column_stack([xy[:, 0], xy[:, 1], hi[good]]))
        bots.append(np.column_stack([xy[:, 0], xy[:, 1], lo[good]]))
        owner.append(np.full(int(good.sum()), gi, dtype=np.int64))
    if not tops:
        empty = (np.zeros((0, 3)), np.zeros((0, 3)))
        return empty + (np.zeros(0, dtype=np.int64),) if with_ring else empty
    out = (np.vstack(tops), np.vstack(bots))
    return out + (np.concatenate(owner),) if with_ring else out


def _cut_extreme(poly_s, poly_z, cuts, high=True):
    """Верх или низ контура на каждом положении вдоль линии."""
    n = len(poly_s)
    out = np.full(len(cuts), np.nan)
    for i in range(n):
        j = (i + 1) % n
        s0, z0 = poly_s[i], poly_z[i]
        s1, z1 = poly_s[j], poly_z[j]
        if s0 == s1:
            continue
        lo_s, hi_s = (s0, s1) if s0 < s1 else (s1, s0)
        m = (cuts > lo_s) & (cuts <= hi_s)
        if not m.any():
            continue
        t = (cuts[m] - s0) / (s1 - s0)
        z = z0 + t * (z1 - z0)
        cur = out[m]
        pick = np.maximum(cur, z) if high else np.minimum(cur, z)
        out[m] = np.where(np.isfinite(cur), pick, z)
    return out
