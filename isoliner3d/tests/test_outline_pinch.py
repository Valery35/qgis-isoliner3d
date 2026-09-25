# -*- coding: utf-8 -*-
"""Выклинивание пласта к контуру на плане (2.08).

Случай из раскопа: борта нарисованы на двух разрезах крест-накрест,
а граница пласта в плане известна вместе с отметками. Если контур
подать только маской, он обрезает готовые кровлю и подошву, и у его
края тело уходит вниз отвесной стенкой. На самом контуре кровля
и подошва сходятся: мощность там нулевая, и тело к нему выклинивается.

Синтетика: линза в эллипсе 40 на 25 м, мощность в центре 4 м,
к краю падает до нуля. Средняя поверхность наклонная, отметки
у контура поэтому разные. Считается на голом NumPy, QGIS не нужен.
"""

import os
import sys

import numpy as np

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import mba, section3d          # noqa: E402
from isoliner3d.mesh3d import polygon_mask     # noqa: E402

CX, CY, A, B, H = 50.0, 30.0, 40.0, 25.0, 4.0
X0, X1, Y0, Y1 = 0.0, 100.0, 0.0, 60.0
CELL = 1.0


def _mid(x, y):
    return -100.0 + 0.02 * np.asarray(x) - 0.01 * np.asarray(y)


def _thick(x, y):
    r2 = ((np.asarray(x) - CX) / A) ** 2 + ((np.asarray(y) - CY) / B) ** 2
    return H * np.clip(1.0 - r2, 0.0, None)


def _section(xs, ys):
    """Контур на разрезе: кровля вперёд, подошва назад."""
    m, h = _mid(xs, ys), _thick(xs, ys)
    top = np.column_stack([xs, ys, m + h / 2.0])
    bot = np.column_stack([xs[::-1], ys[::-1], (m - h / 2.0)[::-1]])
    return np.vstack([top, bot])


def _rings():
    t = np.linspace(-1.0, 1.0, 41)
    along_x = _section(CX + A * t, np.full_like(t, CY))
    along_y = _section(np.full_like(t, CX), CY + B * t)
    return [along_x, along_y]


def _outline(n=24):
    """Контур пласта на плане с отметками, редкими вершинами."""
    a = np.linspace(0.0, 2.0 * np.pi, n + 1)
    x, y = CX + A * np.cos(a), CY + B * np.sin(a)
    return np.column_stack([x, y, _mid(x, y)])


def _grid():
    nx = int(np.ceil((X1 - X0) / CELL))
    ny = int(np.ceil((Y1 - Y0) / CELL))
    gt = (X0, CELL, 0.0, Y0 + ny * CELL, 0.0, -CELL)
    gx = X0 + CELL * (np.arange(nx) + 0.5)
    gy = (Y0 + ny * CELL) - CELL * (np.arange(ny) + 0.5)
    mx, my = np.meshgrid(gx, gy)
    return gt, nx, ny, mx, my


def _build(with_outline):
    """Кровля и подошва тем же путём, что в 2.08, маска по контуру."""
    top, bot, whose = section3d.roof_and_floor(_rings(), with_ring=True)
    ring = _outline()
    if with_outline:
        step = max(section3d.sample_step(top), CELL)
        edge, _n_flat = section3d.outline_points([ring], step)
        top, bot, whose = section3d.pinch_to_outline(top, bot, whose, edge)
    gt, nx, ny, mx, my = _grid()
    surf = []
    for pts in (top, bot):
        lat = mba.fit(pts[:, :2], pts[:, 2], lo=[X0, Y0], hi=[X1, Y1],
                      grid=(2, 2), levels=7, center="plane")
        surf.append(mba.surface_on_grid(lat, gt, nx, ny))
    keep = polygon_mask([[(float(x), float(y)) for x, y, _z in ring]],
                        gt, (ny, nx))
    t, b = [np.where(keep, s, np.nan) for s in surf]
    if with_outline:
        t, b, _n = section3d.close_negative(t, b)
    return t, b, keep, mx, my


def _rim(keep, mx, my, width=2.0):
    """Ячейки внутри контура не дальше `width` метров от него."""
    r = np.sqrt(((mx - CX) / A) ** 2 + ((my - CY) / B) ** 2)
    return keep & (r > 1.0 - width / B)


def test_mask_alone_leaves_a_wall():
    """Одна маска даёт стенку: так Вася и увидел в раскопе.

    Тест держит причину. Если однажды маска сама начнёт давать
    выклинивание, новый вход станет лишним, и смотреть надо сюда.
    """
    t, b, keep, mx, my = _build(False)
    m = t - b
    rim = _rim(keep, mx, my)
    assert np.nanmedian(m[rim]) > 1.0, np.nanmedian(m[rim])


def test_bed_pinches_out_to_the_outline():
    """С контуром мощность у края сходится к нулю."""
    t, b, keep, mx, my = _build(True)
    m = t - b
    rim = _rim(keep, mx, my)
    true = _thick(mx, my)
    assert np.nanmax(np.abs(m[rim] - true[rim])) < 0.6, \
        np.nanmax(np.abs(m[rim] - true[rim]))
    assert np.nanmedian(m[rim]) < 0.5, np.nanmedian(m[rim])


def test_sections_still_hold():
    """На разрезах кровля и подошва остаются там, где их провели."""
    t, b, keep, mx, my = _build(True)
    on = keep & ((np.abs(my - CY) < CELL) | (np.abs(mx - CX) < CELL))
    true_t = _mid(mx, my) + _thick(mx, my) / 2.0
    true_b = _mid(mx, my) - _thick(mx, my) / 2.0
    assert np.nanmax(np.abs(t[on] - true_t[on])) < 0.3
    assert np.nanmax(np.abs(b[on] - true_b[on])) < 0.3


def test_body_is_closer_to_the_true_shape():
    """С контуром тело ближе к настоящему, чем с одной маской.

    Между двумя разрезами крест-накрест данных нет: в четвертях
    мощность держат только разрезы и нулевой край. Поэтому объём
    сходится с формулой 0.5 * pi * A * B * H не точно, а в пределах
    пятой части. Наибольшая ошибка мощности при этом обязана упасть
    хотя бы вдвое: у маски она сидит на стенке по краю.
    """
    true_v = 0.5 * np.pi * A * B * H
    errs = []
    for with_outline in (False, True):
        t, b, keep, mx, my = _build(with_outline)
        m = t - b
        errs.append(float(np.nanmax(np.abs(m - _thick(mx, my))[keep])))
        if with_outline:
            vol = float(np.nansum(m)) * CELL * CELL
            assert abs(vol - true_v) / true_v < 0.2, (vol, true_v)
    assert errs[1] < 0.5 * errs[0], errs


def test_no_negative_thickness():
    t, b, _keep, _mx, _my = _build(True)
    m = t - b
    assert np.nanmin(m) >= 0.0, np.nanmin(m)


def test_outline_is_densified_along_its_edges():
    """Вершины контура редкие, точки идут по рёбрам с шагом."""
    ring = _outline(8)
    pts, n_flat = section3d.outline_points([ring], 2.0)
    assert n_flat == 0
    d = np.hypot(*np.diff(pts[:, :2], axis=0).T)
    assert d.max() <= 2.0 + 1e-6, d.max()
    # отметки по ребру идут линейно, а не скачком
    assert np.allclose(pts[:, 2], np.interp(
        np.arange(len(pts)), np.arange(len(pts)), pts[:, 2]))


def test_outline_without_heights_is_counted_not_used():
    """Контур без отметок в выклинивание не идёт, но считается.

    У двухмерного слоя отметки NaN. Подставить ноль значит положить
    границу пласта на уровень моря.
    """
    ring = _outline(8)
    flat = ring.copy()
    flat[:, 2] = np.nan
    pts, n_flat = section3d.outline_points([ring, flat], 2.0)
    assert n_flat == 1
    assert np.isfinite(pts).all()


def test_outline_disagreeing_with_a_section_is_found():
    """Контур и разрез сходятся в плане: отметки сверяются.

    Если контур на плане и край пласта на разрезе проведены на разных
    отметках, интерполяция усреднит их молча.
    """
    top, bot, whose = section3d.roof_and_floor(_rings(), with_ring=True)
    ring = _outline()
    ring[:, 2] += 1.5            # контур снят не с той отметки
    step = max(section3d.sample_step(top), CELL)
    edge, _n = section3d.outline_points([ring], step)
    t2, _b2, w2 = section3d.pinch_to_outline(top, bot, whose, edge)
    places, worst, _where = section3d.crossing_spread(
        t2, t2[:, 2], snap=step, owner=w2)
    assert places >= 1
    assert worst > 1.0, worst


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all outline tests passed")


if __name__ == "__main__":
    _run()
