# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""2.17 Стволы скважин по инклинометрии: описание и расчёт без QGIS.

Математика минимальной кривизны лежит в wells.py, угадывание полей
по именам Micromine, Datamine и Surpac - в colnames.py. Здесь поля,
сведение устьев с замерами и сборка результата.
"""

import numpy as np

from ..toolspec import N_, Param, Result, Tool, ToolError

CONVENTIONS = ("dip_down_neg", "dip_down_pos", "zenith")


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


def run(values, report):
    """Расчёт 2.17: стволы по устьям COLLARS и замерам SURVEY."""
    from .. import colnames, wells

    collars = values["COLLARS"]
    survey = values.get("SURVEY")
    meta_c = values.get("@COLLARS") or {}
    meta_s = values.get("@SURVEY") or {}
    conv = CONVENTIONS[int(values.get("CONVENTION") or 0)]
    step = float(values.get("STEP") or 1.0)

    cn = list(meta_c.get("fields") or [])
    f_hole = colnames.resolve(values.get("HOLE") or "", cn, "hole")
    f_eoh = colnames.resolve(values.get("EOH") or "", cn, "eoh",
                             taken=[f_hole])
    f_caz = colnames.resolve(values.get("C_AZI") or "", cn, "s_azi")
    f_cang = colnames.resolve(values.get("C_ANGLE") or "", cn, "s_angle")
    if not (f_caz and f_cang):
        f_caz = f_cang = None
    has_geom = (meta_c.get("geometry") or "none") != "none"
    has_z = has_geom and bool(meta_c.get("hasz"))
    f_x = values.get("XFIELD") or ""
    f_y = values.get("YFIELD") or ""
    f_z = values.get("ZFIELD") or ""
    if not has_geom:
        f_x = colnames.resolve(f_x, cn, "collar_x")
        f_y = colnames.resolve(f_y, cn, "collar_y")
    if not f_z and not has_z:
        f_z = colnames.guess(cn, "collar_z")
    if not f_hole:
        raise ToolError(N_("Не найдено поле номера скважины в устьях: "
                           "выберите его."))
    s_hole = values.get("S_HOLE") or ""
    s_d = values.get("S_DEPTH") or ""
    s_a = values.get("S_AZI") or ""
    s_g = values.get("S_ANGLE") or ""
    if survey is not None:
        sn = list(meta_s.get("fields") or [])
        s_hole = colnames.resolve(s_hole, sn, "hole")
        s_d = colnames.resolve(s_d, sn, "s_depth", taken=[s_hole])
        s_a = colnames.resolve(s_a, sn, "s_azi")
        s_g = colnames.resolve(s_g, sn, "s_angle")
    if f_caz:
        report.info(N_("Направление у устья: азимут %s, угол %s."),
                    f_caz, f_cang)
    point = N_("точка")
    report.info(N_("Поля устьев: скважина %s, глубина %s, X %s, Y %s, "
                   "Z %s. Инклинометрия: скважина %s, глубина %s, "
                   "азимут %s, угол %s."),
                *[(f or "-") for f in (
                    f_hole, f_eoh, f_x if not has_geom else point,
                    f_y if not has_geom else point, f_z or point,
                    s_hole, s_d, s_a, s_g)])

    surveys = {}
    if survey is not None:
        if not (s_hole and s_d and s_a and s_g):
            raise ToolError(N_("У инклинометрии не выбраны поля: "
                               "скважина, глубина, азимут и угол."))
        bad = 0
        for row in survey:
            at = row.get("attrs") or {}
            d, a, g = _numv(at.get(s_d)), _numv(at.get(s_a)), \
                _numv(at.get(s_g))
            if d is None or a is None or g is None:
                bad += 1
                continue
            surveys.setdefault(_key(at.get(s_hole)), []).append((d, a, g))
        if bad:
            report.warn(N_("Строк инклинометрии с пустыми или нечисловыми "
                           "значениями: %d, они пропущены."), bad)

    out = Result([("hole", "string"), ("eoh", "double"),
                  ("n_survey", "int")], geometry="line",
                 name=N_("Стволы скважин"))
    n_ok = n_vert = n_noz = n_skip = 0
    seen = set()
    for item in collars:
        if report.canceled():
            break
        at = item.get("attrs") or {}
        name = _key(at.get(f_hole))
        if not name:
            n_skip += 1
            continue
        xyz = item.get("xyz")
        x = y = z = None
        if xyz is not None:
            x, y = float(xyz[0]), float(xyz[1])
            z = float(xyz[2]) if has_z else None
        elif f_x and f_y:
            x, y = _numv(at.get(f_x)), _numv(at.get(f_y))
        if f_z:
            z = _numv(at.get(f_z))
        if x is None or y is None:
            n_skip += 1
            continue
        if z is None or z != z:
            z = 0.0
            n_noz += 1
        rows = surveys.get(name, [])
        seen.add(name)
        eoh = _numv(at.get(f_eoh)) if f_eoh else None
        caz = _numv(at.get(f_caz)) if f_caz else None
        cang = _numv(at.get(f_cang)) if f_cang else None
        sd, sa, sg = wells.with_collar(
            [r[0] for r in rows], [r[1] for r in rows],
            [r[2] for r in rows], caz, cang)
        if not sd:
            n_vert += 1
        if len(sd) <= 1 and eoh is None:
            n_skip += 1
            continue
        pts, mds = wells.desurvey((x, y, z), sd, sa, sg, max_depth=eoh,
                                  convention=conv, step=step)
        if len(pts) < 2:
            n_skip += 1
            continue
        out.add({"points": np.asarray(pts, dtype=float)},
                [name, float(mds[-1]), len(rows)])
        n_ok += 1
    report.info(N_("Стволов: %d."), n_ok)
    if n_vert:
        report.warn(N_("Скважин без инклинометрии: %d. Они построены "
                       "отвесными, а без глубины забоя пропущены."), n_vert)
    if n_noz:
        report.warn(N_("Устьев без отметки: %d. Они поставлены на ноль: "
                       "выберите поле отметки или дайте устьям Z."), n_noz)
    if n_skip:
        report.warn(N_("Пропущено устьев: %d (нет номера, координат или "
                       "глубины)."), n_skip)
    orphan = sorted(set(surveys) - seen)
    if orphan:
        report.warn(N_("Инклинометрия без устья: %d скважин, например %s."),
                    len(orphan), ", ".join(orphan[:5]))
    return {"OUTPUT": out}


SPEC = Tool(
    code="2.17", name="desurvey_holes",
    title=N_("Стволы скважин по инклинометрии"), group="2",
    help=N_("Строит стволы скважин по устьям и инклинометрии.\n\n"
            "Между замерами ствол идёт дугой окружности, касательные "
            "к которой на концах совпадают с замерами: метод "
            "минимальной кривизны, им считают Micromine, Datamine, "
            "Surpac и Leapfrog. От устья до первого замера ствол идёт "
            "по направлению из паспорта скважины, если поля азимута "
            "и угла есть у устьев, иначе по первому замеру. За "
            "последним замером ствол идёт по нему же до забоя. "
            "Скважина без инклинометрии и паспорта отвесная, "
            "скважина вверх из выработки задаётся углом вверх.\n\n"
            "Угол записывают по-разному: от горизонта с минусом вниз "
            "(-90 отвесно вниз), от горизонта с плюсом вниз или "
            "зенитный угол от вертикали. Соглашение выбирается явно.\n\n"
            "На выходе линии с Z, длина каждой равна глубине по "
            "стволу. Дальше 2.18 режет их на интервалы опробования "
            "или композиты, а сцена показывает трубами."),
    params=[
        Param("COLLARS", "table", N_("Устья скважин"),
              N_("Устья скважин: точечный слой или таблица с координатами. "
                 "У точечного слоя координаты берутся из геометрии, у "
                 "таблицы - из полей X и Y.")),
        Param("HOLE", "field", N_("Поле номера скважины"),
              N_("Поле номера скважины в устьях. По нему устье сводится "
                 "с инклинометрией. Пусто - узнаётся по имени: HOLE, "
                 "HOLEID, BHID."),
              default="hole", optional=True, parent="COLLARS"),
        Param("XFIELD", "field", N_("Поле X (если нет геометрии)"),
              N_("Поле X, если у слоя устьев нет геометрии. У точечного "
                 "слоя не нужно."),
              optional=True, parent="COLLARS", numeric=True, advanced=True),
        Param("YFIELD", "field", N_("Поле Y (если нет геометрии)"),
              N_("Поле Y, если у слоя устьев нет геометрии. У точечного "
                 "слоя не нужно."),
              optional=True, parent="COLLARS", numeric=True, advanced=True),
        Param("ZFIELD", "field",
              N_("Поле отметки устья (пусто - Z геометрии)"),
              N_("Поле отметки устья. Пусто - отметка из Z геометрии. "
                 "Без неё ствол встанет на ноль, о чём будет сказано."),
              optional=True, parent="COLLARS", numeric=True),
        Param("EOH", "field", N_("Поле глубины скважины"),
              N_("Поле глубины скважины (забоя). Пусто - узнаётся по "
                 "имени (EOH, DEPTH), а без такого поля ствол кончается "
                 "на последнем замере инклинометрии."),
              default="eoh", optional=True, parent="COLLARS", numeric=True),
        Param("C_AZI", "field", N_("Поле азимута у устья (пусто - по имени)"),
              N_("Азимут скважины у устья из паспорта. Наклонная скважина "
                 "идёт под ним с устья до первого замера. Пусто - "
                 "узнаётся по имени (AZIMUTH, AZI, BRG)."),
              optional=True, parent="COLLARS", numeric=True),
        Param("C_ANGLE", "field", N_("Поле угла у устья (пусто - по имени)"),
              N_("Угол скважины у устья из паспорта, в том же соглашении, "
                 "что инклинометрия. Пусто - узнаётся по имени (DIP, "
                 "ANGLE). Замер на глубине 0 важнее паспорта."),
              optional=True, parent="COLLARS", numeric=True),
        Param("SURVEY", "table", N_("Инклинометрия (таблица)"),
              N_("Таблица инклинометрии: скважина, глубина по стволу, "
                 "азимут, угол. Поля, которые не выбраны, узнаются по "
                 "именам Micromine, Datamine и Surpac. Пусто - все "
                 "скважины отвесные."),
              optional=True),
        Param("S_HOLE", "field", N_("Поле номера скважины в инклинометрии"),
              N_("Поле номера скважины в инклинометрии. Номера сводятся "
                 "с устьями как текст без пробелов по краям."),
              default="hole", optional=True, parent="SURVEY"),
        Param("S_DEPTH", "field", N_("Поле глубины замера"),
              N_("Поле глубины замера по стволу, метры от устья, не "
                 "отметка и не глубина по вертикали."),
              default="depth", optional=True, parent="SURVEY",
              numeric=True),
        Param("S_AZI", "field", N_("Поле азимута"),
              N_("Поле азимута, градусы от севера сетки по часовой "
                 "стрелке. Сближение меридианов не учитывается."),
              default="azimuth", optional=True, parent="SURVEY",
              numeric=True),
        Param("S_ANGLE", "field", N_("Поле угла"),
              N_("Поле угла наклона, в соглашении, выбранном ниже."),
              default="dip", optional=True, parent="SURVEY", numeric=True),
        Param("CONVENTION", "enum", N_("Как записан угол"),
              N_("Как записан угол. Перепутанное соглашение уводит "
                 "ствол вверх или кладёт его горизонтально, поэтому "
                 "проверьте по одной известной скважине."),
              default=0,
              options=(N_("От горизонта, вниз отрицательный "
                          "(-90 - отвесно вниз)"),
                       N_("От горизонта, вниз положительный "
                          "(90 - отвесно вниз)"),
                       N_("Зенитный, от вертикали (0 - отвесно вниз)"))),
        Param("STEP", "number", N_("Шаг узлов ствола, м"),
              N_("Шаг узлов ствола вдоль дуги, метры. По узлам ствол "
                 "рисуется, и по ним же 2.18 находит точки на глубинах."),
              default=1.0, minimum=0.01, advanced=True),
        Param("OUTPUT", "sink", N_("Стволы скважин"),
              N_("Стволы скважин: линии с настоящими Z от устья до "
                 "забоя. Длина линии равна глубине по стволу, поэтому "
                 "2.18 режет её на интервалы без таблицы глубин."),
              geometry="lines"),
    ],
    run=run)
