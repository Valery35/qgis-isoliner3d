# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Кнопка «Открыть в Isoliner Scene»: расчётная часть (scene_app.py).

Запуск:  python isoliner3d/tests/test_scene_app.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from isoliner3d import scene_app  # noqa: E402


def test_package_name_is_safe():
    assert scene_app.package_name("Карьер Север") == "Карьер Север.i3dscene"
    assert scene_app.package_name('a/b:c*?"<>|d') == "a_b_c_d.i3dscene"
    assert scene_app.package_name("") == "scene.i3dscene"
    assert scene_app.package_name(None) == "scene.i3dscene"
    assert scene_app.package_name(" .. ") == "scene.i3dscene"


def test_package_path_follows_the_contract():
    got = scene_app.package_path("demo", "T")
    assert got == os.path.join("T", "isoliner3d", "demo.i3dscene")
    assert scene_app.temp_path(got) == got + ".part"


def test_app_search_order():
    """Настройки, потом PATH, потом место установки."""
    files = {"C:/my/scene.exe",
             os.path.join("L", "Programs", "Isoliner Scene",
                          "isoliner-scene.exe")}

    def isfile(p):
        return p in files

    def which_none(_n):
        return None

    def which_path(n):
        assert n == "isoliner-scene"
        return "/usr/bin/isoliner-scene"

    assert scene_app.find_app("C:/my/scene.exe", which_path, "L",
                              isfile) == "C:/my/scene.exe"
    # путь из настроек пропал - дальше по порядку
    assert scene_app.find_app("C:/gone.exe", which_path, "L",
                              isfile) == "/usr/bin/isoliner-scene"
    assert scene_app.find_app("", which_none, "L", isfile) == \
        os.path.join("L", "Programs", "Isoliner Scene", "isoliner-scene.exe")
    # архив программы кладёт exe в bin\ папки установки
    files.add(os.path.join("M", "Programs", "Isoliner Scene", "bin",
                           "isoliner-scene.exe"))
    assert scene_app.find_app("", which_none, "M", isfile) == \
        os.path.join("M", "Programs", "Isoliner Scene", "bin",
                     "isoliner-scene.exe")
    assert scene_app.find_app("", which_none, "N", isfile) == ""
    assert scene_app.find_app("", which_none, "", isfile) == ""


def test_replace_retries_while_the_file_is_busy():
    calls, naps = [], []

    def busy_twice(src, dst):
        calls.append((src, dst))
        if len(calls) < 3:
            raise PermissionError("busy")
    n = scene_app.replace_file("a", "b", tries=5, delay=0.05,
                               replace=busy_twice, sleep=naps.append)
    assert n == 3 and len(calls) == 3 and naps == [0.05, 0.05]

    def always_busy(src, dst):
        raise PermissionError("busy")
    try:
        scene_app.replace_file("a", "b", tries=3, replace=always_busy,
                               sleep=naps.append)
    except PermissionError:
        pass
    else:
        raise AssertionError("последняя неудача должна уйти наверх")


def test_replace_swaps_a_real_file():
    with tempfile.TemporaryDirectory() as d:
        dst = os.path.join(d, "s.i3dscene")
        with open(dst, "wb") as fh:
            fh.write(b"old")
        part = scene_app.temp_path(dst)
        with open(part, "wb") as fh:
            fh.write(b"new package")
        assert scene_app.replace_file(part, dst) == 1
        assert not os.path.exists(part)
        with open(dst, "rb") as fh:
            assert fh.read() == b"new package"


def test_is_running():
    class P(object):
        def __init__(self, code):
            self.code = code

        def poll(self):
            return self.code
    assert not scene_app.is_running(None)
    assert scene_app.is_running(P(None))
    assert not scene_app.is_running(P(0))


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK", name)
            n += 1
    print("all scene-app tests passed (%d)" % n)
