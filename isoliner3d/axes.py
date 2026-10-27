# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Координатный короб: рёбра, деления и подписи.

Сцена без делений не даёт размера: тело выглядит одинаково и на сто
метров, и на двадцать километров. Короб ставит масштаб на вид, а по
вертикали ещё и отметки, что для разреза важнее всего.

Деления идут по круглым числам: подпись 250 читается сразу, а 247.3
надо разбирать. Шаг берётся единицей, двойкой или пятёркой на степень
десяти - других круглых шагов не бывает.

Считается на голом NumPy, QGIS здесь не нужен.
"""

import numpy as np


def nice_step(span, want=5):
    """Круглый шаг, дающий примерно `want` делений на размах."""
    span = abs(float(span))
    if span <= 0 or not np.isfinite(span):
        return 1.0
    raw = span / max(int(want), 1)
    mag = 10.0 ** np.floor(np.log10(raw))
    for m in (1.0, 2.0, 5.0, 10.0):
        if raw <= m * mag * 1.0000001:
            return m * mag
    return 10.0 * mag


# Потолок по делениям на ось: шаг, заданный руками на большом охвате,
# дал бы тысячи подписей.
MAX_TICKS = 200


def nice_ticks(lo, hi, want=5, step=0.0):
    """Деления по круглым числам внутри размаха.

    Края не добавляются: деление на краю охвата обычно некруглое,
    а некруглая подпись хуже, чем её отсутствие. `step` больше нуля -
    шаг, заданный человеком. Если он дал бы больше MAX_TICKS делений,
    он удваивается.
    """
    lo, hi = float(lo), float(hi)
    if hi < lo:
        lo, hi = hi, lo
    if hi - lo <= 0:
        return [lo]
    step = float(step) if step and float(step) > 0 else \
        nice_step(hi - lo, want)
    while (hi - lo) / step > MAX_TICKS:
        step *= 2.0
    first = np.ceil(lo / step) * step
    out = []
    x = first
    while x <= hi + step * 1e-9:
        out.append(float(round(x, 10)))
        x += step
    return out or [lo, hi]


def tick_label(value, mult=1.0):
    """Подпись деления без хвоста нулей.

    `mult` - множитель подписи: 0.001 даёт километры, -1 - глубину
    положительными числами при отметках ниже нуля. Деления стоят там
    же, меняется только текст.
    """
    v = float(value) * float(mult)
    v = 0.0 if abs(v) < 1e-12 else v
    if abs(v - round(v)) < 1e-9:
        return "%d" % int(round(v))
    return ("%.6f" % v).rstrip("0").rstrip(".")


# Потолок по линиям сетки. Сетка гуще самой сцены читать не помогает,
# а рисуется долго: на мелком шаге легко запросить миллион линий.
MAX_GRID_LINES = 4000


def custom_range(lo, hi, rng):
    """Охват короба: свой, заданный человеком, или по сцене.

    `rng` - (xmin, xmax, ymin, ymax, zmin, zmax) или None. Пара, где
    наибольшее не больше наименьшего, не задана: по этой оси охват
    остаётся от сцены. Так можно задать одни отметки, не трогая план.
    """
    lo = [float(v) for v in lo]
    hi = [float(v) for v in hi]
    if not rng:
        return tuple(lo), tuple(hi)
    for k in range(3):
        a, b = float(rng[2 * k]), float(rng[2 * k + 1])
        if b > a:
            lo[k], hi[k] = a, b
    return tuple(lo), tuple(hi)


def grid_lines(lo, hi, step=0.0, planes=("floor",)):
    """Координатная сетка на выбранных плоскостях короба.

    `planes` это набор из «floor» (пол) и «walls» (две ближние
    к началу вертикальные стены). Шаг ноль означает круглый шаг
    от размаха, а не отсутствие сетки.

    Возвращает список отрезков (начало, конец).
    """
    lo = [float(v) for v in lo]
    hi = [float(v) for v in hi]
    planes = tuple(planes or ())
    if not planes:
        return []
    span = max(hi[k] - lo[k] for k in range(3)) or 1.0
    st = float(step) if float(step) > 0 else nice_step(span, 8)
    # Мельче не рисуем: пересчитываем шаг так, чтобы линий было
    # не больше потолка.
    while True:
        n = 0
        for k in range(3):
            n += int((hi[k] - lo[k]) / st) + 1
        if n * 2 <= MAX_GRID_LINES or st > span:
            break
        st *= 2.0

    def seq(k):
        out, x = [], np.ceil(lo[k] / st) * st
        while x <= hi[k] + st * 1e-9:
            out.append(float(x))
            x += st
        return out

    segs = []
    if "floor" in planes:
        z = lo[2]
        for x in seq(0):
            segs.append(((x, lo[1], z), (x, hi[1], z)))
        for y in seq(1):
            segs.append(((lo[0], y, z), (hi[0], y, z)))
    if "walls" in planes:
        for x in seq(0):
            segs.append(((x, lo[1], lo[2]), (x, lo[1], hi[2])))
        for z in seq(2):
            segs.append(((lo[0], lo[1], z), (hi[0], lo[1], z)))
        for y in seq(1):
            segs.append(((lo[0], y, lo[2]), (lo[0], y, hi[2])))
        for z in seq(2):
            segs.append(((lo[0], lo[1], z), (lo[0], hi[1], z)))
    return segs


def north_arrow(lo, hi, size=None):
    """Стрелка севера рядом с коробом: древко и наконечник.

    В проекции карты север это возрастание Y, туда стрелка и смотрит.
    Стоит она за коробом сбоку: поперёк тела она мешала бы читать
    форму, а без неё на повёрнутой сцене легко потерять стороны света.

    Возвращает список отрезков (начало, конец).
    """
    lo = [float(v) for v in lo]
    hi = [float(v) for v in hi]
    span = max(hi[0] - lo[0], hi[1] - lo[1], 1.0)
    ln = float(size) if size else span * 0.18
    x = lo[0] - span * 0.12
    y0 = lo[1]
    z = lo[2]
    tip = (x, y0 + ln, z)
    wing = ln * 0.28
    return [((x, y0, z), tip),
            (tip, (x - wing * 0.6, y0 + ln - wing, z)),
            (tip, (x + wing * 0.6, y0 + ln - wing, z))]


EDGE_MODES = ("all", "axes", "none")

# Стороны короба для подписей: какое из четырёх параллельных рёбер
# несёт деления оси. Индекс 0 - наименьшая координата, 1 - наибольшая.
# «x» - ребро оси X: (сторона по Y, сторона по Z); «y» - ребро оси Y:
# (сторона по X, сторона по Z); «z» - вертикальное ребро: (сторона по
# X, сторона по Y).
ORIGIN_SIDES = {"x": (0, 0), "y": (0, 0), "z": (0, 0)}


def near_sides(lo, hi, cam):
    """Рёбра для подписей, ближние к камере.

    Подписи у начала координат после поворота уходят за модель или
    за дальнюю стенку короба. Здесь плановые оси подписываются по ребру
    со стороны камеры, а вертикальная - по боковому ребру контура:
    ближнему по X и дальнему по Y. Тогда три ребра идут цепочкой:
    ось X, ближний угол, ось Y, боковой угол, ось Z, и вертикаль
    не встаёт перед моделью.

    Камера ниже середины короба переносит плановые подписи наверх.
    """
    lo = [float(v) for v in lo]
    hi = [float(v) for v in hi]
    mid = [(lo[k] + hi[k]) / 2.0 for k in range(3)]
    xn = 1 if float(cam[0]) > mid[0] else 0
    yn = 1 if float(cam[1]) > mid[1] else 0
    zb = 0 if float(cam[2]) >= mid[2] else 1
    return {"x": (yn, zb), "y": (xn, zb), "z": (xn, 1 - yn)}


def _pick(lo, hi, axis, side):
    return float(hi[axis]) if side else float(lo[axis])


def box_edges(lo, hi, mode="all", sides=None):
    """Рёбра короба по охвату сцены.

    `mode` "all" - все двенадцать, "axes" - три ребра из угла начала
    (наименьшие X, Y, Z), как оси на чертеже: короб не загораживает
    сцену. "none" - без рёбер, остаются сетка и деления.
    """
    if mode == "none":
        return []
    if mode == "axes":
        sd = sides or ORIGIN_SIDES
        x0, y0, z0 = [float(v) for v in lo]
        x1, y1, z1 = [float(v) for v in hi]
        ya, za = _pick(lo, hi, 1, sd["x"][0]), _pick(lo, hi, 2, sd["x"][1])
        xb, zb = _pick(lo, hi, 0, sd["y"][0]), _pick(lo, hi, 2, sd["y"][1])
        xc, yc = _pick(lo, hi, 0, sd["z"][0]), _pick(lo, hi, 1, sd["z"][1])
        return [((x0, ya, za), (x1, ya, za)), ((xb, y0, zb), (xb, y1, zb)),
                ((xc, yc, z0), (xc, yc, z1))]
    x0, y0, z0 = [float(v) for v in lo]
    x1, y1, z1 = [float(v) for v in hi]
    pts = [(x, y, z) for x in (x0, x1) for y in (y0, y1)
           for z in (z0, z1)]
    segs = []
    for i, a in enumerate(pts):
        for b in pts[i + 1:]:
            same = sum(1 for k in range(3) if abs(a[k] - b[k]) < 1e-12)
            if same == 2:
                segs.append((a, b))
    return segs


def tick_marks(lo, hi, want=5, length=None, steps=None, sides=None):
    """Штрихи на рёбрах короба.

    Возвращает список (ось, значение, начало, конец). Штрих стоит
    на ребре и уходит наружу: внутрь он лез бы сквозь тело. `steps` -
    шаг делений по X, Y, Z, ноль на оси - круглый шаг от размаха.
    """
    steps = tuple(steps) if steps else (0.0, 0.0, 0.0)
    lo = [float(v) for v in lo]
    hi = [float(v) for v in hi]
    span = max(hi[k] - lo[k] for k in range(3)) or 1.0
    ln = float(length) if length else span * 0.02
    # Куда уводить штрих наружу. По следующей оси нельзя: для Y
    # следующей выходит Z, и штрихи проваливаются под короб на всю
    # длину, утаскивая за собой подписи. Плановые оси уводим в плане,
    # вертикальную тоже в плане: отметку она обозначает высотой,
    # а не длиной штриха.
    away = {0: 1, 1: 0, 2: 0}
    sd = sides or ORIGIN_SIDES
    # точка ребра для каждой оси: две прочие координаты по сторонам
    fixed = {0: {1: sd["x"][0], 2: sd["x"][1]},
             1: {0: sd["y"][0], 2: sd["y"][1]},
             2: {0: sd["z"][0], 1: sd["z"][1]}}
    out = []
    for axis in range(3):
        other = away[axis]
        base = list(lo)
        for k, side in fixed[axis].items():
            base[k] = _pick(lo, hi, k, side)
        # наружу: от наибольшей стороны в плюс, от наименьшей в минус
        out_dir = 1.0 if fixed[axis][other] else -1.0
        for val in nice_ticks(lo[axis], hi[axis], want, steps[axis]):
            a = list(base)
            a[axis] = val
            b = list(a)
            b[other] = a[other] + out_dir * ln
            out.append((axis, val, tuple(a), tuple(b)))
    return out
