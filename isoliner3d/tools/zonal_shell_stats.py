# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""2.14 Зональная статистика оболочек: описание и расчёт без QGIS.

Это 2.12 с другой стороны: там отбираются объекты по одному телу,
здесь по каждому телу записывается, сколько в него попало. Числа
ложатся в атрибуты тел, и по ним можно сортировать, красить
и отдавать дальше.

Точки считаются лучом вверх по чётности. Линии режутся телом:
отрезок пересекается с треугольниками, точки сортируются вдоль
него, и суммируется только часть внутри. Отрезок, прошивший тело
насквозь между своими вершинами, здесь тоже попадает в счёт.
"""

import numpy as np

from ..toolspec import N_, Param, Result, Tool, ToolError

# поля объектов во втором выходе; занятое имя получает номер: zone_2
ZONE_FIELDS = (("zone", "string"), ("zone_ids", "string"),
               ("zone_n", "int"))

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
    "ё": "e", "ж": "zh", "з": "z", "и": "i", "й": "j", "к": "k",
    "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c",
    "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya"}


def slug(name):
    """Имя поля из имени слоя: латиница, подчёркивания, коротко."""
    out = []
    for ch in name.lower():
        if ch in _TRANSLIT:
            out.append(_TRANSLIT[ch])
        elif ch.isalnum() and ord(ch) < 128:
            out.append(ch)
        else:
            out.append("_")
    s = "".join(out).strip("_")
    while "__" in s:
        s = s.replace("__", "_")
    if not s or s[0].isdigit():
        s = "l_" + s
    return s[:20]


def _numv(v):
    """Число из атрибута или None: пустое и текст не превращаются в 0."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _unique(key, have):
    nm, k = key, 2
    while nm in have:
        nm = "%s_%d" % (key, k)
        k += 1
    return nm


def run(values, report):
    """Расчёт 2.14: счёт объектов values["INPUT"] в телах SHELLS."""
    from .. import boolean3d, zonal
    from ..cleanup import shell_defects

    meta_in = values.get("@INPUT") or {}
    meta_sh = values.get("@SHELLS") or {}
    geom = meta_in.get("geometry") or ""
    is_pt = geom == "point"
    is_ln = geom == "line"
    name = (values.get("NAME") or "").strip()
    if not name:
        name = slug(meta_in.get("name") or "layer")
    attr = values.get("ATTR") or ""
    picked = values.get("STATS") or []
    keys = [zonal.KEYS[i] for i in (picked if picked else [0])
            if 0 <= i < len(zonal.KEYS)] or ["sum"]
    overwrite = bool(values.get("OVERWRITE"))
    zone_field = values.get("ZONE_FIELD") or ""

    # Поля результата. Столкновение имён - отказ, если не разрешено:
    # иначе второй прогон тихо затирает первый.
    new_fields = [(name + "_n", "int")]
    if is_ln:
        new_fields.append((name + "_len", "double"))
    if attr:
        for suf in zonal.suffixes(keys):
            new_fields.append((name + suf, "double"))
    have = set(meta_sh.get("fields") or [])
    clash = [nm for nm, _t in new_fields if nm in have]
    if clash and not overwrite:
        raise ToolError(N_("Поля %s уже есть у слоя тел. Задайте другое "
                           "имя или разрешите перезапись."),
                        ", ".join(clash))

    shells = []
    for item in values["SHELLS"]:
        if report.canceled():
            break
        v, f = item.get("verts"), item.get("faces")
        closed = False
        if v is not None and f is not None and len(f):
            v = np.asarray(v, dtype=float)
            f = np.asarray(f, dtype=np.int64)
            closed = shell_defects(v, f)[0] == 0
        shells.append((item, v, f, closed))
    n_open = sum(1 for _i, _v, _f, c in shells if not c)
    report.info(N_("Тел: %d, незамкнутых %d."), len(shells), n_open)
    if n_open:
        report.warn(N_("Незамкнутых тел %d: им записано пусто, а не ноль. "
                       "У незамкнутого тела нет внутренности."), n_open)

    objs = []
    for item in values["INPUT"]:
        if report.canceled():
            break
        parts = [np.asarray(p, dtype=float).reshape(-1, 3)
                 for p in item.get("parts") or []]
        parts = [p for p in parts if len(p) and np.isfinite(p).all()]
        if not parts:
            continue
        val = _numv((item.get("attrs") or {}).get(attr)) if attr else None
        objs.append((item, parts, val))
    if not objs:
        raise ToolError(N_("Объектов с высотой не нашлось: у геометрии "
                           "должна быть Z."))
    total_len = 0.0
    if is_ln:
        for _it, parts, _v in objs:
            for p in parts:
                total_len += float(np.sum(np.linalg.norm(
                    np.diff(p, axis=0), axis=1)))
    all_pts = np.vstack([p for _it, parts, _v in objs for p in parts])
    owner = np.concatenate([np.full(len(p), oi, dtype=np.int64)
                            for oi, (_it, parts, _v) in enumerate(objs)
                            for p in parts])
    starts_xyz = np.array([p[0] for _it, parts, _v in objs for p in parts])
    report.info(N_("Объектов: %d."), len(objs))

    out = Result(new_fields, keep_source="SHELLS", geometry="source",
                 replace=True, name=N_("Тела со статистикой"))
    # тела, в которые попал каждый объект: подписи по порядку слоя
    zones = [[] for _o in objs]
    grand_n = 0
    grand_len = 0.0
    for si, (item, v, f, closed) in enumerate(shells):
        attrs = item.get("attrs") or {}
        label = attrs.get(zone_field) if zone_field else item.get("id")
        label = "" if label is None else str(label)
        row = {}
        if closed:
            bbox = boolean3d.tri_bbox(v, f)
            n_in = 0
            len_in = 0.0
            in_vals, in_w = [], []
            if is_ln:
                # начала всех ломаных - одним пакетом: луч по каждой
                # отдельно на большом теле занимал часы
                starts = boolean3d.points_inside(v, f, starts_xyz)
                pi = 0
                for oi, (_it, parts, val) in enumerate(objs):
                    hit = False
                    got_obj = 0.0
                    for p in parts:
                        got, _tot = boolean3d.polyline_inside_length(
                            v, f, p, bbox=bbox, start_inside=starts[pi])
                        pi += 1
                        if got > 0.0:
                            hit = True
                            len_in += got
                            got_obj += got
                    if hit:
                        n_in += 1
                        in_vals.append(val)
                        in_w.append(got_obj)
                        zones[oi].append(label)
            else:
                # Точки всех объектов - ОДНИМ пакетом. Опрос по объекту
                # за раз на двадцати тысячах блоков давал двадцать
                # тысяч проходов по оболочке и вешал QGIS.
                ins = boolean3d.points_inside(v, f, all_pts)
                for oi in range(len(objs)):
                    sel = ins[owner == oi]
                    hit = bool(sel.all()) if is_pt else bool(sel.any())
                    if hit:
                        n_in += 1
                        in_vals.append(objs[oi][2])
                        in_w.append(1.0)
                        zones[oi].append(label)
            row[name + "_n"] = int(n_in)
            if is_ln:
                row[name + "_len"] = float(len_in)
                grand_len += len_in
            if attr:
                for suf, x in zonal.stats(in_vals, in_w, keys).items():
                    row[name + suf] = x
            grand_n += n_in
        out.add({"source": item.get("id")}, row)
        report.progress(100.0 * (si + 1) / max(len(shells), 1))
    result = {"OUTPUT": out}
    if values.get("OUTPUT_OBJECTS"):
        have_in = set(meta_in.get("fields") or [])
        zone_out = []
        for key, typ in ZONE_FIELDS:
            nm = _unique(key, have_in)
            have_in.add(nm)
            zone_out.append((nm, typ))
        objs_out = Result(zone_out, keep_source="INPUT", geometry="source",
                          name=N_("Объекты с телом"))
        n_hit = 0
        for (item, _p, _v), zs in zip(objs, zones):
            first, ids, n = zonal.zone_fields(zs)
            objs_out.add({"source": item.get("id")}, [first, ids, n])
            n_hit += 1 if n else 0
        report.info(N_("Объектов в телах: %d из %d."), n_hit, len(objs))
        result["OUTPUT_OBJECTS"] = objs_out

    report.info(N_("Попаданий по всем телам: %d."), grand_n)
    if is_ln:
        report.info(N_("Длина линий: всего %.2f м, внутри тел %.2f м, "
                       "снаружи %.2f м."),
                    total_len, grand_len, total_len - grand_len)
    return result


SPEC = Tool(
    code="2.14", name="zonal_shell_stats",
    title=N_("Зональная статистика оболочек"), group="2",
    help=N_("Считает по каждому телу, сколько объектов в него попало, "
            "и записывает числа в атрибуты тела.\n\n"
            "Точки: число внутри и сумма атрибута. Линии: число линий, "
            "задевших тело, и длина их частей внутри. Полигоны: число "
            "полигонов, у которых хоть одна вершина внутри.\n\n"
            "Линия режется телом: отрезок пересекается "
            "с поверхностью, точки сортируются вдоль него, и в длину "
            "идёт только часть внутри. "
            "Отрезок, прошивший тело насквозь между своими вершинами, "
            "не пропадает.\n\n"
            "Ноль и пусто - разные вещи. Тело, внутри которого ничего "
            "нет, получает ноль: это измеренный факт. Незамкнутое тело "
            "получает пусто и попадает в предупреждение: у него нет "
            "внутренности.\n\n"
            "Повторные прогоны по одному слою тел складываются: "
            "результат предыдущего подаётся как слой тел следующему, "
            "и каждый прогон добавляет свои поля. Столкновение имён - "
            "отказ, если не разрешена перезапись.\n\n"
            "По атрибуту считается сумма, среднее, минимум, максимум, "
            "стандартное отклонение, медиана и квантили, на выбор. "
            "У точек и полигонов каждый объект весит одинаково, у линий "
            "вес - длина их части внутри тела: интервал опробования, "
            "вошедший в тело наполовину, весит половину. Пустые "
            "значения атрибута не участвуют.\n\n"
            "Сумма по телам сходится: длина линий внутри всех тел плюс "
            "длина снаружи равна полной длине, и это печатается "
            "в журнал.\n\n"
            "Второй результат, необязательный, - сами объекты с телом, "
            "в которое они попали: поля zone, zone_ids и zone_n. Так "
            "видно, какие пробы дали итог тела."),
    params=[
        Param("SHELLS", "meshes", N_("Тела (полигоны с Z)"),
              N_("Слой тел: замкнутые оболочки, по одной на объект. У "
                 "каждого тела появятся свои поля со счётом. Незамкнутое "
                 "тело получает пусто, а не ноль: у него нет "
                 "внутренности, и считать там нечего.")),
        Param("INPUT", "features", N_("Что считать (объекты с Z)"),
              N_("Что считать: точки, линии или полигоны с высотой. "
                 "Блочная модель, скважины, следы выработок, разломы.")),
        Param("NAME", "string", N_("Имя полей результата (пусто - от слоя)"),
              N_("Имя для полей результата. Пусто - от имени слоя, "
                 "приведённого к латинице. К нему добавятся суффиксы: _n "
                 "число объектов внутри, _len длина линий внутри, _sum, "
                 "_mean, _std и другие по выбранной статистике. "
                 "Задавайте своё, когда гоняете инструмент "
                 "по одному слою тел несколько раз с разными данными."),
              default="", optional=True),
        Param("ATTR", "field", N_("Атрибут для статистики"),
              N_("Числовой атрибут для статистики: металл или объём "
                 "блока, мощность, содержание. Пусто - только счёт."),
              optional=True, parent="INPUT", numeric=True),
        Param("STATS", "enum", N_("Статистика по атрибуту"),
              N_("Что считать по атрибуту. Сумма - запас, когда атрибут "
                 "уже металл блока. Для содержания нужны среднее, разброс "
                 "и квантили. У линий среднее и квантили взвешены по "
                 "длине внутри тела, как при подсчёте по композитам."),
              default=[0], optional=True, multiple=True,
              options=(N_("Сумма"), N_("Среднее"), N_("Минимум"),
                       N_("Максимум"), N_("Стандартное отклонение"),
                       N_("Медиана"), N_("Квартили 25 и 75 %"),
                       N_("Квантили 10 и 90 %"))),
        Param("OVERWRITE", "bool", N_("Разрешить перезапись полей"),
              N_("Разрешить перезапись полей с тем же именем. Без этого "
                 "повторный прогон с тем же именем - отказ: иначе "
                 "второй результат тихо затёр бы первый."),
              default=False),
        Param("OUTPUT", "sink", N_("Тела со статистикой"),
              N_("Тела со всеми прежними полями и новыми полями счёта. "
                 "Чтобы накопить несколько прогонов, подавайте результат "
                 "предыдущего как слой тел следующему."),
              geometry="source"),
        Param("ZONE_FIELD", "field",
              N_("Поле тела для объектов (пусто - номер)"),
              N_("Поле тела, которое пишется объектам: имя или код "
                 "тела. Пусто - номер объекта тела в слое."),
              optional=True, parent="SHELLS"),
        Param("OUTPUT_OBJECTS", "sink", N_("Объекты с телом"),
              N_("Сами объекты с полем тела, в которое они попали: "
                 "zone - первое тело, zone_ids - все через точку "
                 "с запятой, zone_n - сколько тел. Объект вне тел "
                 "получает пусто и ноль. Без этого слоя видно "
                 "только итог по телу, но не какие пробы его "
                 "дали."),
              optional=True, geometry="source"),
    ],
    run=run)
