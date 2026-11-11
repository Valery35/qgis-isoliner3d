# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Тело вдоль оси: выработка, тоннель, канава (2.24).

Сечение - круг, прямоугольник или прямоугольник со сводом - ставится
поперёк оси в каждой её вершине и протягивается по ней, торцы
закрываются. Выходит замкнутое тело, которое берут 2.11, 2.12, 2.14
и 2.23: объём штрека, пробы внутри камеры, заполнение водой.

Поперечная ось сечения всегда горизонтальна: у наклонной выработки
стенки остаются вертикальными в поперечнике, как у настоящего
уклона. Сечение перпендикулярно оси. У вертикальной оси (ствол)
поперечная ось берётся по X.

На изломе оси сечение ставится по биссектрисе, а его ширина
по излому растягивается на 1/cos половины угла поворота: иначе стенка
на повороте сужалась бы. Излом круче MAX_TURN градусов даёт
самопересечение тела и возвращается как предупреждение.

Сечение задаётся в координатах (u, v): u поперёк оси, вправо по ходу,
v вверх. Ось идёт по центру сечения или по почве - по низу сечения,
как обычно снимают выработки маркшейдеры.

Модуль Qt и QGIS не знает.
"""

import math

import numpy as np

PROFILES = ("circle", "rect", "arch")
MAX_TURN = 100.0   # градусов на одном изломе оси


def profile(kind, width, height=None, rise=None, segments=16):
    """Контур сечения (n, 2) против часовой стрелки, низ на v = 0.

    circle - круг диаметра width. rect - прямоугольник width x height.
    arch - прямоугольник со сводом: стенки height, над ними сегмент
    круга подъёмом rise (0 - пол-ширины, полуциркульный свод).
    """
    w = float(width)
    if w <= 0:
        raise ValueError("width must be positive")
    n = max(int(segments), 6)
    if kind == "circle":
        r = w / 2.0
        a = -math.pi / 2 + 2 * math.pi * np.arange(n) / n
        return np.column_stack([r * np.cos(a), r + r * np.sin(a)])
    h = float(height if height is not None else w)
    if h <= 0:
        raise ValueError("height must be positive")
    if kind == "rect":
        return np.array([[-w / 2, 0.0], [w / 2, 0.0], [w / 2, h],
                         [-w / 2, h]])
    if kind == "arch":
        f = float(rise) if rise else w / 2.0
        f = min(max(f, 1e-6 * w), w / 2.0)
        rad = (w * w / 4.0 + f * f) / (2.0 * f)
        cy = h + f - rad
        a0 = math.atan2(h - cy, w / 2.0)
        a1 = math.pi - a0
        k = max(n // 2, 3)
        ang = a0 + (a1 - a0) * np.arange(1, k) / k
        arc = np.column_stack([rad * np.cos(ang), cy + rad * np.sin(ang)])
        return np.vstack([[[-w / 2, 0.0], [w / 2, 0.0], [w / 2, h]], arc,
                          [[-w / 2, h]]])
    raise ValueError("unknown profile %r" % (kind,))


def section_area(prof):
    """Площадь сечения по формуле шнурования."""
    p = np.asarray(prof, dtype=float)
    x, y = p[:, 0], p[:, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1))
                           - np.dot(y, np.roll(x, -1))))


def _unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def _clean_axis(pts):
    """Ось без повторных вершин подряд."""
    p = np.asarray(pts, dtype=float)
    if len(p) < 2:
        return p
    keep = [0]
    for i in range(1, len(p)):
        if np.linalg.norm(p[i] - p[keep[-1]]) > 1e-9:
            keep.append(i)
    return p[keep]


def frames(axis):
    """Точки и рамки сечений по оси: (точки, u, v, растяжение, излом).

    u - горизонтальная поперечная ось, v - верх сечения, растяжение -
    множитель ширины на изломе, излом - угол поворота в вершине, °.
    """
    p = _clean_axis(axis)
    if len(p) < 2:
        raise ValueError("axis needs two distinct points")
    seg = np.diff(p, axis=0)
    seg = np.array([_unit(s) for s in seg])
    n = len(p)
    us, vs, stretch, turn = [], [], [], []
    up = np.array([0.0, 0.0, 1.0])
    for i in range(n):
        if i == 0:
            t = seg[0]
            k, ang = 1.0, 0.0
        elif i == n - 1:
            t = seg[-1]
            k, ang = 1.0, 0.0
        else:
            a, b = seg[i - 1], seg[i]
            t = _unit(a + b)
            if np.linalg.norm(t) < 1e-9:     # разворот назад
                t = a
            c = float(np.clip(np.dot(a, b), -1.0, 1.0))
            ang = math.degrees(math.acos(c))
            k = 1.0 / max(math.cos(math.radians(ang) / 2.0), 0.2)
        u = np.cross(t, up)
        if np.linalg.norm(u) < 1e-9:         # вертикальная ось, ствол
            u = np.array([1.0, 0.0, 0.0])
        u = _unit(u)
        v = _unit(np.cross(u, t))
        if v[2] < 0:
            v = -v
            u = -u
        us.append(u)
        vs.append(v)
        stretch.append(k)
        turn.append(ang)
    return p, np.array(us), np.array(vs), np.array(stretch), \
        np.array(turn)


def sweep(axis, prof, anchor="floor"):
    """Замкнутое тело: (вершины, грани, длина оси, наибольший излом).

    anchor floor - ось по почве (низ сечения), centre - по центру.
    """
    prof = np.asarray(prof, dtype=float)
    if anchor == "centre":
        lo, hi = prof[:, 1].min(), prof[:, 1].max()
        prof = prof - [0.0, (lo + hi) / 2.0]
    p, us, vs, stretch, turn = frames(axis)
    m = len(prof)
    rings = []
    for i in range(len(p)):
        rings.append(p[i] + np.outer(prof[:, 0] * stretch[i], us[i])
                     + np.outer(prof[:, 1], vs[i]))
    verts = np.vstack(rings)
    faces = []
    for i in range(len(p) - 1):
        a0, b0 = i * m, (i + 1) * m
        for j in range(m):
            j1 = (j + 1) % m
            faces.append([a0 + j, b0 + j, b0 + j1])
            faces.append([a0 + j, b0 + j1, a0 + j1])
    # торцы веером из центра: сечения выпуклые
    c0 = len(verts)
    c1 = c0 + 1
    verts = np.vstack([verts, rings[0].mean(axis=0),
                       rings[-1].mean(axis=0)])
    last = (len(p) - 1) * m
    for j in range(m):
        j1 = (j + 1) % m
        faces.append([c0, j, j1])
        faces.append([c1, last + j1, last + j])
    faces = np.asarray(faces, dtype=np.int64)
    if signed_volume(verts, faces) < 0:
        faces = faces[:, ::-1].copy()
    length = float(np.sum(np.linalg.norm(np.diff(p, axis=0), axis=1)))
    return verts, faces, length, float(turn.max(initial=0.0))


def signed_volume(verts, faces):
    """Объём замкнутой сетки со знаком: плюс у наружных нормалей."""
    v = np.asarray(verts, dtype=float)
    f = np.asarray(faces, dtype=np.int64)
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)
