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


def _cell_index(shape):
    """Номера ячеек по трём осям, вытянутые в один ряд.

    Координаты узла восстанавливаются по номеру ячейки и биту вершины,
    поэтому держать восемь массивов точек на весь куб не нужно: на кубе
    сто на сто на шестьдесят это сто сорок семь мегабайт против
    восемнадцати.
    """
    nz, ny, nx = shape
    ki, ji, ii = np.indices((nz - 1, ny - 1, nx - 1))
    return ki.ravel(), ji.ravel(), ii.ravel()


def _corner_pts(bit, at, idx, xs, ys, zs):
    """Координаты вершины `bit` у ячеек с номерами `at`."""
    ki, ji, ii = idx
    i = 1 if (bit & 1) else 0
    j = 1 if (bit & 2) else 0
    k = 1 if (bit & 4) else 0
    return np.stack([xs[ii[at] + i], ys[ji[at] + j],
                     zs[ki[at] + k]], axis=1)


def _corner_vals(vol, bit):
    """Значения в вершине `bit` у всех ячеек, срезом без копии."""
    nz, ny, nx = vol.shape
    i = 1 if (bit & 1) else 0
    j = 1 if (bit & 2) else 0
    k = 1 if (bit & 4) else 0
    return vol[k:nz - 1 + k, j:ny - 1 + j, i:nx - 1 + i]


def weld(verts, faces, snap=1e-6):
    """Склейка совпадающих вершин.

    Марш выдаёт три вершины на грань, без единого общего ребра: на кубе
    это втрое больше памяти и втрое больше работы у сцены. Склейка идёт
    по округлению, потому что соседние ячейки дают ту же точку с разницей
    в последнем разряде.

    Ключ упаковывается в одно целое, и сортировка идёт по нему, а не по
    тройке: на шестистах тысячах вершин это в четыре с половиной раза
    быстрее. Чтобы упаковка влезла в разрядность, шаг округления при
    большом охвате огрубляется, но остаётся много мельче любой
    геологической точности: на площадке в километр это доли миллиметра.
    """
    verts = np.asarray(verts, dtype=float)
    faces = np.asarray(faces)
    if not len(verts):
        return verts, faces
    lo = verts.min(axis=0)
    span = float(np.max(verts.max(axis=0) - lo))
    step = max(float(snap), span / 1.5e6 if span > 0 else float(snap))
    k = np.round((verts - lo) / step).astype(np.int64)
    size = [int(v) + 1 for v in k.max(axis=0)]
    if size[0] * size[1] * size[2] < 2 ** 62:
        lin = (k[:, 0] * size[1] + k[:, 1]) * size[2] + k[:, 2]
        _u, first, inv = np.unique(lin, return_index=True,
                                   return_inverse=True)
    else:
        _u, first, inv = np.unique(k, axis=0, return_index=True,
                                   return_inverse=True)
    return verts[first], inv.reshape(-1)[faces]


def isosurface_levels(vol, levels, gt, z0=0.0, dz=1.0, weld_verts=True):
    """Оболочки сразу по нескольким отсечкам, одним проходом по кубу.

    Координаты узлов и разбиение ячейки на тетраэдры от отсечки
    не зависят, поэтому общая работа делается один раз, а по уровням
    идёт только сравнение и врезка.

    Возвращает список (отсечка, вершины, треугольники) в порядке
    заданных уровней.
    """
    vol = np.asarray(vol, dtype=float)
    levels = [float(x) for x in levels]
    if not levels or vol.ndim != 3 or min(vol.shape) < 2:
        return []
    xs, ys, zs = _corner_coords(vol.shape, gt, z0, dz)
    idx = _cell_index(vol.shape)
    good = np.isfinite(vol)
    cvals = [_corner_vals(vol, b) for b in range(8)]
    cgood = [_corner_vals(good, b) for b in range(8)]

    out = []
    for level in levels:
        vals = [np.where(g, v, level - 1.0).ravel()
                for v, g in zip(cvals, cgood)]
        ins = [v >= level for v in vals]
        verts, faces = [], []
        for tet in _TETRA:
            code = (ins[tet[0]].astype(np.uint8)
                    | (ins[tet[1]].astype(np.uint8) << 1)
                    | (ins[tet[2]].astype(np.uint8) << 2)
                    | (ins[tet[3]].astype(np.uint8) << 3))
            # Ячейки целиком внутри и целиком снаружи граней не дают,
            # а их подавляющее большинство. Отбираем пограничные один
            # раз, дальше работаем только по ним: перебор четырнадцати
            # случаев по всему кубу стоил больше самой врезки.
            active = np.flatnonzero((code != 0) & (code != 15))
            if not len(active):
                continue
            act_code = code[active]
            for case, tris in _CASES.items():
                if not tris:
                    continue
                at = active[act_code == case]
                if not len(at):
                    continue
                pts = {c: _corner_pts(tet[c], at, idx, xs, ys, zs)
                       for c in range(4)}
                cut = {}
                for e, (a, b) in enumerate(_EDGES):
                    va = vals[tet[a]][at]
                    vb = vals[tet[b]][at]
                    den = np.where(np.abs(vb - va) < 1e-12, 1.0, vb - va)
                    w = np.clip((level - va) / den, 0.0, 1.0)[:, None]
                    cut[e] = pts[a] * (1.0 - w) + pts[b] * w
                # Наружу треугольник разворачивается по данным, а не
                # по таблице: направление от середины внутренних вершин
                # к середине наружных. Иначе часть граней смотрит
                # внутрь, и объём по такой оболочке считается неверно.
                ins_i = [i for i in range(4) if (case >> i) & 1]
                out_i = [i for i in range(4) if not (case >> i) & 1]
                c_in = sum(pts[i] for i in ins_i) / float(len(ins_i))
                c_out = sum(pts[i] for i in out_i) / float(len(out_i))
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
                    ar = np.arange(n)
                    faces.append(np.stack([base + ar, base + n + ar,
                                           base + 2 * n + ar], axis=1))
        if not faces:
            out.append((level, np.zeros((0, 3)),
                        np.zeros((0, 3), dtype=np.int64)))
            continue
        v = np.vstack(verts)
        f = np.vstack(faces).astype(np.int64)
        if weld_verts:
            v, f = weld(v, f)
        out.append((level, v, f.astype(np.int64)))
    return out


def isosurface(vol, level, gt, z0=0.0, dz=1.0, weld=True):
    """Оболочка по отсечке.

    `vol` это куб значений в порядке (уровень, строка, столбец), `level`
    отсечка, `gt` геопривязка слоя, `z0` и `dz` отметка первого уровня
    и шаг по вертикали.

    Возвращает (вершины, треугольники). Пропуски в данных считаются
    находящимися снаружи тела: пустота не должна притягивать оболочку.
    """
    got = isosurface_levels(vol, [level], gt, z0, dz, weld_verts=weld)
    if not got:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    return got[0][1], got[0][2]


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
