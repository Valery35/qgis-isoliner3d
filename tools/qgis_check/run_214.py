#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Прогон 2.14 в QGIS без окна: прежний класс против нового.

python-qgis.bat tools/qgis_check/run_214.py
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
PROV = Isoliner3DProvider()
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


def box_tris(x0, y0, z0, s=10.0):
    v = [(x0, y0, z0), (x0 + s, y0, z0), (x0 + s, y0 + s, z0),
         (x0, y0 + s, z0), (x0, y0, z0 + s), (x0 + s, y0, z0 + s),
         (x0 + s, y0 + s, z0 + s), (x0, y0 + s, z0 + s)]
    f = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
         (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    return [[v[a], v[b], v[c]] for a, b, c in f]


def mpz(tris):
    return "MultiPolygonZ(%s)" % ", ".join(
        "((%s))" % ", ".join("%f %f %f" % (X0 + x, Y0 + y, z)
                             for x, y, z in t + [t[0]]) for t in tris)


def layer(uri, name, fields, rows):
    lyr = QgsVectorLayer(uri + "?crs=EPSG:32640", name, "memory")
    pr = lyr.dataProvider()
    pr.addAttributes([QgsField(n, t) for n, t in fields])
    lyr.updateFields()
    fts = []
    for wkt, attrs in rows:
        ft = QgsFeature(lyr.fields())
        ft.setGeometry(QgsGeometry.fromWkt(wkt))
        ft.setAttributes(attrs)
        fts.append(ft)
    pr.addFeatures(fts)
    return lyr


def P(x, y, z):
    return "%f %f %f" % (X0 + x, Y0 + y, z)


shells = layer("MultiPolygonZ", "Тела",
               [("name", QVariant.String), ("old_n", QVariant.Int)], [
                   (mpz(box_tris(0, 0, 0)), ["A", 7]),
                   (mpz(box_tris(20, 0, 0)), ["B", 7]),
                   (mpz(box_tris(40, 0, 0)[:-2]), ["C", 7]),
               ])
points = layer("PointZ", "Пробы Au", [("au", QVariant.Double)], [
    ("PointZ(%s)" % P(5, 5, 5), [2.0]),
    ("PointZ(%s)" % P(6, 6, 6), [4.0]),
    ("PointZ(%s)" % P(3, 7, 2), [None]),
    ("PointZ(%s)" % P(25, 5, 5), [10.0]),
    ("PointZ(%s)" % P(60, 0, 0), [1.0]),
    ("Point(%f %f)" % (X0 + 5, Y0 + 5), [1.0]),
])
lines = layer("LineStringZ", "Борозды", [("au", QVariant.Double)], [
    ("LineStringZ(%s, %s)" % (P(-5, 5, 5), P(15, 5, 5)), [3.0]),
    ("LineStringZ(%s, %s, %s)" % (P(22, 2, 2), P(28, 8, 8), P(35, 8, 8)),
     [6.0]),
    ("LineStringZ(%s, %s)" % (P(60, 0, 0), P(70, 0, 0)), [1.0]),
])
polys = layer("PolygonZ", "Контуры", [("au", QVariant.Double)], [
    ("PolygonZ((%s, %s, %s, %s))" % (P(5, 5, 5), P(15, 5, 5),
                                     P(15, 8, 5), P(5, 5, 5)), [1.0]),
])

cases = [
    ("points_stats", {"INPUT": points, "ATTR": "au", "STATS": [0, 1, 4, 6],
                      "ZONE_FIELD": "name", "OUTPUT_OBJECTS": "memory:"}),
    ("lines_stats", {"INPUT": lines, "ATTR": "au", "STATS": [0, 1, 5],
                     "OUTPUT_OBJECTS": "memory:"}),
    ("polys_count", {"INPUT": polys}),
    ("clash", {"INPUT": points, "NAME": "old"}),
    ("overwrite", {"INPUT": points, "NAME": "old", "OVERWRITE": True,
                   "ATTR": "au"}),
    ("default_name", {"INPUT": points}),
]
report = {"package": os.path.dirname(isoliner3d.__file__), "runs": []}


def dump(lyr):
    if isinstance(lyr, str):
        lyr = QgsVectorLayer(lyr, "r", "ogr")
    return {"fields": [(f.name(), f.typeName()) for f in lyr.fields()],
            "wkb": lyr.wkbType(),
            "rows": [[str(a) for a in f.attributes()]
                     + [f.geometry().asWkt(2)] for f in lyr.getFeatures()]}


for tag, extra in cases:
    fb = Feed()
    params = dict({"SHELLS": shells, "OUTPUT": "memory:"}, **extra)
    try:
        res = processing.run("isoliner3d:zonal_shell_stats", params,
                             context=QgsProcessingContext(), feedback=fb)
        run = {"case": tag, "out": dump(res["OUTPUT"]),
               "objects": dump(res["OUTPUT_OBJECTS"])
               if res.get("OUTPUT_OBJECTS") else None}
    except Exception as exc:  # отказ тоже итог
        run = {"case": tag, "error": str(exc)}
    run["log"] = [x for x in fb.lines if not x[1].startswith("Results")]
    report["runs"].append(run)

with open(out_json, "w", encoding="utf-8") as fh:
    json.dump(report, fh, ensure_ascii=False, indent=1)
app.exitQgis()
print("done")
