#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Прогон 2.13 в QGIS без окна: прежний класс против нового.

python-qgis.bat tools/qgis_check/run_213.py
    <папка с пакетом isoliner3d> <выход.json> <рабочая папка>

Гриды пишутся GDAL в рабочую папку: плоский пласт в два пласта,
пустые ячейки со своим nodata, подошва выше кровли, разрыв на два
тела. Если у пакета есть toolspec.RasterResult, вдобавок прогоняется
проверочный инструмент с растровым выходом: мощность пласта каналом.
"""
import json
import os
import sys

import numpy as np
from osgeo import gdal, osr
from qgis.core import (QgsApplication, QgsProcessingContext,
                       QgsProcessingFeedback, QgsRasterLayer,
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
PROV = Isoliner3DProvider()   # ссылка держит провайдер живым
QgsApplication.processingRegistry().addProvider(PROV)


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


def tiff(name, bands, nodata=None, cell=10.0):
    path = os.path.join(work, name)
    ny, nx = bands[0].shape
    ds = gdal.GetDriverByName("GTiff").Create(path, nx, ny, len(bands),
                                              gdal.GDT_Float32)
    ds.SetGeoTransform((512000.0, cell, 0.0, 6401000.0, 0.0, -cell))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(32640)
    ds.SetProjection(srs.ExportToWkt())
    for i, a in enumerate(bands, 1):
        rb = ds.GetRasterBand(i)
        if nodata is not None:
            rb.SetNoDataValue(nodata)
            a = np.where(np.isnan(a), nodata, a)
        rb.WriteArray(a)
        rb.SetDescription("b%d" % i)
    ds = None
    return path


yy, xx = np.mgrid[0:12, 0:15].astype(float)
top = -100.0 + 0.3 * xx - 0.2 * yy
bot = top - 4.0 - 0.1 * xx
holes = top.copy()
holes[3:5, 6:9] = np.nan
split = top.copy()
split[:, 7] = np.nan
neg = bot.copy()
neg[0, 0:3] = top[0, 0:3] + 2.0
grids = {
    "flat": tiff("flat.tif", [top, bot, top - 30, bot - 35]),
    "holes": tiff("holes.tif", [holes, bot], nodata=-9999.0),
    "split": tiff("split.tif", [split, bot]),
    "neg": tiff("neg.tif", [top, neg]),
    "empty": tiff("empty.tif", [np.full((4, 4), np.nan)] * 2,
                  nodata=-9999.0),
}
cases = [("flat", 1, 1), ("flat", 3, 1), ("flat", 1, 2), ("flat", 1, 3),
         ("flat", 4, 1), ("holes", 1, 1), ("split", 1, 1), ("neg", 1, 1),
         ("empty", 1, 1)]

report = {"package": os.path.dirname(isoliner3d.__file__), "runs": []}
for tag, band, step in cases:
    fb = Feed()
    lyr = QgsRasterLayer(grids[tag], tag)
    run = {"input": tag, "band": band, "step": step}
    try:
        res = processing.run("isoliner3d:grid_to_shell", {
            "INPUT": lyr, "BAND": band, "STEP": step, "OUTPUT": "memory:"},
            context=QgsProcessingContext(), feedback=fb)
        out = res["OUTPUT"]
        if isinstance(out, str):
            out = QgsVectorLayer(out, "r", "ogr")
        run.update({
            "fields": out.fields().names(), "wkb": out.wkbType(),
            "crs": out.crs().authid(),
            "rows": [[str(a) for a in f.attributes()]
                     + [f.geometry().asWkt(3)] for f in out.getFeatures()]})
    except Exception as exc:  # отказ тоже итог
        run["error"] = str(exc)
    run["log"] = [x for x in fb.lines if not x[1].startswith("Results")]
    report["runs"].append(run)

# Растровый выход обёртки: проверочный инструмент, в панель не идёт.
try:
    from isoliner3d import toolspec
    have_raster = hasattr(toolspec, "RasterResult")
except ImportError:
    have_raster = False
if have_raster:
    from isoliner3d.algorithms import SpecAlgorithm

    def thick_run(values, rep):
        g = values["INPUT"]
        b = values["BAND"]
        t = g.band(b) - g.band(b + 1)
        rep.info("meta %s", json.dumps(values["@INPUT"],
                                       ensure_ascii=False))
        return {"OUTPUT": toolspec.RasterResult(toolspec.Grid(
            [t, t * 2.0], transform=g.transform, names=["мощность", "x2"],
            meta={"ZMIN": "1.5"}), name="Мощность")}

    THICK = toolspec.Tool(
        "9.99", "check_thickness", "Мощность", "2", "", [
            toolspec.Param("INPUT", "raster", "Грид", "h"),
            toolspec.Param("BAND", "band", "Канал", "h", default=1,
                           parent="INPUT"),
            toolspec.Param("OUTPUT", "sink", "Мощность", "h",
                           geometry="raster")], thick_run)

    class CheckThickness(SpecAlgorithm):
        def spec(self):
            return THICK

        def name(self):
            return "check_thickness"

        def displayName(self):
            return "9.99 check"

    fb = Feed()
    dest = os.path.join(work, "thick_out.tif")
    if os.path.exists(dest):
        os.remove(dest)
    run = {"input": "raster_out"}
    try:
        res = processing.run(CheckThickness(), {
            "INPUT": QgsRasterLayer(grids["holes"], "holes"), "BAND": 1,
            "OUTPUT": dest}, context=QgsProcessingContext(), feedback=fb)
        ds = gdal.Open(res["OUTPUT"])
        a = ds.GetRasterBand(1).ReadAsArray().astype(float)
        want = np.where(np.isnan(holes), np.nan, holes - bot)
        run.update({
            "path": res["OUTPUT"], "bands": ds.RasterCount,
            "size": [ds.RasterXSize, ds.RasterYSize],
            "gt": list(ds.GetGeoTransform()),
            "epsg": osr.SpatialReference(ds.GetProjection())
            .GetAuthorityCode(None),
            "names": [ds.GetRasterBand(i).GetDescription()
                      for i in (1, 2)],
            "meta": ds.GetMetadata(),
            "max_err": float(np.nanmax(np.abs(a - want))),
            "nan_same": bool(np.array_equal(np.isnan(a),
                                            np.isnan(want))),
            "band2_ok": bool(np.allclose(
                ds.GetRasterBand(2).ReadAsArray(), 2 * a,
                equal_nan=True))})
        ds = None
    except Exception as exc:
        run["error"] = repr(exc)
    run["log"] = [x for x in fb.lines if not x[1].startswith("Results")]
    report["raster_out"] = run

with open(out_json, "w", encoding="utf-8") as fh:
    json.dump(report, fh, ensure_ascii=False, indent=1)
app.exitQgis()
print("done")
