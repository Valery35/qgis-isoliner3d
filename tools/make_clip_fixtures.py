#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Образец обрезки сцены для приложений на Rust: clip.json.

Обрезка окна режет пересечённые грани средствами QGIS (пересечение
с контуром, разбиение на треугольники, крышка на срезе), поэтому
образец собирается в QGIS без окна, НАСТОЯЩИМИ методами окна:
_clip_tris, _cap_cut и их помощники вызываются на заглушке, у которой
из всего окна есть только настройки обрезки. Копии алгоритма здесь
нет, расходиться с окном нечему.

Запуск (из корня хранилища):

    python-qgis.bat tools/make_clip_fixtures.py <папка>

Части - демо-сцена make_fixtures.demo_parts (тот же scene_demo).
Тела (замкнутые) идут путём окна для тел: резка, сшивка, крышка.
Кровля пласта - путём поясов: только резка граней, без крышки.
Короб в обрезку не идёт. Плюс шкалы вида по разрезу
axes.section_scales на линии коридора.
"""

import json
import os
import sys

import numpy as np

from qgis.core import QgsApplication

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

app = QgsApplication([], False)
app.initQgis()

import make_fixtures as mf  # noqa: E402
from isoliner3d import viewer_dialog as vd  # noqa: E402
from isoliner3d.axes import section_scales  # noqa: E402
from isoliner3d.cleanup import mesh_volume, shell_defects  # noqa: E402
from isoliner3d.iso3d import weld  # noqa: E402

X0, Y0 = mf.X0, mf.Y0


class _Value(object):
    def __init__(self, v):
        self.v = v

    def value(self):
        return self.v

    def currentData(self):
        return self.v


# Заглушка окна: все методы класса ViewerDialog, а состояние -
# только то, что читает обрезка. Счётчики отчёта заводятся нулём
# при первом обращении.
_Base = type("_Base", (object,), {
    k: v for k, v in vd.ViewerDialog.__dict__.items()
    if callable(v) and not k.startswith("__")})


class Window(_Base):
    def __init__(self, rings=(), lines=(), side="in", width=0.0,
                 zlo=None, zhi=None):
        self._clip_now = ([list(r) for r in rings],
                          [list(ln) for ln in lines])
        self._clip_geom_now = None
        self.clip_side = _Value(side)
        self.clip_width = _Value(float(width))
        self.zlo = _Value(-1e7 if zlo is None else float(zlo))
        self.zhi = _Value(-1e7 if zhi is None else float(zhi))
        self.zs_top = _Value(None)
        self.zs_bot = _Value(None)
        self.mask_lyr = _Value(None)
        self._mask_cache = {}
        self._z_surf_now = ((None, None), (None, None))
        self._cap_why = {}
        self._clip_dmin = float("inf")
        self._clip_dmax = 0.0
        self.warnings = []

    def __getattr__(self, name):
        if name.startswith("_cap_") or name.startswith("_clip_") or \
                name.startswith("_body_"):
            setattr(self, name, 0)
            return 0
        raise AttributeError(name)

    def _warn(self, text):
        self.warnings.append(text)


def body(win, v, f):
    """Путь окна для тела: резка в плане, сшивка, крышка на срезе,
    затем резка плоскостями отметок с горизонтальной крышкой."""
    v, f = win._clip_tris(v, f)
    if len(f):
        v, f = weld(v, f)
    cv, cf = win._cap_cut(v, f)
    if len(cf):
        f = np.vstack([f, cf + len(v)])
        v = np.vstack([v, cv])
    if len(f):
        v, f = win._z_cut_mesh(v, f, cap=True)
    return v, f


def belt(win, v, f):
    """Путь окна для поясов и поверхностей: только резка граней."""
    v, f = win._clip_tris(v, f)
    if len(f):
        v, f = win._z_cut_mesh(v, f, cap=False)
    return v, f


def describe(v, f):
    v = np.asarray(v, dtype=float)
    f = np.asarray(f, dtype=np.int64)
    out = {"verts": int(len(v)), "faces": int(len(f))}
    if not len(f):
        out.update(bbox=None, closed=False)
        return out
    used = v[np.unique(f)]
    out["bbox"] = [used.min(axis=0).tolist(), used.max(axis=0).tolist()]
    wv, wf = weld(v, f)
    closed = shell_defects(wv, wf)[0] == 0
    out["closed"] = bool(closed)
    if closed:
        out["volume"] = float(abs(mesh_volume(wv, wf)))
    return out


RING = [(X0 + 30.0, Y0 - 50.0), (X0 + 90.0, Y0 - 50.0),
        (X0 + 90.0, Y0 + 50.0), (X0 + 30.0, Y0 + 50.0)]
LINE = [(X0 - 10.0, Y0 + 2.0), (X0 + 125.0, Y0 + 2.0),
        (X0 + 125.0, Y0 + 100.0)]
CASES = [
    ("contour_in", dict(rings=[RING], side="in")),
    ("contour_out", dict(rings=[RING], side="out")),
    ("corridor", dict(lines=[LINE], side="corridor", width=6.0)),
    ("left", dict(lines=[LINE], side="left")),
    ("right", dict(lines=[LINE], side="right")),
    ("z_ge", dict(zlo=-301.5)),
    ("z_le", dict(zhi=-301.5)),
    ("z_band", dict(zlo=-303.0, zhi=-299.0)),
]


def main(out):
    parts = [p for p in mf.demo_parts()
             if p.get("faces") is not None and not p.get("decor")]
    cases = []
    for tag, kw in CASES:
        win = Window(**kw)
        got = []
        for p in parts:
            v = np.asarray(p["verts"], dtype=float)
            f = np.asarray(p["faces"], dtype=np.int64)
            is_body = shell_defects(v, f)[0] == 0
            cv, cf = (body if is_body else belt)(win, v, f)
            item = {"name": p["name"], "path": "body" if is_body
                    else "belt"}
            item.update(describe(cv, cf))
            got.append(item)
        spec = {"side": kw.get("side", "in"),
                "rings": [[list(q) for q in r] for r in kw.get("rings", [])],
                "lines": [[list(q) for q in ln]
                          for ln in kw.get("lines", [])],
                "width": kw.get("width", 0.0),
                "zlo": kw.get("zlo"), "zhi": kw.get("zhi")}
        cases.append({"case": tag, "clip": spec, "parts": got,
                      "warnings": win.warnings})
    src = {p["name"]: describe(p["verts"], p["faces"]) for p in parts}
    allv = np.vstack([p["verts"] for p in mf.demo_parts()])
    zlo, zhi = float(allv[:, 2].min()), float(allv[:, 2].max())
    sc = section_scales(LINE[0], LINE[-1], zlo, zhi, want=6,
                        vex=mf.FRAME["vex"])

    def plain(x):
        if isinstance(x, dict):
            return {k: plain(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [plain(v) for v in x]
        if isinstance(x, (np.floating, np.integer)):
            return x.item()
        if isinstance(x, np.ndarray):
            return x.tolist()
        return x
    data = {
        "about": "Обрезка демо-сцены (scene_demo) методами окна модуля "
                 "Isoliner3D. side: in - оставить внутри контура, out - "
                 "убрать внутри, left/right - по сторону линии, corridor "
                 "- полоса ширины width по обе стороны линии. zlo - "
                 "оставить z >= zlo, zhi - оставить z <= zhi. Тело (path "
                 "body): резка, сшивка, крышка на срезе. Пояс (belt): "
                 "только резка граней. Число вершин и граней зависит от "
                 "разбиения GEOS, сверять надёжнее охват, замкнутость "
                 "и объём.",
        "source": src,
        "cases": cases,
        "section": {"a": list(LINE[0]), "b": list(LINE[-1]),
                    "zlo": zlo, "zhi": zhi, "want": 6,
                    "vex": mf.FRAME["vex"], "scales": plain(sc)},
    }
    path = os.path.join(out, "clip.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    print("clip.json", os.path.getsize(path))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
    app.exitQgis()
