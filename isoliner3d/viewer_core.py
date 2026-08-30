# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Расчётная часть окна просмотра: всё, что считается без Qt и QGIS.

Окно жило одним файлом на шесть тысяч строк, и правки в нём промахивались
мимо: замена по образцу находила не тот кусок и уезжала в соседнюю
функцию. Здесь лежит то, что от окна не зависит вовсе - чтение растров
и их кэш, кэш триангуляции, шкалы и цвета, бюджет вершин, отбор
по отметке, плоские значки точек, порядок слоёв карты.

Отдельный модуль полезен и проверкам: раньше они вырезали кусок
исходника текстом и выполняли его, потому что импорт окна тянет QGIS.
Отсюда всё это просто импортируется.
"""

import os

_CMAP = [(0.267, 0.005, 0.329), (0.229, 0.322, 0.546),
         (0.128, 0.567, 0.551), (0.369, 0.789, 0.383),
         (0.993, 0.906, 0.144)]


def colormap(t):
    """t в [0..1] (массив) -> RGBA (N, 4). NaN -> серый."""
    import numpy as np
    t = np.asarray(t, dtype=float)
    out = np.empty(t.shape + (4,))
    bad = ~np.isfinite(t)
    tt = np.clip(np.where(bad, 0.0, t), 0.0, 1.0)
    n = len(_CMAP) - 1
    pos = tt * n
    i = np.minimum(pos.astype(int), n - 1)
    f = (pos - i)[..., None]
    a = np.array(_CMAP)
    out[..., :3] = a[i] * (1 - f) + a[i + 1] * f
    out[..., 3] = 1.0
    out[bad] = (0.6, 0.6, 0.6, 1.0)
    return out


LIBS_DIR = os.path.join(os.path.dirname(__file__), "libs")


def is_available():
    """Быстрая проверка без импорта: есть ли pyqtgraph и PyOpenGL
    (системные или в libs/ плагина). По ней решается, показывать ли
    пункт меню - без пакетов пункта просто нет."""
    import importlib.util
    have = (importlib.util.find_spec("pyqtgraph") is not None and
            importlib.util.find_spec("OpenGL") is not None)
    if have:
        return True
    return (os.path.isdir(os.path.join(LIBS_DIR, "pyqtgraph")) and
            os.path.isdir(os.path.join(LIBS_DIR, "OpenGL")))


def _import_gl():
    """Импорт pyqtgraph.opengl: сначала системный, затем из libs/ плагина."""
    try:
        import pyqtgraph.opengl as gl
        return gl
    except Exception:  # nosec
        pass
    import sys
    if os.path.isdir(LIBS_DIR) and LIBS_DIR not in sys.path:
        sys.path.insert(0, LIBS_DIR)
    import pyqtgraph.opengl as gl
    return gl


MAX_VERTS_SCENE = 600000


MIN_VERTS_LAYER = 30000    # ниже прореживать бессмысленно, форма пропадёт


MAX_VERTS = 60000          # запасной потолок, если слоёв не сосчитать


def ramp_colors(values, breaks, cols, kind="interpolated"):
    """Раскраска значений по шкале слоя.

    `breaks` это возрастающие значения шкалы, `cols` цвета в тех же
    точках, RGBA от нуля до единицы. Вид шкалы повторяет QGIS:
    непрерывная тянет цвет между соседними точками, ступенчатая
    отдаёт цвет первой точки, которая не меньше значения, точная
    красит только совпадения.

    Значения вне шкалы прижимаются к её концам, пропуски уходят
    серым: пустое место не должно выглядеть данными.
    """
    import numpy as np
    v = np.asarray(values, dtype=float)
    breaks = np.asarray(breaks, dtype=float)
    cols = np.asarray(cols, dtype=float)
    out = np.empty(v.shape + (4,), dtype=float)
    bad = ~np.isfinite(v)
    safe = np.where(bad, breaks[0] if len(breaks) else 0.0, v)
    if not len(breaks):
        out[...] = (0.6, 0.6, 0.6, 1.0)
        return out
    if kind == "interpolated":
        for c in range(4):
            out[..., c] = np.interp(safe, breaks, cols[:, c])
    elif kind == "discrete":
        idx = np.searchsorted(breaks, safe, side="left")
        out[...] = cols[np.clip(idx, 0, len(breaks) - 1)]
    else:
        idx = np.searchsorted(breaks, safe, side="left")
        idx = np.clip(idx, 0, len(breaks) - 1)
        hit = np.isclose(breaks[idx], safe)
        out[...] = cols[idx]
        out[~hit] = (0.6, 0.6, 0.6, 1.0)
    out[bad] = (0.6, 0.6, 0.6, 1.0)
    return out


def _ramp_from_renderer(lyr):
    """Шкала слоя из его оформления: (канал, значения, цвета, вид).

    Читается то же самое, что рисует карту, поэтому поверхность
    в сцене выходит той же расцветки, что и растр на холсте.
    Возвращает None, если у слоя обычная серая заливка или
    оформление не разобралось.
    """
    import numpy as np
    try:
        rnd = lyr.renderer()
    except Exception:  # nosec
        return None
    if rnd is None:
        return None
    band = 1
    for name in ("band", "inputBand", "grayBand"):
        fn = getattr(rnd, name, None)
        if fn is not None:
            try:
                band = int(fn())
                break
            except Exception:  # nosec
                continue
    items, kind = None, "interpolated"
    shader = getattr(rnd, "shader", None)
    if shader is not None:
        try:
            fn = rnd.shader().rasterShaderFunction()
            items = list(fn.colorRampItemList())
            ctype = int(fn.colorRampType())
            kind = {0: "interpolated", 1: "discrete",
                    2: "exact"}.get(ctype, "interpolated")
        except Exception:  # nosec
            items = None
    if items is None and hasattr(rnd, "classes"):
        try:
            cls = list(rnd.classes())
            items = [(c.value, c.color) for c in cls]
            kind = "exact"
        except Exception:  # nosec
            items = None
        rows = []
        for val, col in (items or []):
            rows.append((float(val), col))
    else:
        rows = []
        for it in (items or []):
            try:
                rows.append((float(it.value), it.color))
            except Exception:  # nosec
                continue
    rows = [r for r in rows if r[0] == r[0] and abs(r[0]) != float("inf")]
    if len(rows) < 2:
        return None
    rows.sort(key=lambda r: r[0])
    breaks = np.array([r[0] for r in rows], dtype=float)
    cols = np.array([[r[1].redF(), r[1].greenF(), r[1].blueF(),
                      r[1].alphaF()] for r in rows], dtype=float)
    return band, breaks, cols, kind


MARKER_SHAPES = ("circle", "square", "diamond", "triangle", "cross")


def flat_marker_mesh(rows, shape, size):
    """Плоские значки в плане: меш на весь слой.

    Спрайт точки в pyqtgraph нарисован кругом в шейдере, и другой формы
    от него не добиться. Поэтому остальные виды делаются мешем: плоская
    фигура лежит в плане на отметке точки. Она закрывается
    поверхностью и уходит под кровлю, чего экранный спрайт не умеет,
    а стоит два-четыре треугольника на точку.

    `rows` это (точка, цвет, размер), размер значка задаётся в метрах.
    Возвращает вершины, треугольники и цвета вершин.
    """
    import numpy as np
    if shape == "square":
        base = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
        tris = [(0, 1, 2), (0, 2, 3)]
    elif shape == "diamond":
        base = [(0, -1), (1, 0), (0, 1), (-1, 0)]
        tris = [(0, 1, 2), (0, 2, 3)]
    elif shape == "triangle":
        base = [(0, 1), (-0.9, -0.7), (0.9, -0.7)]
        tris = [(0, 1, 2)]
    elif shape == "cross":
        t = 0.32
        base = [(-1, -t), (1, -t), (1, t), (-1, t),
                (-t, -1), (t, -1), (t, 1), (-t, 1)]
        tris = [(0, 1, 2), (0, 2, 3), (4, 5, 6), (4, 6, 7)]
    else:
        return None
    base = np.asarray(base, dtype=float)
    tris = np.asarray(tris, dtype=np.int64)
    n = len(rows)
    if not n:
        return None
    half = float(size) / 2.0
    pos = np.array([r[0] for r in rows], dtype=float)
    verts = np.repeat(pos, len(base), axis=0)
    off = np.tile(base * half, (n, 1))
    verts[:, 0] += off[:, 0]
    verts[:, 1] += off[:, 1]
    step = np.arange(n)[:, None, None] * len(base)
    faces = (tris[None, :, :] + step).reshape(-1, 3)
    return verts, faces


def z_range_mask(z, zlo, zhi):
    """Отбор по отметке: что попадает в заданный диапазон.

    Обрезка контуром и коридором работает в плане, к высоте она
    отношения не имеет. Разрез по пачке пластов задаётся именно
    отметками, поэтому отбор по ним стоит отдельно.

    Границы включаются: отметка ровно на границе остаётся, иначе
    у куба пропадал бы крайний уровень. Перепутанные местами границы
    дают пусто, а не меняются молча: опечатку в поле лучше увидеть
    сразу, чем искать причину пустой сцены в данных.
    """
    import numpy as np
    z = np.asarray(z, dtype=float)
    keep = np.isfinite(z)
    if zlo is not None:
        keep &= z >= float(zlo)
    if zhi is not None:
        keep &= z <= float(zhi)
    return keep


def _map_order(proj):
    """Слои в порядке дерева карты, сверху вниз.

    `mapLayers` отдаёт словарь без всякого порядка, и список в окне
    получался случайным. Порядок дерева задаёт и очерёдность в списке,
    и приоритет при отрисовке: верхний слой карты рисуется поверх
    нижнего.
    """
    root = None
    try:
        root = proj.layerTreeRoot()
    except Exception:  # nosec
        root = None
    if root is None:
        return list(proj.mapLayers().values())
    out = []
    try:
        for lyr in root.layerOrder():
            if lyr is not None:
                out.append(lyr)
    except Exception:  # nosec
        out = []
    if not out:
        try:
            for node in root.findLayers():
                lyr = node.layer()
                if lyr is not None:
                    out.append(lyr)
        except Exception:  # nosec
            out = []
    return out or list(proj.mapLayers().values())


def _layer_budget(n_layers, cap=None):
    """Сколько вершин достаётся одному слою при данном их числе."""
    n = max(1, int(n_layers))
    total = int(cap or MAX_VERTS_SCENE)
    return max(MIN_VERTS_LAYER, total // n)


def _auto_step(arr, budget=None):
    """Шаг прореживания, чтобы вершин было не больше бюджета слоя."""
    ny, nx = arr.shape
    total = ny * nx
    cap = int(budget or MAX_VERTS)
    if total <= cap:
        return 1
    import math
    return int(math.ceil(math.sqrt(total / float(cap))))


_MAX_BODIES = 2000


def _body_budget(feats, n_layers=1, cap=None):
    """Какие объекты слоя берём в сцену.

    Считать объекты неправильно: тысяча мелких поясов дешевле десятка
    кадастровых кварталов с миллионом вершин. Поэтому копим вершины и
    останавливаемся по бюджету слоя, а число объектов держим потолком
    от разрастания самих мешей.

    Возвращает (объекты, набрано вершин, бюджет): числа нужны, чтобы
    в строке состояния было видно не только сколько отброшено,
    но и чего именно не хватило.
    """
    budget = _layer_budget(n_layers, cap)
    out, total = [], 0
    for ft in feats:
        try:
            n = ft.geometry().constGet().nCoordinates()
        except Exception:  # nosec
            n = 0
        if out and (total + n > budget or len(out) >= _MAX_BODIES):
            break
        out.append(ft)
        total += n
    return out, total, budget


def _tri_rings(tri):
    """Результат триангуляции как список троек (x, y, z).

    Отметка берётся из вершины и может оказаться NaN: GEOS третью
    координату через триангуляцию проносит не во всех сборках. Поэтому
    здесь она только читается, а решение о ней принимает `_fill_z`.
    """
    out = []
    try:
        parts = list(tri.constParts())
    except Exception:
        try:
            parts = [tri.constGet()]
        except Exception:
            return out
    for part in parts:
        ext = getattr(part, "exteriorRing", None)
        ring = ext() if ext is not None else part
        if ring is None:
            continue
        try:
            vs = list(ring.vertices())
        except Exception:
            vs = []          # не except/continue: сканер даёт B112
        if not vs:
            continue
        pts = []
        for v in vs[:3]:
            try:
                z = float(v.z())
            except Exception:
                z = float("nan")
            pts.append((v.x(), v.y(), z))
        if len(pts) == 3:
            out.append(pts)
    return out


def _fill_z(tris, src, nd=6):
    """Отметки вершинам триангуляции по вершинам исходной геометрии.

    Триангуляция с ограничениями своих точек не добавляет, поэтому почти
    всякая вершина находится в исходной по координатам. Оставшиеся редкие
    берут отметку ближайшей исходной вершины.

    Возвращает (вершины (N,3), число отметок, найденных поиском).
    """
    import numpy as np
    zmap = {}
    for x, y, z in src:
        zmap.setdefault((round(x, nd), round(y, nd)), z)
    verts, miss = [], []
    for t in tris:
        for x, y, z in t:
            zz = zmap.get((round(x, nd), round(y, nd)))
            if zz is None:
                if z == z:               # своя отметка из триангуляции
                    zz = z
                else:
                    zz = float("nan")
                    miss.append(len(verts))
            verts.append((x, y, zz))
    v = np.asarray(verts, dtype=float) if verts else np.zeros((0, 3))
    if miss and len(src):
        arr = np.asarray(src, dtype=float)
        idx = np.asarray(miss, dtype=np.int64)
        if len(idx) * len(arr) > 50000000:
            # искать ближайшую для каждой было бы дороже самой сцены
            v[idx, 2] = float(np.mean(arr[:, 2]))
        else:
            for i0 in range(0, len(idx), 256):
                ch = idx[i0:i0 + 256]
                d = ((arr[None, :, 0] - v[ch, 0][:, None]) ** 2
                     + (arr[None, :, 1] - v[ch, 1][:, None]) ** 2)
                v[ch, 2] = arr[np.argmin(d, axis=1), 2]
    return v, len(miss)


_TRI_CACHE = {}        # ключ -> (вершины, треугольники)


_TRI_ORDER = []


_TRI_BYTES = 0


_TRI_LIMIT = 128 * 1024 * 1024   # потолок кэша триангуляции, байт


def _tri_key(lyr, ft, geom, zfix):
    """Ключ кэша триангуляции.

    Считается дёшево: слой, номер объекта, число вершин, охват
    и отметка. Правка геометрии почти наверняка меняет число вершин
    или охват, поэтому обесценивание срабатывает. Хешировать саму
    геометрию дороже, чем она того стоит.
    """
    try:
        n = geom.constGet().nCoordinates()
    except Exception:
        n = -1
    try:
        b = geom.boundingBox()
        box = (round(b.xMinimum(), 3), round(b.yMinimum(), 3),
               round(b.xMaximum(), 3), round(b.yMaximum(), 3))
    except Exception:
        box = None
    if zfix is None or isinstance(zfix, str):
        z = zfix
    else:
        z = round(float(zfix), 6)
    return (lyr.id(), int(ft.id()), n, box, z)


def _tri_cached(lyr, ft, geom, zfix, prof=None, spatial=False):
    """Триангуляция с кэшем: геометрия между сборками не меняется.

    Разбивка пятисот контуров занимала шесть секунд и повторялась
    на каждое нажатие «Обновить сцену», хотя объекты те же самые.

    `spatial` включает разбор объекта по кольцам, каждое в своей
    плоскости. Так разбираются тела и пояса с переменной отметкой:
    в плане вертикальная стенка вырождается в линию, и плоская
    разбивка даёт мусор. Ключ у этого пути свой, чтобы результаты
    двух разных разбивок одного объекта не путались.
    """
    global _TRI_BYTES
    key = _tri_key(lyr, ft, geom, "3d" if spatial else zfix)
    hit = _TRI_CACHE.get(key)
    if hit is not None:
        if prof is not None:
            prof.count("trihits")
        return hit
    if prof is not None:
        prof.count("tess")
    # Разбивка живёт в окне: ей нужны геометрии QGIS. Сюда она
    # приходит вызовом, чтобы кэш не тянул за собой QGIS.
    from .viewer3d import _tris_from_geometry, _tessellate
    v, f = (_tris_from_geometry(geom) if spatial
            else _tessellate(geom, zfix))
    nbytes = int(getattr(v, "nbytes", 0)) + int(getattr(f, "nbytes", 0))
    if nbytes <= _TRI_LIMIT:
        while _TRI_ORDER and _TRI_BYTES + nbytes > _TRI_LIMIT:
            old = _TRI_ORDER.pop(0)
            prev = _TRI_CACHE.pop(old, None)
            if prev is not None:
                _TRI_BYTES -= (int(getattr(prev[0], "nbytes", 0))
                               + int(getattr(prev[1], "nbytes", 0)))
        _TRI_CACHE[key] = (v, f)
        _TRI_ORDER.append(key)
        _TRI_BYTES += nbytes
    return v, f


def tri_cache_clear():
    """Сбросить кэш триангуляции (для тестов и на закрытие окна)."""
    global _TRI_BYTES
    _TRI_CACHE.clear()
    del _TRI_ORDER[:]
    _TRI_BYTES = 0


def tri_cache_size():
    return len(_TRI_CACHE), _TRI_BYTES


def _ring_normal(pts):
    """Нормаль кольца по формуле Ньюэлла.

    Работает и на невыпуклом кольце, и на слегка неплоском: даёт
    осреднённую нормаль, а не нормаль первых трёх точек.
    """
    import numpy as np
    p = np.asarray(pts, dtype=float)
    q = np.roll(p, -1, axis=0)
    nx = float(np.sum((p[:, 1] - q[:, 1]) * (p[:, 2] + q[:, 2])))
    ny = float(np.sum((p[:, 2] - q[:, 2]) * (p[:, 0] + q[:, 0])))
    nz = float(np.sum((p[:, 0] - q[:, 0]) * (p[:, 1] + q[:, 1])))
    n = np.array([nx, ny, nz], dtype=float)
    ln = float(np.linalg.norm(n))
    return None if ln < 1e-12 else n / ln


def walk_rings(segs, snap=1e-6):
    """Замкнутые кольца из отрезков.

    У замкнутой оболочки срез даёт замкнутые кольца, и обход по концам
    точен: он не решает за нас, где площадь, а просто идёт по рёбрам.
    Отрезки приходят парами точек (x, y).

    Возвращает список колец, каждое списком точек. Незамкнутые куски
    отбрасываются: достраивать их наугад значит рисовать площадь,
    которой нет.
    """
    import collections
    adj = collections.defaultdict(list)

    def key(p):
        return (round(float(p[0]) / snap), round(float(p[1]) / snap))

    pts = {}
    for a, b in segs:
        ka, kb = key(a), key(b)
        pts[ka], pts[kb] = a, b
        if ka == kb:
            continue
        adj[ka].append(kb)
        adj[kb].append(ka)
    rings = []
    seen = set()
    for start in list(adj):
        if start in seen:
            continue
        ring, cur, prev = [start], start, None
        while True:
            # На Т-образном стыке у узла больше двух соседей: берём
            # ещё не пройденного. Кольцо от этого не всегда замкнётся,
            # но там, где замкнётся, крышка встанет.
            nxt = None
            for cand in adj[cur]:
                if cand != prev and (cand == start or cand not in seen):
                    nxt = cand
                    break
            if nxt is None:
                break
            if nxt == start:
                rings.append([pts[k] for k in ring])
                break
            if nxt in seen:
                break
            ring.append(nxt)
            seen.add(nxt)
            prev, cur = cur, nxt
        seen.add(start)
    return [r for r in rings if len(r) >= 3]


def clip_wall(tri, spans):
    """Отвесная грань, обрезанная по доле длины в плане.

    В плане отвесный треугольник вырождается в отрезок, и резать его
    как полигон нечем: площадь нулевая. Зато вдоль отрезка он режется
    точно: вершины переводятся в пару «доля вдоль отрезка - отметка»,
    треугольник обрезается по доле как обычный выпуклый многоугольник,
    и результат возвращается обратно в пространство.

    Оставлять такую грань целиком нельзя: она торчит за контур, а
    соседняя горизонтальная обрезана по нему, и между ними остаётся
    щель. Это и есть дырки в теле.

    `spans` это список пар (от, до) в долях от нуля до единицы.
    Возвращает (вершины, треугольники).
    """
    import numpy as np
    tri = np.asarray(tri, dtype=float)
    p0 = tri[:, :2]
    # направление отрезка в плане: берём самую длинную сторону
    d = p0[[1, 2, 0]] - p0
    ln = (d ** 2).sum(axis=1)
    k = int(np.argmax(ln))
    if ln[k] <= 0:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    base, dirv = p0[k], d[k]
    t = ((p0 - base) * dirv).sum(axis=1) / float((dirv ** 2).sum())
    poly = np.column_stack([t, tri[:, 2]])

    out_v, out_f = [], []
    for lo, hi in spans:
        if hi - lo <= 1e-12:
            continue
        cur = poly
        for sign, bound in ((1.0, lo), (-1.0, hi)):
            if not len(cur):
                break
            keep = (cur[:, 0] - bound) * sign >= 0
            if keep.all():
                continue
            if not keep.any():
                cur = np.zeros((0, 2))
                break
            new = []
            n = len(cur)
            for i in range(n):
                a, b = cur[i], cur[(i + 1) % n]
                ka, kb = keep[i], keep[(i + 1) % n]
                if ka:
                    new.append(a)
                if ka != kb:
                    da = a[0] - bound
                    db = b[0] - bound
                    w = da / (da - db)
                    new.append(a + (b - a) * w)
            cur = np.asarray(new, dtype=float)
        if len(cur) < 3:
            continue
        xy = base + dirv * cur[:, :1]
        pts = np.column_stack([xy, cur[:, 1]])
        m = len(pts)
        base_i = sum(len(x) for x in out_v)
        out_v.append(pts)
        out_f.append(np.array([[base_i, base_i + i, base_i + i + 1]
                               for i in range(1, m - 1)],
                              dtype=np.int64))
    if not out_f:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    import numpy as np2
    return np2.vstack(out_v), np2.vstack(out_f)


_CSS_NAMES = {
    "red": "#ff0000", "green": "#008000", "blue": "#0000ff",
    "yellow": "#ffff00", "cyan": "#00ffff", "magenta": "#ff00ff",
    "white": "#ffffff", "black": "#000000", "gray": "#808080",
    "grey": "#808080", "orange": "#ffa500", "brown": "#a52a2a",
    "pink": "#ffc0cb", "purple": "#800080", "lime": "#00ff00",
    "navy": "#000080", "teal": "#008080", "olive": "#808000",
    "maroon": "#800000", "silver": "#c0c0c0",
}


# Свет падает сверху и чуть сбоку: так рельеф читается лучше всего,
# и так его рисуют на бумажных картах отмывкой.
LIGHT_DIR = (-0.35, -0.45, 0.82)

# У отмывки источник остаётся ОДИН, и это не недосмотр. Тремя
# источниками она выходит площе: диапазон яркости с 0.45 - 1.00
# сжимается до 0.50 - 0.86, и рельеф внутри одного оттенка шкалы
# читается хуже. Тёмная сцена из тел лечится в шейдере (lights.py),
# где освещается СПЛОШНОЙ цвет, а не шкала.


def shade_colors(colors, normals, strength=0.55):
    """Притемнить цвета вершин по наклону поверхности.

    Поверхность, раскрашенная шкалой, рисуется одним цветом вершин
    без света вовсе: рельеф внутри одного оттенка пропадает целиком.
    Умножая цвет на освещённость, возвращаем форму, не трогая саму
    шкалу - светлее и темнее становится один и тот же цвет.

    Прозрачность не трогается: её задаёт слой.
    """
    import numpy as np
    c = np.asarray(colors, dtype=float).copy()
    if not len(c) or float(strength) <= 0.0:
        return c
    n = np.asarray(normals, dtype=float)
    ln = np.linalg.norm(n, axis=1)
    ok = ln > 1e-12
    # У вырожденной грани нормали нет: такую вершину не темним,
    # иначе на месте изъяна появится чёрное пятно.
    k = np.ones(len(c))
    d = np.asarray(LIGHT_DIR, dtype=float)
    d = d / np.linalg.norm(d)
    cosang = np.zeros(len(c))
    cosang[ok] = np.abs(n[ok] @ d) / ln[ok]
    s = float(np.clip(strength, 0.0, 1.0))
    k[ok] = (1.0 - s) + s * cosang[ok]
    c[:, :3] = np.clip(c[:, :3] * k[:, None], 0.0, 1.0)
    return c


def draw_depth(glopts):
    """Очередь рисования по режиму прозрачности.

    Полупрозрачная поверхность пишет в буфер глубины: нарисованная
    раньше забора, она отбрасывает его ещё до смешивания цветов,
    и прозрачность ничего не открывает.

    Непрозрачное идёт первым и заполняет глубину честно, прозрачное
    ложится поверх. Библиотека рисует по возрастанию этого числа.
    """
    return 0 if str(glopts) == "opaque" else 1


def layer_lift(span_z, rank, count):
    """Подъём слоя по порядку в списке, в единицах сцены.

    Совпадающая геометрия иначе спорит за глубину: изолинии то
    показываются, то тонут в поверхности, на которой лежат.

    Считать подъём долей охвата В ПЛАНЕ нельзя. На площадке
    в двенадцать километров это даёт пять метров, и слой уезжает
    от растра, по которому построен, на постоянную величину -
    при мощности пласта в метры расхождение видно сразу.

    Мерой служит размах отметок: подъём остаётся малым против того,
    что и разделяет по высоте.
    """
    span_z = abs(float(span_z))
    n = max(int(count), 1)
    rank = min(max(int(rank), 0), n)
    return span_z * 1e-3 * float(n - rank) / n


def field_color(value):
    """Цвет из атрибута объекта: строка «#rrggbb» либо None.

    Инструменты Isoliner пишут цвет пласта прямо в поле, тем же, что
    на чертеже. Читать его надо раньше символики: он посчитан
    на стороне данных и точнее любого пересчёта.

    Возвращается None на пустом и испорченном значении - тогда цвет
    берётся по общему правилу. Красить наугад нельзя: чёрное тело
    выглядит настоящим и молча врёт про пласт.

    Прозрачность не читается: её задаёт слой, и восьмизначная запись
    сводится к цвету.
    """
    if value is None:
        return None
    txt = str(value).strip().lower()
    if not txt:
        return None
    if txt in _CSS_NAMES:
        return _CSS_NAMES[txt]
    if not txt.startswith("#"):
        return None
    body = txt[1:]
    if not all(c in "0123456789abcdef" for c in body):
        return None
    if len(body) == 3:
        return "#" + "".join(c * 2 for c in body)
    if len(body) == 8:      # альфа впереди: берём только цвет
        body = body[2:]
    if len(body) != 6:
        return None
    return "#" + body


def _closed_and_border(verts, faces):
    """Замкнута ли оболочка и сколько у неё краевых рёбер.

    Число нужно, чтобы сказать вслух, почему крышку на срезе
    не построить: у слитого тела вокселей граница разорвана
    Т-образными стыками ещё до всякой резки, и кольцо среза
    не замыкается никаким способом.
    """
    import collections
    edges = collections.Counter()
    for tri in faces:
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]),
                     (tri[2], tri[0])):
            edges[(a, b) if a < b else (b, a)] += 1
    border = sum(1 for n in edges.values() if n == 1)
    return border == 0, border


def _is_closed(v, f, tol=1e-6):
    """Замкнута ли оболочка: каждое ребро принадлежит двум граням.

    Пояс между изолиниями открыт, и крышку ему строить не надо: попытка
    закрыть открытую поверхность даёт мусор. Замкнутому телу крышка,
    наоборот, обязательна, иначе на срезе видна изнанка.
    """
    import collections
    if not len(f):
        return False
    edges = collections.Counter()
    for tri in f:
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            edges[(a, b) if a < b else (b, a)] += 1
    return all(n == 2 for n in edges.values())


def _bary_z(tri, xs, ys):
    """Отметки точек внутри треугольника по его вершинам.

    Нужна при обрезке грани: у новых вершин, появившихся на линии реза,
    своей высоты нет, её берут из плоскости исходного треугольника.
    """
    import numpy as np
    (x1, y1, z1), (x2, y2, z2), (x3, y3, z3) = tri
    den = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
    if abs(den) < 1e-12:
        return np.full(np.shape(xs), (z1 + z2 + z3) / 3.0)
    l1 = ((y2 - y3) * (xs - x3) + (x3 - x2) * (ys - y3)) / den
    l2 = ((y3 - y1) * (xs - x3) + (x1 - x3) * (ys - y3)) / den
    l3 = 1.0 - l1 - l2
    return l1 * z1 + l2 * z2 + l3 * z3


def _flat_z(geom, tol=1e-6):
    """Отметка плоского объекта или None, если Z меняется.

    Плоский контур (ступень рельефа, подсчётный блок, плита на отметке)
    надо разбивать настоящей триангуляцией: веер даёт лучи через фигуру.
    Обход идёт по всем вершинам с выходом на первом же расхождении.
    Прежний потолок в 4096 вершин судил о фигуре по началу контура: у
    пояса между изолиниями обход идёт сначала по одной границе, и первые
    тысячи вершин лежат на одном уровне. Пояс в двадцать пять тысяч
    вершин объявлялся плоским, и скат превращался в плиту.
    """
    lo = hi = None
    for v in _all_vertices(geom):
        try:
            z = float(v.z())
        except Exception:
            z = float("nan")   # не except/continue: сканер даёт B112
        if z != z:
            continue
        if lo is None:
            lo = hi = z
            continue
        if z < lo:
            lo = z
        elif z > hi:
            hi = z
        if (hi - lo) > tol:
            return None
    if lo is None:
        return None
    return lo


def _all_vertices(geom):
    """Все вершины геометрии подряд, без склейки колец в списки.

    Нужен обход с ранним выходом: у пояса в двадцать пять тысяч вершин
    собирать их все ради проверки отметок незачем.
    """
    it = None
    try:
        it = geom.constGet().vertices()
    except Exception:
        it = None
    if it is not None:
        for v in it:
            yield v
        return
    try:
        parts = list(geom.constParts())
    except Exception:
        return
    for part in parts:
        rings = []
        ext = getattr(part, "exteriorRing", None)
        if ext is not None:
            r = ext()
            if r is not None:
                rings.append(r)
            n_int = getattr(part, "numInteriorRings", None)
            for i in range(n_int() if n_int else 0):
                inner = part.interiorRing(i)
                if inner is not None:
                    rings.append(inner)
        else:
            rings.append(part)
        for ring in rings:
            try:
                vs = list(ring.vertices())
            except Exception:
                vs = []      # не except/continue: сканер даёт B112
            for v in vs:
                yield v


def _css_rgba(css, alpha=1.0):
    """Цвет вида #rrggbb в кортеж долей единицы."""
    s = str(css or "").lstrip("#")
    if len(s) != 6:
        return (0.55, 0.60, 0.66, alpha)
    try:
        r, g, b = (int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return (0.55, 0.60, 0.66, alpha)
    return (r, g, b, alpha)


def _draw_on_top(item):
    """Рисовать элемент поверх всего, не считаясь с глубиной.

    Высота вершин контура берётся с поверхности, но для работы она
    не нужна: важно плановое положение. Зато линия, спрятанная под
    складкой рельефа или под верхним пластом, мешает постоянно.
    """
    try:
        from OpenGL.GL import (GL_DEPTH_TEST, GL_BLEND, GL_CULL_FACE,
                               GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA,
                               GL_ONE)
        # Набор ключей повторяет штатный «translucent» из pyqtgraph,
        # только проверка глубины выключена. Свой ключ вроде
        # GL_ALPHA_TEST сюда класть нельзя: он не из этого набора,
        # и отрисовка падала.
        item.setGLOptions({
            GL_DEPTH_TEST: False,
            GL_BLEND: True,
            GL_CULL_FACE: False,
            'glBlendFuncSeparate': (GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA,
                                    GL_ONE, GL_ONE_MINUS_SRC_ALPHA),
        })
    except Exception:  # nosec
        item.setGLOptions('translucent')


def _find_data(combo, want):
    """Индекс пункта с такими данными или -1.

    Штатный `findData` сравнивает через QVariant и на кортежах Python
    не срабатывает: возвращает -1 даже когда пункт есть. Из-за этого
    выбранная окраска не восстанавливалась при переходе на другой слой
    и подменялась палитрой, хотя в сцене оставалась прежней. Сравниваем
    сами, как обычные объекты Python.
    """
    for i in range(combo.count()):
        if combo.itemData(i) == want:
            return i
    return -1


def _fmt_n(n):
    """Число с пробелами по три разряда: 184 512 читается лучше, чем 184512."""
    s = str(int(n))
    out = []
    while len(s) > 3:
        out.insert(0, s[-3:])
        s = s[:-3]
    out.insert(0, s)
    return "\u00a0".join(out)


def _gdal_open(source):
    """gdal.Open, устойчивый к пустому/битому источнику.

    В сборках с включёнными исключениями GDAL (QGIS 4) gdal.Open на пустой
    строке бросает RuntimeError вместо None - гасим и возвращаем None.
    """
    if not source:
        return None
    from osgeo import gdal
    try:
        return gdal.Open(source)
    except Exception:
        return None


_CACHE = {}          # (путь, канал, отметка файла) -> (массив, geotransform)


_BANDS = {}          # (путь, отметка файла) -> число каналов


_CACHE_ORDER = []    # ключи в порядке появления, для вытеснения старых


_CACHE_BYTES = 0


_CACHE_LIMIT = 256 * 1024 * 1024   # потолок кэша массивов, байт


def _file_stamp(source):
    """Отметка файла (время правки, размер) или None, если это не файл.

    По ней кэш сам себя обесценивает: правленый на диске грид получает
    другую отметку и читается заново. Если источник не файл (сервис, база,
    подзапрос), отметки нет и кэшировать такое нельзя.
    """
    path = str(source or "").split("|")[0]
    try:
        st = os.stat(path)
    except Exception:
        return None
    return (st.st_mtime, st.st_size)


def _cache_put(key, arr, gt):
    global _CACHE_BYTES
    nbytes = int(getattr(arr, "nbytes", 0))
    if nbytes > _CACHE_LIMIT:
        return                      # один такой массив съест весь кэш
    while _CACHE_ORDER and _CACHE_BYTES + nbytes > _CACHE_LIMIT:
        old = _CACHE_ORDER.pop(0)
        prev = _CACHE.pop(old, None)
        if prev is not None:
            _CACHE_BYTES -= int(getattr(prev[0], "nbytes", 0))
    _CACHE[key] = (arr, gt)
    _CACHE_ORDER.append(key)
    _CACHE_BYTES += nbytes


def cache_clear():
    """Сбросить кэш массивов и каналов (для тестов и на закрытие окна)."""
    global _CACHE_BYTES
    _CACHE.clear()
    del _CACHE_ORDER[:]
    _CACHE_BYTES = 0
    _BANDS.clear()


def cache_size():
    """Сколько массивов и байт лежит в кэше."""
    return len(_CACHE), _CACHE_BYTES


def _read_raster(source, band=1, prof=None):
    """Читает канал растра как массив с NaN и geotransform.

    Результат кэшируется по пути, каналу и отметке файла: повторная сборка
    сцены при том же наборе слоёв берёт массивы из памяти, а не с диска.
    На замерах чтение занимало 97 процентов времени перестройки, поэтому
    выигрыш прямой.

    Возвращённый массив принадлежит кэшу, менять его на месте нельзя.
    """
    import numpy as np
    stamp = _file_stamp(source)
    key = (str(source), int(band), stamp)
    if stamp is not None:
        hit = _CACHE.get(key)
        if hit is not None:
            if prof is not None:
                prof.count("hits")
            return hit
    ds = _gdal_open(source)
    if ds is None or band > ds.RasterCount:
        return None, None
    b = ds.GetRasterBand(band)
    arr = b.ReadAsArray().astype(float)
    nd = b.GetNoDataValue()
    if nd is not None:
        arr[arr == nd] = np.nan     # на месте, без копии массива
    gt = ds.GetGeoTransform()
    ds = None
    if prof is not None:
        prof.count("reads")
    if stamp is not None:
        _cache_put(key, arr, gt)
    return arr, gt


def _band_count(source):
    """Число каналов растра, с кэшем: раньше на каждый слой открывался
    отдельный набор данных, и на шести слоях это шесть лишних открытий."""
    stamp = _file_stamp(source)
    key = (str(source), stamp)
    if stamp is not None and key in _BANDS:
        return _BANDS[key]
    ds = _gdal_open(source)
    if ds is None:
        return 0
    n = ds.RasterCount
    ds = None
    if stamp is not None:
        _BANDS[key] = n
    return n


def volume_beyond_box(value, verts):
    """Невозможен ли записанный объём: он не бывает больше габарита.

    Объём тела считался суммой объёмов тетраэдров от начала координат,
    и при шести миллионах метров по северу значащие цифры съедались
    взаимным вычитанием. Счёт исправлен в 0.74.1, но слои, выгруженные
    раньше, продолжают ходить по рукам: на присланном слое из 93 тел
    у 37 объём оказался больше собственного габарита, у худшего
    в пятьдесят тысяч раз.

    Проверка нарочно грубая. Габарит - верхняя граница объёма при любой
    форме тела, поэтому ложных срабатываний у неё нет. Пересчитывать
    чужой слой молча хуже, чем сказать, что верить его числам нельзя.
    """
    import numpy as np
    v = np.asarray(verts, dtype=float)
    if v.ndim != 2 or not len(v):
        return False
    try:
        q = float(value)
    except (TypeError, ValueError):
        return False
    if not np.isfinite(q) or q <= 0:
        return False
    box = float(np.prod(v.max(axis=0) - v.min(axis=0)))
    return box > 0 and q > box * 1.001


def is_bed_grid(source):
    """Похож ли растр на грид пласта, а не на куб значений.

    Различие не косметическое. У куба каналы это уровни по Z, и
    разметку по Z (Z0 и DZ) пишет каждый инструмент куба. У грида
    пласта её нет и быть не может: каналы там кровля и подошва,
    а значения - абсолютные отметки. Спутав одно с другим, сцена
    рисует параллелепипед у нулевой отметки, ниже всех объектов.
    """
    ds = _gdal_open(source)
    if ds is None or ds.RasterCount < 2:
        return False
    meta = ds.GetMetadata() or {}
    marks = [(ds.GetRasterBand(b).GetDescription() or "").lower()
             for b in range(1, ds.RasterCount + 1)]
    ds = None
    if "Z0" in meta or "z0" in meta:
        return False
    return any(w in nm for nm in marks
               for w in ("кровля", "подошва", "roof", "floor"))


def _band_items(source):
    """[(номер, подпись)] по описаниям каналов растра."""
    ds = _gdal_open(source)
    if ds is None:
        return []
    out = []
    for i in range(1, ds.RasterCount + 1):
        d = ds.GetRasterBand(i).GetDescription()
        out.append((i, "%d - %s" % (i, d) if d else str(i)))
    ds = None
    return out
