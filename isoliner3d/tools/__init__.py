# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Инструменты Isoliner3D как объекты: реестр описаний.

Каждый модуль пакета задаёт SPEC (toolspec.Tool). Пакет не знает
QGIS: его берут обёртка Processing, выгрузка tools.json и тесты.
Инструменты переходят сюда по одному, остальные пока живут
классами в algorithms.py.
"""

from . import boolean_shells, fill_volume, select_by_shell, sweep_body

TOOLS = [boolean_shells.SPEC, select_by_shell.SPEC, fill_volume.SPEC,
         sweep_body.SPEC]


def by_name(name):
    """Описание по имени Processing."""
    for t in TOOLS:
        if t.name == name:
            return t
    raise KeyError(name)
