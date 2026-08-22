# -*- coding: utf-8 -*-
#
# Isoliner - грид и изолинии (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Собственный 3D-просмотр поверхностей.

Окно на pyqtgraph.opengl: выбранные растры проекта рисуются треугольными
мешами, каждый горизонт своим цветом, с вертикальным преувеличением и
разносом по Z. Не зависит от штатного 3D-вида QGIS (Qt3D).

Qt и pyqtgraph импортируются лениво: модуль импортируется headless без
ошибок (tests/test_viewer3d.py). Если pyqtgraph/PyOpenGL не установлены,
пользователь получает окно с инструкцией по установке.
"""
import os
import time

from .i18n import tr
from .mesh3d import (grid_to_mesh_arrays, bed_to_mesh_arrays,
                     sample_bilinear, thin_labels_xy, cylinder,
                     polygon_mask, polyline_dist_side)

# закреплённая строка «Сцена» в списке слоёв
_SCENE_KEY = "__scene__"
# ключ пункта «нарисованный контур» в списке обрезки
_DRAWN_KEY = "__drawn__"
# ключ пункта «нарисованная линия» в списке обрезки
_DRAWNL_KEY = "__drawnline__"

# опорные цвета шкалы (тёмно-синий -> бирюза -> жёлтый, а-ля viridis)
_CMAP = [(0.267, 0.005, 0.329), (0.229, 0.322, 0.546),
         (0.128, 0.567, 0.551), (0.369, 0.789, 0.383),
         (0.993, 0.906, 0.144)]


# Предел видимых граней у вокселей: выше этого сцена
# перестаёт быть отзывчивой, и вместо показа выдаётся
# число и совет, что покрутить.
_VOX_FACE_LIMIT = 1500000


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


_DIALOG = None  # держим окно живым

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


# Бюджет вершин на всю сцену, а не на слой. Раньше потолок был
# персональным, и одиночная поверхность получала столько же, сколько
# каждый слой из десятка: детали не хватало там, где она была бесплатна,
# и было слишком много там, где сцена и так тяжёлая.
MAX_VERTS_SCENE = 600000
MIN_VERTS_LAYER = 30000    # ниже прореживать бессмысленно, форма пропадёт
MAX_VERTS = 60000          # запасной потолок, если слоёв не сосчитать

PALETTE = [
    (0.85, 0.55, 0.10, 1.0),
    (0.20, 0.55, 0.85, 1.0),
    (0.30, 0.70, 0.35, 1.0),
    (0.80, 0.30, 0.30, 1.0),
    (0.60, 0.40, 0.80, 1.0),
    (0.50, 0.50, 0.30, 1.0),
    (0.20, 0.70, 0.70, 1.0),
    (0.85, 0.45, 0.65, 1.0),
]


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


# потолок объектов на слой. Раньше он стоял на пятистах, и слой поясов
# в 1174 объекта показывался меньше чем наполовину. Основной сдержкой
# теперь служит бюджет вершин (_body_budget), а этот потолок остаётся
# против разрастания числа мешей в сцене
_MAX_BODIES = 2000

# линии дешевле тел, но контуры рельефа идут тысячами: на 2349 контурах
# получалось полтора миллиона вершин и нечитаемая паутина
_MAX_LINES = 1500


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


def _inside_only(geom, tris):
    """Отсев треугольников, попавших вне фигуры.

    Триангуляция Делоне без ограничений заполняет выпуклую оболочку и на
    вогнутом контуре затягивает заливом заливы, а дыры закрывает вовсе.
    Пояс между изолиниями вогнут почти весь, поэтому лишнее убираем по
    центру треугольника подготовленной геометрией.
    """
    try:
        from qgis.core import QgsGeometry, QgsPointXY
        eng = QgsGeometry.createGeometryEngine(geom.constGet())
        eng.prepareGeometry()
    except Exception:
        return tris
    out = []
    for t in tris:
        cx = (t[0][0] + t[1][0] + t[2][0]) / 3.0
        cy = (t[0][1] + t[1][1] + t[2][1]) / 3.0
        try:
            ok = eng.contains(
                QgsGeometry.fromPointXY(QgsPointXY(cx, cy)).constGet())
        except Exception:
            return tris
        if ok:
            out.append(t)
    return out or tris


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


def _tessellate(geom, zfix=None):
    """Полигон в треугольники строго, с учётом вогнутости и дыр.

    Веерная триангуляция `polyhedral.wkt_to_tris` рассчитана на выпуклые
    грани полиэдров и на произвольном контуре даёт лучи через всю фигуру.
    Поэтому здесь просим QGIS о триангуляции Делоне с ограничениями,
    и только если её нет в сборке, откатываемся на веер.

    `zfix` задаёт единую отметку всей фигуре. При `zfix=None` отметки
    остаются вершинными: у пояса между изолиниями одна граница идёт по
    нижнему уровню, другая по верхнему, и поверхность выходит скатом.

    Возвращает (verts (N,3), faces (M,3)) или пустые массивы.
    """
    import numpy as np
    tri, strict = None, False
    for name, flag in (("constrainedDelaunayTriangulation", True),
                       ("delaunayTriangulation", False)):
        fn = getattr(geom, name, None)
        if fn is None:
            continue
        try:
            res = fn()
        except Exception:
            res = None       # не except/continue: сканер даёт B112
        if res is not None and not res.isEmpty():
            tri, strict = res, flag
            break
    if tri is None:
        from . import polyhedral as poly
        try:
            v, f = poly.wkt_to_tris(geom.asWkt())
        except Exception:
            return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
        if zfix is not None and len(v):
            v = v.copy()
            v[:, 2] = zfix
        return v, f.astype(np.int64)

    tris = _tri_rings(tri)
    if not strict:
        tris = _inside_only(geom, tris)
    if not tris:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    if zfix is None:
        src = []
        for part in _parts_xyz(geom):
            src.extend(part)
        verts, _n = _fill_z(tris, src)
    else:
        verts = np.asarray(
            [(x, y, zfix) for t in tris for x, y, _z in t], dtype=float)
    faces = np.arange(len(verts), dtype=np.int64).reshape(-1, 3)
    return verts, faces


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


def _prism(geom, cap_v, cap_f, zbot, ztop):
    """Призма из плоского контура: две крышки и боковые стенки.

    Контур с полями низа и верха описывает не плиту, а объём: ступень
    рельефа, уступ карьера, подсчётный блок с кровлей и подошвой.
    Крышки берутся из готовой триангуляции контура (она уже в кэше),
    стенки строятся по кольцам между отметками.
    """
    import numpy as np
    if not len(cap_f):
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    top = np.asarray(cap_v, dtype=float).copy()
    top[:, 2] = ztop
    bot = top.copy()
    bot[:, 2] = zbot
    n = len(top)
    faces = [np.asarray(cap_f, dtype=np.int64),
             np.asarray(cap_f, dtype=np.int64)[:, ::-1] + n]
    verts = [top, bot]
    base = 2 * n
    for ring in _parts_xyz(geom, 0.0):
        pts = np.asarray([(x, y) for x, y, _z in ring], dtype=float)
        if len(pts) < 2:
            continue
        if not np.allclose(pts[0], pts[-1]):
            pts = np.vstack([pts, pts[:1]])
        m = len(pts)
        wall_top = np.column_stack([pts, np.full(m, ztop)])
        wall_bot = np.column_stack([pts, np.full(m, zbot)])
        verts.append(wall_top)
        verts.append(wall_bot)
        idx_t = base + np.arange(m)
        idx_b = idx_t + m
        for i in range(m - 1):
            faces.append(np.array([[idx_t[i], idx_b[i], idx_b[i + 1]],
                                   [idx_t[i], idx_b[i + 1], idx_t[i + 1]]],
                                  dtype=np.int64))
        base += 2 * m
    return np.vstack(verts), np.vstack(faces)


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


def _tessellate_ring3d(pts):
    """Разбить кольцо на треугольники в его собственной плоскости.

    Разбивка в плане не годится для вертикальных стенок: там кольцо
    вырождается в линию. Поэтому кольцо кладётся в свою плоскость,
    разбивается там и возвращается обратно. Вогнутость обрабатывается
    заодно, отдельного случая для неё не нужно.
    """
    import numpy as np
    p = np.asarray(pts, dtype=float)
    if len(p) >= 2 and np.allclose(p[0], p[-1]):
        p = p[:-1]
    if len(p) < 3:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    n = _ring_normal(p)
    if n is None:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    ref = np.array([0.0, 0.0, 1.0])
    if abs(float(np.dot(ref, n))) > 0.9:
        ref = np.array([1.0, 0.0, 0.0])
    u = np.cross(n, ref)
    u = u / max(float(np.linalg.norm(u)), 1e-12)
    w = np.cross(n, u)
    origin = p.mean(axis=0)
    rel = p - origin
    uu, ww = rel.dot(u), rel.dot(w)

    from qgis.core import QgsGeometry, QgsPointXY
    flat = QgsGeometry.fromPolygonXY(
        [[QgsPointXY(float(a), float(b)) for a, b in zip(uu, ww)]])
    tri = None
    for name in ("constrainedDelaunayTriangulation",
                 "delaunayTriangulation"):
        fn = getattr(flat, name, None)
        if fn is None:
            continue
        try:
            res = fn()
        except Exception:
            res = None
        if res is not None and not res.isEmpty():
            tri = res
            break
    if tri is None:
        # запасной путь: веер. Хуже, но лучше пустоты
        faces = [(0, i, i + 1) for i in range(1, len(p) - 1)]
        return (p.copy(), np.asarray(faces, dtype=np.int64))

    verts, faces = [], []
    for part in _parts_xyz(tri, 0.0):
        ring = part[:3]
        if len(ring) < 3:
            continue
        base = len(verts)
        for a, b, _z in ring:
            verts.append(origin + a * u + b * w)
        faces.append((base, base + 1, base + 2))
    if not faces:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    return (np.asarray(verts, dtype=float),
            np.asarray(faces, dtype=np.int64))


def _tris_from_geometry(geom, both_sides=True):
    """Треугольники объекта: каждое кольцо в своей плоскости.

    `both_sides` разворачивает грани нормалью вверх, а не дублирует их.
    Пояса между изолиниями не замкнуты, и у половины граней нормаль
    смотрит вниз: такие уходили в чёрный при верной геометрии. Копия
    грани этого не лечит: она ложится ровно на оригинал, и две грани
    начинают спорить за глубину, отчего появляются полосы.
    """
    import numpy as np
    verts, faces, base = [], [], 0
    for ring in _parts_xyz(geom):
        v, f = _tessellate_ring3d(ring)
        if not len(f):
            continue
        verts.append(v)
        faces.append(np.asarray(f, dtype=np.int64) + base)
        base += len(v)
    if not faces:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    v_all, f_all = np.vstack(verts), np.vstack(faces)
    if both_sides and len(f_all):
        a = v_all[f_all[:, 0]]
        b = v_all[f_all[:, 1]]
        c = v_all[f_all[:, 2]]
        nz = ((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1])
              - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0]))
        flip = nz < 0
        if flip.any():
            f_all = f_all.copy()
            f_all[flip] = f_all[flip][:, ::-1]
    return v_all, f_all


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


def _layer_has_z(lyr):
    """Есть ли у геометрии слоя высота."""
    try:
        from qgis.core import QgsWkbTypes
        return bool(QgsWkbTypes.hasZ(lyr.wkbType()))
    except Exception:
        return False


def _parts_xyz(geom, zfix=None):
    """Части геометрии как списки (x, y, z).

    `asPolyline` и `asPoint` возвращают QgsPointXY, у которых высоты нет
    вовсе: линия со своей Z превращалась в пустоту и в сцену не попадала.
    Поэтому идём по настоящим вершинам через constParts.

    `zfix` задаёт отметку из поля: тогда весь объект лежит на одной
    высоте, как и положено изолинии.
    """
    out = []
    try:
        parts = list(geom.constParts())
    except Exception:
        parts = []
    if not parts:
        try:
            parts = [geom.constGet()]
        except Exception:
            return out
    rings = []
    for part in parts:
        # у полигона внутри части кольца идут подряд, и обход всех вершин
        # склеивает внешнее кольцо с дырой в одну ломаную: через фигуру
        # тянется прямой штрих. Поэтому разбираем кольца по отдельности.
        ext = getattr(part, "exteriorRing", None)
        if ext is not None:
            ring = ext()
            if ring is not None:
                rings.append(ring)
            n_int = getattr(part, "numInteriorRings", None)
            for i in range(n_int() if n_int else 0):
                inner = part.interiorRing(i)
                if inner is not None:
                    rings.append(inner)
        else:
            rings.append(part)
    for part in rings:
        pts = []
        try:
            vertices = list(part.vertices())
        except Exception:
            vertices = []    # не except/continue: сканер даёт B112
        for v in vertices:
            z = zfix
            if z is None:
                try:
                    z = v.z()
                except Exception:
                    z = None
            if z is None or z != z:
                continue
            pts.append((v.x(), v.y(), float(z)))
        if pts:
            out.append(pts)
    return out


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


def _tool_icon(kind, size=18):
    """Значок кнопки, нарисованный кодом.

    Файлов нет намеренно: значки должны одинаково выглядеть в светлой
    и тёмной теме и не требовать сборки ресурсов.
    """
    from qgis.PyQt.QtGui import QIcon, QPixmap, QPainter, QPen, QColor
    from qgis.PyQt.QtCore import Qt as _Qt, QPointF
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    try:
        hint = getattr(getattr(QPainter, "RenderHint", QPainter),
                       "Antialiasing")
        p.setRenderHint(hint)
    except Exception:  # nosec
        pass
    pen = QPen(QColor("#1d2b28"))
    pen.setWidthF(1.6)
    cap = getattr(getattr(_Qt, "PenCapStyle", _Qt), "RoundCap")
    pen.setCapStyle(cap)
    p.setPen(pen)
    s = size
    if kind == "draw":            # замкнутый контур с вершинами
        pts = [(0.20, 0.62), (0.38, 0.26), (0.72, 0.32),
               (0.82, 0.68), (0.46, 0.82)]
        poly = [QPointF(x * s, y * s) for x, y in pts]
        for a, b in zip(poly, poly[1:] + poly[:1]):
            p.drawLine(a, b)
        p.setBrush(QColor("#C2622C"))
        for q in poly:
            p.drawEllipse(q, 1.7, 1.7)
    elif kind == "layer":         # стопка листов
        for dy, fill in ((0.16, None), (0.40, None), (0.64, "#cfe3f2")):
            if fill:
                p.setBrush(QColor(fill))
            pts = [(0.5, dy), (0.86, dy + 0.14),
                   (0.5, dy + 0.28), (0.14, dy + 0.14)]
            p.drawPolygon(*[QPointF(x * s, y * s) for x, y in pts])
    elif kind == "copy":          # два прямоугольника
        p.drawRect(int(0.16 * s), int(0.16 * s),
                   int(0.50 * s), int(0.56 * s))
        p.setBrush(QColor("#ffffff"))
        p.drawRect(int(0.34 * s), int(0.30 * s),
                   int(0.50 * s), int(0.56 * s))
    elif kind == "png":           # фотоаппарат
        p.drawRect(int(0.12 * s), int(0.30 * s),
                   int(0.76 * s), int(0.48 * s))
        p.drawLine(QPointF(0.34 * s, 0.30 * s),
                   QPointF(0.42 * s, 0.20 * s))
        p.drawLine(QPointF(0.42 * s, 0.20 * s),
                   QPointF(0.62 * s, 0.20 * s))
        p.setBrush(QColor("#cfe3f2"))
        p.drawEllipse(QPointF(0.50 * s, 0.55 * s), 0.16 * s, 0.16 * s)
    elif kind == "top":           # вид сверху: рамка и перекрестие
        p.drawRect(int(0.18 * s), int(0.18 * s),
                   int(0.64 * s), int(0.64 * s))
        pen2 = QPen(QColor("#0E7C66"))
        pen2.setWidthF(1.4)
        pen2.setCapStyle(cap)
        p.setPen(pen2)
        p.drawLine(QPointF(0.50 * s, 0.10 * s),
                   QPointF(0.50 * s, 0.90 * s))
        p.drawLine(QPointF(0.10 * s, 0.50 * s),
                   QPointF(0.90 * s, 0.50 * s))
    elif kind == "ortho":         # куб в параллельной проекции
        front = [(0.20, 0.36), (0.62, 0.36), (0.62, 0.78), (0.20, 0.78)]
        back = [(x + 0.18, y - 0.18) for x, y in front]
        for poly in (front, back):
            pts_ = [QPointF(x * s, y * s) for x, y in poly]
            for a, b in zip(pts_, pts_[1:] + pts_[:1]):
                p.drawLine(a, b)
        for (x1, y1), (x2, y2) in zip(front, back):
            p.drawLine(QPointF(x1 * s, y1 * s), QPointF(x2 * s, y2 * s))
    elif kind == "eye":           # глаз: показ разметки
        p.drawArc(int(0.08 * s), int(0.24 * s),
                  int(0.84 * s), int(0.52 * s), 20 * 16, 140 * 16)
        p.drawArc(int(0.08 * s), int(0.24 * s),
                  int(0.84 * s), int(0.52 * s), 200 * 16, 140 * 16)
        p.setBrush(QColor("#C2622C"))
        p.drawEllipse(QPointF(0.50 * s, 0.50 * s), 0.13 * s, 0.13 * s)
    elif kind == "export":        # куб со стрелкой наружу
        front = [(0.14, 0.42), (0.52, 0.42), (0.52, 0.80), (0.14, 0.80)]
        pts_ = [QPointF(x * s, y * s) for x, y in front]
        for a, b in zip(pts_, pts_[1:] + pts_[:1]):
            p.drawLine(a, b)
        pen2 = QPen(QColor("#0E7C66"))
        pen2.setWidthF(2.0)
        pen2.setCapStyle(cap)
        p.setPen(pen2)
        p.drawLine(QPointF(0.58 * s, 0.46 * s), QPointF(0.88 * s, 0.18 * s))
        p.setBrush(QColor("#0E7C66"))
        tri = [(0.90, 0.10), (0.92, 0.40), (0.62, 0.34)]
        p.drawPolygon(*[QPointF(x * s, y * s) for x, y in tri])
    elif kind == "clear":         # перечёркнутый контур: снять обрезку
        pts = [(0.22, 0.30), (0.62, 0.22), (0.78, 0.58), (0.36, 0.74)]
        poly = [QPointF(x * s, y * s) for x, y in pts]
        for a, b in zip(poly, poly[1:] + poly[:1]):
            p.drawLine(a, b)
        pen2 = QPen(QColor("#C2622C"))
        pen2.setWidthF(2.2)
        pen2.setCapStyle(cap)
        p.setPen(pen2)
        p.drawLine(QPointF(0.20 * s, 0.80 * s), QPointF(0.82 * s, 0.18 * s))
    elif kind == "line":          # незамкнутая ломаная с концами
        pts = [(0.16, 0.70), (0.40, 0.34), (0.62, 0.60), (0.86, 0.28)]
        poly = [QPointF(x * s, y * s) for x, y in pts]
        for a, b in zip(poly, poly[1:]):
            p.drawLine(a, b)
        p.setBrush(QColor("#C2622C"))
        for q in (poly[0], poly[-1]):
            p.drawEllipse(q, 1.9, 1.9)
    elif kind == "undo":          # стрелка назад
        p.drawLine(QPointF(0.24 * s, 0.50 * s), QPointF(0.82 * s, 0.50 * s))
        p.setBrush(QColor("#1d2b28"))
        tri = [(0.16, 0.50), (0.40, 0.34), (0.40, 0.66)]
        p.drawPolygon(*[QPointF(x * s, y * s) for x, y in tri])
    elif kind == "done":          # замкнутый контур с галкой
        pts = [(0.18, 0.30), (0.52, 0.18), (0.72, 0.44),
               (0.44, 0.62)]
        poly = [QPointF(x * s, y * s) for x, y in pts]
        for a, b in zip(poly, poly[1:] + poly[:1]):
            p.drawLine(a, b)
        pen2 = QPen(QColor("#0E7C66"))
        pen2.setWidthF(2.2)
        pen2.setCapStyle(cap)
        p.setPen(pen2)
        p.drawLine(QPointF(0.42 * s, 0.74 * s), QPointF(0.56 * s, 0.88 * s))
        p.drawLine(QPointF(0.56 * s, 0.88 * s), QPointF(0.88 * s, 0.56 * s))
    elif kind == "rebuild":       # круговая стрелка
        rect_pen = QPen(pen)
        p.setPen(rect_pen)
        p.drawArc(int(0.18 * s), int(0.18 * s),
                  int(0.64 * s), int(0.64 * s), 40 * 16, 280 * 16)
        p.setBrush(QColor("#1d2b28"))
        tri = [(0.78, 0.20), (0.90, 0.44), (0.64, 0.42)]
        p.drawPolygon(*[QPointF(x * s, y * s) for x, y in tri])
    p.end()
    return QIcon(pm)


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


class _Prof:
    """Секундомер и счётчики одной перестройки сцены.

    Нужен, чтобы разговор об ускорении шёл по числам, а не по ощущениям.
    Время копится по фазам: чтение гридов с диска, построение мешей,
    окраска (выборка значений по вершинам) и сборка сцены с заливкой
    в видеопамять. Дальше видно, что именно тормозит на конкретных данных.
    """

    def __init__(self):
        self.phases = {}
        self.counts = {}
        self._t0 = time.perf_counter()
        self._mark = self._t0

    def add(self, phase):
        """Отнести время, прошедшее с прошлой отметки, к фазе."""
        now = time.perf_counter()
        self.phases[phase] = self.phases.get(phase, 0.0) + (now - self._mark)
        self._mark = now
        return self

    def skip(self):
        """Сдвинуть отметку, ничего не записывая."""
        self._mark = time.perf_counter()
        return self

    def count(self, key, n=1):
        self.counts[key] = self.counts.get(key, 0) + n
        return self

    def total(self):
        return time.perf_counter() - self._t0

    def megabytes(self):
        """Оценка занятой видеопамяти, МБ.

        Вершина это три числа по четыре байта плюс цвет и нормаль,
        треугольник это три индекса по четыре байта, текстура четыре
        байта на пиксель. Оценка грубая, но она ловит порядок, а именно
        порядок и объясняет, почему сцена вдруг не влезла.
        """
        verts = self.counts.get("verts", 0)
        tris = self.counts.get("tris", 0)
        texpx = self.counts.get("texpx", 0)
        return (verts * 40 + tris * 12 + texpx * 4) / (1024.0 * 1024.0)

    def brief(self):
        """Короткая строка для окна: три числа, которые смотрят чаще всего."""
        return tr("Сцена: %s треугольников, объектов %d, %.2f с.") % (
            _fmt_n(self.counts.get("tris", 0)),
            self.counts.get("items", 0), self.total())

    def report(self):
        """Подробная строка для журнала QGIS."""
        order = [("read", tr("чтение")), ("mesh", tr("меши")),
                 ("color", tr("окраска")), ("vector", tr("векторы")),
                 ("scene", tr("сцена"))]
        parts = ["%s %.2f" % (name, self.phases.get(key, 0.0))
                 for key, name in order if self.phases.get(key)]
        return tr("Перестройка сцены: всего %.2f с (%s). Треугольников %s, "
                  "вершин %s, объектов %d, память около %.0f МБ, "
                  "прочитано гридов %d, взято из кэша %d.") % (
            self.total(), ", ".join(parts),
            _fmt_n(self.counts.get("tris", 0)),
            _fmt_n(self.counts.get("verts", 0)),
            self.counts.get("items", 0), self.megabytes(),
            self.counts.get("reads", 0), self.counts.get("hits", 0))


def _log(msg):
    """Строка в журнал сообщений QGIS, раздел Isoliner3D."""
    try:
        from qgis.core import QgsMessageLog
        QgsMessageLog.logMessage(msg, "Isoliner3D")
    except Exception:  # nosec
        pass


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


def show_viewer(iface):
    """Открывает (или поднимает) окно 3D-просмотра."""
    global _DIALOG
    parent = iface.mainWindow() if iface is not None else None
    try:
        _import_gl()
    except Exception:
        from qgis.PyQt.QtWidgets import QMessageBox
        QMessageBox.information(
            parent, tr("3D-просмотр поверхностей"),
            tr("3D-просмотр недоступен в этой установке плагина."))
        return
    if _DIALOG is None:
        _DIALOG = _build_dialog(parent)
    _DIALOG.refresh_layers()
    _DIALOG.show()
    _DIALOG.raise_()


def _build_dialog(parent):
    import numpy as np
    gl = _import_gl()
    from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer
    try:  # QGIS 3.30+/4: Qgis.GeometryType.*
        from qgis.core import Qgis
        _POINT_GT = Qgis.GeometryType.Point
        _LINE_GT = Qgis.GeometryType.Line
        _POLYGON_GT = Qgis.GeometryType.Polygon
    except Exception:  # старые QGIS 3
        from qgis.core import QgsWkbTypes
        _POINT_GT = QgsWkbTypes.GeometryType.PointGeometry
        _LINE_GT = QgsWkbTypes.GeometryType.LineGeometry
        _POLYGON_GT = QgsWkbTypes.GeometryType.PolygonGeometry
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtWidgets import (
        QDialog, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem,
        QDoubleSpinBox, QPushButton, QLabel, QFormLayout, QSplitter, QWidget,
        QComboBox, QLineEdit, QGroupBox, QSpinBox,
        QFrame, QMenu, QCheckBox, QToolButton)

    # Qt5/Qt6: enum'ы либо плоские, либо в scoped-подклассах
    _CHECKED = getattr(getattr(Qt, "CheckState", Qt), "Checked")
    _UNCHECKED = getattr(getattr(Qt, "CheckState", Qt), "Unchecked")
    _USER_ROLE = getattr(getattr(Qt, "ItemDataRole", Qt), "UserRole")
    _CHECKABLE = getattr(getattr(Qt, "ItemFlag", Qt),
                         "ItemIsUserCheckable")
    _ENABLED = getattr(getattr(Qt, "ItemFlag", Qt), "ItemIsEnabled")

    class _PickView(gl.GLViewWidget):
        """GLViewWidget с колбэком на клик без перетаскивания."""
        pick_cb = None
        dbl_cb = None

        undo_cb = None
        cancel_cb = None
        hover_cb = None
        draw_mode = False
        ortho = False

        def projectionMatrix(self, region=None, viewport=None):
            """Ортогональная проекция вместо перспективной.

            В перспективе объекты, лежащие выше, смещаются в кадре
            к краям, и нарисованная по одной поверхности линия
            переставала совпадать с коридором, собранным из нескольких.
            Сжимать раствор камеры вместо этого нельзя: камера уезжает
            слишком далеко и буфер глубины теряет точность.
            """
            if not self.ortho:
                try:
                    return super().projectionMatrix(region)
                except TypeError:
                    return super().projectionMatrix(region, viewport)
            import math
            from qgis.PyQt.QtGui import QMatrix4x4
            w = max(self.width(), 1)
            h = max(self.height(), 1)
            dist = float(self.opts.get('distance', 10.0)) or 10.0
            fov = float(self.opts.get('fov', 60.0)) or 60.0
            half_h = dist * math.tan(math.radians(fov / 2.0))
            half_w = half_h * (float(w) / float(h))
            m = QMatrix4x4()
            m.ortho(-half_w, half_w, -half_h, half_h,
                    dist * 0.001, dist * 1000.0)
            return m

        def mouseMoveEvent(self, ev):
            if self.draw_mode and self.hover_cb is not None and \
                    not ev.buttons():
                self.hover_cb(*self._evpos(ev))
                return
            super().mouseMoveEvent(ev)

        def mouseDoubleClickEvent(self, ev):
            if self.dbl_cb is not None:
                self.dbl_cb()
            else:
                super().mouseDoubleClickEvent(ev)

        def contextMenuEvent(self, ev):
            """Правая кнопка снимает последнюю вершину контура."""
            if self.undo_cb is not None and self.undo_cb():
                ev.accept()
                return
            super().contextMenuEvent(ev)

        def keyPressEvent(self, ev):
            key = ev.key()
            esc = getattr(getattr(Qt, "Key", Qt), "Key_Escape")
            back = getattr(getattr(Qt, "Key", Qt), "Key_Backspace")
            if key == esc and self.cancel_cb is not None:
                self.cancel_cb()
                return
            if key == back and self.undo_cb is not None:
                self.undo_cb()
                return
            super().keyPressEvent(ev)

        def mousePressEvent(self, ev):
            # В режиме рисования правая кнопка отдана отмене вершины:
            # иначе её забирает камера и до рисовалки нажатие не доходит.
            right = getattr(getattr(Qt, "MouseButton", Qt), "RightButton")
            if self.draw_mode and ev.button() == right:
                if self.undo_cb is not None:
                    self.undo_cb()
                ev.accept()
                return
            self._press = self._evpos(ev)
            super().mousePressEvent(ev)

        def mouseReleaseEvent(self, ev):
            pos = self._evpos(ev)
            pr = getattr(self, "_press", None)
            super().mouseReleaseEvent(ev)
            if (self.pick_cb is not None and pr is not None and
                    abs(pos[0] - pr[0]) < 3 and abs(pos[1] - pr[1]) < 3):
                self.pick_cb(pos[0], pos[1])

        @staticmethod
        def _evpos(ev):
            p = ev.position() if hasattr(ev, "position") else ev.pos()
            return (float(p.x()), float(p.y()))

    class ViewerDialog(QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            # Состояние заводим первым делом: виджеты шлют сигналы уже
            # при сборке окна, и обработчик натыкался на поле, которого
            # ещё нет. Так окно вообще не открывалось. Сцена тоже
            # объявлена заранее и говорит обработчикам «рано».
            self.view = None
            self._pick = None
            self._pick_marker = None
            self._items = []
            self._owners = []
            self._warnings = []
            self._opts = {}
            self._vopts = {}
            self._loading_opts = False
            self._props = None
            self._draw_mode = False
            self._draw_pts = []
            self._draw_ring = []
            self._draw_path = []
            self._draw_line = None
            self._draw_dots = None
            self._hover = None
            self._show_sketch = True
            self._clip_now = None
            self._view_span = 0.0
            from qgis.PyQt.QtCore import QTimer
            self._rebuild_timer = QTimer(self)
            self._rebuild_timer.setSingleShot(True)
            self._rebuild_timer.timeout.connect(self.rebuild)
            self.setWindowTitle(
                tr("Isoliner3D - 3D-просмотр поверхностей"))
            self.resize(1060, 660)
            try:  # Qt6: scoped enum, Qt5: плоский; без кнопок тоже не беда
                flag = getattr(getattr(Qt, "WindowType", Qt),
                               "WindowMinMaxButtonsHint")
                self.setWindowFlags(self.windowFlags() | flag)
            except Exception:  # nosec
                pass

            self._draw_mode = False  # рисуем ли сейчас контур по сцене
            self._draw_pts = []      # вершины рисуемого контура
            self._draw_ring = []     # замкнутый контур для обрезки
            self._draw_path = []     # незамкнутая линия для коридора
            self._view_span = 0.0    # охват прошлой сцены, для кадра
            self._draw_line = None
            self._draw_dots = None
            self._hover = None       # точка под курсором для резинки
            self._show_sketch = True  # показывать ли контур и линию
            self._clip_now = None    # контур обрезки на время сборки
            self._clip_geom_now = None   # он же геометрией, для резки тел
            self._layer_colors_cache = {}   # цвета из стиля слоя
            self._export = []        # части сцены для выгрузки в GLB
            self._vox_colors = {}    # цвета граней вокселей по слою
            self._dirty = False      # сцена отстала от настроек
            self._style_ramp = {}    # цвета вершин по шкале слоя
            self._state_read = False  # читали ли состояние из проекта
            self._owners = []        # чьего слоя каждый элемент сцены
            self._warnings = []      # что сказать человеку после сборки
            self._opts = {}          # id слоя -> персональные настройки
            self._vopts = {}         # id векторного слоя -> его настройки
            self._loading_opts = False
            self._props = None       # окно свойств, создаётся по требованию

            # --- настройки сцены (живут в свойствах строки «Сцена»)
            self.vex = QDoubleSpinBox()
            self.vex.setRange(0.01, 10000.0)
            self.vex.setValue(5.0)
            self.vex.setDecimals(2)
            self.spacing = QDoubleSpinBox()
            self.spacing.setRange(0.0, 1e9)
            self.spacing.setValue(0.0)
            self.spacing.setDecimals(1)
            self.opacity = QDoubleSpinBox()
            self.opacity.setRange(0.0, 95.0)
            self.opacity.setValue(0.0)
            self.opacity.setDecimals(0)
            self.vert_cap = QSpinBox()
            self.vert_cap.setRange(100, 8000)
            self.vert_cap.setSingleStep(100)
            self.vert_cap.setValue(MAX_VERTS_SCENE // 1000)
            self.texside = QSpinBox()
            self.texside.setRange(256, 8192)
            self.texside.setSingleStep(512)
            self.texside.setValue(2048)
            for w in (self.vex, self.spacing, self.opacity, self.texside,
                      self.vert_cap):
                w.valueChanged.connect(lambda *_a: self._schedule_rebuild())
            self.clip_combo = QComboBox()
            self.clip_combo.setToolTip(tr(
                "Полигональный слой, по которому режется сцена. "
                "Годится любой замкнутый контур: подсчётный блок, "
                "лицензионный участок, нарисованный от руки полигон."))
            self.clip_side = QComboBox()
            for label, key in ((tr("Оставить внутри"), "in"),
                               (tr("Убрать внутри"), "out"),
                               (tr("Слева от линии"), "left"),
                               (tr("Справа от линии"), "right"),
                               (tr("Коридор вдоль линии"), "corridor")):
                self.clip_side.addItem(label, key)
            self.clip_width = QDoubleSpinBox()
            self.clip_width.setRange(0.0, 1e9)
            self.clip_width.setDecimals(1)
            self.clip_width.setValue(250.0)
            self.clip_width.setToolTip(tr(
                "Полуширина коридора вдоль линии, в единицах карты. "
                "Профиль разреза и данные по обе стороны от него."))
            self.clip_width.setFixedWidth(84)
            self.clip_width.setPrefix("\u00b1 ")
            for w in (self.clip_combo, self.clip_side, self.clip_width):
                sig = getattr(w, "currentIndexChanged", None) or \
                    w.valueChanged
                sig.connect(lambda *_a: self._schedule_rebuild())
            self.auto_rebuild = QCheckBox(tr("Обновлять автоматически"))
            self.auto_rebuild.setChecked(False)
            self.auto_rebuild.setToolTip(tr(
                "Обычно сцена считается по кнопке «Обновить сцену», "
                "а отметки и ползунки только записывают, что показать. "
                "С этой галкой сцена пересобирается сразу на каждую "
                "правку: удобно на лёгких данных."))
            self.vert_cap.setToolTip(tr(
                "Сколько вершин отдаётся на всю сцену. Бюджет делится "
                "между слоями, и объекты, на которые его не хватило, "
                "в сцену не попадают: об этом пишет строка состояния. "
                "Поднимайте, если тела показаны не полностью."))
            self.texside.setToolTip(tr(
                "Сторона текстуры по длинной оси охвата. Больше значение - "
                "детальнее карта на поверхности и больше видеопамяти."))
            self.scene_box = QGroupBox(tr("Сцена"))
            sf = QFormLayout(self.scene_box)
            sf.addRow(tr("Вертикальное преувеличение"), self.vex)
            sf.addRow(tr("Разнос по Z (шаг вниз)"), self.spacing)
            sf.addRow(tr("Прозрачность поверхностей (процентов)"),
                      self.opacity)
            sf.addRow(tr("Сторона текстуры (пикселей)"), self.texside)
            sf.addRow(tr("Предел вершин в сцене (тысяч)"), self.vert_cap)
            sf.addRow(tr("Обрезка по контуру"), self.clip_combo)
            sf.addRow(tr("Кусок"), self.clip_side)
            sf.addRow(self.auto_rebuild)

            self.legend_pix = QLabel()
            self.legend_txt = QLabel("")
            self.legend_pix.hide()
            self.legend_txt.hide()
            self.info = QLabel("")
            self.info.setWordWrap(True)

            # --- вкладка «Слои»: растры проекта плюс закреплённая «Сцена»
            self.layer_list = QListWidget()
            self.filter_edit = QLineEdit()
            self.filter_edit.setPlaceholderText(tr("Фильтр слоёв…"))
            self.filter_edit.textChanged.connect(self._apply_filter)
            fl = QHBoxLayout()
            fl.addWidget(self.filter_edit, 1)
            b_all = QPushButton(tr("Все"))
            b_none = QPushButton(tr("Ничего"))
            b_all.clicked.connect(lambda: self._check_visible(True))
            b_none.clicked.connect(lambda: self._check_visible(False))
            fl.addWidget(b_all)
            fl.addWidget(b_none)

            # параметры растра: живут в окне свойств, не на главном окне
            self.opt_box = QGroupBox(tr("Параметры слоя"))
            self.mode_combo = QComboBox()
            for label, key in ((tr("Авто"), "auto"),
                               (tr("Поверхность"), "surface"),
                               (tr("Тело пласта"), "body"),
                               (tr("Изоповерхность по кубу"), "iso"),
                               (tr("Воксели по кубу"), "vox")):
                self.mode_combo.addItem(label, key)
            self.zband = QComboBox()
            self.color_combo = QComboBox()
            self.color_btn = QPushButton()
            self.color_btn.setFixedSize(46, 22)
            self.color_btn.setToolTip(tr("Задать свой цвет"))
            self.color_btn.clicked.connect(self._pick_solid_color)
            self.aband = QComboBox()
            self.iso_level = QDoubleSpinBox()
            self.iso_level.setRange(-1e9, 1e9)
            self.iso_level.setDecimals(3)
            self.iso_level.setToolTip(tr(
                "Отсечка: внутрь тела попадает всё, что не меньше этого "
                "значения. Каналы грида считаются уровнями куба."))
            of = QFormLayout(self.opt_box)
            of.addRow(tr("Режим"), self.mode_combo)
            of.addRow(tr("Канал высот (Z)"), self.zband)
            crow = QHBoxLayout()
            crow.addWidget(self.color_combo, 1)
            crow.addWidget(self.color_btn, 0)
            of.addRow(tr("Окраска"), crow)
            of.addRow(tr("Канал атрибута"), self.aband)
            self.vox_classes = QSpinBox()
            self.vox_classes.setRange(1, 32)
            self.vox_classes.setValue(8)
            self.vox_classes.setToolTip(tr(
                "На сколько интервалов раскладывается содержание при "
                "окраске вокселей. Соседние грани одного интервала "
                "сливаются в один прямоугольник, поэтому чем меньше "
                "интервалов, тем легче сцена."))
            self.vox_merge = QCheckBox(tr("Сливать соседние грани"))
            self.vox_merge.setChecked(True)
            self.vox_merge.setToolTip(tr(
                "Слияние делает сцену в разы легче, но оболочка перестаёт "
                "быть замкнутой: длинный прямоугольник упирается в два "
                "коротких, общего ребра у них нет. Снимите флаг, если "
                "по этой модели считается объём."))
            of.addRow(tr("Отсечка куба"), self.iso_level)
            of.addRow(tr("Интервалов окраски"), self.vox_classes)
            of.addRow("", self.vox_merge)
            self.iso_level.valueChanged.connect(self._save_opts)
            self.vox_classes.valueChanged.connect(self._save_opts)
            self.vox_merge.toggled.connect(self._save_opts)
            for w in (self.mode_combo, self.zband, self.aband):
                w.currentIndexChanged.connect(self._save_opts)
            self.color_combo.currentIndexChanged.connect(self._color_changed)

            self.layer_list.itemChanged.connect(self._item_toggled)
            self.layer_list.currentItemChanged.connect(self._load_props)
            self._wire_props(self.layer_list)

            # --- вкладка «Векторы»: любые векторные слои проекта
            # параметры векторного слоя: тоже в окне свойств
            self.vec_box = QGroupBox(tr("Параметры слоя"))
            self.vec_zsrc = QComboBox()
            for label, key in ((tr("Своя высота геометрии (Z)"), "geom"),
                               (tr("Отметка из поля"), "field"),
                               (tr("Отметка с поверхности"), "surf"),
                               (tr("Плоско, на нуле"), "flat")):
                self.vec_zsrc.addItem(label, key)
            self.vec_zoff = QDoubleSpinBox()
            self.vec_zoff.setRange(-100000.0, 100000.0)
            self.vec_zoff.setDecimals(2)
            self.vec_zoff.setSingleStep(1.0)
            self.vec_zoff.setValue(0.0)
            self.vec_zoff.setToolTip(tr(
                "Сдвиг слоя по вертикали в метрах, поверх выбранного "
                "источника высоты. Небольшой подъём убирает спор "
                "за глубину, когда линия лежит ровно на поверхности."))
            self.vec_zsurf = QComboBox()
            self.vec_zsurf.setToolTip(tr(
                "Поверхность, с которой берётся отметка. Значение "
                "читается в каждой вершине, поэтому объект ложится "
                "на рельеф, а не встаёт на общую отметку. Там, где "
                "у поверхности нет данных, объект обрезается."))
            self.vec_zfield = QComboBox()
            self.vec_poly = QComboBox()
            for label, key in ((tr("Контуром"), "outline"),
                               (tr("Телом (заливка)"), "solid"),
                               (tr("Призмой (от поля до поля)"), "prism")):
                self.vec_poly.addItem(label, key)
            self.vec_poly.setToolTip(tr(
                "Вложенные контуры уровней осмысленно смотреть линиями. "
                "Заливка нужна телам пласта и полиэдрам."))
            self.vec_base = QComboBox()
            self.vec_base.setToolTip(tr(
                "Низ призмы берётся с этой поверхности: подошва дома "
                "садится на рельеф, а не на заданную отметку."))
            self.vec_htop = QComboBox()
            for label, key in ((tr("Верх: поле верха"), "field"),
                               (tr("Верх: низ плюс высота из поля"),
                                "add")):
                self.vec_htop.addItem(label, key)
            self.vec_ztop = QComboBox()
            self.vec_ztop.setToolTip(tr(
                "Поле верха призмы либо высоты над низом, смотря что "
                "выбрано строкой выше."))
            self.vec_kind = QComboBox()
            for label, key in ((tr("Как есть"), "plain"),
                               (tr("Скважины (стволы по отметкам)"),
                                "wells")):
                self.vec_kind.addItem(label, key)
            self.wells_label = QComboBox()
            self.wells_fields = QListWidget()
            self.wells_fields.setMaximumHeight(150)
            vf = QFormLayout(self.vec_box)
            vf.addRow(tr("Точечный слой"), self.vec_kind)
            vf.addRow(tr("Полигональный слой"), self.vec_poly)
            vf.addRow(tr("Источник высоты"), self.vec_zsrc)
            vf.addRow(tr("Поле отметки"), self.vec_zfield)
            vf.addRow(tr("Поверхность отметки"), self.vec_zsurf)
            vf.addRow(tr("Смещение по вертикали, м"), self.vec_zoff)
            vf.addRow(tr("Низ призмы с поверхности"), self.vec_base)
            vf.addRow(tr("Верх призмы"), self.vec_htop)
            vf.addRow(tr("Поле верха или высоты"), self.vec_ztop)
            vf.addRow(tr("Поле подписи скважин"), self.wells_label)
            vf.addRow(tr("Поля отметок"), self.wells_fields)
            for w in (self.vec_kind, self.vec_poly, self.vec_zsrc,
                      self.vec_zfield, self.vec_zsurf, self.vec_ztop,
                      self.vec_base, self.vec_htop, self.wells_label):
                w.currentIndexChanged.connect(self._save_vec_opts)
            self.vec_zoff.valueChanged.connect(self._save_vec_opts)
            self.wells_fields.itemChanged.connect(self._save_vec_opts)

            # --- разрез: свойство линейного слоя, а не отдельная вкладка
            self.sec_box = QGroupBox(tr("Разрез"))
            self.sec_on = QCheckBox(tr("Показывать плоскостью разреза"))
            self.sec_on.setToolTip(tr(
                "Линия становится вертикальной лентой от zmin до zmax "
                "из полей определения разреза."))
            self.draw_combo = QComboBox()
            self.draw_combo.setToolTip(tr(
                "Чертёж разреза в координатах «расстояние вдоль линии на "
                "отметку». Ложится текстурой на ленту разреза. Годится "
                "группа слоёв целиком."))
            sf2 = QFormLayout(self.sec_box)
            sf2.addRow(self.sec_on)
            sf2.addRow(tr("Чертёж разреза"), self.draw_combo)
            self.sec_on.stateChanged.connect(self._save_vec_opts)
            self.draw_combo.currentIndexChanged.connect(self._save_vec_opts)

            # Инструменты живут поверх сцены маленькими значками, как
            # на холсте карты: список слоёв не надо теснить кнопками,
            # а рука и глаз остаются там, где идёт работа.
            def tool(kind, text, slot, checkable=False):
                b = QToolButton(self)
                b.setIcon(_tool_icon(kind))
                b.setToolTip(text)
                b.setAutoRaise(True)
                b.setCheckable(checkable)
                if checkable:
                    b.toggled.connect(slot)
                else:
                    b.clicked.connect(slot)
                return b

            btn_top = tool("top", tr("Вид сверху, план"),
                           lambda: self._set_view(90, -90, plan=True))
            self.btn_ortho = tool(
                "ortho", tr("Параллельная проекция вместо перспективной"),
                self._set_ortho, True)
            self.btn_draw = tool(
                "draw", tr("Рисовать контур по поверхности: клик ставит "
                           "вершину."), self._draw_toggle, True)
            self.btn_undo = tool("undo", tr("Снять последнюю вершину"),
                                 self._draw_undo)
            self.btn_done = tool("done", tr("Замкнуть контур и обрезать "
                                            "сцену"), self._draw_close)
            self.btn_line = tool("line", tr("Завершить линию и резать "
                                            "по ней"), self._draw_line_done)
            for b in (self.btn_undo, self.btn_done, self.btn_line):
                b.setVisible(False)
            self.btn_sketch = tool(
                "eye", tr("Показывать разметку: контур и линию разреза"),
                self._toggle_sketch, True)
            self.btn_sketch.setChecked(True)
            btn_clip_off = tool(
                "clear", tr("Снять обрезку, наброски и точку опроса"),
                self._clip_clear_all)
            btn_draw_save = tool(
                "layer", tr("Сохранить нарисованный контур слоем проекта"),
                self._draw_save)
            btn_export = tool(
                "export", tr("Выгрузить сцену в файл GLB"),
                self._export_glb)
            btn_copy = tool(
                "copy", tr("Положить кадр сцены в буфер обмена (Ctrl+C)"),
                self._copy_png)
            btn_png = tool("png", tr("Сохранить кадр сцены в файл PNG"),
                           self._save_png)
            # Обновление отделено от отметок видимости. Отметка и ползунок
            # только записывают, что показывать, а считает сцену эта
            # кнопка. На тяжёлом кубе разница решающая: без неё каждый
            # щелчок в списке тянул полную пересборку.
            self.btn = tool("rebuild", tr("Обновить сцену"), self.rebuild)
            self.auto_rebuild.toggled.connect(self._auto_toggled)

            left = QWidget()
            lv = QVBoxLayout(left)
            lv.addLayout(fl)
            lv.addWidget(self.layer_list, 1)
            lv.addWidget(self.legend_pix)
            lv.addWidget(self.legend_txt)
            lv.addWidget(self.info)

            from qgis.PyQt.QtGui import QKeySequence
            from qgis.PyQt.QtWidgets import QShortcut
            std = getattr(getattr(QKeySequence, "StandardKey",
                                  QKeySequence), "Copy")
            copy_key = QShortcut(std, self)
            copy_key.activated.connect(self._copy_png)

            self.view = _PickView()
            self.view.setBackgroundColor((250, 250, 248))
            self.view.pick_cb = self._pick_at
            self.view.dbl_cb = self._draw_close
            self.view.undo_cb = self._draw_undo
            self.view.hover_cb = self._draw_hover
            self.view.cancel_cb = self._draw_cancel
            # Список сцены следует за деревом карты: добавили слой,
            # убрали, переставили - список и порядок отрисовки
            # обновляются сами, руками пересобирать не нужно.
            try:
                proj_w = QgsProject.instance()
                proj_w.layersAdded.connect(self._tree_changed)
                proj_w.layersRemoved.connect(self._tree_changed)
                root_w = proj_w.layerTreeRoot()
                root_w.layerOrderChanged.connect(self._tree_changed)
                root_w.addedChildren.connect(self._tree_changed)
                root_w.removedChildren.connect(self._tree_changed)
            except Exception:  # nosec
                pass
            focus = getattr(getattr(Qt, "FocusPolicy", Qt), "StrongFocus")
            self.view.setFocusPolicy(focus)
            self._pick = None
            self._pick_marker = None
            # тонкая тёмная рамка вокруг сцены, как у холста карты QGIS
            frame = QFrame()
            frame.setFrameShape(
                getattr(getattr(QFrame, "Shape", QFrame), "Box"))
            frame.setLineWidth(1)
            frame.setStyleSheet("QFrame { border: 1px solid #7a7a7a; }")
            fv = QVBoxLayout(frame)
            fv.setContentsMargins(1, 1, 1, 1)
            fv.addWidget(self.view)

            self.tools = QWidget(frame)
            tb = QHBoxLayout(self.tools)
            tb.setContentsMargins(3, 3, 3, 3)
            tb.setSpacing(2)
            self.btn.setParent(self.tools)
            tb.addWidget(self.btn)
            sep = QFrame(self.tools)
            sep.setFrameShape(getattr(getattr(QFrame, "Shape", QFrame),
                                      "VLine"))
            sep.setFrameShadow(getattr(getattr(QFrame, "Shadow", QFrame),
                                       "Sunken"))
            tb.addWidget(sep)
            for b in (btn_top, self.btn_ortho, self.btn_draw,
                      self.btn_undo,
                      self.btn_done, self.btn_line, self.btn_sketch,
                      btn_clip_off,
                      btn_draw_save, btn_export, btn_copy, btn_png):
                b.setParent(self.tools)
                tb.addWidget(b)
            # Полуширина коридора стоит здесь же: она нужна ровно тогда,
            # когда режут линией, а в свойствах сцены её никто не искал.
            self.clip_width.setParent(self.tools)
            tb.addWidget(self.clip_width)
            self.clip_side.currentIndexChanged.connect(
                lambda *_a: self._sync_corridor())
            # Стиль вешаем только на саму плашку, по имени. Без имени
            # он распространялся на кнопки внутри и стирал у них
            # подсветку: нажатие никак не отзывалось.
            self.tools.setObjectName("isoliner3dTools")
            self.tools.setStyleSheet(
                "#isoliner3dTools { background: rgba(255,255,255,205);"
                " border: 1px solid rgba(0,0,0,45); border-radius: 4px; }"
                "#isoliner3dTools QToolButton { border: 1px solid"
                " transparent; border-radius: 3px; padding: 2px; }"
                "#isoliner3dTools QToolButton:hover { background:"
                " rgba(14,124,102,45); border-color: rgba(14,124,102,120); }"
                "#isoliner3dTools QToolButton:pressed { background:"
                " rgba(14,124,102,110); }"
                "#isoliner3dTools QToolButton:checked { background:"
                " rgba(14,124,102,90); border-color: rgba(14,124,102,180); }"
                "#isoliner3dTools QToolButton[dirty=\"yes\"] { background:"
                " rgba(208,126,26,105); border-color:"
                " rgba(208,126,26,190); }")
            self.tools.move(8, 8)
            self._sync_corridor()
            self.tools.adjustSize()
            self.tools.raise_()

            split = QSplitter()
            split.addWidget(left)
            split.addWidget(frame)
            split.setStretchFactor(1, 1)
            root = QHBoxLayout(self)
            root.addWidget(split)
            self._items = []

        def _wire_props(self, widget):
            """Свойства по двойному клику и по правой кнопке.

            Пользователь пришёл из QGIS и ждёт свойств именно там,
            поэтому главное окно оставлено под список, а все настройки
            живут в отдельном немодальном окне.
            """
            widget.itemDoubleClicked.connect(
                lambda *_a: self._open_props())
            policy = getattr(getattr(Qt, "ContextMenuPolicy", Qt),
                             "CustomContextMenu")
            widget.setContextMenuPolicy(policy)
            widget.customContextMenuRequested.connect(
                lambda pos, w=widget: self._context_menu(w, pos))

        def _context_menu(self, widget, pos):
            item = widget.itemAt(pos)
            if item is not None:
                widget.setCurrentItem(item)
            menu = QMenu(self)
            act = menu.addAction(tr("Свойства…"))
            act.triggered.connect(self._open_props)
            # exec_ снят в Qt6, exec есть в обоих: берём по имени
            show = getattr(menu, "exec", None) or getattr(menu, "exec_")
            show(widget.mapToGlobal(pos))

        def _open_props(self, *_a):
            """Открыть окно свойств для выделенной строки."""
            if self._props is None:
                dlg = QDialog(self)
                dlg.setWindowTitle(tr("Свойства"))
                lay = QVBoxLayout(dlg)
                lay.addWidget(self.scene_box)
                lay.addWidget(self.opt_box)
                lay.addWidget(self.vec_box)
                lay.addWidget(self.sec_box)
                lay.addStretch(1)
                dlg.resize(430, 420)
                self._props = dlg
            self._sync_props()
            self._props.show()
            self._props.raise_()

        def _sync_props(self):
            """Показать в окне свойств то, что относится к выделенному.

            Список один, поэтому набор свойств выбирается по типу слоя:
            растру каналы и окраска, вектору источник высоты, линейному
            слою вдобавок разрез. Внутри векторной группы строки тоже
            подбираются по типу геометрии и выбранному источнику.
            """
            if self._props is None:
                return
            item = self.layer_list.currentItem()
            lyr = self._current_layer()
            scene = item is None or item.data(_USER_ROLE) == _SCENE_KEY
            raster = isinstance(lyr, QgsRasterLayer)
            vector = isinstance(lyr, QgsVectorLayer)
            line = vector and self._geom_kind(lyr) == "line"
            self.scene_box.setVisible(scene)
            self.opt_box.setVisible(raster)
            self.vec_box.setVisible(vector)
            self.sec_box.setVisible(line)
            if vector:
                self._sync_vec_enabled()
            title = tr("Свойства сцены")
            if lyr is not None:
                title = tr("Свойства слоя: %s") % lyr.name()
            self._props.setWindowTitle(title)

        def _export_glb(self):
            """Выгрузить показанное в файл GLB.

            Выгружается ровно то, что видно: обрезали коридором, уйдёт
            коридор. Иначе человек получит не ту модель, которую смотрел.
            """
            if not self._export:
                self.info.setText(tr("Выгружать нечего: сцена пуста."))
                return
            from qgis.PyQt.QtWidgets import QFileDialog
            fn, _ = QFileDialog.getSaveFileName(
                self, tr("Выгрузить сцену"), "isoliner_3d.glb",
                "glTF (*.glb)")
            if not fn:
                return
            # Настоящие высоты верны для расчёта, но пласт в километры
            # по площади и десятки метров по мощности сплющивается
            # в блин. Поэтому спрашиваем, а не решаем за человека.
            vex = float(self.vex.value() or 1.0)
            keep_vex = False
            if abs(vex - 1.0) > 1e-6:
                from qgis.PyQt.QtWidgets import QMessageBox
                ans = QMessageBox.question(
                    self, tr("Выгрузить сцену"),
                    tr("Применить вертикальное преувеличение %.2f?\n"
                       "Да - модель как на экране.\n"
                       "Нет - настоящие высоты, годные для расчёта.")
                    % vex)
                yes = getattr(getattr(QMessageBox, "StandardButton",
                                      QMessageBox), "Yes")
                keep_vex = ans == yes
            try:
                from .gltf import write_glb
                import numpy as np
                parts = self._export
                if keep_vex:
                    parts = []
                    for part in self._export:
                        v = np.asarray(part["verts"], dtype=float).copy()
                        zc = float(np.mean(v[:, 2])) if len(v) else 0.0
                        v[:, 2] = (v[:, 2] - zc) * vex + zc
                        parts.append(dict(part, verts=v))
                for part in parts:
                    _log(tr("Часть %s: вершин %d, граней %d")
                         % (part.get("name", "?"), len(part["verts"]),
                            len(part["faces"])))
                size = write_glb(fn, parts)
                self.info.setText(
                    tr("Выгружено частей: %d, файл %.1f МБ.")
                    % (len(parts), size / (1024.0 * 1024.0)))
            except Exception as err:
                self.info.setText(tr("Выгрузка не удалась: %s") % err)
                _log(tr("Выгрузка не удалась: %s") % err)

        def _copy_png(self):
            """Кадр сцены в буфер обмена.

            Защита от раннего вызова: обработчик может сработать
            в момент сборки окна, когда сцены ещё нет.

            Чаще всего снимок нужен, чтобы сразу вставить его в письмо
            или в записку, а не чтобы хранить файлом.
            """
            if self.view is None:
                return
            try:
                from qgis.PyQt.QtWidgets import QApplication
                img = self.view.grabFramebuffer()
                QApplication.clipboard().setImage(img)
                self.info.setText(tr("Снимок скопирован в буфер обмена."))
            except Exception as err:
                self.info.setText(tr("Скопировать не удалось: %s") % err)
                _log(tr("Скопировать не удалось: %s") % err)

        def _set_ortho(self, on):
            """Параллельная проекция: масштаб одинаков по всему кадру."""
            self.view.ortho = bool(on)
            self.view.update()

        def _toggle_sketch(self, on):
            """Показ разметки: сама обрезка при этом работает.

            Линия нужна, пока размечаешь, и мешает, когда смотришь
            результат. Прятать её через снятие обрезки было бы неверно:
            это разные вещи.
            """
            self._show_sketch = bool(on)
            self._draw_refresh(
                closed=bool(self._draw_ring) and not self._draw_mode)

        def _state_save(self):
            """Сложить настройки сцены в проект QGIS.

            Именно в проект, а не отдельным файлом: настройки описывают
            те же слои и тот же участок, поэтому должны ехать вместе
            с проектом и переживать передачу другому человеку.
            """
            import json
            try:
                state = {
                    "checked": [
                        self.layer_list.item(i).data(_USER_ROLE)
                        for i in range(self.layer_list.count())
                        if self.layer_list.item(i).checkState() == _CHECKED],
                    "opts": self._opts,
                    "vopts": self._vopts,
                    "vex": float(self.vex.value()),
                    "spacing": float(self.spacing.value()),
                    "opacity": float(self.opacity.value()),
                    "texside": int(self.texside.value()),
                    "vert_cap": int(self.vert_cap.value()),
                    "clip": self.clip_combo.currentData(),
                    "side": self.clip_side.currentData(),
                    "width": float(self.clip_width.value()),
                    "ring": self._draw_ring,
                    "path": self._draw_path,
                }
                QgsProject.instance().writeEntry(
                    "Isoliner3D", "state", json.dumps(state,
                                                      ensure_ascii=False))
            except Exception as err:  # nosec
                _log(tr("Не удалось сохранить состояние сцены: %s") % err)

        def _state_load(self):
            """Достать настройки сцены из проекта."""
            import json
            raw, ok = QgsProject.instance().readEntry("Isoliner3D", "state")
            if not ok or not raw:
                return False
            try:
                state = json.loads(raw)
            except Exception:  # nosec
                return False
            self._loading_opts = True
            try:
                self._opts = dict(state.get("opts") or {})
                self._vopts = dict(state.get("vopts") or {})
                self._draw_ring = [tuple(p) for p in state.get("ring") or []]
                self._draw_path = [tuple(p) for p in state.get("path") or []]
                self.vex.setValue(state.get("vex", 5.0))
                self.spacing.setValue(state.get("spacing", 0.0))
                self.opacity.setValue(state.get("opacity", 0.0))
                self.texside.setValue(int(state.get("texside", 2048)))
                self.vert_cap.setValue(int(state.get(
                    "vert_cap", MAX_VERTS_SCENE // 1000)))
                self.clip_width.setValue(state.get("width", 250.0))
                i = _find_data(self.clip_combo, state.get("clip"))
                self.clip_combo.setCurrentIndex(max(i, 0))
                j = _find_data(self.clip_side, state.get("side"))
                self.clip_side.setCurrentIndex(max(j, 0))
                checked = set(state.get("checked") or [])
                self.layer_list.blockSignals(True)
                for i in range(self.layer_list.count()):
                    it = self.layer_list.item(i)
                    key = it.data(_USER_ROLE)
                    if key == _SCENE_KEY:
                        continue
                    it.setCheckState(_CHECKED if key in checked
                                     else _UNCHECKED)
                self.layer_list.blockSignals(False)
            finally:
                self._loading_opts = False
            self._sync_corridor()
            return True

        def _clip_clear(self):
            """Убрать обрезку и наброски, вернуть сцену целиком."""
            self._draw_pts = []
            self._draw_ring = []
            self._draw_path = []
            self._hover = None
            self._draw_toggle(False)
            self._draw_refresh()
            i = _find_data(self.clip_combo, None)
            if i >= 0:
                self.clip_combo.setCurrentIndex(i)
            self.info.setText(tr("Обрезка снята, сцена показана целиком."))
            self._schedule_rebuild(0)

        def _set_view(self, elevation, azimuth, plan=False):
            """Поставить камеру в заданный ракурс.

            `plan` заодно включает параллельную проекцию: план
            с перспективой это не план, объекты на разной высоте
            смещаются в кадре и перестают совпадать в плане.
            """
            opts = self.view.opts
            if plan and not self.view.ortho:
                # План без перспективы: включаем параллельную проекцию,
                # а не сжимаем раствор камеры. Сжатие уводило камеру
                # далеко и портило точность буфера глубины.
                self.btn_ortho.setChecked(True)
            opts['elevation'] = elevation
            opts['azimuth'] = azimuth
            self.view.update()

        def _save_png(self):
            from qgis.PyQt.QtWidgets import QFileDialog
            fn, _ = QFileDialog.getSaveFileName(
                self, tr("Сохранить снимок"), "isoliner_3d.png",
                "PNG (*.png)")
            if not fn:
                return
            img = self.view.grabFramebuffer()
            img.save(fn, "PNG")
            self.info.setText(tr("Снимок сохранён: %s") % os.path.basename(fn))

        def _show_legend(self, vmin, vmax):
            import numpy as np
            from qgis.PyQt.QtGui import QImage, QPixmap
            w, h = 220, 14
            rgba = (colormap(np.tile(np.linspace(0, 1, w), (h, 1)))
                    * 255).astype(np.uint8)
            self._legend_bytes = rgba.tobytes()  # держим буфер живым
            img = QImage(self._legend_bytes, w, h, w * 4,
                         QImage.Format.Format_RGBA8888)
            self.legend_pix.setPixmap(QPixmap.fromImage(img))
            self.legend_txt.setText("%.4g … %.4g" % (vmin, vmax))
            self.legend_pix.show()
            self.legend_txt.show()

        def _hide_legend(self):
            self.legend_pix.hide()
            self.legend_txt.hide()

        def refresh_layers(self):
            """Пересобирает список, сохраняя отметки и выбор.

            Список один: растры и векторы вместе, как в дереве QGIS. Тип
            слоя виден пометкой в строке, потому что от него зависит,
            какие свойства человек увидит.
            """
            proj = QgsProject.instance()
            checked = {self.layer_list.item(i).data(_USER_ROLE)
                       for i in range(self.layer_list.count())
                       if self.layer_list.item(i).checkState() == _CHECKED}
            current = None
            if self.layer_list.currentItem() is not None:
                current = self.layer_list.currentItem().data(_USER_ROLE)

            self.layer_list.blockSignals(True)
            self.layer_list.clear()
            head = QListWidgetItem(tr("Сцена"))
            head.setData(_USER_ROLE, _SCENE_KEY)
            font = head.font()
            font.setBold(True)
            head.setFont(font)
            head.setToolTip(tr("Свойства сцены: двойной клик"))
            self.layer_list.addItem(head)

            marks = {"raster": tr("растр"), "point": tr("точки"),
                     "line": tr("линии"), "polygon": tr("полигоны")}
            for lyr in _map_order(proj):
                if isinstance(lyr, QgsRasterLayer):
                    kind = "raster"
                elif isinstance(lyr, QgsVectorLayer):
                    kind = self._geom_kind(lyr)
                else:
                    continue
                it = QListWidgetItem("%s  ·  %s" % (lyr.name(),
                                                    marks.get(kind, "")))
                it.setData(_USER_ROLE, lyr.id())
                it.setFlags(it.flags() | _CHECKABLE)
                it.setCheckState(_CHECKED if lyr.id() in checked
                                 else _UNCHECKED)
                self.layer_list.addItem(it)
            self.layer_list.blockSignals(False)

            if current is not None:
                for i in range(self.layer_list.count()):
                    if self.layer_list.item(i).data(_USER_ROLE) == current:
                        self.layer_list.setCurrentRow(i)
                        break

            prev_cl = self.clip_combo.currentData()
            self.clip_combo.blockSignals(True)
            self.clip_combo.clear()
            self.clip_combo.addItem(tr("(нет)"), None)
            self.clip_combo.addItem(tr("Нарисованный контур"), _DRAWN_KEY)
            self.clip_combo.addItem(tr("Нарисованная линия"), _DRAWNL_KEY)
            for lyr in proj.mapLayers().values():
                if not isinstance(lyr, QgsVectorLayer):
                    continue
                kind = self._geom_kind(lyr)
                if kind in ("polygon", "line"):
                    self.clip_combo.addItem(lyr.name(), lyr.id())
            icl = _find_data(self.clip_combo, prev_cl)
            self.clip_combo.setCurrentIndex(max(icl, 0))
            self.clip_combo.blockSignals(False)

            prev_dr = self.draw_combo.currentData()
            self.draw_combo.blockSignals(True)
            self.draw_combo.clear()
            self.draw_combo.addItem(tr("(нет)"), None)
            for grp in proj.layerTreeRoot().findGroups():
                if grp.findLayers():
                    self.draw_combo.addItem(tr("Группа: %s") % grp.name(),
                                            ("group", grp.name()))
            for lyr in proj.mapLayers().values():
                self.draw_combo.addItem(lyr.name(), ("layer", lyr.id()))
            idr = _find_data(self.draw_combo, prev_dr)
            self.draw_combo.setCurrentIndex(max(idr, 0))
            self.draw_combo.blockSignals(False)

            self._load_props()
            if not self._state_read:
                self._state_read = True
                if self._state_load():
                    self.info.setText(tr("Настройки сцены взяты "
                                         "из проекта."))

        def _current_layer(self):
            """Слой выделенной строки или None для «Сцены»."""
            item = self.layer_list.currentItem()
            if item is None:
                return None
            key = item.data(_USER_ROLE)
            if key == _SCENE_KEY:
                return None
            return QgsProject.instance().mapLayer(key)

        def _load_props(self, *_a):
            """Показать свойства выделенной строки по её типу."""
            lyr = self._current_layer()
            if isinstance(lyr, QgsRasterLayer):
                self._load_opts(self.layer_list.currentItem())
            elif isinstance(lyr, QgsVectorLayer):
                self._load_vec_opts()
            self._sync_props()

        def _vec_layer(self, item=None):
            """Векторный слой выделенной строки списка векторов."""
            lyr = self._current_layer()
            return lyr if isinstance(lyr, QgsVectorLayer) else None

        @staticmethod
        def _geom_kind(lyr):
            """point, line, polygon или пусто."""
            gt = lyr.geometryType()
            name = getattr(gt, "name", "")
            if gt == _POINT_GT or name == "Point":
                return "point"
            if gt == _LINE_GT or name == "Line":
                return "line"
            if gt == _POLYGON_GT or name == "Polygon":
                return "polygon"
            return ""

        def _default_vopts(self, lyr):
            """Разумные умолчания по типу геометрии.

            Полигоны с Z раньше жили на вкладке «Тела» и рисовались телом
            по своей геометрии, поэтому для них источник высоты - своя Z.
            Точечный слой по умолчанию рисуется как есть, скважины
            включаются явно.
            """
            has_z = _layer_has_z(lyr)
            return {"kind": "plain", "as_section": False, "draw": None,
                    "zsrc": "geom" if has_z else "field", "zsurf": None,
                    "zoff": 0.0,
                    "poly": "solid" if has_z else "outline",
                    "ztop": None, "base": None, "htop": "field",
                    "zfield": None,
                    "wells_label": None, "wells_fields": []}

        def _opts_of(self, lyr):
            """Настройки слоя, с умолчаниями по типу геометрии.

            Раньше рисование читало словарь напрямую, и слой, свойства
            которого ни разу не открывали, получал пустые настройки:
            полигоны с Z уходили в линии вместо тела. Умолчания заводятся
            здесь же, чтобы показ и диалог видели одно и то же.
            """
            if lyr is None:
                return {}
            return self._vopts.setdefault(lyr.id(), self._default_vopts(lyr))

        def _load_vec_opts(self, *_a):
            """Показать в свойствах настройки выделенного слоя."""
            import re
            lyr = self._vec_layer()
            if lyr is None:
                return
            self._loading_opts = True
            try:
                o = self._vopts.setdefault(lyr.id(),
                                           self._default_vopts(lyr))
                i = _find_data(self.vec_kind, o.get("kind", "plain"))
                self.vec_kind.setCurrentIndex(max(i, 0))
                i = _find_data(self.vec_poly, o.get("poly", "outline"))
                self.vec_poly.setCurrentIndex(max(i, 0))
                self.sec_on.setChecked(bool(o.get("as_section")))
                i = _find_data(self.draw_combo, o.get("draw"))
                self.draw_combo.setCurrentIndex(max(i, 0))
                self.vec_kind.setCurrentIndex(max(i, 0))
                i = _find_data(self.vec_zsrc, o.get("zsrc", "geom"))
                self.vec_zsrc.setCurrentIndex(max(i, 0))

                self.vec_zfield.blockSignals(True)
                self.vec_zfield.clear()
                self.vec_zfield.addItem(tr("(нет)"), None)
                self.vec_ztop.blockSignals(True)
                self.vec_ztop.clear()
                self.vec_ztop.addItem(tr("(нет)"), None)
                self.vec_base.blockSignals(True)
                self.vec_base.clear()
                self.vec_base.addItem(tr("(нет)"), None)
                self.vec_zsurf.blockSignals(True)
                self.vec_zsurf.clear()
                self.vec_zsurf.addItem(tr("(нет)"), None)
                for r in _map_order(QgsProject.instance()):
                    if isinstance(r, QgsRasterLayer):
                        self.vec_base.addItem(r.name(), r.id())
                        self.vec_zsurf.addItem(r.name(), r.id())
                self.wells_label.blockSignals(True)
                self.wells_label.clear()
                self.wells_label.addItem(tr("(нет)"), None)
                guess = -1
                for f in lyr.fields():
                    self.wells_label.addItem(f.name(), f.name())
                    if guess < 0 and f.name().lower() in ("name", "well",
                                                          "скв", "имя"):
                        guess = self.wells_label.count() - 1
                    if f.isNumeric():
                        self.vec_zfield.addItem(f.name(), f.name())
                        self.vec_ztop.addItem(f.name(), f.name())
                iz = _find_data(self.vec_zfield, o.get("zfield"))
                self.vec_zfield.setCurrentIndex(max(iz, 0))
                it_ = _find_data(self.vec_ztop, o.get("ztop"))
                self.vec_ztop.setCurrentIndex(max(it_, 0))
                self.vec_ztop.blockSignals(False)
                ib = _find_data(self.vec_base, o.get("base"))
                self.vec_base.setCurrentIndex(max(ib, 0))
                self.vec_base.blockSignals(False)
                isf = _find_data(self.vec_zsurf, o.get("zsurf"))
                self.vec_zsurf.setCurrentIndex(max(isf, 0))
                self.vec_zsurf.blockSignals(False)
                self.vec_zoff.blockSignals(True)
                self.vec_zoff.setValue(float(o.get("zoff", 0.0) or 0.0))
                self.vec_zoff.blockSignals(False)
                ih = _find_data(self.vec_htop, o.get("htop", "field"))
                self.vec_htop.setCurrentIndex(max(ih, 0))
                il = _find_data(self.wells_label, o.get("wells_label"))
                self.wells_label.setCurrentIndex(
                    il if il >= 0 else max(guess, 0))
                self.vec_zfield.blockSignals(False)
                self.wells_label.blockSignals(False)

                self.wells_fields.blockSignals(True)
                self.wells_fields.clear()
                saved = o.get("wells_fields")
                for f in lyr.fields():
                    if not f.isNumeric():
                        continue
                    it = QListWidgetItem(f.name())
                    it.setFlags(it.flags() | _CHECKABLE)
                    if saved:
                        on = f.name() in saved
                    else:
                        on = bool(re.match(r"^[hz]\d*$", f.name(), re.I))
                    it.setCheckState(_CHECKED if on else _UNCHECKED)
                    self.wells_fields.addItem(it)
                self.wells_fields.blockSignals(False)
                self._sync_vec_enabled()
                self._sync_props()
            finally:
                self._loading_opts = False

        @staticmethod
        def _row(widget, on):
            """Показать или убрать строку формы вместе с подписью.

            Один виджет спрятать мало: подпись живёт отдельной ячейкой
            и осталась бы висеть без поля.
            """
            on = bool(on)
            widget.setVisible(on)
            lay = widget.parentWidget().layout() if widget.parentWidget() \
                else None
            lab = None
            if lay is not None and hasattr(lay, "labelForField"):
                try:
                    lab = lay.labelForField(widget)
                except Exception:  # nosec
                    lab = None
            if lab is not None:
                lab.setVisible(on)

        def _sync_vec_enabled(self):
            """Погасить то, что к выделенному слою не относится.

            Несовместимые сочетания не должны быть доступны вовсе: иначе
            человек выбирает поле отметки при высоте из геометрии и ждёт
            результата, которого не будет.
            """
            lyr = self._vec_layer()
            if lyr is None:
                return
            kind = self._geom_kind(lyr)
            is_point = kind == "point"
            wells = is_point and (self.vec_kind.currentData() == "wells")
            zsrc = self.vec_zsrc.currentData() or "geom"

            prism = (kind == "polygon"
                     and self.vec_poly.currentData() == "prism")
            # Строка, которая к слою не относится, не гасится, а
            # убирается. Погашенная строка всё равно занимает место
            # и заставляет гадать, отчего она серая: у точечного слоя
            # призмы не будет никогда.
            self._row(self.vec_kind, is_point)
            self._row(self.vec_poly, kind == "polygon")
            self._row(self.vec_zsrc, not wells)
            self._row(self.vec_zfield,
                      not wells and (zsrc == "field" or prism))
            self._row(self.vec_zsurf, not wells and zsrc == "surf")
            self._row(self.vec_zoff, not wells)
            self._row(self.vec_base, prism)
            self._row(self.vec_htop, prism)
            self._row(self.vec_ztop, prism)
            self._row(self.wells_label, wells)
            self._row(self.wells_fields, wells)
            self.sec_box.setVisible(kind == "line")
            self.draw_combo.setEnabled(self.sec_on.isChecked())

            # «Своя высота геометрии» недоступна слою без Z
            has_z = _layer_has_z(lyr)
            model = self.vec_zsrc.model()
            for i in range(self.vec_zsrc.count()):
                item = model.item(i) if hasattr(model, "item") else None
                if item is None:
                    continue
                ok = has_z if self.vec_zsrc.itemData(i) == "geom" else True
                flags = item.flags()
                if ok:
                    item.setFlags(flags | _ENABLED)
                else:
                    item.setFlags(flags & ~_ENABLED)
            if not has_z and zsrc == "geom":
                i = _find_data(self.vec_zsrc, "field")
                if i >= 0:
                    self.vec_zsrc.setCurrentIndex(i)

        def _save_vec_opts(self, *_a):
            if self._loading_opts:
                self._sync_vec_enabled()
                return
            lyr = self._vec_layer()
            if lyr is None:
                return
            o = self._vopts.setdefault(lyr.id(), self._default_vopts(lyr))
            o["kind"] = self.vec_kind.currentData() or "plain"
            o["poly"] = self.vec_poly.currentData() or "outline"
            o["ztop"] = self.vec_ztop.currentData()
            o["base"] = self.vec_base.currentData()
            o["htop"] = self.vec_htop.currentData() or "field"
            o["as_section"] = bool(self.sec_on.isChecked())
            o["draw"] = self.draw_combo.currentData()
            o["zsrc"] = self.vec_zsrc.currentData() or "geom"
            o["zsurf"] = self.vec_zsurf.currentData()
            o["zoff"] = float(self.vec_zoff.value())
            o["zfield"] = self.vec_zfield.currentData()
            o["wells_label"] = self.wells_label.currentData()
            o["wells_fields"] = [
                self.wells_fields.item(i).text()
                for i in range(self.wells_fields.count())
                if self.wells_fields.item(i).checkState() == _CHECKED]
            self._sync_vec_enabled()
            self._schedule_rebuild()

        def _checked_vec_layers(self):
            """Отмеченные векторные слои."""
            return self._checked_of(QgsVectorLayer)

        def _z_available(self, lyr, opts):
            """Есть ли чем задать высоту слоя, иначе рисовать нечего.

            Молчаливо пустая сцена хуже отказа: человек не понимает,
            выбрал он не тот слой или сломался модуль.
            """
            if opts.get("kind") == "wells":
                return True      # у скважин отметки в отмеченных полях
            zsrc = opts.get("zsrc", "geom")
            if zsrc == "field":
                if opts.get("zfield"):
                    return True
                self._warn(tr("У слоя %s не выбрано поле отметки.")
                           % lyr.name())
                return False
            if zsrc == "surf":
                if self._zsurf_of(opts) is not None:
                    return True
                self._warn(tr("У слоя %s не выбрана поверхность "
                              "отметки или она не открылась.")
                           % lyr.name())
                return False
            if zsrc == "flat":
                return True
            if _layer_has_z(lyr):
                return True
            self._warn(tr("У слоя %s нет высоты Z, выберите отметку "
                          "из поля.") % lyr.name())
            return False

        def _base_z(self, ft, geom, opts):
            """Отметка низа призмы: из поля или с поверхности.

            Поверхность нужна для построек: подошва садится на рельеф,
            а не на общую для всех отметку. Берётся в центре объекта,
            поэтому основание получается ровным, как фундамент.
            """
            lid = opts.get("base")
            if not lid:
                return self._field_value(ft, opts.get("zfield"))
            lyr = QgsProject.instance().mapLayer(lid)
            if lyr is None:
                return self._field_value(ft, opts.get("zfield"))
            try:
                c = geom.centroid().asPoint()
            except Exception:
                return None
            arr, gt = _read_raster(lyr.source(), 1, None)
            if arr is None:
                return None
            z = sample_bilinear(arr, gt, c.x(), c.y())
            if z is None or z != z:
                return None
            return float(z)

        @staticmethod
        def _field_value(ft, name):
            """Число из поля объекта или None."""
            if not name:
                return None
            try:
                v = float(ft[name])
            except (TypeError, ValueError, KeyError):
                return None
            return v if v == v else None

        def _clip_run(self, pts):
            """Разбить ломаную на куски, попавшие в показанную часть.

            Обрезка режет и векторы тоже: иначе изолинии и разломы
            торчали бы за краем обрезанной модели.
            """
            rings, lines = self._clip_ctx()
            if not rings and not lines:
                return [pts]
            runs, cur = [], []
            for p in pts:
                if self._point_kept(p[0], p[1]):
                    cur.append(p)
                elif cur:
                    runs.append(cur)
                    cur = []
            if cur:
                runs.append(cur)
            return runs

        def _zsurf_of(self, opts):
            """Слой поверхности отметок, если он выбран и открылся."""
            if opts.get("zsrc") != "surf":
                return None
            lyr = QgsProject.instance().mapLayer(opts.get("zsurf") or "")
            if lyr is None:
                return None
            arr, gt = _read_raster(lyr.source(), 1, None)
            if arr is None:
                return None
            return lyr, arr, gt

        def _drape(self, pts, surf, off=0.0):
            """Положить точки на поверхность, выбросив места без данных.

            Отметка читается в каждой вершине, поэтому объект ложится
            на рельеф, а не встаёт на общую отметку. Пропуск это не ноль
            и не край: вершина выбрасывается, а ломаная рвётся на куски,
            иначе линия протянулась бы через пустоту по прямой.
            """
            import numpy as np
            if not surf or not pts:
                return [pts] if pts else []
            lyr, arr, gt = surf
            xs = np.array([p[0] for p in pts], dtype=float)
            ys = np.array([p[1] for p in pts], dtype=float)
            zs = self._sample_layer(lyr, arr, gt, xs, ys, nearest=True)
            runs, cur = [], []
            for i in range(len(pts)):
                z = float(zs[i])
                if z == z:
                    cur.append((float(xs[i]), float(ys[i]), z + off))
                elif cur:
                    runs.append(cur)
                    cur = []
            if cur:
                runs.append(cur)
            return runs

        def _drape_mesh(self, v, f, surf, off=0.0):
            """Положить разбитый объект на поверхность.

            Треугольник, у которого хоть одна вершина без данных,
            выбрасывается целиком: натянуть его не на что, а оставить
            значило бы подвесить кусок в воздухе.
            """
            import numpy as np
            if not surf or not len(v):
                return v, f
            lyr, arr, gt = surf
            v = np.asarray(v, dtype=float).copy()
            z = self._sample_layer(lyr, arr, gt, v[:, 0], v[:, 1],
                                   nearest=True)
            v[:, 2] = z + off
            good = np.isfinite(z)
            if good.all():
                return v, f
            keep = good[f].all(axis=1)
            return v, f[keep]

        @staticmethod
        def _zoff_of(opts):
            """Сдвиг слоя по вертикали, метры."""
            try:
                return float(opts.get("zoff", 0.0) or 0.0)
            except (TypeError, ValueError):
                return 0.0

        def _feature_z(self, ft, opts):
            """Отметка объекта по выбранному источнику высоты.

            None означает «брать из вершин геометрии». Сдвиг слоя
            прибавляется здесь же, кроме случая своей высоты
            геометрии: там он ложится на вершины при разборе.
            """
            zsrc = opts.get("zsrc", "geom")
            off = self._zoff_of(opts)
            if zsrc == "field" and opts.get("zfield"):
                try:
                    return float(ft[opts["zfield"]]) + off
                except (TypeError, ValueError, KeyError):
                    return None
            if zsrc == "flat":
                return off
            if zsrc == "surf":
                # Ноль здесь только затем, чтобы вершины дожили
                # до укладки: у плоского слоя своей Z нет, и вершины
                # отсеивались ещё при разборе геометрии. Настоящую
                # отметку каждой вершине даёт поверхность.
                return 0.0
            return None

        def _well_points(self):
            """(x, y, [отметки], подпись) по слоям в режиме скважин."""
            out = []
            for lyr in self._checked_vec_layers():
                if self._geom_kind(lyr) != "point":
                    continue
                o = self._opts_of(lyr)
                if o.get("kind") != "wells":
                    continue
                names = o.get("wells_fields") or []
                if not names:
                    continue
                lab = o.get("wells_label")
                tr_ = self._xform(lyr)
                for ft in lyr.getFeatures():
                    g = ft.geometry()
                    if g is None or g.isEmpty():
                        continue
                    if tr_ is not None:
                        g.transform(tr_)
                    p = g.asPoint()
                    if not self._point_kept(p.x(), p.y()):
                        continue
                    zs = []
                    for nm in names:
                        try:
                            v = float(ft[nm])
                        except (TypeError, ValueError, KeyError):
                            v = float("nan")   # сканер даёт B112
                        if v == v:  # не NaN
                            zs.append(v)
                    if zs:
                        txt = ""
                        if lab:
                            val = ft[lab]
                            txt = "" if val is None else str(val)
                        out.append((p.x(), p.y(), zs, txt))
            return out

        def _checked_of(self, cls):
            """Отмеченные слои нужного типа из общего списка.

            Список один, поэтому фильтр по типу обязателен: без него
            векторный слой уходил в чтение как растр, не открывался
            и попадал в «Пропущено», хотя рисовался телами.
            """
            proj = QgsProject.instance()
            out = []
            for i in range(self.layer_list.count()):
                it = self.layer_list.item(i)
                if it.checkState() != _CHECKED:
                    continue
                if it.data(_USER_ROLE) == _SCENE_KEY:
                    continue
                lyr = proj.mapLayer(it.data(_USER_ROLE))
                if isinstance(lyr, cls):
                    out.append(lyr)
            return out

        def _checked_layers(self):
            """Отмеченные растры."""
            return self._checked_of(QgsRasterLayer)

        def _layer_colors(self, lyr):
            """Цвет объектов по стилю слоя: fid -> строка цвета.

            Легенду заводить не нужно: раскраска уже лежит в стиле слоя
            и сохраняется вместе с проектом. Сцена спрашивает цвет
            у слоя, поэтому карта и объём выглядят одинаково.
            """
            key = lyr.id()
            if key in self._layer_colors_cache:
                return self._layer_colors_cache[key]
            out = {}
            try:
                from qgis.core import QgsRenderContext
                rnd = lyr.renderer()
                if rnd is not None:
                    rnd = rnd.clone()
                    ctx = QgsRenderContext()
                    rnd.startRender(ctx, lyr.fields())
                    for ft in lyr.getFeatures():
                        sym = rnd.symbolForFeature(ft, ctx)
                        # Снятый в легенде класс отдаёт пустой символ.
                        # Записываем его как None: это не «цвет не
                        # прочитался», а «показывать не надо», и путать
                        # эти два случая нельзя.
                        out[ft.id()] = (None if sym is None
                                        else sym.color().name())
                    rnd.stopRender(ctx)
            except Exception:  # nosec
                out = {}
            self._layer_colors_cache[key] = out
            # Диагностика: по этой строке видно, читается ли стиль
            # вообще и какие цвета из него приходят.
            shown = [v for v in out.values() if v]
            hidden = sum(1 for v in out.values() if v is None)
            _log(tr("Стиль слоя %s: цветов %d, скрыто классами %d, "
                    "первые %s")
                 % (lyr.name(), len(shown), hidden,
                    ", ".join(shown[:5]) or "нет"))
            return out

        @staticmethod
        def _style_hides(by_style, ft):
            """Снят ли объект с показа стилем слоя.

            Отличаем от нечитаемого стиля: там объекта в таблице нет
            вовсе, и прятать его нельзя, иначе пустая сцена вместо
            данных.
            """
            return ft.id() in by_style and by_style[ft.id()] is None

        def _tree_changed(self, *_a):
            """Дерево карты изменилось: обновить список сцены.

            Сама сцена не пересобирается: порядок и состав списка это
            ещё не повод считать заново, а кнопка обновления подсветится
            и скажет, что настройки разошлись с показанным.
            """
            if getattr(self, "_loading_opts", False):
                return
            try:
                self.refresh_layers()
            except Exception:  # nosec
                return
            self._mark_dirty(True)

        def _pick_clear(self, quiet=False):
            """Убрать точку опроса со сцены.

            Точка ставится кликом и оставалась висеть до пересборки:
            убрать её было нечем, а на снимке сцены она мешает.
            """
            if self._pick_marker is not None:
                try:
                    self.view.removeItem(self._pick_marker)
                except Exception:  # nosec
                    pass
                self._pick_marker = None
                self.view.update()
                if not quiet:
                    self.info.setText(tr("Точка опроса убрана."))
                return True
            return False

        def _draw_rank(self, lid):
            """Место слоя в списке сцены: ноль у самого верхнего.

            Порядок списка повторяет дерево карты, поэтому верхний слой
            получает наибольший подъём и рисуется поверх нижнего там,
            где геометрия совпадает.
            """
            for i in range(self.layer_list.count()):
                if self.layer_list.item(i).data(_USER_ROLE) == lid:
                    return i
            return self.layer_list.count()

        def _z_priority(self, lid, span):
            """Подъём слоя по порядку в списке, в единицах сцены.

            Совпадающая геометрия иначе спорит за глубину: изолинии
            то показываются, то тонут в поверхности, на которой лежат.
            Подъём взят малым долей охвата, на глаз он не заметен.
            """
            n = max(self.layer_list.count(), 1)
            rank = self._draw_rank(lid)
            return float(span) * 4e-4 * (n - rank) / n

        def _vert_cap(self):
            """Потолок вершин на всю сцену из свойств сцены."""
            return int(self.vert_cap.value()) * 1000

        def _body_layer_count(self):
            """Сколько отмеченных слоёв рисуется телами.

            Именно между ними и делится бюджет вершин: линии, точки
            и ленты разрезов из него не берут ничего.
            """
            n = 0
            for lyr in self._checked_vec_layers():
                if self._geom_kind(lyr) != "polygon":
                    continue
                if self._opts_of(lyr).get("poly", "outline") in ("solid",
                                                                 "prism"):
                    n += 1
            return max(n, 1)

        def _body_meshes(self, prof=None):
            """(verts, faces, name, цвет) по отмеченным полигонам с Z.

            Каждый ОБЪЕКТ слоя разбирается из WKT в треугольники отдельным
            мешем, поэтому свита из нескольких пластов красится
            по-объектно, каждый пласт своим цветом.
            """
            out = []
            for lyr in self._checked_vec_layers():
                if self._geom_kind(lyr) != "polygon":
                    continue
                o = self._opts_of(lyr)
                rings0, lines0 = self._clip_ctx()
                mode = o.get("poly", "outline")
                if mode not in ("solid", "prism"):
                    continue          # такой слой рисуется линиями
                by_style = self._layer_colors(lyr)
                zsrc = o.get("zsrc", "geom")
                if zsrc == "geom" and not _layer_has_z(lyr):
                    self._warn(tr("У слоя %s нет высоты Z, выберите "
                                  "отметку из поля.") % lyr.name())
                    continue
                n_flat = n_solid = n_noz = 0
                zlo = zhi = None
                feats = list(lyr.getFeatures())
                # Делим бюджет только между слоями, которые и правда
                # идут телами. Раньше в делитель попадал каждый
                # отмеченный вектор, и слой изолиний, ничего из этого
                # бюджета не тративший, забирал половину.
                keep, used, budget = _body_budget(
                    feats, self._body_layer_count(), self._vert_cap())
                if len(keep) < len(feats):
                    self._warn(
                        tr("В слое %s объектов %d, показаны первые %d: "
                           "набрано %d вершин из %d. Предел вершин "
                           "меняется в свойствах сцены.")
                        % (lyr.name(), len(feats), len(keep), used,
                           budget))
                feats = keep
                multi = len(feats) > 1
                k = 0
                tr_ = self._xform(lyr)
                surf_z = self._zsurf_of(o)
                for ft in feats:
                    g = ft.geometry()
                    if g is None or g.isEmpty():
                        continue
                    if self._style_hides(by_style, ft):
                        continue
                    if tr_ is not None:
                        g.transform(tr_)
                    if mode == "prism":
                        cg = self._clip_geom()
                        if cg is not None:
                            side = self.clip_side.currentData()
                            try:
                                g = g.difference(cg) if side == "out" \
                                    else g.intersection(cg)
                            except Exception:  # nosec
                                pass
                            if g is None or g.isEmpty():
                                continue
                        zb = self._base_z(ft, g, o)
                        h = self._field_value(ft, o.get("ztop"))
                        if o.get("htop") == "add":
                            # верх это низ плюс высота: подошва дома
                            # на рельефе, высота в атрибуте
                            zt = None if (zb is None or h is None) \
                                else zb + h
                        else:
                            zt = h
                        if zb is None or zt is None:
                            n_noz += 1
                            continue
                        if zt < zb:
                            zb, zt = zt, zb
                        if self._clip_geom() is not None:
                            # геометрия после обрезки своя, ключ кэша
                            # по объекту тут соврал бы
                            cv, cf = _tessellate(g, zt)
                        else:
                            cv, cf = _tri_cached(lyr, ft, g, zt, prof)
                        v, f = _prism(g, cv, cf, zb, zt)
                        if not len(f):
                            continue
                        k += 1
                        nm = (("%s #%d" % (lyr.name(), k)) if multi
                              else lyr.name())
                        out.append((v, f, nm,
                                    by_style.get(ft.id()),
                                    lyr.id()))
                        continue
                    zfix = None if zsrc == "geom" else \
                        (self._feature_z(ft, o) or 0.0)
                    if zsrc == "surf" and surf_z:
                        # Разбиваем в плане на нулевой отметке,
                        # а высоту вершинам даёт поверхность.
                        v, f = _tri_cached(lyr, ft, g, 0.0, prof)
                        v, f = self._drape_mesh(v, f, surf_z,
                                                self._zoff_of(o))
                        if not len(f):
                            continue
                    elif zsrc == "geom":
                        flat = _flat_z(g)
                        if flat is None:
                            n_solid += 1
                        else:
                            n_flat += 1
                            zlo = flat if zlo is None else min(zlo, flat)
                            zhi = flat if zhi is None else max(zhi, flat)
                        # Плоский контур разбирается в плане, объект
                        # с переменной Z по кольцам, каждое в своей
                        # плоскости: вертикальная стенка в плане
                        # вырождается в линию, и разбивка по плану
                        # даёт мусор.
                        if flat is None:
                            v, f = _tri_cached(lyr, ft, g, None, prof,
                                               spatial=True)
                            if _is_closed(v, f) and (rings0 or lines0):
                                v, f = self._clip_tris(v, f)
                                cv, cf = self._cap_cut(v, f)
                                if len(cf):
                                    f = np.vstack([f, cf + len(v)])
                                    v = np.vstack([v, cv])
                                if not len(f):
                                    continue
                                k += 1
                                nm = (("%s #%d" % (lyr.name(), k))
                                      if multi else lyr.name())
                                out.append((v, f, nm,
                                            by_style.get(ft.id()),
                                            lyr.id()))
                                continue
                        else:
                            v, f = _tri_cached(lyr, ft, g, flat, prof)
                    else:
                        v, f = _tri_cached(lyr, ft, g, zfix, prof)
                    if not len(f):
                        continue
                    rings_c, lines_c = self._clip_ctx()
                    if len(f) and (rings_c or lines_c):
                        # Пояса это открытые поверхности, крышка на срезе
                        # им не нужна: режем сами грани по контуру.
                        v, f = self._clip_tris(v, f)
                        if not len(f):
                            continue
                    k += 1
                    nm = ("%s #%d" % (lyr.name(), k)) if multi else lyr.name()
                    out.append((v, f.astype(np.int64), nm,
                                by_style.get(ft.id()), lyr.id()))
                if n_flat and not n_solid:
                    self._warn(tr(
                        "Слой %s: все %d объектов плоские, отметки "
                        "от %.1f до %.1f. Объёма в геометрии нет, для "
                        "ступеней возьмите показ призмой.")
                        % (lyr.name(), n_flat, zlo or 0.0, zhi or 0.0))
                if n_noz:
                    self._warn(tr("Слой %s: у %d объектов нет отметок "
                                  "низа или верха.") % (lyr.name(), n_noz))
            return out

        def _vec_lines(self):
            """(точки, цвет, имя) по отмеченным линейным слоям.

            Высота берётся из вершин геометрии либо из числового поля,
            тогда весь объект лежит на одной отметке: для изолиний это
            и нужно, они плоские по определению.
            """
            out = []
            for lyr in self._checked_vec_layers():
                kind = self._geom_kind(lyr)
                o = self._opts_of(lyr)
                if kind == "polygon":
                    # контуры уровней осмысленно смотреть линиями,
                    # заливка нужна телам пласта и полиэдрам
                    if o.get("poly", "outline") in ("solid", "prism"):
                        continue
                elif kind != "line":
                    continue
                elif o.get("as_section"):
                    continue      # такой слой рисуется лентой разреза
                if not self._z_available(lyr, o):
                    continue
                # Цвет объекта берётся из стиля слоя. Изолинии почти
                # всегда раскрашены по отметке, и свой цвет на слой
                # стирал всю раскраску: в сцене шла бурая паутина
                # вместо шкалы глубин.
                by_style = self._layer_colors(lyr)
                feats = list(lyr.getFeatures())
                if len(feats) > _MAX_LINES:
                    self._warn(
                        tr("В слое %s объектов %d, показаны первые %d.")
                        % (lyr.name(), len(feats), _MAX_LINES))
                    feats = feats[:_MAX_LINES]
                tr_ = self._xform(lyr)
                surf = self._zsurf_of(o)
                for ft in feats:
                    g = ft.geometry()
                    if g is None or g.isEmpty():
                        continue
                    if self._style_hides(by_style, ft):
                        continue
                    if tr_ is not None:
                        g.transform(tr_)
                    zf = self._feature_z(ft, o)
                    fcol = by_style.get(ft.id()) or "#7a5c3c"
                    off = self._zoff_of(o)
                    for pts in _parts_xyz(g, zf):
                        if surf:
                            laids = self._drape(pts, surf, off)
                        elif off and zf is None:
                            laids = [[(x, y, z + off) for x, y, z in pts]]
                        else:
                            laids = [pts]
                        for laid in laids:
                            for run in self._clip_run(laid):
                                if len(run) >= 2:
                                    out.append((run, fcol, lyr.name(),
                                                lyr.id()))
            return out

        def _vec_points(self):
            """(x, y, z, цвет) по точечным слоям в режиме «как есть»."""
            out = []
            for lyr in self._checked_vec_layers():
                if self._geom_kind(lyr) != "point":
                    continue
                o = self._opts_of(lyr)
                if o.get("kind") == "wells":
                    continue
                if not self._z_available(lyr, o):
                    continue
                by_style = self._layer_colors(lyr)
                tr_ = self._xform(lyr)
                surf = self._zsurf_of(o)
                for ft in lyr.getFeatures():
                    g = ft.geometry()
                    if g is None or g.isEmpty():
                        continue
                    if self._style_hides(by_style, ft):
                        continue
                    if tr_ is not None:
                        g.transform(tr_)
                    fcol = by_style.get(ft.id()) or "#b03030"
                    z = self._feature_z(ft, o)
                    off = self._zoff_of(o)
                    for pts in _parts_xyz(g, z):
                        # Точка без данных под ней выбрасывается,
                        # а не садится на ноль: ноль это отметка,
                        # и такая точка попала бы на чужой уровень.
                        if surf:
                            laids = self._drape(pts, surf, off)
                        elif off and z is None:
                            laids = [[(x, y, zz + off) for x, y, zz in pts]]
                        else:
                            laids = [pts]
                        for laid in laids:
                            for x, y, zz in laid:
                                if not self._point_kept(x, y):
                                    continue
                                out.append((x, y, zz, fcol, lyr.id()))
            return out

        def _apply_filter(self, text):
            low = (text or "").lower()
            for i in range(self.layer_list.count()):
                it = self.layer_list.item(i)
                it.setHidden(bool(low) and low not in it.text().lower())

        def _check_visible(self, state):
            self.layer_list.blockSignals(True)
            for i in range(self.layer_list.count()):
                it = self.layer_list.item(i)
                if not it.isHidden():
                    it.setCheckState(_CHECKED if state else _UNCHECKED)
            self.layer_list.blockSignals(False)

        @staticmethod
        def _fill_band_combo(combo, items, keep, zero_label=None):
            combo.blockSignals(True)
            combo.clear()
            if zero_label:
                combo.addItem(zero_label, 0)
            for num, label in items:
                combo.addItem(label, num)
            i = _find_data(combo, keep)
            combo.setCurrentIndex(i if i >= 0 else 0)
            combo.blockSignals(False)

        def _combo_band(self, combo, default):
            v = combo.currentData()
            return int(v) if v is not None else default

        def _default_opts(self, source):
            n = _band_count(source)
            return dict(solid=None, mode="auto", zband=1,
                        cband=3 if n >= 3 else 0,
                        attr_id=None, texture=False, tex_id=None,
                        aband=1, iso_level=0.0, vox_classes=8,
                        vox_merge=True)

        def _item_toggled(self, item=None, *_a):
            """Галка видимости: прячем и показываем без пересборки.

            Элементы уже лежат в видеопамяти, поэтому переключение
            стоит ничего и отзывается мгновенно на сцене любой тяжести.
            Пересборка нужна только тогда, когда своих элементов у слоя
            в сцене нет: его ещё ни разу не показывали либо он рисуется
            вместе с другими (скважины, ленты разрезов).
            """
            if item is None or self._loading_opts:
                return
            key = item.data(_USER_ROLE)
            if key == _SCENE_KEY:
                return
            on = item.checkState() == _CHECKED
            mine = [it for it, own in zip(self._items, self._owners)
                    if own == key]
            if not mine:
                if on:
                    self._schedule_rebuild()
                return
            for it in mine:
                try:
                    it.setVisible(on)
                except Exception:  # nosec
                    pass
            self.view.update()

        def _schedule_rebuild(self, delay=250):
            """Пересобрать сцену чуть погодя, если это разрешено.

            Задержка нужна, чтобы кручение ползунка не вызывало десяток
            сборок подряд: считается только последнее состояние.
            """
            if not self.auto_rebuild.isChecked():
                self._mark_dirty(True)
                return
            self._rebuild_timer.start(int(delay))

        def _mark_dirty(self, on):
            """Помечает, что показанная сцена отстала от настроек.

            Кнопка обновления подсвечивается, и в строке состояния
            видно, что смотреть надо не на неё, а на кнопку.
            """
            on = bool(on)
            if on == getattr(self, "_dirty", False):
                return
            self._dirty = on
            self.btn.setProperty("dirty", "yes" if on else "no")
            style = self.btn.style()
            style.unpolish(self.btn)
            style.polish(self.btn)
            self.btn.setToolTip(
                tr("Обновить сцену: настройки изменились")
                if on else tr("Обновить сцену"))
            if on:
                self.info.setText(tr("Настройки изменились. "
                                     "Нажмите «Обновить сцену»."))

        def _auto_toggled(self, on):
            """Переключение автосборки.

            При включении сцена подтягивается сразу, иначе останется
            расхождение между настройками и картинкой, а подсветку
            кнопки уже никто не покажет.
            """
            if on and getattr(self, "_dirty", False):
                self._schedule_rebuild(0)

        def _load_opts(self, item, *_a):
            """Показывает настройки выбранного в списке слоя."""
            self._loading_opts = True
            try:
                if item is None:
                    self.opt_box.setEnabled(False)
                    return
                lyr = QgsProject.instance().mapLayer(item.data(_USER_ROLE))
                if lyr is None:
                    self.opt_box.setEnabled(False)
                    return
                self.opt_box.setEnabled(True)
                self.opt_box.setTitle(tr("Параметры слоя") + ": " + lyr.name())
                o = self._opts.setdefault(lyr.id(),
                                          self._default_opts(lyr.source()))
                i = _find_data(self.mode_combo, o["mode"])
                self.mode_combo.setCurrentIndex(max(i, 0))
                items = _band_items(lyr.source()) or [(1, "1")]
                self._fill_band_combo(self.zband, items, o["zband"])
                self.iso_level.setValue(float(o.get("iso_level", 0.0)))
                self.vox_classes.setValue(
                    int(o.get("vox_classes", 8) or 8))
                self.vox_merge.setChecked(
                    bool(o.get("vox_merge", True)))
                cc = self.color_combo
                cc.blockSignals(True)
                cc.clear()
                cc.addItem(tr("Палитра"), ("palette", None))
                cc.addItem(tr("Свой цвет"), ("solid", None))
                cc.addItem(tr("Карта проекта (текстура)"), ("map", None))
                for num, label in items:
                    cc.addItem(label, ("band", num))
                proj = QgsProject.instance()
                first_r = True
                for rl in proj.mapLayers().values():
                    if not isinstance(rl, QgsRasterLayer) or \
                            rl.id() == lyr.id():
                        continue
                    if first_r:
                        cc.insertSeparator(cc.count())
                        first_r = False
                    cc.addItem(rl.name(), ("raster", rl.id()))
                first_t = True
                for ml in self._texture_candidates():
                    if first_t:
                        cc.insertSeparator(cc.count())
                        first_t = False
                    cc.addItem(tr("Текстура: %s") % ml.name(),
                               ("tex", ml.id()))
                if o.get("tex_id"):
                    want = ("tex", o["tex_id"])
                elif o.get("texture"):
                    want = ("map", None)
                elif o.get("attr_id"):
                    want = ("raster", o["attr_id"])
                elif o.get("cband"):
                    want = ("band", o["cband"])
                elif o.get("solid"):
                    want = ("solid", None)
                else:
                    want = ("palette", None)
                i = _find_data(cc, want)
                cc.setCurrentIndex(i if i >= 0 else 0)
                cc.blockSignals(False)
                self._sync_aband(o.get("aband", 1))
                self._sync_swatch()
            finally:
                self._loading_opts = False

        def _sync_swatch(self):
            """Плашка показывает свой цвет слоя и активна в режиме
            «Свой цвет»."""
            item = self.layer_list.currentItem()
            o = self._opts.get(item.data(_USER_ROLE), {}) if item else {}
            d = self.color_combo.currentData() or ("palette", None)
            solid = d[0] == "solid"
            self.color_btn.setEnabled(solid)
            col = o.get("solid") or "#e08214"
            self.color_btn.setStyleSheet(
                "background-color: %s; border: 1px solid #888;" %
                (col if solid else "#d0d0d0"))

        def _pick_solid_color(self):
            from qgis.PyQt.QtWidgets import QColorDialog
            from qgis.PyQt.QtGui import QColor
            item = self.layer_list.currentItem()
            if item is None:
                return
            lid = item.data(_USER_ROLE)
            o = self._opts.get(lid)
            if o is None:
                lyr = QgsProject.instance().mapLayer(lid)
                if lyr is None:
                    return
                o = self._default_opts(lyr.source())
                self._opts[lid] = o
            c = QColorDialog.getColor(QColor(o.get("solid") or "#e08214"),
                                      self, tr("Свой цвет слоя"))
            if c.isValid():
                o["solid"] = c.name()
                self._sync_swatch()

        def _sync_aband(self, keep):
            """Канал атрибута активен только при окраске внешним растром."""
            d = self.color_combo.currentData()
            if d and d[0] == "raster":
                lyr = QgsProject.instance().mapLayer(d[1] or "")
                items = _band_items(lyr.source()) if lyr is not None \
                    else [(1, "1")]
                self._fill_band_combo(self.aband, items or [(1, "1")], keep)
                self.aband.setEnabled(True)
            else:
                self.aband.blockSignals(True)
                self.aband.clear()
                self.aband.blockSignals(False)
                self.aband.setEnabled(False)

        def _color_changed(self, *_a):
            if self._loading_opts:
                return
            self._sync_aband(1)
            self._save_opts()

        def _save_opts(self, *_a):
            """Настройки растрового слоя. После правки сцена пересобирается."""
            if self._loading_opts:
                return
            item = self.layer_list.currentItem()
            if item is None:
                return
            lid = item.data(_USER_ROLE)
            d = self.color_combo.currentData() or ("palette", None)
            prev = self._opts.get(lid, {})
            solid = (prev.get("solid") or "#e08214") \
                if d[0] == "solid" else None
            self._opts[lid] = dict(
                mode=self.mode_combo.currentData() or "auto",
                iso_level=float(self.iso_level.value()),
                vox_classes=int(self.vox_classes.value()),
                vox_merge=bool(self.vox_merge.isChecked()),
                zband=self._combo_band(self.zband, 1),
                cband=d[1] if d[0] == "band" else 0,
                attr_id=d[1] if d[0] == "raster" else None,
                texture=(d[0] in ("map", "tex")),
                tex_id=d[1] if d[0] == "tex" else None,
                solid=solid,
                aband=self._combo_band(self.aband, 1))
            self._schedule_rebuild()
            self._sync_swatch()

        def _plane_lines(self):
            """Полилинии выбранного определения разреза со своими полями.

            Возвращает список записей (точки, zmin, zmax, атрибуты).
            В атрибутах то, что нужно для наложения чертежа: `sec_id`
            (номер разреза, связь с чертежом), `sec` (имя для показа),
            `vex` (вертикальное преувеличение чертежа), `ox` и `oy`
            (смещение, которым чертежи разнесены в слое). Полей может
            не быть, тогда на их месте None и чертёж не накладывается.
            """
            out = []
            for lyr in self._checked_vec_layers():
                if self._geom_kind(lyr) != "line":
                    continue
                if not self._opts_of(lyr).get("as_section"):
                    continue
                out.extend(self._plane_lines_of(lyr))
            return out

        def _plane_lines_of(self, lyr):
            """То же самое для одного слоя определения разреза."""
            names = {f.name().lower() for f in lyr.fields()}
            has_z = "zmin" in names and "zmax" in names

            def num(ft, key, default=None):
                if key not in names:
                    return default
                try:
                    return float(ft[key])
                except (TypeError, ValueError, KeyError):
                    return default

            out = []
            for ft in lyr.getFeatures():
                g = ft.geometry()
                if g is None or g.isEmpty():
                    continue
                try:  # QGIS 4: на одиночной LineString бросает TypeError
                    polys = g.asMultiPolyline()
                except Exception:
                    polys = []
                if not polys:
                    try:
                        pl = g.asPolyline()
                    except Exception:
                        pl = []
                    polys = [pl] if pl else []
                zlo = zhi = None
                if has_z:
                    zlo, zhi = num(ft, "zmin"), num(ft, "zmax")
                sec_id = num(ft, "sec_id")
                sec = None
                if "sec" in names:
                    try:
                        sec = str(ft["sec"])
                    except (TypeError, ValueError, KeyError):
                        sec = None
                att = {"sec_id": None if sec_id is None else int(sec_id),
                       "sec": sec, "vex": num(ft, "vex", 1.0),
                       "ox": num(ft, "ox", 0.0), "oy": num(ft, "oy", 0.0),
                       "draw": self._opts_of(lyr).get("draw"),
                       "has_layout": "ox" in names and "oy" in names}
                for pl in polys:
                    if len(pl) >= 2:
                        out.append(([(p.x(), p.y()) for p in pl],
                                    zlo, zhi, att))
            return out

        def _clip_tris(self, v, f):
            """Обрезать треугольники по области обрезки.

            Грани, целиком внутри, остаются как есть, целиком снаружи
            выбрасываются, а пересечённые режутся по контуру: у пояса
            встречаются треугольники крупнее коридора, и отбор по центру
            для них не годится, они торчали за краем.
            """
            import numpy as np
            cg = self._clip_geom()
            side = self.clip_side.currentData()
            inside_v = self._points_kept(v[:, 0], v[:, 1])
            tri_in = inside_v[f]
            n_in = tri_in.sum(axis=1)
            keep_all = n_in == 3
            mixed = (n_in > 0) & (n_in < 3)
            out_v = [v]
            out_f = [f[keep_all]]
            base = len(v)
            if cg is not None and mixed.any():
                from qgis.core import QgsGeometry, QgsPointXY
                for idx in np.nonzero(mixed)[0]:
                    tri = v[f[idx]]
                    poly = QgsGeometry.fromPolygonXY(
                        [[QgsPointXY(float(x), float(y))
                          for x, y in tri[:, :2]]
                         + [QgsPointXY(float(tri[0, 0]),
                                       float(tri[0, 1]))]])
                    try:
                        cut = poly.difference(cg) if side == "out" \
                            else poly.intersection(cg)
                    except Exception:  # nosec
                        continue
                    if cut is None or cut.isEmpty():
                        continue
                    cv, cf = _tessellate(cut, 0.0)
                    if not len(cf):
                        continue
                    cv = cv.copy()
                    cv[:, 2] = _bary_z(tri, cv[:, 0], cv[:, 1])
                    out_v.append(cv)
                    out_f.append(np.asarray(cf, dtype=np.int64) + base)
                    base += len(cv)
            faces = np.vstack(out_f) if out_f else np.zeros((0, 3),
                                                            dtype=np.int64)
            return np.vstack(out_v), faces.astype(np.int64)

        def _cap_cut(self, v, f):
            """Крышка на срезе замкнутой оболочки.

            После резки граней в оболочке остаётся отверстие, и сквозь
            него видна изнанка. Отверстие ограничено рёбрами, лежащими
            на контуре обрезки. Эти рёбра собираются в кольца, кольцо
            перекладывается в координаты «путь вдоль контура на отметку»,
            где оно плоское, там разбивается и возвращается обратно.
            """
            import numpy as np
            cg = self._clip_geom()
            if cg is None or not len(f):
                return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
            try:
                line = cg.boundary()
            except Exception:  # nosec
                return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
            if line is None or line.isEmpty():
                return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)

            # рёбра, принадлежащие одной грани, это край отверстия
            import collections
            edges = collections.Counter()
            for tri in f:
                for a, b in ((tri[0], tri[1]), (tri[1], tri[2]),
                             (tri[2], tri[0])):
                    edges[(a, b) if a < b else (b, a)] += 1
            border = [e for e, n in edges.items() if n == 1]
            if not border:
                return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)

            from qgis.core import QgsGeometry, QgsPointXY
            tol = max(cg.boundingBox().width(),
                      cg.boundingBox().height()) * 1e-4 + 1e-6

            def on_cut(i):
                p = QgsGeometry.fromPointXY(
                    QgsPointXY(float(v[i, 0]), float(v[i, 1])))
                return line.distance(p) <= tol

            keep_edges = [e for e in border if on_cut(e[0]) and on_cut(e[1])]
            if not keep_edges:
                return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)

            # путь вдоль контура для каждой вершины среза
            spos = {}
            for e in keep_edges:
                for i in e:
                    if i in spos:
                        continue
                    p = QgsGeometry.fromPointXY(
                        QgsPointXY(float(v[i, 0]), float(v[i, 1])))
                    try:
                        spos[i] = float(line.lineLocatePoint(p))
                    except Exception:  # nosec
                        return (np.zeros((0, 3)),
                                np.zeros((0, 3), dtype=np.int64))

            # кольца из рёбер среза
            adj = collections.defaultdict(list)
            for a, b in keep_edges:
                adj[a].append(b)
                adj[b].append(a)
            seen, loops = set(), []
            for start in adj:
                if start in seen:
                    continue
                loop, cur, prev = [start], start, None
                seen.add(start)
                while True:
                    nxt = [x for x in adj[cur] if x != prev]
                    nxt = [x for x in nxt if x not in seen or x == start]
                    if not nxt:
                        break
                    step = nxt[0]
                    if step == start:
                        break
                    loop.append(step)
                    seen.add(step)
                    prev, cur = cur, step
                if len(loop) >= 3:
                    loops.append(loop)
            if not loops:
                return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)

            out_v, out_f, base = [], [], 0
            for loop in loops:
                ss = [spos[i] for i in loop]
                zz = [float(v[i, 2]) for i in loop]
                flat = QgsGeometry.fromPolygonXY(
                    [[QgsPointXY(a, b) for a, b in zip(ss, zz)]])
                cv, cf = _tessellate(flat, 0.0)
                if not len(cf):
                    continue
                pts = []
                for s_, z_, _q in cv:
                    try:
                        pnt = line.interpolate(float(s_)).asPoint()
                    except Exception:  # nosec
                        pnt = None
                    if pnt is None:
                        pts = []
                        break
                    pts.append((pnt.x(), pnt.y(), float(z_)))
                if not pts:
                    continue
                out_v.append(np.asarray(pts, dtype=float))
                out_f.append(np.asarray(cf, dtype=np.int64) + base)
                base += len(pts)
            if not out_f:
                return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
            return np.vstack(out_v), np.vstack(out_f)

        def _clip_geom(self):
            """Область обрезки как геометрия QGIS или None.

            Нужна, чтобы резать тела по-настоящему, а не выбрасывать
            их целиком по центру: пересечение даёт новый контур,
            и по нему призма строится заново вместе с крышками. Срез
            получается закрытым, а не дырой в оболочке.
            """
            if self._clip_geom_now is not None:
                return self._clip_geom_now or None
            from qgis.core import QgsGeometry, QgsPointXY
            rings, lines = self._clip_ctx()
            mode = self.clip_side.currentData()
            geom = None
            try:
                if rings:
                    polys = [[[QgsPointXY(x, y) for x, y in ring]]
                             for ring in rings]
                    parts = [QgsGeometry.fromPolygonXY(pl) for pl in polys]
                    geom = parts[0]
                    for g2 in parts[1:]:
                        geom = geom.combine(g2)
                elif lines and mode == "corridor":
                    w = float(self.clip_width.value())
                    parts = []
                    for pts in lines:
                        ln = QgsGeometry.fromPolylineXY(
                            [QgsPointXY(x, y) for x, y in pts])
                        parts.append(ln.buffer(w, 12))
                    geom = parts[0]
                    for g2 in parts[1:]:
                        geom = geom.combine(g2)
            except Exception:  # nosec
                geom = None
            self._clip_geom_now = geom if geom is not None else False
            return geom

        def _xform(self, lyr, back=False):
            """Преобразование между СК слоя и СК проекта.

            Сцена живёт в системе координат проекта, как и холст карты.
            Смена СК слоя не двигает записанные координаты, она меняет
            их толкование, поэтому без преобразования слой в другой СК
            уезжал в сторону и обновление сцены ничего не меняло.

            None означает, что преобразовывать нечего.
            """
            try:
                from qgis.core import QgsCoordinateTransform
                src = lyr.crs()
                dst = QgsProject.instance().crs()
            except Exception:  # nosec
                return None
            if not src.isValid() or not dst.isValid() or src == dst:
                return None
            a, b = (dst, src) if back else (src, dst)
            try:
                return QgsCoordinateTransform(a, b,
                                              QgsProject.instance())
            except Exception:  # nosec
                return None

        @staticmethod
        def _xform_xy(tr_, xs, ys):
            """Преобразование массивов X и Y одним вызовом.

            Поточечный вызов на полумиллионе вершин стоил бы секунды,
            а `transformInPlace` уходит в C++ целиком.
            """
            import numpy as np
            if tr_ is None:
                return xs, ys
            x = [float(v) for v in np.asarray(xs).ravel()]
            y = [float(v) for v in np.asarray(ys).ravel()]
            z = [0.0] * len(x)
            try:
                tr_.transformInPlace(x, y, z)
            except Exception:  # nosec
                out = [tr_.transform(px, py) for px, py in zip(x, y)]
                x = [p.x() for p in out]
                y = [p.y() for p in out]
            shape = np.asarray(xs).shape
            return (np.array(x).reshape(shape),
                    np.array(y).reshape(shape))

        def _xform_rings(self, rings, tr_):
            """Кольца контура в другую систему координат."""
            if tr_ is None or not rings:
                return rings
            out = []
            for ring in rings:
                if not ring:
                    continue
                xs = [p[0] for p in ring]
                ys = [p[1] for p in ring]
                xs, ys = self._xform_xy(tr_, xs, ys)
                out.append(list(zip(xs.tolist(), ys.tolist())))
            return out

        def _to_layer_xy(self, lid, x, y):
            """Точка сцены в координатах слоя."""
            lyr = QgsProject.instance().mapLayer(lid or "")
            back = None if lyr is None else self._xform(lyr, back=True)
            if back is None:
                return x, y
            try:
                p = back.transform(float(x), float(y))
                return p.x(), p.y()
            except Exception:  # nosec
                return x, y

        def _sample_layer(self, lyr, arr, gt, xs, ys, nearest=False):
            """Значения растра в точках, заданных в координатах проекта.

            Сетка растра лежит в его собственной системе, поэтому точки
            переводятся туда обратно. Без этого окраска брала бы
            значения мимо данных и поверхность уходила в серое.
            """
            import numpy as np
            back = None if lyr is None else self._xform(lyr, back=True)
            if back is not None:
                xs, ys = self._xform_xy(back, xs, ys)
            out = sample_bilinear(arr, gt, xs, ys)
            if not nearest:
                return out
            # Билинейной выборке нужны четыре соседа, поэтому у самого
            # края данных она молчит даже там, где ячейка есть. Для
            # укладки это лишние разрывы, добираем ближайшей ячейкой.
            bad = ~np.isfinite(out)
            if not bad.any():
                return out
            a = np.asarray(arr, dtype=float)
            ny, nx = a.shape
            cx = np.asarray(xs, dtype=float)[bad]
            cy = np.asarray(ys, dtype=float)[bad]
            col = np.round((cx - gt[0]) / gt[1] - 0.5).astype(int)
            row = np.round((cy - gt[3]) / gt[5] - 0.5).astype(int)
            inside = ((col >= 0) & (col < nx) & (row >= 0) & (row < ny))
            fill = np.full(col.shape, np.nan)
            if inside.any():
                fill[inside] = a[row[inside], col[inside]]
            out[bad] = fill
            return out

        def _clip_for_layer(self, lyr, clip, clip_lines):
            """Обрезка, переведённая в СК слоя.

            Маска считается по сетке растра, то есть в его координатах,
            а контур живёт в координатах проекта. Без обратного перевода
            обрезка резала бы пустое место.
            """
            back = self._xform(lyr, back=True)
            if back is None:
                return clip, clip_lines
            return (self._xform_rings(clip, back),
                    self._xform_rings(clip_lines, back))

        def _clip_ctx(self):
            """Контур и линии обрезки, посчитанные один раз за сборку.

            Иначе отбор каждой вершины пересчитывал бы геометрию слоя
            обрезки заново, а вершин в сцене десятки тысяч.
            """
            if self._clip_now is None:
                self._clip_now = (self._clip_rings(), self._clip_lines())
            return self._clip_now

        def _points_kept(self, xs, ys):
            """Отбор сразу для множества точек.

            Поточечная проверка на десятках тысяч треугольников занимала
            десятки секунд: то же самое считается разом по массиву.
            """
            import numpy as np
            xs = np.asarray(xs, dtype=float)
            ys = np.asarray(ys, dtype=float)
            rings, lines = self._clip_ctx()
            if not rings and not lines:
                return np.ones(xs.shape, dtype=bool)
            mode = self.clip_side.currentData()
            if rings:
                inside = np.zeros(xs.shape, dtype=bool)
                for ring in rings:
                    pts = list(ring)
                    if pts[0] != pts[-1]:
                        pts = pts + [pts[0]]
                    p = np.asarray(pts, dtype=float)
                    x1, y1 = p[:-1, 0], p[:-1, 1]
                    x2, y2 = p[1:, 0], p[1:, 1]
                    for i in range(len(x1)):
                        cross = (y1[i] > ys) != (y2[i] > ys)
                        with np.errstate(divide="ignore", invalid="ignore"):
                            xx = x1[i] + (ys - y1[i]) * (x2[i] - x1[i]) \
                                / (y2[i] - y1[i])
                        inside ^= cross & (xs < xx)
                return ~inside if mode == "out" else inside
            keep = np.zeros(xs.shape, dtype=bool)
            width = float(self.clip_width.value())
            for pts in lines:
                p = np.asarray(pts, dtype=float)
                a, b = p[:-1], p[1:]
                d = b - a
                seg2 = (d ** 2).sum(axis=1)
                seg2[seg2 == 0] = 1e-12
                best = np.full(xs.shape, np.inf)
                sign = np.zeros(xs.shape)
                for i in range(len(a)):
                    tt = ((xs - a[i, 0]) * d[i, 0]
                          + (ys - a[i, 1]) * d[i, 1]) / seg2[i]
                    tt = np.clip(tt, 0.0, 1.0)
                    px = a[i, 0] + tt * d[i, 0]
                    py = a[i, 1] + tt * d[i, 1]
                    dist = np.hypot(xs - px, ys - py)
                    closer = dist < best
                    best = np.where(closer, dist, best)
                    cr = d[i, 0] * (ys - a[i, 1]) - d[i, 1] * (xs - a[i, 0])
                    sign = np.where(closer, np.sign(cr), sign)
                if mode == "left":
                    keep |= sign > 0
                elif mode == "right":
                    keep |= sign < 0
                else:
                    keep |= best <= width
            return keep

        def _point_kept(self, x, y):
            """Показана ли точка после обрезки.

            Луч ищет пересечение по исходным гридам, а не по обрезанным,
            поэтому без этой проверки вершина ставилась там, где модель
            уже не видна.
            """
            import numpy as np
            rings, lines = self._clip_ctx()
            if not rings and not lines:
                return True
            mode = self.clip_side.currentData()
            if rings:
                inside = False
                invert = mode == "out"
                for ring in rings:
                    pts = list(ring)
                    if pts[0] != pts[-1]:
                        pts = pts + [pts[0]]
                    for i in range(len(pts) - 1):
                        x1, y1 = pts[i]
                        x2, y2 = pts[i + 1]
                        if (y1 > y) != (y2 > y):
                            xx = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
                            if x < xx:
                                inside = not inside
                return (not inside) if invert else inside
            for pts in lines:
                p = np.asarray(pts, dtype=float)
                a, b = p[:-1], p[1:]
                d = b - a
                seg2 = (d ** 2).sum(axis=1)
                seg2[seg2 == 0] = 1e-12
                tt = np.clip(((x - a[:, 0]) * d[:, 0]
                              + (y - a[:, 1]) * d[:, 1]) / seg2, 0.0, 1.0)
                px_ = a[:, 0] + tt * d[:, 0]
                py_ = a[:, 1] + tt * d[:, 1]
                dist = np.hypot(x - px_, y - py_)
                k = int(np.argmin(dist))
                if mode == "corridor":
                    if dist[k] <= float(self.clip_width.value()):
                        return True
                else:
                    cross = (d[k, 0] * (y - a[k, 1])
                             - d[k, 1] * (x - a[k, 0]))
                    if (mode == "left" and cross > 0) or \
                            (mode == "right" and cross < 0):
                        return True
            return False

        def _hit_plane(self, px, py):
            """Точка на горизонтальном уровне середины сцены.

            Запасной способ, когда целиться не во что: важно плановое
            положение вершины, а высота для обрезки роли не играет.
            """
            import numpy as np
            from qgis.PyQt.QtGui import QVector3D
            pk = self._pick or {}
            w = max(self.view.width(), 1)
            h = max(self.view.height(), 1)
            try:
                proj = self.view.projectionMatrix()
            except TypeError:
                proj = self.view.projectionMatrix((0, 0, w, h), (0, 0, w, h))
            m = proj * self.view.viewMatrix()
            inv, ok = m.inverted()
            if not ok:
                return None
            xn = 2.0 * px / w - 1.0
            yn = 1.0 - 2.0 * py / h
            p0 = inv.map(QVector3D(xn, yn, -1.0))
            p1 = inv.map(QVector3D(xn, yn, 1.0))
            a = np.array([p0.x(), p0.y(), p0.z()], float)
            d = np.array([p1.x(), p1.y(), p1.z()], float) - a
            if abs(d[2]) < 1e-12:
                return None
            tt = -a[2] / d[2]          # плоскость z = 0 в координатах сцены
            p = a + tt * d
            cx, cy = pk.get("cx", 0.0), pk.get("cy", 0.0)
            cz = pk.get("cz", 0.0)
            return (tt, None, float(p[0]) + cx, float(p[1]) + cy, cz)

        def _hit_at(self, px, py, samples=4096):
            """Точка на поверхности под курсором или None.

            Отдельно от опроса, потому что этим же пользуется резинка
            при рисовании контура: ей нужна только точка, без чтения
            каналов, и она может считать грубее.
            """
            import numpy as np
            pk = self._pick
            if not pk:
                return None
            if not pk["layers"]:
                # Поверхностей из растров нет, а размечать надо: в сцене
                # могут лежать одни изолинии. Пересекаем луч с уровнем
                # середины сцены, план от этого не меняется.
                return self._hit_plane(px, py)
            from qgis.PyQt.QtGui import QVector3D
            w = max(self.view.width(), 1)
            h = max(self.view.height(), 1)
            try:  # старый pyqtgraph: без аргументов
                proj = self.view.projectionMatrix()
            # новый pyqtgraph (QGIS 4): нужны region и viewport
            except TypeError:
                try:
                    proj = self.view.projectionMatrix((0, 0, w, h),
                                                      (0, 0, w, h))
                except Exception:
                    return None
            m = proj * self.view.viewMatrix()
            inv, ok = m.inverted()
            if not ok:
                return None
            xn = 2.0 * px / w - 1.0
            yn = 1.0 - 2.0 * py / h
            p0 = inv.map(QVector3D(xn, yn, -1.0))
            p1 = inv.map(QVector3D(xn, yn, 1.0))
            a = np.array([p0.x(), p0.y(), p0.z()], float)
            d = np.array([p1.x(), p1.y(), p1.z()], float) - a
            # Луч бьётся мелко: 512 отсчётов промахивались по узким
            # гребням и по краю площади, и клик в режиме рисования
            # уходил в пустоту чаще, чем попадал.
            ts = np.linspace(0.0, 1.0, int(samples))
            pts = a[None, :] + ts[:, None] * d[None, :]
            cx, cy, cz, vex = pk["cx"], pk["cy"], pk["cz"], pk["vex"]
            X = pts[:, 0] + cx
            Y = pts[:, 1] + cy
            best = None  # (t, layer, X, Y, z_scene)
            for L in pk["layers"]:
                arr, gt = _read_raster(L["source"], L["zband"])
                if arr is None:
                    continue
                lyr_p = QgsProject.instance().mapLayer(L.get("lid") or "")
                zs = self._sample_layer(lyr_p, arr, gt, X, Y)
                surf = (zs + L["zoff"] - cz) * vex
                diff = pts[:, 2] - surf
                okm = np.isfinite(diff)
                sgn = np.where(okm, np.sign(diff), 0.0)
                cross = np.where((sgn[:-1] * sgn[1:] < 0) &
                                 okm[:-1] & okm[1:])[0]
                if not len(cross):
                    # Никаких поблажек: без пересечения вершина
                    # ставилась бы в пустоту рядом с поверхностью,
                    # и контур получался шире, чем нарисован.
                    continue
                i = int(cross[0])
                f = abs(diff[i]) / (abs(diff[i]) + abs(diff[i + 1]) + 1e-12)
                tt = ts[i] + (ts[i + 1] - ts[i]) * f
                if best is None or tt < best[0]:
                    xh = X[i] + (X[i + 1] - X[i]) * f
                    yh = Y[i] + (Y[i + 1] - Y[i]) * f
                    zh = pts[i, 2] + (pts[i + 1, 2] - pts[i, 2]) * f
                    if self._draw_mode and not self._point_kept(xh, yh):
                        continue      # эта часть модели сейчас не видна
                    best = (tt, L, xh, yh, zh)
            return best

        def _pick_at(self, px, py):
            """Клик по сцене: точка, а в обычном режиме ещё и каналы."""
            best = self._hit_at(px, py)
            if best is None:
                if self._draw_mode:
                    self._draw_status(tr("мимо поверхности"))
                else:
                    # Клик по пустому месту снимает точку опроса:
                    # это и есть самый короткий способ её убрать.
                    self._pick_clear()
                return
            _t, L, xh, yh, zh = best
            if self._draw_mode:
                self._draw_add(xh, yh, zh)
                return
            if L is None:
                return       # попали в плоскость, читать нечего
            pk = self._pick or {}
            cx, cy = pk.get("cx", 0.0), pk.get("cy", 0.0)
            gl = _import_gl()
            from osgeo import gdal
            ds = gdal.Open(L["source"])
            vals = []
            # Сцена в координатах проекта, сетка растра в своих:
            # переводим точку обратно, иначе читались бы соседние
            # ячейки или пустота за краем.
            xr, yr = self._to_layer_xy(L.get("lid"), xh, yh)
            if ds is not None:
                j = int((xr - ds.GetGeoTransform()[0]) /
                        ds.GetGeoTransform()[1])
                i = int((yr - ds.GetGeoTransform()[3]) /
                        ds.GetGeoTransform()[5])
                if 0 <= i < ds.RasterYSize and 0 <= j < ds.RasterXSize:
                    for b in range(1, ds.RasterCount + 1):
                        bd = ds.GetRasterBand(b)
                        v = bd.ReadAsArray(j, i, 1, 1)
                        v = float(v[0, 0]) if v is not None else float("nan")
                        nd = bd.GetNoDataValue()
                        if nd is not None and v == nd:
                            v = float("nan")
                        nm = bd.GetDescription() or str(b)
                        vals.append((nm, v))
                ds = None
            parts = ["%s=%.4g" % (nm, v) for nm, v in vals
                     if v == v]
            if len(vals) >= 2 and vals[0][1] == vals[0][1] and \
                    vals[1][1] == vals[1][1]:
                parts.append(tr("мощность") + "=%.4g" %
                             (vals[0][1] - vals[1][1]))
            self.info.setText("%s @ (%.1f, %.1f): %s" %
                              (L["name"], xh, yh, "; ".join(parts)))
            # маркер попадания
            if self._pick_marker is not None:
                try:
                    self.view.removeItem(self._pick_marker)
                except Exception:  # nosec
                    pass
            r = pk["span"] * 0.006
            sph = gl.MeshData.sphere(rows=8, cols=8, radius=r)
            mk = gl.GLMeshItem(meshdata=sph, smooth=True, shader='shaded',
                               color=(0.85, 0.15, 0.15, 1.0),
                               glOptions='opaque')
            mk.translate(xh - cx, yh - cy, zh)
            self.view.addItem(mk)
            self._pick_marker = mk

        def _textured(self, gl, md, verts_map, verts_scene, faces,
                      alpha, prof, opts):
            """Собрать текстурированный элемент или вернуть None.

            Карта рендерится средствами QGIS по охвату самой поверхности,
            поэтому картинка всегда точно накрывает грид и растягивать
            ничего не нужно. Любая осечка (нет видимых слоёв, драйвер
            не потянул текстуру) означает возврат None: слой тогда
            рисуется обычным способом, окно не падает.
            """
            from . import texmesh
            try:
                xmin = float(verts_map[:, 0].min())
                xmax = float(verts_map[:, 0].max())
                ymin = float(verts_map[:, 1].min())
                ymax = float(verts_map[:, 1].max())
                layers = self._map_layers(opts.get("tex_id"))
                if not layers:
                    _log(tr("Для текстуры нет видимых слоёв карты."))
                    return None
                side = int(self.texside.value())
                w, h = texmesh.fit_texture_size(xmax - xmin, ymax - ymin,
                                                side)
                img = texmesh.render_project_map(
                    (xmin, xmax, ymin, ymax), w, h,
                    QgsProject.instance().crs(), layers, prof)
                if img is None:
                    _log(tr("Карта для текстуры не отрисовалась."))
                    return None
                uv = texmesh.texcoords(verts_map, xmin, xmax, ymin, ymax)
                try:
                    normals = md.vertexNormals()
                except Exception:
                    normals = None
                item = texmesh.make_item(gl, verts_scene, faces, uv,
                                         normals, img, alpha=alpha)
                prof.count("tex", 1).count("texpx", w * h)
                return item
            except Exception as e:
                _log(tr("Текстура не построена: %s") % e)
                return None

        def _map_layers(self, only_id=None):
            """Слои для текстуры в порядке дерева.

            Без `only_id` берутся все видимые слои проекта, кроме самих
            гридов сцены: подкладывать поверхность саму под себя
            бессмысленно. С `only_id` берётся ровно один слой, и его
            видимость в дереве значения не имеет: выбор в окне важнее.
            """
            proj = QgsProject.instance()
            if only_id:
                lyr = proj.mapLayer(only_id)
                return [lyr] if lyr is not None else []
            root = proj.layerTreeRoot()
            skip = {lyr.id() for lyr in self._checked_layers()}
            out = []
            for node in root.findLayers():
                if not node.isVisible():
                    continue
                lyr = node.layer()
                if lyr is None or lyr.id() in skip:
                    continue
                out.append(lyr)
            return out

        def _drawing_layers(self, data=None):
            """Слои чертежа разреза по выбору в списке.

            Для группы берутся все её слои в порядке дерева, для слоя -
            он один. Видимость роли не играет: выбор в окне важнее, иначе
            пришлось бы держать чертёж включённым на карте, где он лежит
            в координатах разреза и мешает.
            """
            if data is None:
                data = self.draw_combo.currentData()
            if not data:
                return []
            kind, val = data
            proj = QgsProject.instance()
            if kind == "layer":
                lyr = proj.mapLayer(val)
                return [lyr] if lyr is not None else []
            for grp in proj.layerTreeRoot().findGroups():
                if grp.name() == val:
                    return [n.layer() for n in grp.findLayers()
                            if n.layer() is not None]
            return []

        def _sec_in_drawing(self, layers, sec_id):
            """Есть ли в слоях чертежа объекты этого разреза.

            Сами разрезы разделяются охватом, а не отбором, поэтому
            проверка нужна лишь как страховка от чужого чертежа: если
            номера нет ни в одном слое, чертёж построен от другого
            определения и лёг бы куда попало. Слой без поля `sec_id`
            считается подходящим: старые чертежи строились по одному
            разрезу и номера не несут.
            """
            seen_field = False
            for lyr in layers:
                try:
                    idx = lyr.fields().indexOf("sec_id")
                except Exception:
                    idx = -1          # не except/continue: сканер даёт B112
                if idx < 0:
                    continue
                seen_field = True
                try:
                    vals = {int(v) for v in lyr.uniqueValues(idx)
                            if v is not None}
                except Exception:
                    return True     # не смогли проверить - не мешаем
                if int(sec_id) in vals:
                    return True
            return not seen_field

        def _ribbon_texture(self, gl, pts, pv, fidx, lo, hi, att, prof):
            """Одеть ленту разреза в чертёж. None, если не вышло.

            Чертежи Isoliner лежат в системе координат чертежа: вдоль это
            расстояние по линии, поперёк это отметка, умноженная на `vex`.
            Чертежи разных разрезов разнесены в слое смещением `ox, oy`,
            поэтому охват рендера берётся из полей определения:

                по горизонтали  ox            .. ox + длина линии
                по вертикали    zmin*vex + oy .. zmax*vex + oy

            Именно из определения, а не по границам объектов слоя: за
            рамкой чертежа висит таблица расстояний и азимутов, она
            раздула бы охват и сдвинула картинку. Причём заметно это
            стало бы не у всех, а только у тех, кто строит с таблицей.

            Разрезы разделяются самим охватом: каждый занимает свой
            прямоугольник, поэтому отбирать объекты по `sec_id` не нужно.
            Номер нужен для другого - убедиться, что чертёж и определение
            вообще из одной сборки.

            Затенение выключено: чертёж должен читаться как чертёж,
            а не как освещённая поверхность.
            """
            from . import texmesh
            layers = self._drawing_layers(att.get("draw"))
            if not layers:
                return None
            if not att.get("has_layout"):
                _log(tr("В определении разреза нет полей ox и oy: "
                        "чертёж наложить не по чему. Постройте разрез "
                        "текущей версией Isoliner."))
                return None
            sec_id = att.get("sec_id")
            if (sec_id is not None
                    and not self._sec_in_drawing(layers, sec_id)):
                _log(tr("Чертежа для разреза %d в выбранных слоях нет: "
                        "похоже, чертёж и определение из разных "
                        "построений.") % sec_id)
                return None
            try:
                dists = texmesh.polyline_dists(pts)
                length = float(dists[-1])
                if length <= 0 or hi <= lo:
                    return None
                vex = float(att.get("vex") or 1.0)
                ox, oy = float(att.get("ox") or 0.0), float(att.get("oy")
                                                            or 0.0)
                x0, x1 = ox, ox + length
                y0, y1 = lo * vex + oy, hi * vex + oy
                w, h = texmesh.fit_texture_size(
                    x1 - x0, y1 - y0, int(self.texside.value()))
                img = texmesh.render_project_map(
                    (x0, x1, y0, y1), w, h, None, layers, prof)
                if img is None:
                    _log(tr("Чертёж разреза не отрисовался."))
                    return None
                uv = texmesh.ribbon_texcoords(dists)
                item = texmesh.make_item(
                    gl, pv, np.array(fidx, dtype=np.int64), uv, None, img,
                    alpha=1.0, ambient=1.0)
                prof.count("tex", 1)
                return item
            except Exception as e:
                _log(tr("Чертёж разреза не наложился: %s") % e)
                return None

        def _texture_candidates(self):
            """Слои, годные в текстуру: всё, кроме гридов, отмеченных
            в сцене. Вектор годится не хуже растра, геологическая карта
            со своей символикой ложится отлично."""
            proj = QgsProject.instance()
            skip = {lyr.id() for lyr in self._checked_layers()}
            out = []
            for node in proj.layerTreeRoot().findLayers():
                lyr = node.layer()
                if lyr is None or lyr.id() in skip:
                    continue
                out.append(lyr)
            return out

        def _clip_clear_all(self):
            """Снять обрезку, наброски и точку опроса."""
            self._pick_clear(quiet=True)
            self._clip_clear()

        def _draw_toggle(self, on):
            """Включить рисование контура прямо по сцене.

            Пока режим включён, клик по поверхности ставит вершину,
            а не опрашивает модель. Двойной клик замыкает контур.
            """
            self._draw_mode = bool(on)
            self.view.draw_mode = self._draw_mode
            self.view.setMouseTracking(self._draw_mode)
            self._hover = None
            self.btn_draw.setChecked(self._draw_mode)
            for b in (self.btn_undo, self.btn_done, self.btn_line):
                b.setVisible(self._draw_mode)
            self.tools.adjustSize()
            if self._draw_mode:
                if self._pick_marker is not None:
                    try:
                        self.view.removeItem(self._pick_marker)
                    except Exception:  # nosec
                        pass
                    self._pick_marker = None
                self._draw_pts = []
                self._draw_refresh()
                self._draw_status()
            else:
                self.info.setText("")

        def _draw_hover(self, px, py):
            """Резинка от последней вершины к курсору.

            Луч считается грубее, чем при клике: на движение мыши
            точность не нужна, а скорость нужна.
            """
            if not self._draw_pts:
                return
            best = self._hit_at(px, py, samples=768)
            self._hover = None if best is None else best[2:5]
            self._draw_refresh()

        def _draw_status(self, extra=""):
            """Подсказка живёт всё время рисования, а не гаснет с первым
            же кликом: человеку надо помнить, чем замыкать контур."""
            base = tr("Рисую контур. Клик ставит вершину, кнопки рядом: "
                      "снять последнюю, замкнуть.")
            tail = tr(" Вершин: %d.") % len(self._draw_pts)
            if extra:
                tail += " " + extra
            self.info.setText(base + tail)

        def _draw_undo(self):
            """Снять последнюю вершину. True, если было что снимать."""
            if not self._draw_mode or not self._draw_pts:
                return False
            self._draw_pts.pop()
            self._draw_refresh()
            self._draw_status()
            return True

        def _draw_cancel(self):
            """Бросить рисование и убрать наброски.

            Вне режима рисования тот же Esc снимает точку опроса:
            другой работы у клавиши здесь нет.
            """
            if not self._draw_mode:
                self._pick_clear()
                return
            self._draw_pts = []
            self._draw_refresh()
            self._draw_toggle(False)
            self.info.setText(tr("Рисование отменено."))

        def _draw_add(self, x, y, z):
            """Вершина контура: берём точку на поверхности как есть."""
            self._draw_pts.append((x, y, z))
            self._hover = None
            self._draw_refresh()
            self._draw_status()

        def _draw_refresh(self, closed=False):
            """Перерисовать контур поверх сцены."""
            if self.view is None:
                return            # окно ещё собирается
            gl = _import_gl()
            import numpy as np
            for it in (self._draw_line, self._draw_dots):
                if it is not None:
                    try:
                        self.view.removeItem(it)
                    except Exception:  # nosec
                        pass
            self._draw_line = self._draw_dots = None
            pk = self._pick or {}
            cx, cy = pk.get("cx", 0.0), pk.get("cy", 0.0)
            cz = pk.get("cz", 0.0)
            vex = pk.get("vex", 1.0)
            active = self.clip_combo.currentData()
            if not self._draw_mode and not self._show_sketch:
                self.view.update()
                return
            if not self._draw_mode and active not in (_DRAWN_KEY,
                                                      _DRAWNL_KEY):
                # нарисованное перестало резать сцену: не мозолим глаза
                self.view.update()
                return
            pts = list(self._draw_pts)
            if self._hover is not None and not closed:
                pts = pts + [tuple(self._hover)]
            if not pts:
                self.view.update()
                return
            # Разметка кладётся на один уровень над сценой. Высота
            # вершины берётся с поверхности только ради попадания луча,
            # для обрезки важно плановое положение, а разброс отметок
            # при вертикальном преувеличении читается как ошибка.
            ztop = pk.get("ztop")
            if ztop is None:
                lvl = 0.0
            else:
                lvl = (float(ztop) - cz) * vex + pk.get("span", 1.0) * 0.02
            arr = np.array([(x - cx, y - cy, lvl)
                            for x, y, _z in pts], dtype='float32')
            self._draw_dots = gl.GLScatterPlotItem(
                pos=arr, color=(0.95, 0.35, 0.1, 1.0), size=9.0,
                pxMode=True)
            _draw_on_top(self._draw_dots)
            self.view.addItem(self._draw_dots)
            if len(arr) >= 2:
                seq = np.vstack([arr, arr[:1]]) if closed else arr
                self._draw_line = gl.GLLinePlotItem(
                    pos=seq, mode='line_strip', width=2.5, antialias=True,
                    color=(0.95, 0.35, 0.1, 1.0), glOptions='opaque')
                _draw_on_top(self._draw_line)
                self.view.addItem(self._draw_line)
            self.view.update()

        def _draw_close(self):
            """Замкнуть контур и сразу пустить его в обрезку."""
            if not self._draw_mode:
                return
            if len(self._draw_pts) < 3:
                self.info.setText(tr("Для контура нужно хотя бы три "
                                     "вершины."))
                return
            self._draw_ring = [(x, y) for x, y, _z in self._draw_pts]
            self._draw_path = []
            self._draw_refresh(closed=True)
            self._draw_toggle(False)
            i = _find_data(self.clip_combo, _DRAWN_KEY)
            if i >= 0:
                self.clip_combo.setCurrentIndex(i)
            # режим мог остаться от работы с линией, а для контура
            # осмысленное умолчание одно: показать то, что обвели
            if self.clip_side.currentData() not in ("in", "out"):
                j = _find_data(self.clip_side, "in")
                if j >= 0:
                    self.clip_side.setCurrentIndex(j)
            self.info.setText(tr("Контур замкнут: вершин %d.")
                              % len(self._draw_ring))

        def _sync_corridor(self):
            """Поле полуширины видно только тогда, когда режут коридором."""
            on = self.clip_side.currentData() == "corridor"
            self.clip_width.setVisible(on)
            self.tools.adjustSize()

        def _draw_line_done(self):
            """Завершить незамкнутую линию и резать по ней коридором.

            Контур режет площадь, линия режет вдоль профиля: это разные
            задачи, поэтому и кнопки разные.
            """
            if not self._draw_mode:
                return
            if len(self._draw_pts) < 2:
                self.info.setText(tr("Для линии нужно хотя бы две "
                                     "вершины."))
                return
            self._draw_path = [(x, y) for x, y, _z in self._draw_pts]
            self._draw_ring = []
            self._draw_refresh()
            self._draw_toggle(False)
            i = _find_data(self.clip_combo, _DRAWNL_KEY)
            if i >= 0:
                self.clip_combo.setCurrentIndex(i)
            j = _find_data(self.clip_side, "corridor")
            if j >= 0:
                self.clip_side.setCurrentIndex(j)
            self.info.setText(tr("Линия готова: вершин %d, коридор %.0f.")
                              % (len(self._draw_path),
                                 self.clip_width.value()))

        def _draw_save(self):
            """Сохранить нарисованный контур слоем проекта."""
            if not self._draw_ring:
                self.info.setText(tr("Контур ещё не нарисован."))
                return
            try:
                from qgis.core import (QgsVectorLayer, QgsFeature,
                                       QgsGeometry, QgsPointXY)
                proj = QgsProject.instance()
                crs = proj.crs().authid() or ""
                lyr = QgsVectorLayer("Polygon?crs=" + crs,
                                     tr("Контур (нарисован)"), "memory")
                ft = QgsFeature()
                ring = [QgsPointXY(x, y) for x, y in self._draw_ring]
                ft.setGeometry(QgsGeometry.fromPolygonXY([ring]))
                lyr.dataProvider().addFeatures([ft])
                lyr.updateExtents()
                proj.addMapLayer(lyr)
                self.refresh_layers()
                i = _find_data(self.clip_combo, lyr.id())
                if i >= 0:
                    self.clip_combo.setCurrentIndex(i)
                self.info.setText(tr("Контур сохранён слоем проекта."))
            except Exception as err:
                self.info.setText(tr("Сохранить контур не удалось: %s")
                                  % err)
                _log(tr("Сохранить контур не удалось: %s") % err)

        def _clip_lines(self):
            """Ломаные слоя обрезки, если выбран линейный слой."""
            lid = self.clip_combo.currentData()
            if lid == _DRAWNL_KEY:
                return [list(self._draw_path)] if self._draw_path else []
            if not lid or lid == _DRAWN_KEY:
                return []
            lyr = QgsProject.instance().mapLayer(lid)
            if lyr is None or self._geom_kind(lyr) != "line":
                return []
            out = []
            for ft in lyr.getFeatures():
                g = ft.geometry()
                if g is None or g.isEmpty():
                    continue
                for part in _parts_xyz(g, 0.0):
                    if len(part) >= 2:
                        out.append([(x, y) for x, y, _z in part])
            return out

        def _clip_rings(self):
            """Кольца контура обрезки в координатах проекта.

            Пусто, если контур не выбран. Дырки контура тоже попадают
            сюда своими кольцами: маска считает по правилу чёт-нечет,
            поэтому отверстие останется отверстием.
            """
            lid = self.clip_combo.currentData()
            if lid == _DRAWN_KEY:
                return [list(self._draw_ring)] if self._draw_ring else []
            if not lid:
                return []
            lyr = QgsProject.instance().mapLayer(lid)
            if lyr is None:
                return []
            from qgis.core import QgsGeometry
            tr_ = self._xform(lyr)
            rings = []
            for ft in lyr.getFeatures():
                g = ft.geometry()
                if g is None or g.isEmpty():
                    continue
                if tr_ is not None:
                    g = QgsGeometry(g)
                    g.transform(tr_)
                for part in _parts_xyz(g, 0.0):
                    if len(part) >= 3:
                        rings.append([(x, y) for x, y, _z in part])
            return rings

        def _clip_by_lines(self, arr, gt, lines):
            """Резать по линии: сторона или коридор вдоль неё.

            Коридор это идея из практики: смотреть не голый профиль,
            а полосу заданной ширины по обе стороны от линии, чтобы
            рядом с разрезом были видны данные, а не пустота.
            """
            import numpy as np
            mode = self.clip_side.currentData()
            keep = np.zeros(arr.shape, dtype=bool)
            width = float(self.clip_width.value())
            for pts in lines:
                d, s = polyline_dist_side(pts, gt, arr.shape)
                if mode == "corridor":
                    keep |= d <= max(width, abs(gt[1]))
                elif mode == "left":
                    keep |= s > 0
                elif mode == "right":
                    keep |= s < 0
                else:
                    keep |= d <= max(width, abs(gt[1]))
            out = arr.copy()
            out[~keep] = np.nan
            return out

        def _clip_array(self, arr, gt, rings):
            """Выбросить из грида то, что не нужно показывать.

            Ячейки за пределами куска становятся NaN, то есть выпадают
            из меша так же, как обычные пропуски данных. Край получается
            по контуру, а не по прямоугольнику охвата.
            """
            if not rings:
                return arr
            import numpy as np
            inside = polygon_mask(rings, gt, arr.shape)
            # «убрать внутри» это единственный вывернутый вариант,
            # остальные режимы относятся к линии и контур не выворачивают
            keep = ~inside if (self.clip_side.currentData() == "out") \
                else inside
            out = arr.copy()
            out[~keep] = np.nan
            return out

        def _busy(self, on):
            """Курсор ожидания на время работы.

            Ставится и снимается только здесь, чтобы после сбоя окно
            не осталось с часами навсегда.
            """
            try:
                from qgis.PyQt.QtWidgets import QApplication
                from qgis.PyQt.QtCore import Qt as _Qt
                cursor = getattr(getattr(_Qt, "CursorShape", _Qt),
                                 "WaitCursor")
                if on:
                    QApplication.setOverrideCursor(cursor)
                else:
                    QApplication.restoreOverrideCursor()
                QApplication.processEvents()
            except Exception:  # nosec
                pass

        def _iso_mesh(self, lyr, opts, prof=None):
            """Оболочка по отсечке для слоя-куба.

            Каналы грида считаются уровнями. Отметку первого уровня
            и шаг берём из метаданных, если инструмент их записал,
            иначе считаем от нуля с единичным шагом: лучше показать
            форму, чем не показать ничего.
            """
            import numpy as np
            from .iso3d import isosurface
            from osgeo import gdal
            ds = gdal.Open(lyr.source())
            if ds is None or ds.RasterCount < 2:
                self._warn(tr("Слою %s нужен многоканальный грид: "
                              "каналы это уровни куба.") % lyr.name())
                return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
            gt = ds.GetGeoTransform()
            meta = ds.GetMetadata() or {}
            z0 = float(meta.get("Z0", meta.get("z0", 0.0)) or 0.0)
            dz = float(meta.get("DZ", meta.get("dz", 1.0)) or 1.0)
            bands = []
            for b in range(1, ds.RasterCount + 1):
                arr = ds.GetRasterBand(b).ReadAsArray().astype(float)
                nd = ds.GetRasterBand(b).GetNoDataValue()
                if nd is not None:
                    arr[arr == nd] = np.nan
                bands.append(arr)
            ds = None
            vol = np.stack(bands, axis=0)
            if prof is not None:
                prof.add("read")
            v, f = isosurface(vol, float(opts.get("iso_level", 0.0)),
                              gt, z0, dz)
            if not len(f):
                self._warn(tr("Слой %s: по отсечке %.3f ничего "
                              "не построено.")
                           % (lyr.name(), float(opts.get("iso_level", 0))))
            return v, f

        def _cube_arrays(self, lyr):
            """Куб слоя: значения, геопривязка, отметка и шаг уровней.

            Каналы грида это уровни. Отметку первого уровня и шаг берём
            из метаданных, если инструмент их записал, иначе считаем
            от нуля с единичным шагом.
            """
            import numpy as np
            from osgeo import gdal
            ds = gdal.Open(lyr.source())
            if ds is None or ds.RasterCount < 2:
                self._warn(tr("Слою %s нужен многоканальный грид: "
                              "каналы это уровни куба.") % lyr.name())
                return None, None, 0.0, 1.0
            gt = ds.GetGeoTransform()
            meta = ds.GetMetadata() or {}
            z0 = float(meta.get("Z0", meta.get("z0", 0.0)) or 0.0)
            dz = float(meta.get("DZ", meta.get("dz", 1.0)) or 1.0)
            bands = []
            for b in range(1, ds.RasterCount + 1):
                arr = ds.GetRasterBand(b).ReadAsArray().astype(float)
                nd = ds.GetRasterBand(b).GetNoDataValue()
                if nd is not None:
                    arr[arr == nd] = np.nan
                bands.append(arr)
            ds = None
            return np.stack(bands, axis=0), gt, z0, dz

        def _vox_mesh(self, lyr, opts, clip=None, clip_lines=None,
                      prof=None):
            """Воксельная модель куба: ячейки коробками.

            Строятся только видимые грани, соседние грани одного
            интервала окраски сливаются в прямоугольник. Обрезка
            здесь это отбор ячеек, поэтому крышку строить не нужно:
            срез плоский сам по себе.
            """
            import numpy as np
            from . import voxel
            empty = (np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64),
                     None)
            vol, gt, z0, dz = self._cube_arrays(lyr)
            if vol is None:
                return empty
            if clip or clip_lines:
                for k in range(vol.shape[0]):
                    lvl = vol[k]
                    if clip:
                        lvl = self._clip_array(lvl, gt, clip)
                    if clip_lines:
                        lvl = self._clip_by_lines(lvl, gt, clip_lines)
                    vol[k] = lvl
            if prof is not None:
                prof.add("read")
            level = float(opts.get("iso_level", 0.0))
            occ = voxel.occupancy(vol, level)
            n_cells = int(occ.sum())
            if not n_cells:
                self._warn(tr("Слой %s: по отсечке %.3f ячеек не осталось.")
                           % (lyr.name(), level))
                return empty
            # Оценка до сборки. Счёт видимых граней идёт на NumPy
            # и стоит доли секунды, а сборка меша при миллионах граней
            # уводит окно в неотзывчивость на минуты. Поэтому сначала
            # считаем, потом решаем, строить ли.
            vis = voxel.visible_faces(occ)
            if vis > _VOX_FACE_LIMIT:
                self._warn(tr("Слой %s: видимых граней %d, это больше "
                              "предела %d. Поднимите отсечку, уменьшите "
                              "число интервалов окраски или загрубите "
                              "куб.") % (lyr.name(), vis, _VOX_FACE_LIMIT))
                return empty
            nclass = max(int(opts.get("vox_classes", 8) or 8), 1)
            vals = vol[occ]
            vmin, vmax = float(vals.min()), float(vals.max())
            if nclass > 1 and vmax > vmin:
                edges = np.linspace(vmin, vmax, nclass + 1)[1:-1]
                cls = voxel.quantize(vol, edges)
            else:
                cls = np.zeros(vol.shape, dtype=np.int32)
            merge = bool(opts.get("vox_merge", True))
            verts, faces, tri_cls, over = voxel.voxel_mesh(
                occ, gt, z0, dz, classes=cls, merge=merge)
            if prof is not None:
                prof.add("mesh")
            if over:
                self._warn(tr("Слой %s: воксельная модель слишком велика. "
                              "Поднимите отсечку или уменьшите число "
                              "интервалов окраски.") % lyr.name())
                return empty
            if not len(faces):
                return empty
            denom = float(max(nclass - 1, 1))
            face_col = colormap(np.clip(tri_cls, 0, nclass - 1) / denom)
            colors = np.zeros((len(verts), 4))
            colors[faces[:, 0]] = face_col
            colors[faces[:, 1]] = face_col
            colors[faces[:, 2]] = face_col
            _log(tr("Воксели %s: ячеек %d, видимых граней %d, "
                    "прямоугольников %d.")
                 % (lyr.name(), n_cells, vis, len(faces) // 2))
            return verts, faces, colors

        def _keep_for_export(self, name, verts, faces, colors=None):
            """Отложить часть сцены для выгрузки.

            Координаты приводятся к настоящим: центр сцены возвращается
            на место, вертикальное преувеличение снимается. Преувеличение
            это способ смотреть, а не свойство модели, и в файле ему
            не место.
            """
            import numpy as np
            pk = self._pick or {}
            cx, cy = pk.get("cx", 0.0), pk.get("cy", 0.0)
            cz, vex = pk.get("cz", 0.0), pk.get("vex", 1.0) or 1.0
            v = np.asarray(verts, dtype=float).copy()
            v[:, 0] += cx
            v[:, 1] += cy
            v[:, 2] = v[:, 2] / vex + cz
            self._export.append({"name": name, "verts": v,
                                 "faces": np.asarray(faces),
                                 "colors": colors})
            _log(tr("В выгрузку: %s, вершин %d, граней %d")
                 % (name, len(v), len(np.asarray(faces))))

        def _add_item(self, item, owner=None):
            """Положить элемент в сцену, запомнив, чьего он слоя.

            Хозяин нужен, чтобы галка видимости прятала элемент сразу,
            без пересборки. Если элемент общий для нескольких слоёв,
            хозяин None и такой слой переключается пересборкой.
            """
            self.view.addItem(item)
            self._items.append(item)
            self._owners.append(owner)

        def _warn(self, text):
            """Предупреждение человеку: на экран и в журнал.

            Журнал открыт не у всех и не всегда, а молчаливая пустая
            сцена не объясняет ничего.
            """
            self._warnings.append(text)
            _log(text)

        def rebuild(self):
            """Собрать сцену, показав причину, если не вышло.

            Без этой обёртки сбой выглядел пустым окном без единого
            слова: исключение уходило в журнал Python, куда никто
            не смотрит, а строка состояния оставалась пустой.
            """
            # Курсор ожидания вместо полосы: сборка идёт в потоке
            # интерфейса, поэтому бегущая полоса всё равно не двигалась
            # бы, а часы понятны и не занимают места.
            self.info.setText(tr("Собираю сцену…"))
            self._busy(True)
            try:
                self._rebuild_scene()
            except Exception as err:
                import traceback
                self.info.setText(tr("Сборка сцены не удалась: %s") % err)
                _log(tr("Сборка сцены не удалась: %s") % err)
                _log(traceback.format_exc())
            finally:
                self._busy(False)
                self._mark_dirty(False)

        def _rebuild_scene(self):
            prof = _Prof()
            self._clip_now = None
            self._clip_geom_now = None
            self._layer_colors_cache = {}
            self._export = []
            self._warnings = []
            for m in self._items:
                self.view.removeItem(m)
            self._items = []
            self._owners = []
            # наброски живут вне списка сцены, поэтому убираем их сами:
            # раньше обнулялась только ссылка, а линия оставалась висеть
            for it in (self._draw_line, self._draw_dots):
                if it is not None:
                    try:
                        self.view.removeItem(it)
                    except Exception:  # nosec
                        pass
            self._draw_line = self._draw_dots = None
            if self._pick_marker is not None:
                try:
                    self.view.removeItem(self._pick_marker)
                except Exception:  # nosec
                    pass
                self._pick_marker = None
            layers = self._checked_layers()
            # Цвета вокселей живут на пересборку: у каждой грани свой
            # интервал, и общего цвета слоя тут не хватает.
            self._vox_colors = {}
            prof.skip()
            bodies = self._body_meshes(prof)
            prof.add("vector")
            vlines = self._vec_lines()
            vpoints = self._vec_points()
            prof.add("vector")
            if not layers and not bodies and not vlines and not vpoints:
                self.info.setText(tr("Отметьте слой на вкладке «Слои» "
                                     "или «Векторы»."))
                return
            vex = float(self.vex.value())
            spacing = float(self.spacing.value())
            meshes, skipped = [], []
            nbeds = 0
            n_reproj = 0
            budget = _layer_budget(len(layers), self._vert_cap())
            clip, clip_lines = self._clip_ctx()
            for k, lyr in enumerate(layers):
                o = self._opts.get(lyr.id()) or \
                    self._default_opts(lyr.source())
                mode = o.get("mode", "auto")
                if mode == "iso":
                    # Куб значений: каналы это уровни. Оболочка
                    # по отсечке строится маршем по тетраэдрам, поэтому
                    # выходит замкнутой и годится для подсчёта объёма.
                    # Кладём её в общий список: центрирование, окраска
                    # и выгрузка дальше работают как для поверхностей.
                    v_i, f_i = self._iso_mesh(lyr, o, prof)
                    if len(f_i):
                        col_i = PALETTE[len(meshes) % len(PALETTE)]
                        if o.get("solid"):
                            col_i = _css_rgba(o["solid"])
                        meshes.append((v_i, f_i, col_i, lyr.id(), False,
                                       lyr.source(), o, None, None, 0.0))
                    continue
                if mode == "vox":
                    # Воксели: ячейка куба показывается коробкой.
                    # Невидимые грани не строятся, соседние грани одного
                    # интервала сливаются, поэтому сцена остаётся лёгкой
                    # даже на кубе в миллионы ячеек.
                    v_v, f_v, c_v = self._vox_mesh(lyr, o, clip,
                                                   clip_lines, prof)
                    if len(f_v):
                        col_v = PALETTE[len(meshes) % len(PALETTE)]
                        if o.get("solid"):
                            col_v = _css_rgba(o["solid"])
                            c_v = None
                        if c_v is not None:
                            self._vox_colors[lyr.id()] = c_v
                        meshes.append((v_v, f_v, col_v, lyr.id(), False,
                                       lyr.source(), o, None, None, 0.0))
                    continue
                as_bed = (mode == "body" or
                          (mode == "auto" and
                           _band_count(lyr.source()) >= 2))
                # Маска считается по сетке растра, то есть в его
                # координатах, а контур живёт в координатах проекта.
                lclip, lclip_lines = self._clip_for_layer(
                    lyr, clip, clip_lines)
                try:
                    if as_bed:
                        prof.skip()
                        top, gt = _read_raster(lyr.source(), 1, prof)
                        bot, _g = _read_raster(lyr.source(), 2, prof)
                        prof.add("read")
                        if top is None or bot is None:
                            raise ValueError
                        if lclip:
                            top = self._clip_array(top, gt, lclip)
                            bot = self._clip_array(bot, gt, lclip)
                        if lclip_lines:
                            top = self._clip_by_lines(top, gt,
                                                      lclip_lines)
                            bot = self._clip_by_lines(bot, gt,
                                                      lclip_lines)
                        verts, faces = bed_to_mesh_arrays(
                            top, bot, gt, zscale=1.0,
                            zoffset=-spacing * k,
                            step=_auto_step(top, budget))
                        prof.add("mesh")
                        surf_arr = top
                        nbeds += 1
                    else:
                        prof.skip()
                        arr, gt = _read_raster(lyr.source(),
                                               o.get("zband", 1), prof)
                        prof.add("read")
                        if arr is None:
                            raise ValueError
                        if lclip:
                            arr = self._clip_array(arr, gt, lclip)
                        if lclip_lines:
                            arr = self._clip_by_lines(arr, gt,
                                                      lclip_lines)
                        verts, faces = grid_to_mesh_arrays(
                            arr, gt, zscale=1.0, zoffset=-spacing * k,
                            step=_auto_step(arr, budget))
                        prof.add("mesh")
                        surf_arr = arr
                except ValueError:
                    skipped.append(lyr.name())
                    continue
                if not len(faces):
                    skipped.append(lyr.name())
                    continue
                # Сетка построена в координатах растра. Переводим
                # вершины в координаты проекта: отметка при этом
                # не трогается, она и так в метрах.
                tr_r = self._xform(lyr)
                if tr_r is not None:
                    verts = verts.copy()
                    verts[:, 0], verts[:, 1] = self._xform_xy(
                        tr_r, verts[:, 0], verts[:, 1])
                    n_reproj += 1
                base = PALETTE[k % len(PALETTE)]
                if o.get("solid"):
                    qc = o["solid"].lstrip("#")
                    base = tuple(int(qc[i:i + 2], 16) / 255.0
                                 for i in (0, 2, 4)) + (1.0,)
                meshes.append((verts, faces, base, lyr.id(), as_bed,
                               lyr.source(), o, surf_arr, gt,
                               -spacing * k))
            if not meshes and not bodies and not vlines and not vpoints:
                self.info.setText(tr("Гриды не открылись."))
                return
            prof.skip()
            wells = self._well_points()
            planes = self._plane_lines()
            prof.add("vector")
            vsets = [m[0] for m in meshes] + [b[0] for b in bodies]
            for pts, _c, _n, _l in vlines:
                vsets.append(np.asarray(pts, dtype=float))
            if vpoints:
                vsets.append(np.array([(x, y, z)
                                       for x, y, z, _c, _l in vpoints],
                                      dtype=float))
            allv = np.vstack(vsets)
            xs = [allv[:, 0].min(), allv[:, 0].max()]
            ys = [allv[:, 1].min(), allv[:, 1].max()]
            zs_ = [allv[:, 2].min(), allv[:, 2].max()]
            for x, y, zw, _txt in wells:
                xs.append(x)
                ys.append(y)
                zs_ += [min(zw), max(zw)]
            for pts, zlo, zhi, patt in planes:
                xs += [p[0] for p in pts]
                ys += [p[1] for p in pts]
                if zlo is not None:
                    zs_ += [zlo, zhi]
            cx = 0.5 * (min(xs) + max(xs))
            cy = 0.5 * (min(ys) + max(ys))
            cz = 0.5 * (min(zs_) + max(zs_))
            span_xy = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
            # окраска пер-слойно: свой канал cband; если 0 - внешний
            # атрибутный растр слоя; иначе палитра
            prof.skip()
            vals = {}
            self._style_ramp = {}
            src_names = []
            for m in meshes:
                verts_m, lid, as_bed, src, o = (m[0], m[3], m[4],
                                                m[5], m[6])
                if o.get("texture"):
                    continue          # такому слою нужна текстура, не шкала
                cband = int(o.get("cband", 0) or 0)
                lyr_c = QgsProject.instance().mapLayer(lid)
                if cband > 0:
                    parr, pgt = _read_raster(src, cband, prof)
                    if parr is not None:
                        vals[lid] = self._sample_layer(
                            lyr_c, parr, pgt, verts_m[:, 0], verts_m[:, 1])
                        src_names.append(tr("канал %d") % cband)
                    continue
                alayer = QgsProject.instance().mapLayer(
                    o.get("attr_id") or "")
                if alayer is not None:
                    aarr, agt = _read_raster(alayer.source(),
                                             int(o.get("aband", 1)), prof)
                    if aarr is not None:
                        vals[lid] = self._sample_layer(
                            alayer, aarr, agt, verts_m[:, 0],
                            verts_m[:, 1])
                        src_names.append(alayer.name())
                    continue
                # Своя шкала слоя. Берётся то же оформление, что рисует
                # карту, поэтому поверхность выходит той же расцветки,
                # что и растр на холсте. Явно заданный канал окраски
                # и внешний атрибутный растр главнее: их выбрали руками.
                ramp = None if lyr_c is None else _ramp_from_renderer(lyr_c)
                if ramp is not None:
                    rband, breaks, cols, kind = ramp
                    rarr, rgt = _read_raster(src, rband, prof)
                    if rarr is not None:
                        zz = self._sample_layer(
                            lyr_c, rarr, rgt, verts_m[:, 0],
                            verts_m[:, 1])
                        self._style_ramp[lid] = ramp_colors(
                            zz, breaks, cols, kind)
                        src_names.append(tr("шкала слоя %s")
                                         % lyr_c.name())
            prof.add("color")
            attr = None
            fins = [v[np.isfinite(v)] for v in vals.values()
                    if np.isfinite(v).any()]
            if fins:
                fin = np.concatenate(fins)
                vmin, vmax = float(fin.min()), float(fin.max())
                rng = (vmax - vmin) or 1.0
                attr = (vals, vmin, vmax, rng)

            alpha = 1.0 - float(self.opacity.value()) / 100.0
            gopt = 'opaque' if alpha >= 0.999 else 'translucent'
            for k, (verts, faces, color, lid, as_bed, src, o,
                    _sa, _gt, _zo) in enumerate(meshes):
                v = verts.copy()
                v[:, 0] -= cx
                v[:, 1] -= cy
                v[:, 2] = ((v[:, 2] - cz) * vex
                           + self._z_priority(lid, span_xy))
                md = gl.MeshData(vertexes=v.astype('float32'), faces=faces)
                prof.count("tris", len(faces)).count("verts", len(v))
                if o.get("texture"):
                    item = self._textured(gl, md, verts, v, faces,
                                          alpha, prof, o)
                    if item is not None:
                        self._add_item(item, lid)
                        # В GLB текстура пока не уходит: для неё нужны
                        # координаты текстуры у каждой вершины и сама
                        # картинка внутри файла. Поверхность выгружается
                        # ровным цветом, чтобы не пропасть вовсе.
                        lyr_e = QgsProject.instance().mapLayer(lid)
                        self._keep_for_export(
                            lyr_e.name() if lyr_e else "surface",
                            v, faces,
                            np.tile(np.array(color[:3] + (1.0,)),
                                    (len(v), 1)))
                        continue
                vox_col = self._vox_colors.get(lid)
                if vox_col is not None and len(vox_col) == len(v):
                    vc = vox_col.copy()
                    vc[:, 3] = alpha
                    md.setVertexColors(vc.astype('float32'))
                    # Плоская заливка: у коробки грани плоские,
                    # сглаживание нормалей скруглило бы рёбра.
                    item = gl.GLMeshItem(meshdata=md, smooth=False,
                                         glOptions=gopt)
                    self._add_item(item, lid)
                    lyr_e = QgsProject.instance().mapLayer(lid)
                    self._keep_for_export(
                        lyr_e.name() if lyr_e else "voxels", verts, faces,
                        vox_col)
                    continue
                ramp_c = self._style_ramp.get(lid)
                if ramp_c is not None and len(ramp_c) == len(v):
                    vc = ramp_c.copy()
                    vc[:, 3] = alpha
                    md.setVertexColors(vc.astype('float32'))
                    item = gl.GLMeshItem(meshdata=md, smooth=True,
                                         glOptions=gopt)
                elif attr is not None and lid in attr[0]:
                    vals, vmin, vmax, rng = attr
                    vc = colormap((vals[lid] - vmin) / rng)
                    vc[:, 3] = alpha
                    md.setVertexColors(vc.astype('float32'))
                    item = gl.GLMeshItem(meshdata=md, smooth=True,
                                         glOptions=gopt)
                else:
                    item = gl.GLMeshItem(meshdata=md, smooth=True,
                                         shader='shaded',
                                         color=color[:3] + (alpha,),
                                         glOptions=gopt)
                self._add_item(item, lid)
                lyr_e = QgsProject.instance().mapLayer(lid)
                self._keep_for_export(
                    lyr_e.name() if lyr_e else "surface", verts, faces,
                    np.tile(np.array(color[:3] + (1.0,)),
                            (len(verts), 1)))
            # тела (полиэдры/полигоны с Z): плоские грани, окраска палитрой
            # Объекты собираются в один меш на сцену, а цвет каждого
            # хранится в его вершинах. Отдельный элемент на объект стоил
            # непомерно дорого: на 500 объектах это 500 наборов буферов
            # плюс нормали в двойной точности, то есть сотни мегабайт
            # видеопамяти при 20 МБ полезных данных.
            if bodies:
                # один меш на слой: элемент на объект стоил сотен
                # мегабайт, а общий на сцену не давал прятать слой
                # по галке, не пересобирая всё
                by_layer = {}
                for bi, rec in enumerate(bodies):
                    by_layer.setdefault(rec[4], []).append((bi, rec))
                for lid_b, group in by_layer.items():
                    allv, allf, allc, base = [], [], [], 0
                    for bi, (bverts, bfaces, bname, bcol, _bl) in group:
                        color = PALETTE[(len(meshes) + bi) % len(PALETTE)]
                        if bcol:
                            color = _css_rgba(bcol)
                        v = bverts.copy()
                        v[:, 0] -= cx
                        v[:, 1] -= cy
                        v[:, 2] = ((v[:, 2] - cz) * vex
                                   + self._z_priority(lid_b, span_xy))
                        allv.append(v)
                        allf.append(np.asarray(bfaces, dtype=np.int64)
                                    + base)
                        allc.append(np.tile(
                            np.array(color[:3] + (alpha,), dtype='float32'),
                            (len(v), 1)))
                        base += len(v)
                    bv = np.vstack(allv).astype('float32')
                    bf = np.vstack(allf)
                    md = gl.MeshData(vertexes=bv, faces=bf)
                    md.setVertexColors(np.vstack(allc))
                    prof.count("tris", len(bf)).count("verts", len(bv))
                    # Без затенения: цвет берётся из стиля слоя, и
                    # затенение его умножает, уводя оранжевый в бурый.
                    # Пояса плоские, светотень им ничего не добавляет,
                    # а совпадение с картой важнее.
                    item = gl.GLMeshItem(meshdata=md, smooth=False,
                                         shader=None, glOptions=gopt)
                    self._add_item(item, lid_b)
                    lyr_e = QgsProject.instance().mapLayer(lid_b)
                    self._keep_for_export(
                        lyr_e.name() if lyr_e else "body", bv, bf,
                        np.vstack(allc))
            if attr is not None:
                self._show_legend(attr[1], attr[2])
            else:
                self._hide_legend()
            span = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)

            self._pick_marker = None
            self._pick = dict(cx=cx, cy=cy, cz=cz, vex=vex, span=span,
                              ztop=float(max(zs_)), layers=[])
            for k, (verts, faces, color, lid, as_bed, src, o,
                    _sa, _gt, _zo) in enumerate(meshes):
                zb = 1 if as_bed else int(o.get("zband", 1))
                lyr = QgsProject.instance().mapLayer(lid)
                self._pick["layers"].append(dict(
                    name=lyr.name() if lyr else "?", source=src,
                    zband=zb, zoff=-spacing * k, lid=lid))

            if planes:
                pad = 0.05 * (max(zs_) - min(zs_) or 1.0)
                dlo, dhi = min(zs_) - pad, max(zs_) + pad
                for pts, zlo, zhi, patt in planes:
                    lo = zlo if zlo is not None else dlo
                    hi = zhi if zhi is not None else dhi
                    zl = (lo - cz) * vex
                    zh = (hi - cz) * vex
                    npt = len(pts)
                    pv = np.empty((2 * npt, 3), dtype='float32')
                    for i, (px, py) in enumerate(pts):
                        pv[2 * i] = (px - cx, py - cy, zl)
                        pv[2 * i + 1] = (px - cx, py - cy, zh)
                    fidx = []
                    for i in range(npt - 1):
                        a, b, c_, d = 2 * i, 2 * i + 1, 2 * i + 2, 2 * i + 3
                        fidx += [[a, c_, d], [a, d, b]]
                    itm = self._ribbon_texture(gl, pts, pv, fidx,
                                               lo, hi, patt, prof)
                    if itm is None:
                        md = gl.MeshData(
                            vertexes=pv,
                            faces=np.array(fidx, dtype=np.int64))
                        itm = gl.GLMeshItem(meshdata=md, smooth=False,
                                            color=(0.30, 0.35, 0.50, 0.30),
                                            glOptions='translucent')
                    self._add_item(itm)
                    # контур: низ -> верх в обратном порядке -> замыкание
                    frame = np.vstack([pv[0::2], pv[1::2][::-1], pv[0:1]])
                    ln = gl.GLLinePlotItem(pos=frame, mode='line_strip',
                                           width=1.5, antialias=True,
                                           color=(0.20, 0.24, 0.38, 0.9),
                                           glOptions='translucent')
                    self._add_item(ln)

            # след разреза: линия пересечения секущих плоскостей с каждой
            # поверхностью - яркая нить по кровле/подошве вдоль линии
            if planes and meshes:
                for pts, _zlo, _zhi, _pat in planes:
                    P = np.asarray(pts, dtype=float)
                    if len(P) < 2:
                        continue
                    # плотная передискретизация линии по длине
                    seg = np.diff(P, axis=0)
                    seglen = np.hypot(seg[:, 0], seg[:, 1])
                    total = float(seglen.sum())
                    if total <= 0:
                        continue
                    ns = max(int(total / (span * 0.004)), 32)
                    tt = np.linspace(0.0, total, ns)
                    cum = np.concatenate([[0.0], np.cumsum(seglen)])
                    sx = np.interp(tt, cum, P[:, 0])
                    sy = np.interp(tt, cum, P[:, 1])
                    for mm in meshes:
                        sa, gt, zo = mm[7], mm[8], mm[9]
                        zc = sample_bilinear(sa, gt, sx, sy)
                        good = np.isfinite(zc)
                        if good.sum() < 2:
                            continue
                        tpts = np.column_stack([
                            sx - cx, sy - cy,
                            (zc - cz) * vex + zo]).astype('float32')
                        # разрыв нитей в местах NaN: рисуем связными кусками
                        idx = np.where(good)[0]
                        splits = np.split(idx, np.where(np.diff(idx) > 1)[0]
                                          + 1)
                        for run in splits:
                            if len(run) < 2:
                                continue
                            tl = gl.GLLinePlotItem(
                                pos=tpts[run], mode='line_strip', width=3.0,
                                antialias=True, color=(0.95, 0.20, 0.15, 1.0),
                                glOptions='opaque')
                            self._add_item(tl)

            # контур сечения тел плоскостью разреза: где вертикальная штора
            # вдоль линии режет тело, рисуем яркий след (как по поверхностям)
            if planes and bodies:
                from . import polyhedral as poly
                cut = []
                for pts, _zlo, _zhi, _pat in planes:
                    ppoly = np.asarray(pts, dtype=float)
                    if len(ppoly) < 2:
                        continue
                    for si in range(len(ppoly) - 1):
                        ax, ay = ppoly[si][0], ppoly[si][1]
                        sxx = ppoly[si + 1][0] - ax
                        syy = ppoly[si + 1][1] - ay
                        seglen = float(np.hypot(sxx, syy))
                        if seglen <= 0.0:
                            continue
                        dxn, dyn = sxx / seglen, syy / seglen
                        nrm = (syy, -sxx, 0.0)   # горизонтальная нормаль шторы
                        for bverts, bfaces, _bn, _bc, _bl in bodies:
                            s3 = poly.slice_triangles(
                                bverts, bfaces, (ax, ay, 0.0), nrm)
                            for s in s3:
                                mx = 0.5 * (s[0][0] + s[1][0])
                                my = 0.5 * (s[0][1] + s[1][1])
                                t = (mx - ax) * dxn + (my - ay) * dyn
                                if -1e-6 <= t <= seglen + 1e-6:
                                    cut.append([s[0][0] - cx, s[0][1] - cy,
                                                (s[0][2] - cz) * vex])
                                    cut.append([s[1][0] - cx, s[1][1] - cy,
                                                (s[1][2] - cz) * vex])
                if cut:
                    cl = gl.GLLinePlotItem(
                        pos=np.array(cut, dtype='float32'), mode='lines',
                        width=3.0, antialias=True,
                        color=(0.95, 0.20, 0.15, 1.0), glOptions='opaque')
                    self._add_item(cl)

            if wells:
                mast = span * 0.02   # мачта над устьем поверх непрозрачных тел
                rad = max(span * 0.006, 1e-9)
                allv, allf, allc = [], [], []
                nof = 0
                mseg, tops, labels = [], [], []
                for x, y, zs, txt in wells:
                    xx, yy = x - cx, y - cy
                    zw = [(z - cz) * vex for z in zs]
                    # интервалы литологии: цилиндр между соседними отметками,
                    # цвет по стратиграфическому положению (индексу интервала)
                    for i in range(len(zw) - 1):
                        cv, cf = cylinder((xx, yy, zw[i]),
                                          (xx, yy, zw[i + 1]), rad, sides=10)
                        if not len(cv):
                            continue
                        col = PALETTE[i % len(PALETTE)]
                        allv.append(cv)
                        allf.append(cf + nof)
                        allc.append(np.tile(
                            np.array(col[:3] + (1.0,), dtype='float32'),
                            (len(cv), 1)))
                        nof += len(cv)
                    ztop = max(zw)
                    mseg.append([xx, yy, ztop])
                    mseg.append([xx, yy, ztop + mast])
                    tops.append([xx, yy, ztop + mast])
                    labels.append((xx, yy, ztop + mast + mast * 0.3, txt))
                if allv:   # стволы одним мешем, цвет по интервалам
                    sv = np.vstack(allv)
                    sf = np.vstack(allf)
                    prof.count("tris", len(sf)).count("verts", len(sv))
                    md = gl.MeshData(
                        vertexes=sv.astype('float32'),
                        faces=sf.astype(np.int64))
                    md.setVertexColors(np.vstack(allc).astype('float32'))
                    stems = gl.GLMeshItem(meshdata=md, smooth=False,
                                          glOptions='opaque')
                    self._add_item(stems)
                if mseg:   # мачты тонкой линией
                    ln = gl.GLLinePlotItem(
                        pos=np.array(mseg, dtype='float32'), mode='lines',
                        width=2.0, color=(0.15, 0.15, 0.15, 1.0),
                        antialias=True, glOptions='opaque')
                    self._add_item(ln)
                r = span * 0.004
                if len(tops) <= 500:  # шарики на устьях, одним мешем
                    sph = gl.MeshData.sphere(rows=8, cols=8, radius=r)
                    sv = np.asarray(sph.vertexes(), dtype=float)
                    sf = np.asarray(sph.faces(), dtype=np.int64)
                    bv = np.vstack([sv + np.asarray(t_, dtype=float)
                                    for t_ in tops])
                    bf = np.vstack([sf + i * len(sv)
                                    for i in range(len(tops))])
                    md = gl.MeshData(vertexes=bv.astype('float32'),
                                     faces=bf)
                    ball = gl.GLMeshItem(meshdata=md, smooth=True,
                                         shader='shaded',
                                         color=(0.12, 0.12, 0.12, 1.0),
                                         glOptions='opaque')
                    self._add_item(ball)
                    prof.count("tris", len(bf)).count("verts", len(bv))
                else:  # много скважин - круглые спрайты
                    dots = gl.GLScatterPlotItem(
                        pos=np.array(tops, dtype='float32'),
                        size=r * 2, pxMode=False,
                        color=(0.12, 0.12, 0.12, 0.9),
                        glOptions='translucent')
                    self._add_item(dots)
                TextItem = getattr(gl, "GLTextItem", None)
                if TextItem is not None and len(labels) <= 500:
                    from qgis.PyQt.QtGui import QFont
                    fnt = QFont()
                    fnt.setPointSize(8)
                    # прореживание: не подписывать скважину, если рядом
                    # уже есть подписанная - тексты не налезают
                    shown = thin_labels_xy(
                        [(lx, ly) for lx, ly, _z, _t in labels],
                        min_dist=span * 0.045)
                    for keep, (lx, ly, lz, txt) in zip(shown, labels):
                        if not keep or not txt:
                            continue
                        ti = TextItem(pos=(lx, ly, lz), text=txt,
                                      color=(30, 30, 30, 255), font=fnt)
                        self._add_item(ti)

            # кадрируем с учётом преувеличенной высоты, иначе высокое тело
            # при большом vex выходит за кадр и читается как перекос плана
            zspan_disp = (max(zs_) - min(zs_)) * vex
            view_span = max(span, zspan_disp, 1.0)
            want = view_span * 1.5
            prev = float(self._view_span or 0.0)
            # Кадрируем заново, если охват изменился заметно: обрезка
            # коридором уменьшает сцену в разы, и при прежнем удалении
            # камеры от неё остаётся точка в пустом кадре.
            if prev <= 0 or view_span > prev * 1.6 or \
                    view_span < prev / 1.6:
                self.view.opts['distance'] = want
            self._view_span = view_span
            self.view.opts['center'].setX(0)
            self.view.opts['center'].setY(0)
            self.view.opts['center'].setZ(0)
            self.view.update()
            msg = ""
            if bodies:
                msg += " " + tr("Тел: %d.") % len(bodies)
                if prof.counts.get("trihits"):
                    msg += " " + tr("Триангуляций из кэша: %d.") % (
                        prof.counts["trihits"])
            if vlines:
                msg += " " + tr("Линий: %d.") % len(vlines)
            if vpoints:
                msg += " " + tr("Точек: %d.") % len(vpoints)
            if nbeds:
                msg += " " + tr("Тел пластов: %d.") % nbeds
            # --- линии векторных слоёв: изолинии, разломы, трассы
            if vlines:
                # группируем по слою, а не по цвету: так галка прячет
                # слой сразу, без пересборки сцены
                by_layer = {}
                for pts, col, _nm, lid_v in vlines:
                    seg = by_layer.setdefault((lid_v, col), [])
                    P = np.array(pts, dtype=float)
                    P[:, 0] -= cx
                    P[:, 1] -= cy
                    P[:, 2] = ((P[:, 2] - cz) * vex
                               + self._z_priority(lid_v, span_xy))
                    for a, b in zip(P[:-1], P[1:]):
                        seg.append(a)
                        seg.append(b)
                for (lid_v, col), seg in by_layer.items():
                    if not seg:
                        continue
                    item = gl.GLLinePlotItem(
                        pos=np.array(seg, dtype='float32'), mode='lines',
                        width=1.6, antialias=True,
                        color=_css_rgba(col), glOptions='opaque')
                    self._add_item(item, lid_v)
                    prof.count("verts", len(seg))

            # --- точки векторных слоёв, кроме тех, что рисуются скважинами
            if vpoints:
                by_layer = {}
                for x, y, z, c, lid_v in vpoints:
                    by_layer.setdefault(lid_v, []).append(
                        ((x - cx, y - cy, (z - cz) * vex
                          + self._z_priority(lid_v, span_xy)), c))
                for lid_v, rows in by_layer.items():
                    arr = np.array([r[0] for r in rows], dtype='float32')
                    cols = np.array([_css_rgba(r[1]) for r in rows],
                                    dtype='float32')
                    # Непрозрачная отрисовка обязательна: по умолчанию
                    # у точек аддитивное смешение, и на светлом фоне
                    # сцены они выцветают в белое, то есть пропадают.
                    item = gl.GLScatterPlotItem(pos=arr, color=cols,
                                                size=7.0, pxMode=True,
                                                glOptions='opaque')
                    self._add_item(item, lid_v)
                    prof.count("verts", len(arr))

            if planes:
                msg += " " + tr("Плоскостей разреза: %d.") % len(planes)
                names = [p[3].get("sec") for p in planes if p[3].get("sec")]
                if names and prof.counts.get("tex"):
                    msg += " " + tr("Чертежи: %s.") % ", ".join(names)
            if attr is not None:
                uniq = list(dict.fromkeys(src_names))
                msg += " " + tr("Окраска: %s [%.4g … %.4g].") % (
                    ", ".join(uniq), attr[1], attr[2])
            if wells:
                msg += " " + tr("Скважин: %d.") % len(wells)
            if n_reproj:
                msg += " " + tr("Перепроецировано слоёв: %d.") % n_reproj
            if skipped:
                msg += " " + tr("Пропущено: %s") % ", ".join(skipped)
            # Контур живёт в координатах сцены, а центр сцены меняется
            # вместе с данными: после обрезки охват стал меньше, и линия
            # осталась бы висеть по прежнему центру. Поэтому рисуем её
            # заново, уже по новому центру.
            self._draw_refresh(
                closed=bool(self._draw_ring) and not self._draw_mode)
            self._state_save()
            prof.add("scene").count("items", len(self._items))
            for w in self._warnings[:3]:
                msg += " " + w
            if prof.counts.get("tex"):
                msg += " " + tr("Текстур: %d (из кэша %d).") % (
                    prof.counts["tex"], prof.counts.get("texhits", 0))
            msg += " " + prof.brief()
            _log(prof.report())
            self.info.setText(msg.strip())

    return ViewerDialog(parent)
