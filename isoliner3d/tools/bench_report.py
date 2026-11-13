# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""1.09 Отчёт по горизонтам: описание и расчёт без QGIS.

Блочная модель (1.03, 2.03 или чужая точками) режется уступами,
по каждому - горная масса, руда, вскрыша, содержание, металл,
коэффициент вскрыши, выручка, затраты, маржа. Ядро - benches.py.
Идея из модуля QGIS 3D Studio, расчёт свой.
"""

import numpy as np

from ..toolspec import N_, Param, Result, Tool, ToolError

FIELDS = [("bench", "string"), ("z_top", "double"), ("z_bot", "double"),
          ("n_blocks", "int"), ("vol", "double"), ("ton", "double"),
          ("ore_t", "double"), ("waste_t", "double"), ("grade", "double"),
          ("metal", "double"), ("strip", "double"), ("revenue", "double"),
          ("cost", "double"), ("margin", "double")]


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return np.nan
    return f if f == f else np.nan


def _pick(name, fields, *guess):
    """Поле, заданное человеком, или первое из угаданных, что есть."""
    if name:
        return name
    low = {f.lower(): f for f in fields}
    for g in guess:
        if g in low:
            return low[g]
    return ""


def run(values, report):
    """Расчёт 1.09: отчёт по уступам блочной модели values["BLOCKS"]."""
    from .. import benches

    meta = values.get("@BLOCKS") or {}
    fields = meta.get("fields") or []
    grade_f = values.get("GRADE") or ""
    if not grade_f:
        raise ToolError(N_("Нужно поле содержания."))
    vol_f = _pick(values.get("VOL"), fields, "vol", "volume")
    dens_f = _pick(values.get("DENS"), fields, "dens", "density")
    top_f = _pick(values.get("ZTOP"), fields, "z_from")
    bot_f = _pick(values.get("ZBOT"), fields, "z_to")
    dz_f = "" if top_f and bot_f else _pick("", fields, "dz")
    if not vol_f:
        raise ToolError(N_("Нет поля объёма блока (vol). Задайте его."))
    dens_c = float(values.get("DENSITY") or 0.0)
    report.info(N_("Поля: содержание %s, объём %s, плотность %s, "
                   "высота блока %s."), grade_f, vol_f,
                dens_f or "%.3f" % dens_c,
                "%s..%s" % (top_f, bot_f) if top_f and bot_f
                else (dz_f or N_("нет, по центру")))

    lo, hi, vol, g, dens = [], [], [], [], []
    n_nogeo = 0
    for item in values["BLOCKS"] or []:
        a = item.get("attrs") or {}
        xyz = item.get("xyz")
        z = np.nan if xyz is None else float(xyz[2])
        if top_f and bot_f:
            zt, zb = _num(a.get(top_f)), _num(a.get(bot_f))
        else:
            h = _num(a.get(dz_f)) if dz_f else 0.0
            h = 0.0 if h != h else abs(h)
            zt, zb = z + h / 2.0, z - h / 2.0
        v = _num(a.get(vol_f))
        if not (np.isfinite(zt) and np.isfinite(zb) and np.isfinite(v)):
            n_nogeo += 1
            continue
        d = _num(a.get(dens_f)) if dens_f else np.nan
        if not d > 0:
            d = dens_c
        lo.append(zb)
        hi.append(zt)
        vol.append(v)
        g.append(_num(a.get(grade_f)))
        dens.append(d)
    if n_nogeo:
        report.warn(N_("Блоков без отметки или объёма: %d, они пропущены."),
                    n_nogeo)
    if not vol:
        raise ToolError(N_("Блоков с отметкой и объёмом не нашлось."))
    dens = np.asarray(dens)
    if not (dens > 0).all():
        raise ToolError(N_("У %d блоков нет плотности: задайте поле "
                           "плотности или постоянную плотность."),
                        int(np.sum(~(dens > 0))))
    n_nog = int(np.sum(~np.isfinite(np.asarray(g))))
    if n_nog:
        report.warn(N_("Блоков без содержания: %d, они считаются "
                       "вскрышей."), n_nog)
    unit = benches.UNITS[int(values.get("UNIT") or 0)]
    try:
        rows, tot = benches.report(
            lo, hi, vol, g, dens, float(values.get("HEIGHT") or 10.0),
            float(values.get("BASE") or 0.0),
            float(values.get("CUTOFF") or 0.0), unit,
            float(values.get("PRICE") or 0.0),
            float(values.get("RECOVERY") or 100.0) / 100.0,
            float(values.get("MINE_COST") or 0.0),
            float(values.get("PROC_COST") or 0.0))
    except ValueError:
        raise ToolError(N_("Высота уступа должна быть больше нуля."))

    out = Result(FIELDS, geometry="none", name=N_("Отчёт по горизонтам"))
    for r in rows + [dict(tot, total=True)]:
        label = N_("Итого") if r.get("total") else \
            "%.2f..%.2f" % (r["z_top"], r["z_bot"])
        out.add(None, [label] + [r[k] for k, _t in FIELDS[1:]])
    report.info(N_("Уступов: %d. Горная масса %.0f т, руда %.0f т, "
                   "вскрыша %.0f т, металл %.6g."), len(rows), tot["ton"],
                tot["ore_t"], tot["waste_t"], tot["metal"])
    if tot["revenue"] or tot["cost"]:
        report.info(N_("Выручка %.0f, затраты %.0f, маржа %.0f."),
                    tot["revenue"], tot["cost"], tot["margin"])
    return {"OUTPUT": out}


SPEC = Tool(
    code="1.09", name="bench_report",
    title=N_("Отчёт по горизонтам"), group="1",
    help=N_("Режет блочную модель горизонтальными уступами и считает "
            "по каждому: горную массу, руду и вскрышу, среднее "
            "содержание руды, металл, коэффициент вскрыши, выручку, "
            "затраты и маржу. Последняя строка - итог.\n\n"
            "Уступы идут от базовой отметки с шагом высоты уступа, "
            "отчёт сверху вниз, как отрабатывают карьер. Блок, который "
            "пересекает границу уступа, делится между уступами по доле "
            "своей высоты. Высота блока берётся из полей верха и низа "
            "(z_from и z_to у 1.03), иначе из поля dz (у 2.03) вокруг "
            "отметки точки, иначе блок целиком уходит в уступ своего "
            "центра.\n\n"
            "Руда - блоки с содержанием не ниже бортового. Блок без "
            "содержания считается вскрышей, их число пишется "
            "в журнал.\n\n"
            "Металл зависит от единицы содержания: для процентов он "
            "в тоннах, для г/т - в граммах. Цена - за ту же единицу "
            "металла. Выручка - металл с учётом извлечения по цене, "
            "затраты - выемка всей горной массы плюс переработка руды. "
            "Нули в экономике - только тоннаж и металл.\n\n"
            "Поля объёма и плотности угадываются по именам vol и dens, "
            "как их пишут 1.03 и 2.03. Чужую модель Micromine, "
            "Datamine или Surpac сначала переведите в куб 2.20, потом "
            "в блоки 2.03, или задайте поля сами.\n\n"
            "Идея из модуля QGIS 3D Studio."),
    params=[
        Param("BLOCKS", "points", N_("Блочная модель (точки с Z)"),
              N_("Центры блоков точками с высотой: выход 1.03 или 2.03, "
                 "либо своя модель с полями объёма и содержания.")),
        Param("GRADE", "field", N_("Поле содержания"),
              N_("Содержание полезного компонента в блоке. Единица - "
                 "в поле ниже, от неё зависит единица металла."),
              parent="BLOCKS", numeric=True),
        Param("UNIT", "enum", N_("Единица содержания"),
              N_("Проценты - металл в тоннах. Г/т - металл в граммах. "
                 "Цена металла ниже задаётся за эту же единицу."),
              default=0, options=(N_("Проценты"), N_("Граммы на тонну"))),
        Param("CUTOFF", "number", N_("Бортовое содержание"),
              N_("Блоки с содержанием не ниже этого - руда, остальные "
                 "вскрыша."),
              default=0.0),
        Param("HEIGHT", "number", N_("Высота уступа, м"),
              N_("Высота уступа в метрах. Мельче уступ - подробнее "
                 "отчёт, но больше строк и дробнее блоки."),
              default=10.0, minimum=0.01),
        Param("BASE", "number", N_("Базовая отметка уступов, м"),
              N_("Отметка, от которой отсчитываются уступы: границы "
                 "уступов лежат на ней и через высоту уступа вверх "
                 "и вниз."),
              default=0.0),
        Param("VOL", "field", N_("Поле объёма блока (пусто - vol)"),
              N_("Объём блока, м³. Пусто - поле vol или volume, если "
                 "оно есть."),
              optional=True, parent="BLOCKS", numeric=True),
        Param("DENS", "field", N_("Поле плотности (пусто - dens)"),
              N_("Плотность блока, т/м³. Пусто - поле dens или density, "
                 "если оно есть, иначе постоянная ниже."),
              optional=True, parent="BLOCKS", numeric=True),
        Param("DENSITY", "number", N_("Плотность, т/м³, если поля нет"),
              N_("Плотность для блоков, у которых нет поля плотности "
                 "или оно пустое."),
              default=2.7, minimum=0.0),
        Param("ZTOP", "field", N_("Поле верха блока (пусто - z_from)"),
              N_("Отметка верха блока. Пусто - поле z_from, если оно "
                 "есть. Без верха и низа высота блока берётся из поля "
                 "dz вокруг отметки точки."),
              optional=True, parent="BLOCKS", numeric=True, advanced=True),
        Param("ZBOT", "field", N_("Поле низа блока (пусто - z_to)"),
              N_("Отметка низа блока. Пусто - поле z_to, если оно "
                 "есть."),
              optional=True, parent="BLOCKS", numeric=True, advanced=True),
        Param("PRICE", "number", N_("Цена единицы металла"),
              N_("Цена тонны металла для процентов или грамма для г/т. "
                 "Ноль - без выручки."),
              default=0.0, minimum=0.0),
        Param("RECOVERY", "number", N_("Извлечение, %"),
              N_("Доля металла, которая доходит до продукта."),
              default=100.0, minimum=0.0, maximum=100.0),
        Param("MINE_COST", "number", N_("Выемка, за тонну горной массы"),
              N_("Стоимость выемки тонны горной массы: руды и вскрыши."),
              default=0.0, minimum=0.0),
        Param("PROC_COST", "number", N_("Переработка, за тонну руды"),
              N_("Стоимость переработки тонны руды. Вскрыша её не "
                 "несёт, только выемку."),
              default=0.0, minimum=0.0),
        Param("OUTPUT", "sink", N_("Отчёт по горизонтам"),
              N_("Таблица без геометрии: строка на уступ сверху вниз "
                 "и итог."),
              geometry="none"),
    ],
    run=run)
