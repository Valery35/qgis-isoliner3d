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
# os нужен переэкспорту: окно берёт его отсюда.
import os    # noqa: F401
import time

# Расчётная часть вынесена в viewer_core. Имена продолжают жить
# и здесь: снаружи модуль виден таким же, как был.
from .viewer_core import (    # noqa: F401
    LIBS_DIR, LIGHT_DIR, MARKER_SHAPES, MAX_VERTS, MAX_VERTS_SCENE,
    MIN_VERTS_LAYER, _BANDS, _CACHE, _CACHE_BYTES, _CACHE_LIMIT,
    _CACHE_ORDER, _CMAP, _CSS_NAMES, _MAX_BODIES, _TRI_BYTES, _TRI_CACHE,
    _TRI_LIMIT, _TRI_ORDER, _all_vertices, _auto_step, _band_count,
    _band_items, _bary_z, _body_budget, _cache_put, _closed_and_border,
    _css_rgba, _draw_on_top, _file_stamp, _fill_z, _find_data, _flat_z,
    _fmt_n, _gdal_open, _import_gl, _is_closed, _layer_budget, _map_order,
    _ramp_from_renderer, _read_raster, _ring_normal, _tri_cached, _tri_key,
    _tri_rings, cache_clear, cache_size, clip_wall, colormap, draw_depth,
    field_color, flat_marker_mesh, is_available, is_bed_grid, layer_lift,
    ramp_colors, volume_beyond_box,
    shade_colors, tri_cache_clear, tri_cache_size, walk_rings, z_range_mask)


from .i18n import tr
# Часть этих имён нужна не здесь, а окну: оно берёт их отсюда,
# чтобы не тянуть mesh3d вторым путём.
from .mesh3d import (grid_to_mesh_arrays, bed_to_mesh_arrays,   # noqa: F401
                     sample_bilinear, thin_labels_xy, cylinder,
                     polygon_mask, polyline_dist_side)

# закреплённая строка «Сцена» в списке слоёв
_SCENE_KEY = "__scene__"
# ключ пункта «нарисованный контур» в списке обрезки
_DRAWN_KEY = "__drawn__"
# ключ пункта «нарисованная линия» в списке обрезки
_DRAWNL_KEY = "__drawnline__"

# опорные цвета шкалы (тёмно-синий -> бирюза -> жёлтый, а-ля viridis)


# Предел видимых граней у вокселей: выше этого сцена
# перестаёт быть отзывчивой, и вместо показа выдаётся
# число и совет, что покрутить.
_VOX_FACE_LIMIT = 1500000


_DIALOG = None  # держим окно живым


# Бюджет вершин на всю сцену, а не на слой. Раньше потолок был
# персональным, и одиночная поверхность получала столько же, сколько
# каждый слой из десятка: детали не хватало там, где она была бесплатна,
# и было слишком много там, где сцена и так тяжёлая.
_MAX_POINT_LABELS = 400    # каждая подпись это элемент сцены

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


def _halo_text_item(gl):
    """Подпись с ореолом: текст читается на любом фоне.

    Простая подпись рисуется одним цветом, и на пёстрой сцене тёмный
    текст пропадает на тёмном, светлый на светлом. Здесь под текст
    кладётся обводка контрастного цвета, как это делают в Google Earth
    и на топографических картах. Размер экранный, подпись всегда лицом
    к камере: это даёт GLTextItem, отсюда и наследуемся.

    Возвращает класс или None, если элемента подписи в сборке нет.
    """
    base = getattr(gl, "GLTextItem", None)
    if base is None:
        return None

    from qgis.PyQt import QtCore, QtGui

    class HaloText(base):
        """Подпись с обводкой и отступом от точки."""

        def __init__(self, *a, **kw):
            self.halo = kw.pop("halo", (255, 255, 255, 230))
            self.halo_width = float(kw.pop("halo_width", 3.0))
            self.offset = kw.pop("offset", (10, -8))
            super().__init__(*a, **kw)
            self.setGLOptions("translucent")

        def paint(self):
            if len(self.text) < 1:
                return
            self.setupGLState()
            project = self.compute_projection()
            vec3 = QtGui.QVector3D(*self.pos)
            pos = self.align_text(project.map(vec3).toPointF())
            pos = QtCore.QPointF(pos.x() + self.offset[0],
                                 pos.y() + self.offset[1])
            painter = QtGui.QPainter(self.view())
            painter.setRenderHints(
                QtGui.QPainter.RenderHint.Antialiasing
                | QtGui.QPainter.RenderHint.TextAntialiasing)
            path = QtGui.QPainterPath()
            path.addText(pos, self.font, self.text)
            pen = QtGui.QPen(QtGui.QColor(*self.halo))
            pen.setWidthF(self.halo_width)
            pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(QtGui.QColor(self.color))
            painter.drawPath(path)
            painter.end()

    return HaloText


# потолок объектов на слой. Раньше он стоял на пятистах, и слой поясов
# в 1174 объекта показывался меньше чем наполовину. Основной сдержкой
# теперь служит бюджет вершин (_body_budget), а этот потолок остаётся
# против разрастания числа мешей в сцене

# линии дешевле тел, но контуры рельефа идут тысячами: на 2349 контурах
# получалось полтора миллиона вершин и нечитаемая паутина
_MAX_LINES = 1500


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
    elif kind == "shell":         # оболочка в слой: тело и стрелка вниз
        p.drawEllipse(QPointF(0.40 * s, 0.36 * s), 0.26 * s, 0.20 * s)
        p.drawLine(QPointF(0.14 * s, 0.36 * s),
                   QPointF(0.14 * s, 0.56 * s))
        p.drawLine(QPointF(0.66 * s, 0.36 * s),
                   QPointF(0.66 * s, 0.56 * s))
        pen2 = QPen(QColor("#0E7C66"))
        pen2.setWidthF(1.6)
        pen2.setCapStyle(cap)
        p.setPen(pen2)
        p.drawLine(QPointF(0.40 * s, 0.60 * s),
                   QPointF(0.40 * s, 0.92 * s))
        p.drawLine(QPointF(0.40 * s, 0.92 * s),
                   QPointF(0.26 * s, 0.76 * s))
        p.drawLine(QPointF(0.40 * s, 0.92 * s),
                   QPointF(0.54 * s, 0.76 * s))
    elif kind == "cad":           # выгрузка в CAD: тело и угольник
        p.drawRect(int(0.12 * s), int(0.30 * s),
                   int(0.44 * s), int(0.44 * s))
        p.drawLine(QPointF(0.12 * s, 0.30 * s),
                   QPointF(0.30 * s, 0.14 * s))
        p.drawLine(QPointF(0.56 * s, 0.30 * s),
                   QPointF(0.74 * s, 0.14 * s))
        p.drawLine(QPointF(0.30 * s, 0.14 * s),
                   QPointF(0.74 * s, 0.14 * s))
        p.drawLine(QPointF(0.74 * s, 0.14 * s),
                   QPointF(0.74 * s, 0.58 * s))
        pen3 = QPen(QColor("#0E7C66"))
        pen3.setWidthF(1.6)
        pen3.setCapStyle(cap)
        p.setPen(pen3)
        p.drawLine(QPointF(0.62 * s, 0.90 * s),
                   QPointF(0.92 * s, 0.90 * s))
        p.drawLine(QPointF(0.92 * s, 0.90 * s),
                   QPointF(0.92 * s, 0.62 * s))
    elif kind == "grid":          # короб: рамка, сетка и стрелка севера
        p.drawRect(int(0.14 * s), int(0.28 * s),
                   int(0.56 * s), int(0.56 * s))
        p.drawLine(QPointF(0.32 * s, 0.28 * s),
                   QPointF(0.32 * s, 0.84 * s))
        p.drawLine(QPointF(0.52 * s, 0.28 * s),
                   QPointF(0.52 * s, 0.84 * s))
        p.drawLine(QPointF(0.14 * s, 0.48 * s),
                   QPointF(0.70 * s, 0.48 * s))
        p.drawLine(QPointF(0.14 * s, 0.66 * s),
                   QPointF(0.70 * s, 0.66 * s))
        pen3 = QPen(QColor("#0E7C66"))
        pen3.setWidthF(1.6)
        pen3.setCapStyle(cap)
        p.setPen(pen3)
        p.drawLine(QPointF(0.84 * s, 0.80 * s),
                   QPointF(0.84 * s, 0.22 * s))
        p.drawLine(QPointF(0.84 * s, 0.22 * s),
                   QPointF(0.74 * s, 0.36 * s))
        p.drawLine(QPointF(0.84 * s, 0.22 * s),
                   QPointF(0.94 * s, 0.36 * s))
    elif kind == "spin":          # вращение: дуга со стрелкой
        p.drawArc(int(0.18 * s), int(0.24 * s),
                  int(0.64 * s), int(0.52 * s), 30 * 16, 260 * 16)
        pen2 = QPen(QColor("#C2622C"))
        pen2.setWidthF(1.6)
        pen2.setCapStyle(cap)
        p.setPen(pen2)
        p.drawLine(QPointF(0.74 * s, 0.30 * s),
                   QPointF(0.84 * s, 0.40 * s))
        p.drawLine(QPointF(0.84 * s, 0.40 * s),
                   QPointF(0.70 * s, 0.46 * s))
    elif kind == "frames":        # съёмка оборота: стопка кадров
        for k, off in enumerate((0.10, 0.20, 0.30)):
            p.drawRect(int(off * s), int((0.22 + off * 0.5) * s),
                       int(0.52 * s), int(0.36 * s))
        p.setBrush(QColor("#C2622C"))
        p.drawEllipse(QPointF(0.56 * s, 0.58 * s), 0.07 * s, 0.07 * s)
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
    elif kind == "line":          # прямая линия разреза с засечками
        # Ломаная с точками была неотличима от значка контура:
        # тот же набор фигур, а на восемнадцати пикселях и та же
        # картинка. Здесь одна прямая и поперечные засечки.
        p.drawLine(QPointF(0.14 * s, 0.78 * s),
                   QPointF(0.86 * s, 0.22 * s))
        pen2 = QPen(QColor("#C2622C"))
        pen2.setWidthF(1.6)
        pen2.setCapStyle(cap)
        p.setPen(pen2)
        for t in (0.0, 0.5, 1.0):
            x = 0.14 + (0.86 - 0.14) * t
            y = 0.78 + (0.22 - 0.78) * t
            p.drawLine(QPointF((x - 0.06) * s, (y - 0.08) * s),
                       QPointF((x + 0.06) * s, (y + 0.08) * s))
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
    first = _DIALOG is None
    if first:
        _DIALOG = _build_dialog(parent)
    # Показываем ДО чтения слоёв. На большом проекте чтение занимает
    # секунды, и всё это время окно уже создано, но не показано:
    # человек жмёт кнопку и не видит ничего. К моменту показа окно
    # оказывалось позади главного, и открыть его удавалось только
    # свернув QGIS.
    _DIALOG.show()
    _DIALOG.raise_()
    # Поднять мало: без передачи ввода окно у части оконных
    # управляющих остаётся за главным.
    _DIALOG.activateWindow()
    if first:
        # Даём окну прорисоваться прежде долгой работы: иначе
        # оно висит пустым прямоугольником.
        from qgis.PyQt.QtWidgets import QApplication
        QApplication.processEvents()
    _DIALOG.refresh_layers()


def _build_dialog(parent):
    """Окно просмотра: собирается по требованию.

    Классы окна живут в `viewer_dialog.py` и тянут Qt на верхнем уровне.
    Импорт отложен сюда: модуль читается и там, где QGIS ещё не поднят,
    а окно там никто не открывает.
    """
    from .viewer_dialog import ViewerDialog
    return ViewerDialog(parent)
