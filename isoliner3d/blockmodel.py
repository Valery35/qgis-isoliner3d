# -*- coding: utf-8 -*-
"""Блочная модель в куб: блоки любых размеров в регулярные ячейки.

Блочная модель из Micromine, Datamine или Surpac - таблица блоков:
центр, размер, значения. Куб модуля - регулярная решётка, канал на
уровень (конвенция 2.02: уровень k с центром на z0 + k * dz). Чтобы
по блочной модели строить оболочки, тела вокселей и разрезы, её надо
положить на решётку.

Блоки бывают одного размера, и тогда блок и есть ячейка. Бывают
подблоки: у контакта рудного тела блок дробится на мелкие. Тогда
ячейка куба берёт значение, среднее по объёму пересечения с каждым
блоком. Так подсчёт металла по кубу совпадает с подсчётом по блокам,
а не завышается мелкими богатыми подблоками.

Ячейка, покрытая блоками меньше чем на долю `min_cover`, остаётся
пустой: край модели не размазывается по ячейке, где блок задел лишь
угол.

Модель с поворотом (азимут осей блоков не по сетке) сюда не годится:
перед расчётом её надо развернуть в систему координат блоков.

Считается на голом NumPy, QGIS не нужен.
"""

import numpy as np

# сочетаний сдвигов по трём осям на один прогон: блок в десятки ячеек
# по каждой оси дал бы миллионы проходов
MAX_SPAN_COMBOS = 8192


def infer_step(coords, decimals=6):
    """Шаг решётки по координатам центров: наименьший разнос соседних.

    Подблоки дают и полшага, и четверть: наименьший разнос тогда
    и есть шаг, которым они все ложатся на решётку.
    """
    u = np.unique(np.round(np.asarray(coords, dtype=float), decimals))
    if len(u) < 2:
        return None
    d = np.diff(u)
    d = d[d > 10.0 ** (-decimals + 1)]
    return float(d.min()) if len(d) else None


def block_steps(x, y, z, sx=None, sy=None, sz=None):
    """Шаг по трём осям: наименьший размер блока или разнос центров."""
    steps = []
    for c, s in ((x, sx), (y, sy), (z, sz)):
        s = None if s is None else np.asarray(s, dtype=float)
        if s is not None and (np.isfinite(s) & (s > 0)).any():
            steps.append(float(s[np.isfinite(s) & (s > 0)].min()))
        else:
            st = infer_step(c)
            steps.append(st if st else 1.0)
    return steps


def _sizes(c, s, step):
    """Размеры блоков по оси: из поля или шаг решётки."""
    if s is None:
        return np.full(len(c), float(step))
    s = np.asarray(s, dtype=float)
    bad = ~np.isfinite(s) | (s <= 0)
    if bad.any():
        s = s.copy()
        s[bad] = float(step)
    return s


def blocks_to_cube(x, y, z, values, sx=None, sy=None, sz=None, cell=None,
                   min_cover=0.5):
    """Блоки в куб.

    `values` - (N,) или (N, K). `sx, sy, sz` - размеры блоков или None:
    тогда блок занимает шаг решётки, найденный по центрам. `cell` -
    (cx, cy, cz) или None: тогда ячейка - наименьший размер блока по
    каждой оси.

    Возвращает словарь: `vol` (K, nz, ny, nx) значения, `cover`
    (nz, ny, nx) покрытая блоками доля ячейки, `gt` геопривязка
    (x0, cx, 0, y1, 0, -cy), `z0` центр нижнего уровня, `dz` шаг по
    вертикали, `n_multi` блоков, легших больше чем на одну ячейку.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    z = np.asarray(z, dtype=float)
    v = np.asarray(values, dtype=float)
    if v.ndim == 1:
        v = v[:, None]
    ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    x, y, z, v = x[ok], y[ok], z[ok], v[ok]
    if sx is not None:
        sx = np.asarray(sx, dtype=float)[ok]
    if sy is not None:
        sy = np.asarray(sy, dtype=float)[ok]
    if sz is not None:
        sz = np.asarray(sz, dtype=float)[ok]
    if not len(x):
        raise ValueError("нет блоков с координатами")
    steps = block_steps(x, y, z, sx, sy, sz)
    sx = _sizes(x, sx, steps[0])
    sy = _sizes(y, sy, steps[1])
    sz = _sizes(z, sz, steps[2])
    cx, cy, cz = (float(a) for a in (cell if cell else steps))
    if min(cx, cy, cz) <= 0:
        raise ValueError("размер ячейки должен быть больше нуля")

    xl, xh = x - sx / 2.0, x + sx / 2.0
    yl, yh = y - sy / 2.0, y + sy / 2.0
    zl, zh = z - sz / 2.0, z + sz / 2.0
    x0, y1, zb = float(xl.min()), float(yh.max()), float(zl.min())
    eps = 1e-6
    nx = max(int(np.ceil((xh.max() - x0) / cx - eps)), 1)
    ny = max(int(np.ceil((y1 - yl.min()) / cy - eps)), 1)
    nz = max(int(np.ceil((zh.max() - zb) / cz - eps)), 1)

    # по каждой оси: первая ячейка блока и число ячеек под ним;
    # по Y ряды идут сверху вниз, как у растра
    def span(lo, hi, origin, step, n, down=False):
        a = (origin - hi) / step if down else (lo - origin) / step
        b = (origin - lo) / step if down else (hi - origin) / step
        i0 = np.clip(np.floor(a + eps).astype(np.int64), 0, n - 1)
        i1 = np.clip(np.ceil(b - eps).astype(np.int64), i0 + 1, n)
        return i0, i1 - i0

    ix, nxs = span(xl, xh, x0, cx, nx)
    iy, nys = span(yl, yh, y1, cy, ny, down=True)
    iz, nzs = span(zl, zh, zb, cz, nz)
    mx, my, mz = int(nxs.max()), int(nys.max()), int(nzs.max())
    if mx * my * mz > MAX_SPAN_COMBOS:
        raise ValueError(
            "блок накрывает %d x %d x %d ячеек: ячейка слишком мелкая "
            "для этих блоков" % (mx, my, mz))

    def overlap(lo, hi, idx, origin, step, down=False):
        if down:
            top = origin - idx * step
            return np.minimum(hi, top) - np.maximum(lo, top - step)
        left = origin + idx * step
        return np.minimum(hi, left + step) - np.maximum(lo, left)

    k = v.shape[1]
    n_cells = nz * ny * nx
    w_all = np.zeros(n_cells)
    w_val = np.zeros((k, n_cells))
    s_val = np.zeros((k, n_cells))
    fin = np.isfinite(v)
    v0 = np.where(fin, v, 0.0)
    for oz in range(mz):
        mzk = oz < nzs
        for oy in range(my):
            myk = mzk & (oy < nys)
            for ox in range(mx):
                m = myk & (ox < nxs)
                if not m.any():
                    continue
                jx, jy, jz = ix[m] + ox, iy[m] + oy, iz[m] + oz
                w = (overlap(xl[m], xh[m], jx, x0, cx)
                     * overlap(yl[m], yh[m], jy, y1, cy, down=True)
                     * overlap(zl[m], zh[m], jz, zb, cz))
                w = np.maximum(w, 0.0)
                flat = (jz * ny + jy) * nx + jx
                np.add.at(w_all, flat, w)
                for q in range(k):
                    wq = w * fin[m, q]
                    np.add.at(w_val[q], flat, wq)
                    np.add.at(s_val[q], flat, wq * v0[m, q])
    cell_vol = cx * cy * cz
    cover = np.minimum(w_all / cell_vol, 1.0)
    vol = np.full((k, n_cells), np.nan)
    keep = cover >= min_cover - 1e-9
    for q in range(k):
        good = keep & (w_val[q] > 0)
        vol[q, good] = s_val[q, good] / w_val[q, good]
    return {
        "vol": vol.reshape(k, nz, ny, nx),
        "cover": cover.reshape(nz, ny, nx),
        "gt": (x0, cx, 0.0, y1, 0.0, -cy),
        "z0": zb + cz / 2.0,
        "dz": cz,
        "n_multi": int(((nxs * nys * nzs) > 1).sum()),
        "n_blocks": int(len(x)),
    }


def cube_metal(vol, cover, gt, dz):
    """Сумма значение x объём по кубу: сверка с суммой по блокам."""
    cv = abs(gt[1] * gt[5] * dz)
    f = np.isfinite(vol)
    return float((np.where(f, vol, 0.0) * cover).sum() * cv)
