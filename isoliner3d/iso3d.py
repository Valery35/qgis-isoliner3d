# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Изоповерхность по кубу значений.

Куб приходит многоканальным гридом: канал это горизонтальный уровень.
Оболочка строится по отсечке: всё, что выше заданного значения, попадает
внутрь тела.

Взят марш по тетраэдрам, а не по кубам. Причина в надёжности: у кубов
шестнадцать неоднозначных случаев из двухсот пятидесяти шести, и на них
соседние ячейки могут разойтись, оставив дыру в оболочке. Тетраэдр
делится однозначно, поэтому оболочка выходит замкнутой по построению,
а замкнутость нам нужна: по ней считается объём и по ней строится срез.

Ценой идёт вдвое больше треугольников. Для наших размеров это дешевле,
чем ловить дыры.
"""

import numpy as np

# Шесть тетраэдров, на которые делится ячейка. Вершины нумеруются битами
# по осям: бит 0 это X, бит 1 это Y, бит 2 это Z.
#
# Все шесть делят главную диагональ 0-7. Это обязательно: при разбиении
# по другой диагонали соседние ячейки не сходятся гранями, и оболочка
# получается дырявой.
_TETRA = ((0, 1, 3, 7), (0, 3, 2, 7), (0, 2, 6, 7),
          (0, 6, 4, 7), (0, 4, 5, 7), (0, 5, 1, 7))

# Рёбра тетраэдра парами вершин
_EDGES = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))

# Какие рёбра пересечены при данном наборе вершин внутри тела.
# Ключ это четыре бита, значение это набор треугольников из номеров рёбер.
_CASES = {
    0x0: (), 0xF: (),
    0x1: ((0, 1, 2),), 0xE: ((0, 2, 1),),
    0x2: ((0, 4, 3),), 0xD: ((0, 3, 4),),
    0x4: ((1, 3, 5),), 0xB: ((1, 5, 3),),
    0x8: ((2, 5, 4),), 0x7: ((2, 4, 5),),
    0x3: ((1, 2, 4), (1, 4, 3)), 0xC: ((1, 4, 2), (1, 3, 4)),
    0x5: ((0, 2, 5), (0, 5, 3)), 0xA: ((0, 5, 2), (0, 3, 5)),
    0x9: ((0, 1, 5), (0, 5, 4)), 0x6: ((0, 5, 1), (0, 4, 5)),
}


def _corner_coords(shape, gt, z0, dz):
    """Координаты узлов куба по осям X, Y, Z."""
    nz, ny, nx = shape
    xs = gt[0] + (np.arange(nx) + 0.5) * gt[1]
    ys = gt[3] + (np.arange(ny) + 0.5) * gt[5]
    zs = z0 + np.arange(nz) * dz
    return xs, ys, zs


def isosurface(vol, level, gt, z0=0.0, dz=1.0):
    """Оболочка по отсечке.

    `vol` это куб значений в порядке (уровень, строка, столбец), `level`
    отсечка, `gt` геопривязка слоя, `z0` и `dz` отметка первого уровня
    и шаг по вертикали.

    Возвращает (вершины, треугольники). Пропуски в данных считаются
    находящимися снаружи тела: пустота не должна притягивать оболочку.
    """
    vol = np.asarray(vol, dtype=float)
    if vol.ndim != 3 or min(vol.shape) < 2:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    nz, ny, nx = vol.shape
    xs, ys, zs = _corner_coords(vol.shape, gt, z0, dz)

    val = np.where(np.isfinite(vol), vol, level - 1.0)
    inside = val >= level

    # значения и координаты в восьми узлах каждой ячейки
    def corner(bit):
        i = 1 if (bit & 1) else 0
        j = 1 if (bit & 2) else 0
        k = 1 if (bit & 4) else 0
        v = val[k:nz - 1 + k, j:ny - 1 + j, i:nx - 1 + i]
        ins = inside[k:nz - 1 + k, j:ny - 1 + j, i:nx - 1 + i]
        X, Y, Z = np.meshgrid(xs[i:nx - 1 + i], ys[j:ny - 1 + j],
                              zs[k:nz - 1 + k], indexing="ij")
        pts = np.stack([X.transpose(2, 1, 0), Y.transpose(2, 1, 0),
                        Z.transpose(2, 1, 0)], axis=-1)
        return v, ins, pts

    cor = [corner(b) for b in range(8)]

    verts, faces = [], []
    for tet in _TETRA:
        vals = [cor[c][0] for c in tet]
        ins = [cor[c][1] for c in tet]
        pts = [cor[c][2] for c in tet]
        code = (ins[0].astype(np.uint8)
                | (ins[1].astype(np.uint8) << 1)
                | (ins[2].astype(np.uint8) << 2)
                | (ins[3].astype(np.uint8) << 3))
        for case, tris in _CASES.items():
            if not tris:
                continue
            sel = code == case
            if not sel.any():
                continue
            # точки пересечения на рёбрах тетраэдра
            cut = {}
            for e, (a, b) in enumerate(_EDGES):
                va, vb = vals[a][sel], vals[b][sel]
                den = np.where(np.abs(vb - va) < 1e-12, 1.0, vb - va)
                w = np.clip((level - va) / den, 0.0, 1.0)[:, None]
                cut[e] = pts[a][sel] * (1.0 - w) + pts[b][sel] * w
            # Наружу треугольник разворачивается по данным, а не
            # по таблице: направление от середины внутренних вершин
            # к середине наружных. Иначе часть граней смотрит внутрь,
            # и объём по такой оболочке считается неверно.
            ins_idx = [i for i in range(4) if (case >> i) & 1]
            out_idx = [i for i in range(4) if not (case >> i) & 1]
            c_in = sum(pts[i][sel] for i in ins_idx) / float(len(ins_idx))
            c_out = sum(pts[i][sel] for i in out_idx) / float(len(out_idx))
            outward = c_out - c_in
            for tri in tris:
                base = sum(len(x) for x in verts)
                a, b, c = cut[tri[0]], cut[tri[1]], cut[tri[2]]
                nrm = np.cross(b - a, c - a)
                flip = np.einsum('ij,ij->i', nrm, outward) < 0
                b2 = np.where(flip[:, None], c, b)
                c2 = np.where(flip[:, None], b, c)
                n = len(a)
                verts.extend([a, b2, c2])
                idx = np.arange(n)
                faces.append(np.stack([base + idx,
                                       base + n + idx,
                                       base + 2 * n + idx], axis=1))
    if not faces:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    return np.vstack(verts), np.vstack(faces).astype(np.int64)


def is_watertight(verts, faces, snap=1e-6):
    """Замкнута ли оболочка: каждое ребро входит ровно в две грани.

    Вершины склеиваются по округлению: марш даёт совпадающие точки
    из соседних ячеек, и без склейки любое ребро выглядит висячим.
    """
    import collections
    if not len(faces):
        return False
    key = np.round(np.asarray(verts, dtype=float) / snap).astype(np.int64)
    uniq, inv = np.unique(key, axis=0, return_inverse=True)
    edges = collections.Counter()
    for tri in np.asarray(faces):
        a, b, c = inv[tri[0]], inv[tri[1]], inv[tri[2]]
        for x, y in ((a, b), (b, c), (c, a)):
            if x == y:
                continue
            edges[(x, y) if x < y else (y, x)] += 1
    return all(n == 2 for n in edges.values())
