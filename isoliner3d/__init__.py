# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Точка входа плагина Isoliner3D для QGIS."""


def classFactory(iface):
    from .plugin import Isoliner3DPlugin
    return Isoliner3DPlugin(iface)
