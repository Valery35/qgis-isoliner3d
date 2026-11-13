# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Солнце и тени сцены (shadow.py).

Запуск:  python isoliner3d/tests/test_shadow.py
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from isoliner3d import shadow  # noqa: E402
from isoliner3d.viewer_core import LIGHT_DIR  # noqa: E402


def _plane(n=21, size=100.0, z=0.0):
    xs = np.linspace(0.0, size, n)
    gx, gy = np.meshgrid(xs, xs)
    v = np.column_stack([gx.ravel(), gy.ravel(), np.full(n * n, z)])
    f = []
    for i in range(n - 1):
        for j in range(n - 1):
            a = i * n + j
            f += [(a, a + 1, a + n), (a + 1, a + n + 1, a + n)]
    return v, np.asarray(f)


def _box(x0, y0, x1, y1, z0, z1):
    """Замкнутый ящик из двенадцати треугольников: крупные грани,
    как у выработки, без засева дали бы дыру в карте."""
    v = np.array([(x, y, z) for z in (z0, z1) for y in (y0, y1)
                  for x in (x0, x1)], dtype=float)
    f = [(0, 1, 3), (0, 3, 2), (4, 6, 7), (4, 7, 5),
         (0, 4, 5), (0, 5, 1), (2, 3, 7), (2, 7, 6),
         (0, 2, 6), (0, 6, 4), (1, 5, 7), (1, 7, 3)]
    return v, np.asarray(f)


def test_sun_vector_points_at_the_sun():
    s = shadow.sun_vector(90.0, 0.0)
    assert s[0] > 0.99 and abs(s[1]) < 0.02
    s = shadow.sun_vector(180.0, 45.0)
    assert abs(s[0]) < 1e-9 and s[1] < -0.7 and abs(s[2] - 0.7071) < 1e-3
    assert abs(np.linalg.norm(shadow.sun_vector(33, 17)) - 1.0) < 1e-12


def test_default_sun_is_the_old_hillshade_light():
    d = np.asarray(LIGHT_DIR) / np.linalg.norm(LIGHT_DIR)
    s = shadow.sun_vector(shadow.SUN_AZIMUTH, shadow.SUN_ALTITUDE)
    assert float(d @ s) > 0.999


def test_box_casts_shadow_away_from_the_sun():
    plane = _plane()
    box = _box(45.0, 45.0, 55.0, 55.0, 0.0, 20.0)
    sm = shadow.ShadowMap([plane, box], shadow.sun_vector(180.0, 45.0),
                          side=256)
    pts = np.array([[50.0, 68.0, 0.0],     # за ящиком, к северу
                    [50.0, 30.0, 0.0],     # перед ящиком, на свету
                    [50.0, 85.0, 0.0],     # дальше конца тени
                    [50.0, 50.0, 20.0],    # крыша ящика
                    [10.0, 10.0, 0.0]])    # открытое место
    s = sm.shade(pts)
    assert s[0] > 0.9, s
    assert s[1] < 0.1 and s[2] < 0.1 and s[3] < 0.1 and s[4] < 0.1, s


def test_flat_ground_does_not_shadow_itself():
    plane = _plane()
    sm = shadow.ShadowMap([plane], shadow.sun_vector(218.0, 20.0),
                          side=256)
    assert sm.shade(plane[0]).max() < 0.05


def test_ridge_shadows_the_valley_behind():
    n = 41
    xs = np.linspace(0.0, 100.0, n)
    gx, gy = np.meshgrid(xs, xs)
    gz = np.where(np.abs(gy - 40.0) < 4.0, 15.0, 0.0)
    v = np.column_stack([gx.ravel(), gy.ravel(), gz.ravel()])
    f = []
    for i in range(n - 1):
        for j in range(n - 1):
            a = i * n + j
            f += [(a, a + 1, a + n), (a + 1, a + n + 1, a + n)]
    sm = shadow.ShadowMap([(v, np.asarray(f))],
                          shadow.sun_vector(180.0, 30.0), side=256)
    s = sm.shade(np.array([[50.0, 55.0, 0.0], [50.0, 20.0, 0.0]]))
    assert s[0] > 0.9 and s[1] < 0.1, s


def test_slope_turned_from_the_sun_is_in_its_own_shadow():
    """Склон, отвёрнутый от Солнца, в тени сам по себе, а нормаль,
    смотрящая вниз из-за обхода треугольников, поворачивается вверх."""
    plane = _plane()
    sm = shadow.ShadowMap([plane], shadow.sun_vector(180.0, 30.0),
                          side=256)
    p = np.array([[50.0, 50.0, 0.0]] * 3)
    away = np.array([0.0, 0.7071, 0.7071])     # смотрит на север
    up = np.array([0.0, 0.0, 1.0])
    s = sm.shade(p, np.array([away, up, -up]))
    assert s[0] > 0.99 and s[1] < 0.05 and s[2] < 0.05, s


def test_darken_keeps_alpha_and_light():
    c = np.array([[0.8, 0.6, 0.4, 0.5], [0.8, 0.6, 0.4, 1.0]])
    out = shadow.darken(c, np.array([1.0, 0.0]), 0.5)
    assert np.allclose(out[0], [0.4, 0.3, 0.2, 0.5])
    assert np.allclose(out[1], c[1])


def test_empty_scene_is_lit():
    sm = shadow.ShadowMap([], shadow.sun_vector(0, 45))
    assert sm.shade(np.zeros((3, 3))).tolist() == [0.0, 0.0, 0.0]


if __name__ == "__main__":
    k = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK", name)
            k += 1
    print("all shadow tests passed (%d)" % k)
