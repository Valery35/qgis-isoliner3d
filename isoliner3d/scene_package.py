# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Пакет сцены: сцена отдельно от QGIS, одним файлом.

Окно просмотра держит сцену в проекте QGIS: состояние ссылается
на слои по id, а геометрию каждый раз строит из слоёв. Приложению
без QGIS (сцена на Rust, RustGIS) слоёв не прочитать. Ему нужен
файл, где геометрия уже собрана, а камера и виды записаны в настоящих
координатах.

Пакет .i3dscene - zip из двух частей:

- scene.glb - геометрия сцены, как в выгрузке GLB (gltf.py): привязка
  к системе координат и точка начала в asset.extras.isoliner3d,
  настоящие высоты, без преувеличения;
- scene.json - всё остальное: формат, версия модуля, имя сцены,
  система координат, преувеличение, камера и виды облёта в настоящих
  координатах, список частей с их узлами в GLB и полное состояние
  окна (state) для возврата в QGIS.

Читатель на Rust берёт из scene.json поля format..parts и glb,
а state хранит как есть: это настройки окна QGIS, ему они не нужны.

Камера окна живёт в координатах просмотра: план сдвинут на центр
сцены (cx, cy), высота - (z - cz) * vex. Здесь она переводится
в настоящие координаты и обратно (frame = cx, cy, cz, vex).

Формат. Номер в scene.json - наименьший, которым пакет читается.
Формат 1: части-тела и линии. Формат 2: ещё и точки (пробы, значки
скважин): примитив POINTS в GLB и размер значка в пикселях атрибутом
_SIZE. Пакет без точек пишется первым форматом, и его по-прежнему
читают программы, которые точек не знают. Пакет с точками такая
программа не откроет и скажет, что он новее неё, а не упадёт на
незнакомом примитиве.

Модуль Qt и QGIS не знает.
"""

import io
import json
import struct
import zipfile

import numpy as np

from . import gltf

FORMAT = 2          # наибольший формат, который модуль пишет и читает
FORMAT_POINTS = 2   # с него в пакете бывают точки
EXT = ".i3dscene"
GLB_NAME = "scene.glb"
JSON_NAME = "scene.json"

CAMERA_KEYS = ("center", "distance", "azimuth", "elevation", "fov",
               "ortho")


def _frame(frame):
    f = frame or {}
    return (float(f.get("cx", 0.0)), float(f.get("cy", 0.0)),
            float(f.get("cz", 0.0)), float(f.get("vex", 1.0) or 1.0))


def camera_to_world(cam, frame):
    """Камера окна в настоящих координатах.

    Центр - точка, вокруг которой ходит камера. Удаление - по плану
    в метрах, преувеличение его не меняет. Ракурс и раствор в градусах.
    """
    cx, cy, cz, vex = _frame(frame)
    out = {k: cam[k] for k in CAMERA_KEYS if k in cam}
    x, y, z = cam.get("center", (0.0, 0.0, 0.0))
    out["center"] = [float(x) + cx, float(y) + cy, float(z) / vex + cz]
    return out


def camera_from_world(cam, frame):
    """Обратный перевод: настоящая камера в координаты окна."""
    cx, cy, cz, vex = _frame(frame)
    out = {k: cam[k] for k in CAMERA_KEYS if k in cam}
    x, y, z = cam.get("center", (0.0, 0.0, 0.0))
    out["center"] = [float(x) - cx, float(y) - cy, (float(z) - cz) * vex]
    return out


def _kind(part):
    """Вид части и попадёт ли она в GLB: та же проверка, что в gltf.py."""
    v = part.get("verts")
    if part.get("faces") is not None:
        kind, idx = "mesh", part["faces"]
    elif part.get("lines") is not None:
        kind, idx = "lines", part["lines"]
    elif part.get("points") is not None:
        kind, idx = "points", part["points"]
    else:
        return None
    if v is None or not len(v) or not len(idx):
        return None
    return kind


def describe(parts):
    """Части сцены для scene.json: имя, вид, узел GLB, размеры."""
    out = []
    node = 0
    for part in parts:
        kind = _kind(part)
        if kind is None:
            continue
        idx = part[{"mesh": "faces", "lines": "lines",
                    "points": "points"}[kind]]
        item = {"node": node, "name": part.get("name", "part"),
                "kind": kind, "verts": int(len(part["verts"])),
                "elements": int(len(idx)),
                "decor": bool(part.get("decor", False))}
        for key in ("layer", "opacity", "shape"):
            if part.get(key) is not None:
                item[key] = part[key]
        out.append(item)
        node += 1
    return out


def pack(parts, state, name="", frame=None, crs="", wkt="",
         version=""):
    """Пакет сцены байтами (zip).

    parts - части сцены в настоящих координатах, как для выгрузки GLB.
    state - состояние окна (_state_dict), камера в нём в координатах
    окна. frame - {cx, cy, cz, vex} окна на момент записи.
    """
    state = dict(state or {})
    _cx, _cy, _cz, vex = _frame(frame)
    georef = {"crs": crs, "wkt": wkt, "vex": 1.0}
    glb = gltf.build_glb(parts, name or "Isoliner3D", georef=georef)
    info = describe(parts)
    fmt = FORMAT_POINTS if any(i["kind"] == "points" for i in info) else 1
    meta = {
        "format": fmt,
        "module": "isoliner3d",
        "version": version,
        "name": name,
        "crs": {"authid": crs, "wkt": wkt},
        "origin": list(gltf.georef_origin(parts)),
        "vex": vex,
        "camera": camera_to_world(state.get("camera") or {}, frame),
        "views": [camera_to_world(v, frame)
                  for v in state.get("fly_views") or []
                  if isinstance(v, dict)],
        "parts": info,
        "glb": GLB_NAME,
        "state": state,
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(JSON_NAME, json.dumps(meta, ensure_ascii=False,
                                         indent=1))
        z.writestr(GLB_NAME, glb)
    return buf.getvalue()


def write(path, *args, **kwargs):
    """Записать пакет в файл. Возвращает размер в байтах."""
    data = pack(*args, **kwargs)
    with open(path, "wb") as fh:
        fh.write(data)
    return len(data)


def unpack(data):
    """(scene.json словарём, байты GLB) из пакета."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        meta = json.loads(z.read(JSON_NAME).decode("utf-8"))
        if int(meta.get("format", 0)) > FORMAT:
            raise ValueError("пакет сцены новее модуля: формат %s"
                             % meta.get("format"))
        glb = z.read(meta.get("glb") or GLB_NAME)
    return meta, glb


def read(path):
    with open(path, "rb") as fh:
        return unpack(fh.read())


def state_for_window(meta, frame):
    """Состояние окна из пакета: камера и виды под текущий frame.

    Окно на другом компьютере может собрать сцену с другим центром,
    поэтому камера берётся из настоящих координат пакета.
    """
    state = dict(meta.get("state") or {})
    if meta.get("camera"):
        state["camera"] = camera_from_world(meta["camera"], frame)
    state["fly_views"] = [camera_from_world(v, frame)
                          for v in meta.get("views") or []]
    return state


_COMPONENTS = {"SCALAR": 1, "VEC3": 3, "VEC4": 4}
_DTYPES = {5126: np.float32, 5125: np.uint32}


def read_glb(glb):
    """Части из GLB в настоящих координатах: [{name, verts,
    faces|lines|points, colors, sizes}], и привязка
    из asset.extras.isoliner3d.

    Читает то, что пишет gltf.py. Нужен проверкам и как образец для
    читателя на Rust.
    """
    magic, _ver, _total = struct.unpack_from("<III", glb, 0)
    if magic != 0x46546C67:
        raise ValueError("не GLB")
    n_js, _t = struct.unpack_from("<II", glb, 12)
    doc = json.loads(glb[20:20 + n_js].decode("utf-8"))
    off = 20 + n_js
    n_bin, _t = struct.unpack_from("<II", glb, off)
    binary = glb[off + 8:off + 8 + n_bin]
    extras = (doc.get("asset", {}).get("extras") or {}).get(
        "isoliner3d") or {}
    shift = np.asarray(extras.get("origin") or (0.0, 0.0, 0.0),
                       dtype=float)

    def array(i):
        acc = doc["accessors"][i]
        view = doc["bufferViews"][acc["bufferView"]]
        comp = _COMPONENTS[acc["type"]]
        a = np.frombuffer(binary, dtype=_DTYPES[acc["componentType"]],
                          count=acc["count"] * comp,
                          offset=view["byteOffset"])
        return a.reshape(-1, comp) if comp > 1 else a

    parts = []
    for node in doc.get("nodes", []):
        prim = doc["meshes"][node["mesh"]]["primitives"][0]
        pos = array(prim["attributes"]["POSITION"]).astype(float)
        verts = np.column_stack([pos[:, 0], -pos[:, 2], pos[:, 1]]) + shift
        idx = array(prim["indices"]).astype(np.int64)
        part = {"name": node.get("name", "")}
        mode = prim.get("mode", 4)
        if mode == 1:
            part["lines"] = idx.reshape(-1, 2)
        elif mode == 0:
            part["points"] = idx
        else:
            part["faces"] = idx.reshape(-1, 3)
        part["verts"] = verts
        if "COLOR_0" in prim["attributes"]:
            part["colors"] = array(prim["attributes"]["COLOR_0"]).astype(
                float)
        if "_SIZE" in prim["attributes"]:
            part["sizes"] = array(prim["attributes"]["_SIZE"]).astype(
                float)
        parts.append(part)
    return parts, extras
