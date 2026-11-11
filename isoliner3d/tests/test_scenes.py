# -*- coding: utf-8 -*-
"""Несколько сцен в проекте и перенос из другого проекта (scenes.py).

Просьба Ивана: именованные сцены и импорт сцен из другого проекта
QGIS. Сцена ссылается на слои по id, при переносе id переводятся.
"""

import io
import json
import os
import sys
import zipfile
import pytest

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import scenes                   # noqa: E402

LID_A = "bodies_8518c8ab_5438_45fc_879a_c1c5331bb52b"
LID_B = "holes_c07868ff_20a0_45c4_931c_9c4e82bab609"


def _qgs(entries, layers):
    props = "".join('<%s type="QString">%s</%s>' % (
        k, v.replace("&", "&amp;").replace("<", "&lt;"), k)
        for k, v in entries.items())
    mls = "".join(
        '<maplayer type="vector"><id>%s</id><datasource>%s</datasource>'
        '<layername>%s</layername><provider encoding="UTF-8">ogr'
        '</provider></maplayer>' % (lid, src, name)
        for lid, src, name in layers)
    return ('<qgis version="4.0.3"><projectlayers>%s</projectlayers>'
            '<properties><Isoliner3D>%s</Isoliner3D></properties></qgis>'
            % (mls, props))


def test_unique_name():
    assert scenes.unique_name("Разрез", set()) == "Разрез"
    assert scenes.unique_name("Разрез", {"Разрез"}) == "Разрез (2)"
    assert scenes.unique_name("Разрез", {"Разрез", "Разрез (2)"}) \
        == "Разрез (3)"
    assert scenes.unique_name("  ", set()) == scenes.DEFAULT_NAME


def test_parse_named_scenes_and_layers():
    st = {"checked": [LID_A], "opts": {LID_A: {"color": "#fff"}}}
    xml = _qgs({"scenes": json.dumps({"Общий вид": st, "Разрез": st}),
                "scene": "Разрез"},
               [(LID_A, "./data/тела.gpkg|layername=b", "Тела"),
                (LID_B, "./data/скв.gpkg", "Скважины")])
    got, cur, layers = scenes.parse_project(xml)
    assert sorted(got) == ["Общий вид", "Разрез"] and cur == "Разрез"
    assert layers[LID_A]["name"] == "Тела"
    assert layers[LID_B]["provider"] == "ogr"


def test_old_project_has_one_scene():
    st = {"checked": [LID_B]}
    got, cur, _l = scenes.parse_project(
        _qgs({"state": json.dumps(st)}, []))
    assert got == {scenes.DEFAULT_NAME: st}
    assert cur == scenes.DEFAULT_NAME


def test_qgz_is_read(tmp_path):
    xml = _qgs({"state": json.dumps({"checked": []})}, [])
    p = tmp_path / "p.qgz"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("p.qgs", xml)
        z.writestr("p.qgd", b"")
    assert "Isoliner3D" in scenes.read_project_xml(str(p))


def test_match_by_source_then_id_then_name(tmp_path):
    src = {LID_A: {"name": "Тела", "provider": "ogr", "type": "vector",
                   "source": "./data/тела.gpkg|layername=b"},
           LID_B: {"name": "Скважины", "provider": "ogr",
                   "type": "vector", "source": "./data/скв.gpkg"},
           "x_1": {"name": "Пропавший", "provider": "ogr",
                   "type": "vector", "source": "./data/нет.gpkg"}}
    pdir = str(tmp_path)
    here = {"new_bodies": {"name": "Другое имя", "source": os.path.join(
                pdir, "data", "тела.gpkg") + "|layername=b"},
            "new_holes": {"name": "Скважины", "source": "/elsewhere.gpkg"}}
    mapping, missing = scenes.match_layers(
        {LID_A, LID_B, "x_1"}, src, here, pdir)
    assert mapping == {LID_A: "new_bodies", LID_B: "new_holes"}
    assert missing == ["x_1"]


def test_remap_replaces_ids_everywhere():
    st = {"checked": [LID_A, LID_B], "opts": {LID_A: {"tex": LID_B}},
          "clip": LID_B, "vex": 5.0, "path": [[1.0, 2.0]]}
    out = scenes.remap(st, {LID_A: "a2", LID_B: "b2"})
    assert out["checked"] == ["a2", "b2"]
    assert out["opts"] == {"a2": {"tex": "b2"}}
    assert out["clip"] == "b2" and out["vex"] == 5.0
    assert LID_A in scenes.collect_ids(st)


def test_qgis4_property_layout():
    st = {"checked": [LID_A]}
    xml = ('<qgis><properties><properties name="Gui"/>'
           '<properties name="Isoliner3D">'
           '<properties name="scene" type="QString">Разрез</properties>'
           '<properties name="scenes" type="QString">%s</properties>'
           '</properties></properties></qgis>'
           % json.dumps({"Разрез": st}).replace("&", "&amp;"))
    got, cur, _l = scenes.parse_project(xml)
    assert got == {"Разрез": st} and cur == "Разрез"


def test_project_with_doctype_is_read():
    """Настоящий проект QGIS начинается с <!DOCTYPE qgis ...>."""
    xml = _qgs({"scene": "А", "scenes": json.dumps({"А": {}})}, [])
    head = "<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>\n"
    got, cur, _l = scenes.parse_project(head + xml.split("?>", 1)[-1]
                                        if xml.startswith("<?xml")
                                        else head + xml)
    assert cur == "А" and "А" in got


def test_entities_are_refused():
    """Объявления сущностей - ловушка для разборщика, не проект.

    Сканер каталога (bandit B314) требует защиты от раздувания
    сущностей: без неё такой файл съел бы память QGIS.
    """
    bomb = ('<?xml version="1.0"?>\n<!DOCTYPE q [<!ENTITY a "aaaaaaaa">'
            '<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;">]>\n'
            '<qgis><properties/><title>&b;</title></qgis>')
    with pytest.raises(Exception):
        scenes.parse_project(bomb)


def test_scanner_sees_the_guard():
    """Разбор XML помечен для сканера, сырого ET.fromstring нет."""
    import os
    src = open(os.path.join(os.path.dirname(__file__), "..",
                            "scenes.py"), encoding="utf-8").read()
    assert "ET.fromstring" not in src
    assert "import xml.etree.ElementTree as ET" not in src
    for line in src.splitlines():
        if "xml.etree" in line and "import" in line:
            assert "# nosec" in line, line
        if "_std_fromstring(" in line and "import" not in line:
            assert "# nosec" in line, line
