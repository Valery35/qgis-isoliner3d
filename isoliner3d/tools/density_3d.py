# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""2.25 3D-плотность: описание и расчёт без QGIS.

Куб, в ячейке которого не оценка, а счёт: сколько объектов в ячейке,
их сумма или среднее по полю, длина линий внутри ячейки. Дальше куб
идёт туда же, куда любой куб модуля: изоповерхность и воксели в окне
сцены, 2.03 в блочную модель, 2.04 тело вокселями. Ядро -
density3d.py. Идея из модуля QGIS 3D Studio, расчёт свой.
"""

import numpy as np

from ..toolspec import (N_, Grid, Param, RasterResult, Result, Tool,
                        ToolError)

# что пишется в куб, по номеру пункта METRIC
_METRIC = ("count", "sum", "mean", "length")
_BAND = (N_("число объектов"), N_("сумма атрибута"),
         N_("среднее атрибута"), N_("длина линий, м"))


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def run(values, report):
    """Расчёт 2.25: куб плотности по объектам values["INPUT"]."""
    from .. import density3d

    meta = values.get("@INPUT") or {}
    geom = meta.get("geometry") or "point"
    if geom not in ("point", "line", "polygon"):
        geom = "point"
    which = int(values.get("METRIC") or 0)
    if not 0 <= which < len(_METRIC):
        which = 0
    metric = _METRIC[which]
    attr = values.get("ATTR") or ""
    if metric in ("sum", "mean") and not attr:
        raise ToolError(N_("Для суммы и среднего нужен атрибут."))
    if metric == "length" and geom != "line":
        raise ToolError(N_("Длина линий считается только по слою линий."))

    objs, vals, n_flat = [], [], 0
    for item in values["INPUT"] or []:
        if report.canceled():
            break
        parts = [np.asarray(p, dtype=float).reshape(-1, 3)
                 for p in item.get("parts") or []]
        parts = [p for p in parts if len(p)]
        if not parts:
            continue
        if not all(np.isfinite(p).all() for p in parts):
            n_flat += 1
            continue
        objs.append(parts)
        vals.append(_num((item.get("attrs") or {}).get(attr))
                    if attr else None)
    if n_flat:
        report.warn(N_("Объектов без высоты: %d, они пропущены. Плотности "
                       "в объёме нужна Z у каждой вершины."), n_flat)
    if not objs:
        raise ToolError(N_("Объектов с высотой не нашлось: у геометрии "
                           "должна быть Z."))
    allp = np.vstack([p for parts in objs for p in parts])
    try:
        lat = density3d.Lattice.around(
            allp.min(axis=0), allp.max(axis=0),
            float(values.get("CELL_XY") or 0.0),
            float(values.get("CELL_Z") or 0.0))
    except ValueError as err:
        raise ToolError(N_("Сетка слишком мелкая (%s). Укрупните шаг."),
                        str(err))
    nx, ny, nz = (int(v) for v in lat.size)
    dx, dy, dz = (float(v) for v in lat.step)
    report.info(N_("Сетка %d x %d x %d, шаг %.6g x %.6g x %.6g м."),
                nx, ny, nz, dx, dy, dz)

    cubes, summary = density3d.density(objs, geom, lat,
                                       vals if attr else None)
    report.info(N_("Объектов: %d, в сетке %d."), summary["objects"],
                summary["inside"])
    if geom == "line":
        report.info(N_("Длина линий: всего %.2f м, по ячейкам %.2f м."),
                    summary["len_all"], summary["len_in"])
    cube = cubes[metric]
    filled = int(np.sum(cubes["count"] > 0) if metric != "length"
                 else np.sum(cubes["length"] > 0))
    report.info(N_("Непустых ячеек: %d из %d."), filled, nx * ny * nz)

    x0, y0, z0 = (float(v) for v in lat.origin)
    gt = (x0, dx, 0.0, y0 + ny * dy, 0.0, -dy)
    # строки растра идут с севера, куб лежит с юга: переворот по y
    bands = [cube[k][::-1, :] for k in range(nz)]
    grid = Grid(bands=bands, transform=gt,
                names=[_BAND[which]] * nz,
                meta={"Z0": "%.6f" % (z0 + dz / 2.0), "DZ": "%.6f" % dz})
    out = {"OUTPUT": RasterResult(grid, name=N_("3D-плотность"))}

    if values.get("OUTPUT_CELLS"):
        cells = Result([("n", "int"), ("sum", "double"), ("mean", "double"),
                        ("len_m", "double"), ("vol", "double")],
                       geometry="point", name=N_("Ячейки плотности"))
        busy = (cubes["count"] > 0) | (cubes["length"] > 0)
        kk, jj, ii = np.nonzero(busy)
        vol = dx * dy * dz
        for k, j, i in zip(kk, jj, ii):
            xyz = (x0 + (i + 0.5) * dx, y0 + (j + 0.5) * dy,
                   z0 + (k + 0.5) * dz)
            m = cubes["mean"][k, j, i]
            cells.add({"xyz": xyz},
                      [int(cubes["count"][k, j, i]),
                       float(cubes["sum"][k, j, i]) if attr else None,
                       float(m) if attr and m == m else None,
                       float(cubes["length"][k, j, i]), vol])
        out["OUTPUT_CELLS"] = cells
    return out


SPEC = Tool(
    code="2.25", name="density_3d",
    title=N_("3D-плотность"), group="2",
    help=N_("Строит куб, в ячейке которого не оценка, а счёт: сколько "
            "объектов в ячейке, сумма или среднее их атрибута, длина "
            "линий внутри ячейки.\n\n"
            "Объект считается один раз: точка своим положением, линия "
            "серединой по длине, полигон центром кольца. Длина линии "
            "делится между ячейками точно, по пересечениям отрезка "
            "с гранями сетки, и сумма по ячейкам равна длине линии "
            "внутри сетки. Это печатается в журнал.\n\n"
            "Пустая ячейка - ноль, а не пропуск: ноль находок тоже "
            "измеренный факт. Только у среднего ячейка без объектов "
            "пустая: среднего по пустому множеству нет.\n\n"
            "Куб размечен по высоте (Z0, DZ), как все кубы модуля: "
            "в окне сцены по нему строится изоповерхность и воксели, "
            "2.03 переводит его в блочную модель, 2.04 - в тело "
            "вокселями. Так скопление находок или густая сеть "
            "выработок становится телом по порогу плотности.\n\n"
            "Шаг сетки ноль - круглый шаг от охвата данных: около "
            "пятидесяти ячеек по длинной стороне плана и двадцати "
            "по высоте.\n\n"
            "Идея из модуля QGIS 3D Studio."),
    params=[
        Param("INPUT", "features", N_("Объекты с Z"),
              N_("Точки, линии или полигоны с высотой: находки, пробы, "
                 "интервалы опробования, выработки. Объекты без Z "
                 "пропускаются, их число пишется в журнал.")),
        Param("METRIC", "enum", N_("Что считать в ячейке"),
              N_("Число объектов - плотность находок или проб. Сумма "
                 "и среднее - по атрибуту ниже. Длина линий, м - сколько "
                 "метров выработок или интервалов проходит через "
                 "ячейку."),
              default=0,
              options=(N_("Число объектов"), N_("Сумма атрибута"),
                       N_("Среднее атрибута"), N_("Длина линий, м"))),
        Param("ATTR", "field", N_("Атрибут для суммы и среднего"),
              N_("Числовой атрибут: металл, масса, вес находки. Пустые "
                 "значения не участвуют."),
              optional=True, parent="INPUT", numeric=True),
        Param("CELL_XY", "number", N_("Ячейка в плане, м (0 - от охвата)"),
              N_("Размер ячейки по x и y в метрах. Ноль - круглый шаг "
                 "от охвата данных, около пятидесяти ячеек по длинной "
                 "стороне."),
              default=0.0, minimum=0.0),
        Param("CELL_Z", "number", N_("Ячейка по высоте, м (0 - от охвата)"),
              N_("Размер ячейки по высоте в метрах. Ноль - около "
                 "двадцати слоёв на размах отметок."),
              default=0.0, minimum=0.0),
        Param("OUTPUT", "sink", N_("Куб плотности"),
              N_("Куб плотности: канал на уровень по высоте, разметка "
                 "Z0 и DZ в метаданных. Открывается в окне сцены "
                 "изоповерхностью или вокселями."),
              geometry="raster"),
        Param("OUTPUT_CELLS", "sink", N_("Ячейки плотности (точки)"),
              N_("Непустые ячейки точками в центрах, со всеми счётами "
                 "сразу: n, sum, mean, len_m и объём ячейки vol."),
              optional=True, geometry="points"),
    ],
    run=run)
