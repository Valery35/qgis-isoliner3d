# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Окно «О программе» за кнопкой (i): общий список модуля и Isoliner
Scene.

Тексты ru и en и ссылки с подписями. Isoliner Scene берёт выгрузку
about.json (tools/make_fixtures.py) и строит по ней то же окно.
Номер версии каждая программа подставляет свой.

where - "both", "pro" (только модуль) или "lite" (только Isoliner
Scene), как в scene_params и toolbar. Почты здесь нет: в README и на
сайте её не дают, для связи - страница вопросов на GitHub.
Без Qt и QGIS.
"""
from urllib.parse import quote

VERSION = 1

SITE = "https://www.informpp.ru/"
_LINE = SITE + quote("главная-страница") + "/isoliner3d"
GITHUB = "https://github.com/Valery35/"
SUPPORT = GITHUB[:-1] + "#" + quote("поддержать-разработку")


def _t(ru, en, where="both"):
    return {"ru": ru, "en": en, "where": where}


def _l(url, ru, en, where="both"):
    return {"url": url, "ru": ru, "en": en, "where": where}


TITLE = [
    _t("Isoliner3D", "Isoliner3D", "pro"),
    _t("Isoliner Scene", "Isoliner Scene", "lite"),
]

TEXT = [
    _t("Модуль QGIS для трёхмерных моделей недр и поверхностей: сцена "
       "из слоёв проекта, тела пластов, блочная модель, объёмная "
       "интерполяция.",
       "A QGIS plugin for 3D models of the subsurface and surfaces: a "
       "scene from project layers, bed bodies, block model, volume "
       "interpolation.", "pro"),
    _t("Программа для просмотра сцен Isoliner3D без QGIS: открывает "
       "пакет .i3dscene со слоями, камерой и видами облёта.",
       "A program to view Isoliner3D scenes without QGIS: it opens an "
       ".i3dscene package with its layers, camera and flight views.",
       "lite"),
    _t("Линейка Isoliner3D - модуль для QGIS и программа Isoliner "
       "Scene. Окно параметров сцены и плашка у них общие.",
       "The Isoliner3D line is the QGIS plugin and the Isoliner Scene "
       "program. They share the scene settings window and the "
       "toolbar."),
    _t("© 2026 ООО «Информ++»", "© 2026 Inform++ LLC"),
    _t("Лицензия GPL-2.0-or-later", "License GPL-2.0-or-later", "pro"),
    _t("Лицензия Apache-2.0", "License Apache-2.0", "lite"),
]

LINKS = [
    _l(_LINE, "Линейка Isoliner3D на сайте",
       "The Isoliner3D line on the website"),
    _l(_LINE + "/qgis-isoliner3d", "Страница модуля", "Plugin page",
       "pro"),
    _l(_LINE + "/isoliner-scene", "Страница программы", "Program page",
       "lite"),
    _l(GITHUB + "qgis-isoliner3d", "Модуль на GitHub",
       "The plugin on GitHub"),
    _l(GITHUB + "isoliner-scene", "Isoliner Scene на GitHub",
       "Isoliner Scene on GitHub"),
    _l("https://plugins.qgis.org/plugins/isoliner3d/",
       "Модуль в каталоге QGIS", "The plugin in the QGIS catalog"),
    _l(GITHUB + "qgis-isoliner3d/issues", "Сообщить об ошибке",
       "Report a problem", "pro"),
    _l(GITHUB + "isoliner-scene/issues", "Сообщить об ошибке",
       "Report a problem", "lite"),
    _l(SUPPORT, "Поддержать разработку", "Support the development"),
    _l("https://t.me/qgis_isolines", "Telegram", "Telegram"),
    _l("https://vk.ru/qgismodules", "ВКонтакте", "VK"),
    _l("https://en.osm.town/@Vaery35", "Mastodon", "Mastodon"),
    _l("https://x.com/Valery35", "X", "X"),
    _l("https://www.facebook.com/valery35", "Facebook", "Facebook"),
    _l(SITE, "ООО «Информ++»", "Inform++ LLC"),
]


def for_app(where):
    """Записи для одной программы: "pro" или "lite"."""
    def keep(items):
        return [i for i in items if i["where"] in ("both", where)]
    return {"title": keep(TITLE), "text": keep(TEXT),
            "links": keep(LINKS)}


def as_json():
    """Список для Isoliner Scene (about.json)."""
    return {"version": VERSION, "window": {"ru": "О программе",
                                           "en": "About"},
            "title": TITLE, "text": TEXT, "links": LINKS}
