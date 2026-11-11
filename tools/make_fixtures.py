#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Проверочные данные для приложений на Rust: сцена и инструменты.

Приложение сцены (isoliner-scene) и RustGIS читают то, что пишет
модуль: пакет сцены .i3dscene и tools.json. Их тесты сверяются
с файлами, которые собирает этот скрипт из кода модуля:

- scene_demo.i3dscene и scene_demo.expected.json - пакет сцены
  в настоящих координатах и то, что из него должно прочитаться;
- scene_points.i3dscene и scene_points.expected.json - то же
  с пробами, реперами и бороздами, пакет формата 2;
- tools.json - описания инструментов-объектов;
- flight.json - кадры оборота и облёта по видам (flight.py);
- sweep.json - сечения и тела вдоль оси (sweep.py, 2.24);
- tool_runs.json - прогоны инструментов-объектов: поля на входе,
  значения выходов.

Запуск: python3 tools/make_fixtures.py <папка>
"""

import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from isoliner3d import flight, scene_package, sweep, toolspec  # noqa: E402
from isoliner3d.cleanup import mesh_volume, shell_defects  # noqa: E402
from isoliner3d.tools import by_name  # noqa: E402
from isoliner3d.viewer_core import vector_export_parts  # noqa: E402

X0, Y0 = 512345.0, 6401234.0
CRS = "EPSG:32640"


def _version():
    for line in open(os.path.join(ROOT, "isoliner3d", "metadata.txt"),
                     encoding="utf-8"):
        if line.startswith("version="):
            return line.split("=", 1)[1].strip()
    return ""


def _rgba(n, rgba):
    return np.tile(np.asarray(rgba, dtype=float), (n, 1))


def demo_parts():
    """Части сцены демо: выработки, ствол, кровля пласта, короб."""
    parts = []
    drift = [(X0, Y0, -300.0), (X0 + 120.0, Y0, -302.0),
             (X0 + 120.0, Y0 + 90.0, -304.0)]
    v, f, _l, _t = sweep.sweep(drift, sweep.profile("arch", 5.0, 3.0, 1.0,
                                                    16))
    parts.append({"name": "Штрек", "verts": v, "faces": f,
                  "colors": _rgba(len(v), [0.80, 0.42, 0.18, 1.0]),
                  "layer": "drifts_1"})
    cross = [(X0 + 60.0, Y0 - 40.0, -301.0), (X0 + 60.0, Y0 + 40.0, -301.0)]
    v, f, _l, _t = sweep.sweep(cross, sweep.profile("rect", 4.0, 3.5))
    parts.append({"name": "Сбойка", "verts": v, "faces": f,
                  "colors": _rgba(len(v), [0.55, 0.60, 0.25, 1.0]),
                  "layer": "drifts_1"})
    shaft = [(X0 - 30.0, Y0 + 30.0, 0.0), (X0 - 30.0, Y0 + 30.0, -310.0)]
    v, f, _l, _t = sweep.sweep(shaft, sweep.profile("circle", 7.0,
                                                    segments=24),
                               anchor="centre")
    parts.append({"name": "Ствол", "verts": v, "faces": f,
                  "colors": _rgba(len(v), [0.30, 0.45, 0.85, 0.5]),
                  "opacity": 0.5, "layer": "shafts"})
    # кровля пласта: сетка с цветом по отметке
    nx, ny = 25, 20
    xs = np.linspace(X0 - 60.0, X0 + 180.0, nx)
    ys = np.linspace(Y0 - 60.0, Y0 + 130.0, ny)
    gx, gy = np.meshgrid(xs, ys)
    gz = -285.0 + 6.0 * np.sin((gx - X0) / 40.0) * np.cos((gy - Y0) / 55.0)
    verts = np.column_stack([gx.ravel(), gy.ravel(), gz.ravel()])
    faces = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            a = j * nx + i
            faces += [[a, a + 1, a + nx + 1], [a, a + nx + 1, a + nx]]
    t = (verts[:, 2] - verts[:, 2].min()) / np.ptp(verts[:, 2])
    cols = np.column_stack([0.2 + 0.7 * t, 0.7 - 0.4 * t, 0.9 - 0.7 * t,
                            np.full(len(t), 0.85)])
    parts.append({"name": "Кровля пласта", "verts": verts,
                  "faces": np.asarray(faces, dtype=np.int64),
                  "colors": cols, "opacity": 0.85, "layer": "roof"})
    # координатный короб: рёбра, без граней
    parts.append(_box())
    return parts


def points_parts():
    """Демо с пробами и бороздами: пакет формата 2.

    Штрек, точки проб по борту кругами с размером в пикселях,
    реперы, устья, точки разлома и пикеты плоскими значками в метрах
    (квадрат, ромб, треугольник, крест), борозды линиями. Собраны
    тем же `vector_export_parts`, что и в окне.
    """
    parts = [p for p in demo_parts() if p["name"] == "Штрек"]
    names = {"samples": "Пробы", "marks": "Реперы", "channels": "Борозды"}
    vpoints = [(X0 + 10.0 * i, Y0 + 1.5, -299.0 - 0.02 * i,
                ["#d73027", "#fc8d59", "#91bfdb", "#4575b4"][i % 4],
                "samples", 6.0 + i % 3 * 3.0, "") for i in range(12)]
    vpoints += [(X0 + 120.0, Y0 + 30.0 * k, -296.0, "#1a9850", "marks",
                 7.0, "") for k in range(4)]
    # остальные плоские значки окна: ромб, треугольник, крест
    flat = {"holes": ("Устья скважин", "diamond", 4.0, "#542788"),
            "faults": ("Точки разлома", "triangle", 2.5, "#b35806"),
            "survey": ("Пикеты", "cross", 2.0, "#252525")}
    for k, (lid, (title, _shape, _size, col)) in enumerate(flat.items()):
        names[lid] = title
        vpoints += [(X0 + 15.0 * j, Y0 + 40.0 + 20.0 * k, -290.0 - k,
                     col, lid, 7.0, "") for j in range(3)]
    vlines = [([(X0 + 20.0 * k, Y0 - 2.5, -300.5),
                (X0 + 20.0 * k, Y0 - 2.5, -298.0),
                (X0 + 20.0 * k + 1.0, Y0 - 2.5, -297.5)],
               "#7b3294", "б%d" % k, "channels") for k in range(5)]
    shapes = {"marks": ("square", 3.0)}
    shapes.update({lid: (s, size) for lid, (_t, s, size, _c)
                   in flat.items()})
    parts += vector_export_parts(vpoints, vlines, names, shapes)
    parts.append(_box())
    return parts


def _box():
    """Координатный короб: рёбра, без граней."""
    lo = np.array([X0 - 60.0, Y0 - 60.0, -320.0])
    hi = np.array([X0 + 180.0, Y0 + 130.0, 0.0])
    corners = np.array([[x, y, z] for z in (lo[2], hi[2])
                        for y in (lo[1], hi[1]) for x in (lo[0], hi[0])])
    edges = [[0, 1], [2, 3], [0, 2], [1, 3], [4, 5], [6, 7], [4, 6],
             [5, 7], [0, 4], [1, 5], [2, 6], [3, 7]]
    return {"name": "Координатный короб", "decor": True,
            "verts": corners, "lines": np.asarray(edges),
            "colors": _rgba(8, [0.35, 0.38, 0.45, 1.0])}


FRAME = {"cx": X0 + 60.0, "cy": Y0 + 35.0, "cz": -160.0, "vex": 2.0}


def demo_state():
    cam = {"center": [0.0, 0.0, -150.0], "distance": 650.0,
           "azimuth": -60.0, "elevation": 25.0, "fov": 60.0,
           "ortho": False}
    views = [cam,
             dict(cam, azimuth=30.0, elevation=15.0, distance=420.0),
             dict(cam, center=[60.0, -35.0, -280.0], azimuth=200.0,
                  elevation=5.0, distance=120.0)]
    return {"camera": cam, "fly_views": views, "vex": FRAME["vex"],
            "checked": ["drifts_1", "shafts", "roof"], "opacity": 0.0,
            "axes_on": True}


def _bbox(v):
    v = np.asarray(v, dtype=float)
    return [v.min(axis=0).tolist(), v.max(axis=0).tolist()]


def scene(out):
    _scene(out, "scene_demo", demo_parts(), "Демо: выработки")
    _scene(out, "scene_points", points_parts(), "Демо: пробы и борозды")


def _scene(out, stem, parts, name):
    data = scene_package.pack(parts, demo_state(), name=name,
                              frame=FRAME, crs=CRS, wkt="",
                              version=_version())
    path = os.path.join(out, stem + ".i3dscene")
    with open(path, "wb") as fh:
        fh.write(data)
    meta, glb = scene_package.unpack(data)
    back, extras = scene_package.read_glb(glb)
    exp = {"name": meta["name"], "format": meta["format"], "crs": CRS,
           "origin": meta["origin"],
           "vex": meta["vex"], "camera": meta["camera"],
           "views": meta["views"], "parts": []}
    keys = {"mesh": "faces", "lines": "lines", "points": "points"}
    for part, got in zip([p for p in parts if scene_package._kind(p)],
                         back):
        kind = scene_package._kind(part)
        idx = part[keys[kind]]
        item = {"name": part["name"], "kind": kind,
                "verts": int(len(part["verts"])),
                "elements": int(len(idx)),
                "bbox": _bbox(part["verts"]),
                "max_error": float(np.abs(got["verts"]
                                          - part["verts"]).max()),
                "first_color": [float(x) for x in
                                np.asarray(part["colors"])[0]]}
        if kind == "points":
            item["sizes"] = [float(s) for s in part["sizes"]]
            item["colors"] = np.asarray(part["colors"]).tolist()
            item["shape"] = part.get("shape", "circle")
        if part.get("shape"):
            item["shape"] = part["shape"]
        if kind == "mesh" and not part.get("shape"):
            closed = shell_defects(part["verts"], part["faces"])[0] == 0
            item["closed"] = bool(closed)
            if closed:
                item["volume"] = float(abs(mesh_volume(part["verts"],
                                                       part["faces"])))
        exp["parts"].append(item)
    exp["bbox"] = _bbox(np.vstack([p["verts"] for p in parts]))
    _dump(out, stem + ".expected.json", exp)


def flights(out):
    cams = demo_state()["fly_views"]
    cases = {
        "frame_count": [[s, fps, flight.frame_count(s, fps)]
                        for s, fps in ((0.5, 25), (0.02, 25), (12, 25),
                                       (1.5, 25), (0.1, 25), (2.5, 1),
                                       (3.5, 1), (0.0, 25))],
        "turn": [[a, b, flight.turn(a, b)]
                 for a, b in ((350, 10), (10, 350), (0, 180), (0, 181),
                              (-60, 200), (720, 5))],
        "smoothstep": [[t, flight.smoothstep(t)]
                       for t in (-1, 0, 0.25, 0.5, 0.75, 1, 2)],
        "orbit": [{"cam": cams[0], "degrees": d, "seconds": s,
                   "fps": 25, "frames": flight.orbit(cams[0], d, s, 25)}
                  for d, s in ((360.0, 1.0), (90.0, 0.4), (-45.0, 0.2))],
        "tour": [{"views": cams, "leg": leg, "pause": pause, "fps": 25,
                  "frames": flight.tour(cams, leg, pause, 25)}
                 for leg, pause in ((0.4, 0.2), (0.3, 0.0))]
        + [{"views": cams[:1], "leg": 1.0, "pause": 0.0, "fps": 25,
            "frames": flight.tour(cams[:1], 1.0, 0.0, 25)}],
    }
    _dump(out, "flight.json", cases)


def sweeps(out):
    cases = []
    axes = {
        "straight": [(0, 0, -300), (100, 0, -300)],
        "bend": [(0, 0, 0), (50, 0, 0), (50, 50, 0)],
        "incline": [(0, 0, 0), (100, 0, -20)],
        "shaft": [(10, 10, 0), (10, 10, -400)],
        "repeats": [(0, 0, 0), (0, 0, 0), (10, 0, 0), (10, 0, 0)],
        "sharp": [(0, 0, 0), (10, 0, 0), (0, 1, 0)],
        "curve": [(100 * math.cos(t), 100 * math.sin(t), -200 + 5 * t)
                  for t in np.linspace(0, math.pi, 12)],
    }
    profiles = [("rect", 4.0, 3.0, None, 16), ("arch", 5.0, 2.5, 1.0, 20),
                ("arch", 4.0, 2.0, None, 16), ("circle", 6.0, None, None,
                                               24)]
    for kind, w, h, rise, segs in profiles:
        prof = sweep.profile(kind, w, h, rise, segs)
        for name, axis in axes.items():
            for anchor in ("floor", "centre"):
                v, f, length, turn = sweep.sweep(axis, prof, anchor)
                case = {"profile": [kind, w, h, rise, segs],
                        "axis": [list(map(float, p)) for p in axis],
                        "axis_name": name, "anchor": anchor,
                        "section": prof.tolist(),
                        "area": sweep.section_area(prof),
                        "length": length, "max_turn": turn,
                        "volume": sweep.signed_volume(v, f),
                        "n_verts": int(len(v)), "n_faces": int(len(f))}
                if name in ("bend", "incline") and kind == "arch":
                    case["verts"] = v.tolist()
                    case["faces"] = f.tolist()
                cases.append(case)
    _dump(out, "sweep.json", {"max_turn": sweep.MAX_TURN, "cases": cases})


def _plain(x):
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, (np.floating, np.integer)):
        return x.item()
    return x


def tool_runs(out):
    runs = []
    tool = by_name("sweep_body")
    lines = [
        {"id": 1, "attrs": {"w": 4.0, "h": None, "z": -300.0},
         "parts": [[[0, 0, None], [100, 0, None], [100, 80, None]]]},
        {"id": 2, "attrs": {"w": None, "h": 2.5, "z": None},
         "parts": [[[0, 50, -200.0], [60, 50, -205.0]]]},
        {"id": 3, "attrs": {}, "parts": [[[5, 5, 0.0]]]},
        {"id": 4, "attrs": {"w": "6"}, "parts": [
            [[0, 0, -10.0], [10, 0, -10.0]], [[0, 20, -10.0],
                                               [0, 40, -10.0]]]},
    ]
    for prof in (0, 1, 2):
        for anchor in (0, 1):
            vals = dict(tool.defaults(), PROFILE=prof, ANCHOR=anchor,
                        WIDTH_FIELD="w", HEIGHT_FIELD="h",
                        ELEV_FIELD="z", ELEV=-50.0)
            feed = [{"id": ln["id"], "attrs": ln["attrs"],
                     "parts": [np.array([[np.nan if c is None else c
                                          for c in p] for p in part],
                                        dtype=float)
                               for part in ln["parts"]]}
                    for ln in lines]
            rep = toolspec.Report()
            res = tool.run(dict(vals, INPUT=feed), rep)["OUTPUT"]
            runs.append({
                "tool": tool.name, "values": vals, "input": lines,
                "output": {"fields": res.fields,
                           "features": [{"source": g["source"],
                                         "n_verts": len(g["verts"]),
                                         "n_faces": len(g["faces"]),
                                         "values": [_plain(x)
                                                    for x in row]}
                                        for g, row in res.features]},
                "report": rep.lines})
    tool = by_name("fill_to_volume")
    prof = sweep.profile("rect", 10.0, 10.0)
    v, f, _l, _t = sweep.sweep([(0, 5, -100), (10, 5, -100)], prof)
    for mode, unit, target in ((0, 0, 25.0), (1, 0, 40.0), (0, 1, 300.0),
                               (0, 1, 5000.0)):
        vals = dict(tool.defaults(), MODE=mode, UNIT=unit, TARGET=target)
        rep = toolspec.Report()
        res = tool.run(dict(vals, SHELL={"verts": v, "faces": f}),
                       rep)["OUTPUT"]
        runs.append({
            "tool": tool.name, "values": vals,
            "input": {"verts": v.tolist(), "faces": f.tolist()},
            "output": {"fields": res.fields,
                       "features": [{"values": [_plain(x) for x in row]}
                                    for _g, row in res.features]},
            "report": rep.lines,
            "tolerance": {"level": 0.05, "volume_rel": 0.02}})
    tool = by_name("boolean_shells")
    prof = sweep.profile("rect", 10.0, 10.0)
    va, fa, _l, _t = sweep.sweep([(0, 5, 0), (10, 5, 0)], prof)
    vb, fb, _l, _t = sweep.sweep([(5, 7, 2), (15, 7, 2)], prof)
    for op in (0, 1, 2):
        vals = dict(tool.defaults(), OP=op, CELL=0.5)
        rep = toolspec.Report()
        res = tool.run(dict(vals, SHELL_A={"verts": va, "faces": fa},
                            SHELL_B={"verts": vb, "faces": fb}),
                       rep)["OUTPUT"]
        runs.append({
            "tool": tool.name, "values": vals,
            "input": {"SHELL_A": {"verts": va.tolist(),
                                  "faces": fa.tolist()},
                      "SHELL_B": {"verts": vb.tolist(),
                                  "faces": fb.tolist()}},
            "output": {"fields": res.fields,
                       "features": [{"n_verts": len(g["verts"]),
                                     "n_faces": len(g["faces"]),
                                     "values": [_plain(x) for x in row]}
                                    for g, row in res.features]},
            "report": rep.lines})
    tool = by_name("select_by_shell")
    feats = [
        {"id": 1, "attrs": {"vol": 8.0, "g": 2.0}, "parts": [[[5, 5, 5]]]},
        {"id": 2, "attrs": {"vol": 8.0, "g": 9.0},
         "parts": [[[20, 5, 5]]]},
        {"id": 3, "attrs": {"vol": None},
         "parts": [[[-5, 5, 5], [15, 5, 5]]]},
        {"id": 4, "attrs": {"vol": 4.0, "g": 5.0},
         "parts": [[[2, 2, 2], [8, 8, 8]]]},
        {"id": 5, "attrs": {"vol": 1.0}, "parts": [[[5, 5, None]]]},
    ]
    feed = [dict(it, parts=[np.array([[np.nan if c is None else c
                                       for c in p] for p in part],
                                     dtype=float)
                            for part in it["parts"]]) for it in feats]
    for mode in (0, 1, 2):
        for step in (0.0, 1.0):
            vals = dict(tool.defaults(), MODE=mode, STEP=step,
                        VOLUME="vol", GRADE="g", DENSITY=2.5)
            rep = toolspec.Report()
            # оболочка - куб 0..10 м по всем осям, первое тело 2.11
            res = tool.run(dict(vals, INPUT=feed,
                                SHELL={"verts": va, "faces": fa}),
                           rep)["OUTPUT"]
            runs.append({
                "tool": tool.name, "values": vals,
                "input": {"INPUT": feats,
                          "SHELL": {"verts": va.tolist(),
                                    "faces": fa.tolist()}},
                "output": {"fields": res.fields,
                           "geometry": res.geometry,
                           "features": [{"source": g["source"]}
                                        for g, _row in res.features]},
                "report": rep.lines})
    runs += _zonal_runs()
    runs += _desurvey_runs()
    _dump(out, "tool_runs.json", {"runs": runs})


def _desurvey_runs():
    """2.17: устья таблицей и точками, инклинометрия, три соглашения."""
    tool = by_name("desurvey_holes")
    collars = [
        {"id": 1, "xyz": None, "attrs": {"hole": " H1", "x": 100.0,
                                         "y": 200.0, "z": 50.0,
                                         "eoh": 120.0}},
        {"id": 2, "xyz": None, "attrs": {"hole": "H2", "x": 150.0,
                                         "y": 200.0, "z": 48.0,
                                         "eoh": 80.0}},
        {"id": 3, "xyz": None, "attrs": {"hole": "H3", "x": 1.0, "y": 1.0,
                                         "z": 0.0, "eoh": None}},
    ]
    survey = [
        {"id": 10, "xyz": None, "attrs": {"hole": "H1", "depth": 0.0,
                                          "azimuth": 45.0, "dip": -60.0}},
        {"id": 11, "xyz": None, "attrs": {"hole": "H1", "depth": 60.0,
                                          "azimuth": 50.0, "dip": -55.0}},
        {"id": 12, "xyz": None, "attrs": {"hole": "LOST", "depth": 0.0,
                                          "azimuth": 0.0, "dip": -90.0}},
    ]
    meta = {"@COLLARS": {"name": "collars", "geometry": "none",
                         "hasz": False,
                         "fields": ["hole", "x", "y", "z", "eoh"]},
            "@SURVEY": {"name": "survey", "geometry": "none",
                        "hasz": False,
                        "fields": ["hole", "depth", "azimuth", "dip"]}}
    runs = []
    for conv in (0, 1, 2):
        vals = dict(tool.defaults(), CONVENTION=conv, STEP=5.0)
        rep = toolspec.Report()
        res = tool.run(dict(vals, COLLARS=collars, SURVEY=survey, **meta),
                       rep)["OUTPUT"]
        runs.append({
            "tool": tool.name, "values": dict(vals, **meta),
            "input": {"COLLARS": collars, "SURVEY": survey},
            "output": {"fields": res.fields, "geometry": res.geometry,
                       "features": [{"points": g["points"].tolist(),
                                     "values": [_plain(x) for x in row]}
                                    for g, row in res.features]},
            "report": rep.lines})
    return runs


def _zonal_runs():
    """2.14: тела A (0..10 м), B (20..30 м) и открытое C, точки и линии.

    Строки результата - словари {поле: значение}: поле с именем поля
    тела пишется в него, остальные добавляются (Result.replace).
    """
    tool = by_name("zonal_shell_stats")
    prof = sweep.profile("rect", 10.0, 10.0)
    shells = []
    for i, (nm, x0) in enumerate((("A", 0.0), ("B", 20.0), ("C", 40.0))):
        v, f, _l, _t = sweep.sweep([(x0, 5, 0), (x0 + 10, 5, 0)], prof)
        if nm == "C":
            f = f[:-2]
        shells.append({"id": 11 + i, "attrs": {"name": nm, "old_n": 7},
                       "verts": v, "faces": f})
    pts = [((5, 5, 5), 2.0), ((6, 6, 6), 4.0), ((3, 7, 2), None),
           ((25, 5, 5), 10.0), ((60, 0, 0), 1.0)]
    points = [{"id": i + 1, "attrs": {"au": a},
               "parts": [np.array([xyz], dtype=float)]}
              for i, (xyz, a) in enumerate(pts)]
    lines = [{"id": 1, "attrs": {"au": 3.0},
              "parts": [np.array([(-5, 5, 5), (15, 5, 5.0)])]},
             {"id": 2, "attrs": {"au": 6.0},
              "parts": [np.array([(22, 2, 2), (28, 8, 8), (35, 8, 8.0)])]}]
    cases = [
        (points, "point", "Пробы Au",
         dict(ATTR="au", STATS=[0, 1, 4, 6], ZONE_FIELD="name",
              OUTPUT_OBJECTS=True)),
        (lines, "line", "Борозды",
         dict(ATTR="au", STATS=[0, 1, 5], OUTPUT_OBJECTS=True)),
        (points, "point", "Пробы Au",
         dict(NAME="old", OVERWRITE=True, ATTR="au")),
    ]
    runs = []
    for feats, geom, title, kw in cases:
        vals = dict(tool.defaults(), **kw)
        meta = {"@SHELLS": {"name": "Тела", "geometry": "polygon",
                            "fields": ["name", "old_n"]},
                "@INPUT": {"name": title, "geometry": geom,
                           "fields": ["au"]}}
        rep = toolspec.Report()
        res = tool.run(dict(vals, SHELLS=shells, INPUT=feats, **meta), rep)
        outs = {}
        for key, r in res.items():
            outs[key] = {"fields": r.fields, "replace": r.replace,
                         "geometry": r.geometry,
                         "features": [{"source": g["source"],
                                       "values": {k: _plain(x)
                                                  for k, x in row.items()}
                                       if isinstance(row, dict)
                                       else [_plain(x) for x in row]}
                                      for g, row in r.features]}
        runs.append({
            "tool": tool.name, "values": dict(vals, **meta),
            "input": {"SHELLS": [{"id": s["id"], "attrs": s["attrs"],
                                  "verts": s["verts"].tolist(),
                                  "faces": s["faces"].tolist()}
                                 for s in shells],
                      "INPUT": [{"id": it["id"], "attrs": it["attrs"],
                                 "parts": [p.tolist()
                                           for p in it["parts"]]}
                                for it in feats]},
            "output": outs, "report": rep.lines})
    return runs


def tools_json(out):
    import export_tools
    _dump(out, "tools.json", export_tools.build())


def _dump(out, name, data):
    with open(os.path.join(out, name), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1,
                  default=_plain)
        fh.write("\n")


def main(argv):
    out = argv[1] if len(argv) > 1 else os.path.join(ROOT, "fixtures")
    os.makedirs(out, exist_ok=True)
    scene(out)
    flights(out)
    sweeps(out)
    tool_runs(out)
    tools_json(out)
    for name in sorted(os.listdir(out)):
        sys.stderr.write("%-28s %8d\n" % (name, os.path.getsize(
            os.path.join(out, name))))


if __name__ == "__main__":
    main(sys.argv)
