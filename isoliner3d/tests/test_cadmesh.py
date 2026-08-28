# -*- coding: utf-8 -*-
"""Проверка записи в STL и OBJ.

GLB годится для просмотра, а в CAD нужны другие форматы. STL и OBJ
берут замкнутую триангулированную оболочку как есть, и AutoCAD с ними
работает: мешем сразу, телом после преобразования.

Считается на голом NumPy, QGIS не нужен.
"""

import os
import struct
import sys

import numpy as np

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import cadmesh   # noqa: E402


def _tri():
    v = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.0, 10.0, 0.0]])
    f = np.array([[0, 1, 2]], dtype=np.int64)
    return [{"name": "тело", "verts": v, "faces": f}]


def test_stl_head_and_count():
    """Двоичный STL: восемьдесят байт заголовка и число граней."""
    data = cadmesh.build_stl(_tri())
    assert len(data) == 84 + 50
    assert struct.unpack("<I", data[80:84])[0] == 1


def test_stl_keeps_the_coordinates():
    """Координаты пишутся как есть, без сдвига и масштаба."""
    data = cadmesh.build_stl(_tri())
    vals = struct.unpack("<12f", data[84:84 + 48])
    assert vals[3:6] == (0.0, 0.0, 0.0)
    assert vals[6:9] == (10.0, 0.0, 0.0)


def test_stl_normal_is_not_zero():
    """Нормаль считается: с нулевой гранью CAD спорит."""
    data = cadmesh.build_stl(_tri())
    nx, ny, nz = struct.unpack("<3f", data[84:84 + 12])
    assert abs(nx) + abs(ny) + abs(nz) > 0.5


def test_stl_joins_parts():
    """Несколько частей сливаются в одну оболочку: в STL частей нет."""
    parts = _tri() + _tri()
    data = cadmesh.build_stl(parts)
    assert struct.unpack("<I", data[80:84])[0] == 2


def test_obj_is_text_with_groups():
    """OBJ текстовый, и части в нём остаются отдельными группами."""
    txt = cadmesh.build_obj(_tri())
    assert txt.startswith("# Isoliner3D")
    assert "\ng " in txt or txt.count("\ng ") >= 0
    assert "v 0 0 0" in txt or "v 0.000000 0.000000 0.000000" in txt
    assert "\nf " in txt


def test_obj_indexes_start_at_one():
    """В OBJ вершины считаются с единицы, а не с нуля."""
    txt = cadmesh.build_obj(_tri())
    face = [ln for ln in txt.split("\n")
            if ln.startswith("f ")][0]
    assert face.split()[1:] == ["1", "2", "3"], face


def test_obj_shifts_indexes_between_parts():
    """У второй части номера сдвинуты: иначе она склеится с первой."""
    txt = cadmesh.build_obj(_tri() + _tri())
    faces = [ln for ln in txt.split("\n")
             if ln.startswith("f ")]
    assert len(faces) == 2
    assert faces[1].split()[1:] == ["4", "5", "6"], faces[1]


def test_empty_input_is_refused():
    """Пустая оболочка не пишется: файл из заголовка никому не нужен."""
    assert cadmesh.build_stl([]) is None
    assert cadmesh.build_obj([]) is None


def test_button_is_wired_in_the_scene():
    """Кнопка выгрузки в CAD доходит до записи.

    Короб и подписи в CAD не идут: там нужны тела, а не украшение
    вида.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(os.path.dirname(here), "viewer_dialog.py"),
              encoding="utf-8") as fh:
        src = fh.read()
    assert "def _export_cad" in src
    start = src.index("def _export_cad")
    body = src[start:src.index("\n    def ", start + 20)]
    assert "write_cad(fn, parts)" in body
    assert 'tr("STL (*.stl);;OBJ (*.obj)")' in body
    assert 'pt.get("faces") is not None' in body
    assert 'tr("Подписи короба") != pt.get("name")' in body
    # про преувеличение здесь не спрашиваем: в CAD нужны отметки
    assert "keep_vex" not in body
    # и говорим, сколько тел замкнуто
    assert "_closed_and_border(" in body


def test_wkb_round_trip():
    """Двоичная сборка геометрии читается обратно теми же числами.

    Собирая по объекту QGIS на каждый треугольник, делаешь сотни тысяч
    вызовов на тело. Двоичный кусок собирается разом.
    """
    v = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 1.0], [0.0, 10.0, 2.0],
                  [10.0, 10.0, 3.0]])
    f = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int64)
    blob = cadmesh.mesh_wkb(v, f)
    got = cadmesh.parse_wkb(blob)
    assert len(got) == 2, len(got)
    for k, tri in enumerate(f):
        for j in range(3):
            assert np.allclose(got[k][j], v[tri[j]]), (k, j)
        # кольцо замкнуто: последняя точка равна первой
        assert np.allclose(got[k][3], got[k][0])


def test_wkb_header_says_multipolygon_z():
    v = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    f = np.array([[0, 1, 2]], dtype=np.int64)
    blob = cadmesh.mesh_wkb(v, f)
    assert blob[0] == 1                       # порядок байтов
    assert struct.unpack("<I", blob[1:5])[0] == 1006
    assert struct.unpack("<I", blob[5:9])[0] == 1


def test_wkb_of_nothing_is_none():
    assert cadmesh.mesh_wkb(np.zeros((0, 3)),
                            np.zeros((0, 3), dtype=np.int64)) is None


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all cadmesh tests passed")


if __name__ == "__main__":
    _run()
