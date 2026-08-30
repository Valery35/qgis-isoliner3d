# -*- coding: utf-8 -*-
#
# Isoliner - грид и изолинии (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
"""Мультисеточные B-сплайны (MBA): поверхность по разбросанным точкам.

Метод Ли, Волберга и Шина (1997). Идея простая. Берётся грубая решётка
контрольных точек, по ней строится кубический B-сплайн, приближающий
данные. Он приближает грубо, поэтому считается остаток - разность между
замером и текущей поверхностью, - решётка удваивается, и остаток
приближается заново. Так уровень за уровнем: каждый следующий подхватывает
то, что не смог предыдущий.

Чем он берёт. Система уравнений не решается вообще: коэффициент решётки
считается явно, взвешенной суммой по точкам, попавшим в носитель своего
сплайна. Поэтому работа линейна по числу точек, а память - по размеру
решётки. Кригинг на каждой ячейке решает систему по соседям, и на десятке
миллионов замеров это несопоставимые вещи.

Чего он не даёт. Ни ошибки оценки, ни модели ковариации, ни весов, которые
можно предъявить. Это аппроксиматор, а не оценщик: он не знает, насколько
хорош его ответ. Поэтому MBA идёт рядом с минимальной кривизной, а не
вместо кригинга, и особенно хорош как ТРЕНД, который дальше уточняют
кригингом остатков.

За пределами облака точек он экстраполирует произвольно: у краевых
коэффициентов нет данных, и поверхность там уходит куда угодно. Обрезка
области - забота вызывающей стороны.

Размерность не зашита. Решётка задаётся числом ячеек по каждой оси, и
двумерный случай отличается от трёхмерного только длиной этого списка.
Носитель кубического сплайна - окно 4 в каждой оси: 16 ячеек на плоскости,
64 в объёме.

Модуль не зависит от QGIS и проверяется тестами.
"""

import numpy as np

# Носитель кубического B-сплайна: четыре ячейки по каждой оси.
SUPPORT = 4


def _weights_1d(t):
    """Кубические B-сплайны в точке t внутри ячейки, t в [0, 1).

    Возвращает массив (4, n): вклад четырёх соседних контрольных точек.
    Сумма по четырём равна единице при любом t - это и есть разбиение
    единицы, на котором держится всё остальное.
    """
    t = np.asarray(t, dtype=np.float64)
    omt = 1.0 - t
    return np.stack([
        omt * omt * omt / 6.0,
        (3.0 * t * t * t - 6.0 * t * t + 4.0) / 6.0,
        (-3.0 * t * t * t + 3.0 * t * t + 3.0 * t + 1.0) / 6.0,
        t * t * t / 6.0,
    ])


def _offsets(ndim):
    """Все смещения носителя: (SUPPORT**ndim, ndim)."""
    grids = np.meshgrid(*([np.arange(SUPPORT)] * ndim), indexing="ij")
    return np.stack([g.ravel() for g in grids], axis=1)


class Lattice(object):
    """Решётка коэффициентов одного уровня.

    `lo` и `hi` - углы области, `n` - число ЯЧЕЕК по каждой оси. Контрольных
    точек на три больше по каждой оси: кубическому сплайну нужен запас по
    краям, иначе крайняя ячейка останется без носителя.
    """

    def __init__(self, lo, hi, n):
        self.lo = np.asarray(lo, dtype=np.float64)
        self.hi = np.asarray(hi, dtype=np.float64)
        self.n = np.asarray(n, dtype=np.int64)
        if np.any(self.n < 1):
            raise ValueError("Решётка должна иметь хотя бы одну ячейку.")
        if self.lo.shape != self.hi.shape or self.lo.shape != self.n.shape:
            raise ValueError("Размерности lo, hi и n должны совпадать.")
        self.ndim = int(self.lo.size)
        span = self.hi - self.lo
        span[span <= 0] = 1.0
        self.step = span / self.n
        self.shape = tuple(int(v) + 3 for v in self.n)
        self.coef = np.zeros(self.shape, dtype=np.float64)

    # --- служебное ---

    def _cells(self, pts):
        """Ячейка и доля внутри неё для каждой точки."""
        rel = (np.asarray(pts, dtype=np.float64) - self.lo) / self.step
        base = np.floor(rel).astype(np.int64)
        # точка на самом верхнем краю обязана попасть в последнюю ячейку,
        # иначе она вылетит за решётку и её вклад потеряется
        np.clip(base, 0, self.n - 1, out=base)
        frac = rel - base
        np.clip(frac, 0.0, 1.0, out=frac)
        return base, frac

    def _support(self, base, frac):
        """Индексы носителя и веса для каждой точки.

        Возвращает (idx, w): idx - плоские индексы в массиве коэффициентов,
        (m, SUPPORT**ndim); w - веса той же формы.
        """
        npts = base.shape[0]
        offs = _offsets(self.ndim)                       # (k, ndim)
        w1 = [_weights_1d(frac[:, d]) for d in range(self.ndim)]

        idx = np.zeros((npts, offs.shape[0]), dtype=np.int64)
        w = np.ones((npts, offs.shape[0]), dtype=np.float64)
        for d in range(self.ndim):
            take = base[:, d][:, None] + offs[None, :, d]
            idx = idx * self.shape[d] + take
            w = w * w1[d][offs[:, d], :].T
        return idx, w

    # --- построение и оценка ---

    def fit(self, pts, vals, batch=50000):
        """Считает коэффициенты по точкам и значениям.

        Правило из статьи: каждая точка раскладывает своё значение по
        носителю пропорционально квадрату веса, а коэффициент собирает
        приход со всех своих точек. Знаменатель - сумма квадратов весов:
        там, где точек нет, он ноль, и коэффициент остаётся нулевым.

        Считается порциями. Каждая точка разворачивается в шестьдесят
        четыре узла носителя, и на них заводится несколько массивов:
        миллион точек это два гигабайта разом, и QGIS падает раньше,
        чем NumPy успевает сказать «нет памяти». Порция ограничивает
        занятую память, а на ответ не влияет: суммы накапливаются.
        """
        pts = np.asarray(pts, dtype=np.float64)
        vals = np.asarray(vals, dtype=np.float64)
        if pts.ndim != 2 or pts.shape[1] != self.ndim:
            raise ValueError("Точки должны быть массивом (m, ndim).")
        if vals.shape[0] != pts.shape[0]:
            raise ValueError("Число значений и точек должно совпадать.")

        size = self.coef.size
        num = np.zeros(size, dtype=np.float64)
        den = np.zeros(size, dtype=np.float64)
        step = max(int(batch), 1)
        for start in range(0, len(pts), step):
            part = pts[start:start + step]
            pv = vals[start:start + step]
            base, frac = self._cells(part)
            idx, w = self._support(base, frac)
            w2 = w * w
            denom_pt = w2.sum(axis=1)
            denom_pt[denom_pt == 0.0] = 1.0
            # вклад точки в коэффициент: phi = w * v / sum(w^2)
            phi = w * (pv / denom_pt)[:, None]
            num += np.bincount(idx.ravel(),
                               weights=(w2 * phi).ravel(),
                               minlength=size)
            den += np.bincount(idx.ravel(), weights=w2.ravel(),
                               minlength=size)
        with np.errstate(invalid="ignore", divide="ignore"):
            c = np.where(den > 0, num / np.where(den > 0, den, 1.0), 0.0)
        self.coef = c.reshape(self.shape)
        return self

    def evaluate_axes(self, axes):
        """Значения на правильной сетке, по оси за раз.

        На такой сетке веса разделяются по осям: значение это
        произведение весов по X, по Y и по Z. Значит вместо того,
        чтобы для каждого узла собирать шестьдесят четыре соседа
        вразнобой, можно свернуть решётку по одной оси за раз.

        Ответ тот же до последнего знака, но работы много меньше:
        на кубе двести на двести на семьдесят это секунды вместо
        десятков секунд.
        """
        axes = [np.asarray(a, dtype=np.float64) for a in axes]
        if len(axes) != self.ndim:
            raise ValueError("Осей должно быть по числу измерений.")
        acc = self.coef
        for d in range(self.ndim):
            rel = (axes[d] - self.lo[d]) / self.step[d]
            base = np.floor(rel).astype(np.int64)
            np.clip(base, 0, self.n[d] - 1, out=base)
            frac = np.clip(rel - base, 0.0, 1.0)
            w1 = _weights_1d(frac)                # (SUPPORT, m)
            got = None
            for a in range(w1.shape[0]):
                part = np.take(acc, base + a, axis=d)
                sh = [1] * acc.ndim
                sh[d] = -1
                add = part * w1[a].reshape(sh)
                got = add if got is None else got + add
            acc = got
        return acc

    def evaluate(self, pts, batch=50000):
        """Значение поверхности в точках.

        Тоже порциями: оценка разворачивает те же шестьдесят четыре
        узла на точку, и на большом наборе её память больше, чем
        у самой подгонки - невязка по уровням считается по всем
        точкам сразу.
        """
        pts = np.asarray(pts, dtype=np.float64)
        if pts.ndim != 2 or pts.shape[1] != self.ndim:
            raise ValueError("Точки должны быть массивом (m, ndim).")
        flat = self.coef.ravel()
        out = np.empty(len(pts), dtype=np.float64)
        step = max(int(batch), 1)
        for start in range(0, len(pts), step):
            part = pts[start:start + step]
            base, frac = self._cells(part)
            idx, w = self._support(base, frac)
            out[start:start + step] = (flat[idx] * w).sum(axis=1)
        return out


def _trend_coefs(pts, vals, kind):
    """Тренд, снимаемый перед подгонкой. Множители при осях и свободный член.

    Коэффициент решётки считается формулой, линейной по значению:
    phi = w * v / sum(w^2). Значит и ошибка растёт вместе с ВЕЛИЧИНОЙ
    значения, а не с его разбросом. Там, где носитель односторонний -
    край области, дыра в данных, внутренность замкнутого обхода, -
    знаменатель мал, и коэффициент разлетается пропорционально самой
    отметке. На кровле около -250 м с разбросом в восемьдесят
    сантиметров поверхность уходила на четырнадцать метров, и числом
    уровней это не лечится: с третьего уровня ошибка не меняется вовсе.

    Снятый тренд оставляет решётке остаток около нуля. Та же подгонка
    на том же наборе даёт шесть сантиметров вместо четырнадцати метров.

    `kind`: None или "none" - не снимать, "mean" - среднее, "plane" -
    плоскость наименьшими квадратами. Плоскость на вырожденной сети
    (точек меньше, чем неизвестных, или все они на одной прямой)
    вырождается в среднее: подгонять наклон не по чему.
    """
    if kind is None:
        return None
    kind = str(kind).lower()
    if kind == "none":
        return None
    if kind not in ("mean", "plane"):
        raise ValueError("Снятие тренда бывает 'mean', 'plane' или None.")
    ndim = pts.shape[1]
    out = np.zeros(ndim + 1, dtype=np.float64)
    out[-1] = float(vals.mean())
    if kind == "mean" or len(pts) < ndim + 1:
        return out
    a = np.column_stack([pts, np.ones(len(pts))])
    coef, _res, rank, _sv = np.linalg.lstsq(a, vals, rcond=None)
    if rank < ndim + 1:
        return out
    return np.asarray(coef, dtype=np.float64)


def _trend_at(pts, tc):
    """Значение тренда в точках."""
    return pts @ tc[:-1] + tc[-1]


def _add_trend(lat, tc):
    """Вернуть снятый тренд внутрь решётки нулевого уровня.

    Решётка воспроизводит плоскость ТОЧНО, если коэффициент взять в его
    собственной точке: lo + (j - 1) * step по каждой оси. Поэтому тренд
    возвращается прямо в коэффициенты, и вызывающей стороне не надо
    помнить о нём ни при оценке, ни на гриде, ни в кубе.
    """
    add = np.full(lat.shape, tc[-1], dtype=np.float64)
    for d in range(lat.ndim):
        j = np.arange(lat.shape[d], dtype=np.float64)
        pos = lat.lo[d] + (j - 1.0) * lat.step[d]
        shape = [1] * lat.ndim
        shape[d] = lat.shape[d]
        add = add + tc[d] * pos.reshape(shape)
    lat.coef = lat.coef + add
    return lat


def fit(pts, vals, lo=None, hi=None, grid=(2, 2), levels=8, tol=None,
        progress=None, batch=50000, center=None):
    """Строит поверхность MBA и возвращает список решёток по уровням.

    `grid` - число ячеек начальной решётки по каждой оси. Оно и задаёт
    радиус влияния: чем крупнее ячейка, тем дальше расходится замер.
    Разные числа по осям дают анизотропию - на разведочной сети, вытянутой
    по простиранию, это то, что нужно.

    `levels` - сколько раз решётка удваивается. Каждый уровень вдвое
    подробнее и вдвое ближе к данным; мало уровней - гладкий тренд, много -
    поверхность проходит через замеры. Это и есть управление сглаживанием.

    `tol` - остановка по остатку: если наибольшая невязка стала меньше,
    дальше дробить нечего.

    `center` - снять ли тренд перед подгонкой: "plane", "mean" или None.
    Для отметок и вообще для величин, далёких от нуля, снимать надо:
    без этого ошибка масштабируется самой отметкой (см. `_trend_coefs`).
    По умолчанию не снимается, чтобы не менять молча поведение там,
    где на нём что-то построено.
    """
    pts = np.asarray(pts, dtype=np.float64)
    vals = np.asarray(vals, dtype=np.float64).ravel()
    if pts.ndim != 2:
        raise ValueError("Точки должны быть массивом (m, ndim).")
    if pts.shape[0] == 0:
        raise ValueError("Нет ни одной точки.")
    ndim = pts.shape[1]

    lo = pts.min(axis=0) if lo is None else np.asarray(lo, dtype=np.float64)
    hi = pts.max(axis=0) if hi is None else np.asarray(hi, dtype=np.float64)
    lo = np.asarray(lo, dtype=np.float64).copy()
    hi = np.asarray(hi, dtype=np.float64).copy()
    flat = hi <= lo
    if np.any(flat):                       # вырожденная ось: даём ей толщину
        hi[flat] = lo[flat] + 1.0

    grid = np.asarray(grid, dtype=np.int64)
    if grid.size == 1:
        grid = np.repeat(grid, ndim)
    if grid.size != ndim:
        raise ValueError("Размер начальной решётки должен быть по числу осей.")

    tc = _trend_coefs(pts, vals, center)

    lattices = []
    resid = vals.copy() if tc is None else vals - _trend_at(pts, tc)
    n = grid.copy()
    for lvl in range(max(1, int(levels))):
        lat = Lattice(lo, hi, n).fit(pts, resid, batch=batch)
        lattices.append(lat)
        resid = resid - lat.evaluate(pts, batch=batch)
        worst = float(np.max(np.abs(resid))) if resid.size else 0.0
        if progress is not None:
            progress(lvl, worst, tuple(int(v) for v in n))
        if tol is not None and worst <= float(tol):
            break
        n = n * 2
    if tc is not None:
        _add_trend(lattices[0], tc)
    return lattices


def evaluate(lattices, pts, batch=50000):
    """Сумма всех уровней в точках."""
    pts = np.asarray(pts, dtype=np.float64)
    out = np.zeros(pts.shape[0], dtype=np.float64)
    for lat in lattices:
        out += lat.evaluate(pts, batch=batch)
    return out


def evaluate_grid(lattices, axes):
    """Значения на прямоугольной сетке.

    `axes` - координаты узлов по каждой оси. Возвращает массив формы
    (len(axes[0]), len(axes[1]), ...). Точки строятся построчно, чтобы на
    большой сетке не держать в памяти весь список сразу.
    """
    axes = [np.asarray(a, dtype=np.float64) for a in axes]
    shape = tuple(a.size for a in axes)
    out = np.empty(shape, dtype=np.float64)
    if len(axes) == 1:
        return evaluate(lattices, axes[0][:, None])

    out = np.zeros(shape, dtype=np.float64)
    for lat in lattices:
        out += lat.evaluate_axes(axes)
    return out


def levels_report(lattices, pts, vals, batch=50000):
    """Невязка по уровням: чем каждый уровень помог.

    Нужна не для красоты. По ней видно, когда дробить пора прекратить:
    если очередной уровень почти не уменьшил невязку, дальше он ловит уже
    не структуру, а шум замеров.
    """
    pts = np.asarray(pts, dtype=np.float64)
    vals = np.asarray(vals, dtype=np.float64).ravel()
    out = []
    cur = np.zeros_like(vals)
    for lat in lattices:
        cur = cur + lat.evaluate(pts, batch=batch)
        d = vals - cur
        out.append({"cells": tuple(int(v) for v in lat.n),
                    "max": float(np.max(np.abs(d))) if d.size else 0.0,
                    "rms": float(np.sqrt(np.mean(d * d))) if d.size else 0.0})
    return out


def surface_on_grid(lattices, gt, nx, ny):
    """Поверхность на растровой сетке: массив (ny, nx), строка 0 - север.

    Отдельная функция, а не пара строк в инструменте, по одной причине:
    здесь легко перепутать порядок осей. Точки данных идут как (x, y), а
    растр адресуется как (строка, столбец), то есть (y, x). Подставив
    координаты в порядке строк, получаешь картинку, которая выглядит
    правдоподобно и при этом неверна везде - на неквадратной сетке она
    просто съезжает, а на квадратной оказывается зеркальной.

    `gt` - геопривязка GDAL: (x0, шаг_x, 0, y_верх, 0, -шаг_y). Значения
    берутся в ЦЕНТРАХ ячеек.
    """
    x0, dx, _rx, ytop, _ry, dy = [float(v) for v in gt]
    nx, ny = int(nx), int(ny)
    ax = x0 + dx * (np.arange(nx) + 0.5)
    ay = ytop + dy * (np.arange(ny) + 0.5)
    # оси передаются в порядке данных (x, y), результат разворачивается в
    # порядок растра (строка = y)
    return evaluate_grid(lattices, [ax, ay]).T


def volume_on_grid(lattices, gt, nx, ny, nz, z0, dz):
    """Куб значений на воксельной сетке: массив (nz, ny, nx).

    Отдельная функция в ядре, а не пара строк в инструменте, по той же
    причине, что и `surface_on_grid`: здесь легко перепутать порядок
    осей. Точки данных идут как (x, y, z), а куб адресуется как
    (уровень, строка, столбец). Подставив оси в порядке адресации,
    получишь куб, который выглядит правдоподобно и неверен везде, а на
    симметричной сетке ошибка вообще не видна.

    `gt` - геопривязка GDAL: (x0, шаг_x, 0, y_верх, 0, -шаг_y). Значения
    по плану берутся в ЦЕНТРАХ ячеек, по вертикали - на самих уровнях:
    так их пишут 2.02 и 2.06, и так их читает сцена.

    Уровень 0 это нижняя отметка `z0`, дальше вверх с шагом `dz`.
    """
    x0, dx, _rx, ytop, _ry, dy = [float(v) for v in gt]
    nx, ny, nz = int(nx), int(ny), int(nz)
    ax = x0 + dx * (np.arange(nx) + 0.5)
    ay = ytop + dy * (np.arange(ny) + 0.5)
    az = float(z0) + float(dz) * np.arange(nz)
    # оси передаются в порядке данных (x, y, z), результат
    # разворачивается в порядок куба (уровень, строка, столбец)
    return evaluate_grid(lattices, [ax, ay, az]).transpose(2, 1, 0)


def volume_memory(nx, ny, nz, levels):
    """Сколько байт займут решётки всех уровней.

    Память последнего уровня растёт кубом, и считать её надо ДО
    выделения: 256 по каждой оси это четверть гигабайта на уровень,
    512 - под два гигабайта, и туда идти не нужно.
    """
    total = 0
    gx, gy, gz = int(nx), int(ny), int(nz)
    for _k in range(max(int(levels), 1)):
        total += (gx + 3) * (gy + 3) * (gz + 3) * 8
        gx, gy, gz = gx * 2, gy * 2, gz * 2
    return total


def clamp_values(arr, lo=None, hi=None):
    """Прижать значения к заданным краям.

    Метод приближает, а за облаком точек уходит куда угодно: у краевых
    коэффициентов нет данных. Содержание при этом не бывает ниже нуля,
    и такой ответ надо поправить.

    Обрезка тупая: что вышло за край, встаёт на край, и на месте
    выброса получается плато - форма там теряется. Зато поправка
    предсказуема и видна: возвращается ещё и число прижатых узлов,
    и по нему судят, годится ли модель вообще.

    Пропуски остаются пропусками. Границы навстречу друг другу
    невыполнимы, и молчать об этом нельзя.
    """
    arr = np.asarray(arr, dtype=float)
    if lo is not None and hi is not None and float(lo) > float(hi):
        raise ValueError("Наименьшее значение больше наибольшего.")
    out = arr.copy()
    bad = np.zeros(out.shape, dtype=bool)
    if lo is not None:
        bad |= np.isfinite(out) & (out < float(lo))
        out = np.where(bad, float(lo), out)
    if hi is not None:
        over = np.isfinite(out) & (out > float(hi))
        bad |= over
        out = np.where(over, float(hi), out)
    return out, int(bad.sum())
