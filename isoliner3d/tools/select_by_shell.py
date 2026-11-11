# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""2.12 Выборка оболочкой: описание и расчёт без QGIS.

Луч из точки вверх: если выше неё оболочка пересекается нечётное
число раз, точка внутри (boolean3d.points_inside). Ячейки для этого
не нужны, ответ точный.

Это последнее звено цепочки куб значений - блочная модель - отбор
оболочкой - объём, тоннаж и средневзвешенное содержание. Отбирать
можно и линии с полигонами: скважины, выработки, другие тела.
Выход - те же объекты, что пришли, с той же геометрией и полями.
"""

import math

import numpy as np

from ..toolspec import N_, Param, Result, Tool, ToolError

MODES = ("inside", "cross", "outside")


def _num(attrs, name):
    """Числовое поле объекта: пустое и текстовое дают ноль."""
    try:
        x = float(attrs.get(name))
    except (TypeError, ValueError):
        return 0.0
    return x if math.isfinite(x) else 0.0


def feature_points(parts, step):
    """Точки опроса объекта: вершины, при шаге - с промежуточными.

    Опрос идёт по вершинам: у точки она одна, у линии и полигона
    их сколько нарисовано. Шаг добавляет промежуточные, иначе
    отрезок, прошивший тело насквозь, останется незамеченным.
    Точки без высоты выбрасываются.
    """
    out = []
    for part in parts:
        a = np.asarray(part, dtype=float).reshape(-1, 3)
        out.extend(map(tuple, a))
        if step > 0 and len(a) > 1:
            for k in range(len(a) - 1):
                d = float(np.linalg.norm(a[k + 1] - a[k]))
                m = int(d // step) if math.isfinite(d) else 0
                for t in range(1, m + 1):
                    out.append(tuple(a[k] + (a[k + 1] - a[k])
                                     * (t * step / d)))
    return [p for p in out if np.isfinite(p).all()]


def run(values, report):
    """Расчёт 2.12: отбор объектов values["INPUT"] оболочкой."""
    from .. import boolean3d
    from ..cleanup import mesh_volume, shell_defects

    mesh = values["SHELL"]
    v = np.asarray(mesh["verts"], dtype=float)
    f = np.asarray(mesh["faces"], dtype=np.int64)
    mode = MODES[int(values.get("MODE") or 0)]
    step = float(values.get("STEP") or 0.0)
    vfield = values.get("VOLUME") or ""
    gfield = values.get("GRADE") or ""
    dens = float(values.get("DENSITY") or 0.0)

    holes, _pinch = shell_defects(v, f)
    if holes:
        raise ToolError(N_("Оболочка не замкнута, рваных рёбер %d. У "
                           "незамкнутой внутренности нет."), holes)
    shell_vol = mesh_volume(v, f)
    report.info(N_("Оболочка: граней %d, объём %.1f м3."), len(f),
                shell_vol)

    feats, pts, owner = [], [], []
    for item in values["INPUT"]:
        if report.canceled():
            break
        own = feature_points(item.get("parts") or [], step)
        if not own:
            continue
        owner.extend([len(feats)] * len(own))
        feats.append(item)
        pts.extend(own)
    if not pts:
        raise ToolError(N_("Объектов с высотой не нашлось: у геометрии "
                           "должна быть Z."))
    report.info(N_("Объектов %d, точек опроса %d."), len(feats), len(pts))
    report.progress(30)
    inside = boolean3d.points_inside(v, f, np.asarray(pts))
    owner = np.asarray(owner, dtype=np.int64)
    n_in = np.bincount(owner[inside], minlength=len(feats))
    n_all = np.bincount(owner, minlength=len(feats))
    if mode == "inside":
        keep = n_in == n_all
    elif mode == "cross":
        keep = n_in > 0
    else:
        keep = n_in == 0
    report.progress(70)

    out = Result([], keep_source="INPUT", geometry="source",
                 name=N_("Отобранные объекты"))
    vol = grade_w = 0.0
    n = 0
    for item, take in zip(feats, keep):
        if not take:
            continue
        n += 1
        out.add({"source": item.get("id")}, [])
        if vfield:
            attrs = item.get("attrs") or {}
            q = _num(attrs, vfield)
            vol += q
            if gfield:
                grade_w += q * _num(attrs, gfield)

    report.info(N_("Объектов всего %d, отобрано %d (%.1f процента)."),
                len(feats), n, 100.0 * n / max(len(feats), 1))
    if not vfield:
        report.info(N_("Поле объёма не задано: объём и тоннаж не "
                       "считаются. У блочной модели из 2.03 и 1.03 это "
                       "поле vol."))
        return {"OUTPUT": out}
    report.info(N_("Объём отобранного: %.1f м3."), vol)
    if mode != "outside" and shell_vol > 0:
        # Объём оболочки точный, объём по блокам - сумма ячеек.
        # Расхождение между ними и есть грубость модели для этого
        # тела, и человеку его надо видеть, а не выводить самому.
        report.info(N_("Объём оболочки %.1f м3, расхождение с блоками "
                       "%+.1f процента. Это грубость блочной модели для "
                       "этого тела: блок либо целиком внутри, либо "
                       "целиком снаружи."),
                    shell_vol, 100.0 * (vol - shell_vol) / shell_vol)
    if gfield and vol > 0:
        report.info(N_("Содержание, взвешенное по объёму: %.3f."),
                    grade_w / vol)
    if dens > 0:
        report.info(N_("Тоннаж руды: %.0f т."), vol * dens)
        if gfield and vol > 0:
            report.info(N_("Тоннаж металла: %.0f т."),
                        vol * dens * (grade_w / vol) / 100.0)
    return {"OUTPUT": out}


SPEC = Tool(
    code="2.12", name="select_by_shell",
    title=N_("Выборка оболочкой"), group="2",
    help=N_("Отбирает объекты, попавшие в замкнутую оболочку, "
            "и считает по ним сводку.\n\n"
            "Так получают запас: блочная модель, оболочка рудного "
            "тела или зоны отработки, и на выходе объём, тоннаж "
            "и средневзвешенное содержание отобранного. Отбор "
            "снаружи даёт остаток, не строя вычитания тел.\n\n"
            "Отбирать можно не только точки. Линии и полигоны "
            "с высотой идут тем же путём: скважины, прошившие тело, "
            "следы выработок, оболочки других тел.\n\n"
            "Точка считается внутри по правилу чётности: из неё "
            "вверх пускается луч, и если оболочка пересекается "
            "нечётное число раз, точка внутри. Ячейки для этого "
            "не нужны, и ответ выходит точный, а не с точностью "
            "до ячейки, как у булевых операций.\n\n"
            "У линий и полигонов смотрятся вершины. Отрезок, "
            "прошивший тело насквозь между двумя своими вершинами, "
            "вершинами не ловится - на этот случай есть шаг опроса "
            "вдоль.\n\n"
            "Объём отобранных блоков сверяется с объёмом самой "
            "оболочки: расхождение показывает, насколько модель "
            "груба для этого тела.\n\n"
            "Оболочка должна быть замкнута: у незамкнутой "
            "внутренности нет."),
    params=[
        Param("INPUT", "features", N_("Что отбирать (объекты с Z)"),
              N_("Что отбирать: точки, линии или полигоны с высотой. "
                 "Блочная модель из 2.03 и 1.03, пробы, следы выработок, "
                 "оболочки других тел - лишь бы у геометрии была Z.")),
        Param("SHELL", "mesh", N_("Оболочка (полигоны с Z)"),
              N_("Замкнутая оболочка, которой идёт отбор: рудное тело, "
                 "зона отработки, контур подсчёта. Такие даёт кнопка "
                 "оболочек в окне просмотра, 2.04 и 2.11.")),
        Param("MODE", "enum", N_("Что оставить"),
              N_("Целиком внутри - все вершины объекта внутри оболочки. "
                 "Пересекает - хоть одна внутри: так ловятся скважины "
                 "и выработки, проходящие тело насквозь. Снаружи - "
                 "остаток, то есть всё, что не пересекает."),
              default=0, options=(N_("Целиком внутри"),
                                  N_("Пересекает оболочку"),
                                  N_("Снаружи"))),
        Param("STEP", "number",
              N_("Шаг опроса вдоль линий, м (0 - вершины)"),
              N_("Шаг опроса вдоль линий и по краю полигонов. Без него "
                 "смотрятся только вершины, и отрезок, прошивший тело "
                 "насквозь между двумя своими вершинами, найден не будет. "
                 "Ноль - только вершины."),
              default=0.0, minimum=0.0, advanced=True),
        Param("VOLUME", "field", N_("Поле объёма блока"),
              N_("Поле объёма блока, если отбирается блочная модель. "
                 "С ним считается объём отобранного и сверяется с объёмом "
                 "самой оболочки: расхождение показывает, насколько "
                 "модель груба для этого тела."),
              optional=True, parent="INPUT", numeric=True),
        Param("GRADE", "field", N_("Поле содержания"),
              N_("Поле содержания. Среднее по отобранному считается "
                 "взвешенным по объёму, а не простым: блоки бывают разного "
                 "размера, и простое среднее завышает мелкие."),
              optional=True, parent="INPUT", numeric=True),
        Param("DENSITY", "number", N_("Плотность, т/м3 (0 - без тоннажа)"),
              N_("Плотность руды. С ней объём переводится в тонны, "
                 "а содержание - в тоннаж металла."),
              default=0.0, minimum=0.0, advanced=True),
        Param("OUTPUT", "sink", N_("Отобранные объекты"),
              N_("Отобранные объекты со всеми своими полями. Сводка идёт "
                 "в журнал."),
              geometry="source"),
    ],
    run=run)
