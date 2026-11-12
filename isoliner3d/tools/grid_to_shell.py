# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""2.13 Оболочка грида пласта: описание и расчёт без QGIS.

Оболочка тела пласта из грида, без окна просмотра. То же самое
делает кнопка в сцене, но там это ручной шаг: модель обработки его
не повторит, и на новых данных всё придётся кликать заново. Здесь
тот же меш строится инструментом, поэтому цепочка «поверхность -
тело - вычитание отработки - подсчёт запаса» собирается целиком
и запускается одной кнопкой.
"""

import numpy as np

from ..toolspec import N_, Param, Result, Tool, ToolError


def run(values, report):
    """Расчёт 2.13: оболочки тел по каналам кровли и подошвы."""
    from ..cleanup import mesh_volume, shell_defects, split_bodies
    from ..mesh3d import bed_to_mesh_arrays

    grid = values["INPUT"]
    band = int(values["BAND"] or 1)
    step = max(int(values.get("STEP") or 1), 1)
    if band < 1 or band + 1 > grid.count:
        raise ToolError(N_("После канала %d нет канала подошвы. У грида "
                           "пласта каналы идут парами: кровля, подошва."),
                        band)
    top, bot = grid.band(band), grid.band(band + 1)
    thick = top - bot
    fin = thick[np.isfinite(thick)]
    if not fin.size:
        raise ToolError(N_("Мощность нигде не считается: в каналах нет "
                           "перекрывающихся данных."))
    report.info(N_("Мощность: %.2f .. %.2f м."), float(fin.min()),
                float(fin.max()))
    if float(fin.min()) < 0:
        report.warn(N_("Местами подошва выше кровли: таких ячеек %d. Тела "
                       "там нет, и они выброшены."), int(np.sum(fin < 0)))
    report.progress(30)

    verts, faces = bed_to_mesh_arrays(top, bot, grid.transform, zscale=1.0,
                                      zoffset=0.0, step=step)
    if not len(faces):
        raise ToolError(N_("Оболочка не построилась: проверьте каналы."))
    report.info(N_("Вершин %d, граней %d."), len(verts), len(faces))
    report.progress(60)

    out = Result([("body", "int"), ("band", "int"), ("volume", "double"),
                  ("faces", "int"), ("closed", "int")],
                 name=N_("Тела пласта"))
    total = 0.0
    n_body = n_open = 0
    for bv, bf, _tag in split_bodies(verts, faces):
        if report.canceled():
            break
        holes, _pinch = shell_defects(bv, bf)
        vol = mesh_volume(bv, bf)
        total += vol
        n_body += 1
        if holes:
            n_open += 1
        out.add({"verts": bv, "faces": bf},
                [n_body, band, float(vol), int(len(bf)),
                 1 if holes == 0 else 0])
    report.info(N_("Тел: %d, объём всего %.1f м3."), n_body, total)
    if n_open:
        report.warn(N_("Незамкнутых тел: %d. Их не примут 2.11 и 2.12, "
                       "и объём по ним считать нельзя."), n_open)
    return {"OUTPUT": out}


SPEC = Tool(
    code="2.13", name="grid_to_shell",
    title=N_("Оболочка грида пласта"), group="2",
    help=N_("Строит замкнутую оболочку тела пласта по гриду: кровля, "
            "подошва и бортик между ними.\n\n"
            "То же самое делает кнопка оболочек в окне просмотра, "
            "но там это ручной шаг. Инструментом он становится частью "
            "модели обработки, и цепочка «поверхность - тело - "
            "вычитание отработанного - подсчёт запаса» запускается "
            "целиком.\n\n"
            "Оболочка замкнута, поэтому её принимают 2.11 и 2.12, "
            "а объём считается точной формулой по самой оболочке.\n\n"
            "Объём здесь и объём из 1.02 расходятся примерно "
            "на процент: оболочка идёт по центрам ячеек, а 1.02 "
            "считает ячейки целиком. Это разные границы одной области, "
            "а не спор методов."),
    params=[
        Param("INPUT", "raster", N_("Грид пласта"),
              N_("Грид пласта: канал кровли и канал подошвы. Такой даёт "
                 "1.01 из двух поверхностей или из одной, достроенной "
                 "вниз, и 2.08 по зарисовкам на разрезах.")),
        Param("BAND", "band", N_("Канал кровли"),
              N_("Канал кровли. Подошвой считается следующий за ним: так "
                 "устроен грид пласта. У многопластового грида это выбор "
                 "пласта."),
              default=1, parent="INPUT"),
        Param("STEP", "integer", N_("Прореживание сетки"),
              N_("Прореживание сетки. Единица - как есть; двойка берёт "
                 "каждую вторую ячейку и даёт вчетверо меньше "
                 "треугольников. Объём при этом меняется мало, а вот "
                 "тонкие детали срезаются."),
              default=1, minimum=1, maximum=50, advanced=True),
        Param("OUTPUT", "sink", N_("Тела пласта"),
              N_("Тела пласта: полигоны с Z, объём каждого в атрибутах. "
                 "Дальше их принимают 2.11 и 2.12.")),
    ],
    run=run)
