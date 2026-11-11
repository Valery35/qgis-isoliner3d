# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""2.23 Заполнение тела до объёма: описание и расчёт без QGIS.

Уровень, ниже которого (режим «сверху» - выше которого) внутри тела
заданный объём, и заполненная часть телом. Расчёт по колонкам в
fill.py, здесь поля, проверки и сборка результата.
"""

import numpy as np

from ..toolspec import N_, Param, Result, Tool, ToolError

MODES = ("bottom", "top")


def run(values, report):
    """Расчёт 2.23 на теле values["SHELL"] = {"verts", "faces"}."""
    from .. import boolean3d, fill, voxel
    from ..cleanup import mesh_volume, shell_defects

    mesh = values["SHELL"]
    v = np.asarray(mesh["verts"], dtype=float)
    f = np.asarray(mesh["faces"], dtype=np.int64)
    if not len(f):
        raise ToolError(N_("В слое нет ни одного треугольника."))
    from_top = MODES[int(values.get("MODE") or 0)] == "top"
    target = float(values.get("TARGET") or 0.0)
    in_pct = int(values.get("UNIT") or 0) == 0
    cell = float(values.get("CELL") or 0.0)

    holes, _pinch = shell_defects(v, f)
    if holes:
        raise ToolError(N_("Оболочка не замкнута, рваных рёбер %d. "
                           "У незамкнутой внутренности нет, и заполнять "
                           "нечего."), holes)
    exact = abs(mesh_volume(v, f))
    bounds = (float(v[:, 0].min()), float(v[:, 0].max()),
              float(v[:, 1].min()), float(v[:, 1].max()))
    gt, ny, nx, step = fill.plan_grid(bounds, cell)
    if cell > 0 and step > cell * 1.0001:
        report.warn(N_("Шаг %.3g м дал бы слишком много колонок, "
                       "взят %.3g м."), cell, step)
    report.info(N_("Колонок %d x %d, шаг %.3g м."), nx, ny, step)
    col, zc = boolean3d.column_cuts(v, f, gt, (ny, nx))
    cols, lo, hi = fill.intervals(col, zc)
    if not len(lo):
        raise ToolError(N_("Колонки не задели тело: шаг крупнее самого "
                           "тела."))
    area = step * step
    full = fill.total_volume(lo, hi, area)
    report.info(N_("Объём тела: по колонкам %.1f м3, точный по оболочке "
                   "%.1f м3, расхождение %.2f %%."),
                full, exact,
                100.0 * (full - exact) / exact if exact else 0.0)
    want = full * target / 100.0 if in_pct else target
    if want > full:
        report.warn(N_("Задано %.1f м3, а в теле только %.1f м3: тело "
                       "заполняется целиком."), want, full)
    level, got = fill.level_for_volume(lo, hi, area, want,
                                       from_top=from_top)
    share = 100.0 * got / full if full else 0.0
    report.info(N_("Уровень %.3f м. Объём %s уровня %.1f м3, %.1f %% "
                   "тела."), level, N_("выше") if from_top else N_("ниже"),
                got, share)
    # Тело заполнения - на сетке грубее: уровень уже найден по
    # мелким колонкам, а куб из 400 тысяч колонок на сотню слоёв
    # собирался бы минутами. Сорок тысяч колонок и до ста слоёв -
    # секунды, крышка всё равно ровная на уровне.
    gt2, ny2, nx2, step2 = fill.plan_grid(bounds, max(cell, step),
                                          max_cols=40000)
    col2, zc2 = boolean3d.column_cuts(v, f, gt2, (ny2, nx2))
    cols2, lo2, hi2 = fill.intervals(col2, zc2)
    zspan = float(hi.max() - lo.min())
    dz = max(min(step2, zspan / 50.0), zspan / 100.0, 1e-6)
    occ, z0, dz = fill.filled_occupancy(cols2, lo2, hi2, gt2, ny2, nx2,
                                        level, dz, from_top)
    if boolean3d.cell_budget(occ.shape) > 60000000:
        raise ToolError(N_("Ячеек слишком много: укрупните шаг колонок."))
    verts, faces, _cls, over = voxel.voxel_mesh(
        occ, gt2, z0, dz, classes=np.zeros(occ.shape, np.int32),
        merge=False)
    if over:
        raise ToolError(N_("Граней вышло слишком много: укрупните шаг "
                           "колонок."))
    out = Result([("mode", "string"), ("level", "double"),
                  ("volume", "double"), ("share_pct", "double"),
                  ("body_vol", "double")], name=N_("Заполненная часть"))
    if len(faces):
        out.add({"verts": verts, "faces": faces},
                ["top" if from_top else "bottom", float(level), float(got),
                 float(share), float(full)])
    else:
        report.warn(N_("Заполненная часть пуста: объём меньше одной "
                       "ячейки."))
    return {"OUTPUT": out}


SPEC = Tool(
    code="2.23", name="fill_to_volume",
    title=N_("Заполнение тела до объёма"), group="2",
    help=N_("Находит горизонтальный уровень, ниже которого внутри тела "
            "заданный объём, и выдаёт заполненную часть отдельным телом. "
            "Режим «сверху» - наоборот: уровень, выше которого внутри "
            "тела заданный объём.\n\nВопросы такие. До какой отметки "
            "поднимется вода, если в выработку зайдёт столько кубометров? "
            "Сколько войдёт в камеру до этой отметки? Где пройдёт "
            "подошва, если снять сверху такой объём?\n\nТело режется на "
            "вертикальные колонки по плану. В каждой колонке берутся "
            "отрезки внутри тела, и объём ниже уровня складывается из их "
            "частей ниже него. Пустоты между этажами тела в объём не "
            "идут: две камеры одна над другой заполняются по очереди, "
            "нижняя первой.\n\nТочность объёма ограничена шагом колонок, "
            "отметка уровня по вертикали точная. В журнал идут уровень, "
            "объём по колонкам и точный объём оболочки: по их расхождению "
            "видно, хватает ли шага."),
    params=[
        Param("SHELL", "mesh", N_("Тело (полигоны с Z)"),
              N_("Замкнутое тело: выработка, камера, ёмкость, чаша карьера. "
                 "Слой целиком идёт одним телом, как в 2.11. Такие тела дают "
                 "кнопка оболочек окна просмотра, 2.04, 2.11, 2.13 и 2.15.")),
        Param("MODE", "enum", N_("Откуда заполнять"),
              N_("Снизу - заполнение: вода, закладка, рассол поднимаются от "
                 "дна. Сверху - срезка: уровень, выше которого внутри заданный "
                 "объём, например вынимаемая часть тела."),
              default=0, options=(N_("Снизу (заполнение)"),
                                  N_("Сверху (срезка)"))),
        Param("TARGET", "number", N_("Объём"),
              N_("Сколько заполнить: кубометры или доля тела в процентах, по "
                 "полю ниже. Больше всего тела - тело заполняется целиком, и "
                 "это пишется в журнал."),
              default=50.0, minimum=0.0),
        Param("UNIT", "enum", N_("Объём задан в"),
              N_("В чём задан объём. Проценты удобны, когда сам объём тела "
                 "заранее неизвестен."),
              default=0, options=(N_("процентах объёма тела"),
                                  N_("кубометрах"))),
        Param("CELL", "number", N_("Шаг колонок, м (0 - по охвату)"),
              N_("Шаг колонок в плане, м. Ноль - около 400 тысяч колонок по "
                 "охвату тела. Точность объёма ограничена этим шагом, а "
                 "отметка уровня считается точно: по вертикали ступенек нет. "
                 "Расхождение с точным объёмом оболочки печатается."),
              default=0.0, minimum=0.0),
        Param("OUTPUT", "sink", N_("Заполненная часть (тело)"),
              N_("Заполненная часть телом из ячеек: крышка ровная на уровне, "
                 "стенки ступенчатые по шагу. В атрибутах уровень, объём и "
                 "доля тела. Тело принимают 2.11, 2.12 и 2.14."),
              geometry="polygonz"),
    ],
    run=run)
