# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Пакет сцены .i3dscene (scene_package.py) без QGIS."""
import json
import os
import sys
import zipfile
import io

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from isoliner3d import scene_package as sp  # noqa: E402
from isoliner3d import sweep  # noqa: E402

X0, Y0 = 512345.0, 6401234.0
FRAME = {"cx": X0 + 50.0, "cy": Y0, "cz": -300.0, "vex": 5.0}


def _parts():
    v, f, _l, _t = sweep.sweep([(X0, Y0, -300.0), (X0 + 100, Y0, -300.0)],
                               sweep.profile("rect", 4.0, 3.0))
    box = np.array([(X0, Y0, -310.0), (X0 + 100, Y0, -310.0)])
    return [
        {"name": "Штрек", "verts": v, "faces": f, "layer": "drift_1",
         "colors": np.tile([0.8, 0.2, 0.1, 0.5], (len(v), 1))},
        {"name": "пусто", "verts": np.zeros((0, 3)),
         "faces": np.zeros((0, 3), int)},
        {"name": "Короб", "verts": box, "lines": np.array([[0, 1]]),
         "decor": True},
    ]


def _state():
    cam = {"center": [0.0, 10.0, 25.0], "distance": 400.0,
           "azimuth": 30.0, "elevation": 20.0, "fov": 60.0,
           "ortho": False}
    return {"camera": cam, "vex": 5.0, "checked": ["drift_1"],
            "fly_views": [cam, dict(cam, azimuth=120.0)]}


def test_camera_round_trip():
    cam = _state()["camera"]
    w = sp.camera_to_world(cam, FRAME)
    assert w["center"] == [X0 + 50.0, Y0 + 10.0, -300.0 + 5.0]
    assert w["distance"] == 400.0
    back = sp.camera_from_world(w, FRAME)
    assert np.allclose(back["center"], cam["center"])


def test_pack_and_unpack():
    data = sp.pack(_parts(), _state(), name="Шахта", frame=FRAME,
                   crs="EPSG:32640", wkt="PROJCS[...]", version="1.5.0")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert sorted(z.namelist()) == [sp.GLB_NAME, sp.JSON_NAME]
    meta, glb = sp.unpack(data)
    assert meta["format"] == sp.FORMAT and meta["name"] == "Шахта"
    assert meta["crs"]["authid"] == "EPSG:32640"
    assert meta["vex"] == 5.0
    assert [p["name"] for p in meta["parts"]] == ["Штрек", "Короб"]
    assert [p["node"] for p in meta["parts"]] == [0, 1]
    assert meta["parts"][0]["layer"] == "drift_1"
    assert meta["parts"][1]["kind"] == "lines" and meta["parts"][1]["decor"]
    assert len(meta["views"]) == 2
    assert meta["views"][1]["azimuth"] == 120.0
    assert meta["state"]["checked"] == ["drift_1"]
    json.dumps(meta)


def test_glb_keeps_real_coordinates():
    parts = _parts()
    meta, glb = sp.unpack(sp.pack(parts, _state(), frame=FRAME))
    got, extras = sp.read_glb(glb)
    assert extras["origin"] == meta["origin"]
    assert len(got) == 2
    assert np.abs(got[0]["verts"] - parts[0]["verts"]).max() < 0.01
    assert np.array_equal(got[0]["faces"], parts[0]["faces"])
    assert np.allclose(got[0]["colors"][:, 3], 0.5)
    assert np.array_equal(got[1]["lines"], [[0, 1]])
    vol = sweep.signed_volume(got[0]["verts"], got[0]["faces"])
    assert abs(vol - 1200.0) < 1.0


def test_window_state_follows_a_new_centre():
    """Окно с другим центром ставит камеру туда же в настоящих
    координатах."""
    meta, _glb = sp.unpack(sp.pack(_parts(), _state(), frame=FRAME))
    other = dict(FRAME, cx=X0, vex=2.0)
    st = sp.state_for_window(meta, other)
    w = sp.camera_to_world(st["camera"], other)
    assert np.allclose(w["center"], meta["camera"]["center"])
    assert len(st["fly_views"]) == 2
    assert st["checked"] == ["drift_1"]


def test_newer_format_is_refused():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(sp.JSON_NAME, json.dumps({"format": sp.FORMAT + 1}))
        z.writestr(sp.GLB_NAME, b"")
    with pytest.raises(ValueError):
        sp.unpack(buf.getvalue())


def test_file_round_trip(tmp_path):
    path = str(tmp_path / ("a" + sp.EXT))
    size = sp.write(path, _parts(), _state(), name="A", frame=FRAME)
    assert size == os.path.getsize(path)
    meta, glb = sp.read(path)
    assert meta["name"] == "A" and glb[:4] == b"glTF"
