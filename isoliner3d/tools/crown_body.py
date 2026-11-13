# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""2.26 Тела по контуру со сводом: описание и расчёт без QGIS.

Контур в плане даёт замкнутое тело: плоский пол, стенки и свод,
высота которого растёт с расстоянием до контура. Камера, линза,
купол, отвал по контуру основания. Ядро - crown.py. Идея из модуля
QGIS 3D Studio, расчёт свой.
"""

import numpy as np

from ..toolspec import N_, Param, Result, Tool, ToolError


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def run(values, report):
    """Расчёт 2.26: тело на каждый контур values["INPUT"]."""
    from .. import crown
    from ..cleanup import mesh_volume, shell_defects
    from ..mesh3d import bed_to_mesh_arrays

    meta = values.get("@INPUT") or {}
    if (meta.get("geometry") or "polygon") != "polygon":
        raise ToolError(N_("Нужен слой полигонов: контуры тел в плане."))
    floor_f = values.get("FLOOR_FIELD") or ""
    floor_c = float(values.get("FLOOR") or 0.0)
    wall = max(float(values.get("WALL") or 0.0), 0.0)
    steep = float(values.get("STEEP") or 0.45)
    if not steep > 0:
        raise ToolError(N_("Крутизна свода должна быть больше нуля."))
    rise_max = float(values.get("RISE_MAX") or 0.0)
    shape = "round" if int(values.get("SHAPE") or 0) == 1 else "linear"
    cell = float(values.get("CELL") or 0.0)

    out = Result([("volume", "double"), ("plan_area", "double"),
                  ("zmin", "double"), ("zmax", "double"),
                  ("rise", "double"), ("closed", "int")],
                 keep_source="INPUT", name=N_("Тела по контуру"))
    items = values["INPUT"] or []
    n_body = n_skip = n_open = 0
    vol_sum = 0.0
    for k, item in enumerate(items):
        if report.canceled():
            break
        attrs = item.get("attrs") or {}
        for ring in item.get("parts") or []:
            ring = np.asarray(ring, dtype=float).reshape(-1, 3)
            if len(ring) < 3:
                continue
            z_field = _num(attrs.get(floor_f)) if floor_f else None
            plane = None
            if z_field is not None:
                plane = (0.0, 0.0, z_field)
            elif not np.isfinite(ring[:, 2]).all():
                plane = (0.0, 0.0, floor_c)
            else:
                span = max(np.ptp(ring[:, 0]), np.ptp(ring[:, 1]), 1.0)
                if np.ptp(ring[:, 2]) > 0.35 * span:
                    # отвесный контур - это разрез, а не план: внутри
                    # плана у него нет площади для свода
                    n_skip += 1
                    continue
            try:
                top, bot, gt, info = crown.crown_grids(
                    ring, plane, wall, steep, rise_max, shape, cell)
                v, f = bed_to_mesh_arrays(top, bot, gt)
            except ValueError:
                n_skip += 1
                continue
            holes, _pinch = shell_defects(v, f)
            vol = float(mesh_volume(v, f))
            vol_sum += vol
            n_body += 1
            n_open += 1 if holes else 0
            out.add({"verts": v, "faces": f, "source": item.get("id")},
                    [vol, float(info["area"]), float(v[:, 2].min()),
                     float(v[:, 2].max()), float(info["rise"]),
                     0 if holes else 1])
        report.progress(100.0 * (k + 1) / max(len(items), 1))
    if n_skip:
        report.warn(N_("Пропущено контуров: %d. Вырожденный контур или "
                       "отвесный, как на разрезе: свода в плане у него "
                       "нет."), n_skip)
    if not n_body:
        raise ToolError(N_("Ни одного тела не построилось: нужны контуры "
                           "в плане с площадью."))
    report.info(N_("Тел: %d, объём всего %.1f м3."), n_body, vol_sum)
    if n_open:
        report.warn(N_("Незамкнутых тел: %d. Их не примут 2.11 и 2.12."),
                    n_open)
    return {"OUTPUT": out}


SPEC = Tool(
    code="2.26", name="contour_crown",
    title=N_("Тела по контуру со сводом"), group="2",
    help=N_("Строит замкнутое тело на каждый контур в плане: плоский "
            "пол, стенки и свод над ними. Камера, линза, купол, отвал "
            "по контуру основания.\n\n"
            "Пол - плоскость по отметкам контура наименьшими "
            "квадратами, поэтому небольшой наклон и разброс отметок "
            "допустимы. У контура без высоты пол берётся из поля или "
            "постоянной отметки.\n\n"
            "Высота свода в точке растёт с расстоянием до контура. "
            "Узкое место тела выходит низким, широкое высоким, гребень "
            "идёт по средней линии фигуры, а не по одной оси: у "
            "контура буквой Г свод вдоль обеих полок. Линейный свод - "
            "двускатная кровля с подъёмом «крутизна на метр от "
            "контура», округлый - дуга той же высоты, как свод "
            "камеры. Потолок подъёма срезает гребень: у широкого тела "
            "над серединой плоская кровля.\n\n"
            "Тело строится на сетке с шагом ячейки, граница идёт по "
            "центрам ячеек внутри контура, поэтому объём немного меньше "
            "площади контура на высоту. Мельче ячейка - ближе к "
            "контуру.\n\n"
            "Тела замкнуты: объём, пробы внутри, заполнение водой "
            "считают 2.11, 2.12, 2.14 и 2.23.\n\n"
            "Идея из модуля QGIS 3D Studio."),
    params=[
        Param("INPUT", "features", N_("Контуры тел (полигоны)"),
              N_("Контуры тел в плане: полигоны с высотой или без неё. "
                 "Отвесный контур, как на разрезе, пропускается: площади "
                 "в плане у него нет.")),
        Param("FLOOR_FIELD", "field", N_("Поле отметки пола"),
              N_("Отметка пола из поля. Задана - пол горизонтален на этой "
                 "отметке, даже если у контура есть своя Z."),
              optional=True, parent="INPUT", numeric=True),
        Param("FLOOR", "number", N_("Отметка пола для контуров без Z, м"),
              N_("Отметка пола для контуров без высоты и без поля "
                 "отметки. У контуров с Z пол идёт по их отметкам."),
              default=0.0),
        Param("WALL", "number", N_("Высота стенок, м"),
              N_("Высота отвесных стенок от пола до начала свода. Ноль - "
                 "свод начинается сразу от пола, как у линзы."),
              default=0.0, minimum=0.0),
        Param("SHAPE", "enum", N_("Профиль свода"),
              N_("Линейный - двускатная кровля, подъём растёт ровно. "
                 "Округлый - дуга от стенки к гребню той же высоты, как "
                 "свод камеры, объём больше."),
              default=0, options=(N_("Линейный"), N_("Округлый"))),
        Param("STEEP", "number", N_("Крутизна свода, м на метр от контура"),
              N_("Подъём свода на метр расстояния от контура. 0.45 даёт "
                 "гребень около 24 градусов, единица - 45 градусов."),
              default=0.45, minimum=0.01),
        Param("RISE_MAX", "number", N_("Подъём свода не выше, м (0 - без "
                                       "предела)"),
              N_("Предел подъёма свода над стенками. Ноль - без предела: "
                 "у широкого тела свод тогда поднимается высоко."),
              default=0.0, minimum=0.0),
        Param("CELL", "number", N_("Ячейка, м (0 - от размера контура)"),
              N_("Шаг сетки тела. Ноль - около ста двадцати ячеек по "
                 "длинной стороне контура. Мельче - точнее граница, но "
                 "больше граней."),
              default=0.0, minimum=0.0, advanced=True),
        Param("OUTPUT", "sink", N_("Тела по контуру"),
              N_("Тела, по одному на контур, со всеми полями контура "
                 "и полями объёма, площади, отметок и подъёма свода. Тела "
                 "замкнуты, их принимают 2.11, 2.12, 2.14 и 2.23.")),
    ],
    run=run)
