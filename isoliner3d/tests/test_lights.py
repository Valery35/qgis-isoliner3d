# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Свет сцены. Формула шейдера считается здесь на NumPy: сам шейдер
исполняется на видеокарте, и проверить его иначе нечем, а разойтись
эти две записи не должны.

Запуск: python -m pytest isoliner3d/tests/test_lights.py -q
"""
import os
import re
import sys

import numpy as np

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import lights   # noqa: E402


def _dirs():
    """Направления и веса, прочитанные из текста шейдера.

    Разбором, а не переписыванием чисел рядом: переписанные числа
    расходятся с шейдером на первой же правке, и проверка начинает
    подтверждать не то, что рисуется.
    """
    vecs = [tuple(float(v) for v in m)
            for m in re.findall(
                r"vec3\(\s*(-?[\d.]+),\s*(-?[\d.]+),\s*(-?[\d.]+)\s*\)",
                lights.FRAGMENT)]
    ws = [float(w) for w in re.findall(r"([\d.]+) \* [abc]",
                                       lights.FRAGMENT)]
    amb, gain = (float(x) for x in re.search(
        r"\(([\d.]+) \+ ([\d.]+) \* p\)", lights.FRAGMENT).groups())
    return vecs, ws, amb, gain


def _brightness(normals):
    """Яркость по формуле шейдера."""
    vecs, ws, amb, gain = _dirs()
    p = np.zeros(len(normals))
    for vec, w in zip(vecs, ws):
        d = np.asarray(vec, dtype=float)
        p += w * np.abs(normals @ (d / np.linalg.norm(d)))
    return np.clip(amb + gain * p, 0.0, 1.0)


def _stock(normals):
    """Яркость штатного шейдера pyqtgraph, для сравнения."""
    d = np.array([1.0, -1.0, -1.0])
    d = d / np.linalg.norm(d)
    p = normals @ d
    return np.where(p < 0, 0.0, p * 0.8) + 0.2


def _sphere(n=20000):
    rng = np.random.default_rng(0)
    v = rng.normal(size=(n, 3))
    return v / np.linalg.norm(v, axis=1)[:, None]


def test_three_lights_are_declared():
    """Источников именно три, и веса дают единицу."""
    vecs, ws, amb, gain = _dirs()
    assert len(vecs) == 3 and len(ws) == 3
    assert abs(sum(ws) - 1.0) < 1e-9, ws
    assert amb + gain <= 1.2, "пересвет ломает цвет слоя"


def test_no_face_goes_black():
    """Ни одна грань не проваливается в темноту.

    У штатного шейдера всё, что отвёрнуто от источника, получает
    ровно фоновую пятую долю цвета. У тела пласта таких граней
    половина: боковые стенки и подошва.
    """
    n = _sphere()
    ours, stock = _brightness(n), _stock(n)
    assert stock.min() < 0.25, "иначе сравнивать не с чем"
    assert ours.min() > 0.4, ours.min()
    assert ours.mean() > 1.5 * stock.mean(), (ours.mean(), stock.mean())


def test_form_is_still_readable():
    """Свет не должен стать плоской заливкой: форма читается им же."""
    n = _sphere()
    b = _brightness(n)
    assert b.max() - b.min() > 0.3, (b.min(), b.max())


def test_shader_falls_back_when_opengl_is_missing():
    """Без OpenGL остаёмся на штатном: тёмная сцена лучше пустой."""
    name = lights.soft_shader()
    assert name in (lights.NAME, "shaded")


class _FakeShaders(object):
    """Подобие pyqtgraph.opengl.shaders со своим списком программ."""

    class ShaderProgram(object):
        names = {}

        def __init__(self, name, parts):
            self.name, self.parts = name, parts
            _FakeShaders.ShaderProgram.names[name] = self

    @staticmethod
    def VertexShader(code):
        return ("v", code)

    @staticmethod
    def FragmentShader(code):
        return ("f", code)

    @staticmethod
    def getShaderProgram(name):
        return _FakeShaders.ShaderProgram.names[name]


def _with_fake_pyqtgraph(fake):
    """Подставить модуль, из которого plugin берёт шейдеры."""
    import types
    pkg = types.ModuleType("pyqtgraph")
    ogl = types.ModuleType("pyqtgraph.opengl")
    pkg.opengl = ogl
    ogl.shaders = fake
    saved = {k: sys.modules.get(k) for k in
             ("pyqtgraph", "pyqtgraph.opengl", "pyqtgraph.opengl.shaders")}
    sys.modules["pyqtgraph"] = pkg
    sys.modules["pyqtgraph.opengl"] = ogl
    sys.modules["pyqtgraph.opengl.shaders"] = fake
    return saved


def _restore(saved):
    for k, v in saved.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v


def test_shader_lands_in_the_registry_the_scene_asks():
    """Программа регистрируется там же, где её ищет отрисовка.

    Взятая через `.libs`, она попадала во второй экземпляр модуля
    со своим списком, а рисующий её GLMeshItem искал в первом. Падало
    это молча, при отрисовке, и со сцены пропадало всё, что рисуется
    сплошным цветом: изоповерхности, тела, шарики маркеров.
    """
    fake = _FakeShaders
    fake.ShaderProgram.names = {}
    saved = _with_fake_pyqtgraph(fake)
    try:
        name = lights.soft_shader()
        assert name == lights.NAME, name
        assert fake.getShaderProgram(lights.NAME) is not None
        # повторный вызов не заводит второй экземпляр
        lights.soft_shader()
        assert len(fake.ShaderProgram.names) == 1
    finally:
        _restore(saved)


def test_shader_falls_back_when_registration_fails():
    """Не завелось - рисуем штатным. Тёмная сцена лучше пустой."""
    class _Broken(_FakeShaders):
        @staticmethod
        def getShaderProgram(name):
            raise KeyError(name)

    _Broken.ShaderProgram.names = {}
    saved = _with_fake_pyqtgraph(_Broken)
    try:
        assert lights.soft_shader() == "shaded"
    finally:
        _restore(saved)


if __name__ == "__main__":
    for nm, fn in sorted(globals().items()):
        if nm.startswith("test_") and callable(fn):
            fn()
            print("OK", nm)
    print("all lights tests passed")
