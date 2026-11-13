# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""3D-плотность: сколько объектов в каждой ячейке объёма.

Та же регулярная сетка, что у куба, но в ячейке не оценка значения,
а измеренный факт: число объектов, сумма или среднее их атрибута,
длина линий внутри ячейки. Пустая ячейка - ноль, а не пропуск: ноль
находок тоже находка. Идея из модуля QGIS 3D Studio, расчёт свой.

Объект считается один раз, в одной точке: точка - своим положением,
линия - серединой по длине, полигон - центром кольца. Длина линии
делится между ячейками точно, по пересечениям отрезка с гранями
сетки, а не выборкой точек вдоль него: сумма по ячейкам равна длине
линии внутри сетки до округления.

Без QGIS и Qt.
"""
import math

import numpy as np

METRICS = ("count", "sum", "mean", "length")


class Lattice(object):
    """Сетка куба: начало, шаг, число ячеек по x, y, z.

    Начало - нижний юго-западный угол первой ячейки. Ячейка (k, j, i)
    занимает x0 + i*dx .. x0 + (i+1)*dx и так же по y и z.
    """

    def __init__(self, x0, y0, z0, dx, dy, dz, nx, ny, nz):
        self.origin = np.array([x0, y0, z0], dtype=float)
        self.step = np.array([dx, dy, dz], dtype=float)
        self.size = np.array([nx, ny, nz], dtype=np.int64)

    @classmethod
    def around(cls, lo, hi, cell_xy, cell_z, limit=4000000):
        """Сетка на охват данных, с запасом в полячейки по краям.

        Шаг ноль берётся от охвата: около пятидесяти ячеек по длинной
        стороне плана и двадцати по высоте. Сетка крупнее limit ячеек
        - отказ с подсказкой укрупнить шаг.
        """
        lo = np.asarray(lo, dtype=float)
        hi = np.asarray(hi, dtype=float)
        span = np.maximum(hi - lo, 1e-9)
        dxy = float(cell_xy) if cell_xy and cell_xy > 0 else \
            _round_step(max(span[0], span[1]) / 50.0)
        dz = float(cell_z) if cell_z and cell_z > 0 else \
            _round_step(span[2] / 20.0) if span[2] > 1e-6 else dxy
        step = np.array([dxy, dxy, dz])
        x0 = np.floor(lo / step) * step
        x1 = np.ceil(hi / step) * step
        n = np.maximum(np.round((x1 - x0) / step).astype(np.int64), 1)
        # точка ровно на верхней грани охвата попадает в сетку
        n = np.where(x0 + n * step <= hi, n + 1, n)
        total = int(n[0] * n[1] * n[2])
        if total > limit:
            raise ValueError("cells %d x %d x %d = %d > %d"
                             % (n[0], n[1], n[2], total, limit))
        return cls(x0[0], x0[1], x0[2], step[0], step[1], step[2],
                   n[0], n[1], n[2])

    @property
    def shape(self):
        """(nz, ny, nx): так лежит массив куба."""
        return (int(self.size[2]), int(self.size[1]), int(self.size[0]))

    def index(self, pts):
        """Номера ячеек точек (k, j, i) и признак, что точка в сетке."""
        p = np.asarray(pts, dtype=float).reshape(-1, 3)
        ijk = np.floor((p - self.origin) / self.step).astype(np.int64)
        ok = np.all((ijk >= 0) & (ijk < self.size), axis=1) & \
            np.isfinite(p).all(axis=1)
        return ijk, ok

    def flat(self, ijk):
        nx, ny = int(self.size[0]), int(self.size[1])
        return (ijk[:, 2] * ny + ijk[:, 1]) * nx + ijk[:, 0]


def _round_step(x):
    """Круглый шаг: 1, 2, 2.5 или 5 на степень десяти."""
    if not x > 0:
        return 1.0
    p = 10.0 ** math.floor(math.log10(x))
    for m in (1.0, 2.0, 2.5, 5.0, 10.0):
        if x <= m * p * 1.0001:
            return m * p
    return 10.0 * p


def segment_cells(a, b, lat):
    """Отрезок a-b по ячейкам: (номера ячеек, длины частей).

    Отрезок режется по всем граням сетки, через которые проходит,
    и каждая часть отдаётся ячейке своей середины. Части вне сетки
    отбрасываются.
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    d = b - a
    seg = float(np.linalg.norm(d))
    if not seg > 0:
        return np.zeros(0, dtype=np.int64), np.zeros(0)
    ts = [0.0, 1.0]
    for ax in range(3):
        if abs(d[ax]) < 1e-15:
            continue
        lo = (min(a[ax], b[ax]) - lat.origin[ax]) / lat.step[ax]
        hi = (max(a[ax], b[ax]) - lat.origin[ax]) / lat.step[ax]
        planes = np.arange(math.floor(lo) + 1, math.ceil(hi))
        if len(planes):
            pos = lat.origin[ax] + planes * lat.step[ax]
            ts.extend(((pos - a[ax]) / d[ax]).tolist())
    t = np.unique(np.clip(np.asarray(ts), 0.0, 1.0))
    mid = 0.5 * (t[:-1] + t[1:])
    part = (t[1:] - t[:-1]) * seg
    ijk, ok = lat.index(a + mid[:, None] * d)
    return lat.flat(ijk[ok]), part[ok]


def _anchor(geom, parts):
    """Точка, в которой объект считается один раз."""
    pts = [np.asarray(p, dtype=float).reshape(-1, 3) for p in parts]
    pts = [p for p in pts if len(p)]
    if not pts:
        return None
    if geom == "line":
        best, best_len = None, -1.0
        for p in pts:
            if len(p) < 2:
                continue
            seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
            tot = float(seg.sum())
            if tot > best_len:
                best, best_len = (p, seg, tot), tot
        if best is None or best_len <= 0:
            return pts[0].mean(axis=0)
        p, seg, tot = best
        acc = np.concatenate([[0.0], np.cumsum(seg)])
        k = int(np.searchsorted(acc, tot / 2.0, side="right") - 1)
        k = min(max(k, 0), len(seg) - 1)
        t = (tot / 2.0 - acc[k]) / seg[k] if seg[k] > 0 else 0.0
        return p[k] + t * (p[k + 1] - p[k])
    if geom == "polygon":
        ring = pts[0]
        if len(ring) > 1 and np.array_equal(ring[0], ring[-1],
                                            equal_nan=True):
            ring = ring[:-1]
        return ring.mean(axis=0)
    return np.vstack(pts).mean(axis=0)


def density(objects, geom, lat, value=None):
    """Плотность по ячейкам сетки lat.

    objects - список частей объектов (массивы (n, 3) на часть),
    geom - "point", "line" или "polygon", value - число на объект
    или None. Возвращает словарь кубов (nz, ny, nx): count, sum,
    mean (NaN, где объектов нет), length (у не-линий нули), и сводку:
    объектов всего, в сетке, длина линий всего и внутри.
    """
    total = int(lat.size.prod())
    count = np.zeros(total)
    vsum = np.zeros(total)
    vcnt = np.zeros(total)
    length = np.zeros(total)
    anchors, vals = [], []
    len_all = 0.0
    for k, parts in enumerate(objects):
        a = _anchor(geom, parts)
        if a is None or not np.isfinite(a).all():
            continue
        anchors.append(a)
        vals.append(np.nan if value is None or value[k] is None
                    else float(value[k]))
        if geom == "line":
            for p in parts:
                p = np.asarray(p, dtype=float).reshape(-1, 3)
                for s in range(len(p) - 1):
                    len_all += float(np.linalg.norm(p[s + 1] - p[s]))
                    idx, part = segment_cells(p[s], p[s + 1], lat)
                    if len(idx):
                        np.add.at(length, idx, part)
    n_obj = len(anchors)
    n_in = 0
    if anchors:
        ijk, ok = lat.index(np.vstack(anchors))
        flat = lat.flat(ijk[ok])
        n_in = int(ok.sum())
        np.add.at(count, flat, 1.0)
        v = np.asarray(vals)[ok]
        good = np.isfinite(v)
        np.add.at(vsum, flat[good], v[good])
        np.add.at(vcnt, flat[good], 1.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(vcnt > 0, vsum / np.maximum(vcnt, 1.0), np.nan)
    shape = lat.shape
    return ({"count": count.reshape(shape), "sum": vsum.reshape(shape),
             "mean": mean.reshape(shape), "length": length.reshape(shape)},
            {"objects": n_obj, "inside": n_in, "len_all": len_all,
             "len_in": float(length.sum())})
