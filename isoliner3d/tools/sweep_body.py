# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""2.24 Тело вдоль выработки: описание и расчёт без QGIS.

Сечение протягивается по линии оси (sweep.py), здесь поля, отметка
для линий без Z, сечение из полей объекта и сборка результата.
"""

import math

import numpy as np

from ..toolspec import N_, Param, Result, Tool

PROFILES = ("arch", "rect", "circle")
ANCHORS = ("floor", "centre")


def _num(value):
    """Число из значения поля или None."""
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def run(values, report):
    """Расчёт 2.24 на линиях values["INPUT"]."""
    from .. import sweep
    from ..cleanup import shell_defects

    lines = values["INPUT"]
    elev_f = values.get("ELEV_FIELD") or ""
    elev = float(values.get("ELEV") or 0.0)
    kind = PROFILES[int(values.get("PROFILE") or 0)]
    width = float(values.get("WIDTH") or 5.0)
    width_f = values.get("WIDTH_FIELD") or ""
    height = float(values.get("HEIGHT") or 3.0)
    height_f = values.get("HEIGHT_FIELD") or ""
    rise = float(values.get("RISE") or 0.0)
    anchor = ANCHORS[int(values.get("ANCHOR") or 0)]
    segs = int(values.get("SEGMENTS") or 16)

    out = Result([("length", "double"), ("area", "double"),
                  ("volume", "double"), ("closed", "int")],
                 keep_source="INPUT", name=N_("Тела выработок"))
    total = max(len(lines), 1)
    n_body = n_bad = n_skip = 0
    vol_sum = 0.0
    sharp = []
    for k, ln in enumerate(lines):
        if report.canceled():
            break
        parts = ln.get("parts") or []
        if not parts:
            n_skip += 1
            continue
        attrs = ln.get("attrs") or {}
        w = _num(attrs.get(width_f)) if width_f else None
        h = _num(attrs.get(height_f)) if height_f else None
        w = w if w is not None and w > 0 else width
        h = h if h is not None and h > 0 else height
        z_ft = _num(attrs.get(elev_f)) if elev_f else None
        z_ft = elev if z_ft is None else z_ft
        prof = sweep.profile(kind, w, h, rise or None, segs)
        for part in parts:
            pts = np.array(part, dtype=float).reshape(-1, 3)
            if len(pts) and not np.isfinite(pts[:, 2]).all():
                pts[:, 2] = z_ft
            try:
                v, f, length, turn = sweep.sweep(pts, prof, anchor)
            except ValueError:
                n_skip += 1
                continue
            if turn > sweep.MAX_TURN:
                sharp.append(ln.get("id"))
            holes, _p = shell_defects(v, f)
            vol = sweep.signed_volume(v, f)
            out.add({"verts": v, "faces": f, "source": ln.get("id")},
                    [float(length), float(sweep.section_area(prof)),
                     float(vol), 1 if holes == 0 else 0])
            n_body += 1
            vol_sum += vol
            n_bad += 1 if holes else 0
        report.progress(100.0 * (k + 1) / total)
    report.info(N_("Тел: %d, объём всех %.1f м3."), n_body, vol_sum)
    if n_skip:
        report.warn(N_("Пропущено линий без двух разных вершин: %d."),
                    n_skip)
    if sharp:
        report.warn(N_("Излом оси круче 100° у объектов %s: тело там "
                       "самопересекается, объём завышен. Разбейте линию "
                       "на излом."), ", ".join(str(x) for x in sharp[:20]))
    if n_bad:
        report.warn(N_("Незамкнутых тел: %d."), n_bad)
    return {"OUTPUT": out}


SPEC = Tool(
    code="2.24", name="sweep_body",
    title=N_("Тело вдоль выработки"), group="2",
    help=N_("Строит замкнутое тело вдоль линии: сечение ставится "
            "поперёк оси в каждой её вершине и протягивается по ней, "
            "торцы закрываются. Штрек, камера, уклон, ствол, "
            "канава.\n\nСечение - прямоугольник со сводом, "
            "прямоугольник или круг. Ширина и высота задаются числом "
            "или полем линии, так у каждой выработки может быть своё "
            "сечение.\n\nПоперечник сечения всегда горизонтален: у "
            "наклонной выработки стенки остаются вертикальными, как у "
            "настоящего уклона. На изломе оси сечение ставится по "
            "биссектрисе и расширяется так, чтобы стенка не сужалась на "
            "повороте. Излом круче 100° даёт самопересечение тела, и об "
            "этом предупреждение в журнале.\n\nТела замкнуты: объём, "
            "пробы внутри, заполнение водой считают 2.11, 2.12, 2.14 и "
            "2.23."),
    params=[
        Param("INPUT", "lines", N_("Оси выработок (линии)"),
              N_("Оси выработок: линии. С высотой в геометрии берутся свои "
                 "отметки, без высоты - отметка из поля или постоянная ниже. "
                 "Маркшейдерская съёмка по почве, осевая линия проекта, "
                 "трасса канавы.")),
        Param("ELEV_FIELD", "field",
              N_("Поле отметки оси (для линий без Z)"),
              N_("Поле отметки оси для линий без Z. Пусто - постоянная "
                 "отметка из следующего поля."),
              optional=True, parent="INPUT", numeric=True),
        Param("ELEV", "number", N_("Отметка оси для линий без Z, м"),
              N_("Отметка оси для линий без Z, м. У линий с Z не нужна."),
              default=0.0),
        Param("PROFILE", "enum", N_("Сечение"),
              N_("Форма сечения. Прямоугольник со сводом - штрек и камера "
                 "калийного рудника. Прямоугольник - канава, траншея, камера "
                 "с плоской кровлей. Круг - ствол, тоннель комбайнового "
                 "проходческого щита."),
              default=0, options=(N_("Прямоугольник со сводом"),
                                  N_("Прямоугольник"), N_("Круг"))),
        Param("WIDTH", "number", N_("Ширина (у круга - диаметр), м"),
              N_("Ширина сечения, м, у круга - диаметр. Берётся проектная "
                 "или средняя по съёмке: объём растёт вместе с ней в той же "
                 "доле."),
              default=5.0, minimum=0.01),
        Param("WIDTH_FIELD", "field", N_("Поле ширины"),
              N_("Поле ширины, если сечения разные. Пусто или пустое "
                 "значение - ширина из поля выше."),
              optional=True, parent="INPUT", numeric=True),
        Param("HEIGHT", "number", N_("Высота стенок, м"),
              N_("Высота стенок, м. У прямоугольника - вся высота. У круга "
                 "не нужна."),
              default=3.0, minimum=0.01),
        Param("HEIGHT_FIELD", "field", N_("Поле высоты стенок"),
              N_("Поле высоты стенок. Пусто - высота из поля выше."),
              optional=True, parent="INPUT", numeric=True),
        Param("RISE", "number", N_("Подъём свода, м (0 - полуциркульный)"),
              N_("Подъём свода над стенками, м. Ноль - полуциркульный свод, "
                 "подъём в половину ширины. Меньший подъём - пологий свод."),
              default=1.0, minimum=0.0),
        Param("ANCHOR", "enum", N_("Ось в сечении"),
              N_("Где лежит ось в сечении. По почве - как снимают выработки "
                 "по почве. По центру - осевая линия проекта, ось ствола."),
              default=0, options=(N_("По почве"), N_("По центру"))),
        Param("SEGMENTS", "integer", N_("Граней на круге и своде"),
              N_("Число граней на круге и на своде. Больше - глаже, но "
                 "тяжелее сцена."),
              default=16, minimum=6, maximum=128),
        Param("OUTPUT", "sink", N_("Тела выработок"),
              N_("Тела выработок, по телу на линию, со всеми полями оси и "
                 "полями длины, площади сечения и объёма. Тела замкнуты, их "
                 "принимают 2.11, 2.12, 2.14 и 2.23."),
              geometry="polygonz"),
    ],
    run=run)
