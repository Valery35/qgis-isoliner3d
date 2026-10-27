# -*- coding: utf-8 -*-
"""Система координат сцены: не градусы.

Проект в EPSG:4326, слой перепроецирован в метры: сцена пересчитывала
его обратно в градусы, потому что всегда жила в системе проекта.
Теперь проект в градусах заменяется системой слоя в метрах или зоной
UTM. Проверка без QGIS: зона UTM и то, что пересчёт берёт систему
сцены, а не проекта.
"""

import os
import re
import sys

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d.viewer_core import utm_epsg      # noqa: E402


def test_utm_zones():
    assert utm_epsg(56.25, 58.0) == 32640          # Пермь
    assert utm_epsg(37.6, 55.75) == 32637          # Москва
    assert utm_epsg(-70.6, -33.4) == 32719         # Сантьяго
    assert utm_epsg(-180.0, 10.0) == 32601
    assert utm_epsg(179.9, 10.0) == 32660


def test_transform_targets_the_scene_crs():
    src = open(os.path.join(PKG, "viewer_dialog.py"), encoding="utf-8").read()
    body = src[src.index("    def _xform(self"):]
    body = body[:body.index("\n    def ", 10)]
    assert "self._scene_crs()" in body
    assert "QgsProject.instance().crs()" not in body
    # система выбирается в начале сборки, до чтения слоёв
    reb = src[src.index("    def _rebuild_scene(self"):]
    assert re.search(r"self\._crs_now = self\._pick_scene_crs\(\)", reb)
    assert "isGeographic" in src[src.index("    def _pick_scene_crs"):]


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all scene crs tests passed")


if __name__ == "__main__":
    _run()
