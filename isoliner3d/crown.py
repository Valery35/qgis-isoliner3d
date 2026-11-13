# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Тело по контуру: плоский пол, стенки и свод от контура.

Контур в плане даёт камеру, линзу или купол. Пол - плоскость
по отметкам контура методом наименьших квадратов, так что небольшой
наклон и разброс отметок допустимы. Над полом стенки заданной высоты,
над ними свод. Высота свода в точке растёт с расстоянием до контура:
узкое место тела выходит низким, широкое высоким, гребень идёт по
средней линии фигуры, а не по одной оси.

Два профиля свода: линейный (подъём = крутизна * расстояние,
двускатная кровля) и округлый (дуга от стенки до гребня, как свод
камеры). Подъём можно ограничить сверху: тогда у широкого тела над
серединой плоская кровля.

Идея из модуля QGIS 3D Studio, расчёт свой. Без QGIS и Qt.
"""
import math

import numpy as np

MAX_CELLS = 250000


def fit_plane(ring):
    """Плоскость z = a*x + b*y + c по вершинам кольца, наименьшими
    квадратами. У вырожденного кольца - горизонталь на средней Z."""
    p = np.asarray(ring, dtype=float)
    c = p.mean(axis=0)
    d = p - c
    m = np.array([[d[:, 0] @ d[:, 0], d[:, 0] @ d[:, 1]],
                  [d[:, 0] @ d[:, 1], d[:, 1] @ d[:, 1]]])
    rhs = np.array([d[:, 0] @ d[:, 2], d[:, 1] @ d[:, 2]])
    if abs(np.linalg.det(m)) < 1e-12:
        return 0.0, 0.0, float(c[2])
    a, b = np.linalg.solve(m, rhs)
    return float(a), float(b), float(c[2] - a * c[0] - b * c[1])


def ring_area(ring):
    p = np.asarray(ring, dtype=float)
    x, y = p[:, 0], p[:, 1]
    return 0.5 * abs(float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)))


def boundary_distance(xs, ys, ring, chunk=20000):
    """Расстояние от точек (xs, ys) до ломаной кольца, точно по
    отрезкам. Порциями: память не растёт с числом точек."""
    p = np.asarray(ring, dtype=float)[:, :2]
    if not np.array_equal(p[0], p[-1], equal_nan=True):
        p = np.vstack([p, p[:1]])
    a, b = p[:-1], p[1:]
    ab = b - a
    ll = np.maximum((ab ** 2).sum(axis=1), 1e-24)
    pts = np.column_stack([xs, ys])
    out = np.empty(len(pts))
    for s in range(0, len(pts), chunk):
        q = pts[s:s + chunk, None, :]
        t = np.clip(((q - a) * ab).sum(axis=2) / ll, 0.0, 1.0)
        near = a + t[..., None] * ab
        out[s:s + chunk] = np.sqrt(((q - near) ** 2).sum(axis=2)).min(axis=1)
    return out


def crown_grids(ring, floor=None, wall=0.0, steep=0.45, rise_max=0.0,
                shape="linear", cell=0.0):
    """Гриды кровли и пола тела по контуру.

    ring - кольцо (n, 3) или (n, 2); floor - (a, b, c) плоскости пола
    или None: тогда плоскость по Z кольца. Возвращает (кровля, пол,
    привязка GDAL, сводка) или поднимает ValueError, если контур
    вырожден.
    """
    p = np.asarray(ring, dtype=float)
    if len(p) > 1 and np.array_equal(p[0], p[-1], equal_nan=True):
        p = p[:-1]
    if len(p) < 3 or ring_area(p) <= 0:
        raise ValueError("degenerate ring")
    plane = floor if floor is not None else fit_plane(p)
    x0, y0 = p[:, 0].min(), p[:, 1].min()
    x1, y1 = p[:, 0].max(), p[:, 1].max()
    span = max(x1 - x0, y1 - y0)
    step = float(cell) if cell and cell > 0 else span / 120.0
    nx = int(math.ceil((x1 - x0) / step)) + 2
    ny = int(math.ceil((y1 - y0) / step)) + 2
    while nx * ny > MAX_CELLS:
        step *= 1.25
        nx = int(math.ceil((x1 - x0) / step)) + 2
        ny = int(math.ceil((y1 - y0) / step)) + 2
    gx0 = x0 - step
    gy1 = y1 + step
    gt = (gx0, step, 0.0, gy1, 0.0, -step)
    from .mesh3d import polygon_mask
    inside = polygon_mask([[(float(a), float(b)) for a, b in p[:, :2]]],
                          gt, (ny, nx))
    if not inside.any():
        raise ValueError("cell too coarse")
    xs = gx0 + (np.arange(nx) + 0.5) * step
    ys = gy1 - (np.arange(ny) + 0.5) * step
    XX, YY = np.meshgrid(xs, ys)
    d = np.zeros((ny, nx))
    d[inside] = boundary_distance(XX[inside], YY[inside], p)
    a, b, c = plane
    fl = a * XX + b * YY + c
    dmax = float(d[inside].max())
    k = max(float(steep), 1e-6)
    if shape == "round":
        # дуга: у стенки вертикальна, у гребня горизонтальна; гребень
        # на высоте крутизна * полуширина, как у линейного свода
        u = np.clip(d / dmax, 0.0, 1.0)
        rise = k * dmax * np.sqrt(np.clip(u * (2.0 - u), 0.0, 1.0))
    else:
        rise = k * d
    if rise_max and rise_max > 0:
        rise = np.minimum(rise, float(rise_max))
    top = fl + float(wall) + rise
    top = np.where(inside, top, np.nan)
    bot = np.where(inside, fl, np.nan)
    info = {"plane": plane, "cell": step, "area": ring_area(p),
            "half_width": dmax, "rise": float(np.nanmax(rise[inside]))}
    return top, bot, gt, info
