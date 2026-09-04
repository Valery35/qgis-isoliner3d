# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Свет сцены: три источника вместо одного.

Штатный шейдер pyqtgraph светит одним источником и обрезает
освещённость нулём: `p = dot(n, L); p = p < 0 ? 0 : p * 0.8`, а фон
0.2. Всё, что от источника отвёрнуто, получает ровно эту пятую долю
цвета и выглядит почти чёрным. У тела пласта таких граней половина -
боковые стенки и подошва, - и сцена из тел выходит тёмной.

Здесь источников три. Основной рисует форму, второй светит с другой
стороны вполсилы, третий снизу - это подсветка, а не свет: он не
лепит рельеф, а не даёт провалиться низу. Освещённость берётся по
модулю косинуса: грань, повёрнутая от источника, у замкнутого тела
всё равно видна, и чернить её незачем.

Направления заданы в координатах камеры, как и в штатном шейдере,
поэтому свет не «залипает» на модели при вращении сцены.

Модуль ничего не импортирует на верхнем уровне: OpenGL поднимается
только внутри функции, и модуль читается там, где его нет.
"""

NAME = "isoliner_soft"

FRAGMENT = """
    #ifdef GL_ES
    precision mediump float;
    #endif
    varying vec4 v_color;
    varying vec3 v_normal;
    void main() {
        vec3 n = normalize(v_normal);
        float a = abs(dot(n, normalize(vec3(1.0, -1.0, -1.0))));
        float b = abs(dot(n, normalize(vec3(-1.0, 0.5, -0.8))));
        float c = abs(dot(n, normalize(vec3(0.2, 1.0, -0.5))));
        float p = 0.55 * a + 0.28 * b + 0.17 * c;
        vec3 rgb = v_color.rgb * (0.32 + 0.78 * p);
        gl_FragColor = vec4(clamp(rgb, 0.0, 1.0), v_color.a);
    }
"""

VERTEX = """
    uniform mat4 u_mvp;
    uniform mat3 u_normal;
    attribute vec4 a_position;
    attribute vec3 a_normal;
    attribute vec4 a_color;
    varying vec4 v_color;
    varying vec3 v_normal;
    void main() {
        v_normal = normalize(u_normal * a_normal);
        v_color = a_color;
        gl_Position = u_mvp * a_position;
    }
"""


def soft_shader():
    """Имя шейдера мягкого света. Заводится один раз, при первом спросе.

    Если завести его не удалось - старый OpenGL, нет pyqtgraph, - в ход
    идёт штатный `shaded`. Тёмная сцена лучше, чем пустая.
    """
    try:
        from .viewer_core import _import_gl
        # Тем же путём, каким pyqtgraph поднимает вся остальная сцена.
        # Взяв его через `.libs`, получаешь ВТОРОЙ экземпляр модуля
        # со своим списком шейдеров: программа регистрируется в нём,
        # а рисующий её GLMeshItem ищет в первом и не находит.
        # Падает это молча, уже при отрисовке, и со сцены пропадает
        # всё, что рисуется сплошным цветом: изоповерхности, тела,
        # шарики маркеров.
        _import_gl()
        from pyqtgraph.opengl import shaders
    except Exception:  # nosec - без OpenGL остаёмся на штатном
        return "shaded"
    try:
        if NAME not in shaders.ShaderProgram.names:
            shaders.ShaderProgram(NAME, [
                shaders.VertexShader(VERTEX),
                shaders.FragmentShader(FRAGMENT),
            ])
        # Спрашиваем оттуда же, откуда спросит рисование.
        shaders.getShaderProgram(NAME)
        return NAME
    except Exception:  # nosec
        return "shaded"
