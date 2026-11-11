#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Прогон инструментов Isoliner3D в QGIS без окна.

python-qgis.bat tools/qgis_check/run_211.py
    <папка с пакетом isoliner3d> <выход.json> <рабочая папка>

Провайдер берётся прямо из папки, профили QGIS не трогаются.
Сценарий: две оси -> 2.24 (два тела-коробки) -> 2.11 тремя действиями.
"""
import json
import os
import sys

from qgis.core import (QgsApplication, QgsFeature, QgsGeometry,
                       QgsProcessingContext, QgsProcessingFeedback,
                       QgsVectorLayer)

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

prov = Isoliner3DProvider()
QgsApplication.processingRegistry().addProvider(prov)

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


def axis(name, pts):
    lyr = QgsVectorLayer("LineStringZ?crs=EPSG:32640", name, "memory")
    ft = QgsFeature(lyr.fields())
    wkt = "LineStringZ(%s)" % ", ".join("%f %f %f" % p for p in pts)
    ft.setGeometry(QgsGeometry.fromWkt(wkt))
    lyr.dataProvider().addFeatures([ft])
    return lyr


report = {"package": os.path.dirname(isoliner3d.__file__), "runs": []}
bodies = {}
for tag, pts in (("A", [(X0, Y0 + 5, -300.0), (X0 + 10, Y0 + 5, -300.0)]),
                 ("B", [(X0 + 5, Y0 + 7, -298.0),
                        (X0 + 15, Y0 + 7, -298.0)])):
    dest = os.path.join(work, "box_%s.gpkg" % tag)
    if os.path.exists(dest):
        os.remove(dest)
    fb = Feed()
    res = processing.run("isoliner3d:sweep_body", {
        "INPUT": axis(tag, pts), "PROFILE": 1, "WIDTH": 10.0,
        "HEIGHT": 10.0, "ANCHOR": 0, "OUTPUT": dest},
        context=QgsProcessingContext(), feedback=fb)
    bodies[tag] = res["OUTPUT"]
    lyr = QgsVectorLayer(res["OUTPUT"], tag, "ogr")
    report["runs"].append({"tool": "sweep_body", "tag": tag,
                           "rows": [list(map(str, f.attributes()))
                                    for f in lyr.getFeatures()],
                           "log": fb.lines})

for op in (0, 1, 2):
    fb = Feed()
    try:
        res = processing.run("isoliner3d:boolean_shells", {
            "SHELL_A": bodies["A"], "SHELL_B": bodies["B"], "OP": op,
            "CELL": 0.5, "OUTPUT": "memory:"},
            context=QgsProcessingContext(), feedback=fb)
        lyr = res["OUTPUT"]
        if isinstance(lyr, str):
            lyr = QgsVectorLayer(lyr, "r", "ogr")
        rows = []
        for f in lyr.getFeatures():
            g = f.geometry()
            rows.append({"attrs": [a if isinstance(a, (int, float, str))
                                   else str(a) for a in f.attributes()],
                         "fields": lyr.fields().names(),
                         "wkb": QgsGeometry(g).wkbType(),
                         "parts": g.constGet().numGeometries()})
        report["runs"].append({"tool": "boolean_shells", "op": op,
                               "rows": rows, "log": fb.lines})
    except Exception as exc:  # отчёт о сбое тоже итог проверки
        report["runs"].append({"tool": "boolean_shells", "op": op,
                               "error": str(exc), "log": fb.lines})

with open(out_json, "w", encoding="utf-8") as fh:
    json.dump(report, fh, ensure_ascii=False, indent=1)
app.exitQgis()
print("done")
