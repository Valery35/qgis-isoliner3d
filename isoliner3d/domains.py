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


def _orient_down(pts):
    """Интервал сверху вниз: первая вершина выше последней."""
    p = np.asarray(pts, dtype=float)[:, :3]
    return p[::-1] if p[0, 2] < p[-1, 2] else p


def hole_runs(intervals):
    """Ствол из интервалов: ломаная, глубины и пачки одного кода.

    `intervals` - [(код, вершины (k, 3))] одной скважины в любом
    порядке и направлении. Интервалы ставятся сверху вниз по отметке
    верха, соседние одного кода сливаются в пачку: граница между
    ними не контакт.

    Возвращает (вершины ствола (N, 3), глубины по стволу (N,),
    пачки [(код, от, до)]).
    """
    segs = sorted(((c, _orient_down(p)) for c, p in intervals),
                  key=lambda t: -t[1][0, 2])
    verts, md, runs = [], [], []
    s = 0.0
    for code, p in segs:
        d = np.concatenate([[0.0], np.cumsum(np.linalg.norm(
            np.diff(p, axis=0), axis=1))])
        start = s
        if verts and np.linalg.norm(verts[-1] - p[0]) > 1e-6:
            # разрыв опробования: глубина идёт по прямой через пропуск
            s += float(np.linalg.norm(verts[-1] - p[0]))
            start = s
        for k in range(len(p)):
            if verts and k == 0 and np.linalg.norm(verts[-1] - p[0]) \
                    <= 1e-6:
                continue
            verts.append(p[k])
            md.append(start + d[k])
        s = start + d[-1]
        if runs and runs[-1][0] == code and abs(runs[-1][2] - start) \
                <= 1e-6:
            runs[-1] = (code, runs[-1][1], s)
        else:
            runs.append((code, start, s))
    return np.array(verts), np.array(md), runs


def _at_md(verts, md, s):
    """Точки ствола на глубинах `s`."""
    s = np.clip(np.asarray(s, dtype=float), md[0], md[-1])
    return np.column_stack([np.interp(s, md, verts[:, k])
                            for k in range(3)])


def sample_holes(holes, all_codes, step, cap):
    """Опробование стволов: точки и поле каждой толщи вдоль них.

    То же поле, что в плоскостях контуров (`sample_plane`), только
    одномерное: расстояние по стволу до КОНТАКТОВ толщи со знаком.
    Внутри пачки толщи плюс, до ближайшего её контакта со своей
    стороны. Верх и низ ствола контактом не считаются: там кончились
    данные, а не толща. В чужой пачке минус, до ближайшей пачки этой
    толщи в той же скважине. Толща, которой в скважине нет, получает
    `-cap`: здесь её нет, а насколько далеко она, скважина не знает.

    На каждом контакте ставится точка, где поле обеих толщ ноль.

    `holes` - список скважин, скважина - [(код, вершины (k, 3))].
    Возвращает (точки (N, 3), {код: значения (N,)}, устья (M, 3)).
    """
    pts, vals = [], {c: [] for c in all_codes}
    collars = []
    for intervals in holes:
        if not intervals:
            continue
        verts, md, runs = hole_runs(intervals)
        if len(verts) < 2:
            continue
        collars.append(verts[0])
        bounds = [r[1] for r in runs] + [runs[-1][2]]
        samples, own = [], []
        for ri, (code, a, b) in enumerate(runs):
            n = max(int(np.ceil((b - a) / step)), 1)
            ss = a + (np.arange(n) + 0.5) * (b - a) / n
            samples.append(ss)
            own.append(np.full(n, ri))
        contacts = [ri for ri in range(1, len(runs))
                    if runs[ri][0] != runs[ri - 1][0]]
        for ri in contacts:
            samples.append(np.array([bounds[ri]]))
            own.append(np.array([-1 - ri]))     # контакт перед пачкой ri
        ss = np.concatenate(samples)
        ow = np.concatenate(own)
        pts.append(_at_md(verts, md, ss))
        for c in all_codes:
            mine = [ri for ri, r in enumerate(runs) if r[0] == c]
            v = np.empty(len(ss))
            for k, (s, o) in enumerate(zip(ss, ow)):
                if o < 0:
                    ri = -1 - o
                    v[k] = 0.0 if c in (runs[ri][0], runs[ri - 1][0]) \
                        else -min(cap, min((abs(s - x) for m in mine
                                            for x in runs[m][1:]),
                                           default=cap))
                    continue
                code, a, b = runs[o]
                if code == c:
                    d = []
                    if o > 0 and runs[o - 1][0] != c:
                        d.append(s - a)
                    if o < len(runs) - 1 and runs[o + 1][0] != c:
                        d.append(b - s)
                    v[k] = min(min(d), cap) if d else cap
                elif mine:
                    v[k] = -min(cap, min(min(abs(s - runs[m][1]),
                                             abs(s - runs[m][2]))
                                         for m in mine))
                else:
                    v[k] = -cap
            vals[c].append(v)
    if not pts:
        return np.zeros((0, 3)), {c: np.zeros(0) for c in all_codes}, \
            np.zeros((0, 3))
    return (np.vstack(pts), {c: np.concatenate(v) for c, v in vals.items()},
            np.array(collars))


def hole_spacing(collars):
    """Обычное расстояние между соседними скважинами в плане (медиана)."""
    c = np.asarray(collars, dtype=float)[:, :2]
    if len(c) < 2:
        return None
    d = np.hypot(c[:, None, 0] - c[None, :, 0], c[:, None, 1] - c[None, :, 1])
    np.fill_diagonal(d, np.inf)
    nn = d.min(axis=1)
    nn = nn[np.isfinite(nn) & (nn > 1e-6)]
    return float(np.median(nn)) if len(nn) else None


def group_intervals(items, tol=0.01):
    """Интервалы в скважины.

    `items` - [(номер скважины или None, код, вершины (k, 3))]. Номер
    есть - скважину собирают интервалы с одним номером. Номера нет -
    интервалы сцепляются концами: низ одного там же, где верх
    следующего, с точностью `tol`. Так собирается и наклонная
    скважина без поля номера.

    Возвращает список скважин, скважина - [(код, вершины)].
    """
    named, loose = {}, []
    for key, code, p in items:
        p = np.asarray(p, dtype=float)[:, :3]
        if len(p) < 2 or not np.isfinite(p).all():
            continue
        if key is None or str(key).strip() in ("", "NULL"):
            loose.append((code, p))
        else:
            named.setdefault(str(key).strip(), []).append((code, p))
    out = list(named.values())
    if loose:
        parent = list(range(len(loose)))

        def root(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        ends = {}
        for i, (_c, p) in enumerate(loose):
            for v in (p[0], p[-1]):
                k = tuple(np.round(v / tol).astype(np.int64))
                if k in ends:
                    parent[root(i)] = root(ends[k])
                else:
                    ends[k] = i
        by = {}
        for i, it in enumerate(loose):
            by.setdefault(root(i), []).append(it)
        out.extend(by.values())
    return out


DEMO_CODES = ("Почвенно-растительный слой", "Песок мелкий",
              "Песок крупный", "Глина")


def demo_relief(x, y, z0=140.0):
    """Рельеф демо-участка: пологие увалы."""
    return z0 + 2.0 * np.sin(x / 150.0) + 1.5 * np.cos(y / 120.0)


def demo_thickness(x, y):
    """Мощности толщ демо над глиной: ПРС, песок мелкий, песок крупный.

    Песок мелкий выклинивается на восток: к x = 480 м его нет.
    Песок крупный - линза в середине участка.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    prs = 0.8 + 0.3 * np.sin(x / 60.0 + y / 90.0)
    fine = np.clip(6.0 - x / 80.0, 0.0, None) * (1.0 + 0.2 * np.cos(
        y / 70.0))
    lens = 6.0 * np.clip(1.0 - ((x - 300.0) / 170.0) ** 2
                         - ((y - 200.0) / 110.0) ** 2, 0.0, None)
    return prs, fine, lens


def demo_unit(x, y, z):
    """Номер толщи демо в точке (по DEMO_CODES), над рельефом -1."""
    top = demo_relief(x, y)
    prs, fine, lens = demo_thickness(x, y)
    d = top - np.asarray(z, dtype=float)
    out = np.full(np.shape(d), 3)
    out = np.where(d < prs + fine + lens, 2, out)
    out = np.where(d < prs + fine, 1, out)
    out = np.where(d < prs, 0, out)
    return np.where(d < 0, -1, out)


def demo_holes(seed=1, x0=0.0, y0=0.0, depth=20.0, spacing=50.0,
               nx=13, ny=9):
    """Вертикальные скважины по демо-участку, интервалами толщ.

    Скважины стоят сеткой через `spacing` со сдвигом до пятой доли
    шага. Интервал - толща от кровли до подошвы в скважине,
    выклиненная толща в скважине не пишется.

    Возвращает [(номер скважины, код, от, до, вершины (2, 3))].
    """
    rng = np.random.default_rng(seed)
    out = []
    n = 0
    for j in range(ny):
        for i in range(nx):
            x = i * spacing + rng.uniform(-0.2, 0.2) * spacing
            y = j * spacing + rng.uniform(-0.2, 0.2) * spacing
            if not (0.0 <= x <= (nx - 1) * spacing
                    and 0.0 <= y <= (ny - 1) * spacing):
                continue
            n += 1
            top = float(demo_relief(x, y))
            prs, fine, lens = (float(v) for v in demo_thickness(x, y))
            bounds = np.cumsum([0.0, prs, fine, lens])
            bounds = np.round(np.minimum(np.append(bounds, depth),
                                         depth), 1)
            for k in range(4):
                a, b = float(bounds[k]), float(bounds[k + 1])
                if b - a < 0.05:
                    continue
                v = np.array([[x0 + x, y0 + y, top - a],
                              [x0 + x, y0 + y, top - b]])
                out.append(("C-%03d" % n, DEMO_CODES[k], a, b, v))
    return out


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


def outline_share(outline, xy):
    """Доля точек `xy` (N, 2) внутри контура `outline` (M, 2) в плане.

    Контур карьера из другой системы координат или с другого участка
    не накрывает ни одной скважины, и тела обрезались бы в ноль.
    По этой доле инструмент узнаёт такой контур заранее.
    """
    r = np.asarray(outline, dtype=float)
    p = np.asarray(xy, dtype=float).reshape(-1, 2)
    if len(r) < 3 or not len(p):
        return 0.0
    return float(np.mean(_inside(r[:, 0], r[:, 1], p[:, 0], p[:, 1])))


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
          levels=None, progress=None, holes=None, outline=None):
    """Поле каждой толщи, рельеф и классы на воксельной сетке.

    `rings` - контуры (N, 3) в любых плоскостях, `codes` - код толщи
    у каждого. `cell` - шаг сетки в плане, `cellz` - по вертикали.
    `holes` - скважины с интервалами (см. `sample_holes`), можно
    вместо контуров или вместе с ними. `outline` - контур (N, 2)
    в плане: горная масса только внутри него.

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
    holes = [h for h in (holes or []) if h]
    hole_codes = {c for h in holes for c, _p in h}
    all_codes = sorted(set(codes) | hole_codes, key=lambda v: str(v))
    cell = float(cell)
    cellz = float(cellz or cell)
    step = float(step or cell)
    hole_pts = [np.asarray(p, dtype=float)[:, :3] for h in holes
                for _c, p in h]
    if not rings and not hole_pts:
        raise ValueError("no data")
    allp = np.vstack(rings + hole_pts)
    x0, y0, zb = allp.min(axis=0)
    x1, y1, zt = allp.max(axis=0)
    span = float(max(x1 - x0, y1 - y0, zt - zb))
    if cap is None:
        cap = max(10.0 * step, 0.1 * span)
    tol = max(step, 0.01 * span)
    groups = plane_groups(rings, tol) if rings else []
    # по стволу опробуем мельче, чем по площади: слои в скважине
    # бывают в метр, а шаг по площади - десятки метров
    hstep = min(step, cellz)
    h_pts, h_vals, collars = sample_holes(holes, all_codes, hstep, cap)

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
    if len(collars):
        relief = np.vstack([relief, collars]) if len(relief) else collars
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
    if len(h_pts):
        pts.append(h_pts)
        for c in all_codes:
            vals[c].append(h_vals[c])
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
    spacing_h = hole_spacing(collars) if len(collars) else None
    target = step
    if frame["spacing"] is None and spacing_h:
        # Только скважины, без параллельных разрезов. В плане данные
        # редкие (скважины через десятки метров), по стволу густые
        # (через метр). Изотропная решётка дала бы либо бугор вокруг
        # каждой скважины, либо размытый по вертикали контакт. Поэтому
        # отметка растягивается так, что шаг по стволу становится
        # равен шагу между скважинами, и решётка дробится до половины
        # этого шага: контакт между скважинами идёт плавно, а в самих
        # скважинах держится до опробования.
        kz = spacing_h / max(hstep, 1e-9)
        frame = {"to": (lambda p, k=kz: np.asarray(p, dtype=float)
                        .reshape(-1, 3) * np.array([1.0, 1.0, k])),
                 "grid": frame["grid"], "spacing": None, "kz": kz}
        target = 0.5 * spacing_h
    to = frame["to"]
    q_pts = to(pts)
    q_all = np.vstack([q_pts, to(allp)])
    lo, hi = q_all.min(axis=0), q_all.max(axis=0)
    ext = np.maximum(hi - lo, 1e-9)
    grid3 = frame["grid"](ext)
    if levels is None:
        levels = auto_levels(ext, grid3, target)
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
    if outline is not None and len(outline) >= 3:
        hd = np.minimum(hd, hull_distance(np.asarray(outline)[:, :2],
                                          MX, MY))
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
            "spacing": frame["spacing"], "hole_spacing": spacing_h,
            "kz": frame.get("kz"), "holes": len(collars),
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
