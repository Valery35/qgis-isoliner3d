# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Запись сцены в glTF двоичный (GLB).

Формат выбран из-за читателей: GLB открывают браузерные просмотрщики,
Blender, Windows и большинство программ, куда геологу нужно отдать
модель. Файл один, внешних ссылок нет, поэтому его можно просто
отправить письмом.

Пишется вручную, без сторонних библиотек: glTF это JSON плюс двоичный
кусок, и для набора треугольников с цветами в вершинах этого достаточно.

Координаты пишутся настоящие, из проекта, без центрирования сцены
и без вертикального преувеличения: преувеличение это способ смотреть,
а не свойство модели. Оси переставляются в порядок glTF (Y вверх),
иначе модель ложится на бок в любом просмотрщике.
"""

import json
import struct

import numpy as np

_FLOAT = 5126
_UINT = 5125
_ARRAY_BUFFER = 34962
_ELEMENT_ARRAY_BUFFER = 34963
_TRIANGLES = 4


def _pad(data, fill=b"\x00"):
    """Дополнить до кратности четырём: этого требует формат."""
    rem = len(data) % 4
    return data if rem == 0 else data + fill * (4 - rem)


def build_glb(parts, name="Isoliner3D"):
    """Собрать GLB из набора частей.

    Каждая часть это словарь с ключами `verts` (N, 3), `faces` (M, 3)
    и необязательным `colors` (N, 3) или (N, 4) в долях единицы,
    плюс `name`. Возвращает байты файла.
    """
    buf = bytearray()
    views, accessors, meshes, nodes = [], [], [], []

    def add_view(data, target):
        offset = len(buf)
        buf.extend(data)
        while len(buf) % 4:
            buf.append(0)
        views.append({"buffer": 0, "byteOffset": offset,
                      "byteLength": len(data), "target": target})
        return len(views) - 1

    for part in parts:
        v = np.asarray(part["verts"], dtype=np.float32)
        f = np.asarray(part["faces"], dtype=np.uint32)
        if not len(v) or not len(f):
            continue
        # glTF смотрит вдоль -Z, вверх у него Y: наши XYZ становятся
        # X, Z, -Y, иначе модель лежит на боку
        pos = np.column_stack([v[:, 0], v[:, 2], -v[:, 1]]).astype(np.float32)
        vi = add_view(pos.tobytes(), _ARRAY_BUFFER)
        accessors.append({
            "bufferView": vi, "componentType": _FLOAT, "count": len(pos),
            "type": "VEC3",
            "min": [float(x) for x in pos.min(axis=0)],
            "max": [float(x) for x in pos.max(axis=0)]})
        p_acc = len(accessors) - 1

        fi = add_view(f.reshape(-1).tobytes(), _ELEMENT_ARRAY_BUFFER)
        accessors.append({"bufferView": fi, "componentType": _UINT,
                          "count": int(f.size), "type": "SCALAR"})
        i_acc = len(accessors) - 1

        attrs = {"POSITION": p_acc}
        cols = part.get("colors")
        if cols is not None and len(cols):
            c = np.asarray(cols, dtype=np.float32)
            if c.shape[1] == 3:
                c = np.column_stack([c, np.ones(len(c), dtype=np.float32)])
            ci = add_view(c.astype(np.float32).tobytes(), _ARRAY_BUFFER)
            accessors.append({"bufferView": ci, "componentType": _FLOAT,
                              "count": len(c), "type": "VEC4"})
            attrs["COLOR_0"] = len(accessors) - 1

        meshes.append({"name": part.get("name", "part"),
                       "primitives": [{"attributes": attrs,
                                       "indices": i_acc,
                                       "material": 0,
                                       "mode": _TRIANGLES}]})
        nodes.append({"mesh": len(meshes) - 1,
                      "name": part.get("name", "part")})

    gltf = {
        "asset": {"version": "2.0", "generator": name},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": meshes,
        "accessors": accessors,
        "bufferViews": views,
        "buffers": [{"byteLength": len(buf)}],
        "materials": [{
            "name": "vertex",
            "pbrMetallicRoughness": {
                "baseColorFactor": [1.0, 1.0, 1.0, 1.0],
                "metallicFactor": 0.0, "roughnessFactor": 0.9},
            "doubleSided": True}],
    }

    js = _pad(json.dumps(gltf, ensure_ascii=False).encode("utf-8"), b" ")
    bin_chunk = _pad(bytes(buf))
    total = 12 + 8 + len(js) + 8 + len(bin_chunk)
    out = bytearray()
    out.extend(struct.pack("<III", 0x46546C67, 2, total))
    out.extend(struct.pack("<II", len(js), 0x4E4F534A))
    out.extend(js)
    out.extend(struct.pack("<II", len(bin_chunk), 0x004E4942))
    out.extend(bin_chunk)
    return bytes(out)


def write_glb(path, parts, name="Isoliner3D"):
    """Записать GLB в файл. Возвращает размер в байтах."""
    data = build_glb(parts, name)
    with open(path, "wb") as fh:
        fh.write(data)
    return len(data)
