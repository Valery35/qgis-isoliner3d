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
