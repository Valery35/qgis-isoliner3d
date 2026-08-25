# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Вариограмма: замер по данным и подбор модели.

Обратные расстояния взвешивают по одному расстоянию и о строении
изменчивости не знают ничего. Вариограмма это и есть замер строения:
насколько две пробы различаются в зависимости от того, как далеко они
друг от друга.

Три числа описывают её целиком. Самородковый эффект это разброс, который
не убывает даже у соседних проб: ошибка опробования и изменчивость мельче
сети. Порог это общий разброс данных. Длина связи это расстояние, после
которого пробы уже ничего не знают друг о друге.

Считается на голом NumPy: QGIS здесь не нужен, и проверить подбор можно
на данных с заранее известной моделью.
"""

import numpy as np

MODELS = ("spherical", "exponential", "gaussian")

# Направления замера. «Все» смешивает пары любого наклона, «в плане»
# берёт почти горизонтальные, «по вертикали» почти отвесные.
DIRECTIONS = ("all", "plan", "vert")

# Допуск по наклону: пара считается плановой, если её вертикальная
# составляющая меньше этой доли длины. Четверть это примерно
# пятнадцать градусов от горизонта.
_TOL = 0.25


def model(h, nugget, sill, rng, kind="spherical"):
    """Модельная вариограмма в точках `h`.

    `rng` это длина связи. У показательной и гауссовой модели связь
    формально не кончается никогда, поэтому длиной считают расстояние,
    на котором пройдено девяносто пять сотых порога: иначе числа
    разных моделей несравнимы.
    """
    h = np.asarray(h, dtype=float)
    a = max(float(rng), 1e-9)
    t = h / a
    if kind == "spherical":
        g = np.where(t < 1.0, 1.5 * t - 0.5 * t ** 3, 1.0)
    elif kind == "exponential":
        g = 1.0 - np.exp(-3.0 * t)
    elif kind == "gaussian":
        g = 1.0 - np.exp(-3.0 * t ** 2)
    else:
        raise ValueError("неизвестная модель вариограммы: %r" % (kind,))
    return float(nugget) + float(sill) * g


def experimental(points, values, nlags=12, anisotropy=1.0, max_dist=None,
                 max_pairs=2000000, seed=0, direction="all"):
    """Замер вариограммы по парам проб.

    Возвращает (середины интервалов, значения, число пар в каждом).
    Пара даёт половину квадрата разности значений, пары складываются
    по интервалам расстояния.

    Число пар растёт как квадрат числа проб: на десяти тысячах проб их
    пятьдесят миллионов. Выше `max_pairs` берётся случайная выборка пар,
    зерно задаётся, чтобы замер не менялся от запуска к запуску.

    `direction` разделяет замер по наклону пары. У пласта содержание
    меняется поперёк залежи быстро, а вдоль неё медленно, и одной
    вариограммой эти два строения не описать: общий замер усреднит
    их в одно и не опишет ни того, ни другого.
    """
    if direction not in DIRECTIONS:
        raise ValueError("неизвестное направление: %r" % (direction,))
    pts = np.asarray(points, dtype=float).copy()
    val = np.asarray(values, dtype=float)
    if len(pts) < 4:
        raise ValueError("для вариограммы нужно хотя бы четыре точки")
    aniso = float(anisotropy) or 1.0
    pts[:, 2] /= aniso

    n = len(pts)
    total = n * (n - 1) // 2
    rs = np.random.RandomState(int(seed))
    if total > int(max_pairs):
        # Случайная выборка пар: замер по ней тот же, а работа посильная.
        m = int(max_pairs)
        i = rs.randint(0, n, size=m * 2)
        j = rs.randint(0, n, size=m * 2)
        keep = i != j
        i, j = i[keep][:m], j[keep][:m]
    else:
        i, j = np.triu_indices(n, k=1)

    dv = pts[i] - pts[j]
    d = np.sqrt((dv ** 2).sum(axis=1))
    if direction != "all":
        with np.errstate(invalid="ignore", divide="ignore"):
            slope = np.abs(dv[:, 2]) / np.where(d > 0, d, np.nan)
        take = slope <= _TOL if direction == "plan" else slope >= 1 - _TOL
        take &= np.isfinite(slope)
        i, j, d = i[take], j[take], d[take]
    gam = 0.5 * (val[i] - val[j]) ** 2
    good = np.isfinite(d) & np.isfinite(gam)
    d, gam = d[good], gam[good]
    if not len(d):
        raise ValueError("ни одной пригодной пары")

    top = float(max_dist) if max_dist else float(np.percentile(d, 60))
    top = max(top, np.min(d[d > 0]) * 2 if (d > 0).any() else 1.0)
    edges = np.linspace(0.0, top, int(nlags) + 1)
    idx = np.clip(np.digitize(d, edges) - 1, 0, int(nlags) - 1)
    inside = d <= top
    idx, dd, gg = idx[inside], d[inside], gam[inside]

    cnt = np.bincount(idx, minlength=int(nlags))
    hsum = np.bincount(idx, weights=dd, minlength=int(nlags))
    gsum = np.bincount(idx, weights=gg, minlength=int(nlags))
    ok = cnt > 0
    return (hsum[ok] / cnt[ok], gsum[ok] / cnt[ok], cnt[ok])


def _sse(h, g, cnt, nugget, sill, rng, kind):
    """Взвешенная невязка подбора.

    Вес это число пар: ближние интервалы обычно населены гуще, и без
    веса подбор тянуло бы к редким дальним точкам замера.
    """
    diff = model(h, nugget, sill, rng, kind) - g
    return float(np.sum(cnt * diff ** 2))


def fit(h, g, cnt, kind="spherical"):
    """Подбор модели по замеру: самородок, порог, длина связи.

    Перебор по сетке с последующим уточнением. Метод грубый, но у него
    нет посторонних минимумов и он не зависит от начального приближения,
    а вариограмма подбирается один раз на набор данных.
    """
    h = np.asarray(h, dtype=float)
    g = np.asarray(g, dtype=float)
    cnt = np.asarray(cnt, dtype=float)
    if not len(h):
        raise ValueError("пустой замер вариограммы")
    top = float(np.max(g))
    hmax = float(np.max(h))
    best = None
    for c0 in np.linspace(0.0, top, 11):
        for c in np.linspace(max(top - c0, 1e-9) * 0.4,
                             max(top - c0, 1e-9) * 1.6, 11):
            for a in np.linspace(hmax * 0.15, hmax * 2.0, 16):
                s = _sse(h, g, cnt, c0, c, a, kind)
                if best is None or s < best[0]:
                    best = (s, c0, c, a)
    _s, c0, c, a = best
    # уточнение вокруг найденного
    for _ in range(3):
        step = (top / 20.0, top / 20.0, hmax / 20.0)
        for c0t in (c0 - step[0], c0, c0 + step[0]):
            for ct in (c - step[1], c, c + step[1]):
                for at in (a - step[2], a, a + step[2]):
                    if c0t < 0 or ct <= 0 or at <= 0:
                        continue
                    s = _sse(h, g, cnt, c0t, ct, at, kind)
                    if s < best[0]:
                        best = (s, c0t, ct, at)
        _s, c0, c, a = best
    return {"kind": kind, "nugget": float(c0), "sill": float(c),
            "range": float(a), "sse": float(best[0])}


def assemble(plan, vert, variance):
    """Рабочая модель из двух замеров: плановая длина, вертикальный
    самородок и анизотропия как отношение длин.

    Самородок берётся из вертикального замера не из вкусовщины.
    В плане пар ближе шага сети нет вовсе: скважины стоят через сто
    сорок метров, и первый интервал начинается там же. Самородок
    из такого замера это продолжение прямой к нулю через пустоту,
    и он выходит завышенным в разы. По стволу пары есть с трёх метров,
    и там самородок виден по-настоящему.

    Порог доводится до разброса данных: сумма самородка и порога это
    то, к чему вариограмма выходит на больших расстояниях.
    """
    out = dict(plan)
    if vert:
        out["nugget"] = float(vert.get("nugget", 0.0))
        rp = float(plan.get("range", 1.0)) or 1.0
        out["anisotropy"] = float(vert.get("range", rp)) / rp
    else:
        out["anisotropy"] = 1.0
    out["sill"] = max(float(variance) - out["nugget"], 1e-9)
    return out


def auto_fit(points, values, nlags=12, anisotropy=1.0, max_dist=None,
             max_pairs=2000000, kinds=MODELS, direction="all"):
    """Замер и подбор лучшей из моделей.

    Лучшей считается та, у которой взвешенная невязка меньше. Разница
    между моделями обычно невелика, и выбор вида важнее не сам по себе,
    а тем, как ведёт себя модель у нуля: гауссова даёт слишком гладкое
    поле там, где данные шумят.
    """
    h, g, cnt = experimental(points, values, nlags=nlags,
                             anisotropy=anisotropy, max_dist=max_dist,
                             max_pairs=max_pairs, direction=direction)
    best = None
    for kind in kinds:
        got = fit(h, g, cnt, kind=kind)
        if best is None or got["sse"] < best["sse"]:
            best = got
    best = dict(best)
    best["direction"] = direction
    best["n_pairs"] = int(np.sum(cnt))
    best["lags"] = h
    best["gamma"] = g
    best["counts"] = cnt
    return best
