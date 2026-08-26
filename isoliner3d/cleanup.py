# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Чистка поверхности: сглаживание и отброс мелочи.

Маршевая поверхность идёт ступенями по ячейкам куба, и мелкие обрывки
на ней шумят. Изолинии по уровням с последующей сшивкой дают то же
самое, но добавляют неоднозначность: когда на одном уровне одно кольцо,
а на следующем два, машина не знает, как их соединить.

Здесь то же делается прямо на поверхности. Сглаживание тянет каждую
вершину к середине соседей, отчего ступени садятся. Отброс мелочи
убирает куски мельче заданного числа граней.

Края не двигаются. Крышка на срезе строится по краевым рёбрам, и стоит
их сдвинуть, как она перестанет сходиться с телом.

Считается на голом NumPy, QGIS здесь не нужен.
"""

import collections

import numpy as np


def _edges(faces):
    """Рёбра меша и сколько граней у каждого."""
    cnt = collections.Counter()
    for tri in faces:
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            cnt[(a, b) if a < b else (b, a)] += 1
    return cnt


def _labels(verts, faces):
    """Номер связного куска для каждой грани."""
    n = len(verts)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for tri in faces:
        ra, rb, rc = find(tri[0]), find(tri[1]), find(tri[2])
        parent[rb] = ra
        parent[rc] = ra
    return np.array([find(int(tri[0])) for tri in faces], dtype=np.int64)


def count_parts(verts, faces):
    """Сколько связных кусков в поверхности."""
    if not len(faces):
        return 0
    return int(len(set(_labels(verts, faces).tolist())))


def drop_small(verts, faces, min_faces):
    """Выбросить куски мельче порога.

    Если порог убирает всё, поверхность возвращается как была: пустая
    сцена вместо тела это не чистка, а потеря, и лучше дать человеку
    убавить порог.
    """
    verts = np.asarray(verts, dtype=float)
    faces = np.asarray(faces)
    if not len(faces) or int(min_faces) <= 1:
        return verts, faces
    lab = _labels(verts, faces)
    sizes = collections.Counter(lab.tolist())
    keep = np.array([sizes[int(x)] >= int(min_faces) for x in lab])
    if not keep.any():
        return verts, faces
    return verts, faces[keep]


def smooth(verts, faces, rounds=1, strength=0.5):
    """Сглаживание: вершина тянется к середине соседей.

    `strength` от нуля до единицы задаёт, насколько сильно тянуть
    за один проход. Краевые вершины остаются на месте.

    Сглаживание слегка ужимает тело: каждая вершина идёт внутрь.
    На пяти проходах это доли ячейки, но для подсчёта объёма меш лучше
    брать несглаженным.
    """
    verts = np.asarray(verts, dtype=float).copy()
    faces = np.asarray(faces)
    rounds = int(rounds)
    if not len(faces) or rounds <= 0:
        return verts

    n = len(verts)
    cnt = _edges(faces)
    border = np.zeros(n, dtype=bool)
    ia, ib = [], []
    for (a, b), k in cnt.items():
        ia.append(a)
        ib.append(b)
        if k == 1:
            border[a] = True
            border[b] = True
    ia = np.asarray(ia, dtype=np.int64)
    ib = np.asarray(ib, dtype=np.int64)
    if not len(ia):
        return verts

    w = float(np.clip(strength, 0.0, 1.0))
    for _ in range(rounds):
        acc = np.zeros_like(verts)
        deg = np.zeros(n)
        np.add.at(acc, ia, verts[ib])
        np.add.at(acc, ib, verts[ia])
        np.add.at(deg, ia, 1.0)
        np.add.at(deg, ib, 1.0)
        ok = deg > 0
        mid = np.zeros_like(verts)
        mid[ok] = acc[ok] / deg[ok, None]
        move = ok & ~border
        verts[move] += (mid[move] - verts[move]) * w
    return verts
