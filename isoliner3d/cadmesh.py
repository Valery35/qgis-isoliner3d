# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Запись оболочки в STL и OBJ - форматы, которые понимает CAD.

GLB годится для просмотра: он несёт цвет, прозрачность и камеру.
В CAD нужно другое - замкнутая триангулированная оболочка, из которой
можно сделать тело. Её берут STL и OBJ, оба читает AutoCAD.

Чем они отличаются друг от друга. STL двоичный, хранит только
треугольники и нормали, частей и имён в нём нет: несколько оболочек
сливаются в одну. OBJ текстовый, части в нём остаются отдельными
группами со своими именами, зато файл выходит больше.

Отметки пишутся настоящие. Вертикальное преувеличение это способ
смотреть, а не свойство модели, и в CAD ему делать нечего.

Считается на голом NumPy.
"""

import struct

import numpy as np


def _normals(v, f):
    """Нормали граней. С нулевой нормалью CAD спорит, поэтому
    вырожденной грани даём направление вверх."""
    a = v[f[:, 0]]
    b = v[f[:, 1]]
    c = v[f[:, 2]]
    n = np.cross(b - a, c - a)
    ln = np.linalg.norm(n, axis=1)
    bad = ln < 1e-30
    n[bad] = (0.0, 0.0, 1.0)
    ln[bad] = 1.0
    return n / ln[:, None]


def build_stl(parts, name="Isoliner3D"):
    """Двоичный STL из набора частей.

    Часть это словарь с `verts` (N, 3) и `faces` (M, 3). Частей
    в формате нет, поэтому все они сливаются в одну оболочку.
    Возвращает байты либо None, если писать нечего.
    """
    tris = []
    for part in parts or []:
        v = np.asarray(part.get("verts"), dtype=float)
        f = part.get("faces")
        if f is None or not len(v) or not len(f):
            continue
        f = np.asarray(f, dtype=np.int64)
        tris.append((v, f))
    total = sum(len(f) for _v, f in tris)
    if not total:
        return None

    out = bytearray()
    head = ("%s" % name).encode("ascii", "replace")[:79]
    out.extend(head + b" " * (80 - len(head)))
    out.extend(struct.pack("<I", total))
    for v, f in tris:
        nrm = _normals(v, f)
        for k, tri in enumerate(f):
            out.extend(struct.pack("<3f", *[float(x) for x in nrm[k]]))
            for vi in tri:
                out.extend(struct.pack(
                    "<3f", *[float(x) for x in v[vi]]))
            out.extend(struct.pack("<H", 0))
    return bytes(out)


def build_obj(parts, name="Isoliner3D"):
    """Текстовый OBJ из набора частей.

    Части остаются группами: в CAD их видно порознь, и оболочку
    по одному уровню можно взять отдельно. Вершины в OBJ считаются
    с единицы, у каждой следующей части номера сдвигаются.

    Возвращает строку либо None, если писать нечего.
    """
    lines = ["# %s" % name]
    base = 0
    wrote = 0
    for k, part in enumerate(parts or []):
        v = np.asarray(part.get("verts"), dtype=float)
        f = part.get("faces")
        if f is None or not len(v) or not len(f):
            continue
        f = np.asarray(f, dtype=np.int64)
        lines.append("g %s" % (part.get("name") or ("part_%d" % (k + 1))))
        for p in v:
            lines.append("v %.6f %.6f %.6f"
                         % (float(p[0]), float(p[1]), float(p[2])))
        for tri in f:
            lines.append("f %d %d %d" % (base + int(tri[0]) + 1,
                                         base + int(tri[1]) + 1,
                                         base + int(tri[2]) + 1))
        base += len(v)
        wrote += len(f)
    if not wrote:
        return None
    return "\n".join(lines) + "\n"


def write_cad(path, parts, name="Isoliner3D"):
    """Записать STL или OBJ по расширению пути.

    Возвращает размер в байтах либо None, если писать нечего.
    """
    low = str(path).lower()
    if low.endswith(".obj"):
        txt = build_obj(parts, name)
        if txt is None:
            return None
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(txt)
        return len(txt.encode("utf-8"))
    data = build_stl(parts, name)
    if data is None:
        return None
    with open(path, "wb") as fh:
        fh.write(data)
    return len(data)


_WKB_MULTIPOLYGON_Z = 1006
_WKB_POLYGON_Z = 1003


def mesh_wkb(verts, faces):
    """Меш в двоичную геометрию MultiPolygon Z одним куском.

    Собирая по объекту QGIS на каждый треугольник, делаешь на теле
    в сорок тысяч граней сотни тысяч вызовов через границу языка.
    Двоичный кусок собирается разом средствами NumPy, и геометрия
    читается из него одним вызовом.

    Возвращает байты либо None, если граней нет.
    """
    v = np.asarray(verts, dtype="<f8")
    f = np.asarray(faces)
    if not len(f):
        return None
    n = len(f)
    # кольцо замкнуто: четвёртая точка повторяет первую
    ring = v[np.column_stack([f[:, 0], f[:, 1], f[:, 2], f[:, 0]])]
    rec = np.zeros(n, dtype=np.dtype([
        ("bo", "u1"), ("typ", "<u4"), ("rings", "<u4"),
        ("pts", "<u4"), ("xyz", "<f8", (4, 3))]))
    rec["bo"] = 1
    rec["typ"] = _WKB_POLYGON_Z
    rec["rings"] = 1
    rec["pts"] = 4
    rec["xyz"] = ring
    head = struct.pack("<BII", 1, _WKB_MULTIPOLYGON_Z, n)
    return head + rec.tobytes()


def parse_wkb(blob):
    """Разобрать MultiPolygon Z обратно в кольца. Нужна проверке."""
    n = struct.unpack("<I", blob[5:9])[0]
    rec = np.frombuffer(blob[9:], dtype=np.dtype([
        ("bo", "u1"), ("typ", "<u4"), ("rings", "<u4"),
        ("pts", "<u4"), ("xyz", "<f8", (4, 3))]), count=n)
    return [rec["xyz"][k] for k in range(n)]
