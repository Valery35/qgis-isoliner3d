# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Заполнение тела до заданного объёма (2.23).

Вопрос «до какой отметки дойдёт вода, если в выработку зайдёт столько
кубометров», «сколько войдёт в ёмкость до этой отметки», «где пройдёт
кровля, если срезать сверху такой объём». Ответ - горизонтальный
уровень, ниже которого (или выше которого) внутри тела ровно заданный
объём.

Тело режется на вертикальные колонки по сетке плана. В каждой колонке
луч вверх пересекает оболочку: вход, выход, вход, выход - это отрезки
внутри тела (boolean3d.column_cuts). Объём ниже уровня h - сумма по
колонкам длины отрезков ниже h на площадь колонки. Функция V(h)
кусочно-линейная и не убывает, поэтому уровень ищется делением
пополам, а отрезки считаются один раз: перебор уровней не трогает
сетку тела.

Точность по объёму ограничена шагом плана, по высоте - нет: отметка
уровня в колонке берётся точно, без ступенек по вертикали. Расхождение
объёма по колонкам и точного объёма оболочки печатается, по нему видно,
хватает ли шага.

Модуль Qt и QGIS не знает.
"""

import numpy as np


def intervals(col, zc):
    """Отрезки внутри тела по пересечениям колонок.

    col, zc - выход boolean3d.column_cuts. Возвращает (колонка, низ,
    верх) тремя массивами. Нечётный хвост колонки отбрасывается: у
    замкнутого тела его нет, а у рваного это не внутренность.
    """
    col = np.asarray(col, dtype=np.int64)
    zc = np.asarray(zc, dtype=float)
    if not len(col):
        z = np.zeros(0)
        return np.zeros(0, dtype=np.int64), z, z
    idx = np.arange(len(col))
    first = np.r_[True, col[1:] != col[:-1]]
    start = np.maximum.accumulate(np.where(first, idx, 0))
    rank = idx - start
    size = np.diff(np.r_[np.flatnonzero(first), len(col)])
    count = np.repeat(size, size)
    # вход - чётное пересечение, у которого в той же колонке есть выход
    ok = (rank % 2 == 0) & (rank + 1 < count)
    k = np.flatnonzero(ok)
    return col[k], zc[k], zc[k + 1]


def volume_below(lo, hi, area, h):
    """Объём внутри тела ниже уровня h."""
    lo = np.asarray(lo, dtype=float)
    hi = np.asarray(hi, dtype=float)
    return float(area * np.clip(np.minimum(hi, h) - lo, 0.0, None).sum())


def total_volume(lo, hi, area):
    """Весь объём тела по колонкам."""
    return float(area * np.clip(np.asarray(hi, dtype=float)
                                - np.asarray(lo, dtype=float),
                                0.0, None).sum())


def level_for_volume(lo, hi, area, target, from_top=False, tol=1e-6):
    """Уровень, ниже которого (from_top - выше которого) объём target.

    Возвращает (уровень, объём на этом уровне). Объём больше всего
    тела даёт верх (низ) тела и полный объём, ноль - низ (верх).
    """
    lo = np.asarray(lo, dtype=float)
    hi = np.asarray(hi, dtype=float)
    if not len(lo):
        raise ValueError("empty body")
    full = total_volume(lo, hi, area)
    zmin, zmax = float(lo.min()), float(hi.max())
    target = min(max(float(target), 0.0), full)
    if target >= full:
        return (zmin if from_top else zmax), full
    if target <= 0.0:
        return (zmax if from_top else zmin), 0.0
    want = full - target if from_top else target
    a, b = zmin, zmax
    span = max(zmax - zmin, 1e-12)
    for _ in range(200):
        mid = 0.5 * (a + b)
        if volume_below(lo, hi, area, mid) < want:
            a = mid
        else:
            b = mid
        if b - a <= tol * span:
            break
    h = 0.5 * (a + b)
    got = volume_below(lo, hi, area, h)
    return h, (full - got if from_top else got)


def plan_grid(bounds, cell=0.0, max_cols=400000):
    """Грид плана по охвату тела: (gt, ny, nx, сторона колонки).

    cell 0 - шаг по охвату, чтобы колонок было около max_cols.
    Меньший шаг, давший больше колонок, укрупняется до предела.
    """
    x0, x1, y0, y1 = (float(v) for v in bounds[:4])
    w = max(x1 - x0, 1e-9)
    hgt = max(y1 - y0, 1e-9)
    auto = (w * hgt / float(max_cols)) ** 0.5
    step = max(float(cell), auto) if cell > 0 else auto
    step = max(step, 1e-9)
    nx = max(1, int(np.ceil(w / step)))
    ny = max(1, int(np.ceil(hgt / step)))
    gt = (x0, step, 0.0, y0 + ny * step, 0.0, -step)
    return gt, ny, nx, step


def filled_occupancy(cols, lo, hi, gt, ny, nx, level, dz,
                     from_top=False):
    """Куб заполненной части: (занятость, z0 центра нижней ячейки, dz).

    Слои куба ставятся так, что уровень приходится на границу ячеек:
    крышка заполнения выходит ровной, без ступеньки у уровня.
    """
    cols = np.asarray(cols, dtype=np.int64)
    lo = np.asarray(lo, dtype=float)
    hi = np.asarray(hi, dtype=float)
    if from_top:
        bottom, top = level, float(hi.max())
    else:
        bottom, top = float(lo.min()), level
    nz = max(1, int(np.ceil((top - bottom) / dz)))
    if from_top:
        zc = bottom + dz * (np.arange(nz) + 0.5)
    else:
        zc = top - dz * (nz - np.arange(nz) - 0.5)
    occ = np.zeros((nz, ny * nx), dtype=bool)
    # пачками отрезков: у одной колонки их бывает несколько, поэтому
    # «или» копится через logical_or.at, а не присваиванием
    step = max(1, 4000000 // max(nz, 1))
    for k in range(0, len(cols), step):
        c = cols[k:k + step]
        hit = (zc[:, None] >= lo[None, k:k + step]) & \
            (zc[:, None] <= hi[None, k:k + step])
        np.logical_or.at(occ.T, c, hit.T)
    return occ.reshape(nz, ny, nx), float(zc[0]), dz
