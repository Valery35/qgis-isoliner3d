# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Интерполяция значений в объёме по точкам.

Два метода: ближний сосед и обратные расстояния. Кригинг встанет сюда же
третьим, поэтому обвязка общая: сетка, поиск соседей, анизотропия,
пропуски.

Поиск соседей идёт по ячейкам, а не перебором: точки раскладываются
по сетке с шагом порядка радиуса, и для узла берутся только соседние
ячейки. Куб двести на двести на сто это четыре миллиона узлов, перебор
всех точек для каждого узла не пройдёт.

Анизотропия задаётся одним числом: отношением вертикального масштаба
к горизонтальному. Перед поиском вертикальная координата делится на
него. Без этого при шаге по горизонтали в сотни метров и по вертикали
в метры ближайшей точкой окажется соседняя скважина, а не соседний
замер в той же точке плана.
"""

import numpy as np


class CellIndex(object):
    """Точки, разложенные по ячейкам сетки поиска."""

    def __init__(self, pts, cell):
        self.cell = float(cell)
        self.pts = np.asarray(pts, dtype=float)
        keys = np.floor(self.pts / self.cell).astype(np.int64)
        self.order = np.lexsort((keys[:, 2], keys[:, 1], keys[:, 0]))
        self.keys = keys[self.order]
        self.sorted = self.pts[self.order]
        uniq, start = np.unique(self.keys, axis=0, return_index=True)
        self.uniq = uniq
        self.start = np.append(start, len(self.keys))
        self.lookup = {tuple(k): i for i, k in enumerate(uniq)}

    def neighbours(self, point, rings=1):
        """Номера точек в соседних ячейках вокруг узла."""
        base = np.floor(np.asarray(point, dtype=float)
                        / self.cell).astype(np.int64)
        out = []
        rng = range(-rings, rings + 1)
        for dx in rng:
            for dy in rng:
                for dz in rng:
                    idx = self.lookup.get((base[0] + dx, base[1] + dy,
                                           base[2] + dz))
                    if idx is None:
                        continue
                    a, b = self.start[idx], self.start[idx + 1]
                    out.append(self.order[a:b])
        if not out:
            return np.zeros(0, dtype=np.int64)
        return np.concatenate(out)


# Выше этого числа точек матрица расстояний блоком уже не окупается,
# и работа идёт через ячеечный указатель.
_DENSE_LIMIT = 20000

# Узлов в блоке: блок на двадцать тысяч точек это примерно полсотни
# мегабайт, столько можно занять не спрашивая.
_BLOCK = 2000


def _dense(pts, val, nodes, r2, method, power, max_points, min_points):
    """Тот же расчёт блоками узлов, без поштучного цикла.

    Результат совпадает с расчётом по одному узлу: тот же шар,
    те же ближайшие точки, тот же вес.
    """
    n = len(nodes)
    out = np.full(n, np.nan)
    pn2 = (pts * pts).sum(axis=1)
    kmax = max(int(max_points), 0)
    kmin = max(int(min_points), 1)
    for a in range(0, n, _BLOCK):
        b = min(a + _BLOCK, n)
        blk = nodes[a:b]
        # Расстояния через произведение матриц: раскрытие квадрата
        # уходит в BLAS, а разность по осям заняла бы втрое больше
        # памяти и считалась бы медленнее.
        d2 = ((blk * blk).sum(axis=1)[:, None] + pn2[None, :]
              - 2.0 * (blk @ pts.T))
        np.maximum(d2, 0.0, out=d2)
        inside = d2 <= r2
        cnt = inside.sum(axis=1)
        d2 = np.where(inside, d2, np.inf)
        if kmax and kmax < pts.shape[0]:
            take = np.argpartition(d2, kmax - 1, axis=1)[:, :kmax]
        else:
            take = np.argsort(d2, axis=1)
        rows = np.arange(b - a)[:, None]
        dsel = d2[rows, take]
        vsel = val[take]
        good = np.isfinite(dsel)
        if method == "nearest":
            first = np.argmin(np.where(good, dsel, np.inf), axis=1)
            res = vsel[np.arange(b - a), first]
        else:
            hit = dsel <= 1e-12
            w = np.where(good, 1.0 / np.power(np.sqrt(
                np.where(good, dsel, 1.0)), float(power)), 0.0)
            wsum = w.sum(axis=1)
            res = np.where(wsum > 0, (w * vsel).sum(axis=1)
                           / np.where(wsum > 0, wsum, 1.0), np.nan)
            if hit.any():
                first = np.argmax(hit, axis=1)
                exact = hit.any(axis=1)
                res = np.where(exact, vsel[np.arange(b - a), first], res)
        out[a:b] = np.where(cnt >= kmin, res, np.nan)
    return out


def interpolate(points, values, grid, method="idw", radius=None,
                anisotropy=1.0, power=2.0, max_points=16, min_points=1):
    """Значения в узлах сетки по точкам.

    `points` это (N, 3) в координатах карты, `grid` это (M, 3) узлы,
    `anisotropy` отношение вертикального масштаба к горизонтальному.

    Узлы, где точек в радиусе меньше `min_points`, остаются пропуском:
    пустота лучше выдуманного значения.
    """
    pts = np.asarray(points, dtype=float).copy()
    val = np.asarray(values, dtype=float)
    nodes = np.asarray(grid, dtype=float).copy()
    if not len(pts) or not len(nodes):
        return np.full(len(nodes), np.nan)

    aniso = float(anisotropy) or 1.0
    pts[:, 2] /= aniso
    nodes[:, 2] /= aniso

    if radius is None or radius <= 0:
        span = np.ptp(pts, axis=0)
        radius = float(max(span.max(), 1.0)) / 4.0
    cell = max(float(radius), 1e-9)
    index = CellIndex(pts, cell)

    out = np.full(len(nodes), np.nan)
    r2 = float(radius) ** 2

    # Точек немного: считаем расстояния блоками узлов целиком на NumPy.
    # Ячеечный указатель при большом радиусе всё равно отдаёт почти все
    # точки, и выигрыш даёт не отбор кандидатов, а уход от поштучного
    # цикла по узлам.
    if len(pts) <= _DENSE_LIMIT:
        return _dense(pts, val, nodes, r2, method, power,
                      int(max_points), int(min_points))

    for i, node in enumerate(nodes):
        cand = index.neighbours(node)
        if not len(cand):
            continue
        d2 = ((pts[cand] - node) ** 2).sum(axis=1)
        near = d2 <= r2
        if near.sum() < max(int(min_points), 1):
            continue
        cand, d2 = cand[near], d2[near]
        if len(cand) > int(max_points) > 0:
            keep = np.argsort(d2)[:int(max_points)]
            cand, d2 = cand[keep], d2[keep]
        if method == "nearest":
            out[i] = val[cand[int(np.argmin(d2))]]
            continue
        if (d2 <= 1e-12).any():
            out[i] = val[cand[int(np.argmin(d2))]]
            continue
        w = 1.0 / np.power(np.sqrt(d2), float(power))
        out[i] = float((w * val[cand]).sum() / w.sum())
    return out


def grid_nodes(x0, y0, z0, nx, ny, nz, dx, dy, dz):
    """Узлы куба в порядке (уровень, строка, столбец)."""
    xs = x0 + (np.arange(nx) + 0.5) * dx
    ys = y0 - (np.arange(ny) + 0.5) * dy
    zs = z0 + np.arange(nz) * dz
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    return np.column_stack([X.transpose(2, 1, 0).ravel(),
                            Y.transpose(2, 1, 0).ravel(),
                            Z.transpose(2, 1, 0).ravel()])


def cross_validate(points, values, method="idw", **kw):
    """Проверка с исключением по одной точке.

    Возвращает (остатки, средняя ошибка, среднеквадратичная). Без неё
    сравнивать методы нельзя: у обратных расстояний степень и радиус
    подбираются, и подбирать надо по числам.
    """
    pts = np.asarray(points, dtype=float)
    val = np.asarray(values, dtype=float)
    res = np.full(len(pts), np.nan)
    for i in range(len(pts)):
        mask = np.ones(len(pts), dtype=bool)
        mask[i] = False
        got = interpolate(pts[mask], val[mask], pts[i:i + 1],
                          method=method, **kw)
        res[i] = got[0] - val[i]
    ok = np.isfinite(res)
    if not ok.any():
        return res, float("nan"), float("nan")
    return (res, float(np.mean(np.abs(res[ok]))),
            float(np.sqrt(np.mean(res[ok] ** 2))))
