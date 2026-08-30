# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Спрямление: вертикаль отсчитывается от опорной поверхности.

В абсолютных отметках интерполяция идёт поперёк напластования. У пласта
со складкой соседняя по вертикали проба лежит в другой пачке, а своя
по пласту оказывается далеко, и связь считается не вдоль залежи, а через
неё. Никакой анизотропией это не лечится: она правит масштаб, а не форму.

Спрямление переводит отметку в отсчёт от кровли или подошвы. В таких
координатах пласт горизонтален, соседи по спрямлённой вертикали лежат
в той же пачке, и интерполяция идёт вдоль напластования. Посчитав куб,
отметки возвращают обратно.

Два способа отсчёта. От одной поверхности - разность в метрах: годится,
когда мощность выдержана. Между двумя - доля от кровли до подошвы, ноль
на кровле и единица на подошве: так сопоставляются пачки разной мощности,
и раздув не размазывает связь.

Считается на голом NumPy, QGIS здесь не нужен.
"""

import numpy as np


def sample(x, y, surf, gt):
    """Отметка поверхности в точках, билинейно.

    За краем грида возвращается пропуск: край не продлевается наружу,
    иначе спрямление за границей данных считалось бы от выдумки.
    """
    from .mesh3d import sample_bilinear
    return sample_bilinear(np.asarray(surf, dtype=float), gt,
                           np.asarray(x, dtype=float),
                           np.asarray(y, dtype=float))


def mask_cube(vol, gt, z0, dz, top, top_gt, bottom, bottom_gt):
    """Погасить ячейки куба вне заданных поверхностей.

    Резать построенное поздно: оболочка, воксели и объём по блочной
    модели считались бы по разным телам и разошлись бы между собой.
    Гася ячейки до построения, получаем согласие всех трёх.

    Возвращает копию куба, где лишние ячейки стали пропуском.
    """
    vol = np.asarray(vol, dtype=float)
    if top is None and bottom is None:
        return vol
    nz, ny, nx = vol.shape
    xs = gt[0] + (np.arange(nx) + 0.5) * gt[1]
    ys = gt[3] + (np.arange(ny) + 0.5) * gt[5]
    gx, gy = np.meshgrid(xs, ys)
    flat_x, flat_y = gx.ravel(), gy.ravel()
    zt = sample(flat_x, flat_y, top, top_gt) if top is not None else None
    zb = (sample(flat_x, flat_y, bottom, bottom_gt)
          if bottom is not None else None)
    out = vol.copy()
    for k in range(nz):
        zk = float(z0) + k * float(dz)
        keep = np.ones(flat_x.shape, dtype=bool)
        if zt is not None:
            keep &= np.isfinite(zt) & (zk <= zt)
        if zb is not None:
            keep &= np.isfinite(zb) & (zk >= zb)
        layer = out[k]
        layer[~keep.reshape(ny, nx)] = np.nan
    return out


def keep_between(x, y, z, top, top_gt, bottom, bottom_gt):
    """Отбор по поверхностям: что лежит между кровлей и подошвой.

    Одной отметкой этого не заменить: кровля и подошва меняются
    по площади, а отметка плоская. Так отсекают всё выше дневного
    рельефа или всё вне пласта.

    Любая из поверхностей может отсутствовать: тогда с той стороны
    не отсекается ничего. Границы включаются, иначе пропала бы сама
    кровля. Точка, под которой поверхности нет, не остаётся: пропустить
    её значит показать данные там, где отсечка не работала, а на глаз
    одно от другого не отличить.
    """
    z = np.asarray(z, dtype=float)
    keep = np.isfinite(z)
    if top is not None:
        zt = sample(x, y, top, top_gt)
        keep &= np.isfinite(zt) & (z <= zt)
    if bottom is not None:
        zb = sample(x, y, bottom, bottom_gt)
        keep &= np.isfinite(zb) & (z >= zb)
    return keep


def to_flat(x, y, z, roof, gt, floor=None):
    """Абсолютная отметка в спрямлённую.

    Без `floor` это разность с опорной поверхностью в метрах.
    С `floor` это доля мощности: ноль на кровле, единица на подошве.

    Точка, для которой поверхности нет, возвращается пропуском.
    """
    z = np.asarray(z, dtype=float)
    top = sample(x, y, roof, gt)
    if floor is None:
        return z - top
    bot = sample(x, y, floor, gt)
    thick = top - bot
    with np.errstate(invalid="ignore", divide="ignore"):
        out = (top - z) / np.where(np.abs(thick) > 1e-9, thick, np.nan)
    return out


def from_flat(x, y, f, roof, gt, floor=None):
    """Спрямлённая отметка обратно в абсолютную.

    Нужна, чтобы вернуть посчитанный куб в настоящие отметки: иначе он
    остался бы картинкой в выдуманных координатах.
    """
    f = np.asarray(f, dtype=float)
    top = sample(x, y, roof, gt)
    if floor is None:
        return top + f
    bot = sample(x, y, floor, gt)
    thick = top - bot
    bad = ~(np.abs(thick) > 1e-9)
    return np.where(bad, np.nan, top - f * thick)


def flat_span(x, y, z, roof, gt, floor=None):
    """Размах спрямлённой и абсолютной отметки и число спрямлённых точек.

    Сравнивать эти два числа осмысленно только для проб внутри пласта:
    там у лёгшего плоско размах спрямлённой много меньше. По всему
    стволу спрямлённая уходит на всю глубину скважины, и размах у неё
    выходит больше абсолютной - это не признак неудачи.
    """
    f = to_flat(x, y, z, roof, gt, floor=floor)
    ok = np.isfinite(f)
    z = np.asarray(z, dtype=float)
    zo = np.isfinite(z)
    if not ok.any() or not zo.any():
        return None
    return (float(np.ptp(f[ok])), float(np.ptp(z[zo])), int(ok.sum()))


def mask_keep(xs, ys, mask, gt, level=0.5):
    """Отбор точек по растровой маске: внутри там, где значение выше.

    Полигон задаёт границу линией, а маска - площадью. Так удобнее,
    когда границу считал инструмент: зону, вероятность, контур
    отработки. Рисовать её потом полигоном значит терять точность
    на ровном месте.

    Точка вне охвата маски отбрасывается: маска про неё ничего
    не говорит, и считать такую точку своей нельзя. Пропуск в маске
    это «снаружи» по той же причине.
    """
    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)
    m = np.asarray(mask, dtype=float)
    if m.ndim != 2 or not m.size:
        return np.zeros(xs.shape, dtype=bool)
    x0, dx, _rx, ytop, _ry, dy = [float(v) for v in gt]
    if abs(dx) < 1e-30 or abs(dy) < 1e-30:
        return np.zeros(xs.shape, dtype=bool)
    cols = np.floor((xs - x0) / dx).astype(np.int64)
    rows = np.floor((ys - ytop) / dy).astype(np.int64)
    ok = ((cols >= 0) & (cols < m.shape[1])
          & (rows >= 0) & (rows < m.shape[0]))
    out = np.zeros(xs.shape, dtype=bool)
    if not ok.any():
        return out
    val = m[rows[ok], cols[ok]]
    out[ok] = np.isfinite(val) & (val >= float(level))
    return out
