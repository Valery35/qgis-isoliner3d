# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Булевы операции между оболочками: вычитание, объединение, пересечение.

Считается не по сеткам, а по ячейкам. Обе оболочки переводятся
в занятость общего куба, над занятостью выполняется логическая
операция, и результат снова превращается в тело.

Почему так, а не точной операцией над сетками. Точная режет
треугольники друг о друга, и на касаниях - а в геологии тела касаются
постоянно - регулярно даёт вырожденные грани и незамкнутый результат.
Объём по такому телу уже не взять, а объём здесь и есть цель. У ячеек
своя цена: результат ступенчатый, а точность ограничена ячейкой,
и ошибка идёт по ПЛОЩАДИ ПОВЕРХНОСТИ, не по объёму. Зато оболочка
замкнута всегда.

Занятость считается лучом вверх. Из центра каждой колонки куба идёт
вертикальный луч, собираются его пересечения с треугольниками
оболочки, отметки сортируются, и ячейки между первой и второй, третьей
и четвёртой и так далее лежат внутри. Это обычное правило чётности,
и работает оно ровно для замкнутой оболочки: у незамкнутой пересечений
выходит нечётное число, и внутренности у неё нет.
"""
import numpy as np


OPS = ("difference", "union", "intersection")


def shell_occupancy(verts, faces, gt, z0, dz, shape):
    """Занятость ячеек куба замкнутой оболочкой.

    Возвращает булев массив (nz, ny, nx): True там, где центр ячейки
    лежит внутри оболочки.
    """
    nz, ny, nx = (int(v) for v in shape)
    v = np.asarray(verts, dtype=float)
    f = np.asarray(faces, dtype=np.int64)
    # Луч сдвигается на ничтожную долю ячейки. Легший ровно на ребро
    # двух треугольников, он засчитывается обоим, чётность ломается,
    # и тело выходит пустым. У куба таких мест целая диагональ грани,
    # и центры ячеек ложатся на неё десятками.
    ex = abs(gt[1]) * 1e-6 * np.sqrt(2.0)
    ey = abs(gt[5]) * 1e-6 * np.sqrt(3.0)
    xs = gt[0] + gt[1] * (np.arange(nx) + 0.5) + ex
    ys = gt[3] + gt[5] * (np.arange(ny) + 0.5) + ey
    cols, zcut = [], []
    for tri in f:
        a, b, c = v[tri[0]], v[tri[1]], v[tri[2]]
        # Площадь в плане: вертикальная грань луч не пересекает,
        # а делить на её нулевую площадь нельзя.
        det = ((b[0] - a[0]) * (c[1] - a[1])
               - (c[0] - a[0]) * (b[1] - a[1]))
        if abs(det) < 1e-12:
            continue
        i0 = np.searchsorted(xs, min(a[0], b[0], c[0]), side="left")
        i1 = np.searchsorted(xs, max(a[0], b[0], c[0]), side="right")
        # Строки грида идут сверху вниз, поэтому по Y порядок обратный.
        j0 = np.searchsorted(-ys, -max(a[1], b[1], c[1]), side="left")
        j1 = np.searchsorted(-ys, -min(a[1], b[1], c[1]), side="right")
        if i1 <= i0 or j1 <= j0:
            continue
        gx, gy = np.meshgrid(xs[i0:i1], ys[j0:j1])
        px, py = gx.ravel(), gy.ravel()
        u = ((px - a[0]) * (c[1] - a[1])
             - (py - a[1]) * (c[0] - a[0])) / det
        w = ((py - a[1]) * (b[0] - a[0])
             - (px - a[0]) * (b[1] - a[1])) / det
        inside = (u >= 0.0) & (w >= 0.0) & (u + w <= 1.0)
        if not inside.any():
            continue
        z = (a[2] + u[inside] * (b[2] - a[2])
             + w[inside] * (c[2] - a[2]))
        jj, ii = np.divmod(np.flatnonzero(inside), i1 - i0)
        cols.append((jj + j0) * nx + (ii + i0))
        zcut.append(z)
    occ = np.zeros((nz, ny, nx), dtype=bool)
    if not cols:
        return occ
    col = np.concatenate(cols)
    zc = np.concatenate(zcut)
    order = np.lexsort((zc, col))
    col, zc = col[order], zc[order]
    # Границы колонок в отсортированном списке пересечений.
    starts = np.flatnonzero(np.r_[True, col[1:] != col[:-1]])
    ends = np.r_[starts[1:], len(col)]
    zlev = z0 + dz * np.arange(nz)
    flat = occ.reshape(nz, ny * nx)
    for s, e in zip(starts, ends):
        n = e - s
        if n < 2:
            continue
        zs = zc[s:e]
        n -= n % 2                      # нечётный хвост - не пара
        lo = zs[0:n:2]
        hi = zs[1:n:2]
        m = np.zeros(nz, dtype=bool)
        for k in range(len(lo)):
            m |= (zlev >= lo[k]) & (zlev <= hi[k])
        flat[:, col[s]] = m
    return occ


def points_inside(verts, faces, pts):
    """Какие точки лежат внутри замкнутой оболочки.

    То же правило чётности, что и у заливки ячеек, но луч пускается
    из самой точки: если выше неё оболочка пересекается нечётное число
    раз, точка внутри. Ячейки для этого не нужны, и ответ получается
    точный, а не с точностью до ячейки.

    Так блочная модель разбирается оболочкой: какие блоки попали
    в рудное тело, в зону отработки, в контур подсчёта.
    """
    v = np.asarray(verts, dtype=float)
    f = np.asarray(faces, dtype=np.int64)
    p = np.asarray(pts, dtype=float)
    if not len(p):
        return np.zeros(0, dtype=bool)
    # Точки упорядочены по X: у треугольника берётся только своя
    # полоса, иначе каждая грань опрашивала бы всю модель.
    order = np.argsort(p[:, 0], kind="stable")
    # Тот же сдвиг, что и у заливки ячеек: точка, легшая ровно
    # на ребро двух треугольников, засчиталась бы обоим, и чётность
    # объявила бы её снаружи. У куба на диагонали грани это каждая
    # вторая точка правильной сетки.
    scale = float(max(np.ptp(p[:, 0]), np.ptp(p[:, 1]), 1.0))
    px = p[order, 0] + scale * 1e-9 * np.sqrt(2.0)
    py = p[order, 1] + scale * 1e-9 * np.sqrt(3.0)
    pz = p[order, 2]
    above = np.zeros(len(p), dtype=np.int64)
    for tri in f:
        a, b, c = v[tri[0]], v[tri[1]], v[tri[2]]
        det = ((b[0] - a[0]) * (c[1] - a[1])
               - (c[0] - a[0]) * (b[1] - a[1]))
        if abs(det) < 1e-12:
            continue
        i0 = np.searchsorted(px, min(a[0], b[0], c[0]), side="left")
        i1 = np.searchsorted(px, max(a[0], b[0], c[0]), side="right")
        if i1 <= i0:
            continue
        sl = slice(i0, i1)
        ys = py[sl]
        near = ((ys >= min(a[1], b[1], c[1]))
                & (ys <= max(a[1], b[1], c[1])))
        if not near.any():
            continue
        idx = np.flatnonzero(near) + i0
        u = ((px[idx] - a[0]) * (c[1] - a[1])
             - (py[idx] - a[1]) * (c[0] - a[0])) / det
        w = ((py[idx] - a[1]) * (b[0] - a[0])
             - (px[idx] - a[0]) * (b[1] - a[1])) / det
        ok = (u >= 0.0) & (w >= 0.0) & (u + w <= 1.0)
        if not ok.any():
            continue
        idx = idx[ok]
        z = (a[2] + u[ok] * (b[2] - a[2]) + w[ok] * (c[2] - a[2]))
        hit = idx[z > pz[idx]]
        if len(hit):
            np.add.at(above, hit, 1)
    res = np.zeros(len(p), dtype=bool)
    res[order] = (above % 2) == 1
    return res


def tri_bbox(verts, faces):
    """Охват каждого треугольника: отсечка перед точным пересечением."""
    t = np.asarray(verts, dtype=float)[np.asarray(faces, dtype=np.int64)]
    return t.min(axis=1), t.max(axis=1)


def _segment_hits(verts, faces, a, b, bbox):
    """Параметры t в (0, 1), где отрезок a-b пересекает оболочку.

    Мёллер-Трумбор векторно по треугольникам, чей охват задевает
    охват отрезка. Точки на общем ребре двух треугольников приходят
    парами - они сливаются, иначе чётность ломается.
    """
    v = np.asarray(verts, dtype=float)
    f = np.asarray(faces, dtype=np.int64)
    lo, hi = bbox
    d = b - a
    s_lo, s_hi = np.minimum(a, b), np.maximum(a, b)
    near = np.all(hi >= s_lo, axis=1) & np.all(lo <= s_hi, axis=1)
    if not near.any():
        return np.zeros(0)
    tri = v[f[near]]
    p0, p1, p2 = tri[:, 0], tri[:, 1], tri[:, 2]
    e1, e2 = p1 - p0, p2 - p0
    h = np.cross(d, e2)
    det = np.einsum("ij,ij->i", e1, h)
    ok = np.abs(det) > 1e-14
    if not ok.any():
        return np.zeros(0)
    inv = np.zeros_like(det)
    inv[ok] = 1.0 / det[ok]
    s = a - p0
    u = np.einsum("ij,ij->i", s, h) * inv
    q = np.cross(s, e1)
    w = np.einsum("j,ij->i", d, q) * inv
    t = np.einsum("ij,ij->i", e2, q) * inv
    hit = ok & (u >= 0.0) & (w >= 0.0) & (u + w <= 1.0) \
        & (t > 0.0) & (t < 1.0)
    ts = np.sort(t[hit])
    if not len(ts):
        return ts
    keep = np.r_[True, np.diff(ts) > 1e-9]
    return ts[keep]


def polyline_inside_length(verts, faces, pts, bbox=None):
    """Длина ломаной внутри замкнутой оболочки.

    Каждый отрезок режется поверхностью: находятся его пересечения
    с треугольниками, точки сортируются вдоль отрезка, и дальше
    работает та же чётность, что у луча в points_inside. Внутри или
    снаружи начало ломаной, решает луч вверх один раз; дальше
    состояние передаётся по цепочке отрезков, и у каждой вершины
    не бывает своих шансов лечь на ребро.

    Возвращает (длина внутри, длина всего).
    """
    v = np.asarray(verts, dtype=float)
    f = np.asarray(faces, dtype=np.int64)
    p = np.asarray(pts, dtype=float)
    if len(p) < 2:
        return 0.0, 0.0
    if bbox is None:
        bbox = tri_bbox(v, f)
    inside = bool(points_inside(v, f, p[:1])[0])
    got = total = 0.0
    for k in range(len(p) - 1):
        a, b = p[k], p[k + 1]
        L = float(np.linalg.norm(b - a))
        if L <= 0.0:
            continue
        total += L
        ts = _segment_hits(v, f, a, b, bbox)
        edges = np.r_[0.0, ts, 1.0]
        for m in range(len(edges) - 1):
            if inside:
                got += (edges[m + 1] - edges[m]) * L
            inside = not inside
        # цикл выше переключил состояние на каждом краю, включая
        # последний фиктивный: возвращаем его на место
        inside = not inside
    return got, total


def combine(occ_a, occ_b, op):
    """Логическая операция над занятостью двух тел."""
    a = np.asarray(occ_a, dtype=bool)
    b = np.asarray(occ_b, dtype=bool)
    if op == "union":
        return a | b
    if op == "intersection":
        return a & b
    if op == "difference":
        return a & ~b
    raise ValueError("неизвестная операция: %s" % op)


def common_box(bounds_a, bounds_b, cell, op):
    """Общий куб для двух тел: охват, отметка низа и размеры.

    У вычитания охват берётся по первому телу: то, чего в нём нет,
    результату не принадлежит, и считать там нечего. У объединения
    нужен охват обоих. У пересечения хватило бы общей части, но она
    бывает пустой, и тогда отказ понятнее пустого грида.
    """
    ax0, ax1, ay0, ay1, az0, az1 = bounds_a
    bx0, bx1, by0, by1, bz0, bz1 = bounds_b
    if op == "difference":
        x0, x1, y0, y1, z0, z1 = ax0, ax1, ay0, ay1, az0, az1
    else:
        x0, x1 = min(ax0, bx0), max(ax1, bx1)
        y0, y1 = min(ay0, by0), max(ay1, by1)
        z0, z1 = min(az0, bz0), max(az1, bz1)
    pad = float(cell)
    x0, x1 = x0 - pad, x1 + pad
    y0, y1 = y0 - pad, y1 + pad
    z0, z1 = z0 - pad, z1 + pad
    nx = max(int(np.ceil((x1 - x0) / cell)), 1)
    ny = max(int(np.ceil((y1 - y0) / cell)), 1)
    nz = max(int(np.ceil((z1 - z0) / cell)) + 1, 1)
    gt = (x0, float(cell), 0.0, y0 + ny * cell, 0.0, -float(cell))
    return gt, z0, float(cell), (nz, ny, nx)


def cell_budget(shape):
    """Сколько ячеек выйдет: считать надо до выделения памяти."""
    nz, ny, nx = shape
    return int(nz) * int(ny) * int(nx)
