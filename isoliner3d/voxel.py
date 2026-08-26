# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Воксельная модель куба: ячейки показываются коробками.

Куб приходит многоканальным гридом, канал это горизонтальный уровень,
тот же порядок (уровень, строка, столбец), что и у изоповерхности.
Ячейка занимает шаг грида по горизонтали и шаг уровней по вертикали,
то есть ровно тот объём, который она и означает в подсчёте.

Строятся не все грани, а только видимые. Грань между двумя занятыми
соседями не видна никогда, поэтому её отбрасывают: заполненный куб
двести на двести на сто это двадцать четыре миллиона граней в лоб
и сто шестьдесят тысяч после отбрасывания.

Соседние грани одного класса сливаются в прямоугольник. Слияние идёт
по классам, а не по значению: у непрерывного содержания одинаковых
соседей не бывает и сливать нечего, поэтому значения раскладывают
по интервалам заранее.

Слияние стоит замкнутости. Длинный прямоугольник упирается в два
коротких, общего ребра у них нет, и оболочка перестаёт быть телом
в смысле подсчёта. Для показа это не важно, для подсчёта объёма
слияние выключается.
"""

import numpy as np

# Направления граней: ось и сторона. Ось 0 это уровень, 1 это строка,
# 2 это столбец.
_DIRS = ((0, -1), (0, 1), (1, -1), (1, 1), (2, -1), (2, 1))


def occupancy(vol, level, below=False):
    """Занятые ячейки: значение не пропуск и прошло отсечку.

    Пропуск занятым не считается: пустота не должна выглядеть телом.
    """
    vol = np.asarray(vol, dtype=float)
    good = np.isfinite(vol)
    if below:
        return good & (vol <= level)
    return good & (vol >= level)


def parse_edges(text):
    """Границы интервалов из строки, как их пишет человек.

    Годятся запятая, точка с запятой и пробел. Порядок и повторы
    не важны: границы приводятся к возрастанию, повторы убираются.

    Возвращает None, если границ меньше двух: одного числа
    на интервал не хватит, а молча достраивать вторую границу значит
    решать за человека.
    """
    if not text:
        return None
    out = []
    for part in str(text).replace(";", " ").replace(",", " ").split():
        # Разбор без исключений: сканер каталога отклоняет и голый
        # continue, и голый pass в обработчике.
        body = part.lstrip("+-")
        if body.replace(".", "", 1).isdigit():
            out.append(float(part))
    out = sorted(set(out))
    return out if len(out) >= 2 else None


def parse_labels(text, count):
    """Названия интервалов: ровно столько, сколько интервалов.

    Недостающие остаются пустыми, лишние отбрасываются: подставлять
    название не тому интервалу хуже, чем оставить его без названия.
    """
    parts = [p.strip() for p in str(text or "").split(",")]
    parts = [p for p in parts if p != ""] if any(parts) else []
    out = list(parts[:int(count)])
    while len(out) < int(count):
        out.append("")
    return out


def quantize(vol, edges):
    """Раскладка значений по интервалам: номер класса на ячейку.

    Границы задаются возрастающим списком. Ячейка ниже первой границы
    получает нулевой класс, выше последней - последний. Пропуски
    получают минус единицу и в модель не идут.
    """
    vol = np.asarray(vol, dtype=float)
    edges = np.asarray(edges, dtype=float)
    out = np.searchsorted(edges, vol, side="right").astype(np.int32)
    out[~np.isfinite(vol)] = -1
    return out


def _edges(shape, gt, z0, dz):
    """Границы ячеек по трём осям, на одну больше, чем ячеек."""
    nz, ny, nx = shape
    xs = gt[0] + np.arange(nx + 1) * gt[1]
    ys = gt[3] + np.arange(ny + 1) * gt[5]
    zs = z0 + (np.arange(nz + 1) - 0.5) * dz
    return zs, ys, xs


def visible_faces(mask):
    """Сколько граней остаётся после отбрасывания невидимых."""
    mask = np.asarray(mask, dtype=bool)
    total = 0
    for axis, side in _DIRS:
        a = np.moveaxis(mask, axis, 0)
        pad = np.zeros_like(a[:1])
        if side > 0:
            nb = np.concatenate([a[1:], pad], axis=0)
        else:
            nb = np.concatenate([pad, a[:-1]], axis=0)
        total += int((a & ~nb).sum())
    return total


def _row_runs(row):
    """Отрезки подряд идущих ячеек одного класса в одной строке.

    Возвращает список (столбец от, столбец до включительно, класс).
    Пустые ячейки помечены минус единицей и в отрезки не входят.
    """
    n = row.size
    if n == 0:
        return []
    change = np.empty(n, dtype=bool)
    change[0] = True
    change[1:] = row[1:] != row[:-1]
    starts = np.flatnonzero(change)
    ends = np.append(starts[1:], n) - 1
    out = []
    for s, e in zip(starts, ends):
        cls = int(row[s])
        if cls >= 0:
            out.append((int(s), int(e), cls))
    return out


def greedy_rects(key):
    """Слияние соседних клеток одного класса в прямоугольники.

    `key` это двумерный массив классов, минус единица означает пусто.
    Возвращает список (строка от, строка до, столбец от, столбец до,
    класс), границы включительные.
    """
    key = np.asarray(key)
    rows, _cols = key.shape
    out = []
    open_runs = {}
    for r in range(rows):
        cur = set(_row_runs(key[r]))
        for run in cur:
            if run not in open_runs:
                open_runs[run] = r
        for run in [k for k in open_runs if k not in cur]:
            c0, c1, cls = run
            out.append((open_runs.pop(run), r - 1, c0, c1, cls))
    for run, r0 in open_runs.items():
        c0, c1, cls = run
        out.append((r0, rows - 1, c0, c1, cls))
    return out


def _quad_corners(axis, side, slab, rect, zs, ys, xs):
    """Четыре угла прямоугольной грани в координатах карты."""
    r0, r1, c0, c1 = rect
    if axis == 0:
        z = zs[slab + 1] if side > 0 else zs[slab]
        a, b = ys[r0], ys[r1 + 1]
        c, d = xs[c0], xs[c1 + 1]
        return np.array([[c, a, z], [d, a, z], [d, b, z], [c, b, z]])
    if axis == 1:
        y = ys[slab + 1] if side > 0 else ys[slab]
        a, b = zs[r0], zs[r1 + 1]
        c, d = xs[c0], xs[c1 + 1]
        return np.array([[c, y, a], [d, y, a], [d, y, b], [c, y, b]])
    x = xs[slab + 1] if side > 0 else xs[slab]
    a, b = zs[r0], zs[r1 + 1]
    c, d = ys[c0], ys[c1 + 1]
    return np.array([[x, c, a], [x, d, a], [x, d, b], [x, c, b]])


def _outward(axis, side, zs, ys, xs):
    """Вектор наружу для данной стороны, с учётом знака шага грида."""
    step = {0: zs[1] - zs[0], 1: ys[1] - ys[0], 2: xs[1] - xs[0]}[axis]
    v = np.zeros(3)
    pos = {0: 2, 1: 1, 2: 0}[axis]
    v[pos] = side * (1.0 if step > 0 else -1.0)
    return v


def unit_rects(key):
    """Каждая занятая клетка отдельным прямоугольником, без слияния."""
    rows, cols = np.nonzero(np.asarray(key) >= 0)
    key = np.asarray(key)
    return [(int(r), int(r), int(c), int(c), int(key[r, c]))
            for r, c in zip(rows, cols)]


def voxel_mesh(mask, gt, z0=0.0, dz=1.0, classes=None, merge=True,
               max_quads=2000000):
    """Меш из коробок по занятым ячейкам.

    Возвращает вершины, треугольники и класс каждого треугольника.
    Если классы не заданы, сливаются все соседние видимые грани,
    и модель выходит одноцветной.

    При слиянии на гранях появляются Т-образные стыки: длинный
    прямоугольник упирается в два коротких, и общего ребра у них нет.
    Для показа это не мешает, а для подсчёта объёма и выгрузки телом
    слияние надо выключить: без него каждое ребро принадлежит ровно
    двум граням.

    При превышении `max_quads` работа прекращается и возвращается
    признак переполнения: сцена такого размера всё равно не читается,
    а память кончится раньше.
    """
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 3 or not mask.any():
        return (np.zeros((0, 3), dtype=np.float32),
                np.zeros((0, 3), dtype=np.int32),
                np.zeros(0, dtype=np.int32), False)
    if classes is None:
        key_full = np.where(mask, 0, -1).astype(np.int32)
    else:
        key_full = np.where(mask, np.asarray(classes), -1).astype(np.int32)
    zs, ys, xs = _edges(mask.shape, gt, z0, dz)

    corners, cls_out, out_vecs = [], [], []
    n_quads = 0
    for axis, side in _DIRS:
        a = np.moveaxis(mask, axis, 0)
        k = np.moveaxis(key_full, axis, 0)
        pad = np.zeros_like(a[:1])
        kpad = np.full_like(k[:1], -1)
        if side > 0:
            nb = np.concatenate([a[1:], pad], axis=0)
            nbk = np.concatenate([k[1:], kpad], axis=0)
        else:
            nb = np.concatenate([pad, a[:-1]], axis=0)
            nbk = np.concatenate([kpad, k[:-1]], axis=0)
        # Грань между занятыми ячейками разных интервалов остаётся:
        # 2.04 пишет объект на интервал, и без неё оба тела выходят
        # дырявыми на стыке. Вместе они выглядят целыми, а беда
        # вылезает только при разрезе.
        vis = a & (~nb | (k != nbk))
        if not vis.any():
            continue
        out_vec = _outward(axis, side, zs, ys, xs)
        for slab in range(vis.shape[0]):
            plane = vis[slab]
            if not plane.any():
                continue
            key = np.where(plane, k[slab], -1)
            rects = greedy_rects(key) if merge else unit_rects(key)
            for r0, r1, c0, c1, cls in rects:
                corners.append(_quad_corners(axis, side, slab,
                                             (r0, r1, c0, c1), zs, ys, xs))
                cls_out.append(cls)
                out_vecs.append(out_vec)
                n_quads += 1
            if n_quads > max_quads:
                return (np.zeros((0, 3), dtype=np.float32),
                        np.zeros((0, 3), dtype=np.int32),
                        np.zeros(0, dtype=np.int32), True)

    if not corners:
        return (np.zeros((0, 3), dtype=np.float32),
                np.zeros((0, 3), dtype=np.int32),
                np.zeros(0, dtype=np.int32), False)

    quads = np.asarray(corners, dtype=float)
    verts = quads.reshape(-1, 3)
    m = quads.shape[0]
    idx = np.arange(m) * 4
    tris = np.concatenate([
        np.stack([idx, idx + 1, idx + 2], axis=1),
        np.stack([idx, idx + 2, idx + 3], axis=1)], axis=0)
    cls_arr = np.asarray(cls_out, dtype=np.int32)
    tri_cls = np.concatenate([cls_arr, cls_arr])
    normals = np.asarray(out_vecs, dtype=float)
    tri_out = np.concatenate([normals, normals], axis=0)

    # Разворот граней наружу считается по данным: шаг грида по Y обычно
    # отрицательный, и порядок обхода из-за этого меняется на обратный.
    tris = _face_outward(verts, tris, tri_out)
    return (verts.astype(np.float32), tris.astype(np.int32),
            tri_cls, False)


def _face_outward(verts, tris, want):
    """Разворачивает треугольники так, чтобы нормаль смотрела наружу."""
    a = verts[tris[:, 0]]
    b = verts[tris[:, 1]]
    c = verts[tris[:, 2]]
    nrm = np.cross(b - a, c - a)
    flip = np.einsum("ij,ij->i", nrm, want) < 0
    out = tris.copy()
    out[flip, 1] = tris[flip, 2]
    out[flip, 2] = tris[flip, 1]
    return out


def pinch_edges(mask):
    """Число защипов по ребру: касаний ячеек только диагональю.

    Две занятые ячейки, соприкасающиеся диагональю, дают ребро,
    принадлежащее четырём граням. Дырой это не является и объём
    не портит, но оболочка перестаёт быть многообразием, и проверка
    замкнутости по рёбрам такое тело отвергает.
    """
    mask = np.asarray(mask, dtype=bool)
    total = 0
    for ax in ((0, 1), (0, 2), (1, 2)):
        a = np.moveaxis(mask, ax, (0, 1))
        for s1 in (1, -1):
            for s2 in (1, -1):
                diag = np.roll(np.roll(a, -s1, axis=0), -s2, axis=1)
                n1 = np.roll(a, -s1, axis=0)
                n2 = np.roll(a, -s2, axis=1)
                total += int((a & diag & ~n1 & ~n2).sum())
    return total // 2


def unpinch(mask, rounds=8):
    """Заполняет углы, которыми ячейки касаются диагональю.

    Добавляется одна ячейка на защип, и касание становится по грани.
    Заполнение может породить новый защип, поэтому проходов несколько.
    Возвращает (маску, сколько ячеек добавлено).
    """
    out = np.asarray(mask, dtype=bool).copy()
    added = 0
    for _ in range(int(rounds)):
        fill = np.zeros_like(out)
        for ax in ((0, 1), (0, 2), (1, 2)):
            a = np.moveaxis(out, ax, (0, 1))
            f = np.moveaxis(fill, ax, (0, 1))
            for s1 in (1, -1):
                for s2 in (1, -1):
                    diag = np.roll(np.roll(a, -s1, axis=0), -s2, axis=1)
                    n1 = np.roll(a, -s1, axis=0)
                    n2 = np.roll(a, -s2, axis=1)
                    hit = a & diag & ~n1 & ~n2
                    f |= np.roll(hit, s1, axis=0)
        new = fill & ~out
        n = int(new.sum())
        if not n:
            break
        out |= new
        added += n
    return out, added
