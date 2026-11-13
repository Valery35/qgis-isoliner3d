# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""2.18 Интервалы по стволу скважины: описание и расчёт без QGIS.

Ствол - линия с Z, глубина по стволу - её длина от начала. Куски
ствола, равные интервалы и композиты считает wells.py, здесь поля,
сведение стволов с таблицей и сборка двух выходов: кусков ствола
и середин интервалов.
"""

import numpy as np

from ..toolspec import N_, Param, Result, Tool, ToolError

MODES = ("table", "equal", "composite")


def _numv(v):
    """Число из атрибута или None: пустое и текст не превращаются в 0."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _key(v):
    """Номер скважины как строка без пробелов по краям."""
    return "" if v is None else str(v).strip()


def trace_xyz(parts):
    """Вершины ствола (N, 3) и глубины по стволу как длина.

    У составной линии берётся первая часть: ствол один.
    """
    if not parts:
        return None, None
    pts = np.asarray(parts[0], dtype=float).reshape(-1, 3)
    if len(pts) < 2 or not np.isfinite(pts).all():
        return None, None
    md = np.concatenate([[0.0], np.cumsum(np.linalg.norm(
        np.diff(pts, axis=0), axis=1))])
    return pts, md


def run(values, report):
    """Расчёт 2.18: интервалы по стволам TRACES."""
    from .. import colnames, wells

    mode = int(values.get("MODE") or 0)
    tab = values.get("TABLE")
    meta_t = values.get("@TRACES") or {}
    meta_b = values.get("@TABLE") or {}
    length = float(values.get("LENGTH") or 1.0)
    picked = list(values.get("VALUES") or [])

    t_hole = colnames.resolve(values.get("T_HOLE") or "",
                              list(meta_t.get("fields") or []), "hole")
    if not t_hole:
        raise ToolError(N_("Не найдено поле номера скважины в стволах: "
                           "выберите его."))
    f_hole = values.get("F_HOLE") or ""
    f_from = values.get("F_FROM") or ""
    f_to = values.get("F_TO") or ""
    tn = list(meta_b.get("fields") or [])
    if tab is not None:
        f_hole = colnames.resolve(f_hole, tn, "hole")
        f_from = colnames.resolve(f_from, tn, "from")
        f_to = colnames.resolve(f_to, tn, "to")
        report.info(N_("Поля таблицы: скважина %s, от %s, до %s."),
                    *[(f or "-") for f in (f_hole, f_from, f_to)])
    if mode in (0, 2) and (tab is None or not (f_hole and f_from
                                               and f_to)):
        raise ToolError(N_("Для этого способа нужна таблица интервалов "
                           "с полями скважины, начала и конца."))

    traces = {}
    for item in values["TRACES"]:
        pts, md = trace_xyz(item.get("parts") or [])
        if pts is not None:
            traces[_key((item.get("attrs") or {}).get(t_hole))] = (pts, md)
    if not traces:
        raise ToolError(N_("Стволов с отметками не нашлось."))

    fields = [("hole", "string"), ("from_m", "double"), ("to_m", "double"),
              ("length_m", "double")]
    names = [nm for nm, _t in fields]
    carry = []
    if mode == 0:
        # поля таблицы переходят как есть, со своим типом
        for nm in tn:
            if nm in (f_hole, f_from, f_to) or nm in names:
                continue
            fields.append((nm, "copy:TABLE"))
            names.append(nm)
            carry.append(nm)
    elif mode == 2:
        if not picked:
            picked = [nm for nm in tn
                      if nm in (meta_b.get("numeric") or [])
                      and nm not in (f_from, f_to)]
        for nm in picked:
            if nm not in names:
                fields.append((nm, "double"))
                names.append(nm)
        fields.append(("cover", "double"))

    rows = {}
    n_bad = 0
    if tab is not None and mode in (0, 2):
        for item in tab:
            at = item.get("attrs") or {}
            a, b = _numv(at.get(f_from)), _numv(at.get(f_to))
            if a is None or b is None or b <= a:
                n_bad += 1
                continue
            rows.setdefault(_key(at.get(f_hole)), []).append((a, b, at))

    out = Result(fields, geometry="line", name=N_("Интервалы"))
    mids = Result(fields, geometry="point", name=N_("Середины интервалов"))

    def put(name, pts, md, a, b, extra):
        seg = wells.segment(pts, md, a, b)
        if len(seg) < 2:
            return 0
        row = [name, float(a), float(b), float(b - a)] + extra
        out.add({"points": seg}, row)
        mid = wells.at_depth(pts, md, [(a + b) / 2.0])[0]
        mids.add({"xyz": mid}, row)
        return 1

    made = beyond = 0
    for name, (pts, md) in traces.items():
        if report.canceled():
            break
        end = float(md[-1])
        if mode == 0:
            for a, b, at in rows.get(name, []):
                # хорды узлов короче дуги на доли миллиметра, поэтому
                # проба до самого забоя кончается чуть дальше линии:
                # это не ошибка данных, предупреждать не о чем
                if b > end + 0.05:
                    beyond += 1
                made += put(name, pts, md, a, min(b, end),
                            [at.get(c) for c in carry])
        elif mode == 1:
            for a, b in wells.equal_intervals(end, length):
                made += put(name, pts, md, a, b, [])
        else:
            r = rows.get(name, [])
            if not r:
                continue
            vv = np.array([[_numv(at.get(c)) if _numv(at.get(c))
                            is not None else np.nan for c in picked]
                           for _a, _b, at in r], dtype=float)
            iv, cv, cover = wells.composite(
                [x[0] for x in r], [x[1] for x in r], vv, length, end=end)
            for k, (a, b) in enumerate(iv):
                if cover[k] <= 0:
                    continue
                extra = [None if not np.isfinite(x) else float(x)
                         for x in cv[k]] + [float(cover[k])]
                made += put(name, pts, md, a, b, extra)
    report.info(N_("Стволов: %d, интервалов: %d."), len(traces), made)
    if n_bad:
        report.warn(N_("Строк таблицы без начала и конца или с концом не "
                       "дальше начала: %d, они пропущены."), n_bad)
    if beyond:
        report.warn(N_("Интервалов глубже забоя: %d. Они обрезаны по "
                       "забою: проверьте глубину скважины в устьях."),
                    beyond)
    orphan = sorted(set(rows) - set(traces))
    if orphan:
        report.warn(N_("Интервалы без ствола: %d скважин, например %s."),
                    len(orphan), ", ".join(orphan[:5]))
    return {"OUTPUT": out, "OUTPUT_POINTS": mids}


SPEC = Tool(
    code="2.18", name="hole_intervals",
    title=N_("Интервалы по стволу скважины"), group="2",
    help=N_("Режет стволы скважин на интервалы тремя способами.\n\n"
            "**Интервалы из таблицы** кладут каждую строку опробования на "
            "ствол от своей глубины до своей со всеми полями таблицы. Так в "
            "сцене видно опробование как оно есть.\n\n"
            "**Равные интервалы** режут ствол на куски заданной длины от "
            "устья. Последний кусок до забоя короче, если длина не делится "
            "нацело.\n\n"
            "**Композиты по длине** режут так же и в каждом интервале считают "
            "среднее по таблице, взвешенное по длине пересечения с пробой. "
            "Проба 0-1 м по 10 г/т и проба 1-4 м по 2 г/т дают композит 0-4 м "
            "по 4 г/т, а простое среднее дало бы 6. Композит без единой пробы "
            "получает пустое значение, а не ноль: пропуск опробования не "
            "равен пустой породе. Поле cover показывает опробованную долю "
            "длины композита.\n\n"
            "На выходе два слоя. Куски ствола с Z показывают в сцене трубами, "
            "с толщиной и цветом по содержанию. Середины интервалов точками с "
            "теми же полями идут в 2.02, 2.06 и 2.07: так от опробования "
            "доходят до куба и оболочек."),
    params=[
        Param("TRACES", "lines", N_("Стволы скважин (линии с Z)"),
              N_("Стволы скважин: линии с Z от устья к забою, например "
                 "из 2.17. Глубина по стволу считается длиной линии "
                 "от её начала.")),
        Param("T_HOLE", "field", N_("Поле номера скважины в стволах"),
              N_("Поле номера скважины в стволах. По нему ствол "
                 "сводится со строками таблицы интервалов."),
              default="hole", optional=True, parent="TRACES"),
        Param("MODE", "enum", N_("Как резать"),
              N_("Интервалы из таблицы кладут каждую строку опробования "
                 "на ствол как есть. Равные интервалы режут ствол на "
                 "пробы заданной длины от устья до забоя. Композиты "
                 "режут так же и считают в каждом среднее по таблице, "
                 "взвешенное по длине."),
              default=0, options=(N_("Интервалы из таблицы"),
                                  N_("Равные интервалы заданной длины"),
                                  N_("Композиты по длине из таблицы"))),
        Param("TABLE", "table", N_("Таблица интервалов"),
              N_("Таблица интервалов: скважина, от, до и значения. Нужна "
                 "для интервалов из таблицы и для композитов."),
              optional=True),
        Param("F_HOLE", "field", N_("Поле номера скважины в таблице"),
              N_("Поле номера скважины в таблице интервалов. Номера "
                 "сводятся со стволами как текст."),
              default="hole", optional=True, parent="TABLE"),
        Param("F_FROM", "field", N_("Поле начала интервала"),
              N_("Поле начала интервала, метры по стволу от устья, "
                 "не отметка."),
              default="from_m", optional=True, parent="TABLE",
              numeric=True),
        Param("F_TO", "field", N_("Поле конца интервала"),
              N_("Поле конца интервала, метры по стволу. Строка с концом "
                 "не дальше начала пропускается."),
              default="to_m", optional=True, parent="TABLE", numeric=True),
        Param("VALUES", "field",
              N_("Поля для композитов (пусто - все числовые)"),
              N_("Числовые поля для композитов. Пусто - все числовые, "
                 "кроме начала и конца интервала."),
              optional=True, parent="TABLE", numeric=True, multiple=True),
        Param("LENGTH", "number", N_("Длина интервала, м"),
              N_("Длина равного интервала или композита, метры. "
                 "Последний интервал до забоя короче, если длина "
                 "не делится нацело."),
              default=1.0, minimum=0.01),
        Param("OUTPUT", "sink", N_("Интервалы"),
              N_("Интервалы: куски ствола с Z от начала до конца "
                 "интервала, с полями от, до, длина и значениями. "
                 "В сцене их показывают трубами с толщиной или цветом "
                 "по содержанию."),
              geometry="lines"),
        Param("OUTPUT_POINTS", "sink", N_("Середины интервалов"),
              N_("Середины интервалов: точки с Z и теми же полями. "
                 "Это вход для 2.02, 2.06 и 2.07."),
              geometry="points"),
    ],
    run=run)
