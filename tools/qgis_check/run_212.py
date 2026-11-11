#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Прогон 2.12 в QGIS без окна: прежний класс против нового.

python-qgis.bat tools/qgis_check/run_212.py
    <папка с пакетом isoliner3d> <выход.json> <рабочая папка>
"""
import json
import os
import sys

from qgis.core import (QgsApplication, QgsFeature, QgsField, QgsGeometry,
                       QgsProcessingContext, QgsProcessingFeedback,
                       QgsVectorLayer)
from qgis.PyQt.QtCore import QVariant

pkg_parent, out_json, work = sys.argv[1], sys.argv[2], sys.argv[3]
app = QgsApplication([], False)
app.initQgis()
sys.path.insert(0, os.path.join(os.environ["QGIS_PREFIX_PATH"], "python",
                                "plugins"))
import processing  # noqa: E402
from processing.core.Processing import Processing  # noqa: E402
Processing.initialize()
sys.path.insert(0, pkg_parent)
from isoliner3d.provider import Isoliner3DProvider  # noqa: E402
import isoliner3d  # noqa: E402
PROV = Isoliner3DProvider()   # ссылка держит провайдер живым
QgsApplication.processingRegistry().addProvider(PROV)

X0, Y0 = 512345.0, 6401234.0


class Feed(QgsProcessingFeedback):
    def __init__(self):
        super().__init__()
        self.lines = []

    def pushInfo(self, t):
        self.lines.append(("info", t))

    def pushWarning(self, t):
        self.lines.append(("warn", t))

    def reportError(self, t, fatal=False):
        self.lines.append(("error", t))


def layer(uri, name, rows):
    lyr = QgsVectorLayer(uri + "?crs=EPSG:32640", name, "memory")
    pr = lyr.dataProvider()
    pr.addAttributes([QgsField("name", QVariant.String),
                      QgsField("vol", QVariant.Double),
                      QgsField("g", QVariant.Double)])
    lyr.updateFields()
    fts = []
    for nm, wkt, vol, g in rows:
        ft = QgsFeature(lyr.fields())
        ft.setGeometry(QgsGeometry.fromWkt(wkt))
        ft.setAttributes([nm, vol, g])
        fts.append(ft)
    pr.addFeatures(fts)
    return lyr


def P(x, y, z):
    return "%f %f %f" % (X0 + x, Y0 + y, z)


# коробка 10 x 10 x 10 м: x 0..10, y 0..10, z -300..-290
axis = QgsVectorLayer("LineStringZ?crs=EPSG:32640", "ax", "memory")
ft = QgsFeature(axis.fields())
ft.setGeometry(QgsGeometry.fromWkt("LineStringZ(%s, %s)"
                                   % (P(0, 5, -300), P(10, 5, -300))))
axis.dataProvider().addFeatures([ft])
shell = os.path.join(work, "shell.gpkg")
if os.path.exists(shell):
    os.remove(shell)
shell = processing.run("isoliner3d:sweep_body", {
    "INPUT": axis, "PROFILE": 1, "WIDTH": 10.0, "HEIGHT": 10.0,
    "ANCHOR": 0, "OUTPUT": shell})["OUTPUT"]

points = layer("PointZ", "pts", [
    ("in1", "PointZ(%s)" % P(5, 5, -295), 8.0, 2.0),
    ("in2", "PointZ(%s)" % P(2, 8, -291), 4.0, 5.0),
    ("out", "PointZ(%s)" % P(20, 5, -295), 8.0, 9.0),
    ("noz", "Point(%f %f)" % (X0 + 5, Y0 + 5), 1.0, 1.0),
])
lines = layer("LineStringZ", "ln", [
    ("thru", "LineStringZ(%s, %s)" % (P(-5, 5, -295), P(15, 5, -295)),
     None, None),
    ("inside", "LineStringZ(%s, %s)" % (P(2, 2, -298), P(8, 8, -292)),
     4.0, 5.0),
    ("away", "LineStringZ(%s, %s)" % (P(30, 0, -295), P(40, 0, -295)),
     2.0, 1.0),
])
polys = layer("PolygonZ", "pg", [
    ("sq_in", "PolygonZ((%s, %s, %s, %s, %s))"
     % (P(3, 3, -295), P(6, 3, -295), P(6, 6, -295), P(3, 6, -295),
        P(3, 3, -295)), 9.0, 1.0),
])

report = {"package": os.path.dirname(isoliner3d.__file__), "runs": []}
for tag, src in (("points", points), ("lines", lines), ("polys", polys)):
    for mode in (0, 1, 2):
        for step in (0.0, 1.0):
            fb = Feed()
            try:
                res = processing.run("isoliner3d:select_by_shell", {
                    "INPUT": src, "SHELL": shell, "MODE": mode,
                    "STEP": step, "VOLUME": "vol", "GRADE": "g",
                    "DENSITY": 2.5, "OUTPUT": "memory:"},
                    context=QgsProcessingContext(), feedback=fb)
                out = res["OUTPUT"]
                if isinstance(out, str):
                    out = QgsVectorLayer(out, "r", "ogr")
                rows = [[str(a) for a in f.attributes()]
                        + [f.geometry().asWkt(3)]
                        for f in out.getFeatures()]
                report["runs"].append({
                    "input": tag, "mode": mode, "step": step,
                    "fields": out.fields().names(),
                    "wkb": out.wkbType(), "rows": rows,
                    "log": [x for x in fb.lines
                            if not x[1].startswith("Results")]})
            except Exception as exc:  # отказ тоже итог
                report["runs"].append({"input": tag, "mode": mode,
                                       "step": step, "error": str(exc),
                                       "log": fb.lines})

with open(out_json, "w", encoding="utf-8") as fh:
    json.dump(report, fh, ensure_ascii=False, indent=1)
app.exitQgis()
print("done")
