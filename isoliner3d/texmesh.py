# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Это свободная программа: вы можете распространять её и/или изменять на
# условиях Стандартной общественной лицензии GNU (GNU GPL) версии 2 либо
# (на ваше усмотрение) любой более поздней версии. Полный текст - в LICENSE.
"""Наложение карты на поверхность грида: текстура вместо цвета по вершинам.

Штатный `GLMeshItem` из pyqtgraph текстур не умеет вовсе, поэтому здесь
свой элемент сцены. За образец взят `GLImageItem` из того же pyqtgraph: он
уже содержит всю обвязку (генерация текстуры, VBO, выбор версии GLSL
с откатом на legacy для старых драйверов), нам остаётся заменить квад
на произвольный меш и добавить затенение.

Почему текстура, а не цвет по вершинам. Цвет в вершинах привязывает
детальность картинки к плотности сетки: прореженный до 60 тысяч узлов грид
превращает ортофото в мозаику. Текстура разрывает эту связь, разрешение
изображения от сетки больше не зависит.

Затенение обязательно. Без него рельеф под картой перестаёт читаться:
пропадает светотень, по которой глаз распознаёт форму. Цвет текстуры
домножается на ламбертовский член по нормали вершины, доля затенения
задаётся параметром.

Модуль не импортирует ни QGIS, ни Qt, ни OpenGL на верхнем уровне:
чистая часть (расчёт текстурных координат) проверяется headless.
"""
import numpy as np

# доля постоянной подсветки в затенении: 0 - чёрные склоны, 1 - плоско
AMBIENT = 0.45

# потолок стороны текстуры, если у драйвера не удалось спросить свой
MAX_TEXTURE = 4096


def texcoords(verts, xmin, xmax, ymin, ymax):
    """Текстурные координаты вершин по их положению в охвате картинки.

    Развёртку строить не нужно: поверхность однозначно проецируется на
    план, поэтому координата текстуры - это просто доля от левого и от
    нижнего края охвата. Возвращает массив (N, 2) во float32.

    Ось V считается снизу вверх, как в OpenGL. Картинка при загрузке
    переворачивается, потому что у растра начало отсчёта сверху.
    """
    v = np.asarray(verts, dtype=float)
    dx = float(xmax - xmin) or 1.0
    dy = float(ymax - ymin) or 1.0
    uv = np.empty((len(v), 2), dtype=np.float32)
    uv[:, 0] = (v[:, 0] - xmin) / dx
    uv[:, 1] = (v[:, 1] - ymin) / dy
    return uv


def ribbon_texcoords(dists):
    """Текстурные координаты ленты разреза по накопленным расстояниям.

    Лента строится парами вершин: чётная - низ, нечётная - верх. Вдоль
    ленты координата U это доля пройденного пути, поперёк V равна нулю
    внизу и единице наверху. Так чертёж разреза в координатах
    «расстояние вдоль линии на отметку» ложится на своё место
    в пространстве без всякого пересчёта.

    `dists` - накопленное расстояние в вершинах линии, длиной N.
    Возвращает массив (2N, 2) во float32.
    """
    d = np.asarray(dists, dtype=float)
    total = float(d[-1]) if len(d) and d[-1] > 0 else 1.0
    u = d / total
    uv = np.empty((2 * len(d), 2), dtype=np.float32)
    uv[0::2, 0] = u
    uv[1::2, 0] = u
    uv[0::2, 1] = 0.0
    uv[1::2, 1] = 1.0
    return uv


def polyline_dists(points):
    """Накопленное расстояние по вершинам полилинии, начиная с нуля."""
    p = np.asarray(points, dtype=float)
    if len(p) < 2:
        return np.zeros(len(p), dtype=float)
    seg = np.sqrt(((p[1:] - p[:-1]) ** 2).sum(axis=1))
    return np.concatenate([[0.0], np.cumsum(seg)])


def fit_texture_size(width_m, height_m, side, cap=MAX_TEXTURE):
    """Размер картинки в пикселях под охват, с сохранением пропорций.

    `side` - желаемая сторона по длинной оси. Результат ограничен `cap`
    и не бывает меньше 64 на 64: текстура мельче бессмысленна.
    """
    side = int(max(64, min(int(side), int(cap))))
    w = float(width_m) or 1.0
    h = float(height_m) or 1.0
    if w >= h:
        return side, int(max(64, round(side * h / w)))
    return int(max(64, round(side * w / h))), side


def _gl_max_texture(GL):
    """Спросить у драйвера предельную сторону текстуры."""
    try:
        n = int(GL.glGetIntegerv(GL.GL_MAX_TEXTURE_SIZE))
        return n if n >= 64 else MAX_TEXTURE
    except Exception:
        return MAX_TEXTURE


SHADER_LEGACY_VERT = """
    uniform mat4 u_mvp;
    uniform mat3 u_normal;
    attribute vec4 a_position;
    attribute vec2 a_texcoord;
    attribute vec3 a_norm;
    varying vec2 v_texcoord;
    varying float v_shade;
    void main() {
        gl_Position = u_mvp * a_position;
        v_texcoord = a_texcoord;
        vec3 n = normalize(u_normal * a_norm);
        v_shade = abs(n.z);
    }
"""

SHADER_LEGACY_FRAG = """
    #ifdef GL_ES
    precision mediump float;
    #endif
    uniform sampler2D u_texture;
    uniform float u_ambient;
    uniform float u_alpha;
    varying vec2 v_texcoord;
    varying float v_shade;
    void main() {
        vec4 c = texture2D(u_texture, v_texcoord);
        float k = u_ambient + (1.0 - u_ambient) * v_shade;
        gl_FragColor = vec4(c.rgb * k, c.a * u_alpha);
    }
"""

SHADER_CORE_VERT = """
    uniform mat4 u_mvp;
    uniform mat3 u_normal;
    in vec4 a_position;
    in vec2 a_texcoord;
    in vec3 a_norm;
    out vec2 v_texcoord;
    out float v_shade;
    void main() {
        gl_Position = u_mvp * a_position;
        v_texcoord = a_texcoord;
        vec3 n = normalize(u_normal * a_norm);
        v_shade = abs(n.z);
    }
"""

SHADER_CORE_FRAG = """
    #ifdef GL_ES
    precision mediump float;
    #endif
    uniform sampler2D u_texture;
    uniform float u_ambient;
    uniform float u_alpha;
    in vec2 v_texcoord;
    in float v_shade;
    out vec4 fragColor;
    void main() {
        vec4 c = texture(u_texture, v_texcoord);
        float k = u_ambient + (1.0 - u_ambient) * v_shade;
        fragColor = vec4(c.rgb * k, c.a * u_alpha);
    }
"""


def make_item(gl, verts, faces, uv, normals, image,
              alpha=1.0, ambient=AMBIENT, smooth=True):
    """Собрать элемент сцены с текстурой.

    `gl` - модуль pyqtgraph.opengl (передаётся снаружи, чтобы этот файл
    не импортировал OpenGL на верхнем уровне). `image` - массив (H, W, 4)
    из байтов. Возвращает готовый к добавлению в сцену элемент.
    """
    return _item_class(gl)(verts, faces, uv, normals, image,
                           alpha=alpha, ambient=ambient, smooth=smooth)


_CLASS = None


def _item_class(gl):
    """Класс элемента строится один раз, при первом обращении."""
    global _CLASS
    if _CLASS is not None:
        return _CLASS

    import importlib
    from OpenGL import GL
    from OpenGL.GL import shaders
    from pyqtgraph.Qt import QtGui, QT_LIB
    from pyqtgraph.opengl.GLGraphicsItem import GLGraphicsItem

    if QT_LIB in ("PyQt5", "PySide2"):
        QtOpenGL = QtGui
    else:
        QtOpenGL = importlib.import_module("%s.QtOpenGL" % QT_LIB)

    class TexturedMeshItem(GLGraphicsItem):
        """Меш, окрашенный текстурой, с затенением по нормали."""

        _program = None

        def __init__(self, verts, faces, uv, normals, image,
                     alpha=1.0, ambient=AMBIENT, smooth=True):
            super().__init__()
            self.setGLOptions('opaque' if alpha >= 0.999 else 'translucent')
            self._alpha = float(alpha)
            self._ambient = float(ambient)
            self._smooth = bool(smooth)
            self._image = np.ascontiguousarray(image)
            self._texture = None
            self._need_texture = True
            # позиция (3) + текстура (2) + нормаль (3) в одном буфере
            n = len(verts)
            inter = np.empty((n, 8), dtype=np.float32)
            inter[:, 0:3] = np.asarray(verts, dtype=np.float32)
            inter[:, 3:5] = np.asarray(uv, dtype=np.float32)
            if normals is None:
                inter[:, 5:8] = np.array([0.0, 0.0, 1.0], dtype=np.float32)
            else:
                inter[:, 5:8] = np.asarray(normals, dtype=np.float32)
            self._inter = inter
            self._index = np.asarray(faces, dtype=np.uint32).ravel()
            self._count = len(self._index)
            self._vbo = QtOpenGL.QOpenGLBuffer(
                QtOpenGL.QOpenGLBuffer.Type.VertexBuffer)
            self._ibo = QtOpenGL.QOpenGLBuffer(
                QtOpenGL.QOpenGLBuffer.Type.IndexBuffer)
            self._uploaded = False

        def _upload(self):
            for buf, data in ((self._vbo, self._inter),
                              (self._ibo, self._index)):
                if not buf.isCreated():
                    buf.create()
                buf.bind()
                buf.allocate(data, data.nbytes)
                buf.release()
            self._uploaded = True

        def _upload_texture(self):
            if self._texture is None:
                self._texture = GL.glGenTextures(1)
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._texture)
            filt = GL.GL_LINEAR if self._smooth else GL.GL_NEAREST
            GL.glTexParameteri(GL.GL_TEXTURE_2D,
                               GL.GL_TEXTURE_MIN_FILTER, filt)
            GL.glTexParameteri(GL.GL_TEXTURE_2D,
                               GL.GL_TEXTURE_MAG_FILTER, filt)
            GL.glTexParameteri(GL.GL_TEXTURE_2D,
                               GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
            GL.glTexParameteri(GL.GL_TEXTURE_2D,
                               GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
            h, w = self._image.shape[:2]
            GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA, w, h, 0,
                            GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, self._image)
            GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
            self._need_texture = False

        @classmethod
        def program(cls):
            if cls._program is not None:
                return cls._program
            ctx = QtGui.QOpenGLContext.currentContext()
            fmt = ctx.format()
            if ctx.isOpenGLES():
                core = fmt.version() >= (3, 0)
                head = "#version 300 es\n" if core else ""
            else:
                core = fmt.version() >= (3, 1)
                head = "#version 140\n" if core else ""
            vert = SHADER_CORE_VERT if core else SHADER_LEGACY_VERT
            frag = SHADER_CORE_FRAG if core else SHADER_LEGACY_FRAG
            compiled = [
                shaders.compileShader([head, vert], GL.GL_VERTEX_SHADER),
                shaders.compileShader([head, frag], GL.GL_FRAGMENT_SHADER)]
            program = shaders.compileProgram(*compiled)
            GL.glBindAttribLocation(program, 0, "a_position")
            GL.glBindAttribLocation(program, 1, "a_texcoord")
            GL.glBindAttribLocation(program, 2, "a_norm")
            GL.glLinkProgram(program)
            cls._program = program
            return program

        def paint(self):
            if not self._count:
                return
            self.setupGLState()
            if not self._uploaded:
                self._upload()
            if self._need_texture:
                self._upload_texture()

            mat_mvp = np.array(self.mvpMatrix().data(), dtype=np.float32)
            mat_n = np.array(self.modelViewMatrix().normalMatrix().data(),
                             dtype=np.float32)
            program = self.program()
            stride = 8 * 4
            self._vbo.bind()
            GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, False, stride, None)
            GL.glVertexAttribPointer(1, 2, GL.GL_FLOAT, False, stride,
                                     GL.GLvoidp(3 * 4))
            GL.glVertexAttribPointer(2, 3, GL.GL_FLOAT, False, stride,
                                     GL.GLvoidp(5 * 4))
            self._vbo.release()
            for loc in (0, 1, 2):
                GL.glEnableVertexAttribArray(loc)
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._texture)
            self._ibo.bind()
            with program:
                GL.glUniformMatrix4fv(
                    GL.glGetUniformLocation(program, "u_mvp"),
                    1, False, mat_mvp)
                loc_n = GL.glGetUniformLocation(program, "u_normal")
                if loc_n != -1:
                    GL.glUniformMatrix3fv(loc_n, 1, False, mat_n)
                GL.glUniform1f(
                    GL.glGetUniformLocation(program, "u_ambient"),
                    self._ambient)
                GL.glUniform1f(
                    GL.glGetUniformLocation(program, "u_alpha"),
                    self._alpha)
                GL.glUniform1i(
                    GL.glGetUniformLocation(program, "u_texture"), 0)
                GL.glDrawElements(GL.GL_TRIANGLES, self._count,
                                  GL.GL_UNSIGNED_INT, None)
            self._ibo.release()
            for loc in (0, 1, 2):
                GL.glDisableVertexAttribArray(loc)
            GL.glBindTexture(GL.GL_TEXTURE_2D, 0)

    _CLASS = TexturedMeshItem
    return _CLASS


_TEX_CACHE = {}        # ключ -> массив картинки
_TEX_ORDER = []       # ключи по времени появления
_TEX_BYTES = 0
_TEX_LIMIT = 192 * 1024 * 1024   # потолок кэша текстур, байт
_TEX_WATCHED = set()  # слои, у которых уже перехвачена смена оформления


def texture_key(extent, width, height, layers):
    """Ключ кэша: охват, размер и набор слоёв.

    Охват округляется до микрона: иначе мельчайшее дрожание границ грида
    от пересчёта в float давало бы промах на ровном месте.
    """
    ext = tuple(round(float(v), 6) for v in extent)
    ids = tuple(getattr(lyr, "id", lambda: str(lyr))() for lyr in layers)
    return (ext, int(width), int(height), ids)


def texture_cache_clear():
    """Сбросить кэш текстур. Зовётся при смене оформления слоя."""
    global _TEX_BYTES
    _TEX_CACHE.clear()
    del _TEX_ORDER[:]
    _TEX_BYTES = 0


def texture_cache_size():
    return len(_TEX_CACHE), _TEX_BYTES


def _tex_put(key, img):
    global _TEX_BYTES
    nbytes = int(getattr(img, "nbytes", 0))
    if nbytes > _TEX_LIMIT:
        return
    while _TEX_ORDER and _TEX_BYTES + nbytes > _TEX_LIMIT:
        old = _TEX_ORDER.pop(0)
        prev = _TEX_CACHE.pop(old, None)
        if prev is not None:
            _TEX_BYTES -= int(getattr(prev, "nbytes", 0))
    _TEX_CACHE[key] = img
    _TEX_ORDER.append(key)
    _TEX_BYTES += nbytes


def _watch_styles(layers):
    """Подписаться на смену оформления слоёв, чтобы сбросить кэш.

    Иначе смена символики или цветовой шкалы не доехала бы до сцены:
    картинка бралась бы из памяти прежней. Подписка одноразовая на слой.
    """
    for lyr in layers:
        try:
            lid = lyr.id()
        except Exception:  # nosec
            continue
        if lid in _TEX_WATCHED:
            continue
        for signal in ("styleChanged", "rendererChanged",
                       "dataSourceChanged"):
            sig = getattr(lyr, signal, None)
            if sig is None:
                continue
            try:
                sig.connect(texture_cache_clear)
            except Exception:  # nosec
                pass
        _TEX_WATCHED.add(lid)


def render_project_map(extent, width, height, crs, layers, prof=None):
    """Отрисовать слои проекта в массив (H, W, 4) байтов.

    Рендерит средствами QGIS, а не читает файл: так на текстуру попадает
    ровно то, что человек видит на карте, вместе с настроенной символикой
    и подписями, а перепроецирование берёт на себя QGIS. Годится любой
    слой, не только трёхканальный растр.

    `extent` - (xmin, xmax, ymin, ymax) в координатах `crs`. Если `crs`
    равен None, берётся система первого слоя: так рендерится чертёж
    разреза, который лежит в своих координатах и перепроецированию
    не подлежит. Возвращает None, если отрисовать не удалось.
    """
    key = texture_key(extent, width, height, layers)
    hit = _TEX_CACHE.get(key)
    if hit is not None:
        if prof is not None:
            prof.count("texhits")
        return hit
    try:
        from qgis.core import (QgsMapSettings, QgsMapRendererParallelJob,
                               QgsRectangle)
        from qgis.PyQt.QtCore import QSize
        from qgis.PyQt.QtGui import QColor, QImage
    except Exception:
        return None
    xmin, xmax, ymin, ymax = extent
    ms = QgsMapSettings()
    ms.setLayers(list(layers))
    ms.setBackgroundColor(QColor(255, 255, 255))
    ms.setOutputSize(QSize(int(width), int(height)))
    ms.setExtent(QgsRectangle(xmin, ymin, xmax, ymax))
    if crs is not None:
        try:
            ms.setDestinationCrs(crs)
        except Exception:  # nosec
            pass
    else:
        # чертёж разреза живёт в своих координатах (расстояние на отметку),
        # перепроецировать его не во что: берём систему самих слоёв
        try:
            ms.setDestinationCrs(layers[0].crs())
        except Exception:  # nosec
            pass
    job = QgsMapRendererParallelJob(ms)
    job.start()
    job.waitForFinished()
    img = job.renderedImage()
    if img is None or img.isNull():
        return None
    arr = qimage_to_rgba(img)
    _watch_styles(layers)
    _tex_put(key, arr)
    if prof is not None:
        prof.count("texrender")
    return arr


def qimage_to_rgba(img):
    """QImage в массив (H, W, 4) байтов, перевёрнутый под ось V OpenGL."""
    from qgis.PyQt.QtGui import QImage
    img = img.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = img.width(), img.height()
    ptr = img.constBits()
    try:
        ptr.setsize(img.sizeInBytes())
    except Exception:  # nosec
        pass
    arr = np.frombuffer(bytes(ptr), dtype=np.uint8).reshape(h, w, 4)
    # у картинки начало отсчёта сверху, у текстурной оси V - снизу
    return np.ascontiguousarray(arr[::-1])
