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


def auto_grid(dz, dxy, per):
    """Умолчания сетки, снятые с самой сети опробования.

    Постоянные умолчания не подходят никому: на почвенных пробах через
    триста метров шаг в двадцать пять метров даёт сетку мельче данных,
    а на площадке в двадцать семь километров те же двадцать пять метров
    дают сорок пять миллионов узлов. Оба раза это не выбор человека,
    а умолчание, и промах виден только по результату.

    Шаг в плане берётся пятой частью расстояния между точками плана:
    мельче данных в промежутке всё равно нет. Шаг по вертикали
    половина шага опробования, иначе соседние уровни сливаются.
    Соседей берётся на одного больше, чем замеров в одной точке плана:
    больше значит смешать уровни и сгладить различие по глубине.

    Возвращает None, если сеть замерить не удалось.
    """
    if dz is None or dxy is None or per is None:
        return None
    cell = float(dxy) / 5.0
    if cell >= 10.0:
        cell = round(cell / 10.0) * 10.0
    cellz = max(float(dz) / 2.0, 0.01)
    pts = int(per) + 1
    return {"cell": max(cell, 0.01),
            "cellz": cellz,
            "max_points": max(min(pts, 16), 4)}


NODE_LIMIT = 20 * 10 ** 6


def grid_advice(nx, ny, nz, cell, dxy=None, limit=NODE_LIMIT):
    """Что сказать про заданную сетку до начала счёта.

    Узел считается по всем соседям, поэтому время растёт вместе с их
    числом, а не с размером площадки. Сетка мельче сети опробования
    данных не добавляет: между соседними точками плана нет ни одного
    замера, и лишние узлы повторяют одно и то же.

    Возвращает список готовых замечаний, пустой список означает,
    что сетка соразмерна данным.
    """
    nodes = int(nx) * int(ny) * int(nz)
    out = []
    if nodes > int(limit):
        out.append("узлов %d, это больше предела %d: счёт займёт "
                   "минуты и займёт сотни мегабайт" % (nodes, int(limit)))
    if dxy and cell > 0:
        per = float(dxy) / float(cell)
        if per > 50:
            out.append("между соседними точками плана %d ячеек, "
                       "данных между ними нет: шаг мельче сети "
                       "опробования" % int(round(per)))
    return out


def sampling_spacing(points, decimals=1):
    """Как устроена сеть опробования: (шаг по вертикали, шаг в плане,
    замеров в одной точке плана).

    Числа нужны для выбора анизотропии, но подсказать значение по ним
    нельзя: у скважин и у проб по уровням отношение шагов почти
    одинаковое, а нужные значения различаются в тысячу раз. Различает
    их число замеров в одной точке плана: у скважины их десятки,
    у почвенной пробы три. Поэтому инструмент печатает измеренное,
    а решение остаётся за геологом.

    Возвращает None, если повторов в плане нет и мерить нечего.
    """
    pts = np.asarray(points, dtype=float)
    if len(pts) < 4:
        return None
    key = np.round(pts[:, :2], int(decimals))
    uniq, inv = np.unique(key, axis=0, return_inverse=True)
    if len(uniq) < 2 or len(uniq) == len(pts):
        return None
    steps, per = [], []
    for k in range(len(uniq)):
        z = np.sort(pts[inv == k, 2])
        per.append(len(z))
        if len(z) > 1:
            steps.extend(v for v in np.diff(z) if v > 0)
    if not steps:
        return None
    d2 = ((uniq[:, None, :] - uniq[None, :, :]) ** 2).sum(axis=2)
    np.fill_diagonal(d2, np.inf)
    return (float(np.median(steps)),
            float(np.median(np.sqrt(d2.min(axis=1)))),
            int(np.median(per)))


Z_SOURCES = ("geom", "field", "depth")


def resolve_z(mode, gz=None, fz=None, surf=None, depth=None):
    """Отметка точек по выбранному источнику.

    Плоский слой отдаёт нулевую Z у каждой точки, и брать её как есть
    нельзя: все пробы легли бы в одну плоскость. Поэтому источник
    задаётся явно.

    `geom` берёт отметку из геометрии, `field` из поля, `depth`
    отсчитывает глубину вниз от поверхности. Последнее нужно почвенным
    и подобным пробам: там записана глубина, а не отметка, и без
    поверхности перевести одно в другое нельзя.

    Точка, для которой отметку получить не удалось, возвращается
    пропуском и в расчёт не идёт.
    """
    if mode not in Z_SOURCES:
        raise ValueError("неизвестный источник отметки: %r" % (mode,))
    if mode == "geom":
        return np.asarray(gz, dtype=float)
    if mode == "field":
        return np.asarray(fz, dtype=float)
    s_ = np.asarray(surf, dtype=float)
    d_ = np.asarray(depth, dtype=float)
    return s_ - d_


def _sector_take(blk, pts, d2, kmax, sectors):
    """Отбор соседей по секторам вокруг узла.

    Без секторов при анизотропии все ближайшие точки набираются из
    одной скважины: проба в стволе в сотни раз ближе соседней скважины.
    Веса тогда считаются по одному значению, и обратные расстояния
    вырождаются в ближайшего соседа.

    Площадь делится на сектора по азимуту, из каждого берётся своя доля
    ближайших. Возвращает столбцы номеров точек, пустое место помечено
    номером минус один.
    """
    sectors = max(int(sectors), 1)
    if sectors == 1:
        if kmax and kmax < pts.shape[0]:
            return np.argpartition(d2, kmax - 1, axis=1)[:, :kmax]
        return np.argsort(d2, axis=1)
    per = max(int(kmax) // sectors, 1) if kmax else 1
    dx = blk[:, 0][:, None] - pts[None, :, 0]
    dy = blk[:, 1][:, None] - pts[None, :, 1]
    ang = np.arctan2(dy, dx)
    sec = np.floor((ang + np.pi) / (2 * np.pi) * sectors).astype(np.int64)
    np.clip(sec, 0, sectors - 1, out=sec)
    # Составляющие азимута больше не нужны: держать их рядом с копиями
    # по секторам значило бы удваивать память на пустом месте.
    del dx, dy, ang
    parts = []
    for k in range(sectors):
        ds = np.where(sec == k, d2, np.inf)
        if per < ds.shape[1]:
            idx = np.argpartition(ds, per - 1, axis=1)[:, :per]
        else:
            idx = np.argsort(ds, axis=1)[:, :per]
        rows = np.arange(ds.shape[0])[:, None]
        # Пустой сектор помечаем минус единицей, чтобы он не тянул
        # в среднее случайную точку с другой стороны узла.
        parts.append(np.where(np.isfinite(ds[rows, idx]), idx, -1))
    return np.concatenate(parts, axis=1)


def neighbour_ids(points, grid, radius=None, anisotropy=1.0,
                  max_points=16, sectors=8):
    """Номера точек, которые узел берёт в расчёт.

    Отдельная функция нужна проверкам: по ней видно, из скольких
    скважин набраны соседи, а по одному значению в узле этого
    не увидеть.
    """
    pts = np.asarray(points, dtype=float).copy()
    nodes = np.asarray(grid, dtype=float).copy()
    aniso = float(anisotropy) or 1.0
    pts[:, 2] /= aniso
    nodes[:, 2] /= aniso
    if radius is None or radius <= 0:
        span = np.ptp(pts, axis=0)
        radius = float(max(span.max(), 1.0)) / 4.0
    d2 = ((nodes[:, None, :] - pts[None, :, :]) ** 2).sum(axis=2)
    d2 = np.where(d2 <= float(radius) ** 2, d2, np.inf)
    return _sector_take(nodes, pts, d2, int(max_points), int(sectors))


def _dense(pts, val, nodes, r2, method, power, max_points, min_points,
           sectors=8):
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
        take = _sector_take(blk, pts, d2, kmax, sectors)
        rows = np.arange(b - a)[:, None]
        empty = take < 0
        safe = np.where(empty, 0, take)
        dsel = np.where(empty, np.inf, d2[rows, safe])
        vsel = val[safe]
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
                anisotropy=1.0, power=2.0, max_points=16, min_points=1,
                sectors=8, vmodel=None):
    """Значения в узлах сетки по точкам.

    `points` это (N, 3) в координатах карты, `grid` это (M, 3) узлы,
    `anisotropy` отношение вертикального масштаба к горизонтальному.

    Узлы, где точек в радиусе меньше `min_points`, остаются пропуском:
    пустота лучше выдуманного значения.

    `sectors` делит окружность вокруг узла на равные части, и из каждой
    берётся своя доля ближайших точек. Единица отключает деление
    и возвращает прежний отбор просто по расстоянию.

    Метод `kriging` требует модели вариограммы в `vmodel` и считается
    отдельным модулем: там своя система на каждый узел, а здесь только
    развилка, чтобы проверка исключением работала со всеми методами
    одинаково.
    """
    if method == "kriging":
        if not vmodel:
            raise ValueError("кригингу нужна модель вариограммы")
        from .kriging import ordinary
        est, _var = ordinary(points, values, grid, vmodel, radius=radius,
                             max_points=max_points, sectors=sectors,
                             anisotropy=anisotropy)
        return est
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
                      int(max_points), int(min_points), int(sectors))

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
            take = _sector_take(node[None, :], pts[cand], d2[None, :],
                                int(max_points), int(sectors))[0]
            keep = np.unique(take[take >= 0])
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


def cv_report(residuals, values):
    """Сводка по невязкам проверки с исключением по одной.

    Средняя ошибка сама по себе мало что говорит: единица это много
    на содержаниях от нуля до двух и мало на содержаниях от нуля
    до ста. Поэтому рядом идёт её доля от размаха данных.

    Смещение показывает, уводит ли модель в одну сторону: положительное
    значит завышает. Ошибку без смещения глазом не отличить
    от разброса, а лечится она по-разному.
    """
    res = np.asarray(residuals, dtype=float)
    val = np.asarray(values, dtype=float)
    ok = np.isfinite(res)
    n = int(ok.sum())
    if not n:
        nan = float("nan")
        return {"n": 0, "mae": nan, "rmse": nan, "bias": nan,
                "mae_share": nan, "spread": nan}
    r = res[ok]
    good = np.isfinite(val)
    spread = float(np.ptp(val[good])) if good.any() else 0.0
    mae = float(np.mean(np.abs(r)))
    return {"n": n,
            "mae": mae,
            "rmse": float(np.sqrt(np.mean(r ** 2))),
            "bias": float(np.mean(r)),
            "spread": spread,
            "mae_share": mae / spread if spread > 0 else float("nan")}


def cross_validate(points, values, method="idw", groups=None, **kw):
    """Проверка с исключением: по одной пробе или по группе целиком.

    Возвращает (остатки, средняя ошибка, среднеквадратичная). Без неё
    сравнивать методы нельзя: у обратных расстояний степень и радиус
    подбираются, и подбирать надо по числам.

    `groups` задаёт, что убирать за раз. Без него убирается одна проба,
    и на разведочной сети это льстит модели: соседей она берёт из того же
    ствола в трёх метрах, то есть меряется связность по стволу, а не
    умение попасть между скважинами. Подав номер скважины, убираем ствол
    целиком, и проверка отвечает уже на нужный вопрос.
    """
    pts = np.asarray(points, dtype=float)
    val = np.asarray(values, dtype=float)
    res = np.full(len(pts), np.nan)
    if groups is None:
        keys = np.arange(len(pts))
    else:
        keys = np.asarray(groups)
    for key in np.unique(keys):
        out = keys == key
        if out.all():
            continue
        got = interpolate(pts[~out], val[~out], pts[out],
                          method=method, **kw)
        res[out] = got - val[out]
    ok = np.isfinite(res)
    if not ok.any():
        return res, float("nan"), float("nan")
    return (res, float(np.mean(np.abs(res[ok]))),
            float(np.sqrt(np.mean(res[ok] ** 2))))
