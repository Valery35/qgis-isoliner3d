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


def nice_ticks(lo, hi, want=5):
    """Деления по круглым числам внутри размаха.

    Края не добавляются: деление на краю охвата обычно некруглое,
    а некруглая подпись хуже, чем её отсутствие.
    """
    lo, hi = float(lo), float(hi)
    if hi < lo:
        lo, hi = hi, lo
    if hi - lo <= 0:
        return [lo]
    step = nice_step(hi - lo, want)
    first = np.ceil(lo / step) * step
    out = []
    x = first
    while x <= hi + step * 1e-9:
        out.append(float(round(x, 10)))
        x += step
    return out or [lo, hi]


def tick_label(value):
    """Подпись деления без хвоста нулей."""
    v = float(value)
    if abs(v - round(v)) < 1e-9:
        return "%d" % int(round(v))
    return ("%.6f" % v).rstrip("0").rstrip(".")


# Потолок по линиям сетки. Сетка гуще самой сцены читать не помогает,
# а рисуется долго: на мелком шаге легко запросить миллион линий.
MAX_GRID_LINES = 4000


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


def box_edges(lo, hi):
    """Двенадцать рёбер короба по охвату сцены."""
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


def tick_marks(lo, hi, want=5, length=None):
    """Штрихи на рёбрах короба.

    Возвращает список (ось, значение, начало, конец). Штрих стоит
    на ребре и уходит наружу: внутрь он лез бы сквозь тело.
    """
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
    out = []
    for axis in range(3):
        other = away[axis]
        for val in nice_ticks(lo[axis], hi[axis], want):
            a = list(lo)
            a[axis] = val
            b = list(a)
            b[other] = lo[other] - ln
            out.append((axis, val, tuple(a), tuple(b)))
    return out
