#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Прогон 2.18 в QGIS без окна: прежний класс против нового.

python-qgis.bat tools/qgis_check/run_218.py
    <папка с пакетом isoliner3d> <выход.json>
"""
import json
import os
import sys

from qgis.core import (QgsApplication, QgsFeature, QgsField, QgsGeometry,
                       QgsProcessingContext, QgsProcessingFeedback,
                       QgsVectorLayer)
from qgis.PyQt.QtCore import QVariant

pkg_parent, out_json = sys.argv[1], sys.argv[2]
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
S, D, I = QVariant.String, QVariant.Double, QVariant.Int


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


def layer(uri, fields, rows):
    lyr = QgsVectorLayer(uri + ("?crs=EPSG:32640" if uri != "None"
                                else ""), "l", "memory")
    pr = lyr.dataProvider()
    pr.addAttributes([QgsField(n, t) for n, t in fields])
    lyr.updateFields()
    fts = []
    for wkt, attrs in rows:
        ft = QgsFeature(lyr.fields())
        if wkt:
            ft.setGeometry(QgsGeometry.fromWkt(wkt))
        ft.setAttributes(attrs)
        fts.append(ft)
    pr.addFeatures(fts)
    return lyr


def P(x, y, z):
    return "%f %f %f" % (X0 + x, Y0 + y, z)


traces = layer("MultiLineStringZ", [("hole", S)], [
    ("MultiLineStringZ((%s, %s, %s))" % (P(0, 0, 0), P(0, 0, -60),
                                         P(10, 0, -100)), ["H1"]),
    ("MultiLineStringZ((%s, %s), (%s, %s))"
     % (P(20, 0, 0), P(20, 0, -50), P(30, 0, 0), P(30, 0, -9)), ["H2"]),
])
traces2d = layer("LineString", [("hole", S)], [
    ("LineString(%f %f, %f %f)" % (X0, Y0, X0 + 5, Y0), ["F1"]),
])
table = layer("None", [("hole", S), ("from_m", D), ("to_m", D),
                       ("au", D), ("lith", S), ("n", I)], [
    (None, ["H1", 0.0, 10.0, 1.5, "A", 1]),
    (None, ["H1", 10.0, 30.0, 3.0, "B", 2]),
    (None, ["H1", 90.0, 120.0, None, "C", 3]),
    (None, [" H2 ", 5.0, 15.0, 7.0, "D", 4]),
    (None, ["H2", 5.0, 5.0, 9.0, "E", 5]),
    (None, ["LOST", 0.0, 1.0, 1.0, "F", 6]),
])

cases = [
    ("table", {"TRACES": traces, "MODE": 0, "TABLE": table}),
    ("equal", {"TRACES": traces, "MODE": 1, "LENGTH": 25.0}),
    ("composite", {"TRACES": traces, "MODE": 2, "TABLE": table,
                   "LENGTH": 20.0}),
    ("composite_au", {"TRACES": traces, "MODE": 2, "TABLE": table,
                      "LENGTH": 7.0, "VALUES": ["au"]}),
    ("no_table", {"TRACES": traces, "MODE": 0}),
    ("flat", {"TRACES": traces2d, "MODE": 1}),
]
report = {"package": os.path.dirname(isoliner3d.__file__), "runs": []}


def dump(lyr):
    if isinstance(lyr, str):
        lyr = QgsVectorLayer(lyr, "r", "ogr")
    return {"fields": [(f.name(), f.typeName()) for f in lyr.fields()],
            "wkb": lyr.wkbType(),
            "rows": [[str(a) for a in f.attributes()]
                     + [f.geometry().asWkt(3)] for f in lyr.getFeatures()]}


for tag, extra in cases:
    fb = Feed()
    params = dict({"OUTPUT": "memory:", "OUTPUT_POINTS": "memory:"},
                  **extra)
    try:
        res = processing.run("isoliner3d:hole_intervals", params,
                             context=QgsProcessingContext(), feedback=fb)
        run = {"case": tag, "out": dump(res["OUTPUT"]),
               "points": dump(res["OUTPUT_POINTS"])}
    except Exception as exc:  # отказ тоже итог
        run = {"case": tag, "error": str(exc)}
    run["log"] = [x for x in fb.lines if not x[1].startswith("Results")]
    report["runs"].append(run)

with open(out_json, "w", encoding="utf-8") as fh:
    json.dump(report, fh, ensure_ascii=False, indent=1)
app.exitQgis()
print("done")
