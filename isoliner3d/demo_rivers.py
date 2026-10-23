# -*- coding: utf-8 -*-
"""Демонстрационная речная сеть с расходами (2.16).

Рельеф задаётся формулой: общий уклон к выходу, гряды и случайные
холмы. По нему строится сток: бессточные понижения заполняются,
направление течёт к самому крутому из восьми соседей, площадь
водосбора копится вниз по течению. Русло начинается там, где
водосбор больше порога, расход пропорционален площади водосбора.

Набор нужен, чтобы показать линии трубами: расход растёт вниз
по течению на порядки, и толщина трубы читается сразу. Порядок
по Стралеру лежит отдельным полем: им удобно красить.

Считается на голом NumPy, QGIS не нужен.
"""

import heapq

import numpy as np

# соседи по часовой стрелке, начиная с востока: (строка, столбец)
_DR = np.array([0, 1, 1, 1, 0, -1, -1, -1])
_DC = np.array([1, 1, 0, -1, -1, -1, 0, 1])


def make_dem(nx=140, ny=110, cell=50.0, seed=1, relief=120.0):
    """Рельеф (ny, nx), строка 0 - север, отметки в метрах.

    Общий уклон ведёт к югу и немного к востоку, чтобы реки сходились
    к одному выходу на южной кромке. Гряды и холмы дают водоразделы
    и притоки.
    """
    rng = np.random.default_rng(seed)
    y = np.arange(ny)[:, None] / max(ny - 1, 1)
    x = np.arange(nx)[None, :] / max(nx - 1, 1)
    # к югу (большие номера строк) и к середине южной кромки
    z = relief * (1.0 - y) * 0.9 + 0.35 * relief * (x - 0.55) ** 2 * 4.0
    for _ in range(14):
        cx, cy = rng.uniform(0, 1), rng.uniform(0, 1)
        s = rng.uniform(0.04, 0.12)
        h = rng.uniform(-0.12, 0.22) * relief
        z = z + h * np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2 * s * s))
    z = z + 0.06 * relief * np.sin(9.0 * x + 2.0 * rng.uniform()) \
        * np.cos(7.0 * y)
    z = z + rng.normal(0.0, 0.004 * relief, z.shape)
    return z + 150.0


def fill_pits(z):
    """Заполнить бессточные понижения: вода выходит к кромке.

    Обход от кромки по возрастанию отметки (заполнение с очередью).
    Ячейка, в которую пришли снизу, поднимается до отметки соседа
    с малым уклоном, чтобы направление стока у неё было.
    """
    ny, nx = z.shape
    out = z.astype(float).copy()
    seen = np.zeros(z.shape, dtype=bool)
    heap = []
    for r in range(ny):
        for c in (0, nx - 1):
            heapq.heappush(heap, (out[r, c], r, c))
            seen[r, c] = True
    for c in range(1, nx - 1):
        for r in (0, ny - 1):
            heapq.heappush(heap, (out[r, c], r, c))
            seen[r, c] = True
    eps = 1e-4
    while heap:
        h, r, c = heapq.heappop(heap)
        for k in range(8):
            rr, cc = r + _DR[k], c + _DC[k]
            if 0 <= rr < ny and 0 <= cc < nx and not seen[rr, cc]:
                seen[rr, cc] = True
                if out[rr, cc] <= h:
                    out[rr, cc] = h + eps
                heapq.heappush(heap, (out[rr, cc], rr, cc))
    return out


def flow_dirs(z, cell):
    """Номер соседа стока у каждой ячейки, -1 у стока за кромку."""
    ny, nx = z.shape
    best = np.zeros(z.shape)
    d = np.full(z.shape, -1, dtype=np.int64)
    pad = np.pad(z, 1, mode="constant", constant_values=np.inf)
    for k in range(8):
        nb = pad[1 + _DR[k]:1 + _DR[k] + ny, 1 + _DC[k]:1 + _DC[k] + nx]
        dist = cell * (np.sqrt(2.0) if _DR[k] and _DC[k] else 1.0)
        slope = (z - nb) / dist
        upd = slope > best
        best = np.where(upd, slope, best)
        d = np.where(upd, k, d)
    # кромка без нижнего соседа уходит наружу
    return d


def accumulate(z, d):
    """Число ячеек водосбора, считая саму ячейку."""
    ny, nx = z.shape
    acc = np.ones(z.size)
    order = np.argsort(-z, axis=None)
    rr, cc = np.divmod(order, nx)
    dd = d.ravel()[order]
    for i in range(len(order)):
        k = dd[i]
        if k < 0:
            continue
        r2, c2 = rr[i] + _DR[k], cc[i] + _DC[k]
        if 0 <= r2 < ny and 0 <= c2 < nx:
            acc[r2 * nx + c2] += acc[order[i]]
    return acc.reshape(z.shape)


def network(z, d, acc, min_cells):
    """Звенья сети от истока или слияния до слияния или выхода.

    Возвращает список словарей: ячейки звена (строка, столбец) по
    течению, порядок по Стралеру, площадь водосбора в ячейках
    в начале и в конце звена.
    """
    ny, nx = z.shape
    chan = acc >= min_cells

    def down(r, c):
        k = d[r, c]
        if k < 0:
            return None
        r2, c2 = r + _DR[k], c + _DC[k]
        if 0 <= r2 < ny and 0 <= c2 < nx:
            return int(r2), int(c2)
        return None

    # сколько русловых ячеек втекает в каждую
    inflow = np.zeros(z.shape, dtype=np.int64)
    rs, cs = np.nonzero(chan)
    for r, c in zip(rs, cs):
        nb = down(r, c)
        if nb is not None and chan[nb]:
            inflow[nb] += 1
    # звено начинается в истоке (нет притоков) или ниже слияния
    starts = [(r, c) for r, c in zip(rs, cs) if inflow[r, c] != 1]
    links, end_of = [], {}
    for r, c in starts:
        cells = [(int(r), int(c))]
        cur = (int(r), int(c))
        while True:
            nb = down(*cur)
            if nb is None or not chan[nb]:
                break
            cells.append(nb)
            if inflow[nb] != 1:
                break
            cur = nb
        links.append({"cells": cells})
        end_of[(int(r), int(c))] = len(links) - 1
    # порядок по Стралеру: от верхних звеньев к нижним
    up = {}
    for i, ln in enumerate(links):
        last = ln["cells"][-1]
        if last in end_of and end_of[last] != i:
            up.setdefault(end_of[last], []).append(i)
    order = [0] * len(links)

    def strahler(i):
        if order[i]:
            return order[i]
        ups = [strahler(j) for j in up.get(i, [])]
        if not ups:
            o = 1
        else:
            top = max(ups)
            o = top + 1 if ups.count(top) > 1 else top
        order[i] = o
        return o
    import sys
    lim = sys.getrecursionlimit()
    sys.setrecursionlimit(max(lim, 10 * len(links) + 100))
    try:
        for i in range(len(links)):
            strahler(i)
    finally:
        sys.setrecursionlimit(lim)
    for i, ln in enumerate(links):
        ln["order"] = order[i]
        a0 = ln["cells"][0]
        # расход звена - по нижней ячейке перед слиянием: в самой
        # точке слияния уже сложены оба притока
        tail = ln["cells"][-2] if len(ln["cells"]) > 1 else a0
        ln["acc0"] = float(acc[a0])
        ln["acc1"] = float(acc[tail])
    return links


def smooth(xyz, rounds=2):
    """Срезать углы ломаной (Чайкин), концы на месте.

    Русло по восьми направлениям идёт ступенькой через ячейку, а
    у трубы на каждой ступеньке излом. Концы не двигаются, иначе
    притоки отошли бы от места слияния.
    """
    p = np.asarray(xyz, dtype=float)
    for _ in range(int(rounds)):
        if len(p) < 3:
            return p
        q = 0.75 * p[:-1] + 0.25 * p[1:]
        r = 0.25 * p[:-1] + 0.75 * p[1:]
        mid = np.empty((2 * (len(p) - 1), 3))
        mid[0::2], mid[1::2] = q, r
        p = np.vstack([p[:1], mid[1:-1], p[-1:]])
    return p


def demo(nx=140, ny=110, cell=50.0, seed=1, min_area_km2=0.5,
         runoff=8.0, x0=0.0, y0=0.0, lift=3.0):
    """Рельеф и речная сеть в координатах местности.

    `runoff` - модуль стока, литров в секунду с квадратного
    километра. `lift` - подъём русла над рельефом, метры: линия
    по самой поверхности уходит под неё в половине ячеек.

    Возвращает словарь: dem (ny, nx) с заполненными понижениями,
    gt - геопривязка GDAL, links - список звеньев с ключами
    xyz (N, 3), order, q (расход в конце звена, м3/с), area_km2,
    length_m.
    """
    z = fill_pits(make_dem(nx, ny, cell, seed))
    d = flow_dirs(z, cell)
    acc = accumulate(z, d)
    cell_km2 = cell * cell / 1e6
    min_cells = max(int(np.ceil(min_area_km2 / cell_km2)), 2)
    links = network(z, d, acc, min_cells)
    ytop = y0 + ny * cell
    gt = (float(x0), float(cell), 0.0, float(ytop), 0.0, -float(cell))
    out = []
    for ln in links:
        cells = np.array(ln["cells"])
        xs = x0 + (cells[:, 1] + 0.5) * cell
        ys = ytop - (cells[:, 0] + 0.5) * cell
        zs = z[cells[:, 0], cells[:, 1]] + lift
        xyz = np.column_stack([xs, ys, zs])
        if len(xyz) < 2:
            continue
        xyz = smooth(xyz)
        area = ln["acc1"] * cell_km2
        out.append({"xyz": xyz, "order": int(ln["order"]),
                    "area_km2": float(area),
                    "q": float(area * runoff / 1000.0),
                    "length_m": float(np.sum(np.linalg.norm(
                        np.diff(xyz[:, :2], axis=0), axis=1)))})
    return {"dem": z, "gt": gt, "links": out}
