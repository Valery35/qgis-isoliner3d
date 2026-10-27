# -*- coding: utf-8 -*-
"""Стволы скважин по инклинометрии и интервалы по стволу (2.17, 2.18).

Данные бурения приходят тремя таблицами: устья (координаты и отметка),
инклинометрия (глубина по стволу, азимут, угол) и интервалы
опробования (от, до, содержания). Ствол строится методом минимальной
кривизны: между двумя замерами он идёт дугой окружности, касательные
на концах которой совпадают с замерами. Это отраслевой стандарт,
им считают Micromine, Datamine, Surpac и Leapfrog.

Угол наклона записывают по-разному, и путать соглашения нельзя: ствол
уйдёт вверх или ляжет горизонтально. Поддержаны три записи:

    "dip_down_neg"  угол от горизонта, вниз отрицательный: -90 - вниз
                    отвесно (Micromine, Datamine, Surpac, Leapfrog);
    "dip_down_pos"  угол от горизонта, вниз положительный: 90 - вниз;
    "zenith"        зенитный угол от вертикали: 0 - вниз отвесно
                    (отечественная инклинометрия).

Азимут отсчитывается от севера сетки по часовой стрелке. Сближение
меридианов не учитывается: инклинометрию принято приводить к сетке
до загрузки.

Считается на голом NumPy, QGIS не нужен.
"""

import numpy as np

CONVENTIONS = ("dip_down_neg", "dip_down_pos", "zenith")


def inclination(angle, convention="dip_down_neg"):
    """Угол в зенитный: 0 - вниз отвесно, 90 - горизонтально."""
    a = np.asarray(angle, dtype=float)
    if convention == "dip_down_neg":
        return 90.0 + a
    if convention == "dip_down_pos":
        return 90.0 - a
    if convention == "zenith":
        return a
    raise ValueError("unknown convention %r" % (convention,))


def tangent(inc_deg, azi_deg):
    """Единичное направление ствола: X - восток, Y - север, Z - вверх."""
    i = np.radians(np.asarray(inc_deg, dtype=float))
    a = np.radians(np.asarray(azi_deg, dtype=float))
    return np.stack([np.sin(i) * np.sin(a), np.sin(i) * np.cos(a),
                     -np.cos(i)], axis=-1)


def _slerp(t1, t2, f):
    """Касательные на дуге между t1 и t2, доли f от 0 до 1."""
    c = float(np.clip(np.dot(t1, t2), -1.0, 1.0))
    beta = np.arccos(c)
    f = np.asarray(f, dtype=float)[:, None]
    if beta < 1e-9:
        v = t1 + f * (t2 - t1)
    else:
        s = np.sin(beta)
        v = (np.sin((1.0 - f) * beta) / s) * t1 + (np.sin(f * beta) / s) * t2
    return v / np.linalg.norm(v, axis=1)[:, None]


def _mc_step(t1, t2, dmd):
    """Шаг минимальной кривизны между двумя касательными."""
    c = float(np.clip(np.dot(t1, t2), -1.0, 1.0))
    beta = np.arccos(c)
    rf = 1.0 if beta < 1e-9 else (2.0 / beta) * np.tan(beta / 2.0)
    return 0.5 * dmd * (t1 + t2) * rf


def clean_survey(depth, azimuth, angle, convention="dip_down_neg"):
    """Замеры по возрастанию глубины, без повторов и пустот.

    Возвращает (глубины, зенитные углы, азимуты). Повтор глубины
    оставляет последний замер: в таблицах инклинометрии так обычно
    правят ошибочную строку.
    """
    d = np.asarray(depth, dtype=float)
    a = np.asarray(azimuth, dtype=float)
    inc = inclination(angle, convention)
    ok = np.isfinite(d) & np.isfinite(a) & np.isfinite(inc)
    d, a, inc = d[ok], a[ok], inc[ok]
    if not len(d):
        return d, inc, a
    order = np.argsort(d, kind="stable")
    d, a, inc = d[order], a[order], inc[order]
    keep = np.ones(len(d), dtype=bool)
    keep[:-1] = np.diff(d) > 1e-9
    return d[keep], inc[keep], a[keep]


def desurvey(collar, depth, azimuth, angle, max_depth=None,
             convention="dip_down_neg", step=1.0):
    """Ствол скважины: точки (N, 3) и глубины по стволу (N,).

    `collar` - устье (x, y, z). Замеры `depth`, `azimuth`, `angle`.
    Без замеров ствол отвесный. От устья до первого замера ствол идёт
    по первому замеру, после последнего - прямо по последнему.
    `max_depth` - глубина забоя, без неё ствол кончается на последнем
    замере. `step` - шаг узлов вдоль дуги, метры: по нему ствол
    рисуется и по нему же ищутся точки на заданных глубинах.
    """
    c = np.asarray(collar, dtype=float).reshape(3)
    d, inc, azi = clean_survey(depth, azimuth, angle, convention)
    if not len(d):
        d = np.array([0.0])
        inc = np.array([0.0])
        azi = np.array([0.0])
    end = float(max_depth) if max_depth is not None and \
        np.isfinite(max_depth) else float(d[-1])
    end = max(end, 0.0)
    # станции: устье, замеры внутри (0, end), забой
    md = [0.0]
    tg = [tangent(inc[0], azi[0])]
    for k in range(len(d)):
        if 1e-9 < d[k] < end - 1e-9:
            md.append(float(d[k]))
            tg.append(tangent(inc[k], azi[k]))
    if end > md[-1] + 1e-9:
        # Забой: на замере - его касательная, между замерами - точка
        # той же дуги, за последним замером - прямо по нему.
        nxt = np.nonzero(d >= end - 1e-9)[0]
        if len(nxt):
            k = int(nxt[0])
            t_k = tangent(inc[k], azi[k])
            if abs(d[k] - end) < 1e-9 or k == 0:
                t_end = t_k
            else:
                f = (end - md[-1]) / (d[k] - md[-1])
                t_end = _slerp(tg[-1], t_k, [f])[0]
        else:
            t_end = tg[-1]
        md.append(end)
        tg.append(t_end)
    step = max(float(step), 1e-3)
    pts = [c.copy()]
    mds = [0.0]
    for i in range(len(md) - 1):
        L = md[i + 1] - md[i]
        n = max(int(np.ceil(L / step)), 1)
        f = np.linspace(0.0, 1.0, n + 1)
        ts = _slerp(tg[i], tg[i + 1], f)
        p = pts[-1]
        for k in range(n):
            p = p + _mc_step(ts[k], ts[k + 1], L / n)
            pts.append(p)
            mds.append(md[i] + L * f[k + 1])
    return np.array(pts), np.array(mds)


def at_depth(points, mds, depth):
    """Точки ствола на заданных глубинах, линейно между узлами.

    Глубины вне ствола обрезаются по устью и забою.
    """
    p = np.asarray(points, dtype=float)
    m = np.asarray(mds, dtype=float)
    q = np.clip(np.asarray(depth, dtype=float), m[0], m[-1])
    return np.column_stack([np.interp(q, m, p[:, k]) for k in range(3)])


def segment(points, mds, d0, d1):
    """Кусок ствола от глубины d0 до d1: узлы внутри плюс концы."""
    p = np.asarray(points, dtype=float)
    m = np.asarray(mds, dtype=float)
    lo, hi = sorted((float(d0), float(d1)))
    inner = (m > lo) & (m < hi)
    ends = at_depth(p, m, [lo, hi])
    return np.vstack([ends[:1], p[inner], ends[1:]])


def equal_intervals(end, length, start=0.0):
    """Равные интервалы от `start` до забоя: (от, до) по строкам.

    Последний интервал короче, если длина не делится нацело: забой
    не выдумывается.
    """
    end, length, start = float(end), float(length), float(start)
    if length <= 0 or end <= start:
        return np.zeros((0, 2))
    edges = np.arange(start, end, length)
    edges = np.append(edges, end)
    if edges[-1] - edges[-2] < 1e-9:
        edges = edges[:-1]
    return np.column_stack([edges[:-1], edges[1:]])


def composite(froms, tos, values, length, start=0.0, end=None):
    """Композиты по длине: среднее, взвешенное по длине пересечения.

    `values` - (N,) или (N, K), пустые значения (NaN) в среднее
    не идут. Возвращает (интервалы (M, 2), значения (M, K),
    опробованная доля длины (M,)). Композит без единой пробы
    получает NaN и долю 0: дыра в опробовании видна, а не
    заполнена нулём.
    """
    f = np.asarray(froms, dtype=float)
    t = np.asarray(tos, dtype=float)
    v = np.asarray(values, dtype=float)
    if v.ndim == 1:
        v = v[:, None]
    lo = np.minimum(f, t)
    hi = np.maximum(f, t)
    if end is None:
        end = float(hi.max()) if len(hi) else start
    iv = equal_intervals(end, length, start)
    out = np.full((len(iv), v.shape[1]), np.nan)
    cover = np.zeros(len(iv))
    for k, (a, b) in enumerate(iv):
        ov = np.clip(np.minimum(hi, b) - np.maximum(lo, a), 0.0, None)
        sel = ov > 0
        if not sel.any():
            continue
        cover[k] = min(float(ov[sel].sum()) / (b - a), 1.0)
        for j in range(v.shape[1]):
            ok = sel & np.isfinite(v[:, j])
            w = ov[ok]
            if w.sum() > 0:
                out[k, j] = float((v[ok, j] * w).sum() / w.sum())
    return iv, out, cover


def demo(seed=1, x0=0.0, y0=0.0, z0=400.0, n_lines=5, per_line=4):
    """Демонстрационное бурение по золоторудной жиле.

    Жила - плоскость простиранием на северо-восток, падает на
    юго-восток под 60 градусов, мощность 3-8 м меняется по простиранию.
    Скважины стоят профилями вкрест простирания и бурятся навстречу
    падению под -60, по ходу ствол выполаживается и уходит по азимуту,
    как настоящий. Инклинометрия через 25 м с погрешностью прибора.
    Опробование: в зоне жилы пробы по метру, вне её по два, местами
    пропуски.

    Возвращает словарь: collars - список (скважина, x, y, z, забой),
    survey - (скважина, глубина, азимут, угол от горизонта, вниз
    отрицательный), assays - (скважина, от, до, au г/т), а также
    vein - (точка, нормаль, функция мощности) для проверки.
    """
    rng = np.random.default_rng(seed)
    strike = np.radians(45.0)
    dip = np.radians(60.0)
    along = np.array([np.sin(strike), np.cos(strike), 0.0])
    down_dip = np.array([np.sin(strike + np.pi / 2) * np.cos(dip),
                         np.cos(strike + np.pi / 2) * np.cos(dip),
                         -np.sin(dip)])
    normal = np.cross(along, down_dip)
    normal /= np.linalg.norm(normal)
    origin = np.array([x0 + 300.0, y0 + 300.0, z0 - 20.0])

    def thick(p):
        s = float((np.asarray(p) - origin) @ along)
        return 5.5 + 2.5 * np.sin(s / 60.0)

    collars, survey, assays = [], [], []
    hole = 0
    for li in range(n_lines):
        s = (li - (n_lines - 1) / 2.0) * 50.0
        base = origin + s * along
        for k in range(per_line):
            hole += 1
            name = "DH%03d" % hole
            # устье на висячем боку, тем дальше, чем глубже цель
            back = 40.0 + 45.0 * k
            c = base + back * np.array([down_dip[0], down_dip[1], 0.0]) \
                / np.hypot(down_dip[0], down_dip[1])
            c = c + rng.normal(0.0, 3.0, 3) * np.array([1, 1, 0])
            c[2] = z0 + 0.02 * (c[0] - x0) - 0.01 * (c[1] - y0) \
                + rng.normal(0.0, 0.5)
            azi0 = (np.degrees(strike) - 90.0) % 360.0 + rng.normal(0, 3)
            dip0 = -60.0 + rng.normal(0, 2)
            # глубина округлена заранее: иначе последняя проба
            # кончается глубже забоя, записанного в устье
            eoh = round(80.0 + 60.0 * k + rng.uniform(0, 20), 1)
            collars.append((name, float(c[0]), float(c[1]), float(c[2]),
                            float(eoh)))
            dd = np.arange(0.0, eoh + 1e-9, 25.0)
            for d in dd:
                f = d / 100.0
                survey.append((name, float(d),
                               float((azi0 + 6.0 * f
                                      + rng.normal(0, 0.3)) % 360.0),
                               float(dip0 + 4.0 * f + rng.normal(0, 0.2))))
            sv = [r for r in survey if r[0] == name]
            pts, mds = desurvey(c, [r[1] for r in sv], [r[2] for r in sv],
                                [r[3] for r in sv], max_depth=eoh,
                                step=0.5)
            dist = (pts - origin) @ normal
            # глубина по стволу, где ствол пересекает плоскость жилы
            cross = np.nonzero(np.diff(np.sign(dist)))[0]
            hit = float(mds[cross[0]]) if len(cross) else None
            d = 0.0
            while d < eoh - 1e-9:
                near = hit is not None and abs(d - hit) < 15.0
                ln = 1.0 if near else 2.0
                to = min(d + ln, eoh)
                if rng.uniform() < 0.04 and not near:
                    d = to          # пропуск опробования
                    continue
                mid = at_depth(pts, mds, [(d + to) / 2.0])[0]
                inside = abs(float((mid - origin) @ normal)) <= \
                    thick(mid) / 2.0
                if inside:
                    au = float(np.exp(rng.normal(np.log(4.0), 0.9)))
                else:
                    au = float(np.exp(rng.normal(np.log(0.03), 0.8)))
                assays.append((name, round(d, 2), round(to, 2),
                               round(au, 3)))
                d = to
    return {"collars": collars, "survey": survey, "assays": assays,
            "vein": (origin, normal, thick)}
