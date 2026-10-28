# -*- coding: utf-8 -*-
"""Разбор колец из WKB без обёрток QGIS (viewer_core.wkb_rings).

Тело толщ из 2.15 на данных Василия - мультиполигон из восьмидесяти
тысяч треугольников. Обход его частей через `constParts` ронял QGIS
нарушением доступа в разных местах разбивки. Сцена теперь берёт кольца
из байтов WKB, и разбор должен давать те же кольца, что и обход.
"""

import os
import struct
import sys

import numpy as np

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import viewer_core as vc       # noqa: E402
from isoliner3d.cadmesh import mesh_wkb         # noqa: E402


def _ring_z(pts):
    return b"".join(struct.pack("<ddd", *p) for p in pts)


def test_multipolygon_z_from_mesh():
    v = np.array([[0, 0, 1], [1, 0, 2], [0, 1, 3], [1, 1, 4]], float)
    f = np.array([[0, 1, 2], [1, 3, 2]])
    rings = vc.wkb_rings(mesh_wkb(v, f))
    assert len(rings) == 2
    assert np.allclose(rings[0], v[[0, 1, 2, 0]])
    assert np.allclose(rings[1], v[[1, 3, 2, 1]])


def test_polygon_with_hole_big_endian_and_ewkb():
    outer = [(0, 0, 5), (4, 0, 5), (4, 4, 5), (0, 0, 5)]
    inner = [(1, 1, 5), (2, 1, 5), (2, 2, 5), (1, 1, 5)]
    body = struct.pack(">I", 2)
    for r in (outer, inner):
        body += struct.pack(">I", len(r)) + b"".join(
            struct.pack(">ddd", *p) for p in r)
    w = b"\x00" + struct.pack(">I", 3 | 0x80000000) + body
    rings = vc.wkb_rings(w)
    assert [len(r) for r in rings] == [4, 4]
    assert np.allclose(rings[1][0], (1, 1, 5))


def test_2d_needs_zfix_and_m_is_skipped():
    pts2 = [(0, 0), (3, 4)]
    w = b"\x01" + struct.pack("<II", 2, 2) + b"".join(
        struct.pack("<dd", *p) for p in pts2)
    assert vc.wkb_rings(w) == []
    got = vc.wkb_rings(w, zfix=7.0)
    assert np.allclose(got[0], [(0, 0, 7), (3, 4, 7)])
    # LineString ZM: четвёртая координата не становится отметкой
    w = b"\x01" + struct.pack("<II", 3002, 1) + struct.pack(
        "<dddd", 1, 2, 3, 99)
    assert np.allclose(vc.wkb_rings(w)[0], [(1, 2, 3)])


def test_curves_fall_back():
    w = b"\x01" + struct.pack("<II", 1008, 0)      # CircularString Z
    assert vc.wkb_rings(w) is None
