#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Прогон 2.17 в QGIS без окна: прежний класс против нового.

python-qgis.bat tools/qgis_check/run_217.py
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
S, D = QVariant.String, QVariant.Double


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


col_table = layer("None", [("hole", S), ("x", D), ("y", D), ("z", D),
                           ("eoh", D)], [
    (None, [" H1", X0 + 100, Y0 + 200, 50.0, 120.0]),
    (None, ["H2", X0 + 150, Y0 + 200, 48.0, 80.0]),
    (None, ["H3", X0 + 1, Y0 + 1, 0.0, None]),
    (None, [None, X0 + 1, Y0 + 1, 0.0, 10.0]),
])
survey = layer("None", [("hole", S), ("depth", D), ("azimuth", D),
                        ("dip", D)], [
    (None, ["H1", 0.0, 45.0, -60.0]),
    (None, ["H1", 60.0, 50.0, -55.0]),
    (None, ["H1", 100.0, None, -50.0]),
    (None, ["LOST", 0.0, 0.0, -90.0]),
])
col_ptz = layer("PointZ", [("hole", S), ("eoh", D), ("azi", D),
                           ("ang", D)], [
    ("PointZ(%f %f 70)" % (X0 + 5, Y0 + 6), ["P1", 10.0, 90.0, -45.0]),
    ("PointZ(%f %f 65)" % (X0 + 9, Y0 + 6), ["P2", 25.0, 180.0, -70.0]),
])
col_pt = layer("Point", [("BHID", S), ("DEPTH", D)], [
    ("Point(%f %f)" % (X0 + 5, Y0 + 6), ["D1", 30.0]),
])
survey_dm = layer("None", [("BHID", S), ("AT", D), ("BRG", D),
                           ("DIP", D)], [
    (None, ["D1", 0.0, 10.0, 30.0]),
    (None, ["D1", 20.0, 20.0, 25.0]),
])

cases = [
    ("table", {"COLLARS": col_table, "SURVEY": survey}),
    ("table_zenith", {"COLLARS": col_table, "SURVEY": survey,
                      "CONVENTION": 2, "STEP": 5.0}),
    ("points_z", {"COLLARS": col_ptz}),
    ("points_collar_dir", {"COLLARS": col_ptz, "C_AZI": "azi",
                           "C_ANGLE": "ang"}),
    ("points_noz_names", {"COLLARS": col_pt, "SURVEY": survey_dm,
                          "HOLE": "", "EOH": "", "S_HOLE": "",
                          "S_DEPTH": "", "S_AZI": "", "S_ANGLE": "",
                          "CONVENTION": 1}),
    ("no_hole", {"COLLARS": col_pt, "HOLE": "", "EOH": "DEPTH"}),
]
cases[-1][1]["HOLE"] = ""
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
    params = dict({"OUTPUT": "memory:"}, **extra)
    try:
        res = processing.run("isoliner3d:desurvey_holes", params,
                             context=QgsProcessingContext(), feedback=fb)
        run = {"case": tag, "out": dump(res["OUTPUT"])}
    except Exception as exc:  # отказ тоже итог
        run = {"case": tag, "error": str(exc)}
    run["log"] = [x for x in fb.lines if not x[1].startswith("Results")]
    report["runs"].append(run)

with open(out_json, "w", encoding="utf-8") as fh:
    json.dump(report, fh, ensure_ascii=False, indent=1)
app.exitQgis()
print("done")
