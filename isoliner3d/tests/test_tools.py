# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Инструменты-объекты (toolspec.py, tools/) без QGIS.

Описание и расчёт инструмента запускаются здесь так же, как их
запустит обёртка Processing или будущий RustGIS: простые данные
на входе, Result на выходе.
"""
import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from isoliner3d import sweep, toolspec  # noqa: E402
from isoliner3d.cleanup import mesh_volume, shell_defects  # noqa: E402
from isoliner3d.tools import TOOLS, by_name  # noqa: E402


def _box(x0, x1, y0, y1, z0, z1):
    prof = sweep.profile("rect", y1 - y0, z1 - z0)
    v, f, _l, _t = sweep.sweep([(x0, (y0 + y1) / 2.0, z0),
                                (x1, (y0 + y1) / 2.0, z0)], prof)
    return {"verts": v, "faces": f}


def test_registry_is_consistent():
    names = [t.name for t in TOOLS]
    assert len(set(names)) == len(names)
    for t in TOOLS:
        assert by_name(t.name) is t
        assert t.code.startswith(t.group + ".")
        for p in t.params:
            assert p.label and p.hint, (t.code, p.key)
            if p.kind == "enum":
                assert p.options and 0 <= p.default < len(p.options)
            if p.kind == "field":
                assert t.param(p.parent).kind in ("lines", "points")
        assert any(p.kind == "sink" for p in t.params), t.code
    with pytest.raises(KeyError):
        by_name("no_such_tool")


def test_description_goes_to_json():
    for t in TOOLS:
        d = json.loads(json.dumps(t.to_dict(), ensure_ascii=False))
        assert d["code"] == t.code
        assert [p["key"] for p in d["params"]] == [p.key for p in t.params]


def test_param_refuses_unknown_kind():
    with pytest.raises(ValueError):
        toolspec.Param("X", "raster", "a", "b")
    with pytest.raises(ValueError):
        toolspec.Tool("9.99", "t", "t", "9", "", [
            toolspec.Param("A", "number", "a", "b"),
            toolspec.Param("A", "number", "a", "b")], None)


def test_fill_half_of_a_box():
    tool = by_name("fill_to_volume")
    vals = tool.defaults()
    vals["SHELL"] = _box(0, 10, 0, 10, -100, -90)
    rep = toolspec.Report()
    out = tool.run(vals, rep)["OUTPUT"]
    (geom, row), = out.features
    mode, level, got, share, full = row
    assert mode == "bottom"
    assert abs(level + 95.0) < 0.05
    assert abs(share - 50.0) < 0.5
    assert abs(full - 1000.0) / 1000.0 < 0.02
    assert shell_defects(geom["verts"], geom["faces"])[0] == 0
    assert abs(abs(mesh_volume(geom["verts"], geom["faces"])) - got) \
        < 0.05 * got
    assert any("Уровень" in text for kind, text in rep.lines)


def test_fill_from_top_in_cubic_metres():
    tool = by_name("fill_to_volume")
    vals = dict(tool.defaults(), SHELL=_box(0, 10, 0, 10, 0, 10),
                MODE=1, UNIT=1, TARGET=200.0)
    row = tool.run(vals, toolspec.Report())["OUTPUT"].features[0][1]
    assert row[0] == "top"
    assert abs(row[1] - 8.0) < 0.05
    assert abs(row[2] - 200.0) < 1.0


def test_fill_refuses_an_open_shell():
    tool = by_name("fill_to_volume")
    box = _box(0, 10, 0, 10, 0, 10)
    box["faces"] = box["faces"][:-2]
    with pytest.raises(toolspec.ToolError) as err:
        tool.run(dict(tool.defaults(), SHELL=box), toolspec.Report())
    assert "не замкнута" in err.value.template


def test_sweep_keeps_source_fields_and_reads_widths():
    tool = by_name("sweep_body")
    lines = [
        {"id": 7, "attrs": {"w": 4.0, "z": -300.0},
         "parts": [np.array([(0, 0, np.nan), (100, 0, np.nan)])]},
        {"id": 8, "attrs": {"w": None},
         "parts": [np.array([(0, 50, -200.0), (50, 50, -200.0)])]},
        {"id": 9, "attrs": {}, "parts": [np.array([(1, 1, 0.0)])]},
    ]
    vals = dict(tool.defaults(), INPUT=lines, PROFILE=1, WIDTH_FIELD="w",
                ELEV_FIELD="z", WIDTH=2.0, HEIGHT=3.0)
    rep = toolspec.Report()
    out = tool.run(vals, rep)["OUTPUT"]
    assert out.keep_source == "INPUT"
    assert [n for n, _t in out.fields] == ["length", "area", "volume",
                                           "closed"]
    (g1, r1), (g2, r2) = out.features
    assert g1["source"] == 7 and g2["source"] == 8
    assert abs(r1[2] - 4.0 * 3.0 * 100.0) < 1e-6 and r1[3] == 1
    assert abs(g1["verts"][:, 2].min() + 300.0) < 1e-9
    assert abs(r2[2] - 2.0 * 3.0 * 50.0) < 1e-6
    assert any(kind == "warn" and "Пропущено" in text
               for kind, text in rep.lines)


def test_sweep_matches_the_module():
    """Обёртка не меняет расчёта: тело то же, что из sweep.py."""
    tool = by_name("sweep_body")
    axis = np.array([(0, 0, -10.0), (40, 0, -12.0), (40, 30, -12.0)])
    vals = dict(tool.defaults(), INPUT=[{"id": 1, "attrs": {},
                                         "parts": [axis]}])
    geom, row = tool.run(vals, toolspec.Report())["OUTPUT"].features[0]
    prof = sweep.profile("arch", 5.0, 3.0, 1.0, 16)
    v, f, length, _t = sweep.sweep(axis, prof, "floor")
    assert np.allclose(geom["verts"], v) and np.array_equal(
        geom["faces"], f)
    assert abs(row[0] - length) < 1e-9


def test_boolean_of_two_overlapping_boxes():
    """2.11: два куба 10 м со сдвигом 5 м. Разность и пересечение
    по 500 м3, объединение 1500 м3, тела замкнуты.

    Ячейка 0.25 м: на ней справка 2.11 обещает ошибку около двух
    с половиной процентов, при 0.5 м она доходит до пяти."""
    tool = by_name("boolean_shells")
    a = _box(0, 10, 0, 10, 0, 10)
    b = _box(5, 15, 0, 10, 0, 10)
    want = {0: ("difference", 500.0), 1: ("union", 1500.0),
            2: ("intersection", 500.0)}
    for op, (name, vol) in want.items():
        vals = dict(tool.defaults(), SHELL_A=a, SHELL_B=b, OP=op,
                    CELL=0.25)
        rep = toolspec.Report()
        out = tool.run(vals, rep)["OUTPUT"]
        assert out.keep_source is None
        assert [n for n, _t in out.fields] == ["body", "op", "volume",
                                               "faces", "closed"]
        (geom, row), = out.features
        assert row[0] == 1 and row[1] == name and row[4] == 1, row
        assert abs(row[2] - vol) / vol < 0.03, (name, row[2])
        assert row[3] == len(geom["faces"])
        assert shell_defects(geom["verts"], geom["faces"])[0] == 0
        assert any("Куб" in text for _k, text in rep.lines)


def test_boolean_refuses_open_shell_and_empty_result():
    tool = by_name("boolean_shells")
    a = _box(0, 10, 0, 10, 0, 10)
    hole = dict(a, faces=a["faces"][:-2])
    with pytest.raises(toolspec.ToolError) as err:
        tool.run(dict(tool.defaults(), SHELL_A=a, SHELL_B=hole),
                 toolspec.Report())
    assert "не замкнута" in err.value.template
    assert err.value.args_[0] == "Второе тело"
    far = _box(50, 60, 0, 10, 0, 10)
    with pytest.raises(toolspec.ToolError) as err:
        tool.run(dict(tool.defaults(), SHELL_A=a, SHELL_B=far, OP=2),
                 toolspec.Report())
    assert "ни одной ячейки" in err.value.template


def test_report_cancel_stops_the_sweep():
    class Stop(toolspec.Report):
        def canceled(self):
            return True
    tool = by_name("sweep_body")
    vals = dict(tool.defaults(), INPUT=[{"id": 1, "attrs": {}, "parts": [
        np.array([(0, 0, 0.0), (10, 0, 0.0)])]}])
    assert tool.run(vals, Stop())["OUTPUT"].features == []


def test_export_has_both_languages():
    """tools.json несёт каждую строку на двух языках.

    Скрипт выгрузки лежит в репозитории, в архиве модуля его нет.
    """
    path = os.path.join(os.path.dirname(__file__), "..", "..", "tools",
                        "export_tools.py")
    if not os.path.isfile(path):
        return
    import importlib.util
    spec = importlib.util.spec_from_file_location("export_tools", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    data = json.loads(json.dumps(mod.build(), ensure_ascii=False))
    assert data["format"] == mod.FORMAT
    assert [t["code"] for t in data["tools"]] == [t.code for t in TOOLS]
    for t in data["tools"]:
        texts = [t["title"], t["help"]]
        for p in t["params"]:
            texts += [p["label"], p["hint"]] + p.get("options", [])
        texts += t["messages"]
        # «Тело» в тексте сообщения и единицы вроде м3 - тоже переводы
        same = [x["ru"] for x in texts if x["ru"] == x["en"]]
        assert not same, (t["code"], same)
