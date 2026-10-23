# -*- coding: utf-8 -*-
"""Линии трубами: меш трубы по ломаной и толщина по значению поля.

Экранная линия рисуется шириной в пиксели и одинакова при любом
удалении камеры, поэтому толщиной ничего не покажешь. Труба имеет
диаметр в метрах сцены: дальняя тоньше, ближняя толще, и значение
поля читается размером, как на карте шириной линии.

Труба собирается одним куском на ломаную, а не цилиндром на звено.
Цилиндры на изломе расходятся щелью снаружи и врезаются друг в друга
внутри. Здесь кольцо ставится в каждой вершине поперёк средней
касательной и растягивается в плоскости излома, чтобы стенка
сохраняла толщину. Кольца соседних вершин сшиваются, и стык выходит
без щели.

Поворот колец переносится от вершины к вершине (параллельный
перенос). Если строить каждое кольцо от своей опорной оси, на звене,
близком к этой оси, кольцо проворачивается, и стенка скручивается
жгутом.

Считается на голом NumPy, QGIS не нужен.
"""

import numpy as np

# растяжение кольца на изломе ограничено: на острой шпильке миттер
# уходит в бесконечность и протыкает соседние трубы
MAX_MITER = 3.0


def _clean(points, radius):
    """Убрать повторы вершин: у нулевого звена нет направления."""
    p = np.asarray(points, dtype=float).reshape(-1, 3)
    r = np.broadcast_to(np.asarray(radius, dtype=float),
                        (len(p),)).copy()
    if len(p) < 2:
        return p, r
    keep = np.ones(len(p), dtype=bool)
    d = np.linalg.norm(np.diff(p, axis=0), axis=1)
    keep[1:] = d > 1e-9 * max(1.0, float(np.abs(p).max()))
    return p[keep], r[keep]


def _frames(p):
    """Касательные и переносимая нормаль в каждой вершине."""
    seg = np.diff(p, axis=0)
    seg /= np.linalg.norm(seg, axis=1)[:, None]
    n = len(p)
    tan = np.empty((n, 3))
    tan[0], tan[-1] = seg[0], seg[-1]
    if n > 2:
        mid = seg[:-1] + seg[1:]
        ln = np.linalg.norm(mid, axis=1)
        # разворот на 180 градусов: средней касательной нет, берём
        # направление входящего звена
        bad = ln < 1e-9
        mid[bad] = seg[:-1][bad]
        ln[bad] = 1.0
        tan[1:-1] = mid / ln[:, None]
    # первая нормаль: перпендикуляр к касательной, ближе к вертикали
    # или к оси X, если звено само вертикально
    ref = np.array([0.0, 0.0, 1.0])
    if abs(float(tan[0] @ ref)) > 0.9:
        ref = np.array([1.0, 0.0, 0.0])
    nrm = np.empty((n, 3))
    v = ref - (ref @ tan[0]) * tan[0]
    nrm[0] = v / np.linalg.norm(v)
    for i in range(1, n):
        v = nrm[i - 1] - (nrm[i - 1] @ tan[i]) * tan[i]
        ln = np.linalg.norm(v)
        if ln < 1e-9:
            v = np.cross(tan[i], np.cross(nrm[i - 1], tan[i]))
            ln = max(np.linalg.norm(v), 1e-12)
        nrm[i] = v / ln
    bin_ = np.cross(tan, nrm)
    return seg, tan, nrm, bin_


def tube_mesh(points, radius, sides=10, caps=True):
    """Труба по ломаной: (вершины (M, 3), треугольники (K, 3)).

    `radius` - одно число или по числу на вершину. `sides` - граней
    по окружности. С `caps` концы закрыты торцами, и труба замкнута.
    Ломаная короче двух несовпадающих вершин даёт пустой меш.
    """
    p, r = _clean(points, radius)
    empty = (np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64))
    if len(p) < 2:
        return empty
    sides = max(3, int(sides))
    seg, tan, nrm, bin_ = _frames(p)
    ang = np.linspace(0.0, 2.0 * np.pi, sides, endpoint=False)
    ca, sa = np.cos(ang), np.sin(ang)
    n = len(p)
    # растяжение на изломе: вдоль направления излома кольцо длиннее
    # в 1/cos(половины угла), поперёк остаётся радиусом
    stretch = np.ones(n)
    bend = np.zeros((n, 3))
    if n > 2:
        cos_half = np.clip(np.einsum("ij,ij->i", seg[:-1], tan[1:-1]),
                           1.0 / MAX_MITER, 1.0)
        stretch[1:-1] = 1.0 / cos_half
        b = seg[1:] - seg[:-1]
        b -= np.einsum("ij,ij->i", b, tan[1:-1])[:, None] * tan[1:-1]
        ln = np.linalg.norm(b, axis=1)
        ok = ln > 1e-9
        bend[1:-1][ok] = b[ok] / ln[ok][:, None]
    off = (ca[None, :, None] * nrm[:, None, :]
           + sa[None, :, None] * bin_[:, None, :])
    along = np.einsum("ijk,ik->ij", off, bend)
    off = off + ((stretch - 1.0)[:, None, None] * along[:, :, None]
                 * bend[:, None, :])
    verts = (p[:, None, :] + r[:, None, None] * off).reshape(-1, 3)
    i = np.arange(n - 1)[:, None] * sides
    j = np.arange(sides)[None, :]
    j1 = (j + 1) % sides
    a, b_ = i + j, i + j1
    c, d = a + sides, b_ + sides
    faces = np.concatenate([np.stack([a, b_, d], -1).reshape(-1, 3),
                            np.stack([a, d, c], -1).reshape(-1, 3)])
    if caps:
        c0 = len(verts)
        c1 = c0 + 1
        verts = np.vstack([verts, p[0], p[-1]])
        k = np.arange(sides)
        k1 = (k + 1) % sides
        last = (n - 1) * sides
        start = np.stack([np.full(sides, c0), k1, k], -1)
        end = np.stack([np.full(sides, c1), last + k, last + k1], -1)
        faces = np.concatenate([faces, start, end])
    return verts, faces.astype(np.int64)


def many_tubes(lines, radii, sides=10, caps=True):
    """Трубы многих линий одним мешем.

    Возвращает (вершины, треугольники, номер линии у каждой вершины).
    По номеру раскрашиваются вершины: цвет и прозрачность у каждой
    линии свои, а меш один - элемент сцены на линию стоил бы набора
    буферов на каждую из тысяч линий.
    """
    vs, fs, own = [], [], []
    base = 0
    for k, (pts, rad) in enumerate(zip(lines, radii)):
        v, f = tube_mesh(pts, rad, sides=sides, caps=caps)
        if not len(f):
            continue
        vs.append(v)
        fs.append(f + base)
        own.append(np.full(len(v), k, dtype=np.int64))
        base += len(v)
    if not vs:
        return (np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64),
                np.zeros(0, dtype=np.int64))
    return np.vstack(vs), np.vstack(fs), np.concatenate(own)


def value_to_diameter(values, dmin, dmax, scale="area", vmin=None,
                      vmax=None):
    """Значения поля в диаметры трубы, метры.

    Наименьшее значение даёт `dmin`, наибольшее `dmax`. Со `scale`
    "area" пропорциональна значению площадь сечения, а не диаметр:
    глаз читает толщину трубы площадью, и при линейном диаметре
    большие значения забивают картинку. "linear" - пропорционален
    диаметр.

    Пустые и нечисловые значения получают `dmin`: труба остаётся
    видна, но не притворяется большой. Если все значения равны,
    все трубы получают `dmax`.
    """
    v = np.asarray(values, dtype=float).ravel()
    dmin, dmax = float(dmin), float(dmax)
    out = np.full(len(v), dmin)
    ok = np.isfinite(v)
    if not ok.any():
        return out
    lo = float(np.nanmin(v[ok])) if vmin is None else float(vmin)
    hi = float(np.nanmax(v[ok])) if vmax is None else float(vmax)
    if hi <= lo:
        out[ok] = dmax
        return out
    t = np.clip((v[ok] - lo) / (hi - lo), 0.0, 1.0)
    if scale == "linear":
        out[ok] = dmin + t * (dmax - dmin)
    else:
        out[ok] = np.sqrt(dmin * dmin + t * (dmax * dmax - dmin * dmin))
    return out


def sides_for(n_vertices, budget, most=12, least=4):
    """Граней по окружности, чтобы меш уложился в бюджет вершин.

    На тысячах изолиний по сотне вершин двенадцать граней дают
    миллионы вершин и сцену, которая не вращается. Тогда граней
    меньше: на таком удалении труба и так читается цилиндром.
    """
    n = max(int(n_vertices), 1)
    s = int(budget // n)
    return int(min(max(s, least), most))
