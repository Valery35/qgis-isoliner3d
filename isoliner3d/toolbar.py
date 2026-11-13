# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Плашка значков окна сцены: общий список модуля и Isoliner Scene.

Образец - плашка модуля (решение автора). Список задаёт порядок
кнопок, разделители, ключ действия, подсказки и имя значка. Isoliner
Scene берёт выгрузку toolbar.json вместе с SVG значков
(tools/make_fixtures.py), значки нарисованы тем же кодом, что в окне
модуля (viewer3d._tool_icon).

where - "both" (обе программы), "pro" (только модуль: обновить из
QGIS, слои проекта, открыть в Isoliner Scene), "lite" (только
Isoliner Scene). mode - кнопка видна только в этом режиме (draw:
рисование контура). checkable - кнопка-переключатель.
Подсказки ru совпадают с tr() окна модуля, en берётся из таблицы
переводов. Без Qt и QGIS.
"""

VERSION = 1

SEP = {"sep": True}


def _b(key, icon, ru, where="both", **kw):
    out = {"key": key, "icon": icon, "ru": ru, "where": where}
    out.update(kw)
    return out


ITEMS = [
    _b("rebuild", "rebuild", "Обновить сцену"),
    SEP,
    _b("params", "params",
       "Параметры сцены: вид, камера, оформление, короб, обрезка"),
    _b("top", "top", "Вид сверху, план"),
    _b("home", "home",
       "Сбросить вид: угол обзора, ракурс и кадр по сцене"),
    _b("section", "section",
       "Вид по разрезу: камера поперёк линии обрезки, поворот заперт, "
       "остаются сдвиг и масштаб", checkable=True),
    _b("draw", "draw",
       "Рисовать контур по поверхности: клик ставит вершину.",
       checkable=True),
    _b("draw_undo", "undo", "Снять последнюю вершину", mode="draw"),
    _b("draw_close", "done", "Замкнуть контур и обрезать сцену",
       mode="draw"),
    _b("draw_line", "line", "Завершить линию и резать по ней",
       mode="draw"),
    _b("clip_clear", "clear", "Снять обрезку, наброски и точку опроса"),
    _b("draw_save", "save", "Сохранить нарисованный контур слоем проекта",
       "pro"),
    _b("shells", "shell", "Оболочки выбранного слоя в слой проекта",
       "pro"),
    _b("export", "export", "Выгрузить сцену в файл: GLB, STL или OBJ"),
    _b("export_package", "save",
       "Сохранить пакет сцены (.i3dscene)", "lite"),
    _b("scene_app", "scene",
       "Открыть в Isoliner Scene: сцена в отдельной программе. "
       "Повторное нажатие обновляет её там", "pro"),
    _b("spin", "spin", "Вращать сцену (ещё раз - остановить)",
       checkable=True),
    _b("views", "views",
       "Виды облёта: запомнить текущий вид, убрать, перейти к виду"),
    _b("video", "frames",
       "Записать видео: оборот вокруг сцены или облёт по видам, файлом "
       "MP4 или кадрами PNG"),
    _b("copy", "copy", "Положить кадр сцены в буфер обмена (Ctrl+C)"),
    _b("png", "png", "Сохранить кадр сцены в файл PNG"),
    _b("about", "about", "О программе: кто мы и где нас найти"),
]


def buttons():
    """Кнопки без разделителей, в порядке плашки."""
    return [i for i in ITEMS if not i.get("sep")]


def icons():
    """Имена значков, которые нужны списку."""
    return sorted({b["icon"] for b in buttons()})


def as_json():
    """Список для Isoliner Scene (toolbar.json), с английскими
    подсказками из таблицы переводов модуля."""
    from .i18n import TRANSLATIONS
    items = []
    for i in ITEMS:
        i = dict(i)
        if not i.get("sep"):
            i["en"] = TRANSLATIONS.get(i["ru"], i["ru"])
            i["svg"] = "icons/%s.svg" % i["icon"]
        items.append(i)
    return {"version": VERSION, "items": items}
