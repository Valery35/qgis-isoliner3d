# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Обычный кригинг в объёме.

Обратные расстояния взвешивают по одному расстоянию: им всё равно,
на каком расстоянии связь пропадает и сколько разброса приходится
на ошибку опробования. Кригинг берёт веса из вариограммы, поэтому знает
и то, и другое.

Два свойства отличают его от взвешивания. Веса учитывают, что соседи
знают друг про друга: две пробы рядом друг с другом несут почти одно
и то же, и кригинг не даёт им двойного голоса. И он выдаёт дисперсию
оценки, то есть карту доверия: где данных нет, там она растёт, и это
видно сразу, а не после проверки.

Считается на голом NumPy, QGIS здесь не нужен.
"""

import numpy as np

from .variogram import model as vgm
from .interp3d import _sector_take


# Потолок по ячейкам временных матриц. Отбор соседей держит их
# несколько штук размером блок на число проб, и постоянный блок при
# больших выборках съедал память: на сорока тысячах проб выходило около
# гигабайта, а в фоновом потоке Windows это кончалось не ошибкой памяти,
# а падением.
BLOCK_CELLS = 2 * 10 ** 6


def block_for(n_points, block, cells=BLOCK_CELLS):
    """Сколько узлов брать за раз при таком числе проб."""
    n = max(int(n_points), 1)
    return max(min(int(block), int(cells) // n), 1)


def _prep(points, grid, anisotropy):
    """Координаты в масштабе расчёта: вертикаль сжимается."""
    pts = np.asarray(points, dtype=float).copy()
    nodes = np.asarray(grid, dtype=float).copy()
    a = float(anisotropy) or 1.0
    pts[:, 2] /= a
    nodes[:, 2] /= a
    return pts, nodes


def _gamma(h, vm):
    return vgm(h, vm.get("nugget", 0.0), vm.get("sill", 1.0),
               vm.get("range", 1.0), vm.get("kind", "spherical"))


def weights(points, grid, vmodel, radius=None, max_points=16, sectors=8,
            anisotropy=1.0, block=512):
    """Веса кригинга и множитель Лагранжа для каждого узла.

    Возвращает (веса, множитель, номера соседей). У пустого места
    в наборе соседей номер минус один, вес там не считается.

    Система строится на вариограмме: слева попарные значения между
    соседями, справа значения между соседями и узлом, плюс строка
    и столбец единиц. Единицы и есть условие несмещённости: сумма
    весов равна единице.
    """
    pts, nodes = _prep(points, grid, anisotropy)
    n = len(nodes)
    if radius is None or float(radius) <= 0:
        span = np.ptp(pts, axis=0)
        radius = float(max(span.max(), 1.0)) / 4.0
    r2 = float(radius) ** 2
    kmax = max(int(max_points), 1)
    sec_n = max(int(sectors), 1)
    # Ширину набора соседей считаем заранее: отбор по секторам берёт
    # свою долю из каждого, и всего выходит секторов на долю.
    k = sec_n if sec_n > 1 else kmax
    if sec_n > 1:
        k = sec_n * max(kmax // sec_n, 1)
    out_w = np.full((n, k), np.nan)
    out_mu = np.full(n, np.nan)
    out_idx = np.full((n, k), -1, dtype=np.int64)
    step = block_for(len(pts), block)

    for a in range(0, n, step):
        b = min(a + step, n)
        blk = nodes[a:b]
        d2 = ((blk[:, None, :] - pts[None, :, :]) ** 2).sum(axis=2)
        d2 = np.where(d2 <= r2, d2, np.inf)
        take = _sector_take(blk, pts, d2, kmax, sec_n)
        if take.shape[1] != k:
            # Ширина разошлась с ожидаемой: подгоняем, не сбрасывая
            # уже посчитанные блоки.
            fix = np.full((take.shape[0], k), -1, dtype=np.int64)
            m = min(k, take.shape[1])
            fix[:, :m] = take[:, :m]
            take = fix
        out_idx[a:b] = take
        safe = np.where(take < 0, 0, take)
        good = take >= 0

        # правая часть: вариограмма между узлом и каждым соседом
        rows = np.arange(b - a)[:, None]
        d0 = np.sqrt(np.where(good, d2[rows, safe], 0.0))
        g0 = np.where(good, _gamma(d0, vmodel), 0.0)

        # левая часть: вариограмма между соседями
        p = pts[safe]
        dd = np.sqrt(((p[:, :, None, :] - p[:, None, :, :]) ** 2).sum(-1))
        G = _gamma(dd, vmodel)
        # Пустое место в наборе соседей выключается: единица на диагонали
        # и ноль в строке дают этому весу ровно ноль.
        pair = good[:, :, None] & good[:, None, :]
        G = np.where(pair, G, 0.0)
        diag = np.arange(k)
        G[:, diag, diag] = np.where(good, 0.0, 1.0)

        A = np.zeros((b - a, k + 1, k + 1))
        A[:, :k, :k] = G
        A[:, :k, k] = np.where(good, 1.0, 0.0)
        A[:, k, :k] = np.where(good, 1.0, 0.0)
        rhs = np.zeros((b - a, k + 1))
        rhs[:, :k] = g0
        rhs[:, k] = 1.0
        empty = ~good.any(axis=1)
        # Узел без соседей: ставим единичную систему, ответ всё равно
        # выбрасывается ниже.
        A[empty] = np.eye(k + 1)
        try:
            sol = np.linalg.solve(A, rhs[..., None])[..., 0]
        except np.linalg.LinAlgError:
            sol = np.full((b - a, k + 1), np.nan)
        w = np.where(good, sol[:, :k], np.nan)
        w[empty] = np.nan
        out_w[a:b] = w
        mu = sol[:, k]
        mu[empty] = np.nan
        out_mu[a:b] = mu
    return out_w, out_mu, out_idx


def ordinary(points, values, grid, vmodel, radius=None, max_points=16,
             sectors=8, anisotropy=1.0, block=512):
    """Оценка кригингом и дисперсия оценки.

    Возвращает (значения в узлах, дисперсия). Узел, вокруг которого
    соседей не нашлось, остаётся пропуском: пустота лучше выдуманного
    значения, и дисперсия там тоже пропуск, а не ноль.

    Дисперсия считается как сумма весов на вариограмму до узла плюс
    множитель Лагранжа. В самой пробе она обращается в ноль: там ничего
    не гадается.
    """
    val = np.asarray(values, dtype=float)
    w, mu, idx = weights(points, grid, vmodel, radius=radius,
                         max_points=max_points, sectors=sectors,
                         anisotropy=anisotropy, block=block)
    good = idx >= 0
    safe = np.where(good, idx, 0)
    est = np.where(good, w * val[safe], 0.0).sum(axis=1)

    pts, nodes = _prep(points, grid, anisotropy)
    # Расстояние от узла до каждого его соседа: узел разворачивается
    # по оси соседей, поэтому явный None вместо среза.
    d0 = np.sqrt(((nodes[:, None, :] - pts[safe]) ** 2).sum(axis=2))
    g0 = np.where(good, _gamma(d0, vmodel), 0.0)
    var = np.where(good, w * g0, 0.0).sum(axis=1) + mu

    bad = ~good.any(axis=1) | ~np.isfinite(mu)
    est = np.where(bad, np.nan, est)
    var = np.where(bad, np.nan, np.maximum(var, 0.0))
    return est, var
