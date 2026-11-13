# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Значки плашки окна сцены в SVG и список toolbar.json для Isoliner
Scene.

Значки рисует тот же код, что плашку модуля (viewer3d._paint_tool),
только на холсте SVG. Нужен QtSvg, поэтому запуск из консоли Python
QGIS:

    exec(open(r"<репозиторий>/tools/export_icons.py").read(),
         {"OUT": r"<папка fixtures сцены>"})

Пишет <OUT>/toolbar.json и <OUT>/icons/<имя>.svg.
"""
import json
import os

from qgis.PyQt.QtCore import QRectF, QSize
from qgis.PyQt.QtGui import QPainter
try:
    from qgis.PyQt.QtSvg import QSvgGenerator
except ImportError:     # Qt6: генератор переехал в QtSvg тем же именем
    from PyQt6.QtSvg import QSvgGenerator

from isoliner3d import toolbar
from isoliner3d.viewer3d import _paint_tool

SIZE = 18


def export(out):
    icons = os.path.join(out, "icons")
    os.makedirs(icons, exist_ok=True)
    for name in toolbar.icons():
        gen = QSvgGenerator()
        gen.setFileName(os.path.join(icons, name + ".svg"))
        gen.setSize(QSize(SIZE, SIZE))
        gen.setViewBox(QRectF(0, 0, SIZE, SIZE))
        gen.setTitle(name)
        gen.setDescription("Isoliner3D toolbar icon")
        p = QPainter(gen)
        hint = getattr(getattr(QPainter, "RenderHint", QPainter),
                       "Antialiasing")
        p.setRenderHint(hint)
        _paint_tool(p, name, SIZE)
        p.end()
    with open(os.path.join(out, "toolbar.json"), "w",
              encoding="utf-8") as fh:
        json.dump(toolbar.as_json(), fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    return toolbar.icons()


if "OUT" in globals():
    print(export(OUT))  # noqa: F821
