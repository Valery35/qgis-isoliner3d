# -*- coding: utf-8 -*-
"""Привязка в GLB: сдвиг от точки начала и система в метаданных.

Вершины glTF - float32. На настоящих координатах (6 400 000 по северу)
шаг float32 - полметра, и модель на глобусе дрожит. Пишется сдвиг от
круглой точки начала, а точка и система лежат в asset.extras.

Считается без QGIS.
"""

import json
import os
import struct
import sys

import numpy as np

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import gltf                      # noqa: E402


def _parse(data):
    """JSON и двоичный кусок GLB."""
    magic, ver, total = struct.unpack("<III", data[:12])
    assert magic == 0x46546C67 and ver == 2 and total == len(data)
    jl, jt = struct.unpack("<II", data[12:20])
    js = json.loads(data[20:20 + jl].decode("utf-8"))
    bl, _bt = struct.unpack("<II", data[20 + jl:28 + jl])
    return js, data[28 + jl:28 + jl + bl]


def _positions(js, binc, k=0):
    acc = js["accessors"][js["meshes"][k]["primitives"][0]
                          ["attributes"]["POSITION"]]
    view = js["bufferViews"][acc["bufferView"]]
    raw = binc[view["byteOffset"]:view["byteOffset"] + view["byteLength"]]
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 3)


def _part():
    """Треугольник у Перми в UTM 40N с сантиметровыми долями."""
    v = np.array([[501234.56, 6401234.78, 150.25],
                  [501300.01, 6401250.33, 140.75],
                  [501250.99, 6401330.12, 160.5]])
    return {"verts": v, "faces": np.array([[0, 1, 2]]), "name": "t"}


def test_origin_is_round_and_near_the_middle():
    o = gltf.georef_origin([_part()])
    assert o == (501000.0, 6401000.0, 0.0)


def test_local_coordinates_keep_centimetres():
    part = _part()
    js, binc = _parse(gltf.build_glb([part], georef={
        "crs": "EPSG:32640", "wkt": "PROJCS[...]"}))
    meta = js["asset"]["extras"]["isoliner3d"]
    assert meta["crs"] == "EPSG:32640"
    org = meta["origin"]
    pos = _positions(js, binc).astype(float)
    east = pos[:, 0] + org[0]
    north = -pos[:, 2] + org[1]
    elev = pos[:, 1] + org[2]
    real = np.column_stack([east, north, elev])
    # сантиметры сохраняются: без сдвига float32 дал бы полметра
    assert np.abs(real - part["verts"]).max() < 0.005
    assert np.abs(pos).max() < 2000.0
    raw = np.float32(part["verts"][0, 1])
    assert abs(float(raw) - part["verts"][0, 1]) > 0.01


def test_without_georef_coordinates_are_as_before():
    js, binc = _parse(gltf.build_glb([_part()]))
    assert "extras" not in js["asset"]
    pos = _positions(js, binc)
    assert abs(float(pos[0, 0]) - 501234.56) < 0.1


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all gltf georef tests passed")


if __name__ == "__main__":
    _run()
