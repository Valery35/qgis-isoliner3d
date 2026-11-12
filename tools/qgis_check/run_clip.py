#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Обрезка длинных граней окном: проверка в QGIS без окна.

python-qgis.bat tools/qgis_check/run_clip.py

Штрек из демо - тело вдоль ломаной, его грани тянутся во всю длину
колена выработки. Контур x 30..90 м пересекает первое колено, и ни
одна вершина граней в контур не попадает. Окно обязано резать такие
грани: внутри контура остаётся 60 м штрека, снаружи - остальное,
оба куска замкнуты крышками. Объём сверяется с площадью сечения.
Коридор и отвесные стены ствола проверяются так же.
Выход с кодом 1 и списком расхождений, если что-то не так.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import make_clip_fixtures as mc  # noqa: E402
import numpy as np  # noqa: E402
from isoliner3d import sweep  # noqa: E402
from isoliner3d.cleanup import mesh_volume, shell_defects  # noqa: E402
from isoliner3d.iso3d import weld  # noqa: E402

X0, Y0 = mc.X0, mc.Y0
parts = {p["name"]: p for p in mc.mf.demo_parts()}
drift = parts["Штрек"]
area = sweep.section_area(sweep.profile("arch", 5.0, 3.0, 1.0, 16))
full = abs(mesh_volume(drift["verts"], drift["faces"]))
bad = []


def check(tag, got_v, got_f, want, tol=0.03):
    if not len(got_f):
        bad.append("%s: граней не осталось, ждали %.0f м3" % (tag, want))
        return
    wv, wf = weld(got_v, got_f)
    holes = shell_defects(wv, wf)[0]
    vol = abs(mesh_volume(wv, wf))
    print("%-14s граней %4d, рваных рёбер %d, объём %8.1f, ждали %8.1f"
          % (tag, len(wf), holes, vol, want))
    if holes:
        bad.append("%s: тело не замкнуто, рваных рёбер %d" % (tag, holes))
    if abs(vol - want) > tol * want:
        bad.append("%s: объём %.1f вместо %.1f" % (tag, vol, want))


inside = 60.0 * area
for side, want in (("in", inside), ("out", full - inside)):
    win = mc.Window(rings=[mc.RING], side=side)
    v, f = mc.body(win, drift["verts"], drift["faces"])
    check("контур " + side, v, f, want)

# коридор 6 м по оси первого колена, x от -10 до 50. Буфер QGIS
# кончается полукругом радиуса 6 м, и за x = 50 в коридор попадает
# ещё sqrt(36 - y^2) штрека, в среднем по ширине 5 м около 5.7 м.
line = [(X0 - 10.0, Y0), (X0 + 50.0, Y0)]
win = mc.Window(lines=[line], side="corridor", width=6.0)
v, f = mc.body(win, drift["verts"], drift["faces"])
ys = np.linspace(-2.5, 2.5, 201)
check("коридор", v, f, (50.0 + float(np.sqrt(36.0 - ys ** 2).mean()))
      * area)

# Коридор по ломаной с изломом: граница идёт вдоль второго колена
# и упирается внутренним углом в пол штрека. Кольцо буфера QGIS
# начинается ровно в этом углу, и путь вдоль границы прыгал там
# с конца кольца на начало: крышка теряла кусок, оставалась щель.
win = mc.Window(lines=[mc.LINE], side="corridor", width=6.0)
v, f = mc.body(win, drift["verts"], drift["faces"])
wv, wf = weld(v, f)
holes = shell_defects(wv, wf)[0]
print("%-14s граней %4d, рваных рёбер %d" % ("коридор с углом", len(wf),
                                              holes))
if holes:
    bad.append("коридор с углом: тело не замкнуто, рваных рёбер %d"
               % holes)

# ствол - круг 7 м, отвесные стены: контур режет его почти пополам.
# Граница не по оси: ось проходит точно через вершины окружности.
shaft = parts["Ствол"]
ring = [(X0 - 40.0, Y0 + 20.0), (X0 - 30.3, Y0 + 20.0),
        (X0 - 30.3, Y0 + 40.0), (X0 - 40.0, Y0 + 40.0)]
win = mc.Window(rings=[ring], side="in")
v, f = mc.body(win, shaft["verts"], shaft["faces"])
r = 3.5
h = 0.3                       # сегмент круга за хордой на 0.3 м от оси
seg = r * r * np.arccos(h / r) - h * np.sqrt(r * r - h * h)
check("ствол", v, f, seg * 310.0, tol=0.05)

mc.app.exitQgis()
if bad:
    print("\n".join(["РАСХОЖДЕНИЯ:"] + bad))
    sys.exit(1)
print("обрезка длинных граней: всё сходится")
