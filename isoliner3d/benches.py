# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Отчёт по горизонтам блочной модели: руда, вскрыша, металл, деньги.

Модель режется горизонтальными уступами заданной высоты от базовой
отметки. Блок, который пересекает границу уступа, делится между
уступами по доле своей высоты: блок 10 м на уступах по 5 м отдаёт
каждому половину. Блок без высоты (только центр) целиком уходит
в уступ своего центра.

Руда - блоки с содержанием не ниже бортового, остальное вскрыша.
Блок без содержания считается вскрышей, их число пишется отдельно.
Металл = руда, т * содержание * единица: для процентов единица 0.01
и металл в тоннах, для г/т единица 1 и металл в граммах. Выручка =
металл * извлечение * цена единицы металла, затраты = горная масса
* стоимость выемки + руда * стоимость переработки.

Идея отчёта из модуля QGIS 3D Studio, расчёт свой. Без QGIS и Qt.
"""
import math

import numpy as np

UNITS = (0.01, 1.0)       # % - металл в тоннах, г/т - в граммах


def bench_edges(lo, hi, height, base=0.0):
    """Границы уступов, накрывающие отметки lo..hi, сверху вниз."""
    h = float(height)
    if not h > 0:
        raise ValueError("bench height must be positive")
    k0 = math.floor((float(np.nanmin(lo)) - base) / h + 1e-9)
    k1 = math.ceil((float(np.nanmax(hi)) - base) / h - 1e-9)
    if k1 <= k0:
        k1 = k0 + 1
    return [(base + (k + 1) * h, base + k * h)
            for k in range(k1 - 1, k0 - 1, -1)]


def report(z_lo, z_hi, vol, grade, dens, height, base=0.0, cutoff=0.0,
           unit=0.01, price=0.0, recovery=1.0, mine_cost=0.0,
           proc_cost=0.0):
    """Строки отчёта по уступам сверху вниз и итог.

    z_lo, z_hi - низ и верх блока (равны, если у блока только центр),
    vol - объём блока, м³, grade - содержание (NaN - нет), dens -
    плотность, т/м³. Возвращает (строки, итог): словари с полями
    z_top, z_bot, n_blocks, vol, ton, ore_t, waste_t, grade, metal,
    strip, revenue, cost, margin.
    """
    lo = np.asarray(z_lo, dtype=float)
    hi = np.asarray(z_hi, dtype=float)
    lo, hi = np.minimum(lo, hi), np.maximum(lo, hi)
    vol = np.asarray(vol, dtype=float)
    g = np.asarray(grade, dtype=float)
    dens = np.broadcast_to(np.asarray(dens, dtype=float), vol.shape)
    ton = vol * dens
    is_ore = np.isfinite(g) & (g >= float(cutoff))
    span = hi - lo
    rows = []
    for top, bot in bench_edges(lo, hi, height, base):
        flat = span <= 1e-9
        share = np.where(
            flat, ((lo >= bot) & (lo < top)).astype(float),
            np.clip(np.minimum(hi, top) - np.maximum(lo, bot), 0.0, None)
            / np.where(flat, 1.0, span))
        sel = share > 0
        if not sel.any():
            continue
        t = ton * share
        ore = np.where(is_ore, t, 0.0)
        metal = float(np.sum(ore[is_ore] * g[is_ore])) * unit
        rows.append(_row(top, bot, int(sel.sum()), float(np.sum(vol * share)),
                         float(t.sum()), float(ore.sum()), metal, unit,
                         price, recovery, mine_cost, proc_cost))
    tot = _row(rows[0]["z_top"] if rows else 0.0,
               rows[-1]["z_bot"] if rows else 0.0,
               int(len(vol)), float(sum(r["vol"] for r in rows)),
               float(sum(r["ton"] for r in rows)),
               float(sum(r["ore_t"] for r in rows)),
               float(sum(r["metal"] for r in rows)), unit, price,
               recovery, mine_cost, proc_cost)
    return rows, tot


def _row(top, bot, n, vol, ton, ore_t, metal, unit, price, recovery,
         mine_cost, proc_cost):
    waste = ton - ore_t
    revenue = metal * recovery * price
    cost = ton * mine_cost + ore_t * proc_cost
    return {"z_top": top, "z_bot": bot, "n_blocks": n, "vol": vol,
            "ton": ton, "ore_t": ore_t, "waste_t": waste,
            "grade": metal / (ore_t * unit) if ore_t > 0 else None,
            "metal": metal,
            "strip": waste / ore_t if ore_t > 0 else None,
            "revenue": revenue, "cost": cost, "margin": revenue - cost}
