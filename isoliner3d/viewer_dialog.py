# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Само окно просмотра: диалог и вид сцены.

Раньше оба класса жили внутри функции `_build_dialog` в `viewer3d.py`:
так откладывался импорт Qt, ведь модуль читается и там, где QGIS ещё
не поднят. Из-за этого один файл разросся до шести тысяч строк, и правки
в нём промахивались мимо.

Приём тот же, но перенесён на уровень выше: Qt импортируется здесь,
на верхнем уровне, а откладывается импорт самого этого модуля - его
делает `_build_dialog`, когда окно и правда открывают.

Расчёты, которые считаются числами, лежат в `viewer_core.py`, общие
помощники окна остались в `viewer3d.py` и приходят сюда импортом.
"""

import os

from .iso3d import weld
from .lights import soft_shader

from .viewer3d import (    # noqa: F401
    LIGHT_DIR, MAX_VERTS_SCENE, MIN_VERTS_LAYER, PALETTE, _DRAWNL_KEY,
    _DRAWN_KEY,
    _MAX_LINES, _MAX_POINT_LABELS, _Prof, _SCENE_KEY, _VOX_FACE_LIMIT,
    _auto_step, _band_count, _band_items, _bary_z, _closed_and_border,
    is_bed_grid, volume_beyond_box, bed_pairs,
    _css_rgba, _draw_on_top, _find_data, _flat_z, _halo_text_item,
    _import_gl, _layer_budget, _layer_has_z, _log, _map_order, _parts_xyz,
    _prism, _ramp_from_renderer, _read_raster, _tessellate, _tool_icon,
    _tri_cached, bed_to_mesh_arrays, clip_wall, colormap, cylinder,
    draw_depth, field_color, flat_marker_mesh, grid_to_mesh_arrays,
    layer_lift, polygon_mask, polyline_dist_side, ramp_colors,
    sample_bilinear, shade_colors, thin_labels_xy, tr, walk_rings,
    z_range_mask)

import numpy as np                                # noqa: E402

# Отрисовка идёт вложенным pyqtgraph: путь к нему ставит
# _import_gl, поэтому импорт qgis идёт после него.
gl = _import_gl()
from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer    # noqa: E402
try:  # QGIS 3.30+/4: Qgis.GeometryType.*
    from qgis.core import Qgis                     # noqa: E402
    _POINT_GT = Qgis.GeometryType.Point
    _LINE_GT = Qgis.GeometryType.Line
    _POLYGON_GT = Qgis.GeometryType.Polygon
except Exception:  # старые QGIS 3
    from qgis.core import QgsWkbTypes              # noqa: E402
    _POINT_GT = QgsWkbTypes.GeometryType.PointGeometry
    _LINE_GT = QgsWkbTypes.GeometryType.LineGeometry
    _POLYGON_GT = QgsWkbTypes.GeometryType.PolygonGeometry
from qgis.PyQt.QtCore import Qt    # noqa: E402
from qgis.PyQt.QtWidgets import (    # noqa: E402
    QDialog, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem,
    QDoubleSpinBox, QPushButton, QLabel, QFormLayout, QSplitter, QWidget,
    QComboBox, QLineEdit, QGroupBox, QSpinBox,
    QTableWidget, QTableWidgetItem,
    QFrame, QMenu, QCheckBox, QToolButton)

# Qt5/Qt6: enum'ы либо плоские, либо в scoped-подклассах
_CHECKED = getattr(getattr(Qt, "CheckState", Qt), "Checked")
_UNCHECKED = getattr(getattr(Qt, "CheckState", Qt), "Unchecked")
_USER_ROLE = getattr(getattr(Qt, "ItemDataRole", Qt), "UserRole")
_CHECKABLE = getattr(getattr(Qt, "ItemFlag", Qt),
                     "ItemIsUserCheckable")
_ENABLED = getattr(getattr(Qt, "ItemFlag", Qt), "ItemIsEnabled")


class _OneStyle(dict):
    """Стиль слоя, у которого цвет один на все объекты.

    Слой с одним символом красится одинаково целиком, и спрашивать
    цвет у каждого объекта незачем: на блочной модели в полмиллиона
    точек это полмиллиона вызовов ради одного и того же ответа.

    Ведёт себя как словарь, отвечающий на любой номер объекта, чтобы
    места, которые читают стиль, не различали этот случай.
    """

    def __init__(self, value):
        dict.__init__(self)
        self._value = value

    def get(self, key, default=None):
        return self._value

    def __contains__(self, key):
        return True

    def __getitem__(self, key):
        return self._value

    def __len__(self):
        return 1

    def values(self):
        return [self._value]


class _PickView(gl.GLViewWidget):
    """GLViewWidget с колбэком на клик без перетаскивания."""
    pick_cb = None
    pivot_cb = None
    dbl_cb = None

    undo_cb = None
    cancel_cb = None
    hover_cb = None
    draw_mode = False
    ortho = False

    bg_top = None      # верхний цвет градиента, доли единицы
    bg_bottom = None   # нижний

    def paint(self, *, region, viewport, useItemNames=False):
        """Отрисовка вида с градиентным фоном.

        Фон нельзя нарисовать ни подложкой Qt, ни элементом сцены:
        область OpenGL закрашивает подложку, а элемент сцены пришлось
        бы держать обращённым к камере. Правильное место здесь -
        там, где вид и так заливает фон одним цветом.

        Градиент кладётся полосами по высоте кадра: их немного,
        и цена такой заливки не отличается от сплошной.
        """
        if self.bg_top is None or self.bg_bottom is None:
            return super().paint(region=region, viewport=viewport,
                                 useItemNames=useItemNames)
        from OpenGL import GL
        self.setProjection(region, viewport)
        self.setModelview()
        GL.glClearColor(*self.bg_bottom)
        GL.glClear(GL.GL_DEPTH_BUFFER_BIT | GL.GL_COLOR_BUFFER_BIT)
        self._paint_gradient(GL)
        self.drawItemTree(useItemNames=useItemNames)

    def _paint_gradient(self, GL):
        """Залить кадр полосами от нижнего цвета к верхнему."""
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glPushMatrix()
        GL.glLoadIdentity()
        GL.glOrtho(0, 1, 0, 1, -1, 1)
        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glPushMatrix()
        GL.glLoadIdentity()
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glDisable(GL.GL_LIGHTING)
        lo = np.asarray(self.bg_bottom, dtype=float)
        hi = np.asarray(self.bg_top, dtype=float)
        n = 24
        GL.glBegin(GL.GL_QUAD_STRIP)
        for k in range(n + 1):
            t = float(k) / n
            c = lo + (hi - lo) * t
            GL.glColor4f(*[float(q) for q in c])
            GL.glVertex2f(0.0, t)
            GL.glVertex2f(1.0, t)
        GL.glEnd()
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glPopMatrix()
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glPopMatrix()
        GL.glMatrixMode(GL.GL_MODELVIEW)

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
        if self.draw_mode and _btn_code(ev.button()) == 2:
            if self.undo_cb is not None:
                self.undo_cb()
            ev.accept()
            return
        self._press = self._evpos(ev)
        self._press_btn = ev.button()
        super().mousePressEvent(ev)

    def mouseReleaseEvent(self, ev):
        pos = self._evpos(ev)
        pr = getattr(self, "_press", None)
        btn = getattr(self, "_press_btn", None)
        super().mouseReleaseEvent(ev)
        if pr is None or abs(pos[0] - pr[0]) >= 3 \
                or abs(pos[1] - pr[1]) >= 3:
            return                      # это было вращение, не щелчок
        # Кнопку сравниваем по НОМЕРУ, а не с константой: в Qt6
        # это уже не число, и сравнение с константой другого модуля
        # молча даёт ложь - правый щелчок уходил в опрос точки.
        if _btn_code(btn) == 2 and not self.draw_mode:
            # Правая кнопка в сцене свободна: перетаскиванием камера
            # берёт её себе, а щелчок без движения - нет.
            if self.pivot_cb is not None:
                self.pivot_cb(pos[0], pos[1])
            return
        if self.pick_cb is not None:
            self.pick_cb(pos[0], pos[1])

    @staticmethod
    def _evpos(ev):
        p = ev.position() if hasattr(ev, "position") else ev.pos()
        return (float(p.x()), float(p.y()))


def _pg_vector():
    """Класс вектора pyqtgraph, тем же путём, каким берётся сцена.

    Он живёт в корне pyqtgraph, а не в opengl: взяв его не оттуда,
    получишь второй экземпляр модуля - на этом уже обжигались
    со светом.
    """
    try:
        _import_gl()
        from pyqtgraph import Vector
        return Vector
    except Exception:  # nosec - без него остаётся правка на месте
        return None


def _btn_code(btn):
    """Номер кнопки мыши, одинаково в Qt5 и Qt6.

    В Qt6 кнопка - не число, и сравнение с константой, взятой
    из другого модуля, даёт ложь без всякой ошибки. Левая - 1,
    правая - 2, и эти номера не менялись никогда.
    """
    if btn is None:
        return 0
    try:
        return int(btn)
    except (TypeError, ValueError):
        return int(getattr(btn, "value", 0))


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
        self._spin_timer = None
        self._was_active = False
        self._mask_cache = {}
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
        # Номер версии в заголовке: без него не отличить, какая сборка
        # стоит, и разбор чужого журнала начинается с гадания.
        ver = ""
        try:
            import os as _os
            meta = _os.path.join(_os.path.dirname(_os.path.abspath(
                __file__)), "metadata.txt")
            with open(meta, encoding="utf-8") as fh:
                for ln in fh:
                    if ln.startswith("version="):
                        ver = " " + ln.split("=", 1)[1].strip()
                        break
        except Exception:  # nosec
            ver = ""
        self.setWindowTitle(
            tr("Isoliner3D - 3D-просмотр поверхностей") + ver)
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
        self._mode_rows = {}     # строки свойств по режимам
        self._opt_form = None
        self._clip_now = None    # контур обрезки на время сборки
        self._z_surf_now = None  # поверхности отсечки
        self._clip_seen = 0      # граней до обрезки, для отчёта
        self._clip_kept = 0      # граней после
        self._cap_open = 0       # тел, у которых срез остался открытым
        self._cap_border = 0     # краевых рёбер у них до резки
        self._cap_edges_seen = 0  # краевых рёбер, поданных крышке
        self._cap_segs = 0       # из них легло на контур среза
        self._cap_polys = 0      # полигонов крышки собралось
        self._cap_bad = 0        # полигонов, не разбившихся
        # Причины раннего выхода со счётчиками: одна на весь
        # прогон перетиралась последним телом, и по ней нельзя
        # было судить об остальных.
        self._cap_why = {}
        self._cap_calls = 0
        self._cap_with_faces = 0
        self._body_open = 0
        self._body_open_edges = 0
        self._clip_dmin = float("inf")   # ближайшая грань к линии
        self._clip_dmax = 0.0            # дальняя
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
        self.grid_planes = QComboBox()
        for lab, key in ((tr("Только короб"), ""),
                         (tr("Пол"), "floor"),
                         (tr("Пол и стены"), "floor,walls"),
                         (tr("Стены"), "walls")):
            self.grid_planes.addItem(lab, key)
        self.grid_planes.setToolTip(tr(
            "На каких плоскостях короба рисовать сетку. Пол даёт "
            "масштаб в плане, стены - по отметкам, что для разреза "
            "важнее."))
        self.grid_step = QDoubleSpinBox()
        self.grid_step.setRange(0.0, 1000000.0)
        self.grid_step.setDecimals(1)
        self.grid_step.setValue(0.0)
        self.grid_step.setSpecialValueText(tr("(от размаха)"))
        self.grid_step.setToolTip(tr(
            "Шаг сетки в единицах карты. Ноль берёт круглый шаг "
            "от размаха сцены. Слишком мелкий шаг укрупняется сам: "
            "сетка гуще самой сцены читать не помогает, а рисуется "
            "долго."))
        self.zs_top = QComboBox()
        self.zs_bot = QComboBox()
        for w, tip in (
                (self.zs_top,
                 tr("Поверхность сверху: остаётся то, что ниже неё. "
                    "Так отсекают всё выше дневного рельефа или выше "
                    "кровли пласта.")),
                (self.zs_bot,
                 tr("Поверхность снизу: остаётся то, что выше неё. "
                    "Вместе с верхней оставляет только пласт."))):
            w.setToolTip(tip)
            w.setMinimumWidth(140)
        self.zlo = QDoubleSpinBox()
        self.zhi = QDoubleSpinBox()
        for w, pref in ((self.zlo, "z\u2265 "), (self.zhi, "z\u2264 ")):
            w.setRange(-1e7, 1e7)
            w.setDecimals(1)
            w.setSpecialValueText(tr("(нет)"))
            w.setValue(-1e7)
            w.setFixedWidth(96)
            w.setPrefix(pref)
            w.setToolTip(tr(
                "Обрезка по отметке. Контур и коридор режут только "
                "в плане, а разрез по пачке пластов задаётся "
                "отметками. Обе строки живут в свойствах сцены, "
                "рядом с остальной обрезкой. Снимаются кнопкой «Снять» "
                "или общей кнопкой очистки на плашке."))
        for w in (self.clip_combo, self.clip_side, self.clip_width,
                  self.zlo, self.zhi):
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
        # Тринадцать строк подряд читаются как свалка. Делим на три
        # части по смыслу: как показывать, что отрезать, чем мерить.
        # В каждой не больше пяти строк, и нужное находится глазом.
        self.scene_box = QGroupBox(tr("Сцена"))
        sv = QVBoxLayout(self.scene_box)

        box_view = QGroupBox(tr("Вид"))
        f1 = QFormLayout(box_view)
        f1.addRow(tr("Вертикальное преувеличение"), self.vex)
        f1.addRow(tr("Разнос по Z (шаг вниз)"), self.spacing)
        f1.addRow(tr("Прозрачность поверхностей (процентов)"),
                  self.opacity)
        f1.addRow(tr("Сторона текстуры (пикселей)"), self.texside)
        f1.addRow(tr("Предел вершин в сцене (тысяч)"), self.vert_cap)
        sv.addWidget(box_view)

        box_clip = QGroupBox(tr("Обрезка"))
        f2 = QFormLayout(box_clip)
        self.clip_combo.setToolTip(tr(
            "Обрезка по контуру или линии: остаётся то, что внутри. "
            "Годится любой полигональный слой проекта, а также "
            "нарисованное прямо в сцене - его можно сохранить слоем "
            "кнопкой на плашке и выбрать здесь."))
        f2.addRow(tr("Контуром или линией"), self.clip_combo)
        self.clip_side.setToolTip(tr(
            "Что оставить от контура: внутренность, наружное или "
            "коридор вдоль линии заданной полуширины."))
        f2.addRow(tr("Что оставить"), self.clip_side)
        f2.addRow(tr("Полуширина коридора, м"), self.clip_width)
        zrow = QHBoxLayout()
        zrow.addWidget(self.zlo)
        zrow.addWidget(self.zhi)
        self.btn_zclear = QToolButton()
        self.btn_zclear.setText(tr("Снять"))
        self.btn_zclear.setToolTip(tr("Снять обрезку по отметке"))
        self.btn_zclear.clicked.connect(lambda *_a: self._z_clear())
        zrow.addWidget(self.btn_zclear)
        f2.addRow(tr("По отметке"), zrow)
        srow = QHBoxLayout()
        srow.addWidget(self.zs_top)
        srow.addWidget(self.zs_bot)
        self.mask_lyr = QComboBox()
        self.mask_lyr.setToolTip(tr(
            "Растр-маска: тело остаётся там, где значение не меньше "
            "порога. Полигон задаёт границу линией, а маска - "
            "площадью: так удобнее, когда границу посчитал "
            "инструмент, а не рисовал человек."))
        self.mask_level = QDoubleSpinBox()
        self.mask_level.setRange(-1e9, 1e9)
        self.mask_level.setDecimals(3)
        self.mask_level.setValue(0.5)
        self.mask_level.setToolTip(tr(
            "Порог маски: что не меньше - внутри. Пропуск в маске "
            "считается «снаружи»."))
        self.zs_top.setToolTip(tr(
            "Верхняя поверхность отсечки: всё выше неё не "
            "показывается. Растр, а не отметка: кровля меняется "
            "по площади."))
        self.zs_bot.setToolTip(tr(
            "Нижняя поверхность отсечки: всё ниже неё "
            "не показывается."))
        f2.addRow(tr("Сверху и снизу (растры)"), srow)
        self.fence_all = QCheckBox(tr("Показать заборами по линии"))
        self.fence_all.setToolTip(tr(
            "Грид пластов показывается вертикальным разрезом "
            "по выбранной линии: сквозь всю пачку сразу, с кровлей "
            "и подошвой каждого пласта. Это чертёж разреза, "
            "поставленный в сцену, а не поверхность, натянутая "
            "на линию. Линия берётся та же, что и для обрезки."))
        box_mask = QGroupBox(tr("Маска и заборы"))
        f5 = QFormLayout(box_mask)
        mrow = QHBoxLayout()
        mrow.addWidget(self.mask_lyr)
        mrow.addWidget(self.mask_level)
        f5.addRow(tr("По маске (растр)"), mrow)
        f5.addRow("", self.fence_all)
        sv.addWidget(box_mask)
        sv.addWidget(box_clip)

        self.light = QSpinBox()
        self.light.setRange(0, 100)
        self.light.setValue(55)
        self.light.setSuffix(" %")
        self.light.setToolTip(tr(
            "Отмывка по наклону поверхности. Поверхность, раскрашенная "
            "шкалой, рисуется одним цветом вершин без света вовсе, "
            "и рельеф внутри одного оттенка пропадает. Ноль - как "
            "было."))
        self.bg_grad = QCheckBox(tr("Градиентный фон"))
        # Градиент включён по умолчанию: на плоской заливке тело
        # теряет глубину, а верх и низ сцены не различить.
        self.bg_grad.setChecked(True)
        self.smooth_edges = QCheckBox(tr("Сглаживать края"))
        self.smooth_edges.setChecked(True)
        self.bg_grad.toggled.connect(self._bg_apply)
        self.mask_lyr.currentIndexChanged.connect(
            self._schedule_rebuild)
        self.mask_level.valueChanged.connect(self._schedule_rebuild)
        self.fence_all.toggled.connect(self._schedule_rebuild)
        self.light.valueChanged.connect(self._schedule_rebuild)
        self.smooth_edges.setToolTip(tr(
            "Сглаживание краёв линий и подписей. Действует "
            "со следующего открытия окна: режим рисования выбирается "
            "при его создании."))
        box_look = QGroupBox(tr("Оформление"))
        f4 = QFormLayout(box_look)
        f4.addRow(tr("Отмывка"), self.light)
        f4.addRow("", self.bg_grad)
        f4.addRow("", self.smooth_edges)
        sv.addWidget(box_look)

        box_grid = QGroupBox(tr("Координатный короб"))
        f3 = QFormLayout(box_grid)
        f3.addRow(tr("Сетка"), self.grid_planes)
        f3.addRow(tr("Шаг сетки, м"), self.grid_step)
        sv.addWidget(box_grid)
        sv.addWidget(self.auto_rebuild)

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
                           (tr("Воксели по кубу"), "vox"),
                           (tr("Стенка по линии"), "wall"),
                           (tr("Объёмная заливка"), "fog")):
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
        self.zband.setToolTip(tr(
            "В режиме тела пласта это ПЕРВЫЙ канал пары: "
            "за ним идёт подошва, дальше следующая пара. Грид "
            "пластов показывается всеми парами сразу, а этот "
            "канал говорит, с какого пласта начать."))
        of.addRow(tr("Канал высот (Z)"), self.zband)
        # Обёртка вокруг строки окраски: прятать по режиму можно
        # только виджет, у раскладки такого нет.
        self.color_row = QWidget()
        crow = QHBoxLayout(self.color_row)
        crow.setContentsMargins(0, 0, 0, 0)
        crow.addWidget(self.color_combo, 1)
        crow.addWidget(self.color_btn, 0)
        of.addRow(tr("Окраска"), self.color_row)
        of.addRow(tr("Канал атрибута"), self.aband)
        self.iso_table = QTableWidget(0, 3)
        self.iso_table.setHorizontalHeaderLabels(
            [tr("Уровень"), tr("Цвет"), tr("Непрозрачность, %")])
        self.iso_table.verticalHeader().setVisible(False)
        self.iso_table.setMinimumHeight(120)
        self.iso_table.setToolTip(tr(
            "Строка на оболочку. Пустая ячейка берёт автоматическое: "
            "цвет по номеру оболочки, плотность растёт наружу. "
            "Снятая галка убирает оболочку, не стирая строку. "
            "Пустая таблица это отсечка и одна оболочка. "
            "Непрозрачность в процентах: сто это плотная оболочка. "
            "По цвету щёлкните дважды - откроется выбор. "
            "Правая кнопка на строке удаляет её."))
        self.lyr_opacity = QSpinBox()
        self.lyr_opacity.setRange(0, 100)
        self.lyr_opacity.setValue(0)
        self.lyr_opacity.setSuffix(" %")
        self.lyr_opacity.setToolTip(tr(
            "Прозрачность этого слоя поверх общей. Общая правит всю "
            "сцену разом, а здесь можно приглушить один слой, чтобы "
            "видеть тело под ним. Работает и на текстуру."))
        self.iso_cap = QCheckBox(tr("Закрывать выход на край куба"))
        self.iso_cap.setToolTip(tr(
            "Маршевая поверхность обрывается на границе куба: тело "
            "выглядит вскрытым, а объём по нему не посчитать. Крышка "
            "закрывает этот выход плоским куском на самой грани. "
            "По умолчанию выключено: крышка нужна не всегда, "
            "а на просмотр она добавляет граней."))
        self.iso_smooth = QSpinBox()
        self.iso_smooth.setRange(0, 20)
        self.iso_smooth.setValue(0)
        self.iso_smooth.setToolTip(tr(
            "Сколько проходов сглаживания. Маршевая поверхность идёт "
            "ступенями по ячейкам куба, и сглаживание их сажает. Тело "
            "при этом слегка ужимается, поэтому для подсчёта объёма "
            "берите несглаженное."))
        self.iso_min_faces = QSpinBox()
        self.iso_min_faces.setRange(0, 1000000)
        self.iso_min_faces.setValue(0)
        self.iso_min_faces.setSingleStep(50)
        self.iso_min_faces.setToolTip(tr(
            "Отбросить куски мельче этого числа граней. Мелкие обрывки "
            "на поверхности шумят и мешают читать форму. Если порог "
            "убирает всё, поверхность остаётся как была: пустая сцена "
            "это не чистка, а потеря."))
        self.vox_classes = QSpinBox()
        self.vox_classes.setRange(1, 32)
        self.vox_classes.setValue(8)
        self.vox_classes.setToolTip(tr(
            "На сколько интервалов раскладывается содержание при "
            "окраске вокселей. Соседние грани одного интервала "
            "сливаются в один прямоугольник, поэтому чем меньше "
            "интервалов, тем легче сцена."))
        self.fog_density = QDoubleSpinBox()
        self.fog_density.setRange(0.0, 1.0)
        self.fog_density.setDecimals(2)
        self.fog_density.setSingleStep(0.05)
        self.fog_density.setValue(0.6)
        self.fog_density.setToolTip(tr(
            "Плотность объёмной заливки. Ниже отсечки заливки нет "
            "вовсе, выше неё непрозрачность растёт со значением. "
            "Заливка не заменяет оболочку, а дополняет её: "
            "оболочка отвечает, где граница тела, заливка - как "
            "значение меняется вокруг."))
        self.wall_step = QDoubleSpinBox()
        self.wall_step.setRange(0.0, 100000.0)
        self.wall_step.setDecimals(1)
        self.wall_step.setValue(0.0)
        self.wall_step.setToolTip(tr(
            "Шаг узлов стенки вдоль линии, в единицах карты. Ноль "
            "берёт шаг грида: мельче него данных всё равно нет. "
            "Линия берётся из списка обрезки, поэтому нарисуйте "
            "её или выберите слой там же."))
        self.vox_merge = QCheckBox(tr("Сливать соседние грани"))
        self.vox_merge.setChecked(True)
        self.vox_merge.setToolTip(tr(
            "Слияние делает сцену в разы легче, но оболочка перестаёт "
            "быть замкнутой: длинный прямоугольник упирается в два "
            "коротких, общего ребра у них нет. Снимите флаг, если "
            "по этой модели считается объём."))
        of.addRow(tr("Прозрачность слоя"), self.lyr_opacity)
        of.addRow(tr("Отсечка куба"), self.iso_level)
        of.addRow(tr("Оболочки"), self.iso_table)
        of.addRow(self.iso_cap)
        of.addRow(tr("Сглаживание, проходов"), self.iso_smooth)
        of.addRow(tr("Отбросить куски мельче, граней"),
                  self.iso_min_faces)
        of.addRow(tr("Интервалов окраски"), self.vox_classes)
        of.addRow(tr("Шаг стенки, м (0 - шаг грида)"), self.wall_step)
        of.addRow(tr("Плотность заливки"), self.fog_density)
        of.addRow("", self.vox_merge)
        self._opt_form = of
        # Строка видна только в своём режиме: поле, которое ничего
        # не делает, человек всё равно правит и потом ищет причину.
        self._mode_rows.update({
            # Каналы читают только поверхность и тело пласта. Режимы
            # куба берут отметки из шага между каналами, а цвет
            # из своей таблицы либо интервалов.
            "zband": (self.zband, ("auto", "surface", "body")),
            "cband": (self.color_row, ("auto", "surface", "body")),
            "aband": (self.aband, ("auto", "surface", "body")),
            "iso_level": (self.iso_level, ("iso", "vox", "fog")),
            "iso_table": (self.iso_table, ("iso",)),
            "iso_cap": (self.iso_cap, ("iso",)),
            "iso_smooth": (self.iso_smooth, ("iso",)),
            "iso_min_faces": (self.iso_min_faces, ("iso",)),
            "vox_classes": (self.vox_classes, ("vox",)),
            "vox_merge": (self.vox_merge, ("vox",)),
            "wall_step": (self.wall_step, ("wall",)),
            "fog_density": (self.fog_density, ("fog",)),
        })
        self.iso_level.valueChanged.connect(self._save_opts)
        self.vox_classes.valueChanged.connect(self._save_opts)
        self.lyr_opacity.valueChanged.connect(self._save_opts)
        self.iso_table.itemChanged.connect(self._iso_table_edited)
        self.iso_table.cellDoubleClicked.connect(self._iso_cell_clicked)
        self.iso_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.iso_table.customContextMenuRequested.connect(
            self._iso_menu)
        self.iso_cap.toggled.connect(self._save_opts)
        self.iso_smooth.valueChanged.connect(self._save_opts)
        self.iso_min_faces.valueChanged.connect(self._save_opts)
        self.wall_step.valueChanged.connect(self._save_opts)
        self.fog_density.valueChanged.connect(self._save_opts)
        self.vox_merge.toggled.connect(self._save_opts)
        for w in (self.mode_combo, self.zband, self.aband):
            w.currentIndexChanged.connect(self._save_opts)
        self.mode_combo.currentIndexChanged.connect(self._sync_mode_rows)
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
        self.vec_shape = QComboBox()
        for label, key in ((tr("Круг (экранный)"), "circle"),
                           (tr("Квадрат"), "square"),
                           (tr("Ромб"), "diamond"),
                           (tr("Треугольник"), "triangle"),
                           (tr("Крест"), "cross")):
            self.vec_shape.addItem(label, key)
        self.vec_shape.setToolTip(tr(
            "Круг рисуется экранным значком: размер в пикселях, "
            "при приближении не растёт, стоит почти ничего. "
            "Остальные виды лежат в плане на отметке точки: размер "
            "в метрах, значок закрывается поверхностью и уходит "
            "под кровлю, но с высоты сплющивается."))
        self.vec_msize = QDoubleSpinBox()
        self.vec_msize.setRange(0.1, 100000.0)
        self.vec_msize.setDecimals(1)
        self.vec_msize.setValue(20.0)
        self.vec_msize.setToolTip(tr(
            "Размер плоского значка в метрах, по ширине."))
        self.vec_nlab = QSpinBox()
        self.vec_nlab.setRange(0, 5000)
        self.vec_nlab.setValue(400)
        self.vec_nlab.setToolTip(tr(
            "Сколько подписей ставить, не больше. Каждая подпись "
            "это отдельный элемент отрисовки, поэтому число "
            "ограничено. Ноль означает «без подписей»."))
        self.vec_label = QComboBox()
        self.vec_label.setToolTip(tr(
            "Поле, из которого берётся подпись точки. Подписи "
            "прореживаются: если рядом уже есть подписанная точка, "
            "текст не ставится, иначе они налезают друг на друга."))
        self.vec_psize = QDoubleSpinBox()
        self.vec_psize.setRange(0.0, 60.0)
        self.vec_psize.setDecimals(1)
        self.vec_psize.setSingleStep(1.0)
        self.vec_psize.setValue(0.0)
        self.vec_psize.setToolTip(tr(
            "Размер точки в пикселях. Ноль означает «из стиля слоя»: "
            "размер маркера на карте задан в миллиметрах печати "
            "и пересчитывается от обычных двух миллиметров. Размер "
            "экранный, при приближении точка не растёт."))
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
        self.vec_opacity = QSpinBox()
        self.vec_opacity.setRange(0, 100)
        self.vec_opacity.setValue(0)
        self.vec_opacity.setSuffix(" %")
        self.vec_opacity.setToolTip(tr(
            "Прозрачность этого слоя. Общая настройка сцены правит "
            "только поверхности: тело не должно просвечивать оттого, "
            "что просвечивает поверхность над ним."))
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
        vf.addRow(tr("Прозрачность слоя"), self.vec_opacity)
        vf.addRow(tr("Размер точки, px (0 - из стиля)"),
                  self.vec_psize)
        vf.addRow(tr("Вид маркера"), self.vec_shape)
        vf.addRow(tr("Размер значка, м"), self.vec_msize)
        vf.addRow(tr("Поле подписи точек"), self.vec_label)
        vf.addRow(tr("Подписей не более"), self.vec_nlab)
        vf.addRow(tr("Низ призмы с поверхности"), self.vec_base)
        vf.addRow(tr("Верх призмы"), self.vec_htop)
        vf.addRow(tr("Поле верха или высоты"), self.vec_ztop)
        vf.addRow(tr("Поле подписи скважин"), self.wells_label)
        vf.addRow(tr("Поля отметок"), self.wells_fields)
        for w in (self.vec_kind, self.vec_poly, self.vec_zsrc,
                  self.vec_zfield, self.vec_zsurf, self.vec_label,
                  self.vec_shape,
                  self.vec_ztop,
                  self.vec_base, self.vec_htop, self.wells_label):
            w.currentIndexChanged.connect(self._save_vec_opts)
        self.vec_zoff.valueChanged.connect(self._save_vec_opts)
        self.vec_opacity.valueChanged.connect(self._save_vec_opts)
        self.vec_psize.valueChanged.connect(self._save_vec_opts)
        self.vec_msize.valueChanged.connect(self._save_vec_opts)
        self.vec_nlab.valueChanged.connect(self._save_vec_opts)
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

        self.btn_axes = tool("grid", tr("Координатный короб: деления "
                                        "и подписи по осям"),
                             lambda *_a: self._schedule_rebuild(0),
                             checkable=True)
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
            "save", tr("Сохранить нарисованный контур слоем проекта"),
            self._draw_save)
        btn_shells = tool(
            "shell", tr("Оболочки выбранного слоя в слой проекта"),
            self._shells_to_layer)
        btn_export = tool(
            "export", tr("Выгрузить сцену в файл: GLB, STL или OBJ"),
            self._export_scene)
        self.btn_spin = tool(
            "spin", tr("Вращать сцену (ещё раз - остановить)"),
            self._spin_toggle)
        self.btn_spin.setCheckable(True)
        btn_turn = tool(
            "frames", tr("Снять оборот кадрами PNG"),
            self._spin_capture)
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
        # Сглаживание задаётся ЭТОМУ виджету, до его показа. Общий
        # формат приложения менять нельзя: он применяется к уже
        # созданным окнам не сразу, и первый кадр не выходит, пока
        # окно не пересоздадут - сцена открывалась пустой до
        # сворачивания и разворачивания QGIS.
        if self._state_flag("smooth_edges", True):
            setf = getattr(self.view, "setFormat", None)
            if setf is not None:
                fmt = self.view.format()
                if fmt.samples() < 4:
                    fmt.setSamples(4)
                    setf(fmt)
        self.view.setBackgroundColor((250, 250, 248))
        self._bg_apply()
        self.view.pick_cb = self._pick_at
        self.view.pivot_cb = self._pivot_at
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
        for b in (btn_top, self.btn_ortho, self.btn_axes, self.btn_draw,
                  self.btn_undo,
                  self.btn_done, self.btn_line, self.btn_sketch,
                  btn_clip_off,
                  btn_draw_save, btn_shells, btn_export,
                  self.btn_spin, btn_turn,
                  btn_copy, btn_png):
            b.setParent(self.tools)
            tb.addWidget(b)
        # Полуширина коридора и границы отметок переехали в свойства
        # сцены, к остальной обрезке: на плашке они занимали место
        # у кнопок, которыми пользуются постоянно, а правят их редко.
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
        menu.addSeparator()
        fly = menu.addAction(tr("Подлететь"))
        fly.triggered.connect(lambda *_a: self._fly_to(False))
        orb = menu.addAction(tr("Облететь текущий центр"))
        orb.triggered.connect(self._orbit_now)
        res = menu.addAction(tr("Центр вращения - вся сцена"))
        res.triggered.connect(self._center_reset)
        # exec_ снят в Qt6, exec есть в обоих: берём по имени
        show = getattr(menu, "exec", None) or getattr(menu, "exec_")
        show(widget.mapToGlobal(pos))

    def _center_reset(self, *_a):
        """Вернуть центр вращения на всю сцену."""
        self._center_keeping_view(0.0, 0.0, 0.0)
        self.info.setText(tr("Центр вращения - вся сцена."))

    def _orbit_now(self, *_a):
        """Крутить вокруг ТЕКУЩЕГО центра, ничего не наводя.

        Порядок работы такой: подлететь к слою, поставить центр
        щелчком правой по нужному месту, включить облёт. Если бы облёт
        сам наводился на слой, он бы стирал выбранный центр -
        последний шаг отменял бы предыдущий.
        """
        if hasattr(self, "btn_spin") and not self.btn_spin.isChecked():
            # Кнопка вращения переключается щелчком: так же, как её
            # нажал бы человек, и без разбора, чем она соединена.
            self.btn_spin.click()
        self.info.setText(tr("Облёт вокруг текущего центра."))

    def _fly_to(self, orbit=False):
        """Подвести камеру к выбранному слою.

        На большой сцене мелкий объект искать нечем: он занимает
        пиксель, а кручение вокруг общего центра его только уводит.
        Здесь центр вращения переносится на сам слой, и удаление
        камеры берётся по его охвату - дальше можно крутить вокруг
        него же.

        Сцена живёт в сдвинутых координатах: центр охвата данных
        стоит в нуле, а отметки растянуты преувеличением. Поэтому
        охват слоя переводится тем же преобразованием, каким строились
        меши, иначе камера уедет мимо.
        """
        pk = getattr(self, "_pick", None)
        if not pk:
            self.info.setText(tr("Сначала соберите сцену."))
            return
        lyr = self._current_layer()
        if lyr is None:
            self.info.setText(tr("Выберите слой в списке сцены."))
            return
        ext = lyr.extent()
        if ext is None or ext.isEmpty():
            self.info.setText(tr("У слоя %s нет охвата.")
                              % self._title(lyr))
            return
        tr_ = self._xform(lyr)
        xs = [ext.xMinimum(), ext.xMaximum()]
        ys = [ext.yMinimum(), ext.yMaximum()]
        if tr_ is not None:
            xs, ys = self._xform_xy(tr_, np.asarray(xs, dtype=float),
                                    np.asarray(ys, dtype=float))
            xs, ys = list(xs), list(ys)
        cx, cy = pk["cx"], pk["cy"]
        mx = (float(min(xs)) + float(max(xs))) * 0.5 - cx
        my = (float(min(ys)) + float(max(ys))) * 0.5 - cy
        span = max(float(max(xs)) - float(min(xs)),
                   float(max(ys)) - float(min(ys)), 1.0)
        c = self.view.opts["center"]
        c.setX(mx)
        c.setY(my)
        c.setZ(0.0)
        self.view.opts["distance"] = span * 1.5
        self.view.update()
        self.info.setText(tr("Камера у слоя %s, охват %.0f м.")
                          % (self._title(lyr), span))

    def _current_layer(self):
        """Слой выделенной строки списка сцены."""
        it = self.layer_list.currentItem()
        if it is None:
            return None
        return QgsProject.instance().mapLayer(it.data(_USER_ROLE))

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
        # Заголовок ставится первым. Если дальше что-то сорвётся,
        # окно хотя бы скажет, чьи свойства в нём показаны, а не
        # останется с именем приложения в шапке.
        title = tr("Свойства сцены")
        if lyr is not None:
            title = tr("Свойства слоя: %s") % lyr.name()
        self._props.setWindowTitle(title)
        scene = item is None or item.data(_USER_ROLE) == _SCENE_KEY
        raster = isinstance(lyr, QgsRasterLayer)
        vector = isinstance(lyr, QgsVectorLayer)
        line = vector and self._geom_kind(lyr) == "line"
        self.scene_box.setVisible(scene)
        self.opt_box.setVisible(raster)
        self.vec_box.setVisible(vector)
        self.sec_box.setVisible(line)
        # Подбор строк здесь не вызывается. Значения в виджетах
        # к этому моменту могут принадлежать прежнему слою, и решать
        # по ним, что показывать, нельзя. Строки подбираются в конце
        # загрузки свойств слоя, когда виджеты уже заполнены.

    def _bed_meshes(self, lyr, o):
        """Меши тела пласта в координатах проекта, для выгрузки.

        Сцена строит то же самое, но для показа: с преувеличением
        по вертикали, с разносом слоёв по Z и с прореживанием сетки
        под бюджет вершин. В слой проекта это отдавать нельзя -
        объём такого тела будет неверен ровно во столько раз, во
        сколько растянута вертикаль. Здесь отметки настоящие, сетка
        полная, а обрезка берётся та же, что в сцене: человек её уже
        настроил и видит.

        Возвращает список (вершины, грани, цвет, номер канала кровли).
        """
        import numpy as np
        n_band = _band_count(lyr.source())
        clip, clip_lines = self._clip_ctx()
        lclip, lclip_lines = self._clip_for_layer(lyr, clip, clip_lines)
        pairs = bed_pairs(n_band, o.get("zband", 1))
        # Бюджет делится на все пласты слоя и ещё пополам: у тела
        # пласта на каждую ячейку грида приходится две вершины,
        # кровля и подошва. Считая бюджет по ячейкам целиком,
        # прореживание не включается там, где оно и нужно.
        budget = max(MIN_VERTS_LAYER,
                     self._vert_cap() // max(1, 2 * len(pairs)))
        out = []
        for pi, b_top in enumerate(pairs):
            top, gt = _read_raster(lyr.source(), b_top, None)
            bot, _g = _read_raster(lyr.source(), b_top + 1, None)
            if top is None or bot is None:
                continue
            top = np.where(self._z_kept(top), top, np.nan)
            bot = np.where(self._z_kept(bot), bot, np.nan)
            if lclip:
                top = self._clip_array(top, gt, lclip)
                bot = self._clip_array(bot, gt, lclip)
            if lclip_lines:
                top = self._clip_by_lines(top, gt, lclip_lines)
                bot = self._clip_by_lines(bot, gt, lclip_lines)
            # Сетка полная, пока тело влезает в бюджет вершин сцены.
            # Гриду в полмиллиона ячеек полная сетка даёт миллион
            # треугольников на пласт: слой такого размера сцена уже
            # не показывает целиком, а память съедает. Прореживание
            # честнее обрезки по числу тел: лучше показать все пласты
            # грубее, чем три из пяти подробно.
            step = _auto_step(top, budget)
            v, f = bed_to_mesh_arrays(top, bot, gt, zscale=1.0,
                                      zoffset=0.0, step=step)
            if not len(f):
                continue
            tr_r = self._xform(lyr)
            if tr_r is not None:
                v = v.copy()
                v[:, 0], v[:, 1] = self._xform_xy(tr_r, v[:, 0], v[:, 1])
            col = PALETTE[pi % len(PALETTE)]
            if o.get("solid"):
                qc = o["solid"].lstrip("#")
                col = tuple(int(qc[i:i + 2], 16) / 255.0
                            for i in (0, 2, 4)) + (1.0,)
            out.append((v, f, col, b_top, step))
        return out

    def _shells_to_layer(self):
        """Оболочки выбранного слоя в слой проекта.

        Выгружается то, что настроено и видно: уровни, крышка на краю,
        сглаживание и отброс мелочи берутся из свойств слоя. Набирать
        их заново в инструменте человек не обязан.

        Отметки настоящие: вертикальное преувеличение это способ
        смотреть, а не свойство модели. Объект на уровень, как в 2.04
        объект на интервал.
        """
        from qgis.PyQt.QtCore import QVariant
        from .algorithms import _field
        from qgis.core import (QgsVectorLayer, QgsFeature, QgsFields,
                               QgsGeometry, QgsProject)
        it = self.layer_list.currentItem()
        lid = it.data(_USER_ROLE) if it is not None else None
        lyr = (QgsProject.instance().mapLayer(lid)
               if lid and lid != _SCENE_KEY else None)
        if lyr is None:
            self.info.setText(tr(
                "Выберите в списке слой: куб в режиме изоповерхности "
                "либо грид пласта в режиме тела."))
            return
        o = self._opts.get(lid) or self._default_opts(lyr)
        mode = o.get("mode")
        bed_mode = (mode == "body" or
                    (mode == "auto" and is_bed_grid(lyr.source())))
        thin = 1
        if mode == "iso":
            got = self._iso_mesh(lyr, o, None)
        elif bed_mode:
            beds = self._bed_meshes(lyr, o)
            thin = max([m[4] for m in beds] or [1])
            got = [(v, f, col, None, float(band))
                   for v, f, col, band, _st in beds]
        else:
            self.info.setText(
                tr("Слой не в режиме изоповерхности или тела пласта."))
            return
        if not got:
            self.info.setText(tr("Оболочек не построено."))
            return

        fields = QgsFields()
        for nm, tp in (("body", QVariant.Int),
                       ("level", QVariant.Double),
                       ("color", QVariant.String),
                       ("faces", QVariant.Int),
                       ("closed", QVariant.Int),
                       ("holes", QVariant.Int),
                       ("pinch", QVariant.Int),
                       ("volume", QVariant.Double),
                       ("zmin", QVariant.Double),
                       ("zmax", QVariant.Double)):
            fields.append(_field(nm, tp))
        crs = lyr.crs().authid() or ""
        mem = QgsVectorLayer(
            "MultiPolygonZ?crs=%s" % crs,
            tr("Оболочки: %s") % lyr.name(), "memory")
        mem.dataProvider().addAttributes(fields)
        mem.updateFields()

        # Оболочка сразу разбирается на связные тела, и объём
        # считается тут же: разбирать её потом отдельным инструментом
        # значит делать в два действия то, что нужно в одно.
        from .cleanup import (split_bodies, mesh_volume,
                              shell_defects, close_holes)
        from .cadmesh import mesh_wkb
        made, tris, n_open, total = 0, 0, 0, 0.0
        n_odd = 0
        n_sewn = 0
        for v, f, col, _a, lev in got:
            hexc = "#%02x%02x%02x" % tuple(
                int(round(255 * float(c))) for c in col[:3])
            for pv, pf, _tag in split_bodies(v, f):
                # Дыра и защип - разные вещи. У дыры есть рёбра
                # с одной гранью, и объём по ней бессмыслен. Защип это
                # касание тела самого себя: дыр нет, объём точен.
                holes, pinch = shell_defects(pv, pf)
                if holes:
                    # Мелкие дыры зашиваем: на оболочке в десятки
                    # тысяч граней остаётся пара рваных рёбер
                    # от вырожденной ячейки на стыке крышки
                    # с поверхностью. Большую прореху не трогаем.
                    pv, pf, n_fix = close_holes(pv, pf)
                    if n_fix:
                        holes, pinch = shell_defects(pv, pf)
                        n_sewn += n_fix
                closed = holes == 0
                # У незамкнутого тела объём не считаем: число вышло бы,
                # а смысла в нём нет.
                q = mesh_volume(pv, pf) if closed else None
                if closed:
                    # Объём не бывает больше собственного габарита.
                    # Это верный признак сбоя счёта, а не данных,
                    # и молчать о нём нельзя: число выглядит
                    # настоящим и уходит в отчёт.
                    box = float(np.prod(pv.max(axis=0) - pv.min(axis=0)))
                    if box > 0 and q > box * 1.001:
                        n_odd += 1
                        q = None
                        closed = False
                    else:
                        total += q
                if q is None:
                    n_open += 1
                # Геометрия собирается двоично, одним куском.
                # По объекту QGIS на треугольник это триста тысяч
                # вызовов через границу языка на одно тело.
                geom = QgsGeometry()
                geom.fromWkb(mesh_wkb(pv, pf))
                ft = QgsFeature(mem.fields())
                ft.setGeometry(geom)
                made += 1
                ft.setAttributes([made, float(lev), hexc, int(len(pf)),
                                  1 if closed else 0,
                                  int(holes), int(pinch),
                                  (float(q) if closed else None),
                                  float(pv[:, 2].min()),
                                  float(pv[:, 2].max())])
                mem.dataProvider().addFeature(ft)
                tris += len(pf)
        mem.updateExtents()
        QgsProject.instance().addMapLayer(mem)
        note = ""
        if n_sewn:
            note += tr(" Зашито мелких дыр: %d.") % n_sewn
        if n_odd:
            note += tr(" У %d тел объём вышел больше их габарита - "
                       "это сбой счёта, и он не записан.") % n_odd
        if n_open:
            note = tr(" Тел с дырами %d, объём у них не посчитан: "
                      "в поле holes число рваных рёбер, в поле pinch - "
                      "касаний тела самого себя, они объёму не мешают.")\
                % n_open
        if thin > 1:
            note += tr(" Сетка прорежена в %d раза: полная не влезает "
                       "в предел вершин сцены. Объём посчитан "
                       "по прореженной, предел меняется в свойствах "
                       "сцены.") % thin
        self.info.setText(
            tr("Тел в слой: %d, треугольников %d, объём %.0f м3.%s "
               "Слой временный, сохраните его в файл.")
            % (made, tris, total, note))

    def _export_scene(self):
        """Выгрузить показанное в файл. Формат по расширению.

        Действие одно, форматов три, и разводить их по кнопкам значит
        заставлять человека помнить, какая для чего. GLB несёт цвет
        и прозрачность и годится для просмотра, STL и OBJ - для CAD,
        где нужна замкнутая оболочка.

        Выгружается ровно то, что видно: обрезали коридором, уйдёт
        коридор. Иначе человек получит не ту модель, которую смотрел.
        """
        from qgis.PyQt.QtWidgets import QFileDialog
        if not self._export:
            self.info.setText(tr("Выгружать нечего: сцена пуста."))
            return
        fn, _f = QFileDialog.getSaveFileName(
            self, tr("Выгрузить сцену"), "isoliner_3d.glb",
            tr("glTF (*.glb);;STL (*.stl);;OBJ (*.obj)"))
        if not fn:
            return
        low = str(fn).lower()
        if low.endswith(".stl") or low.endswith(".obj"):
            self._write_cad_file(fn)
        else:
            self._write_glb_file(fn)

    def _write_cad_file(self, fn):
        """Записать сцену в STL или OBJ.

        GLB несёт цвет и прозрачность и годится для просмотра, а в CAD
        нужна замкнутая оболочка, из которой делают тело. Формат
        выбирается расширением: STL двоичный и без частей, OBJ
        текстовый и с группами.

        Отметки настоящие: преувеличение это способ смотреть,
        а не свойство модели, и в CAD ему делать нечего. Поэтому
        и вопроса о нём здесь нет.
        """
        from .cadmesh import write_cad
        # Линии и подписи короба в CAD не идут: там нужны тела,
        # а не украшение вида.
        parts = [pt for pt in self._export
                 if pt.get("faces") is not None and len(pt["faces"])
                 and not pt.get("decor")]
        try:
            size = write_cad(fn, parts)
        except Exception as e:  # nosec
            self.info.setText(tr("Выгрузка не удалась: %s") % e)
            return
        if size is None:
            self.info.setText(tr("Выгружать нечего: в сцене нет тел."))
            return
        closed = 0
        for pt in parts:
            v = np.asarray(pt["verts"], dtype=float)
            ok, _n = _closed_and_border(*weld(v, np.asarray(pt["faces"])))
            closed += 1 if ok else 0
        self.info.setText(
            tr("Выгружено тел: %d, из них замкнутых %d, файл %.1f МБ. "
               "Незамкнутое тело CAD покажет, но телом не сделает.")
            % (len(parts), closed, size / (1024.0 * 1024.0)))

    def _write_glb_file(self, fn):
        """Записать сцену в GLB.

        Спрашивается вертикальное преувеличение: настоящие высоты
        верны для расчёта, а модель как на экране нужна для показа.
        """
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
            _log(tr("Выгрузка: преувеличение %s.")
                 % (tr("применено") if keep_vex else tr("не применено")))
        try:
            from .gltf import write_glb
            import numpy as np
            parts = self._export
            if keep_vex:
                # Середина берётся одна на всю выгрузку. Масштабируя
                # каждую часть вокруг своей, растянешь только рельеф
                # внутри неё, а расстояния между частями останутся
                # прежними, и на глаз преувеличение не применится.
                # Середина считается по ТЕЛАМ. Короб и его подписи
                # лежат по краю охвата и тянут её на себя, а тела
                # разлетаются от неё: подписи это полоски, то есть
                # тоже грани, и по одному признаку граней их
                # не отличить.
                zs_all = [np.asarray(pt["verts"], dtype=float)[:, 2]
                          for pt in self._export
                          if len(pt["verts"]) and "faces" in pt
                          and not pt.get("decor")]
                zc_all = (float(np.mean(np.concatenate(zs_all)))
                          if zs_all else 0.0)
                parts = []
                for part in self._export:
                    v = np.asarray(part["verts"], dtype=float).copy()
                    v[:, 2] = (v[:, 2] - zc_all) * vex + zc_all
                    parts.append(dict(part, verts=v))
                _log(tr("Выгрузка с преувеличением %.2f, середина "
                        "по отметке %.1f.") % (vex, zc_all))
            for part in parts:
                # У короба граней нет, только линии: обращение
                # к «faces» роняло всю выгрузку целиком.
                got_f = part.get("faces")
                got_l = part.get("lines")
                n_f = 0 if got_f is None else len(got_f)
                n_l = 0 if got_l is None else len(got_l)
                _log(tr("Часть %s: вершин %d, граней %d, линий %d")
                     % (part.get("name", "?"), len(part["verts"]),
                        n_f, n_l))
            size = write_glb(fn, parts)
            # Итог показываем в окне, а не только в журнале: иначе
            # неудачу от удачи не отличить, и человек открывает
            # прежний файл, гадая, почему ничего не изменилось.
            n_box = sum(1 for pt in parts if pt.get("decor"))
            self.info.setText(
                tr("Выгружено: тел %d, короб %s, преувеличение %s, "
                   "файл %.1f МБ.")
                % (len(parts) - n_box,
                   tr("есть") if n_box else tr("нету"),
                   tr("есть") if keep_vex else tr("нету"),
                   size / (1024.0 * 1024.0)))
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
                "zlo": float(self.zlo.value()),
                "zhi": float(self.zhi.value()),
                "zs_top": self.zs_top.currentData(),
                "zs_bot": self.zs_bot.currentData(),
                "grid_planes": self.grid_planes.currentData(),
                "grid_step": float(self.grid_step.value()),
                "axes_on": bool(self.btn_axes.isChecked()),
                "mask_lyr": self.mask_lyr.currentData(),
                "mask_level": float(self.mask_level.value()),
                "fence_all": bool(self.fence_all.isChecked()),
                "light": int(self.light.value()),
                "bg_grad": bool(self.bg_grad.isChecked()),
                "smooth_edges": bool(self.smooth_edges.isChecked()),
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
            self.zlo.setValue(float(state.get("zlo", -1e7)))
            self.zhi.setValue(float(state.get("zhi", -1e7)))
            for combo, key in ((self.zs_top, "zs_top"),
                               (self.zs_bot, "zs_bot"),
                               (self.grid_planes, "grid_planes")):
                k = _find_data(combo, state.get(key))
                combo.setCurrentIndex(max(k, 0))
            self.grid_step.setValue(float(state.get("grid_step", 0.0)))
            self.btn_axes.setChecked(bool(state.get("axes_on", False)))
            im = _find_data(self.mask_lyr, state.get("mask_lyr"))
            self.mask_lyr.setCurrentIndex(max(im, 0))
            self.mask_level.setValue(
                float(state.get("mask_level", 0.5) or 0.5))
            self.fence_all.setChecked(bool(state.get("fence_all")))
            self.light.setValue(int(state.get("light", 55)))
            self.bg_grad.setChecked(bool(state.get("bg_grad", True)))
            self.smooth_edges.setChecked(
                bool(state.get("smooth_edges", True)))
            self._bg_apply()
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

    def closeEvent(self, ev):
        """Остановить вращение при закрытии окна.

        Таймер, оставшийся жить после окна, будет дёргать мёртвый
        виджет: сцены уже нет, а тик приходит.
        """
        if self._spin_timer is not None:
            self._spin_timer.stop()
        super().closeEvent(ev)

    def _spin_toggle(self):
        """Пустить или остановить вращение сцены.

        Крутится камера, сцена не пересобирается: пересборка занимает
        секунду с лишним, и анимация из пересборок вышла бы
        слайд-шоу с рывками.
        """
        from qgis.PyQt.QtCore import QTimer
        if self._spin_timer is None:
            self._spin_timer = QTimer(self)
            self._spin_timer.timeout.connect(self._spin_step)
        if self._spin_timer.isActive():
            self._spin_timer.stop()
            self.btn_spin.setChecked(False)
            return
        self.btn_spin.setChecked(True)
        self._spin_timer.start(40)

    def _spin_step(self):
        """Довернуть камеру на шаг."""
        if self.view is None:
            return
        az = float(self.view.opts.get("azimuth", 0.0)) + 1.0
        self.view.setCameraPosition(azimuth=az % 360.0)

    def _spin_capture(self):
        """Снять полный оборот кадрами PNG.

        Складывать кадры в видео модуль не берётся: для этого есть
        готовые средства, а тащить их в плагин ради одной кнопки
        незачем. Кадры нумеруются с ведущими нулями, иначе склейка
        поставит десятый между первым и вторым.
        """
        from qgis.PyQt.QtWidgets import QFileDialog
        if self.view is None:
            return
        folder = QFileDialog.getExistingDirectory(
            self, tr("Куда складывать кадры"))
        if not folder:
            return
        if self._spin_timer is not None and self._spin_timer.isActive():
            self._spin_timer.stop()
            self.btn_spin.setChecked(False)
        was = float(self.view.opts.get("azimuth", 0.0))
        step = 10
        made = 0
        for k in range(0, 360, step):
            self.view.setCameraPosition(azimuth=(was + k) % 360.0)
            self.view.repaint()
            img = self.view.grabFramebuffer()
            if img.save(os.path.join(folder, "frame_%03d.png" % made),
                        "PNG"):
                made += 1
        self.view.setCameraPosition(azimuth=was)
        self.info.setText(
            tr("Снято кадров: %d, по %d градусов. Склейте их в видео "
               "любым средством: ffmpeg, редактор, что привычнее.")
            % (made, step))

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

        # Поверхности отсечки: растры проекта. Одной отметкой этого
        # не заменить, кровля и подошва меняются по площади.
        for combo in (self.zs_top, self.zs_bot, self.mask_lyr):
            prev = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(tr("(нет)"), None)
            for lyr in proj.mapLayers().values():
                if isinstance(lyr, QgsRasterLayer):
                    combo.addItem(lyr.name(), lyr.id())
            combo.setCurrentIndex(max(_find_data(combo, prev), 0))
            combo.blockSignals(False)

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
                "zoff": 0.0, "lyr_opacity": 0,
                "psize": 0.0, "label": None,
                "shape": "circle", "msize": 20.0, "nlab": 400,
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
            self.vec_label.blockSignals(True)
            self.vec_label.clear()
            self.vec_label.addItem(tr("(нет)"), None)
            guess = -1
            for f in lyr.fields():
                self.wells_label.addItem(f.name(), f.name())
                self.vec_label.addItem(f.name(), f.name())
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
            self.vec_opacity.setValue(
                int(o.get("lyr_opacity", 0) or 0))
            self.vec_zoff.blockSignals(False)
            self.vec_psize.blockSignals(True)
            self.vec_psize.setValue(float(o.get("psize", 0.0) or 0.0))
            self.vec_psize.blockSignals(False)
            self.vec_shape.blockSignals(True)
            ish = _find_data(self.vec_shape, o.get("shape") or "circle")
            self.vec_shape.setCurrentIndex(max(ish, 0))
            self.vec_shape.blockSignals(False)
            self.vec_msize.blockSignals(True)
            self.vec_msize.setValue(float(o.get("msize", 20.0) or 20.0))
            self.vec_msize.blockSignals(False)
            self.vec_nlab.blockSignals(True)
            self.vec_nlab.setValue(int(o.get("nlab", 400) or 0))
            self.vec_nlab.blockSignals(False)
            ih = _find_data(self.vec_htop, o.get("htop", "field"))
            self.vec_htop.setCurrentIndex(max(ih, 0))
            il = _find_data(self.wells_label, o.get("wells_label"))
            self.wells_label.setCurrentIndex(
                il if il >= 0 else max(guess, 0))
            ivl = _find_data(self.vec_label, o.get("label"))
            self.vec_label.setCurrentIndex(max(ivl, 0))
            self.vec_label.blockSignals(False)
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
        self._row(self.vec_label, is_point and not wells)
        flat = (self.vec_shape.currentData() or "circle") != "circle"
        self._row(self.vec_shape, is_point and not wells)
        self._row(self.vec_msize, is_point and not wells and flat)
        self._row(self.vec_psize, is_point and not wells and not flat)
        self._row(self.vec_nlab,
                  is_point and not wells
                  and bool(self.vec_label.currentData()))
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
        if not has_z and zsrc == "geom" and self._loading_opts:
            # Подменяем источник только во время загрузки свойств
            # слоя. Вне её значения в виджетах могут относиться
            # к другому слою, и подмена записала бы чужую настройку.
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
        o["lyr_opacity"] = int(self.vec_opacity.value())
        o["psize"] = float(self.vec_psize.value())
        o["label"] = self.vec_label.currentData()
        o["shape"] = self.vec_shape.currentData() or "circle"
        o["msize"] = float(self.vec_msize.value())
        o["nlab"] = int(self.vec_nlab.value())
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

    def _style_by_ranges(self, lyr, rnd):
        """Цвета градуированного или категорийного стиля разом.

        На полумиллионе объектов запрос символа у каждого это
        полмиллиона вызовов QGIS. У градуированного стиля границы
        известны заранее: цвет находится по значению поля поиском
        по границам, одним проходом. У категорийного это таблица
        значение-цвет.

        Возвращает None, если стиль не такой: тогда работает прежний
        путь по объектам.
        """
        import numpy as np
        try:
            from qgis.core import (QgsGraduatedSymbolRenderer,
                                   QgsCategorizedSymbolRenderer,
                                   QgsFeatureRequest)
        except ImportError:  # nosec
            return None
        if not isinstance(rnd, (QgsGraduatedSymbolRenderer,
                                QgsCategorizedSymbolRenderer)):
            return None
        try:
            field = rnd.classAttribute()
        except Exception:  # nosec
            return None
        if not field or field not in [f.name() for f in lyr.fields()]:
            return None    # выражение вместо поля: считать нам нечем

        def pair(sym):
            if sym is None:
                return None
            try:
                size = float(sym.size())
            except Exception:  # nosec
                size = None
            return (sym.color().name(), size)

        req = QgsFeatureRequest()
        try:
            req.setFlags(QgsFeatureRequest.Flag.NoGeometry)
        except AttributeError:  # nosec
            req.setFlags(QgsFeatureRequest.NoGeometry)
        try:
            req.setSubsetOfAttributes([field], lyr.fields())
        except Exception:  # nosec
            pass

        out = {}
        if isinstance(rnd, QgsCategorizedSymbolRenderer):
            table = {}
            for cat in rnd.categories():
                table[cat.value()] = (pair(cat.symbol())
                                      if cat.renderState() else None)
            other = table.get("", None)
            for ft in lyr.getFeatures(req):
                out[ft.id()] = table.get(ft[field], other)
            return out

        rngs = [r for r in rnd.ranges()]
        if not rngs:
            return None
        lows = np.array([r.lowerValue() for r in rngs], dtype=float)
        ups = np.array([r.upperValue() for r in rngs], dtype=float)
        cols = [pair(r.symbol()) if r.renderState() else None
                for r in rngs]
        order = np.argsort(lows)
        lows, ups = lows[order], ups[order]
        cols = [cols[i] for i in order]
        ids, vals = [], []
        for ft in lyr.getFeatures(req):
            ids.append(ft.id())
            try:
                vals.append(float(ft[field]))
            except (TypeError, ValueError):
                vals.append(np.nan)
        if not ids:
            return out
        arr = np.asarray(vals, dtype=float)
        # Ищем по верхним границам: у QGIS интервал «больше нижней,
        # меньше или равно верхней», и значение ровно на границе идёт
        # в нижний класс. Поиск по нижним кладёт его в следующий,
        # а у блочной модели значения квантованы и ложатся на границы
        # часто - целые классы уезжают.
        idx = np.searchsorted(ups, arr, side="left")
        safe = np.clip(idx, 0, len(ups) - 1)
        ok = (idx < len(ups)) & np.isfinite(arr) & (arr >= lows[safe])
        for k, fid in enumerate(ids):
            out[fid] = cols[int(idx[k])] if ok[k] else None
        return out

    def _colors_from_field(self, lyr):
        """Цвета объектов из поля слоя, если оно есть.

        Возвращает карту fid -> (цвет, размер) либо None, если поля
        нет или ни одно значение не разобралось - тогда работает
        символика слоя.

        Объект с испорченным значением остаётся без цвета и берёт
        его по общему правилу: красить наугад нельзя, чёрное тело
        выглядит настоящим и молча врёт про пласт.
        """
        from qgis.core import QgsFeatureRequest
        names = [f.name() for f in lyr.fields()]
        want = None
        for nm in names:
            if nm.lower() == "color":
                want = nm
                break
        if want is None:
            return None
        req = QgsFeatureRequest()
        try:
            req.setFlags(QgsFeatureRequest.Flag.NoGeometry)
        except AttributeError:  # nosec
            req.setFlags(QgsFeatureRequest.NoGeometry)
        try:
            req.setSubsetOfAttributes([want], lyr.fields())
        except Exception:  # nosec
            pass
        out, good, bad = {}, 0, 0
        for ft in lyr.getFeatures(req):
            col = field_color(ft[want])
            if col is None:
                bad += 1
                continue
            out[ft.id()] = (col, None)
            good += 1
        if not good:
            return None
        _log(tr("Цвет слоя %s из поля %s: разобрано %d, "
                "не разобрано %d.") % (self._title(lyr), want, good, bad))
        return out

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
        # Цвет из поля читается раньше символики: он посчитан
        # на стороне данных, тем же справочником, что и чертёж.
        # Пересчитывать его символикой значит терять точность
        # и расходиться с планом.
        own = self._colors_from_field(lyr)
        if own is not None:
            self._layer_colors_cache[key] = own
            return own
        try:
            from qgis.core import (QgsRenderContext, QgsFeatureRequest,
                                   QgsSingleSymbolRenderer)
            rnd = lyr.renderer()
            if isinstance(rnd, QgsSingleSymbolRenderer):
                # Один символ на слой: обходить объекты незачем.
                sym = rnd.symbol()
                one = None
                if sym is not None:
                    try:
                        size = float(sym.size())
                    except Exception:  # nosec
                        size = None
                    one = (sym.color().name(), size)
                out = _OneStyle(one)
                self._layer_colors_cache[key] = out
                _log(tr("Стиль слоя %s: один символ на слой, %s.")
                     % (lyr.name(), one[0] if one else tr("пусто")))
                return out
            fast = self._style_by_ranges(lyr, rnd)
            if fast is not None:
                self._layer_colors_cache[key] = fast
                return fast
            if rnd is not None:
                rnd = rnd.clone()
                ctx = QgsRenderContext()
                rnd.startRender(ctx, lyr.fields())
                # Геометрия для цвета не нужна, а на полумиллионе
                # объектов её чтение и есть основная цена. Полей берём
                # только те, что читает сам стиль.
                req = QgsFeatureRequest()
                try:
                    req.setFlags(QgsFeatureRequest.Flag.NoGeometry)
                except AttributeError:  # nosec
                    req.setFlags(QgsFeatureRequest.NoGeometry)
                try:
                    req.setSubsetOfAttributes(rnd.usedAttributes(ctx),
                                              lyr.fields())
                except Exception:  # nosec
                    pass
                for ft in lyr.getFeatures(req):
                    sym = rnd.symbolForFeature(ft, ctx)
                    # Снятый в легенде класс отдаёт пустой символ.
                    # Записываем его как None: это не «цвет не
                    # прочитался», а «показывать не надо», и путать
                    # эти два случая нельзя.
                    if sym is None:
                        out[ft.id()] = None
                        continue
                    size = None
                    # Размер маркера задан в миллиметрах печати
                    # и в трёх измерениях сам по себе ничего
                    # не значит. Берём его отношением к обычным
                    # двум миллиметрам, а метры задаются отдельно.
                    try:
                        size = float(sym.size())
                    except Exception:  # nosec
                        size = None
                    out[ft.id()] = (sym.color().name(), size)
                rnd.stopRender(ctx)
        except Exception:  # nosec
            out = {}
        self._layer_colors_cache[key] = out
        # Диагностика: по этой строке видно, читается ли стиль
        # вообще и какие цвета из него приходят.
        shown = [v[0] for v in out.values() if v]
        hidden = sum(1 for v in out.values() if v is None)
        _log(tr("Стиль слоя %s: цветов %d, скрыто классами %d, "
                "первые %s")
             % (lyr.name(), len(shown), hidden,
                ", ".join(shown[:5]) or "нет"))
        return out

    @staticmethod
    def _style_color(by_style, ft):
        """Цвет объекта из стиля, без размера."""
        v = by_style.get(ft.id())
        return v[0] if v else None

    @staticmethod
    def _style_size(by_style, ft):
        """Размер маркера из стиля, в миллиметрах печати."""
        v = by_style.get(ft.id())
        return v[1] if v else None

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

    def _add_point_labels(self, labels, span, cap=None):
        """Подписи точек: с ореолом, с прореживанием и потолком.

        Прореживание обязательно: на слое в тысячи точек подписи
        налезают друг на друга и не читается ни одна. Потолок
        нужен потому, что каждая подпись это отдельный элемент
        сцены со своей отрисовкой.
        """
        cap = _MAX_POINT_LABELS if cap is None else int(cap)
        if not labels or cap <= 0:
            return
        gl = _import_gl()
        TextItem = _halo_text_item(gl)
        if TextItem is None:
            return
        from qgis.PyQt.QtGui import QFont
        fnt = QFont()
        fnt.setPointSize(8)
        keep = thin_labels_xy([(p[0], p[1]) for p, _t in labels],
                              min_dist=span * 0.035)
        shown = 0
        for ok, (p, txt) in zip(keep, labels):
            if not ok:
                continue
            if shown >= cap:
                break
            self._add_item(TextItem(pos=p, text=txt,
                                    color=(25, 25, 25, 255), font=fnt))
            shown += 1
        if shown < sum(1 for _ in labels):
            _log(tr("Подписей точек: %d из %d.")
                 % (shown, len(labels)))

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
                self._info_dirty(tr("Точка опроса убрана."))
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

    def _state_flag(self, key, default):
        """Настройка из сохранённого состояния до сборки окна.

        Сглаживание краёв нужно знать раньше, чем создан виджет:
        режим рисования выбирается при его создании и потом
        не меняется.
        """
        from qgis.core import QgsProject
        raw, ok = QgsProject.instance().readEntry("Isoliner3D", "state")
        if not ok or not raw:
            return default
        import json
        try:
            got = json.loads(raw)
        except ValueError:
            return default
        return bool(got.get(key, default))

    def _bg_apply(self):
        """Фон сцены: сплошной или с градиентом.

        Градиент рисуется средствами Qt под областью показа, а не
        в самой сцене: элемент сцены пришлось бы держать всегда
        обращённым к камере, а это возня без пользы.
        """
        if self.view is None:
            return
        grad = bool(self.bg_grad.isChecked()) \
            if hasattr(self, "bg_grad") else True
        if not grad:
            self.view.bg_top = None
            self.view.bg_bottom = None
            self.view.setBackgroundColor((250, 250, 248))
        else:
            # Сверху холоднее, снизу светлее: так небо и земля,
            # и модель на этом фоне читается лучше плоской заливки.
            self.view.bg_top = (0.78, 0.84, 0.92, 1.0)
            self.view.bg_bottom = (0.98, 0.98, 0.96, 1.0)
        self.view.update()

    def _shaded(self, colors, md):
        """Притемнить цвета вершин по наклону, если отмывка включена.

        Поверхность, раскрашенная шкалой, рисуется одним цветом вершин
        без света вовсе: рельеф внутри одного оттенка пропадает.
        Нормали берём у самого меша - он их уже считает для показа.
        """
        s = float(self.light.value()) / 100.0
        if s <= 0.0:
            return colors
        try:
            nrm = md.vertexNormals()
        except Exception:  # nosec
            return colors
        if nrm is None or len(nrm) != len(colors):
            return colors
        return shade_colors(colors, nrm, s)

    def _z_priority(self, lid, span_z):
        """Подъём слоя по порядку в списке, в единицах сцены.

        Меряется размахом ОТМЕТОК, не охватом в плане: доля от охвата
        на площадке в двенадцать километров даёт пять метров, и слой
        уезжает от растра, по которому построен.
        """
        return layer_lift(span_z, self._draw_rank(lid),
                          self.layer_list.count())

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
            n_vol_bad = 0
            vol_idx = lyr.fields().lookupField("volume")
            zlo = zhi = None
            feats = list(lyr.getFeatures())
            # Делим бюджет только между слоями, которые и правда
            # идут телами. Раньше в делитель попадал каждый
            # отмеченный вектор, и слой изолиний, ничего из этого
            # бюджета не тративший, забирал половину.
            # Бюджет считаем по построенному, а не по исходной
            # геометрии: в слое каждый четырёхугольник несёт свои
            # вершины, а в сцене после склейки их вдвое меньше.
            # Считая по исходным, одно тело съедало весь предел,
            # занимая на деле половину.
            budget = _layer_budget(self._body_layer_count(),
                                   self._vert_cap())
            used_verts = 0
            shown = 0
            multi = len(feats) > 1
            k = 0
            tr_ = self._xform(lyr)
            surf_z = self._zsurf_of(o)
            n_empty = n_style = n_cut = 0
            for ft in feats:
                g = ft.geometry()
                if g is None or g.isEmpty():
                    n_empty += 1
                    continue
                if self._style_hides(by_style, ft):
                    n_style += 1
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
                                self._style_color(by_style, ft),
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
                        # Меш приходит несклеенным: у каждого
                        # треугольника свои вершины, и по номерам
                        # каждое ребро выглядит краевым. Оболочка
                        # никогда не признавалась замкнутой, и крышка
                        # не строилась ни разу ни у кого. Заодно
                        # вершин становится втрое меньше.
                        if len(f):
                            v, f = weld(v, f)
                        n_vol_bad += self._volume_is_impossible(ft, v,
                                                                vol_idx)
                        if used_verts and used_verts + len(v) > budget:
                            break
                        used_verts += len(v)
                        shown += 1
                        if rings0 or lines0 or self._z_active():
                            # Крышку пробуем и у незамкнутой оболочки.
                            # Тело вокселей со слиянием граней
                            # не замкнуто по построению, и раньше срез
                            # оставался открытым: видно нутро, а тело
                            # выглядит россыпью плит. Хуже от попытки
                            # не станет: не вышло - остаётся как было.
                            closed, open_edges = _closed_and_border(v, f)
                            if not closed:
                                self._body_open += 1
                                self._body_open_edges += int(open_edges)
                            v, f = self._clip_tris(v, f)
                            # Резчик добавляет куски отдельными
                            # блоками со своими вершинами, и швы между
                            # ними снова выглядят краевыми рёбрами.
                            if len(f):
                                v, f = weld(v, f)
                            try:
                                cv, cf = self._cap_cut(v, f)
                            except Exception:  # nosec
                                cv, cf = None, []
                            if len(cf):
                                f = np.vstack([f, cf + len(v)])
                                v = np.vstack([v, cv])
                            elif not closed:
                                self._cap_open += 1
                                self._cap_border += int(open_edges)
                            if not len(f):
                                continue
                            k += 1
                            nm = (("%s #%d" % (lyr.name(), k))
                                  if multi else lyr.name())
                            out.append((v, f, nm,
                                        self._style_color(by_style, ft),
                                        lyr.id()))
                            continue
                    else:
                        v, f = _tri_cached(lyr, ft, g, flat, prof)
                else:
                    v, f = _tri_cached(lyr, ft, g, zfix, prof)
                if not len(f):
                    continue
                rings_c, lines_c = self._clip_ctx()
                if len(f) and (rings_c or lines_c
                               or self._z_active()):
                    # Пояса это открытые поверхности, крышка на срезе
                    # им не нужна: режем сами грани по контуру.
                    v, f = self._clip_tris(v, f)
                    if not len(f):
                        continue
                k += 1
                nm = ("%s #%d" % (lyr.name(), k)) if multi else lyr.name()
                out.append((v, f.astype(np.int64), nm,
                            self._style_color(by_style, ft), lyr.id()))
            if not k:
                _log(tr("Слой %s: объектов %d, тел не вышло. Пусто %d, "
                        "скрыто стилем %d, без отметок %d, плоских %d.")
                     % (self._title(lyr), len(feats), n_empty,
                        n_style, n_noz, n_flat))
            if shown < len(feats):
                self._warn(
                    tr("В слое %s объектов %d, показаны первые %d: "
                       "набрано %d вершин из %d. Предел вершин "
                       "меняется в свойствах сцены.")
                    % (self._title(lyr), len(feats), shown, used_verts,
                       budget))
            if n_flat and not n_solid:
                self._warn(tr(
                    "Слой %s: все %d объектов плоские, отметки "
                    "от %.1f до %.1f. Объёма в геометрии нет, для "
                    "ступеней возьмите показ призмой.")
                    % (self._title(lyr), n_flat, zlo or 0.0, zhi or 0.0))
            if n_noz:
                self._warn(tr("Слой %s: у %d объектов нет отметок "
                              "низа или верха.") % (self._title(lyr), n_noz))
            if n_vol_bad:
                self._warn(tr(
                    "Слой %s: у %d тел объём в поле volume больше их "
                    "собственного габарита, то есть неверен. Такие "
                    "слои выгружены сборкой до 0.74.1, где счёт объёма "
                    "терял значащие цифры в настоящих координатах. "
                    "Выгрузите оболочки заново.")
                    % (self._title(lyr), n_vol_bad))
        return out

    def _volume_is_impossible(self, ft, verts, vol_idx):
        """Проверка объёма в атрибутах: он не бывает больше габарита.

        Объём тела считался суммой объёмов тетраэдров от начала
        координат, и при шести миллионах метров по северу значащие
        цифры съедались взаимным вычитанием. Счёт исправлен в 0.74.1,
        но слои, выгруженные раньше, продолжают ходить по рукам: там
        встречается восемь миллиардов кубометров при собственном
        габарите в шесть миллионов.

        Проверка нарочно грубая и дешёвая. Габарит - верхняя граница
        объёма при любой форме тела, поэтому ложных срабатываний
        у неё нет, а пересчитывать чужой слой молча хуже, чем сказать,
        что верить его числам нельзя.
        """
        if vol_idx is None or vol_idx < 0 or not len(verts):
            return 0
        try:
            value = ft.attribute(vol_idx)
        except (KeyError, IndexError):
            return 0
        return 1 if volume_beyond_box(value, verts) else 0

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
            # Счётчики причин: пустая сцена при отмеченном слое
            # разбирается только по ним. Без них видно «линий 0»,
            # а почему - неизвестно.
            n_empty = n_style = n_zcut = n_clip = n_made = 0
            for ft in feats:
                g = ft.geometry()
                if g is None or g.isEmpty():
                    n_empty += 1
                    continue
                if self._style_hides(by_style, ft):
                    n_style += 1
                    continue
                if tr_ is not None:
                    g.transform(tr_)
                zf = self._feature_z(ft, o)
                fcol = self._style_color(by_style, ft) or "#7a5c3c"
                off = self._zoff_of(o)
                for pts in _parts_xyz(g, zf):
                    kept = [p for p in pts
                            if self._z_kept([p[2]], [p[0]], [p[1]])[0]]
                    if not kept:
                        n_zcut += 1
                        continue
                    pts = kept
                    if surf:
                        laids = self._drape(pts, surf, off)
                    elif off and zf is None:
                        laids = [[(x, y, z + off) for x, y, z in pts]]
                    else:
                        laids = [pts]
                    for laid in laids:
                        runs = list(self._clip_run(laid))
                        if not runs:
                            n_clip += 1
                        for run in runs:
                            if len(run) >= 2:
                                n_made += 1
                                out.append((run, fcol, lyr.name(),
                                            lyr.id()))
            if not n_made:
                _log(tr("Слой %s: объектов %d, линий не вышло. "
                        "Пусто %d, скрыто стилем %d, снято обрезкой "
                        "по Z %d, снято обрезкой в плане %d.")
                     % (self._title(lyr), len(feats), n_empty,
                        n_style, n_zcut, n_clip))
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
            lbl_field = o.get("label")
            for ft in lyr.getFeatures():
                g = ft.geometry()
                if g is None or g.isEmpty():
                    continue
                if self._style_hides(by_style, ft):
                    continue
                if tr_ is not None:
                    g.transform(tr_)
                fcol = self._style_color(by_style, ft) or "#b03030"
                # Ноль в параметре означает «из стиля слоя».
                # Обычный маркер QGIS это два миллиметра, от них
                # и считаем: размер в миллиметрах печати сам по себе
                # в сцене ничего не значит.
                psz = float(o.get("psize", 0.0) or 0.0)
                if psz <= 0:
                    mm = self._style_size(by_style, ft)
                    psz = 7.0 * (float(mm) / 2.0) if mm else 7.0
                psz = max(min(psz, 60.0), 1.0)
                txt = ""
                if lbl_field:
                    try:
                        val = ft[lbl_field]
                    except (KeyError, IndexError):
                        val = None
                    txt = "" if val is None else str(val).strip()
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
                        # Отбор идёт разом в конце: на каждую точку
                        # шли два вызова, и каждый строил массивы ради
                        # одного числа. На ста девяноста тысячах точек
                        # это давало пятьдесят пять секунд из шестидесяти.
                        for x, y, zz in laid:
                            out.append((x, y, zz, fcol, lyr.id(),
                                        psz, txt))
        if not out:
            return out
        import numpy as np
        xs = np.fromiter((p[0] for p in out), dtype=float, count=len(out))
        ys = np.fromiter((p[1] for p in out), dtype=float, count=len(out))
        zs = np.fromiter((p[2] for p in out), dtype=float, count=len(out))
        keep = self._points_kept(xs, ys) & self._z_kept(zs, xs, ys)
        if keep.all():
            return out
        return [p for p, ok in zip(out, keep) if ok]

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
                    aband=1, iso_level=0.0, lyr_opacity=0,
                    iso_shells=[], iso_cap=False, iso_smooth=0,
                    iso_min_faces=0, wall_step=0.0, fog_density=0.6,
                    vox_classes=8, vox_merge=True)

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

    def _info_dirty(self, text):
        """Сообщение в строку состояния с подсказкой об обновлении.

        Правка обрезки помечает сцену устаревшей и сама пишет,
        что нажать. Следом сообщение о готовой линии затирало эту
        строку, и обрезка выглядела нерабочей: линия готова,
        а в сцене ничего не изменилось.
        """
        if getattr(self, "_dirty", False):
            text = text + " " + tr("Нажмите «Обновить сцену».")
        self.info.setText(text)

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
            self._sync_mode_rows()
            items = _band_items(lyr.source()) or [(1, "1")]
            self._fill_band_combo(self.zband, items, o["zband"])
            self.iso_level.setValue(float(o.get("iso_level", 0.0)))
            self.vox_classes.setValue(
                int(o.get("vox_classes", 8) or 8))
            self.lyr_opacity.setValue(
                int(o.get("lyr_opacity", 0) or 0))
            self._iso_fill(o.get("iso_shells") or [])
            self.iso_cap.setChecked(bool(o.get("iso_cap", False)))
            self.iso_smooth.setValue(int(o.get("iso_smooth", 0) or 0))
            self.iso_min_faces.setValue(
                int(o.get("iso_min_faces", 0) or 0))
            self.wall_step.setValue(
                float(o.get("wall_step", 0.0) or 0.0))
            self.fog_density.setValue(
                float(o.get("fog_density", 0.6) or 0.0))
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
            lyr_opacity=int(self.lyr_opacity.value()),
            iso_shells=self._iso_rows(),
            iso_cap=bool(self.iso_cap.isChecked()),
            iso_smooth=int(self.iso_smooth.value()),
            iso_min_faces=int(self.iso_min_faces.value()),
            wall_step=float(self.wall_step.value()),
            fog_density=float(self.fog_density.value()),
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
        # Отбор по отметке идёт вместе с плановым: треугольник,
        # у которого хоть одна вершина вне диапазона, целиком
        # выбрасывается. Резать его по горизонтали было бы точнее,
        # но грани тут мельче шага уровней, и разница не видна.
        inside_v = (self._points_kept(v[:, 0], v[:, 1])
                    & self._z_kept(v[:, 2], v[:, 0], v[:, 1]))
        tri_in = inside_v[f]
        n_in = tri_in.sum(axis=1)
        keep_all = n_in == 3
        # Отвесная грань в плане вырождается в отрезок нулевой
        # площади: пересечение с контуром даёт пусто, и такие грани
        # пропадали целиком. У вокселей это все стенки ячеек,
        # и от тела оставался один низ. Их решаем по вершинам:
        # оставляем, если хоть одна внутри. Перелёт не больше
        # размера ячейки, потеря стенок была куда заметнее.
        tv = v[f]
        _plan_area = 0.5 * np.abs(
            (tv[:, 1, 0] - tv[:, 0, 0]) * (tv[:, 2, 1] - tv[:, 0, 1])
            - (tv[:, 2, 0] - tv[:, 0, 0]) * (tv[:, 1, 1] - tv[:, 0, 1]))
        flat_tri = _plan_area < 1e-9
        # Отвесную грань раньше оставляли целиком, если хоть одна
        # вершина внутри. Она торчала за контур, соседняя
        # горизонтальная была обрезана по нему, и между ними
        # оставалась щель: это и были дырки. Теперь режем её точно,
        # вдоль отрезка, в который она вырождается в плане.
        wall_cut = flat_tri & (n_in > 0) & (n_in < 3)
        keep_all = keep_all | (flat_tri & (n_in == 3))
        if cg is None:
            # Резать нечем: оставляем стенку целиком, это лучше,
            # чем потерять её вовсе.
            keep_all = keep_all | wall_cut
            wall_cut = np.zeros(len(f), dtype=bool)
        # Счётчики для отчёта: по картинке не понять, кто срезал.
        self._clip_seen += int(len(f))
        self._clip_kept += int(keep_all.sum())
        mixed = (n_in > 0) & (n_in < 3) & ~flat_tri
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
        if cg is not None and wall_cut.any():
            from qgis.core import QgsGeometry, QgsPointXY
            for idx in np.nonzero(wall_cut)[0]:
                tri = v[f[idx]]
                p0 = tri[:, :2]
                d = p0[[1, 2, 0]] - p0
                k = int(np.argmax((d ** 2).sum(axis=1)))
                a, b = p0[k], p0[k] + d[k]
                ln = QgsGeometry.fromPolylineXY(
                    [QgsPointXY(float(a[0]), float(a[1])),
                     QgsPointXY(float(b[0]), float(b[1]))])
                try:
                    got = ln.difference(cg) if side == "out" \
                        else ln.intersection(cg)
                except Exception:  # nosec
                    continue
                if got is None or got.isEmpty():
                    continue
                spans = []
                dirv = b - a
                den = float((dirv ** 2).sum()) or 1.0
                for part in got.asGeometryCollection() or [got]:
                    try:
                        pts = part.asPolyline()
                    except Exception:  # nosec
                        pts = []
                    if len(pts) < 2:
                        continue
                    ts = [float(((np.array([q.x(), q.y()]) - a)
                                 * dirv).sum() / den) for q in pts]
                    spans.append((max(min(ts), 0.0), min(max(ts), 1.0)))
                if not spans:
                    continue
                cv, cf = clip_wall(tri, spans)
                if not len(cf):
                    continue
                out_v.append(cv)
                out_f.append(np.asarray(cf, dtype=np.int64) + base)
                base += len(cv)
        faces = np.vstack(out_f) if out_f else np.zeros((0, 3),
                                                        dtype=np.int64)
        return np.vstack(out_v), faces.astype(np.int64)

    def _clip_boundary(self, cg):
        """Граница области обрезки как линия.

        Штатный вызов границы у полигона возвращает пусто в некоторых
        сборках QGIS, и тогда крышку строить не на чем, а грани
        поперёк границы выбрасываются целиком: отсюда дырки. Поэтому
        границу собираем сами из колец, а штатный вызов только
        пробуем первым.
        """
        from qgis.core import QgsGeometry, QgsPointXY
        try:
            got = cg.boundary()
            if got is not None and not got.isEmpty():
                return got
        except Exception:  # nosec
            pass
        rings = []
        try:
            if cg.isMultipart():
                for poly in cg.asMultiPolygon():
                    rings.extend(poly)
            else:
                rings.extend(cg.asPolygon())
        except Exception:  # nosec
            rings = []
        parts = []
        for ring in rings:
            if len(ring) < 2:
                continue
            pts = [QgsPointXY(p.x(), p.y()) for p in ring]
            if pts[0] != pts[-1]:
                pts.append(pts[0])
            parts.append(QgsGeometry.fromPolylineXY(pts))
        if not parts:
            return None
        out = parts[0]
        for g2 in parts[1:]:
            out = out.combine(g2)
        return out

    def _export_box(self, lo, hi, _segs):
        """Короб в выгрузку линиями.

        Подписи в GLB не уходят: там текст это геометрия букв, и ради
        чисел её делать незачем. Рёбра, сетка и штрихи масштаб дают
        и без подписей.
        """
        import numpy as np
        from .axes import box_edges, tick_marks, grid_lines
        pieces = list(box_edges(lo, hi))
        pieces += [(a, b) for _ax, _v, a, b in tick_marks(lo, hi,
                                                          want=5)]
        planes = tuple(p for p in
                       (self.grid_planes.currentData() or "").split(",")
                       if p)
        if planes:
            pieces += grid_lines(lo, hi,
                                 float(self.grid_step.value()), planes)
        # Подписи делений: в GLB текста не бывает, поэтому цифры
        # рисуются отрезками, как на чертеже. Плоская картинка при
        # повороте встаёт ребром и пропадает, а эти поворачиваются
        # вместе с коробом.
        from .glyphs import label_3d, label_size, ribbon
        from .axes import tick_label
        # Подписи полосками, а не линиями: толщину линий в glTF задать
        # нельзя, её выбирает просмотрщик, и обычно это один пиксель,
        # который на большой модели теряется.
        lab_v, lab_f = [], []
        base = 0
        for axis, val, a, b in tick_marks(lo, hi, want=5):
            txt = tick_label(val)
            gsz = label_size(lo, hi, axis)
            # Подпись отодвигается от штриха и не налезает на короб:
            # по плану уходит наружу, по вертикали влево от штриха.
            wide = gsz * 0.8 * len(txt)
            if axis == 2:
                at = (b[0] - wide - gsz * 0.4, b[1], b[2] - gsz * 0.5)
                plane = "xz"
            else:
                at = (b[0] - wide * 0.5, b[1] - gsz * 1.4, b[2])
                plane = "xy"
            segs = label_3d(txt, at, gsz, plane=plane)
            rv, rf = ribbon(segs, gsz * 0.14, plane=plane)
            if len(rf):
                lab_v.append(rv)
                lab_f.append(rf + base)
                base += len(rv)
        if lab_f:
            lv = np.vstack(lab_v)
            self._export.append({
                "name": tr("Подписи короба"), "decor": True,
                "verts": lv,
                "faces": np.vstack(lab_f),
                "colors": np.tile(np.array([0.20, 0.22, 0.30, 1.0]),
                                  (len(lv), 1))})
            _log(tr("В выгрузку: подписи, знаков %d.") % len(lab_f))
        if not pieces:
            return
        v = np.array([q for seg in pieces for q in seg], dtype=float)
        idx = np.arange(len(v), dtype=np.int64).reshape(-1, 2)
        self._export.append({"name": tr("Координатный короб"),
                             "decor": True,
                             "verts": v, "lines": idx,
                             "colors": np.tile(
                                 np.array([0.35, 0.38, 0.45, 1.0]),
                                 (len(v), 1))})
        _log(tr("В выгрузку: короб, линий %d, с подписями.")
             % len(idx))

    def _add_axes_box(self, gl, lo, hi, cx, cy, cz, vex):
        """Координатный короб: рёбра, штрихи и подписи.

        Сцена без делений не даёт размера: тело выглядит одинаково
        и на сто метров, и на двадцать километров. По вертикали
        подписываются отметки, что для разреза важнее всего.

        Подписи ставятся у штрихов и только на ближней к началу
        стороне: по всем рёбрам сразу их было бы вчетверо больше,
        и они забили бы сцену.
        """
        import numpy as np
        from .axes import (box_edges, tick_marks, tick_label,
                           north_arrow, grid_lines)

        def put(p):
            return (float(p[0]) - cx, float(p[1]) - cy,
                    (float(p[2]) - cz) * vex)

        segs = [(put(a), put(b)) for a, b in box_edges(lo, hi)]
        if not segs:
            return
        # Короб идёт и в выгрузку: без него в файле нет масштаба.
        # Настоящие отметки, как и у прочих частей: преувеличение
        # накладывается на выгрузке целиком.
        self._export_box(lo, hi, segs)
        pos = np.array([q for seg in segs for q in seg], dtype=float)
        item = gl.GLLinePlotItem(pos=pos, mode='lines', width=1.0,
                                 antialias=True,
                                 color=(0.35, 0.38, 0.45, 0.65),
                                 glOptions='translucent')
        self._add_item(item)

        # Сетка на выбранных плоскостях: пол даёт масштаб в плане,
        # стены по отметкам, что для разреза важнее.
        planes = tuple(p for p in
                       (self.grid_planes.currentData() or "").split(",")
                       if p)
        if planes:
            gsegs = grid_lines(lo, hi, float(self.grid_step.value()),
                               planes)
            if gsegs:
                gp = np.array([q for seg in gsegs
                               for q in (put(seg[0]), put(seg[1]))],
                              dtype=float)
                self._add_item(gl.GLLinePlotItem(
                    pos=gp, mode='lines', width=1.0, antialias=True,
                    color=(0.45, 0.48, 0.55, 0.35),
                    glOptions='translucent'))
                _log(tr("Сетка: линий %d.") % len(gsegs))

        marks = tick_marks(lo, hi, want=5)
        if not marks:
            return
        tp = np.array([q for _a, _v, s0, s1 in marks
                       for q in (put(s0), put(s1))], dtype=float)
        self._add_item(gl.GLLinePlotItem(
            pos=tp, mode='lines', width=1.4, antialias=True,
            color=(0.25, 0.28, 0.36, 0.9), glOptions='translucent'))
        # Стрелка севера: на повёрнутой сцене стороны света теряются
        # мгновенно, а по одной подписи их не восстановить.
        arrow = north_arrow(lo, hi)
        ap = np.array([q for seg in arrow for q in (put(seg[0]),
                                                    put(seg[1]))],
                      dtype=float)
        self._add_item(gl.GLLinePlotItem(
            pos=ap, mode='lines', width=2.0, antialias=True,
            color=(0.20, 0.24, 0.38, 0.95), glOptions='translucent'))

        TextItem = _halo_text_item(gl)
        if TextItem is None:
            return
        from qgis.PyQt.QtGui import QFont
        fnt = QFont()
        fnt.setPointSize(8)
        self._add_item(TextItem(pos=put(arrow[0][1]), text=tr("С"),
                                color=(30, 30, 30, 255), font=fnt))
        cap = 60
        for n, (_axis, val, _s0, s1) in enumerate(marks):
            if n >= cap:
                _log(tr("Подписей осей больше %d, остальные "
                        "не ставим: они забили бы сцену.") % cap)
                break
            self._add_item(TextItem(pos=put(s1), text=tick_label(val),
                                    color=(30, 30, 30, 255), font=fnt))

    def _cap_cut(self, v, f):
        """Крышка на срезе оболочки.

        После резки в оболочке остаётся отверстие, и сквозь него видна
        изнанка. Край отверстия это рёбра, лежащие на контуре обрезки.

        Кольца по ним не обходятся: у слитых граней стыки Т-образные,
        длинный прямоугольник упирается в два коротких, общего конца
        у рёбер нет, и кольцо не замыкается. Вместо обхода рёбра
        переводятся в плоскость «путь вдоль контура - отметка», где
        срез плоский, сшиваются по узлам и собираются в полигоны.
        Порядок обхода такому способу не нужен вовсе.
        """
        import collections
        import numpy as np
        empty = (np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64))
        self._cap_calls += 1
        if len(f):
            self._cap_with_faces += 1
        cg = self._clip_geom()
        if cg is None:
            self._cap_why["область обрезки не построилась"] = \
                self._cap_why.get(
                    "область обрезки не построилась", 0) + 1
            return empty
        if not len(f):
            self._cap_why["после резки граней не осталось"] = \
                self._cap_why.get(
                    "после резки граней не осталось", 0) + 1
            return empty
        line = self._clip_boundary(cg)
        if line is None or line.isEmpty():
            self._cap_why["у области обрезки нет границы"] = \
                self._cap_why.get(
                    "у области обрезки нет границы", 0) + 1
            return empty

        # ребро, принадлежащее одной грани, это край отверстия
        edges = collections.Counter()
        for tri in f:
            for a, b in ((tri[0], tri[1]), (tri[1], tri[2]),
                         (tri[2], tri[0])):
                edges[(a, b) if a < b else (b, a)] += 1
        border = [e for e, n in edges.items() if n == 1]
        if not border:
            self._cap_why["краевых рёбер нет: срез не состоялся"] = \
                self._cap_why.get(
                    "краевых рёбер нет: срез не состоялся",
                    0) + 1
            return empty

        from qgis.core import QgsGeometry, QgsPointXY
        tol = max(cg.boundingBox().width(),
                  cg.boundingBox().height()) * 1e-4 + 1e-6
        spos = {}

        def on_cut(i):
            if i in spos:
                return True
            p = QgsGeometry.fromPointXY(
                QgsPointXY(float(v[i, 0]), float(v[i, 1])))
            if line.distance(p) > tol:
                return False
            try:
                spos[i] = float(line.lineLocatePoint(p))
            except Exception:  # nosec
                return False
            return True

        # Проверка «лежит ли вершина на контуре» идёт геометрией QGIS
        # и стоит дорого: у незамкнутой оболочки краевых рёбер тысячи,
        # и на теле вокселей это десятки секунд. Сначала грубый отсев
        # по охвату контура, геометрия только для переживших.
        bb = cg.boundingBox()
        x0, x1 = bb.xMinimum() - tol, bb.xMaximum() + tol
        y0, y1 = bb.yMinimum() - tol, bb.yMaximum() + tol

        def near_box(i):
            return (x0 <= float(v[i, 0]) <= x1
                    and y0 <= float(v[i, 1]) <= y1)

        self._cap_edges_seen += len(border)
        segs, pairs = [], []
        for a, b in border:
            if not (near_box(a) and near_box(b)):
                continue
            if not (on_cut(a) and on_cut(b)):
                continue
            pa = QgsPointXY(spos[a], float(v[a, 2]))
            pb = QgsPointXY(spos[b], float(v[b, 2]))
            if abs(pa.x() - pb.x()) < 1e-12 and \
                    abs(pa.y() - pb.y()) < 1e-12:
                continue
            segs.append(QgsGeometry.fromPolylineXY([pa, pb]))
            pairs.append(((pa.x(), pa.y()), (pb.x(), pb.y())))
        if not segs:
            return empty

        # Сначала обход колец: у замкнутой оболочки срез даёт замкнутые
        # кольца, и обход точен. Полигонизация нужна там, где кольцо
        # рвётся Т-образным стыком, и она посредник: сшивает сеть
        # и решает за нас, где площадь. Пробуем точное, потом её.
        polys = None
        rings = walk_rings(pairs)
        if rings:
            try:
                parts = [QgsGeometry.fromPolygonXY(
                    [[QgsPointXY(x, y) for x, y in r]]) for r in rings]
                polys = parts[0]
                for g2 in parts[1:]:
                    polys = polys.combine(g2)
            except Exception:  # nosec
                polys = None
        if polys is None or polys.isEmpty():
            try:
                noded = QgsGeometry.unaryUnion(segs)
                polys = QgsGeometry.polygonize([noded])
            except Exception:  # nosec
                polys = None
        if polys is None or polys.isEmpty():
            self._cap_why["кольца среза не собрались"] = \
                self._cap_why.get(
                    "кольца среза не собрались", 0) + 1
            return empty

        self._cap_segs += len(segs)
        parts = polys.asGeometryCollection()
        self._cap_polys += len(parts)
        out_v, out_f, base = [], [], 0
        for part in parts:
            if part is None or part.isEmpty():
                continue
            cv, cf = _tessellate(part, 0.0)
            if not len(cf):
                self._cap_bad += 1
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
            return empty
        return np.vstack(out_v), np.vstack(out_f)

    def _clip_report(self, prof=None):
        """Сказать в журнал, сколько срезала обрезка и чем именно.

        Когда от сцены остаётся горстка треугольников, по картинке
        не понять, кто их срезал: контур, коридор, сторона от линии
        или диапазон отметок. Одно число без другого тоже ничего
        не говорит, поэтому в отчёте и что было, и что осталось.
        """
        if not self._clip_seen:
            return
        key = self.clip_combo.currentData()
        src = self.clip_combo.currentText()
        side = self.clip_side.currentText()
        lo, hi = self._z_bounds()
        zpart = ""
        if lo is not None or hi is not None:
            zpart = tr(" Отметка: %s .. %s.") % (
                "%.1f" % lo if lo is not None else tr("без границы"),
                "%.1f" % hi if hi is not None else tr("без границы"))
        dpart = ""
        if self._clip_dmax > 0:
            dpart = tr(" До линии: от %.0f до %.0f м.") % (
                self._clip_dmin, self._clip_dmax)
            if self._clip_dmin > float(self.clip_width.value()):
                dpart += tr(" Линия проведена мимо данных: "
                            "ближайшая грань дальше полуширины.")
        if self._body_open:
            _log(tr("Тело не замкнуто до резки: тел %d, краевых рёбер "
                    "%d. Крышку на срезе такому телу не построить: "
                    "кольцо не замыкается. Пересоберите тело в 2.04 "
                    "этой версией со снятым слиянием соседних граней.")
                 % (self._body_open, self._body_open_edges))
        if self._cap_calls:
            _log(tr("Крышка: вызовов %d, из них с гранями %d.")
                 % (self._cap_calls, self._cap_with_faces))
        _log(tr("Крышка: краевых рёбер %d, на контуре среза %d, "
                "полигонов собрано %d, не разбилось %d.%s")
             % (self._cap_edges_seen, self._cap_segs,
                self._cap_polys, self._cap_bad,
                (tr(" Ранний выход: %s.") % "; ".join(
                    "%s - %d" % (tr(k), n)
                    for k, n in sorted(self._cap_why.items())))
                if self._cap_why else ""))
        if self._cap_open:
            _log(tr("Срез остался открытым у тел: %d, краевых рёбер "
                    "до резки %d. Оболочка разорвана ещё до резки, "
                    "и крышку не построить никаким способом: кольцо "
                    "среза не замыкается. Соберите тело в 2.04 "
                    "со снятым слиянием соседних граней - тогда "
                    "оболочка замкнута и срез закрывается.")
                 % (self._cap_open, self._cap_border))
        _log(tr("Обрезка: осталось %d граней из %d. Источник: %s, "
                "режим: %s, полуширина %.0f.%s%s")
             % (self._clip_kept, self._clip_seen,
                src if key else tr("нет"), side,
                float(self.clip_width.value()), zpart, dpart))

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
        if geom is not None:
            # Негодная по геометрии область режет как попало:
            # пересечение с ней даёт пусто, грани поперёк границы
            # выбрасываются целиком, и в теле появляются дырки.
            try:
                if not geom.isGeosValid():
                    fixed = geom.makeValid()
                    if fixed is not None and not fixed.isEmpty():
                        _log(tr("Область обрезки была негодной "
                                "по геометрии и исправлена."))
                        geom = fixed
            except Exception:  # nosec
                pass
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
        # Местные системы координат пересчитывать нельзя. У раскопа
        # или карьера своя сетка без привязки к земле, и QGIS всё
        # равно поведёт пересчёт через WGS 84: координаты в полтора
        # миллиона превращаются в минус миллион, и модель уезжает
        # неизвестно куда.
        for crs in (src, dst):
            aid = ""
            try:
                aid = crs.authid() or ""
            except Exception:  # nosec
                aid = ""
            if not aid or aid.startswith("USER:"):
                self._warn(tr(
                    "Система координат местная (%s), пересчёт "
                    "не делается: у неё нет привязки к земле. "
                    "Задайте слою и проекту одну систему, если "
                    "они в разных.") % (aid or tr("не задана")))
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
            rings, lines = self._clip_now
            side = self.clip_side.currentData()
            # Коридор нужен по линии. Выбрав полигональный слой
            # и оставив коридор, не режешь ничего - и молча: человек
            # видит несрезанную сцену и ищет причину в данных.
            if side == "corridor" and rings and not lines:
                self._warn(tr(
                    "Коридор строится по линии, а выбран слой "
                    "с полигонами. Поставьте «Что оставить» "
                    "на внутренность или наружное, либо выберите "
                    "линейный слой."))
            elif side != "corridor" and lines and not rings:
                self._warn(tr(
                    "Выбран линейный слой: у линии нет внутренности. "
                    "Поставьте «Что оставить» на коридор вдоль "
                    "линии."))
        return self._clip_now

    def _z_active(self):
        """Задан ли отбор по отметке.

        Резка граней вызывалась только когда задан контур или
        коридор, и диапазон отметок без них не срабатывал вовсе: тело
        оставалось целым, а человек видел, что верхняя и нижняя
        плоскости не режут.

        Заодно называем перепутанные границы: z≥ и z≤ навстречу друг
        другу невыполнимы, и сцена выходит пустой. Молчать об этом
        значит отправить человека искать причину в данных.
        """
        if self.zs_top.currentData() or self.zs_bot.currentData():
            return True
        lo, hi = self._z_bounds()
        if lo is not None and hi is not None and lo > hi:
            self._warn(tr("Границы отметок перепутаны: z\u2265 %.1f "
                          "и z\u2264 %.1f навстречу друг другу. "
                          "Сцена выйдет пустой.") % (lo, hi))
        return lo is not None or hi is not None

    def _z_clear(self, quiet=False):
        """Снять обрезку по отметке.

        «Без границы» это минимум диапазона, минус десять миллионов.
        Спустить туда со ста метров можно было только набрав это число
        руками, то есть снять обрезку было нечем.
        """
        changed = False
        for w in (self.zlo, self.zhi):
            if float(w.value()) > -1e7 + 1:
                w.setValue(-1e7)
                changed = True
        if changed and not quiet:
            self._info_dirty(tr("Обрезка по отметке снята."))
        return changed

    def _z_bounds(self):
        """Границы обрезки по отметке, None означает «без границы»."""
        lo = float(self.zlo.value())
        hi = float(self.zhi.value())
        return (None if lo <= -1e7 + 1 else lo,
                None if hi <= -1e7 + 1 else hi)

    def _z_surfaces(self):
        """Поверхности отсечки: (массив, геопривязка) сверху и снизу.

        Читаются раз на сборку сцены: растр открывается дорого,
        а нужен он на каждый слой.
        """
        if self._z_surf_now is not None:
            return self._z_surf_now
        from qgis.core import QgsProject
        out = []
        for combo in (self.zs_top, self.zs_bot):
            lid = combo.currentData()
            got = (None, None)
            if lid:
                lyr = QgsProject.instance().mapLayer(lid)
                if lyr is not None:
                    arr, gt = _read_raster(lyr.source(), 1)
                    if arr is not None:
                        got = (arr, gt)
            out.append(got)
        self._z_surf_now = tuple(out)
        return self._z_surf_now

    def _z_kept(self, zs, xs=None, ys=None):
        """Отбор вершин по отметке и по поверхностям.

        Отметка плоская, а кровля и подошва меняются по площади,
        поэтому поверхности отсекают точнее. Без координат в плане
        поверхности не применяются: отсечь по ним нечем.
        """
        import numpy as np
        from .flatten import keep_between
        zs = np.asarray(zs, dtype=float)
        lo, hi = self._z_bounds()
        keep = (z_range_mask(zs, lo, hi)
                if (lo is not None or hi is not None)
                else np.ones(zs.shape, dtype=bool))
        if xs is None or ys is None:
            return keep
        # Маска в плане: тело остаётся там, где значение не меньше
        # порога. Полигон задаёт границу линией, а маска - площадью.
        ma, mg = self._mask_array()
        if ma is not None:
            from .flatten import mask_keep
            keep = keep & mask_keep(xs, ys, ma, mg,
                                    float(self.mask_level.value()))
        (ta, tg), (ba, bg) = self._z_surfaces()
        if ta is None and ba is None:
            return keep
        return keep & keep_between(xs, ys, zs, ta, tg, ba, bg)

    def _mask_array(self):
        """Растр-маска и его геопривязка, если задан."""
        lid = self.mask_lyr.currentData()
        if not lid:
            return None, None
        got = self._mask_cache.get(lid)
        if got is not None:
            return got
        from qgis.core import QgsProject
        lyr = QgsProject.instance().mapLayer(lid)
        if lyr is None:
            return None, None
        arr, gt = _read_raster(lyr.source(), 1, None)
        if arr is None:
            self._warn(tr("Маска %s не прочиталась.") % lyr.name())
            return None, None
        self._mask_cache[lid] = (arr, gt)
        return arr, gt

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
                # Запоминаем, насколько далеко данные от линии: без
                # этого «срезало почти всё» не отличить от «линия
                # проведена мимо».
                fin = best[np.isfinite(best)]
                if len(fin):
                    self._clip_dmin = min(self._clip_dmin,
                                          float(fin.min()))
                    self._clip_dmax = max(self._clip_dmax,
                                          float(fin.max()))
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
                # X и Y здесь в координатах ПРОЕКТА (выше к ним
                # прибавлены cx и cy), а Z - в координатах СЦЕНЫ,
                # растянутая преувеличением. Смешение пространств
                # неочевидно и уже стоило одной ошибки: кто берёт
                # отсюда точку, пусть переводит только то, что нужно.
                best = (tt, L, xh, yh, zh)
        return best

    def _outside_scene(self, px, py):
        """Щелчок пришёлся за пределы площадки данных.

        Считается по лучу до горизонтального уровня середины сцены:
        точнее и не нужно, потому что вопрос грубый - целились
        в модель или мимо неё. Запас в четверть охвата оставлен
        нарочно: у края коробки промах по телу дело обычное,
        и сбрасывать там центр было бы неожиданно.
        """
        pk = self._pick or {}
        hit = self._hit_plane(px, py)
        if hit is None:
            return True                 # луч ушёл в небо
        _t, _L, xh, yh, _z = hit
        cx, cy = pk.get("cx", 0.0), pk.get("cy", 0.0)
        half = 0.5 * float(pk.get("span", 0.0) or 0.0)
        if half <= 0:
            return False
        edge = half * 1.25
        return abs(float(xh) - cx) > edge or abs(float(yh) - cy) > edge

    def _center_keeping_view(self, x, y, z):
        """Перенести центр вращения, не сдвинув картинку.

        Камера у вида стоит НЕ сама по себе: её место считается
        от центра, удаления и двух углов. Перенеся центр и оставив
        остальное, картинку неизбежно уводит - именно это и было
        видно.

        Здесь запоминается место камеры, переносится центр, а удаление
        и углы пересчитываются обратно так, чтобы камера осталась там
        же. Меняется только точка, вокруг которой пойдёт вращение,
        а вид - нет.
        """
        import math
        try:
            cam = self.view.cameraPosition()
            dx = float(cam.x()) - x
            dy = float(cam.y()) - y
            dz = float(cam.z()) - z
        except Exception:  # nosec - без места камеры остаётся простой путь
            self._set_center(_pg_vector(), x, y, z)
            return
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        if dist < 1e-9:
            self._set_center(_pg_vector(), x, y, z)
            return
        elev = math.degrees(math.asin(max(-1.0, min(1.0, dz / dist))))
        azim = math.degrees(math.atan2(dy, dx))
        vec = _pg_vector()
        try:
            self.view.setCameraPosition(
                pos=vec(x, y, z) if vec is not None else None,
                distance=dist, elevation=elev, azimuth=azim)
        except Exception:  # nosec
            self._set_center(vec, x, y, z)
            self.view.opts["distance"] = dist
        self._view_span = None      # кадрирование теперь не наше
        self.view.update()

    def _set_center(self, vec, x, y, z):
        """Поставить центр вращения штатным способом вида.

        Правка `opts['center']` на месте работает не везде: вид
        подменяет этот объект своим при каждом сдвиге камеры.
        Поэтому центр ставится тем же вызовом, каким его ставит сам
        pyqtgraph, а правка на месте остаётся запасным путём.
        """
        try:
            if vec is not None:
                self.view.setCameraPosition(pos=vec(x, y, z))
            else:
                raise AttributeError
        except Exception:  # nosec - запасной путь для старых сборок
            c = self.view.opts["center"]
            c.setX(x)
            c.setY(y)
            c.setZ(z)
        self.view.update()

    def _pivot_at(self, px, py):
        """Центр вращения по щелчку правой кнопкой.

        Сцена крутится вокруг центра охвата данных, и осмотреть
        деталь этим не выходит: она уезжает из кадра быстрее, чем
        поворачивается. Здесь центр переносится в точку, куда
        показали, - как в горных программах, откуда люди и приходят.

        Щелчок по пустому месту возвращает центр на всю сцену:
        отдельной кнопки для этого не нужно.
        """
        pk = self._pick
        if not pk:
            self.info.setText(tr("Сначала соберите сцену."))
            return
        best = self._hit_at(px, py)
        if best is None:
            # Промах промаху рознь. Щелчок ЗА пределами данных - это
            # «покажи всё», и центр сбрасывается. Щелчок внутри
            # площадки, но мимо тонкого тела, - обычный недолёт руки,
            # и центр трогать нельзя: раньше он сбрасывался и там,
            # и выглядело это как самовольный уход вида.
            if self._outside_scene(px, py):
                self._center_reset()
            else:
                self.info.setText(tr("Мимо объекта: центр не изменён. "
                                     "Щелчок за пределами площадки "
                                     "вернёт центр на всю сцену."))
            return
        _t, _L, xh, yh, zh = best
        # ВАЖНО про пространства: `_hit_at` отдаёт X и Y в координатах
        # проекта, а Z - уже в координатах сцены, растянутую
        # преувеличением. Пересчитав Z второй раз, центр улетал
        # тем дальше, чем сильнее растянута вертикаль, - вид отскакивал
        # куда попало. Отметка для показа человеку, наоборот, считается
        # обратно.
        cx, cy = pk.get("cx", 0.0), pk.get("cy", 0.0)
        cz, vex = pk.get("cz", 0.0), pk.get("vex", 1.0)
        self._center_keeping_view(float(xh) - cx, float(yh) - cy,
                                  float(zh))
        z_real = float(zh) / (vex or 1.0) + cz
        self.info.setText(tr("Центр вращения: %.1f, %.1f, отметка "
                             "%.2f м.") % (xh, yh, z_real))

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
        mk = gl.GLMeshItem(meshdata=sph, smooth=True, shader=soft_shader(),
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
        """Снять обрезку, наброски, точку опроса и границы отметок."""
        self._pick_clear(quiet=True)
        self._z_clear(quiet=True)
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
        self._info_dirty(tr("Контур замкнут: вершин %d.")
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
        self._info_dirty(tr("Линия готова: вершин %d, коридор %.0f.")
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
                # Запоминаем, были ли мы впереди: обработка событий
                # ниже даёт оконному управляющему повод переложить
                # окна, и наше уходит за главное. Возвращать его
                # без разбора нельзя - если человек нарочно ушёл
                # в другое окно, вырывать у него ввод грубо.
                self._was_active = self.isActiveWindow()
                QApplication.setOverrideCursor(cursor)
            else:
                QApplication.restoreOverrideCursor()
            QApplication.processEvents()
            if not on and getattr(self, "_was_active", False) \
                    and not self.isActiveWindow():
                self.raise_()
                self.activateWindow()
        except Exception:  # nosec
            pass

    @staticmethod
    def _is_number(txt):
        body = str(txt or "").lstrip("+-")
        return bool(body) and body.replace(".", "", 1).isdigit()

    def _sync_mode_rows(self, *_a):
        """Показать только то, что относится к выбранному режиму.

        Таблица оболочек у точечного слоя и шаг стенки у поверхности
        сбивают с толку: правишь поле, а оно ничего не делает.
        Отсечка куба нужна и изоповерхности, и вокселям, поэтому
        она в обоих списках.
        """
        rows = self._mode_rows
        if not rows or self._opt_form is None:
            return
        mode = self.mode_combo.currentData() or "auto"
        for _key, (w, modes) in rows.items():
            on = mode in modes
            w.setVisible(on)
            lab = self._opt_form.labelForField(w)
            if lab is not None:
                lab.setVisible(on)

    def _iso_rows(self):
        """Строки таблицы оболочек как список словарей."""
        rows = []
        for r in range(self.iso_table.rowCount()):
            it = self.iso_table.item(r, 0)
            txt = (it.text().strip() if it else "").replace(",", ".")
            # Разбор без исключений: сканер каталога отклоняет голый
            # continue в обработчике.
            if not self._is_number(txt):
                continue
            lev = float(txt)
            col_it = self.iso_table.item(r, 1)
            al_it = self.iso_table.item(r, 2)
            al = (al_it.text().strip() if al_it else "").replace(",", ".")
            # В таблице проценты, как и в поле прозрачности сцены:
            # доли единицы рядом с процентами читаются как ошибка.
            alpha = float(al) / 100.0 if self._is_number(al) else None
            on = True
            if it is not None:
                try:
                    on = it.checkState() != Qt.CheckState.Unchecked
                except AttributeError:  # nosec
                    on = it.checkState() != 0
            rows.append({"level": lev,
                         "color": col_it.text().strip() if col_it else "",
                         "alpha": alpha, "on": on})
        return rows

    def _iso_fill(self, rows):
        """Заполнить таблицу оболочек и оставить пустую строку внизу.

        Таблица растёт сама: заполнили последнюю строку - появилась
        следующая. Кнопки добавления не нужно.
        """
        self.iso_table.blockSignals(True)
        self.iso_table.setRowCount(0)
        for row in list(rows) + [{}]:
            self._iso_add_row(row)
        self.iso_table.blockSignals(False)

    def _iso_add_row(self, row=None):
        row = row or {}
        r = self.iso_table.rowCount()
        self.iso_table.insertRow(r)
        lev = row.get("level")
        it = QTableWidgetItem("" if lev is None else ("%g" % lev))
        try:
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked
                             if row.get("on", True)
                             else Qt.CheckState.Unchecked)
        except AttributeError:  # nosec
            pass
        self.iso_table.setItem(r, 0, it)
        self.iso_table.setItem(
            r, 1, QTableWidgetItem(str(row.get("color") or "")))
        al = row.get("alpha")
        self.iso_table.setItem(
            r, 2, QTableWidgetItem("" if al is None
                                   else ("%g" % (float(al) * 100.0))))
        col = str(row.get("color") or "")
        if col:
            self._iso_paint(r, col)

    def _iso_paint(self, r, name):
        """Закрасить ячейку цвета, чтобы он читался без кода."""
        from qgis.PyQt.QtGui import QColor, QBrush
        it = self.iso_table.item(r, 1)
        if it is None:
            return
        c = QColor(name)
        if c.isValid():
            it.setBackground(QBrush(c))

    def _iso_pick_color(self, r, _c=None):
        """Выбор цвета мышью: набирать код никто не обязан."""
        from qgis.PyQt.QtWidgets import QColorDialog
        from qgis.PyQt.QtGui import QColor
        it = self.iso_table.item(r, 1)
        cur = QColor(it.text().strip()) if it and it.text().strip() \
            else QColor("#3b7dd8")
        got = QColorDialog.getColor(cur, self, tr("Цвет оболочки"))
        if not got.isValid():
            return
        self.iso_table.blockSignals(True)
        if it is None:
            it = QTableWidgetItem("")
            self.iso_table.setItem(r, 1, it)
        it.setText(got.name())
        self._iso_paint(r, got.name())
        self.iso_table.blockSignals(False)
        self._save_opts()

    def _iso_cell_clicked(self, r, c):
        if c == 1:
            self._iso_pick_color(r)

    def _iso_menu(self, pos):
        """Правая кнопка на строке: удалить её.

        Без удаления таблица только растёт, и убрать лишний уровень
        можно лишь стерев его руками - а строка всё равно остаётся.
        """
        r = self.iso_table.rowAt(pos.y())
        if r < 0 or r >= self.iso_table.rowCount():
            return
        menu = QMenu(self)
        act = menu.addAction(tr("Удалить строку"))
        if menu.exec(self.iso_table.viewport().mapToGlobal(pos)) is act:
            self.iso_table.blockSignals(True)
            self.iso_table.removeRow(r)
            if self.iso_table.rowCount() == 0:
                self._iso_add_row()
            self.iso_table.blockSignals(False)
            self._save_opts()

    def _iso_table_edited(self, *_a):
        """Правка таблицы: дорастить пустую строку и сохранить."""
        if getattr(self, "_loading_opts", False):
            return
        last = self.iso_table.rowCount() - 1
        it = self.iso_table.item(last, 0) if last >= 0 else None
        if last < 0 or (it is not None and it.text().strip()):
            self.iso_table.blockSignals(True)
            self._iso_add_row()
            self.iso_table.blockSignals(False)
        self._save_opts()

    def _iso_mesh(self, lyr, opts, prof=None):
        """Оболочки по отсечке для слоя-куба.

        Одна оболочка берётся по заданной отсечке, несколько
        раскладываются от неё до наибольшего значения куба. Цвет
        каждой берётся из шкалы, прозрачность растёт к наружным,
        чтобы внутренние было видно сквозь них.

        Возвращает список (вершины, треугольники, цвет, прозрачность).
        """
        import numpy as np
        from .iso3d import (isosurface_levels, shell_alpha,
                            cap_faces, resolve_shells,
                            gaps_below)
        vol, gt, z0, dz = self._cube_arrays(lyr)
        if vol is None:
            return []
        if prof is not None:
            prof.add("read")
        base = float(opts.get("iso_level", 0.0))
        # Таблица оболочек: строка на уровень, пустая ячейка берёт
        # автоматическое. Пустая таблица это отсечка и одна оболочка.
        shells = resolve_shells(opts.get("iso_shells") or [], vol, base)
        levels = [sh["level"] for sh in shells]
        if len(levels) > 1:
            _log(tr("Оболочки %s: уровни %s.")
                 % (lyr.name(),
                    ", ".join("%.3g" % v for v in levels)))
        # Пропуски считаем «ниже отсечки» до построения: оболочка
        # тогда замыкается по их границе сама. Гася их после,
        # мы правили только крышку, а сама оболочка оставалась рваной.
        if opts.get("iso_cap"):
            vol = gaps_below(vol, base)
        got = isosurface_levels(vol, levels, gt, z0, dz)
        if prof is not None:
            prof.add("mesh")
        # Крышка ставится до чистки. Сглаживание двигает вершины,
        # а крышка считается по кубу, по несдвинутым координатам:
        # поставив её после, получишь разошедшийся шов и незамкнутое
        # тело.
        if opts.get("iso_cap"):
            capped, added = [], 0
            for lev, cv, cf in got:
                pv, pf = cap_faces(vol, lev, gt, z0, dz)
                if len(pf):
                    cf = np.vstack([cf, pf + len(cv)]) if len(cf) \
                        else pf
                    cv = np.vstack([cv, pv])
                    added += len(pf)
                capped.append((lev, cv, cf))
            got = capped
            if added:
                _log(tr("Крышки на краю куба: граней %d.") % added)

        # Чистка: отброс мелочи до сглаживания, иначе обрывки успевают
        # затянуть к себе соседей.
        rounds = int(opts.get("iso_smooth", 0) or 0)
        minf = int(opts.get("iso_min_faces", 0) or 0)
        if rounds or minf > 1:
            from .cleanup import drop_small, smooth, count_parts
            cleaned = []
            for lev, cv, cf in got:
                if len(cf) and minf > 1:
                    before = count_parts(cv, cf)
                    cv, cf = drop_small(cv, cf, minf)
                    after = count_parts(cv, cf)
                    if after < before:
                        _log(tr("Отброшено кусков: %d из %d.")
                             % (before - after, before))
                if len(cf) and rounds:
                    cv = smooth(cv, cf, rounds=rounds, strength=0.5)
                cleaned.append((lev, cv, cf))
            got = cleaned
            if prof is not None:
                prof.add("clean")
        out = []
        span = max(len(levels) - 1, 1)
        for k, (lev, v, f) in enumerate(got):
            if not len(f):
                continue
            col = _css_rgba(shells[k]["color"]) if k < len(shells) \
                else colormap(np.array([k / float(span)]))[0]
            # Наружная оболочка самая прозрачная: сквозь неё должны
            # читаться внутренние, ради этого всё и строится. Одна
            # оболочка сквозь себя ничего не показывает и остаётся
            # плотной.
            alpha = (shells[k]["alpha"] if k < len(shells)
                     else shell_alpha(k, len(got)))
            out.append((v, f, col, alpha, lev))
        if not out:
            self._warn(tr("Слой %s: по уровням %s ничего "
                          "не построено. Проверьте, что они лежат "
                          "внутри размаха значений куба.")
                       % (lyr.name(),
                          ", ".join("%.3g" % v for v in levels)))
        elif len(out) > 1:
            _log(tr("Оболочки %s: уровни %s, треугольников %d.")
                 % (lyr.name(),
                    ", ".join("%.2f" % r[4] for r in out),
                    sum(len(r[1]) for r in out)))
        return out

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
        marks = [(ds.GetRasterBand(b).GetDescription() or "").lower()
                 for b in range(1, ds.RasterCount + 1)]
        bed_like = any(w in nm for nm in marks
                       for w in ("кровля", "подошва", "roof", "floor"))
        if "Z0" not in meta and "z0" not in meta:
            # Каналы куба - это уровни по Z, и разметку по Z пишут все
            # инструменты куба. У грида пласта её нет и быть не может:
            # каналы там кровля и подошва, а значения - абсолютные
            # отметки. Считая их уровнями от нуля с шагом единица,
            # сцена рисовала параллелепипед у нулевой отметки, ниже
            # всех объектов, и по нему делали вывод о модели.
            if bed_like:
                self._warn(tr("Слой %s - это грид пласта: каналы кровля "
                              "и подошва, а не уровни куба. Разметки "
                              "по Z у него нет. Кубовые режимы к нему "
                              "неприменимы, для него режим «Тело "
                              "пласта».") % lyr.name())
                return None, None, 0.0, 1.0
            self._warn(tr("У слоя %s нет разметки куба по Z (Z0 и DZ). "
                          "Уровни взяты от нуля с шагом единица, и куб "
                          "встанет не на своё место по высоте.")
                       % lyr.name())
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
        # Отсечка поверхностями гасит ячейки до построения. Резать
        # построенное поздно: оболочка, воксели и объём по блочной
        # модели считались бы по разным телам и разошлись бы.
        (ta, tg), (ba, bg) = self._z_surfaces()
        if ta is not None or ba is not None:
            from .flatten import mask_cube
            before = int(np.isfinite(vol).sum())
            vol = mask_cube(vol, gt, z0, dz, ta, tg, ba, bg)
            after = int(np.isfinite(vol).sum())
            if after < before:
                _log(tr("Куб %s: отсечка поверхностями убрала ячеек "
                        "%d, осталось %d.")
                     % (lyr.name(), before - after, after))
        return vol, gt, z0, dz

    def _cube_box(self, lyr):
        """Углы куба слоя: восемь точек охвата.

        Нужны, чтобы заливка попадала в общий охват сцены. Своих
        вершин у неё нет, и без этого сцена из одной заливки
        центровалась бы по пустому множеству.
        """
        got = self._cube_arrays(lyr)
        if not got or got[0] is None:
            return None
        vol, gt, z0, dz = got
        nz, ny, nx = vol.shape
        x0, x1 = gt[0], gt[0] + nx * gt[1]
        y1, y0 = gt[3], gt[3] + ny * gt[5]
        za, zb = float(z0), float(z0) + (nz - 1) * float(dz)
        return [(x, y, z) for x in (x0, x1) for y in (y0, y1)
                for z in (za, zb)]

    def _fog_item(self, lyr, opts, cx, cy, cz, vex, prof=None):
        """Объёмная заливка куба: элемент сцены или None.

        Рендер объёма умеет одно: показать массив цвета
        с прозрачностью, глядя сквозь него. Всё остальное решает
        передаточная функция, она в отдельном модуле и проверяется
        числами.

        Заливка не заменяет оболочку, а дополняет её: оболочка
        отвечает, где граница тела, заливка - как значение меняется
        вокруг.
        """
        from .volume import rgba
        gl = _import_gl()
        Item = getattr(gl, "GLVolumeItem", None)
        if Item is None:
            self._warn(tr("В этой сборке нет объёмной заливки."))
            return None
        vol, gt, z0, dz = self._cube_arrays(lyr)
        if vol is None:
            return None
        if prof is not None:
            prof.add("read")
        level = opts.get("iso_level")
        data = rgba(vol, cutoff=(float(level) if level is not None
                                 else None),
                    density=float(opts.get("fog_density", 0.6) or 0.0))
        if data is None:
            self._warn(tr("Слой %s: заливка не построена. Куб пуст "
                          "либо крупнее предела.") % lyr.name())
            return None
        item = Item(data, smooth=True, glOptions="translucent")
        # Ставим ящик на место: элемент рисует куб от начала
        # координат с единичной ячейкой, поэтому масштаб и сдвиг
        # задаются преобразованием.
        nz, ny, nx = vol.shape
        item.scale(gt[1], gt[5], float(dz) * vex)
        item.translate((gt[0] - cx) / gt[1],
                       (gt[3] - cy) / gt[5],
                       (float(z0) - cz) * vex / (float(dz) * vex))
        if prof is not None:
            prof.add("mesh")
        _log(tr("Заливка %s: ячеек %d, плотность %.2f.")
             % (lyr.name(), nx * ny * nz,
                float(opts.get("fog_density", 0.6) or 0.0)))
        return item

    def _wall_mesh(self, lyr, opts, clip_lines, prof=None):
        """Стенка по линии: вертикальный срез куба вдоль ломаной.

        Оболочка показывает границу тела, воксели занятые ячейки,
        а стенка показывает само поле значений внутри, там где её
        провели. Линия берётся из списка обрезки: рисовать её
        отдельным способом незачем, она там уже есть.

        Возвращает (вершины, треугольники, цвета вершин).
        """
        import numpy as np
        from .slice3d import section_mesh
        empty = (np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64),
                 None)
        if not clip_lines:
            self._warn(tr("Стенке нужна линия: нарисуйте её или "
                          "выберите слой в списке обрезки."))
            return empty
        vol, gt, z0, dz = self._cube_arrays(lyr)
        if vol is None:
            return empty
        if prof is not None:
            prof.add("read")
        step = float(opts.get("wall_step", 0.0) or 0.0) or abs(gt[1])
        verts, faces, val = [], [], []
        base = 0
        for line in clip_lines:
            if len(line) < 2:
                continue
            v, f, g = section_mesh(vol, gt, z0, dz, line, step=step)
            if not len(f):
                continue
            verts.append(v)
            faces.append(f + base)
            val.append(g)
            base += len(v)
        if not faces:
            self._warn(tr("Слой %s: стенка вышла пустой, линия "
                          "за пределами куба.") % lyr.name())
            return empty
        v = np.vstack(verts)
        f = np.vstack(faces)
        g = np.concatenate(val)
        if prof is not None:
            prof.add("mesh")
        good = np.isfinite(g)
        lo = float(np.nanmin(g)) if good.any() else 0.0
        hi = float(np.nanmax(g)) if good.any() else 1.0
        rng = (hi - lo) or 1.0
        cols = colormap((g - lo) / rng)
        _log(tr("Стенка %s: узлов %d, треугольников %d, "
                "значения %.3f .. %.3f.")
             % (lyr.name(), len(v), len(f), lo, hi))
        return v, f, cols

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
        lo_z, hi_z = self._z_bounds()
        if lo_z is not None or hi_z is not None:
            zc = z0 + np.arange(vol.shape[0]) * dz
            keep_z = z_range_mask(zc, lo_z, hi_z)
            occ &= keep_z[:, None, None]
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

    def _add_item(self, item, owner=None, gopt=None):
        """Положить элемент в сцену, запомнив, чьего он слоя.

        Хозяин нужен, чтобы галка видимости прятала элемент сразу,
        без пересборки. Если элемент общий для нескольких слоёв,
        хозяин None и такой слой переключается пересборкой.

        Очередь рисования задаётся режимом прозрачности: прозрачное
        идёт после непрозрачного, иначе оно занимает глубину и
        отбрасывает то, что за ним, ещё до смешивания цветов.
        """
        if gopt is not None:
            try:
                item.setDepthValue(draw_depth(gopt))
            except AttributeError:  # nosec
                pass
        self.view.addItem(item)
        self._items.append(item)
        self._owners.append(owner)

    def _title(self, lyr):
        """Имя слоя для сообщений, с хвостом при совпадении имён.

        Отметки и настройки держатся на идентификаторе, поэтому два
        слоя с одним именем в сцене не путаются. А вот сообщения
        путаются: «Слой Границы: линий не вышло» при двух «Границах»
        разобрать нельзя. Здесь к имени добавляется хвост
        идентификатора, и только когда имя в сцене повторяется.
        """
        if lyr is None:
            return "?"
        name = lyr.name()
        proj = QgsProject.instance()
        same = 0
        for i in range(self.layer_list.count()):
            other = proj.mapLayer(self.layer_list.item(i)
                                  .data(_USER_ROLE))
            if other is not None and other.name() == name:
                same += 1
                if same > 1:
                    return "%s [%s]" % (name, lyr.id()[-6:])
        return name

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
        self._z_surf_now = None
        self._clip_seen = 0
        self._clip_kept = 0
        self._clip_dmin = float("inf")
        self._clip_dmax = 0.0
        self._cap_open = 0
        self._cap_border = 0
        self._cap_edges_seen = 0
        self._cap_segs = 0
        self._cap_polys = 0
        self._cap_bad = 0
        self._cap_why = {}
        self._cap_calls = 0
        self._cap_with_faces = 0
        self._body_open = 0
        self._body_open_edges = 0
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
        # Строка для разбора издалека: по ней видно, на каком шаге
        # обрывается цепочка. Отмечено ноль - дело в списке слоёв;
        # отмечено, а тел и линий ноль - в разборе геометрии.
        n_marked = n_vec = 0
        for i in range(self.layer_list.count()):
            it = self.layer_list.item(i)
            if it.checkState() != _CHECKED:
                continue
            n_marked += 1
            lyr_i = QgsProject.instance().mapLayer(it.data(_USER_ROLE))
            if isinstance(lyr_i, QgsVectorLayer):
                n_vec += 1
        _log(tr("Сбор сцены: отмечено %d (растров %d, векторов %d), "
                "тел %d, линий %d, точек %d.")
             % (n_marked, len(layers), n_vec, len(bodies),
                len(vlines), len(vpoints)))
        if not layers and not bodies and not vlines and not vpoints:
            if not n_marked:
                self.info.setText(tr("Отметьте слой в списке сцены."))
            else:
                # Слой отмечен, а показывать нечего: причина уже
                # найдена при разборе, и человеку нужна она, а не совет
                # отметить то, что он отметил. Так было с чертёжным
                # разрезом: у него нет отметок, он законно пропущен,
                # а окно предлагало отметить слой.
                why = " ".join(self._warnings[:2])
                self.info.setText(
                    (tr("Отмечено слоёв: %d, но показывать нечего.")
                     % n_marked) + ((" " + why) if why else
                                    tr(" Причина в журнале плагина.")))
            return
        vex = float(self.vex.value())
        spacing = float(self.spacing.value())
        meshes, skipped, fogs = [], [], []
        nbeds = 0
        n_reproj = 0
        budget = _layer_budget(len(layers), self._vert_cap())
        clip, clip_lines = self._clip_ctx()
        for k, lyr in enumerate(layers):
            o = self._opts.get(lyr.id()) or \
                self._default_opts(lyr.source())
            mode = o.get("mode", "auto")
            # Заборы задаются на всю сцену, а не слою за слоем:
            # обрезка общая, и разрез по той же линии тоже общий.
            # Кубы и воксели остаются как есть - у них своя геометрия,
            # и полотнищем её не показать.
            if mode == "iso":
                # Куб значений: каналы это уровни. Оболочка
                # по отсечке строится маршем по тетраэдрам, поэтому
                # выходит замкнутой и годится для подсчёта объёма.
                # Кладём её в общий список: центрирование, окраска
                # и выгрузка дальше работают как для поверхностей.
                # Внутренние оболочки кладём раньше наружных.
                # Глубина пишется, и нарисованная первой закрывает
                # собой то, что за ней: наружная, идя первой, съедала
                # все внутренние. Идя последней, она ложится поверх
                # них своей прозрачностью, как и задумано.
                for v_i, f_i, col_i, a_i, _lev in reversed(
                        self._iso_mesh(lyr, o, prof)):
                    if o.get("solid"):
                        col_i = _css_rgba(o["solid"])
                    else:
                        col_i = tuple(col_i)
                    # Прозрачность оболочки идёт своя, поэтому
                    # кладём её в запись слоя, а не в общую.
                    o_i = dict(o)
                    o_i["alpha"] = float(a_i) * float(
                        o.get("alpha", 1.0) or 1.0)
                    o_i["shell"] = True
                    # Оболочку режем, как тело: поверхности режутся
                    # маской по растру, а у оболочки растра нет,
                    # и без этого она оставалась целой.
                    if clip or clip_lines or self._z_active():
                        v_i, f_i = self._clip_tris(v_i, f_i)
                        if not len(f_i):
                            continue
                        try:
                            cv, cf = self._cap_cut(v_i, f_i)
                        except Exception:  # nosec
                            cv, cf = None, []
                        if len(cf):
                            f_i = np.vstack([f_i, cf + len(v_i)])
                            v_i = np.vstack([v_i, cv])
                    meshes.append((v_i, f_i, col_i, lyr.id(), False,
                                   lyr.source(), o_i, None, None, 0.0))
                continue
            if mode == "fog":
                # Заливку строим позже: ей нужен центр сцены,
                # а он известен только после обхода всех слоёв.
                box = self._cube_box(lyr)
                if box is not None:
                    fogs.append((lyr, o, box))
                continue
            if mode == "wall":
                # Стенка по линии: срез куба вдоль ломаной обрезки.
                v_w, f_w, c_w = self._wall_mesh(lyr, o, clip_lines,
                                                prof)
                if len(f_w):
                    col_w = PALETTE[len(meshes) % len(PALETTE)]
                    if o.get("solid"):
                        col_w = _css_rgba(o["solid"])
                        c_w = None
                    if c_w is not None:
                        self._vox_colors[lyr.id()] = c_w
                    meshes.append((v_w, f_w, col_w, lyr.id(), False,
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
                if as_bed and self.fence_all.isChecked() \
                        and clip_lines:
                    # Забор: вертикальный разрез сквозь ВСЮ пачку
                    # по линии обрезки. Не поверхность, натянутая
                    # на линию, а чертёж, поставленный вертикально.
                    from .slice3d import fence_mesh
                    n_band = _band_count(lyr.source())
                    pairs, gt = [], None
                    for b in bed_pairs(n_band, o.get("zband", 1)):
                        tp, gt = _read_raster(lyr.source(), b, prof)
                        bt, _g = _read_raster(lyr.source(), b + 1, prof)
                        if tp is None or bt is None:
                            continue
                        pairs.append((tp, bt))
                    prof.add("read")
                    v_f = f_f = None
                    if pairs and gt is not None:
                        for ln in clip_lines:
                            v2, f2 = fence_mesh(pairs, gt, ln)
                            if not len(f2):
                                continue
                            if v_f is None:
                                v_f, f_f = v2, f2
                            else:
                                f_f = np.vstack([f_f, f2 + len(v_f)])
                                v_f = np.vstack([v_f, v2])
                    prof.add("mesh")
                    if v_f is None:
                        self._warn(tr("Забор %s не построен: линия "
                                      "мимо данных.") % lyr.name())
                        continue
                    _log(tr("Забор %s: пластов %d, граней %d.")
                         % (lyr.name(), len(pairs), len(f_f)))
                    meshes.append((v_f, f_f,
                                   PALETTE[len(meshes) % len(PALETTE)],
                                   lyr.id(), False, lyr.source(), o,
                                   None, None, 0.0))
                    nbeds += 1
                    continue
                if as_bed:
                    prof.skip()
                    # Пар каналов бывает несколько: у грида пластов
                    # на каждый пласт своя кровля и подошва. Брав
                    # только первую пару, показываешь верхний пласт
                    # и молчишь про остальные.
                    n_band = _band_count(lyr.source())
                    pairs = [(b, b + 1)
                             for b in bed_pairs(n_band,
                                                o.get("zband", 1))]
                    verts = faces = None
                    surf_arr = None
                    for pi, (b_top, b_bot) in enumerate(pairs):
                        top, gt = _read_raster(lyr.source(), b_top,
                                               prof)
                        bot, _g = _read_raster(lyr.source(), b_bot,
                                               prof)
                        if top is None or bot is None:
                            continue
                        top = np.where(self._z_kept(top), top, np.nan)
                        bot = np.where(self._z_kept(bot), bot, np.nan)
                        if lclip:
                            top = self._clip_array(top, gt, lclip)
                            bot = self._clip_array(bot, gt, lclip)
                        if lclip_lines:
                            top = self._clip_by_lines(top, gt,
                                                      lclip_lines)
                            bot = self._clip_by_lines(bot, gt,
                                                      lclip_lines)
                        v2, f2 = bed_to_mesh_arrays(
                            top, bot, gt, zscale=1.0,
                            zoffset=-spacing * k,
                            step=_auto_step(top, budget))
                        if not len(f2):
                            continue
                        if verts is None:
                            verts, faces = v2, f2
                            surf_arr = top
                        else:
                            faces = np.vstack([faces, f2 + len(verts)])
                            verts = np.vstack([verts, v2])
                    prof.add("read")
                    if verts is None:
                        raise ValueError
                    prof.add("mesh")
                    if len(pairs) > 1:
                        _log(tr("Тело пласта %s: пар каналов %d.")
                             % (lyr.name(), len(pairs)))
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
                    # Поверхность режется по отметке своими же
                    # значениями: узел вне диапазона становится
                    # пропуском и в сетку не идёт.
                    arr = np.where(self._z_kept(arr), arr, np.nan)
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
        for row in vlines:
            vsets.append(np.asarray(row[0], dtype=float))
        if vpoints:
            # Берём первые три поля по срезу: в записи точки лежат
            # ещё цвет, слой, размер и подпись, и жёсткая распаковка
            # ломалась на каждом новом поле.
            vsets.append(np.array([tuple(p[:3]) for p in vpoints],
                                  dtype=float))
        for _l, _o, box in fogs:
            vsets.append(np.array(box, dtype=float))
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
        # Подъём слоёв меряется размахом отметок: в плане километры,
        # по высоте метры, и общая мера тут не годится.
        span_z = max(max(zs_) - min(zs_), 0.0) * float(vex)
        box_lo = (min(xs), min(ys), min(zs_))
        box_hi = (max(xs), max(ys), max(zs_))
        if self.btn_axes.isChecked():
            self._add_axes_box(gl, box_lo, box_hi, cx, cy, cz, vex)
        else:
            # Короб кладём в выгрузку и когда его не показывают:
            # в файле без него нет масштаба, а на экране он мешает.
            self._export_box(box_lo, box_hi, None)
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

        for lyr_f, o_f, _box in fogs:
            item_f = self._fog_item(lyr_f, o_f, cx, cy, cz, vex, prof)
            if item_f is not None:
                self._add_item(item_f, lyr_f.id(), 'translucent')

        alpha0 = 1.0 - float(self.opacity.value()) / 100.0
        # Тела берут прозрачность и режим отрисовки ниже, а в сцене
        # из одних тел обход поверхностей не выполняется вовсе:
        # заводим оба значения здесь.
        alpha = alpha0
        gopt = 'opaque' if alpha >= 0.999 else 'translucent'
        for k, (verts, faces, color, lid, as_bed, src, o,
                _sa, _gt, _zo) in enumerate(meshes):
            # Оболочка по отсечке несёт свою прозрачность: наружная
            # прозрачнее внутренних, иначе видно только её.
            # Прозрачность слоя поверх общей: общая правит всю сцену
            # разом, а этой приглушают один слой, чтобы видеть тело
            # под ним. Текстуру она накрывает тоже.
            own = 1.0 - float(o.get("lyr_opacity", 0) or 0) / 100.0
            alpha = alpha0 * own * float(o.get("alpha", 1.0) or 1.0)
            gopt = 'opaque' if alpha >= 0.999 else 'translucent'
            v = verts.copy()
            v[:, 0] -= cx
            v[:, 1] -= cy
            v[:, 2] = ((v[:, 2] - cz) * vex
                       + self._z_priority(lid, span_z))
            md = gl.MeshData(vertexes=v.astype('float32'), faces=faces)
            prof.count("tris", len(faces)).count("verts", len(v))
            if o.get("texture"):
                item = self._textured(gl, md, verts, v, faces,
                                      alpha, prof, o)
                if item is not None:
                    self._add_item(item, lid, gopt)
                    # В GLB текстура пока не уходит: для неё нужны
                    # координаты текстуры у каждой вершины и сама
                    # картинка внутри файла. Поверхность выгружается
                    # ровным цветом, чтобы не пропасть вовсе.
                    lyr_e = QgsProject.instance().mapLayer(lid)
                    # В выгрузку идут НАСТОЯЩИЕ координаты: сцена
                    # сдвинута к середине и растянута преувеличением,
                    # и такие вершины лягут не на место и в другом
                    # масштабе.
                    self._keep_for_export(
                        lyr_e.name() if lyr_e else "surface",
                        verts, faces,
                        np.tile(np.array(color[:3] + (alpha,)),
                                (len(verts), 1)))
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
                self._add_item(item, lid, gopt)
                lyr_e = QgsProject.instance().mapLayer(lid)
                self._keep_for_export(
                    lyr_e.name() if lyr_e else "voxels", verts, faces,
                    vox_col)
                continue
            # У оболочки свой цвет из таблицы, и раскраска по каналу
            # его перебивать не должна: человек назвал цвет,
            # решать за него нечего.
            ramp_c = None if o.get("shell") else self._style_ramp.get(lid)
            if ramp_c is not None and len(ramp_c) == len(v):
                vc = ramp_c.copy()
                vc[:, 3] = alpha
                vc = self._shaded(vc, md)
                md.setVertexColors(vc.astype('float32'))
                item = gl.GLMeshItem(meshdata=md, smooth=True,
                                     glOptions=gopt)
                exp_col = vc
            elif (attr is not None and lid in attr[0]
                    and not o.get("shell")):
                vals, vmin, vmax, rng = attr
                vc = colormap((vals[lid] - vmin) / rng)
                vc[:, 3] = alpha
                vc = self._shaded(vc, md)
                md.setVertexColors(vc.astype('float32'))
                item = gl.GLMeshItem(meshdata=md, smooth=True,
                                     glOptions=gopt)
                exp_col = vc
            else:
                item = gl.GLMeshItem(meshdata=md, smooth=True,
                                     shader=soft_shader(),
                                     color=color[:3] + (alpha,),
                                     glOptions=gopt)
                exp_col = None
            self._add_item(item, lid, gopt)
            lyr_e = QgsProject.instance().mapLayer(lid)
            # В выгрузку идёт та же раскраска, что и на экране.
            # Ровный цвет слоя вместо шкалы делает файл нечитаемым:
            # все поверхности выходят одинаковыми пятнами.
            # Прозрачность уходит в файл такой же, как на экране:
            # сцену настраивают глазом, и разглядывать выгрузку
            # человек будет так же.
            if exp_col is not None:
                out_col = np.asarray(exp_col, dtype=float).copy()
                out_col[:, 3] = alpha
            else:
                out_col = np.tile(np.array(color[:3] + (alpha,)),
                                  (len(verts), 1))
            self._keep_for_export(
                lyr_e.name() if lyr_e else "surface", verts, faces,
                out_col)
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
                # Общая прозрачность зовётся «прозрачностью
                # поверхностей» и к телам не относится: разрез
                # не должен просвечивать оттого, что просвечивает
                # поверхность над ним. У тела своя прозрачность,
                # в свойствах его слоя.
                o_b = self._opts.get(lid_b) or {}
                alpha = 1.0 - float(
                    o_b.get("lyr_opacity", 0) or 0) / 100.0
                gopt = 'opaque' if alpha >= 0.999 else 'translucent'
                # Копим и координаты сцены, и настоящие: сцена нужна
                # для показа, выгрузке нужны настоящие.
                allv, allf, allc, base = [], [], [], 0
                allmap = []
                for bi, (bverts, bfaces, bname, bcol, _bl) in group:
                    color = PALETTE[(len(meshes) + bi) % len(PALETTE)]
                    if bcol:
                        color = _css_rgba(bcol)
                    v = bverts.copy()
                    v[:, 0] -= cx
                    v[:, 1] -= cy
                    v[:, 2] = ((v[:, 2] - cz) * vex
                               + self._z_priority(lid_b, span_z))
                    allv.append(v)
                    allmap.append(np.asarray(bverts, dtype=float))
                    allf.append(np.asarray(bfaces, dtype=np.int64)
                                + base)
                    allc.append(np.tile(
                        np.array(color[:3] + (alpha,), dtype='float32'),
                        (len(v), 1)))
                    base += len(v)
                bv = np.vstack(allv).astype('float32')
                bf = np.vstack(allf)
                md = gl.MeshData(vertexes=bv, faces=bf)
                md.setVertexColors(self._shaded(np.vstack(allc), md))
                prof.count("tris", len(bf)).count("verts", len(bv))
                # Без затенения: цвет берётся из стиля слоя, и
                # затенение его умножает, уводя оранжевый в бурый.
                # Пояса плоские, светотень им ничего не добавляет,
                # а совпадение с картой важнее.
                item = gl.GLMeshItem(meshdata=md, smooth=False,
                                     shader=None, glOptions=gopt)
                self._add_item(item, lid_b, gopt)
                lyr_e = QgsProject.instance().mapLayer(lid_b)
                self._keep_for_export(
                    lyr_e.name() if lyr_e else "body",
                    np.vstack(allmap), bf, np.vstack(allc))
        self._clip_report(prof)
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
                                     shader=soft_shader(),
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
            TextItem = _halo_text_item(gl)
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
                           + self._z_priority(lid_v, span_z))
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
            pt_labels = []
            lbl_cap = _MAX_POINT_LABELS
            for lid_v in {r[4] for r in vpoints}:
                o_l = self._opts_of(
                    QgsProject.instance().mapLayer(lid_v))
                n = o_l.get("nlab")
                if n is not None:
                    lbl_cap = min(lbl_cap, int(n))
            for x, y, z, c, lid_v, psz, txt in vpoints:
                p3 = (x - cx, y - cy, (z - cz) * vex
                      + self._z_priority(lid_v, span_z))
                by_layer.setdefault(lid_v, []).append((p3, c, psz))
                if txt:
                    pt_labels.append((p3, txt))
            for lid_v, rows in by_layer.items():
                o_v = self._opts_of(
                    QgsProject.instance().mapLayer(lid_v))
                shape = o_v.get("shape") or "circle"
                cols = np.array([_css_rgba(r[1]) for r in rows],
                                dtype='float32')
                flat = flat_marker_mesh(
                    rows, shape, float(o_v.get("msize", 20.0) or 20.0))
                if flat is not None:
                    fv, ff = flat
                    per = len(fv) // max(len(rows), 1)
                    vc = np.repeat(cols, per, axis=0)
                    md = gl.MeshData(vertexes=fv.astype('float32'),
                                     faces=ff)
                    md.setVertexColors(vc)
                    item = gl.GLMeshItem(meshdata=md, smooth=False,
                                         glOptions='opaque')
                    self._add_item(item, lid_v)
                    prof.count("tris", len(ff))
                    continue
                arr = np.array([r[0] for r in rows], dtype='float32')
                sizes = np.array([r[2] for r in rows],
                                 dtype='float32')
                # Непрозрачная отрисовка обязательна: по умолчанию
                # у точек аддитивное смешение, и на светлом фоне
                # сцены они выцветают в белое, то есть пропадают.
                item = gl.GLScatterPlotItem(pos=arr, color=cols,
                                            size=sizes, pxMode=True,
                                            glOptions='opaque')
                self._add_item(item, lid_v)
                prof.count("verts", len(arr))
            self._add_point_labels(pt_labels, span, lbl_cap)

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
        # Фон ставится заново на каждой пересборке. Он живёт
        # в самом виде, а не в сцене, и его терял любой путь,
        # который вид пересоздавал: сцена собиралась, а градиент
        # пропадал, и человеку приходилось снимать и ставить флажок.
        self._bg_apply()
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
