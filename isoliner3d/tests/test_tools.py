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
                picks = p.default if p.multiple else [p.default]
                assert p.options and all(0 <= i < len(p.options)
                                         for i in picks)
            if p.kind == "field":
                assert t.param(p.parent).kind in toolspec.SOURCE_KINDS
            if p.kind == "band":
                assert t.param(p.parent).kind == "raster"
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
        toolspec.Param("X", "grid", "a", "b")
    with pytest.raises(ValueError):
        # канал без растра-родителя
        toolspec.Tool("9.99", "t", "t", "9", "", [
            toolspec.Param("A", "number", "a", "b"),
            toolspec.Param("B", "band", "a", "b", parent="A")], None)
    with pytest.raises(ValueError):
        toolspec.Result([], geometry="points")
    with pytest.raises(ValueError):
        toolspec.Result([], geometry="source")      # без keep_source
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


def _select_input():
    """Объекты для 2.12 вокруг куба 0..10 м."""
    def feat(i, parts, **attrs):
        return {"id": i, "attrs": attrs,
                "parts": [np.asarray(p, dtype=float).reshape(-1, 3)
                          for p in parts]}
    return [
        feat(1, [[(5, 5, 5)]], vol=8.0, g=2.0),          # точка внутри
        feat(2, [[(20, 5, 5)]], vol=8.0, g=9.0),         # точка снаружи
        feat(3, [[(-5, 5, 5), (15, 5, 5)]], vol=None),   # прошивает куб
        feat(4, [[(2, 2, 2), (8, 8, 8)]], vol=4.0, g=5.0),  # внутри
        feat(5, [[(5, 5, np.nan)]], vol=1.0),            # без Z
    ]


def test_select_by_shell_modes_and_step():
    """2.12: целиком внутри, пересекает, снаружи, с шагом и без."""
    tool = by_name("select_by_shell")
    shell = _box(0, 10, 0, 10, 0, 10)

    def run(mode, step):
        vals = dict(tool.defaults(), INPUT=_select_input(), SHELL=shell,
                    MODE=mode, STEP=step)
        out = tool.run(vals, toolspec.Report())["OUTPUT"]
        assert out.geometry == "source" and out.keep_source == "INPUT"
        assert out.fields == []
        assert all(row == [] for _g, row in out.features)
        return [g["source"] for g, _row in out.features]
    assert run(0, 0.0) == [1, 4]
    assert run(1, 0.0) == [1, 4]
    assert run(1, 1.0) == [1, 3, 4]
    assert run(2, 0.0) == [2, 3]
    assert run(2, 1.0) == [2]


def test_select_by_shell_summary():
    """Объём, взвешенное содержание и тоннаж отобранного в журнале."""
    tool = by_name("select_by_shell")
    vals = dict(tool.defaults(), INPUT=_select_input(),
                SHELL=_box(0, 10, 0, 10, 0, 10), VOLUME="vol", GRADE="g",
                DENSITY=2.5)
    rep = toolspec.Report()
    tool.run(vals, rep)
    text = "\n".join(t for _k, t in rep.lines)
    assert "Объектов 4, точек опроса 6." in text
    assert "отобрано 2 (50.0 процента)" in text
    assert "Объём отобранного: 12.0 м3." in text
    assert "взвешенное по объёму: 3.000." in text      # (8*2+4*5)/12
    assert "Тоннаж руды: 30 т." in text
    assert "Тоннаж металла: 1 т." in text            # 30 * 3 / 100


def test_select_by_shell_refusals():
    tool = by_name("select_by_shell")
    box = _box(0, 10, 0, 10, 0, 10)
    with pytest.raises(toolspec.ToolError) as err:
        tool.run(dict(tool.defaults(), INPUT=_select_input(),
                      SHELL=dict(box, faces=box["faces"][:-2])),
                 toolspec.Report())
    assert "не замкнута" in err.value.template
    flat = [{"id": 1, "attrs": {}, "parts": [np.array([[1, 1, np.nan]])]}]
    with pytest.raises(toolspec.ToolError) as err:
        tool.run(dict(tool.defaults(), INPUT=flat, SHELL=box),
                 toolspec.Report())
    assert "с высотой" in err.value.template


def _zonal_values(**kw):
    """Входы 2.14: тела A (0..10), B (20..30) и открытое C."""
    tool = by_name("zonal_shell_stats")
    a = _box(0, 10, 0, 10, 0, 10)
    b = _box(20, 30, 0, 10, 0, 10)
    c = _box(40, 50, 0, 10, 0, 10)
    c["faces"] = c["faces"][:-2]
    shells = [dict(m, id=i, attrs={"name": nm, "old_n": 7})
              for i, nm, m in ((11, "A", a), (12, "B", b), (13, "C", c))]

    def pt(i, xyz, val):
        return {"id": i, "attrs": {"au": val},
                "parts": [np.array([xyz], dtype=float)]}
    points = [pt(1, (5, 5, 5), 2.0), pt(2, (6, 6, 6), 4.0),
              pt(3, (25, 5, 5), 10.0), pt(4, (60, 0, 0), None),
              pt(5, (5, 5, np.nan), 1.0)]
    vals = dict(tool.defaults(), SHELLS=shells, INPUT=points)
    vals["@SHELLS"] = {"name": "Тела", "geometry": "polygon",
                       "fields": ["name", "old_n"]}
    vals["@INPUT"] = {"name": "Пробы Au", "geometry": "point",
                      "fields": ["au"]}
    vals.update(kw)
    return tool, vals


def test_zonal_counts_points_and_stats():
    tool, vals = _zonal_values(ATTR="au", STATS=[0, 1],
                               OUTPUT_OBJECTS=True, ZONE_FIELD="name")
    rep = toolspec.Report()
    res = tool.run(vals, rep)
    out = res["OUTPUT"]
    assert out.keep_source == "SHELLS" and out.geometry == "source"
    # имя полей от имени слоя латиницей
    assert [n for n, _t in out.fields] == ["proby_au_n", "proby_au_sum",
                                           "proby_au_mean"]
    rows = {g["source"]: row for g, row in out.features}
    assert rows[11] == {"proby_au_n": 2, "proby_au_sum": 6.0,
                        "proby_au_mean": 3.0}
    assert rows[12]["proby_au_n"] == 1 and rows[12]["proby_au_sum"] == 10.0
    assert rows[13] == {}            # незамкнутое тело - пусто, не ноль
    assert any(k == "warn" and "Незамкнутых тел 1" in t
               for k, t in rep.lines)
    objs = res["OUTPUT_OBJECTS"]
    assert [n for n, _t in objs.fields] == ["zone", "zone_ids", "zone_n"]
    zone = {g["source"]: row for g, row in objs.features}
    assert zone[1] == ["A", "A", 1] and zone[3] == ["B", "B", 1]
    assert zone[4] == [None, None, 0] and 5 not in zone
    text = "\n".join(t for _k, t in rep.lines)
    assert "Объектов в телах: 3 из 4." in text
    assert "Попаданий по всем телам: 3." in text


def test_zonal_lines_cut_by_the_body():
    tool, vals = _zonal_values()
    vals["INPUT"] = [{"id": 1, "attrs": {},
                      "parts": [np.array([(-5, 5, 5), (15, 5, 5.0)])]}]
    vals["@INPUT"] = {"name": "Борозды", "geometry": "line", "fields": []}
    rep = toolspec.Report()
    res = tool.run(vals, rep)
    rows = {g["source"]: row for g, row in res["OUTPUT"].features}
    assert rows[11]["borozdy_n"] == 1
    assert abs(rows[11]["borozdy_len"] - 10.0) < 1e-6
    assert rows[12] == {"borozdy_n": 0, "borozdy_len": 0.0}
    assert "OUTPUT_OBJECTS" not in res      # второй выход не заказан
    assert any("всего 20.00 м, внутри тел 10.00 м" in t
               for _k, t in rep.lines)


def test_zonal_refuses_a_name_clash_unless_allowed():
    tool, vals = _zonal_values(NAME="old")
    vals["@SHELLS"]["fields"].append("old_n")
    with pytest.raises(toolspec.ToolError) as err:
        tool.run(vals, toolspec.Report())
    assert "уже есть" in err.value.template
    vals["OVERWRITE"] = True
    out = tool.run(vals, toolspec.Report())["OUTPUT"]
    assert out.replace
    rows = {g["source"]: row for g, row in out.features}
    assert rows[11] == {"old_n": 2}


def _desurvey_values(**kw):
    tool = by_name("desurvey_holes")
    collars = [
        {"id": 1, "xyz": None, "attrs": {"hole": " H1", "x": 100.0,
                                         "y": 200.0, "z": 50.0,
                                         "eoh": 120.0}},
        {"id": 2, "xyz": None, "attrs": {"hole": "H2", "x": 150.0,
                                         "y": 200.0, "z": 48.0,
                                         "eoh": 80.0}},
        {"id": 3, "xyz": None, "attrs": {"hole": "H3", "x": 1.0, "y": 1.0,
                                         "z": 0.0, "eoh": None}},
        {"id": 4, "xyz": None, "attrs": {"hole": None, "x": 1.0,
                                         "y": 1.0}},
    ]
    survey = [
        {"id": 10, "xyz": None, "attrs": {"hole": "H1", "depth": 0.0,
                                          "azimuth": 45.0, "dip": -60.0}},
        {"id": 11, "xyz": None, "attrs": {"hole": "H1", "depth": 60.0,
                                          "azimuth": 50.0, "dip": -55.0}},
        {"id": 12, "xyz": None, "attrs": {"hole": "H1", "depth": 100.0,
                                          "azimuth": "x", "dip": -50.0}},
        {"id": 13, "xyz": None, "attrs": {"hole": "LOST", "depth": 0.0,
                                          "azimuth": 0.0, "dip": -90.0}},
    ]
    vals = dict(tool.defaults(), COLLARS=collars, SURVEY=survey)
    vals["@COLLARS"] = {"name": "collars", "geometry": "none",
                        "hasz": False,
                        "fields": ["hole", "x", "y", "z", "eoh"]}
    vals["@SURVEY"] = {"name": "survey", "geometry": "none",
                       "hasz": False,
                       "fields": ["hole", "depth", "azimuth", "dip"]}
    vals.update(kw)
    return tool, vals


def test_desurvey_matches_the_module():
    """2.17: ствол тот же, что из wells.py, поля и предупреждения."""
    from isoliner3d import wells
    tool, vals = _desurvey_values()
    rep = toolspec.Report()
    out = tool.run(vals, rep)["OUTPUT"]
    assert out.geometry == "line" and out.keep_source is None
    assert [n for n, _t in out.fields] == ["hole", "eoh", "n_survey"]
    (g1, r1), (g2, r2) = out.features
    sd, sa, sg = wells.with_collar([0.0, 60.0], [45.0, 50.0],
                                   [-60.0, -55.0], None, None)
    pts, mds = wells.desurvey((100.0, 200.0, 50.0), sd, sa, sg,
                              max_depth=120.0, step=1.0)
    assert np.allclose(g1["points"], pts)
    assert r1 == ["H1", float(mds[-1]), 2]
    assert np.allclose(g2["points"][-1], (150.0, 200.0, -32.0))
    assert r2 == ["H2", 80.0, 0]
    text = "\n".join("%s %s" % kt for kt in rep.lines)
    assert "warn Строк инклинометрии с пустыми или нечисловыми " \
        "значениями: 1" in text
    assert "Стволов: 2." in text
    assert "Скважин без инклинометрии: 2." in text
    assert "Пропущено устьев: 2" in text
    assert "Инклинометрия без устья: 1 скважин, например LOST." in text
    assert "X x, Y y, Z z." in text


def test_desurvey_takes_points_with_z():
    """Устья точками: координаты и отметка из геометрии."""
    tool, vals = _desurvey_values(SURVEY=None)
    vals["COLLARS"] = [
        {"id": 1, "xyz": np.array([5.0, 6.0, 70.0]),
         "attrs": {"hole": "P1", "eoh": 10.0}},
        {"id": 2, "xyz": np.array([9.0, 6.0, np.nan]),
         "attrs": {"hole": "P2", "eoh": 10.0}},
    ]
    vals["@COLLARS"] = {"name": "c", "geometry": "point", "hasz": True,
                        "fields": ["hole", "eoh"]}
    del vals["@SURVEY"]
    rep = toolspec.Report()
    out = tool.run(vals, rep)["OUTPUT"]
    (g1, _r1), (g2, _r2) = out.features
    assert np.allclose(g1["points"][0], (5, 6, 70))
    assert np.allclose(g1["points"][-1], (5, 6, 60))
    assert np.allclose(g2["points"][0], (9, 6, 0))      # без Z - на ноль
    assert any(k == "warn" and "Устьев без отметки: 1" in t
               for k, t in rep.lines)


def test_desurvey_refusals():
    tool, vals = _desurvey_values()
    vals["@COLLARS"]["fields"] = ["name", "x", "y"]
    with pytest.raises(toolspec.ToolError) as err:
        tool.run(vals, toolspec.Report())
    assert "номера скважины" in err.value.template
    tool, vals = _desurvey_values()
    vals["@SURVEY"]["fields"] = ["hole", "depth"]
    with pytest.raises(toolspec.ToolError) as err:
        tool.run(vals, toolspec.Report())
    assert "не выбраны поля" in err.value.template


def _intervals_values(**kw):
    tool = by_name("hole_intervals")
    traces = [
        {"id": 1, "attrs": {"hole": "H1"},
         "parts": [np.array([(0, 0, 0.0), (0, 0, -100.0)])]},
        {"id": 2, "attrs": {"hole": "H2"},
         "parts": [np.array([(10, 0, 0.0), (10, 0, -50.0)])]},
        {"id": 3, "attrs": {"hole": "H3"},
         "parts": [np.array([(20, 0, np.nan), (20, 5, np.nan)])]},
    ]

    def row(i, hole, a, b, au, lith):
        return {"id": i, "xyz": None,
                "attrs": {"hole": hole, "from_m": a, "to_m": b, "au": au,
                          "lith": lith}}
    table = [row(1, "H1", 0.0, 10.0, 1.5, "A"),
             row(2, "H1", 10.0, 30.0, 3.0, "B"),
             row(3, "H1", 90.0, 105.0, 0.5, "C"),
             row(4, "H2", 5.0, 5.0, 9.0, "D"),
             row(5, "LOST", 0.0, 1.0, 1.0, "E")]
    vals = dict(tool.defaults(), TRACES=traces, TABLE=table)
    vals["@TRACES"] = {"name": "t", "geometry": "line", "hasz": True,
                       "fields": ["hole"]}
    vals["@TABLE"] = {"name": "assay", "geometry": "none", "hasz": False,
                      "fields": ["hole", "from_m", "to_m", "au", "lith"],
                      "numeric": ["from_m", "to_m", "au"]}
    vals.update(kw)
    return tool, vals


def test_intervals_from_the_table():
    """2.18 из таблицы: поля таблицы переходят, забой режет."""
    tool, vals = _intervals_values(MODE=0)
    rep = toolspec.Report()
    res = tool.run(vals, rep)
    out, pts = res["OUTPUT"], res["OUTPUT_POINTS"]
    assert out.geometry == "line" and pts.geometry == "point"
    assert out.fields == pts.fields == [
        ("hole", "string"), ("from_m", "double"), ("to_m", "double"),
        ("length_m", "double"), ("au", "copy:TABLE"),
        ("lith", "copy:TABLE")]
    rows = [r for _g, r in out.features]
    assert rows == [["H1", 0.0, 10.0, 10.0, 1.5, "A"],
                    ["H1", 10.0, 30.0, 20.0, 3.0, "B"],
                    ["H1", 90.0, 100.0, 10.0, 0.5, "C"]]
    assert np.allclose(pts.features[0][0]["xyz"], (0, 0, -5))
    assert np.allclose(out.features[2][0]["points"][-1], (0, 0, -100))
    text = "\n".join(t for _k, t in rep.lines)
    assert "Поля таблицы: скважина hole, от from_m, до to_m." in text
    assert "Стволов: 2, интервалов: 3." in text
    assert "с концом не дальше начала: 1" in text
    assert "Интервалов глубже забоя: 1." in text
    assert "Интервалы без ствола: 1 скважин, например LOST." in text


def test_intervals_equal_and_composites():
    tool, vals = _intervals_values(MODE=1, LENGTH=25.0, TABLE=None)
    del vals["@TABLE"]
    out = tool.run(vals, toolspec.Report())["OUTPUT"]
    assert [r[1:3] for _g, r in out.features] == [
        [0.0, 25.0], [25.0, 50.0], [50.0, 75.0], [75.0, 100.0],
        [0.0, 25.0], [25.0, 50.0]]
    tool, vals = _intervals_values(MODE=2, LENGTH=20.0)
    out = tool.run(vals, toolspec.Report())["OUTPUT"]
    assert [n for n, _t in out.fields][4:] == ["au", "cover"]
    rows = [r for _g, r in out.features]
    assert rows[0][:4] == ["H1", 0.0, 20.0, 20.0]
    assert abs(rows[0][4] - 2.25) < 1e-9 and rows[0][5] == 1.0
    assert rows[1][4] == 3.0 and abs(rows[1][5] - 0.5) < 1e-9
    assert len(rows) == 3          # пустые композиты 40-80 м не пишутся
    tool, vals = _intervals_values(MODE=2, LENGTH=20.0, VALUES=["au"])
    assert len(tool.run(vals, toolspec.Report())["OUTPUT"].features) == 3


def test_intervals_refusals():
    tool, vals = _intervals_values(MODE=0, TABLE=None)
    del vals["@TABLE"]
    with pytest.raises(toolspec.ToolError) as err:
        tool.run(vals, toolspec.Report())
    assert "нужна таблица" in err.value.template
    tool, vals = _intervals_values(MODE=1)
    vals["@TRACES"]["fields"] = ["name"]
    with pytest.raises(toolspec.ToolError) as err:
        tool.run(vals, toolspec.Report())
    assert "номера скважины в стволах" in err.value.template


def test_grid_reads_bands_on_demand():
    """Grid: каналы с единицы, ленивое чтение, проверки формы."""
    asked = []

    def read(b):
        asked.append(b)
        return np.full((2, 3), float(b))
    g = toolspec.Grid(read=read, count=3, shape=(2, 3),
                      transform=(100, 10, 0, 500, 0, -10),
                      names=["a", "b", "c"])
    assert (g.width, g.height, g.count) == (3, 2, 3)
    assert g.band(2)[0, 0] == 2.0 and asked == [2]
    g.band(2)
    assert asked == [2]                      # второй раз из памяти
    with pytest.raises(IndexError):
        g.band(4)
    with pytest.raises(IndexError):
        g.band(0)
    with pytest.raises(ValueError):
        toolspec.Grid([np.zeros((2, 2)), np.zeros((3, 2))])
    with pytest.raises(ValueError):
        toolspec.Grid([np.zeros((2, 2))], names=["a", "b"])
    with pytest.raises(ValueError):
        toolspec.Grid()
    with pytest.raises(ValueError):
        toolspec.RasterResult(np.zeros((2, 2)))
    res = toolspec.RasterResult(toolspec.Grid([np.zeros((2, 2))]), "x")
    assert res.geometry == "raster" and res.grid.count == 1


def _bed_grid(nx=8, ny=6, cell=10.0, top=-100.0, thick=5.0):
    """Плоский пласт: кровля top, подошва на thick ниже, второй
    пласт каналами 3 и 4 ещё на 20 м ниже."""
    t = np.full((ny, nx), top)
    b = t - thick
    return toolspec.Grid([t, b, t - 20.0, b - 20.0 - thick],
                         transform=(1000.0, cell, 0.0, 2000.0, 0.0, -cell))


def test_grid_to_shell_volume_of_a_flat_bed():
    """2.13: плоский пласт 8 x 6 ячеек по 10 м, мощность 5 м.

    Оболочка идёт по центрам ячеек: 70 x 50 м, объём 17500 м3."""
    tool = by_name("grid_to_shell")
    vals = dict(tool.defaults(), INPUT=_bed_grid())
    rep = toolspec.Report()
    out = tool.run(vals, rep)["OUTPUT"]
    assert out.geometry == "mesh" and out.keep_source is None
    assert [n for n, _t in out.fields] == ["body", "band", "volume",
                                           "faces", "closed"]
    (geom, row), = out.features
    assert row[0] == 1 and row[1] == 1 and row[4] == 1
    assert abs(abs(row[2]) - 70 * 50 * 5.0) < 1e-6
    assert row[3] == len(geom["faces"])
    assert shell_defects(geom["verts"], geom["faces"])[0] == 0
    assert abs(geom["verts"][:, 2].max() + 100.0) < 1e-9
    text = "\n".join(t for _k, t in rep.lines)
    assert "Мощность: 5.00 .. 5.00 м." in text
    assert "Тел: 1, объём всего" in text
    # второй пласт: каналы 3 и 4, мощность 10 м
    out = tool.run(dict(vals, BAND=3), toolspec.Report())["OUTPUT"]
    (_g, row), = out.features
    assert row[1] == 3 and abs(abs(row[2]) - 70 * 50 * 10.0) < 1e-6


def test_grid_to_shell_two_bodies_and_negative_thickness():
    tool = by_name("grid_to_shell")
    g = _bed_grid(nx=9)
    top, bot = g.band(1).copy(), g.band(2).copy()
    top[:, 4] = np.nan                     # пустой столбец делит тело
    bot[0, 0] = top[0, 0] + 1.0            # подошва выше кровли
    rep = toolspec.Report()
    out = tool.run(dict(tool.defaults(), INPUT=toolspec.Grid(
        [top, bot], transform=g.transform)), rep)["OUTPUT"]
    assert len(out.features) == 2
    assert [r[0] for _g, r in out.features] == [1, 2]
    assert any(k == "warn" and "таких ячеек 1" in t for k, t in rep.lines)


def test_grid_to_shell_refusals():
    tool = by_name("grid_to_shell")
    g = _bed_grid()
    with pytest.raises(toolspec.ToolError) as err:
        tool.run(dict(tool.defaults(), INPUT=g, BAND=4), toolspec.Report())
    assert "нет канала подошвы" in err.value.template
    assert err.value.args_ == (4,)
    empty = toolspec.Grid([np.full((3, 3), np.nan)] * 2)
    with pytest.raises(toolspec.ToolError) as err:
        tool.run(dict(tool.defaults(), INPUT=empty), toolspec.Report())
    assert "нигде не считается" in err.value.template


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
