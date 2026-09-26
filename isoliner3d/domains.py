# -*- coding: utf-8 -*-
"""Тела толщ по контурам в любых плоскостях (2.15).

Толщи лежат рядом, а не одна над другой: граница между ними это
крутой контакт, а не кровля и подошва над планом. Поэтому здесь
строится не пара поверхностей на толщу, а поле на толщу во всём
объёме, и каждая точка отходит той толще, чьё поле в ней больше.
Щелей и нахлёстов между телами тогда нет по построению.

Поле толщи это расстояние до её границы со знаком: внутри плюс,
снаружи минус. Считается оно в плоскости каждого контура, какой
бы эта плоскость ни была: вертикальный разрез, план, наклонное
сечение. Между плоскостями поле интерполируется мультисеточными
B-сплайнами в объёме (mba.py), тем же путём, что в 2.07.

Сверху тела обрезаются рельефом. Он строится по отметкам контуров
на плане и по верху разрезов: над рельефом горной массы нет, а поле
туда тянется само. Снизу обрезка по нижней отметке данных, в плане
по выпуклой оболочке данных. Ниже и в стороне никто ничего не видел.

Считается на голом NumPy, QGIS не нужен.
"""

import numpy as np

from . import mba
from .section3d import _cut_extreme, _dist_to_ring, _inside

WALL, PLAN, SLANT = "wall", "plan", "slant"


def ring_frame(pts):
    """Плоскость контура: центр, два направления в ней, нормаль, разброс.

    Плоскость подбирается по всем вершинам, а не по первым трём:
    контур, снятый с разреза или карты, плоским бывает только
    приблизительно.

    У вертикальной плоскости первое направление горизонтально, второе
    смотрит вверх. У горизонтальной первое идёт на восток, второе на
    север. Так координаты в плоскости читаются как путь и отметка
    или как план.

    Возвращает (центр, e1, e2, нормаль, разброс) или None у вырожденного
    контура.
    """
    p = np.asarray(pts, dtype=float)[:, :3]
    if len(p) < 3 or not np.isfinite(p).all():
        return None
    c = p.mean(axis=0)
    q = p - c
    try:
        _u, s, vt = np.linalg.svd(q, full_matrices=False)
    except np.linalg.LinAlgError:
        return None
    if s[1] < 1e-9 * max(s[0], 1e-12):
        return None
    n = vt[2] / np.linalg.norm(vt[2])
    if n[2] < 0:
        n = -n
    up = np.array([0.0, 0.0, 1.0])
    if abs(n[2]) > 0.999:
        e1 = np.array([1.0, 0.0, 0.0])
    else:
        e1 = np.cross(up, n)
        e1 /= np.linalg.norm(e1)
    e2 = np.cross(n, e1)
    e2 /= np.linalg.norm(e2)
    rms = float(np.sqrt(np.mean((q @ n) ** 2)))
    return c, e1, e2, n, rms


def kind_of(normal):
    """Разрез, план или наклонное сечение - по наклону нормали."""
    nz = abs(float(normal[2]))
    if nz < 0.3:
        return WALL
    if nz > 0.8:
        return PLAN
    return SLANT


def plane_groups(rings, tol):
    """Контуры одной плоскости одной группой.

    На разрезе толщи нарисованы рядом, каждая своим контуром. Опробуя
    их порознь, не узнаешь, что точка внутри соседа лежит снаружи
    этой толщи. Поэтому плоскость опробуется целиком, по всем её
    контурам разом.

    Плоскость совпадает, если нормали сходятся в пределах пяти градусов,
    а вершины одного контура лежат не дальше `tol` от плоскости другого.
    """
    frames = [ring_frame(r) for r in rings]
    groups = []
    for i, f in enumerate(frames):
        if f is None:
            continue
        c, _e1, _e2, n, _rms = f
        for g in groups:
            c0, n0 = g["c"], g["n"]
            if abs(float(n @ n0)) < np.cos(np.radians(5.0)):
                continue
            off = np.abs((np.asarray(rings[i])[:, :3] - c0) @ n0)
            if float(off.max()) <= tol and abs(float((c - c0) @ n0)) <= tol:
                g["idx"].append(i)
                break
        else:
            groups.append({"c": c, "n": n, "idx": [i]})
    return [g["idx"] for g in groups]


def _group_frame(rings, idx):
    return ring_frame(np.vstack([np.asarray(rings[i])[:, :3] for i in idx]))


def _segments(pu, pv):
    """Рёбра замкнутого контура: (N, 4) - начало и конец в плоскости."""
    a = np.column_stack([pu, pv])
    b = np.roll(a, -1, axis=0)
    keep = np.hypot(*(b - a).T) > 0
    return np.hstack([a[keep], b[keep]])


def _dist_to_segments(seg, u, v):
    """Расстояние от точек до ближайшего из отрезков."""
    best = np.full(len(u), np.inf)
    for ax, ay, bx, by in seg:
        vx, vy = bx - ax, by - ay
        ln = vx * vx + vy * vy
        t = np.clip(((u - ax) * vx + (v - ay) * vy) / ln, 0.0, 1.0)
        best = np.minimum(best, np.hypot(u - (ax + t * vx),
                                         v - (ay + t * vy)))
    return best


def contact_segments(loc, tol):
    """Рёбра, по которым толща граничит с соседкой: {код: (N, 4)}.

    Внешний край контура контактом не является. Низ разреза, его торцы
    и обрез карты проведены там, где кончились данные, а не там, где
    кончилась толща. Мерить поле до них значит объявить, что у низа
    разреза толща кончается: поле там падает к нулю, и соседка
    забирает то, что ей не принадлежит.

    Ребро считается контактом, если его середина лежит не дальше `tol`
    от контура другой толщи в той же плоскости.
    """
    out = {}
    for code, polys in loc.items():
        others = [q for c2, ps in loc.items() if c2 != code for q in ps]
        segs = []
        for pu, pv in polys:
            sg = _segments(pu, pv)
            if not len(sg) or not others:
                continue
            mu = 0.5 * (sg[:, 0] + sg[:, 2])
            mv = 0.5 * (sg[:, 1] + sg[:, 3])
            d = np.full(len(sg), np.inf)
            for qu, qv in others:
                d = np.minimum(d, _dist_to_ring(qu, qv, mu, mv))
            segs.append(sg[d <= tol])
        out[code] = np.vstack(segs) if segs else np.zeros((0, 4))
    return out


def sample_plane(rings, codes, idx, all_codes, step, cap, tol=None):
    """Опробование одной плоскости: точки и поле каждой толщи в них.

    Точки берутся только внутри контуров плоскости. Снаружи всех
    контуров ничего не известно: под разрезом горная масса есть, но
    какая, никто не видел. Считать её «чужой» для всех толщ значило бы
    выдумать там пустоту.

    Поле толщи - расстояние до её КОНТАКТОВ со знаком: внутри плюс,
    снаружи минус (см. `contact_segments`). Толща без контактов
    в плоскости получает `cap` внутри своего контура. Толща, которой
    в плоскости нет, получает `-cap`: здесь её точно нет, а насколько
    далеко она, плоскость не знает. Расстояния обрезаются по `cap`,
    чтобы глубь большого контура не перевешивала соседей.

    Возвращает (точки (N, 3), {код: значения (N,)}, (центр, e1, e2, n)).
    """
    fr = _group_frame(rings, idx)
    if fr is None:
        return np.zeros((0, 3)), {}, None
    c, e1, e2, n, _rms = fr
    if tol is None:
        tol = 0.5 * step
    loc = {}
    for i in idx:
        q = np.asarray(rings[i], dtype=float)[:, :3] - c
        loc.setdefault(codes[i], []).append((q @ e1, q @ e2))
    allu = np.concatenate([u for v in loc.values() for u, _w in v])
    allv = np.concatenate([w for v in loc.values() for _u, w in v])
    us = np.arange(allu.min(), allu.max() + step, step)
    vs = np.arange(allv.min(), allv.max() + step, step)
    U, V = np.meshgrid(us, vs)
    U, V = U.ravel(), V.ravel()
    inside = {}
    for code, polys in loc.items():
        ins = np.zeros(len(U), dtype=bool)
        for pu, pv in polys:
            ins |= _inside(pu, pv, U, V)
        inside[code] = ins
    keep = np.zeros(len(U), dtype=bool)
    for ins in inside.values():
        keep |= ins
    U, V = U[keep], V[keep]
    inside = {k: v[keep] for k, v in inside.items()}
    contacts = contact_segments(loc, tol)
    # точки на самих контактах: там поле ноль, и без них контакт
    # держится только точками решётки в полшага от него
    extra = []
    for sg in contacts.values():
        if not len(sg):
            continue
        ln = np.hypot(sg[:, 2] - sg[:, 0], sg[:, 3] - sg[:, 1])
        for (ax, ay, bx, by), L in zip(sg, ln):
            t = np.arange(0.0, 1.0, min(1.0, step / max(L, 1e-9)))
            extra.append(np.column_stack([ax + t * (bx - ax),
                                          ay + t * (by - ay)]))
    n_in = len(U)
    if extra:
        e = np.vstack(extra)
        U = np.concatenate([U, e[:, 0]])
        V = np.concatenate([V, e[:, 1]])
    vals = {}
    for code in all_codes:
        if code not in loc:
            vals[code] = np.full(len(U), -float(cap))
            continue
        ins = np.zeros(len(U), dtype=bool)
        ins[:n_in] = inside[code]
        sg = contacts[code]
        if len(sg):
            d = np.minimum(_dist_to_segments(sg, U, V), cap)
        else:
            d = np.full(len(U), float(cap))
        v = np.where(ins, d, -d)
        # на контакте ноль у обеих сторон, какой бы ни вышла точка
        v[n_in:] = np.where(d[n_in:] <= 1e-9, 0.0, v[n_in:])
        vals[code] = v
    pts = c[None, :] + U[:, None] * e1[None, :] + V[:, None] * e2[None, :]
    return pts, vals, (c, e1, e2, n)


def relief_points(rings, groups, step):
    """Точки рельефа: вершины плана и верх разрезов.

    План снят с дневной поверхности, и отметки его вершин и есть
    рельеф. У разреза рельеф это верхняя граница всех его контуров
    вместе: у каждой толщи свой кусок верха.
    """
    out = []
    for idx in groups:
        fr = _group_frame(rings, idx)
        if fr is None:
            continue
        c, e1, e2, n, _rms = fr
        kind = kind_of(n)
        if kind == PLAN:
            for i in idx:
                out.append(np.asarray(rings[i], dtype=float)[:, :3])
        elif kind == WALL:
            polys = []
            for i in idx:
                q = np.asarray(rings[i], dtype=float)[:, :3] - c
                polys.append((q @ e1, q @ e2))
            lo = min(float(u.min()) for u, _v in polys)
            hi = max(float(u.max()) for u, _v in polys)
            cuts = np.arange(lo, hi + step * 0.5, step)
            top = np.full(len(cuts), np.nan)
            for pu, pv in polys:
                t = _cut_extreme(pu, pv, cuts, high=True)
                top = np.where(np.isfinite(top) & np.isfinite(t),
                               np.maximum(top, t),
                               np.where(np.isfinite(t), t, top))
            ok = np.isfinite(top)
            if ok.any():
                out.append(c[None, :] + cuts[ok, None] * e1[None, :]
                           + top[ok, None] * e2[None, :])
    if not out:
        return np.zeros((0, 3))
    return np.vstack(out)


def hull_distance(ring, x, y):
    """Расстояние в плане до выпуклой оболочки, внутри плюс."""
    r = np.asarray(ring, dtype=float)
    if len(r) < 3:
        return np.full(np.shape(x), np.inf)
    rs, rz = r[:, 0], r[:, 1]
    xs = np.asarray(x, dtype=float).ravel()
    ys = np.asarray(y, dtype=float).ravel()
    ins = _inside(rs, rz, xs, ys)
    d = _dist_to_ring(rs, rz, xs, ys)
    return np.where(ins, d, -d).reshape(np.shape(x))


def auto_levels(extent, grid, step):
    """Уровней MBA, чтобы последняя решётка дошла до шага опробования."""
    cell0 = max(float(np.max(np.asarray(extent) / np.asarray(grid))), step)
    return int(np.clip(np.ceil(np.log2(cell0 / step)) + 1, 3, 11))


def section_frame(rings, groups, step):
    """Оси интерполяции по разрезам: вдоль, поперёк, вверх.

    Мультисеточная интерполяция переносит подробности только туда, где
    есть данные: мелкие решётки между разрезами пусты, и там остаётся
    одна грубая. При разрезах через четыреста метров и ячейке в сто
    контакт посередине уходил на сорок метров. Поэтому начальная
    решётка анизотропна: частая в плоскости разрезов, где данные
    густые, и в две-три ячейки поперёк, где их нет. Тогда контакт
    между разрезами идёт от одного к другому, а не расплывается.

    Поперёк - средняя нормаль вертикальных разрезов, если они
    параллельны между собой. Если разрезов нет или они смотрят
    в разные стороны, оси остаются как есть, решётка изотропная.

    Возвращает словарь: to(точки) - перевод в оси интерполяции,
    grid(размах) - начальная решётка, spacing - шаг между разрезами
    или None.
    """
    normals, offs = [], []
    for idx in groups:
        fr = _group_frame(rings, idx)
        if fr is None or kind_of(fr[3]) != WALL:
            continue
        nh = np.array([fr[3][0], fr[3][1]])
        nh /= max(np.linalg.norm(nh), 1e-12)
        normals.append(nh)
        offs.append(fr[0][:2])
    iso = {"to": lambda p: np.asarray(p, dtype=float).reshape(-1, 3),
           "spacing": None}

    def _iso_grid(ext):
        return tuple(int(max(1, round(e / max(float(np.min(ext)),
                                                1e-9)))) for e in ext)
    iso["grid"] = _iso_grid
    if len(normals) < 2:
        return iso
    ref = normals[0]
    al = [n if float(n @ ref) >= 0 else -n for n in normals]
    if min(float(n @ ref) for n in al) < np.cos(np.radians(15.0)):
        return iso
    nb = np.mean(al, axis=0)
    nb /= np.linalg.norm(nb)
    na = np.array([nb[1], -nb[0]])
    o = np.sort(np.array([float(c @ nb) for c in offs]))
    gaps = np.diff(o)
    gaps = gaps[gaps > max(step, 1e-6)]
    if not len(gaps):
        return iso
    spacing = float(np.median(gaps))

    def _to(p):
        p = np.asarray(p, dtype=float).reshape(-1, 3)
        return np.column_stack([p[:, :2] @ na, p[:, :2] @ nb, p[:, 2]])

    def _grid(ext):
        # в плоскости разреза ячейка в шестнадцатую долю шага между
        # разрезами, поперёк - две ячейки на шаг
        fine = spacing / 16.0
        ga = int(np.clip(round(ext[0] / fine), 2, 64))
        gz = int(np.clip(round(ext[2] / fine), 1, 64))
        gb = int(max(2, round(2.0 * ext[1] / spacing)))
        return (ga, gb, gz)
    return {"to": _to, "grid": _grid, "spacing": spacing}


def build(rings, codes, cell, cellz=None, step=None, cap=None,
          levels=None, progress=None):
    """Поле каждой толщи, рельеф и классы на воксельной сетке.

    `rings` - контуры (N, 3) в любых плоскостях, `codes` - код толщи
    у каждого. `cell` - шаг сетки в плане, `cellz` - по вертикали.

    Возвращает словарь:
        gt, z0, dz, shape - сетка куба (уровень, строка, столбец);
        codes             - порядок толщ;
        margin            - {код: поле со знаком, где плюс это эта
                             толща: её поле минус лучшее из чужих,
                             и не больше расстояния до рельефа, дна
                             и оболочки};
        cls               - номер толщи в `codes` у каждого вокселя,
                            -1 вне горной массы;
        rock              - воксели горной массы;
        groups, kinds     - плоскости и их род;
        relief            - точки рельефа.
    """
    rings = [np.asarray(r, dtype=float)[:, :3] for r in rings]
    all_codes = sorted(set(codes), key=lambda v: str(v))
    cell = float(cell)
    cellz = float(cellz or cell)
    step = float(step or cell)
    allp = np.vstack(rings)
    x0, y0, zb = allp.min(axis=0)
    x1, y1, zt = allp.max(axis=0)
    span = float(max(x1 - x0, y1 - y0, zt - zb))
    if cap is None:
        cap = max(10.0 * step, 0.1 * span)
    tol = max(step, 0.01 * span)
    groups = plane_groups(rings, tol)

    # Карта и разрезы интерполируются вместе. Пробовали иначе: поле по
    # одним разрезам, а невязку на карте прибавлять на всю глубину.
    # Тогда поправка у разных толщ разная, и на самих разрезах контакт
    # съезжал: у Василия Швалева разрезы воспроизводились на 81 и 84
    # процента. Вместе, на анизотропной решётке (см. `section_frame`),
    # карта держит контакт у поверхности, а в глубину его ведут разрезы.
    pts, vals, kinds = [], {c: [] for c in all_codes}, []
    # План опробуется по рельефу, а не по подобранной плоскости: карта
    # снята с дневной поверхности, и между вершинами отметка идёт
    # по рельефу. Поэтому рельеф строится первым.
    relief = relief_points(rings, groups, step)
    gx = max(int(np.ceil((x1 - x0) / cell)), 2)
    gy = max(int(np.ceil((y1 - y0) / cell)), 2)
    gt = (float(x0), cell, 0.0, float(y0) + gy * cell, 0.0, -cell)
    lev2 = auto_levels([x1 - x0, y1 - y0], (2, 2), step)
    top_lat = None
    if len(relief) >= 3:
        top_lat = mba.fit(relief[:, :2], relief[:, 2], lo=[x0, y0],
                          hi=[x1, y1], grid=(2, 2), levels=lev2,
                          center="plane")
    for gi, idx in enumerate(groups):
        p, v, fr = sample_plane(rings, codes, idx, all_codes, step, cap)
        if fr is None or not len(p):
            continue
        kind = kind_of(fr[3])
        kinds.append(kind)
        if kind == PLAN and top_lat is not None:
            p = p.copy()
            p[:, 2] = mba.evaluate(top_lat, p[:, :2])
        pts.append(p)
        for c in all_codes:
            vals[c].append(v[c])
        if progress is not None:
            progress(gi + 1, len(groups))
    if not pts:
        raise ValueError("no planar outlines")
    pts = np.vstack(pts)
    vals = {c: np.concatenate(v) for c, v in vals.items()}
    n_samples = len(pts)

    nz = max(int(np.ceil((zt - zb) / cellz)) + 1, 2)
    z0 = float(zb)
    shape = (nz, gy, gx)
    ax = gt[0] + cell * (np.arange(gx) + 0.5)
    ay = gt[3] - cell * (np.arange(gy) + 0.5)
    az = z0 + cellz * np.arange(nz)
    ZZ, YY, XX = np.meshgrid(az, ay, ax, indexing="ij")
    nodes = np.column_stack([XX.ravel(), YY.ravel(), ZZ.ravel()])

    frame = section_frame(rings, groups, step)
    to = frame["to"]
    q_pts = to(pts)
    q_all = np.vstack([q_pts, to(allp)])
    lo, hi = q_all.min(axis=0), q_all.max(axis=0)
    ext = np.maximum(hi - lo, 1e-9)
    grid3 = frame["grid"](ext)
    if levels is None:
        levels = auto_levels(ext, grid3, step)
    q_nodes = to(nodes)
    field = {}
    misfit = {}
    for c in all_codes:
        lat = mba.fit(q_pts, vals[c], lo=lo, hi=hi,
                      grid=grid3, levels=levels, center="plane")
        field[c] = mba.evaluate(lat, q_nodes).reshape(shape)
        # невязка у самого контакта, где поле по данным меньше двух
        # шагов: глубь толщи здесь неинтересна, она обрезана `cap`
        near = np.abs(vals[c]) <= 2.0 * step
        if near.any():
            r = vals[c][near] - mba.evaluate(lat, q_pts[near])
            misfit[c] = float(np.sqrt(np.mean(r ** 2)))

    # горная масса: под рельефом, над дном данных, внутри оболочки
    MX, MY = np.meshgrid(ax, ay)
    from .section3d import convex_hull_ring
    hull = convex_hull_ring(allp)
    hd = hull_distance(hull, MX, MY) if hull else np.full(MX.shape, np.inf)
    if top_lat is not None:
        topz = mba.surface_on_grid(top_lat, gt, gx, gy)
    else:
        topz = np.full(MX.shape, zt)
    below = topz[None, :, :] - az[:, None, None]
    above = az[:, None, None] - zb
    bound = np.minimum(np.minimum(below, above), hd[None, :, :])
    rock = bound >= 0

    stack = np.stack([field[c] for c in all_codes])
    best = np.argmax(stack, axis=0)
    cls = np.where(rock, best, -1)
    margin = {}
    for k, c in enumerate(all_codes):
        if len(all_codes) > 1:
            other = np.delete(stack, k, axis=0).max(axis=0)
            m = stack[k] - other
        else:
            m = stack[k]
        m = np.minimum(m, bound)
        # Точный ноль в узле кладёт вершину оболочки прямо в узел,
        # и соседние треугольники схлопываются в линию. Ноль на
        # границе горной массы здесь обычен: дно данных проходит
        # ровно по уровню. Сдвиг на миллионную шага наружу убирает
        # это, не двигая оболочку.
        eps = 1e-6 * cellz
        m[np.abs(m) < eps] = -eps
        margin[c] = m
    return {"gt": gt, "z0": z0, "dz": cellz, "shape": shape,
            "codes": all_codes, "margin": margin, "cls": cls,
            "rock": rock, "groups": groups, "kinds": kinds,
            "relief": relief, "topz": topz, "samples": n_samples,
            "misfit": misfit, "grid3": grid3,
            "spacing": frame["spacing"],
            "levels": levels, "cap": cap}


def padded(vol, gt, z0, dz, fill=-1.0):
    """Куб с рамкой в одну ячейку, чтобы оболочка замкнулась.

    Изоповерхность у края куба обрывается: снаружи точек нет, и тело,
    дошедшее до края, остаётся без стенки. Рамка отрицательных значений
    закрывает его по самому краю.
    """
    v = np.pad(np.nan_to_num(vol, nan=fill), 1, mode="constant",
               constant_values=fill)
    g = (gt[0] - gt[1], gt[1], 0.0, gt[3] - gt[5], 0.0, gt[5])
    return v, g, z0 - dz


def body_mesh(margin, gt, z0, dz):
    """Оболочка толщи по её полю: (вершины, треугольники) одним куском."""
    from .iso3d import isosurface
    v, g, z = padded(margin, gt, z0, dz)
    return isosurface(v, 0.0, g, z, dz)


def bodies(margin, gt, z0, dz, min_volume=None):
    """Тела толщи: связные куски оболочки с проверкой и объёмом.

    Путь тот же, что у кнопки оболочек в сцене. Оболочка разбирается
    на связные тела: толща, прерванная соседкой, даёт два тела, и объём
    каждого нужен отдельно. Мелкие дыры зашиваются, большие остаются
    и считаются: у тела с дырой объёма нет.

    Тела меньше `min_volume` (по умолчанию половина ячейки) отброшены:
    это крошки марша на стыке трёх толщ, а не тела.

    Возвращает список (вершины, треугольники, дыр, защипов, объём или
    None).
    """
    if min_volume is None:
        min_volume = 0.5 * abs(gt[1] * gt[5]) * dz
    from .cleanup import (close_holes, mesh_volume, shell_defects,
                          split_bodies)
    v, f = body_mesh(margin, gt, z0, dz)
    out = []
    if not len(f):
        return out
    for pv, pf, _tag in split_bodies(v, f):
        holes, pinch = shell_defects(pv, pf)
        if holes:
            pv, pf, n_fix = close_holes(pv, pf)
            if n_fix:
                holes, pinch = shell_defects(pv, pf)
        vol = mesh_volume(pv, pf) if not holes else None
        if vol is not None and vol < min_volume:
            continue
        out.append((pv, pf, int(holes), int(pinch), vol))
    return out
