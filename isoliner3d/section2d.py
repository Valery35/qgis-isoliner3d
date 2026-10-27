# -*- coding: utf-8 -*-
"""Разрез 2D-инверсии: ячейки разреза вертикальными гранями в пространстве.

Двумерная инверсия выдаёт значения на сетке разреза: точки профиля
в плане и отметки под каждой. Выгрузка для модуля - таблица x, y, z,
значение, где x и y лежат на профиле. Чтобы увидеть такой разрез
в 3D рядом со скважинами и кубами, каждая строка становится ячейкой:
вертикальной гранью вдоль профиля, от середины до предыдущей точки
профиля до середины до следующей и на полшага по высоте вверх и вниз.

Профиль бывает ломаным. Тогда ячейка у излома - две плоские грани,
до точки профиля и после неё, и разрез идёт по профилю без щелей.

Точки профиля упорядочиваются сами: от крайней точки вдоль главного
направления профиля к ближайшей ещё не взятой. Порядок строк в файле
тогда не важен. Разрыв профиля (пропуск съёмки, два куска одной
линии) узнаётся по шагу: если до следующей точки больше трёх обычных
шагов, ячейки через разрыв не тянутся.

Считается на голом NumPy, QGIS не нужен.
"""

import numpy as np

GAP_FACTOR = 3.0


def stations(x, y, decimals=3):
    """Точки профиля в плане и номер точки у каждой строки.

    Возвращает (xy точек (S, 2), номер точки (N,)). Строки одной
    вертикали сводятся в одну точку по координатам с округлением:
    выгрузка пишет координату с разной точностью в разных строках.
    """
    xy = np.column_stack([np.asarray(x, float), np.asarray(y, float)])
    key = np.round(xy, decimals)
    uniq, inv = np.unique(key, axis=0, return_inverse=True)
    sums = np.zeros_like(uniq)
    np.add.at(sums, inv.ravel(), xy)
    cnt = np.bincount(inv.ravel(), minlength=len(uniq))[:, None]
    return sums / cnt, inv.ravel()


def order(xy):
    """Порядок точек вдоль профиля.

    Начало - крайняя точка по главному направлению, дальше каждый раз
    ближайшая из ещё не взятых. Для прямого профиля это сортировка
    вдоль него, ломаный обходится по ходу.
    """
    n = len(xy)
    if n < 3:
        if n == 2:
            return np.array([0, 1])
        return np.arange(n)
    c = xy - xy.mean(axis=0)
    _u, _s, vt = np.linalg.svd(c, full_matrices=False)
    t = c @ vt[0]
    start = int(np.argmin(t))
    left = np.ones(n, dtype=bool)
    left[start] = False
    out = [start]
    cur = start
    for _ in range(n - 1):
        d = np.hypot(*(xy[left] - xy[cur]).T)
        k = np.flatnonzero(left)[int(np.argmin(d))]
        out.append(k)
        left[k] = False
        cur = k
    return np.array(out)


def _breaks(seq_xy):
    """Где профиль рвётся: шаг больше GAP_FACTOR обычных."""
    d = np.hypot(*np.diff(seq_xy, axis=0).T)
    if not len(d):
        return d.astype(bool)
    norm = float(np.median(d))
    return d > GAP_FACTOR * max(norm, 1e-9)


def column_edges(seq_xy):
    """Края ячеек в плане у каждой точки упорядоченного профиля.

    Возвращает (левый край (S, 2), правый край (S, 2)): середины
    до соседей, а у конца профиля или у разрыва - полшага наружу
    по своему звену.
    """
    s = len(seq_xy)
    left = np.empty((s, 2))
    right = np.empty((s, 2))
    if s == 1:
        left[0] = right[0] = seq_xy[0]
        return left, right
    br = _breaks(seq_xy)
    mid = 0.5 * (seq_xy[:-1] + seq_xy[1:])
    half = 0.5 * (seq_xy[1:] - seq_xy[:-1])
    for i in range(s):
        has_prev = i > 0 and not br[i - 1]
        has_next = i < s - 1 and not br[i]
        if has_prev:
            left[i] = mid[i - 1]
        elif has_next:
            left[i] = seq_xy[i] - half[i]
        else:
            left[i] = seq_xy[i]
        if has_next:
            right[i] = mid[i]
        elif has_prev:
            right[i] = seq_xy[i] + half[i - 1]
        else:
            right[i] = seq_xy[i]
    return left, right


def vertical_step(z, decimals=3):
    """Шаг по вертикали: наименьший разнос отметок одной вертикали."""
    u = np.unique(np.round(np.asarray(z, float), decimals))
    d = np.diff(u)
    d = d[d > 10.0 ** (-decimals)]
    return float(d.min()) if len(d) else 1.0


def cells(x, y, z, dz=None):
    """Ячейки разреза: по списку граней на каждую строку.

    `dz` - высота ячейки на строку или None: тогда шаг по вертикали
    общий, наименьший разнос отметок. Возвращает список той же длины,
    что строки: у каждой строки одна или две плоские грани, грань -
    массив (4, 3) вершин по кругу. Точка профиля одна, без соседей -
    граней нет.
    """
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    z = np.asarray(z, float)
    xy, st = stations(x, y)
    seq = order(xy)
    pos = np.empty(len(seq), dtype=np.int64)
    pos[seq] = np.arange(len(seq))
    seq_xy = xy[seq]
    left, right = column_edges(seq_xy)
    if dz is None:
        h = np.full(len(z), vertical_step(z) / 2.0)
    else:
        h = np.asarray(dz, float) / 2.0
        bad = ~np.isfinite(h) | (h <= 0)
        if bad.any():
            h = h.copy()
            h[bad] = vertical_step(z) / 2.0
    out = []
    for r in range(len(z)):
        p = pos[st[r]]
        a, c, b = left[p], seq_xy[p], right[p]
        lo, hi = z[r] - h[r], z[r] + h[r]
        faces = []
        for u, v in ((a, c), (c, b)):
            if np.hypot(*(v - u)) <= 1e-9:
                continue
            faces.append(np.array([[u[0], u[1], lo], [v[0], v[1], lo],
                                   [v[0], v[1], hi], [u[0], u[1], hi]]))
        # прямой участок: две грани в одной плоскости сливаются в одну
        if len(faces) == 2:
            d1 = c - a
            d2 = b - c
            cross = d1[0] * d2[1] - d1[1] * d2[0]
            if abs(cross) <= 1e-9 * max(np.hypot(*d1) * np.hypot(*d2),
                                        1e-12):
                faces = [np.array([[a[0], a[1], lo], [b[0], b[1], lo],
                                   [b[0], b[1], hi], [a[0], a[1], hi]])]
        out.append(faces)
    return out


def area(faces):
    """Площадь граней ячейки: длина по профилю на высоту."""
    s = 0.0
    for f in faces:
        w = np.hypot(f[1, 0] - f[0, 0], f[1, 1] - f[0, 1])
        s += w * (f[2, 2] - f[1, 2])
    return s
