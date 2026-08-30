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


def drop_degenerate(verts, faces):
    """Убрать схлопнувшиеся грани: у них совпадают номера вершин.

    После склейки вершин часть треугольников вырождается в линию.
    Площади у такой грани нет, объёму она не нужна, а счёт рёбер
    портит: своё ребро она считает дважды. На настоящем теле это
    выдумало двадцать пять защипов и спрятало дыру из трёх рёбер,
    показав одно.
    """
    f = np.asarray(faces)
    if not len(f):
        return f
    bad = ((f[:, 0] == f[:, 1]) | (f[:, 1] == f[:, 2])
           | (f[:, 0] == f[:, 2]))
    return f[~bad]


def shell_defects(verts, faces):
    """Дыры и защипы оболочки, по отдельности.

    Правило «у каждого ребра ровно две грани» валит в одну кучу два
    разных случая. У дыры есть рёбра с одной гранью, и объём по такому
    телу бессмыслен. У защипа - там, где тело касается само себя, -
    рёбра принадлежат трём и более граням, дыр при этом нет, и объём
    считается точно.

    Возвращает пару: рёбер с одной гранью и рёбер с тремя и более.
    """
    if not len(faces):
        return 0, 0
    # Считаем по склеенным вершинам: у несклеенного меша совпадающие
    # точки это разные номера, и ни дыры, ни защипа не видно.
    from .iso3d import weld
    _v, faces = weld(np.asarray(verts, dtype=float),
                     np.asarray(faces))
    faces = drop_degenerate(_v, faces)
    if not len(faces):
        return 0, 0
    cnt = _edges(faces)
    holes = sum(1 for n in cnt.values() if n == 1)
    pinch = sum(1 for n in cnt.values() if n > 2)
    return int(holes), int(pinch)


def is_closed_mesh(verts, faces):
    """Нет ли в оболочке дыр.

    Защипы замкнутости не мешают: объём по телу с защипом считается
    точно, а по телу с дырой - нет.
    """
    if not len(faces):
        return False
    holes, _pinch = shell_defects(verts, faces)
    return holes == 0


def orient_faces(verts, faces):
    """Согласовать обход граней по всей оболочке.

    Формула объёма складывает подписанные объёмы тетраэдров, и грань,
    обойдённая в другую сторону, вычитается вместо сложения. У маршевой
    поверхности с крышками обход вразнобой, и без согласования объём
    выходит втрое меньше настоящего.

    Обход идёт по соседству через общие рёбра: у согласованных граней
    общее ребро проходится в противоположных направлениях. Грани,
    до которых не дошли, остаются как были.
    """
    f = np.asarray(faces).copy()
    if not len(f):
        return f
    edge_map = collections.defaultdict(list)
    for i, tri in enumerate(f):
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]),
                     (tri[2], tri[0])):
            edge_map[(a, b) if a < b else (b, a)].append(i)
    seen = np.zeros(len(f), dtype=bool)
    for start in range(len(f)):
        if seen[start]:
            continue
        seen[start] = True
        stack = [start]
        while stack:
            i = stack.pop()
            tri = f[i]
            for a, b in ((tri[0], tri[1]), (tri[1], tri[2]),
                         (tri[2], tri[0])):
                key = (a, b) if a < b else (b, a)
                for j in edge_map[key]:
                    if seen[j]:
                        continue
                    seen[j] = True
                    t2 = f[j]
                    # общее ребро должно идти в другую сторону
                    same = any(t2[k] == a and t2[(k + 1) % 3] == b
                               for k in range(3))
                    if same:
                        f[j] = t2[::-1]
                    stack.append(j)
    return f


def mesh_volume(verts, faces):
    """Объём замкнутой оболочки.

    Считается через сумму подписанных объёмов тетраэдров, натянутых
    на грань и начало координат: точная формула, а не приближение
    по ячейкам. Считать по ячейкам нельзя - оболочка режет их пополам,
    и сумма по целым даёт ступенчатую ошибку.

    Знак зависит от того, наружу или внутрь смотрят грани, поэтому
    возвращается модуль: вывернутая оболочка это не отрицательный
    объём, а та же самая.

    У незамкнутой оболочки число выйдет, но смысла в нём нет:
    проверяйте `is_closed_mesh` до того, как показывать его человеку.
    """
    v = np.asarray(verts, dtype=float)
    f = np.asarray(faces)
    if not len(f):
        return 0.0
    f = drop_degenerate(v, orient_faces(v, f))
    if not len(f):
        return 0.0
    # Считаем от середины тела, а не от начала координат. Формула
    # складывает объёмы тетраэдров, натянутых на грань и начало.
    # В настоящих координатах - шесть миллионов метров по северу -
    # каждое слагаемое выходит порядка десяти в четырнадцатой,
    # а их сумма должна дать миллион: значащие цифры съедаются
    # взаимным вычитанием. На теле из девяноста трёх тысяч граней
    # так вышло восемь миллиардов кубометров вместо миллиона,
    # то есть в тысячу триста раз больше собственного габарита.
    v = v - v.mean(axis=0)
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    return float(abs(np.einsum("ij,ij->i",
                               a, np.cross(b, c)).sum()) / 6.0)


def split_bodies(verts, faces, snap=None, tag=None):
    """Разбить меш на связные тела.

    Вершины сперва склеиваются: слой пишет треугольники поштучно,
    и без склейки каждый из них окажется отдельным телом. Ровно
    на этом спотыкается разбиение составной геометрии в QGIS -
    связность там не считается вовсе.

    `tag` это номер исходного объекта на каждую грань. Если он задан,
    Возвращаются тройки (вершины, грани, номера) всегда: без метки
    третьим идёт None. Кортеж разной длины ловится только падением
    на месте вызова.

    Возвращает список от большего куска к меньшему.
    """
    from .iso3d import weld
    v = np.asarray(verts, dtype=float)
    f = np.asarray(faces)
    if not len(f):
        return []
    v, f = weld(v, f) if snap is None else weld(v, f, snap)
    lab = _labels(v, f)
    out = []
    for key in sorted(set(lab.tolist())):
        sel = lab == key
        fs = f[sel]
        used = np.unique(fs)
        remap = np.full(len(v), -1, dtype=np.int64)
        remap[used] = np.arange(len(used))
        # Длина кортежа одна всегда. Возврат разной длины в зависимости
        # от довода ловится только на месте вызова, и притом падением:
        # без метки шли пары, а вызывающий ждал тройки.
        own = (None if tag is None
               else np.asarray(tag, dtype=np.int64)[sel])
        out.append((v[used], remap[fs], own))
    out.sort(key=lambda p: -len(p[1]))
    return out


def close_holes(verts, faces, max_edges=64):
    """Зашить мелкие дыры оболочки веером по их краю.

    На оболочке в десятки тысяч граней остаётся пара рваных рёбер:
    вырожденная ячейка на стыке крышки с поверхностью. Искать причину
    по одному такому случаю дороже, чем зашить остаток.

    Большие дыры не трогаем: затянув пол-оболочки плоской заплатой,
    получишь объём, который выглядит настоящим и неверен. Порог
    `max_edges` и есть граница между изъяном и настоящей прорехой.

    Возвращает вершины, грани и число зашитых дыр.
    """
    from .iso3d import weld
    v = np.asarray(verts, dtype=float)
    f = np.asarray(faces)
    if not len(f):
        return v, f, 0
    v, f = weld(v, f)
    f = drop_degenerate(v, f)
    cnt = _edges(f)
    border = [e for e, n in cnt.items() if n == 1]
    if not border:
        return v, f, 0
    nb = collections.defaultdict(list)
    for a, b in border:
        nb[a].append(b)
        nb[b].append(a)
    seen = set()
    add_f = []
    n_done = 0
    # Сперва концы края, потом всё прочее. Начав с середины, обход
    # уйдёт в одну сторону, и вторая половина останется необойдённой:
    # дыра не зашьётся вовсе. Порядок вершин в словаре произволен,
    # и полагаться на него нельзя.
    order = sorted(nb, key=lambda q: len(nb[q]))
    for start in order:
        if start in seen:
            continue
        loop, cur, prev = [start], start, None
        seen.add(start)
        while True:
            nxt = [q for q in nb[cur] if q != prev and q not in seen]
            if not nxt:
                break
            cur, prev = nxt[0], cur
            seen.add(cur)
            loop.append(cur)
            if cur == start:
                break
        if len(loop) < 3 or len(loop) > int(max_edges):
            continue
        for t in range(1, len(loop) - 1):
            add_f.append([loop[0], loop[t], loop[t + 1]])
        n_done += 1
    if not add_f:
        return v, f, 0
    return v, np.vstack([f, np.asarray(add_f, dtype=f.dtype)]), n_done
