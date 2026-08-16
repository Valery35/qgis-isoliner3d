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
                     sample_bilinear, thin_labels_xy, cylinder)

# закреплённая строка «Сцена» в списке слоёв
_SCENE_KEY = "__scene__"

# опорные цвета шкалы (тёмно-синий -> бирюза -> жёлтый, а-ля viridis)
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


def _layer_budget(n_layers):
    """Сколько вершин достаётся одному слою при данном их числе."""
    n = max(1, int(n_layers))
    return max(MIN_VERTS_LAYER, MAX_VERTS_SCENE // n)


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


def _body_budget(feats, n_layers=1):
    """Какие объекты слоя берём в сцену.

    Считать объекты неправильно: тысяча мелких поясов дешевле десятка
    кадастровых кварталов с миллионом вершин. Поэтому копим вершины и
    останавливаемся по бюджету слоя, а число объектов держим потолком
    от разрастания самих мешей.
    """
    budget = _layer_budget(n_layers)
    out, total = [], 0
    for ft in feats:
        try:
            n = ft.geometry().constGet().nCoordinates()
        except Exception:
            n = 0
        if out and (total + n > budget or len(out) >= _MAX_BODIES):
            break
        out.append(ft)
        total += n
    return out


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
    """Полигон в треугольники честно, с учётом вогнутости и дыр.

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
            continue
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
    z = None if zfix is None else round(float(zfix), 6)
    return (lyr.id(), int(ft.id()), n, box, z)


def _tri_cached(lyr, ft, geom, zfix, prof=None):
    """Триангуляция с кэшем: геометрия между сборками не меняется.

    Разбивка пятисот контуров занимала шесть секунд и повторялась
    на каждое нажатие «Обновить сцену», хотя объекты те же самые.
    """
    global _TRI_BYTES
    key = _tri_key(lyr, ft, geom, zfix)
    hit = _TRI_CACHE.get(key)
    if hit is not None:
        if prof is not None:
            prof.count("trihits")
        return hit
    if prof is not None:
        prof.count("tess")
    v, f = _tessellate(geom, zfix)
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


def _flat_z(geom, tol=1e-6):
    """Отметка плоского объекта или None, если Z меняется.

    Плоский контур (ступень рельефа, подсчётный блок, плита на отметке)
    надо разбивать честной триангуляцией: веер даёт лучи через фигуру.
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
            continue
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
            continue
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
                continue
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
        QFrame, QMenu, QCheckBox)

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

        def mousePressEvent(self, ev):
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
            self.setWindowTitle(
                tr("Isoliner3D - 3D-просмотр поверхностей"))
            self.resize(1060, 660)
            try:  # Qt6: scoped enum, Qt5: плоский; без кнопок тоже не беда
                flag = getattr(getattr(Qt, "WindowType", Qt),
                               "WindowMinMaxButtonsHint")
                self.setWindowFlags(self.windowFlags() | flag)
            except Exception:  # nosec
                pass

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
            self.texside = QSpinBox()
            self.texside.setRange(256, 8192)
            self.texside.setSingleStep(512)
            self.texside.setValue(2048)
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
                               (tr("Тело пласта"), "body")):
                self.mode_combo.addItem(label, key)
            self.zband = QComboBox()
            self.color_combo = QComboBox()
            self.color_btn = QPushButton()
            self.color_btn.setFixedSize(46, 22)
            self.color_btn.setToolTip(tr("Задать свой цвет"))
            self.color_btn.clicked.connect(self._pick_solid_color)
            self.aband = QComboBox()
            of = QFormLayout(self.opt_box)
            of.addRow(tr("Режим"), self.mode_combo)
            of.addRow(tr("Канал высот (Z)"), self.zband)
            crow = QHBoxLayout()
            crow.addWidget(self.color_combo, 1)
            crow.addWidget(self.color_btn, 0)
            of.addRow(tr("Окраска"), crow)
            of.addRow(tr("Канал атрибута"), self.aband)
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
                               (tr("Плоско, на нуле"), "flat")):
                self.vec_zsrc.addItem(label, key)
            self.vec_zfield = QComboBox()
            self.vec_poly = QComboBox()
            for label, key in ((tr("Контуром"), "outline"),
                               (tr("Телом (заливка)"), "solid"),
                               (tr("Призмой (от поля до поля)"), "prism")):
                self.vec_poly.addItem(label, key)
            self.vec_poly.setToolTip(tr(
                "Вложенные контуры уровней осмысленно смотреть линиями. "
                "Заливка нужна телам пласта и полиэдрам."))
            self.vec_ztop = QComboBox()
            self.vec_ztop.setToolTip(tr(
                "Поле верха призмы. Поле низа задаётся строкой "
                "«Поле отметки»."))
            self.vec_kind = QComboBox()
            for label, key in ((tr("Как есть"), "plain"),
                               (tr("Скважины (стволы по отметкам)"),
                                "wells")):
                self.vec_kind.addItem(label, key)
            self.vec_color_btn = QPushButton()
            self.vec_color_btn.setFixedSize(46, 22)
            self.vec_color_btn.setToolTip(tr("Задать свой цвет"))
            self.vec_color_btn.clicked.connect(self._pick_vec_color)
            self.wells_label = QComboBox()
            self.wells_fields = QListWidget()
            self.wells_fields.setMaximumHeight(150)
            vf = QFormLayout(self.vec_box)
            vf.addRow(tr("Точечный слой"), self.vec_kind)
            vf.addRow(tr("Полигональный слой"), self.vec_poly)
            vf.addRow(tr("Источник высоты"), self.vec_zsrc)
            vf.addRow(tr("Поле отметки"), self.vec_zfield)
            vf.addRow(tr("Поле верха призмы"), self.vec_ztop)
            vf.addRow(tr("Цвет"), self.vec_color_btn)
            vf.addRow(tr("Поле подписи скважин"), self.wells_label)
            vf.addRow(tr("Поля отметок"), self.wells_fields)
            for w in (self.vec_kind, self.vec_poly, self.vec_zsrc,
                      self.vec_zfield, self.vec_ztop, self.wells_label):
                w.currentIndexChanged.connect(self._save_vec_opts)
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

            # --- кнопки снизу: вид сцены отдельной строкой, сборка крупно
            btn_top = QPushButton(tr("Сверху"))
            btn_top.clicked.connect(lambda: self._set_view(90, -90))
            btn_side = QPushButton(tr("Сбоку"))
            btn_side.clicked.connect(lambda: self._set_view(8, -90))
            btn_iso = QPushButton(tr("Наклонно"))
            btn_iso.clicked.connect(lambda: self._set_view(35, -60))
            btn_png = QPushButton(tr("Снимок…"))
            btn_png.setToolTip(tr("Сохранить кадр сцены в файл PNG"))
            btn_png.clicked.connect(self._save_png)
            views = QHBoxLayout()
            views.setSpacing(4)
            for b in (btn_top, btn_side, btn_iso, btn_png):
                views.addWidget(b)
            self.btn = QPushButton(tr("Обновить сцену"))
            self.btn.setMinimumHeight(30)
            self.btn.setDefault(True)
            self.btn.clicked.connect(self.rebuild)

            left = QWidget()
            lv = QVBoxLayout(left)
            lv.addLayout(fl)
            lv.addWidget(self.layer_list, 1)
            lv.addLayout(views)
            lv.addWidget(self.btn)
            lv.addWidget(self.legend_pix)
            lv.addWidget(self.legend_txt)
            lv.addWidget(self.info)

            self.view = _PickView()
            self.view.setBackgroundColor((250, 250, 248))
            self.view.pick_cb = self._pick_at
            self._pick = None
            self._pick_marker = None
            # тонкая тёмная рамка вокруг сцены, как у холста карты QGIS
            frame = QFrame()
            frame.setFrameShape(QFrame.Shape.Box
                                if hasattr(QFrame, "Shape")
                                else QFrame.Box)
            frame.setLineWidth(1)
            frame.setStyleSheet("QFrame { border: 1px solid #7a7a7a; }")
            fv = QVBoxLayout(frame)
            fv.setContentsMargins(1, 1, 1, 1)
            fv.addWidget(self.view)

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
            menu.exec(widget.mapToGlobal(pos)) if hasattr(menu, "exec") \
                else menu.exec_(widget.mapToGlobal(pos))

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
            растру каналы и окраска, вектору источник высоты и цвет,
            линейному слою вдобавок разрез.
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
            title = tr("Свойства сцены")
            if lyr is not None:
                title = tr("Свойства слоя: %s") % lyr.name()
            self._props.setWindowTitle(title)

        def _set_view(self, elevation, azimuth):
            self.view.opts['elevation'] = elevation
            self.view.opts['azimuth'] = azimuth
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
            for lyr in proj.mapLayers().values():
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
                    "zsrc": "geom" if has_z else "field",
                    "poly": "solid" if has_z else "outline",
                    "ztop": None,
                    "zfield": None, "color": None,
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
                self._sync_vec_swatch()
                self._sync_vec_enabled()
                self._sync_props()
            finally:
                self._loading_opts = False

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

            self.vec_kind.setEnabled(is_point)
            self.vec_poly.setEnabled(kind == "polygon")
            prism = (kind == "polygon"
                     and self.vec_poly.currentData() == "prism")
            self.vec_ztop.setEnabled(prism)
            if prism:
                # призме нужны оба поля, отметка низа обязательна
                self.vec_zfield.setEnabled(True)
            self.draw_combo.setEnabled(self.sec_on.isChecked())
            # у скважин отметки берутся из отмеченных полей, источник
            # высоты к ним отношения не имеет
            self.vec_zsrc.setEnabled(not wells)
            self.vec_zfield.setEnabled(not wells and zsrc == "field")
            self.wells_label.setEnabled(wells)
            self.wells_fields.setEnabled(wells)

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
            o["as_section"] = bool(self.sec_on.isChecked())
            o["draw"] = self.draw_combo.currentData()
            o["zsrc"] = self.vec_zsrc.currentData() or "geom"
            o["zfield"] = self.vec_zfield.currentData()
            o["wells_label"] = self.wells_label.currentData()
            o["wells_fields"] = [
                self.wells_fields.item(i).text()
                for i in range(self.wells_fields.count())
                if self.wells_fields.item(i).checkState() == _CHECKED]
            self._sync_vec_enabled()

        def _sync_vec_swatch(self):
            lyr = self._vec_layer()
            o = self._opts_of(lyr)
            css = o.get("color") or "#8899aa"
            self.vec_color_btn.setStyleSheet(
                "QPushButton { background: %s; border: 1px solid #888; }"
                % css)

        def _pick_vec_color(self):
            lyr = self._vec_layer()
            if lyr is None:
                return
            from qgis.PyQt.QtWidgets import QColorDialog
            from qgis.PyQt.QtGui import QColor
            o = self._vopts.setdefault(lyr.id(), self._default_vopts(lyr))
            start = QColor(o.get("color") or "#8899aa")
            col = QColorDialog.getColor(start, self, tr("Задать свой цвет"))
            if col.isValid():
                o["color"] = col.name()
                self._sync_vec_swatch()

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
            if zsrc == "flat":
                return True
            if _layer_has_z(lyr):
                return True
            self._warn(tr("У слоя %s нет высоты Z, выберите отметку "
                          "из поля.") % lyr.name())
            return False

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

        def _feature_z(self, ft, opts):
            """Отметка объекта по выбранному источнику высоты.

            None означает «брать из вершин геометрии».
            """
            zsrc = opts.get("zsrc", "geom")
            if zsrc == "field" and opts.get("zfield"):
                try:
                    return float(ft[opts["zfield"]])
                except (TypeError, ValueError, KeyError):
                    return None
            if zsrc == "flat":
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
                for ft in lyr.getFeatures():
                    g = ft.geometry()
                    if g is None or g.isEmpty():
                        continue
                    p = g.asPoint()
                    zs = []
                    for nm in names:
                        try:
                            v = float(ft[nm])
                        except (TypeError, ValueError, KeyError):
                            continue
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
                mode = o.get("poly", "outline")
                if mode not in ("solid", "prism"):
                    continue          # такой слой рисуется линиями
                col = o.get("color")
                zsrc = o.get("zsrc", "geom")
                if zsrc == "geom" and not _layer_has_z(lyr):
                    self._warn(tr("У слоя %s нет высоты Z, выберите "
                                  "отметку из поля.") % lyr.name())
                    continue
                n_flat = n_solid = n_noz = 0
                zlo = zhi = None
                feats = list(lyr.getFeatures())
                keep = _body_budget(feats, len(self._checked_vec_layers()))
                if len(keep) < len(feats):
                    self._warn(
                        tr("В слое %s объектов %d, показаны первые %d.")
                        % (lyr.name(), len(feats), len(keep)))
                feats = keep
                multi = len(feats) > 1
                k = 0
                for ft in feats:
                    g = ft.geometry()
                    if g is None or g.isEmpty():
                        continue
                    if mode == "prism":
                        zb = self._field_value(ft, o.get("zfield"))
                        zt = self._field_value(ft, o.get("ztop"))
                        if zb is None or zt is None:
                            n_noz += 1
                            continue
                        if zt < zb:
                            zb, zt = zt, zb
                        cv, cf = _tri_cached(lyr, ft, g, zt, prof)
                        v, f = _prism(g, cv, cf, zb, zt)
                        if not len(f):
                            continue
                        k += 1
                        nm = (("%s #%d" % (lyr.name(), k)) if multi
                              else lyr.name())
                        out.append((v, f, nm, col))
                        continue
                    zfix = None if zsrc == "geom" else \
                        (self._feature_z(ft, o) or 0.0)
                    if zsrc == "geom":
                        flat = _flat_z(g)
                        if flat is None:
                            n_solid += 1
                        else:
                            n_flat += 1
                            zlo = flat if zlo is None else min(zlo, flat)
                            zhi = flat if zhi is None else max(zhi, flat)
                        # и плоский контур, и скат разбираются одинаково
                        # честно. Веер давал лучи через фигуру и терял
                        # внутренние кольца, поясу между изолиниями это
                        # ломало и форму, и отметки.
                        v, f = _tri_cached(lyr, ft, g, flat, prof)
                    else:
                        v, f = _tri_cached(lyr, ft, g, zfix, prof)
                    if not len(f):
                        continue
                    k += 1
                    nm = ("%s #%d" % (lyr.name(), k)) if multi else lyr.name()
                    out.append((v, f.astype(np.int64), nm, col))
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
                col = o.get("color") or "#7a5c3c"
                if not self._z_available(lyr, o):
                    continue
                feats = list(lyr.getFeatures())
                if len(feats) > _MAX_LINES:
                    self._warn(
                        tr("В слое %s объектов %d, показаны первые %d.")
                        % (lyr.name(), len(feats), _MAX_LINES))
                    feats = feats[:_MAX_LINES]
                for ft in feats:
                    g = ft.geometry()
                    if g is None or g.isEmpty():
                        continue
                    zf = self._feature_z(ft, o)
                    for pts in _parts_xyz(g, zf):
                        if len(pts) >= 2:
                            out.append((pts, col, lyr.name()))
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
                col = o.get("color") or "#b03030"
                if not self._z_available(lyr, o):
                    continue
                for ft in lyr.getFeatures():
                    g = ft.geometry()
                    if g is None or g.isEmpty():
                        continue
                    z = self._feature_z(ft, o)
                    for pts in _parts_xyz(g, z):
                        for x, y, zz in pts:
                            out.append((x, y, zz, col))
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
                        aband=1)

        def _item_toggled(self, *_a):
            pass  # отметки читаются при перестройке сцены

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
                zband=self._combo_band(self.zband, 1),
                cband=d[1] if d[0] == "band" else 0,
                attr_id=d[1] if d[0] == "raster" else None,
                texture=(d[0] in ("map", "tex")),
                tex_id=d[1] if d[0] == "tex" else None,
                solid=solid,
                aband=self._combo_band(self.aband, 1))
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

        def _pick_at(self, px, py):
            """Клик по сцене: луч, пересечение с рельефом, каналы в точке."""
            import numpy as np
            pk = self._pick
            if not pk or not pk["layers"]:
                return
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
                    return
            m = proj * self.view.viewMatrix()
            inv, ok = m.inverted()
            if not ok:
                return
            xn = 2.0 * px / w - 1.0
            yn = 1.0 - 2.0 * py / h
            p0 = inv.map(QVector3D(xn, yn, -1.0))
            p1 = inv.map(QVector3D(xn, yn, 1.0))
            a = np.array([p0.x(), p0.y(), p0.z()], float)
            d = np.array([p1.x(), p1.y(), p1.z()], float) - a
            ts = np.linspace(0.0, 1.0, 512)
            pts = a[None, :] + ts[:, None] * d[None, :]
            cx, cy, cz, vex = pk["cx"], pk["cy"], pk["cz"], pk["vex"]
            X = pts[:, 0] + cx
            Y = pts[:, 1] + cy
            best = None  # (t, layer, X, Y, z_scene)
            for L in pk["layers"]:
                arr, gt = _read_raster(L["source"], L["zband"])
                if arr is None:
                    continue
                zs = sample_bilinear(arr, gt, X, Y)
                surf = (zs + L["zoff"] - cz) * vex
                diff = pts[:, 2] - surf
                okm = np.isfinite(diff)
                sgn = np.where(okm, np.sign(diff), 0.0)
                cross = np.where((sgn[:-1] * sgn[1:] < 0) &
                                 okm[:-1] & okm[1:])[0]
                if not len(cross):
                    continue
                i = int(cross[0])
                f = abs(diff[i]) / (abs(diff[i]) + abs(diff[i + 1]) + 1e-12)
                tt = ts[i] + (ts[i + 1] - ts[i]) * f
                if best is None or tt < best[0]:
                    xh = X[i] + (X[i + 1] - X[i]) * f
                    yh = Y[i] + (Y[i + 1] - Y[i]) * f
                    zh = pts[i, 2] + (pts[i + 1, 2] - pts[i, 2]) * f
                    best = (tt, L, xh, yh, zh)
            if best is None:
                return
            _t, L, xh, yh, zh = best
            from osgeo import gdal
            ds = gdal.Open(L["source"])
            vals = []
            if ds is not None:
                j = int((xh - ds.GetGeoTransform()[0]) /
                        ds.GetGeoTransform()[1])
                i = int((yh - ds.GetGeoTransform()[3]) /
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

        def _warn(self, text):
            """Предупреждение человеку: на экран и в журнал.

            Журнал открыт не у всех и не всегда, а молчаливая пустая
            сцена не объясняет ничего.
            """
            self._warnings.append(text)
            _log(text)

        def rebuild(self):
            prof = _Prof()
            self._warnings = []
            for m in self._items:
                self.view.removeItem(m)
            self._items = []
            if self._pick_marker is not None:
                try:
                    self.view.removeItem(self._pick_marker)
                except Exception:  # nosec
                    pass
                self._pick_marker = None
            layers = self._checked_layers()
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
            budget = _layer_budget(len(layers))
            for k, lyr in enumerate(layers):
                o = self._opts.get(lyr.id()) or \
                    self._default_opts(lyr.source())
                mode = o.get("mode", "auto")
                as_bed = (mode == "body" or
                          (mode == "auto" and
                           _band_count(lyr.source()) >= 2))
                try:
                    if as_bed:
                        prof.skip()
                        top, gt = _read_raster(lyr.source(), 1, prof)
                        bot, _g = _read_raster(lyr.source(), 2, prof)
                        prof.add("read")
                        if top is None or bot is None:
                            raise ValueError
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
            for pts, _c, _n in vlines:
                vsets.append(np.asarray(pts, dtype=float))
            if vpoints:
                vsets.append(np.array([(x, y, z) for x, y, z, _c in vpoints],
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
            # окраска пер-слойно: свой канал cband; если 0 - внешний
            # атрибутный растр слоя; иначе палитра
            prof.skip()
            vals = {}
            src_names = []
            for m in meshes:
                verts_m, lid, as_bed, src, o = (m[0], m[3], m[4],
                                                m[5], m[6])
                if o.get("texture"):
                    continue          # такому слою нужна текстура, не шкала
                cband = int(o.get("cband", 0) or 0)
                if cband > 0:
                    parr, pgt = _read_raster(src, cband, prof)
                    if parr is not None:
                        vals[lid] = sample_bilinear(
                            parr, pgt, verts_m[:, 0], verts_m[:, 1])
                        src_names.append(tr("канал %d") % cband)
                    continue
                alayer = QgsProject.instance().mapLayer(
                    o.get("attr_id") or "")
                if alayer is not None:
                    aarr, agt = _read_raster(alayer.source(),
                                             int(o.get("aband", 1)), prof)
                    if aarr is not None:
                        vals[lid] = sample_bilinear(
                            aarr, agt, verts_m[:, 0], verts_m[:, 1])
                        src_names.append(alayer.name())
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
                v[:, 2] = (v[:, 2] - cz) * vex
                md = gl.MeshData(vertexes=v.astype('float32'), faces=faces)
                prof.count("tris", len(faces)).count("verts", len(v))
                if o.get("texture"):
                    item = self._textured(gl, md, verts, v, faces,
                                          alpha, prof, o)
                    if item is not None:
                        self.view.addItem(item)
                        self._items.append(item)
                        continue
                if attr is not None and lid in attr[0]:
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
                self.view.addItem(item)
                self._items.append(item)
            # тела (полиэдры/полигоны с Z): плоские грани, окраска палитрой
            # Объекты собираются в один меш на сцену, а цвет каждого
            # хранится в его вершинах. Отдельный элемент на объект стоил
            # непомерно дорого: на 500 объектах это 500 наборов буферов
            # плюс нормали в двойной точности, то есть сотни мегабайт
            # видеопамяти при 20 МБ полезных данных.
            if bodies:
                allv, allf, allc, base = [], [], [], 0
                for bi, (bverts, bfaces, bname, bcol) in enumerate(bodies):
                    color = PALETTE[(len(meshes) + bi) % len(PALETTE)]
                    if bcol:
                        color = _css_rgba(bcol)
                    v = bverts.copy()
                    v[:, 0] -= cx
                    v[:, 1] -= cy
                    v[:, 2] = (v[:, 2] - cz) * vex
                    allv.append(v)
                    allf.append(np.asarray(bfaces, dtype=np.int64) + base)
                    allc.append(np.tile(
                        np.array(color[:3] + (alpha,), dtype='float32'),
                        (len(v), 1)))
                    base += len(v)
                bv = np.vstack(allv).astype('float32')
                bf = np.vstack(allf)
                md = gl.MeshData(vertexes=bv, faces=bf)
                md.setVertexColors(np.vstack(allc))
                prof.count("tris", len(bf)).count("verts", len(bv))
                item = gl.GLMeshItem(meshdata=md, smooth=False,
                                     shader='shaded', glOptions=gopt)
                self.view.addItem(item)
                self._items.append(item)
            if attr is not None:
                self._show_legend(attr[1], attr[2])
            else:
                self._hide_legend()
            span = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)

            self._pick_marker = None
            self._pick = dict(cx=cx, cy=cy, cz=cz, vex=vex, span=span,
                              layers=[])
            for k, (verts, faces, color, lid, as_bed, src, o,
                    _sa, _gt, _zo) in enumerate(meshes):
                zb = 1 if as_bed else int(o.get("zband", 1))
                lyr = QgsProject.instance().mapLayer(lid)
                self._pick["layers"].append(dict(
                    name=lyr.name() if lyr else "?", source=src,
                    zband=zb, zoff=-spacing * k))

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
                    self.view.addItem(itm)
                    self._items.append(itm)
                    # контур: низ -> верх в обратном порядке -> замыкание
                    frame = np.vstack([pv[0::2], pv[1::2][::-1], pv[0:1]])
                    ln = gl.GLLinePlotItem(pos=frame, mode='line_strip',
                                           width=1.5, antialias=True,
                                           color=(0.20, 0.24, 0.38, 0.9),
                                           glOptions='translucent')
                    self.view.addItem(ln)
                    self._items.append(ln)

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
                            self.view.addItem(tl)
                            self._items.append(tl)

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
                        for bverts, bfaces, _bn, _bc in bodies:
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
                    self.view.addItem(cl)
                    self._items.append(cl)

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
                    self.view.addItem(stems)
                    self._items.append(stems)
                if mseg:   # мачты тонкой линией
                    ln = gl.GLLinePlotItem(
                        pos=np.array(mseg, dtype='float32'), mode='lines',
                        width=2.0, color=(0.15, 0.15, 0.15, 1.0),
                        antialias=True, glOptions='opaque')
                    self.view.addItem(ln)
                    self._items.append(ln)
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
                    self.view.addItem(ball)
                    self._items.append(ball)
                    prof.count("tris", len(bf)).count("verts", len(bv))
                else:  # много скважин - круглые спрайты
                    dots = gl.GLScatterPlotItem(
                        pos=np.array(tops, dtype='float32'),
                        size=r * 2, pxMode=False,
                        color=(0.12, 0.12, 0.12, 0.9),
                        glOptions='translucent')
                    self.view.addItem(dots)
                    self._items.append(dots)
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
                        self.view.addItem(ti)
                        self._items.append(ti)

            # кадрируем с учётом преувеличенной высоты, иначе высокое тело
            # при большом vex выходит за кадр и читается как перекос плана
            zspan_disp = (max(zs_) - min(zs_)) * vex
            view_span = max(span, zspan_disp, 1.0)
            self.view.opts['distance'] = view_span * 1.5
            self.view.opts['center'].setX(0)
            self.view.opts['center'].setY(0)
            self.view.opts['center'].setZ(0)
            self.view.update()
            msg = tr("Показано поверхностей: %d.") % len(meshes)
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
                by_color = {}
                for pts, col, _nm in vlines:
                    seg = by_color.setdefault(col, [])
                    P = np.asarray(pts, dtype=float)
                    P[:, 0] -= cx
                    P[:, 1] -= cy
                    P[:, 2] = (P[:, 2] - cz) * vex
                    for a, b in zip(P[:-1], P[1:]):
                        seg.append(a)
                        seg.append(b)
                for col, seg in by_color.items():
                    if not seg:
                        continue
                    item = gl.GLLinePlotItem(
                        pos=np.array(seg, dtype='float32'), mode='lines',
                        width=1.6, antialias=True,
                        color=_css_rgba(col), glOptions='opaque')
                    self.view.addItem(item)
                    self._items.append(item)
                    prof.count("verts", len(seg))

            # --- точки векторных слоёв, кроме тех, что рисуются скважинами
            if vpoints:
                arr = np.array([(x - cx, y - cy, (z - cz) * vex)
                                for x, y, z, _c in vpoints], dtype='float32')
                cols = np.array([_css_rgba(c) for _x, _y, _z, c in vpoints],
                                dtype='float32')
                item = gl.GLScatterPlotItem(pos=arr, color=cols,
                                            size=7.0, pxMode=True)
                self.view.addItem(item)
                self._items.append(item)
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
            if skipped:
                msg += " " + tr("Пропущено: %s") % ", ".join(skipped)
            prof.add("scene").count("items", len(self._items))
            for w in self._warnings[:3]:
                msg += " " + w
            if prof.counts.get("tex"):
                msg += " " + tr("Текстур: %d (из кэша %d).") % (
                    prof.counts["tex"], prof.counts.get("texhits", 0))
            msg += " " + prof.brief()
            _log(prof.report())
            self.info.setText(msg)

    return ViewerDialog(parent)
