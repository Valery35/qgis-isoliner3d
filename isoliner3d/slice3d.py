# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Срез куба вертикальной стенкой вдоль ломаной.

Куб целиком показать нельзя: снаружи видно только его оболочку. Оболочка
по отсечке показывает границу тела, воксели показывают занятые ячейки,
а стенка показывает само поле значений внутри, там где её провели.

Стенка строится узлами: вдоль ломаной берутся точки через заданный шаг,
по вертикали уровни куба, и в каждом узле значение выбирается из куба
трилинейно. Дальше это обычный меш с цветом в вершинах, и он живёт
в сцене как все остальные.

Считается на голом NumPy, QGIS здесь не нужен.
"""

import numpy as np


def sample_cube(vol, gt, z0, dz, x, y, z):
    """Значение куба в точках, трилинейно.

    Куб приходит в порядке (уровень, строка, столбец), как и везде.
    За краями куба возвращается пропуск: край не продлевается наружу,
    иначе стенка за границей данных выглядела бы данными.
    """
    vol = np.asarray(vol, dtype=float)
    nz, ny, nx = vol.shape
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    z = np.asarray(z, dtype=float)

    fx = (x - gt[0]) / gt[1] - 0.5
    fy = (y - gt[3]) / gt[5] - 0.5
    fz = (z - float(z0)) / float(dz)

    out = np.full(x.shape, np.nan)
    ok = (np.isfinite(fx) & np.isfinite(fy) & np.isfinite(fz)
          & (fx >= 0) & (fx <= nx - 1)
          & (fy >= 0) & (fy <= ny - 1)
          & (fz >= 0) & (fz <= nz - 1))
    if not ok.any():
        return out

    xi = np.clip(np.floor(fx[ok]).astype(int), 0, nx - 2 if nx > 1 else 0)
    yi = np.clip(np.floor(fy[ok]).astype(int), 0, ny - 2 if ny > 1 else 0)
    zi = np.clip(np.floor(fz[ok]).astype(int), 0, nz - 2 if nz > 1 else 0)
    tx = np.clip(fx[ok] - xi, 0.0, 1.0)
    ty = np.clip(fy[ok] - yi, 0.0, 1.0)
    tz = np.clip(fz[ok] - zi, 0.0, 1.0)
    x1 = np.minimum(xi + 1, nx - 1)
    y1 = np.minimum(yi + 1, ny - 1)
    z1 = np.minimum(zi + 1, nz - 1)

    acc = np.zeros(xi.shape)
    for dzi, wz in ((zi, 1.0 - tz), (z1, tz)):
        for dyi, wy in ((yi, 1.0 - ty), (y1, ty)):
            for dxi, wx in ((xi, 1.0 - tx), (x1, tx)):
                acc = acc + vol[dzi, dyi, dxi] * (wz * wy * wx)
    out[ok] = acc
    return out


def walk(line, step):
    """Точки вдоль ломаной через заданный шаг.

    Возвращает (точки, расстояние от начала). Шаг выдерживается вдоль
    всей ломаной, а не по отрезкам: на изломе стенка не должна рваться.
    """
    pts = np.asarray([(float(a), float(b)) for a, b in line], dtype=float)
    if len(pts) < 2:
        raise ValueError("для стенки нужно хотя бы два узла ломаной")
    seg = np.sqrt(((pts[1:] - pts[:-1]) ** 2).sum(axis=1))
    total = float(seg.sum())
    if total <= 0:
        raise ValueError("ломаная нулевой длины")
    step = max(float(step), total / 5000.0)
    s = np.arange(0.0, total + step * 0.5, step)
    s[-1] = min(s[-1], total)
    edges = np.concatenate([[0.0], np.cumsum(seg)])
    idx = np.clip(np.searchsorted(edges, s, side="right") - 1,
                  0, len(seg) - 1)
    t = (s - edges[idx]) / np.where(seg[idx] > 0, seg[idx], 1.0)
    xy = pts[idx] + (pts[idx + 1] - pts[idx]) * t[:, None]
    return xy, s


def section_mesh(vol, gt, z0, dz, line, step=None, nz_step=1):
    """Стенка вдоль ломаной: вершины, треугольники, значения.

    По вертикали берутся уровни куба, `nz_step` их прореживает.
    Треугольник, у которого хоть один узел без данных, не строится:
    иначе у стенки появился бы кусок из ничего, а на глаз он выглядел
    бы данными.
    """
    vol = np.asarray(vol, dtype=float)
    nz = vol.shape[0]
    if step is None:
        step = abs(gt[1])
    xy, _s = walk(line, step)
    ks = np.arange(0, nz, max(int(nz_step), 1))
    zs = float(z0) + ks * float(dz)

    n_a, n_z = len(xy), len(zs)
    X = np.repeat(xy[:, 0], n_z)
    Y = np.repeat(xy[:, 1], n_z)
    Z = np.tile(zs, n_a)
    val = sample_cube(vol, gt, z0, dz, X, Y, Z)
    verts = np.column_stack([X, Y, Z])

    # четырёхугольники между соседними столбцами и уровнями
    a = np.arange(n_a - 1)[:, None] * n_z + np.arange(n_z - 1)[None, :]
    v00 = a.ravel()
    v01 = v00 + 1
    v10 = v00 + n_z
    v11 = v10 + 1
    tris = np.concatenate([np.stack([v00, v10, v11], axis=1),
                           np.stack([v00, v11, v01], axis=1)], axis=0)
    keep = np.isfinite(val[tris]).all(axis=1)
    return verts, tris[keep].astype(np.int64), val
