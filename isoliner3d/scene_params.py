# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Окно «Параметры сцены»: общий список полей модуля и Isoliner Scene.

Список один на оба приложения. Модуль его ведёт, Isoliner Scene берёт
выгрузку scene_params.json (tools/make_fixtures.py) и строит по ней
своё окно: вкладки, группы, порядок, подписи. Тесты с обеих сторон
сверяют окно со списком, поэтому расхождение не пройдёт молча.

key - ключ в state файла scene.json пакета .i3dscene. Ключи камеры
пишутся через точку: camera.azimuth лежит в state["camera"] и в
корневом camera. where - "both" (оба приложения), "pro" (только
модуль), "lite" (только Isoliner Scene, в пакет не пишется).
Подписи ru совпадают с tr() окна модуля, en - с переводом в i18n.
Без Qt и QGIS.
"""

VERSION = 1

NONE_Z = -1e7      # отметка обрезки «нет»


def _p(key, ru, en, kind, where="both", **kw):
    out = {"key": key, "ru": ru, "en": en, "kind": kind, "where": where}
    out.update(kw)
    return out


def _c(value, ru, en):
    return {"value": value, "ru": ru, "en": en}


GROUPS = [
    {"id": "view", "ru": "Вид", "en": "View", "sections": [
        # Система координат сцены - для модулей (QGIS и RustGIS), Лайт
        # её не показывает. В QGIS это система проекта, окно её только
        # показывает, а пакет пишет её и в meta.crs.authid.
        {"ru": "Система координат", "en": "Coordinate system", "params": [
            _p("scene_crs", "Система координат сцены (EPSG)",
               "Scene coordinate system (EPSG)", "string", "pro",
               default="",
               hint="Код EPSG системы, в метрах которой строится сцена, "
                    "например EPSG:28410. Пусто - система проекта.",
               hint_en="The EPSG code of the system the scene is built "
                       "in, for example EPSG:28410. Empty takes the "
                       "project's system."),
        ]},
        {"ru": "Масштаб", "en": "Scale", "params": [
            _p("vex", "Вертикальное преувеличение",
               "Vertical exaggeration", "float",
               min=0.01, max=10000.0, step=0.5, default=5.0),
            _p("spacing", "Разнос по Z, м", "Z spacing, m", "float",
               "pro", min=0.0, max=1e9, step=1.0, default=0.0),
            _p("opacity", "Прозрачность, %", "Transparency, %", "float",
               min=0.0, max=95.0, step=1.0, default=0.0),
        ]},
        {"ru": "Камера", "en": "Camera", "params": [
            _p("camera.azimuth", "Азимут, °", "Azimuth, °", "float",
               min=-360.0, max=720.0, step=1.0, default=45.0),
            _p("camera.elevation", "Наклон, °", "Elevation, °", "float",
               min=-90.0, max=90.0, step=1.0, default=30.0),
            _p("camera.distance", "Удаление, м", "Distance, m", "float",
               min=0.01, max=1e9, step=1.0),
            _p("camera.fov", "Угол обзора, °", "Field of view, °",
               "float", min=1.0, max=150.0, step=1.0, default=60.0),
            _p("camera.ortho", "Параллельная проекция",
               "Orthographic projection", "bool", default=False),
        ]},
        {"ru": "", "en": "", "params": [
            _p("auto_rebuild", "Обновлять автоматически",
               "Update automatically", "bool", "pro", default=False,
               stored=False),
        ]},
    ]},
    {"id": "look", "ru": "Оформление", "en": "Appearance", "sections": [
        {"ru": "Оформление", "en": "Appearance", "params": [
            _p("bg_grad", "Градиентный фон", "Gradient background",
               "bool", default=True),
            _p("smooth_edges", "Сглаживать края", "Smooth the edges", "bool",
               default=True),
            _p("sketch_on", "Показывать разметку", "Show sketch", "bool",
               default=True),
            _p("theme", "Тема", "Theme", "choice", "lite",
               stored=False, choices=[
                   _c("light", "Светлая", "Light"),
                   _c("dark", "Тёмная", "Dark")]),
        ]},
        {"ru": "Нагрузка", "en": "Load", "params": [
            _p("texside", "Текстура, пикс.", "Texture, px", "int", "pro",
               min=256, max=8192, step=512, default=2048),
            _p("vert_cap", "Предел вершин, тыс.",
               "Vertex limit, thousands", "int", "pro",
               min=100, max=8000, step=100),
        ]},
    ]},
    {"id": "light", "ru": "Освещение", "en": "Lighting", "sections": [
        {"ru": "Солнце", "en": "Sun", "params": [
            _p("sun_az", "Азимут Солнца, °", "Sun azimuth, °", "float",
               min=0.0, max=360.0, step=15.0, default=218.0),
            _p("sun_alt", "Высота Солнца, °", "Sun altitude, °", "float",
               min=1.0, max=90.0, step=5.0, default=55.0),
            _p("light", "Отмывка", "Hillshade", "int",
               min=0, max=100, step=5, default=55),
        ]},
        {"ru": "Тени", "en": "Shadows", "toggle": "shadows_on",
         "params": [
             _p("shadows_on", "Тени", "Shadows", "bool", default=False),
             _p("shadow_k", "Сила тени, %", "Shadow strength, %", "int",
                min=0, max=100, step=5, default=50),
         ]},
    ]},
    {"id": "box", "ru": "Короб", "en": "Box", "sections": [
        {"ru": "Координатный короб", "en": "Coordinate box",
         "toggle": "axes_on", "params": [
             _p("axes_on", "Координатный короб", "Coordinate box",
                "bool", default=False),
             _p("box_edges", "Рёбра", "Edges", "choice", default="all",
                choices=[
                    _c("all", "Все двенадцать", "All twelve"),
                    _c("axes", "Три оси из угла",
                       "Three axes from the corner"),
                    _c("none", "Без рёбер", "No edges")]),
             _p("box_near", "подписи к ближним", "labels to the near edges",
                "bool", default=True, row_with="box_edges"),
             _p("grid_planes", "Сетка", "Grid", "choice", default="",
                choices=[
                    _c("", "Только короб", "Box only"),
                    _c("floor", "Пол", "Floor"),
                    _c("floor,walls", "Пол и стены", "Floor and walls"),
                    _c("walls", "Стены", "Walls")]),
             _p("grid_step", "Шаг сетки, м", "Grid step, m", "float",
                min=0.0, max=1e6, step=10.0, default=0.0),
             _p("tick_xy", "Шаг делений: план, Z", "Tick step: plan, Z",
                "float", min=0.0, max=1e7, default=0.0),
             _p("tick_z", "Шаг делений: план, Z", "Tick step: plan, Z",
                "float", min=0.0, max=1e7, default=0.0),
             _p("mult_xy", "Множитель подписей: план, Z",
                "Label multiplier: plan, Z", "float", min=-1e6, max=1e6,
                default=1.0),
             _p("mult_z", "Множитель подписей: план, Z",
                "Label multiplier: plan, Z", "float", min=-1e6, max=1e6,
                default=1.0),
         ]},
        {"ru": "Охват короба", "en": "Box extent", "params": [
            _p("box_range_on", "Свой охват короба", "Own box extent",
               "bool", default=False),
            _p("box_range", "X, Y, Z от и до", "X, Y, Z from and to",
               "float6", default=[0.0] * 6),
        ]},
    ]},
    {"id": "clip", "ru": "Обрезка", "en": "Clipping", "sections": [
        {"ru": "Обрезка", "en": "Clipping", "params": [
            _p("clip", "Контуром или линией", "By an outline or a line",
               "layer", "pro"),
            _p("side", "Что оставить", "What to keep", "choice",
               default="in", choices=[
                   _c("in", "Оставить внутри", "Keep what is inside"),
                   _c("out", "Убрать внутри", "Remove what is inside"),
                   _c("left", "Слева от линии", "To the left of the line"),
                   _c("right", "Справа от линии", "To the right of the line"),
                   _c("corridor", "Коридор вдоль линии",
                      "A corridor along the line")]),
            _p("width", "Полуширина коридора, м",
               "Corridor half-width, m", "float", min=0.0, max=1e9,
               default=250.0),
            _p("zlo", "По отметке", "By elevation", "float",
               min=NONE_Z, max=1e7, default=NONE_Z),
            _p("zhi", "По отметке", "By elevation", "float",
               min=NONE_Z, max=1e7, default=NONE_Z),
            _p("zs_top", "Сверху и снизу (растры)",
               "Above and below (rasters)", "layer", "pro"),
            _p("zs_bot", "Сверху и снизу (растры)",
               "Above and below (rasters)", "layer", "pro"),
        ]},
        {"ru": "Маска и заборы", "en": "Mask and fences", "params": [
            _p("mask_lyr", "По маске (растр)", "By a mask (raster)",
               "layer", "pro"),
            _p("mask_level", "По маске (растр)", "By a mask (raster)",
               "float", "pro", default=0.5),
            _p("fence_all", "Показать заборами по линии",
               "Show as fences along the line", "bool", "pro",
               default=False),
        ]},
    ]},
]


def params():
    """Все поля подряд, в порядке окна."""
    return [p for g in GROUPS for s in g["sections"] for p in s["params"]]


def stored_keys():
    """Ключи, которые едут в пакет: без свойств программы."""
    return [p["key"] for p in params() if p.get("stored", True)
            and p["where"] != "lite"]


def as_json():
    """Список для Isoliner Scene словарём (scene_params.json)."""
    return {"version": VERSION, "window": {
        "ru": "Параметры сцены", "en": "Scene settings"},
        "groups": GROUPS}
