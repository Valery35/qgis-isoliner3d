# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Окно «Параметры сцены» сходится с общим списком scene_params.py.

Тот же список Isoliner Scene берёт файлом scene_params.json и сверяет
своё окно. Здесь проверяется сторона модуля: вкладки и группы в том
же порядке, у каждого поля есть подпись в окне и ключ в состоянии
сцены, английские подписи те же, что в таблице переводов.

Запуск:  python isoliner3d/tests/test_scene_params.py
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from isoliner3d import scene_params as sp  # noqa: E402
from isoliner3d.i18n import TRANSLATIONS  # noqa: E402


def _dialog():
    path = os.path.join(os.path.dirname(HERE), "viewer_dialog.py")
    with open(path, encoding="utf-8") as fh:
        return fh.read().replace("\r\n", "\n")


def _module_side(p):
    return p["where"] != "lite"


def test_tabs_follow_the_list():
    src = _dialog()
    tabs = re.findall(r'self\.scene_box\.addTab\(\w+, tr\("([^"]+)"\)\)',
                      src)
    assert tabs == [g["ru"] for g in sp.GROUPS], tabs


def test_sections_are_groups_of_the_window():
    src = _dialog()
    for g in sp.GROUPS:
        for s in g["sections"]:
            if s["ru"]:
                assert 'QGroupBox(tr("%s"))' % s["ru"] in src, s["ru"]


def test_every_field_has_a_label_in_the_window():
    src = _dialog()
    for p in sp.params():
        if not _module_side(p) or p["kind"] == "float6":
            continue
        assert 'tr("%s")' % p["ru"] in src, p["key"]
        for c in p.get("choices", []):
            assert 'tr("%s")' % c["ru"] in src, (p["key"], c["value"])


def test_every_stored_key_is_in_the_scene_state():
    src = _dialog()
    i = src.index("def _state_dict(self)")
    state = src[i:src.index("return state", i)]
    j = src.index("def _camera_state(self)")
    cam = src[j:src.index("def _camera_apply", j)]
    for key in sp.stored_keys():
        if key.startswith("camera."):
            assert '"%s"' % key.split(".", 1)[1] in cam, key
        else:
            assert '"%s":' % key in state, key


def test_english_labels_match_the_translations():
    for p in sp.params():
        if p["ru"] in TRANSLATIONS:
            assert p["en"] == TRANSLATIONS[p["ru"]], (p["key"], p["en"])
        for c in p.get("choices", []):
            if c["ru"] in TRANSLATIONS:
                assert c["en"] == TRANSLATIONS[c["ru"]], c
    for g in sp.GROUPS:
        if g["ru"] in TRANSLATIONS:
            assert g["en"] == TRANSLATIONS[g["ru"]], g["ru"]


def test_row_with_matches_the_window():
    """Поле row_with стоит в одной строке с полем в той же секции.

    В модуле галка подписей к ближним рёбрам - вторая половина строки
    «Рёбра», поэтому и подпись у неё со строчной.
    """
    src = _dialog()
    for g in sp.GROUPS:
        for s in g["sections"]:
            keys = [p["key"] for p in s["params"]]
            for p in s["params"]:
                if "row_with" in p:
                    assert p["row_with"] in keys, p["key"]
    assert "self._pair(self.box_edge_mode," in src
    near = [p for p in sp.params() if p["key"] == "box_near"][0]
    assert near["row_with"] == "box_edges"


def test_keys_are_unique_and_json_is_plain():
    keys = [p["key"] for p in sp.params()]
    assert len(keys) == len(set(keys))
    data = json.loads(json.dumps(sp.as_json(), ensure_ascii=False))
    assert data["version"] == sp.VERSION
    assert [g["id"] for g in data["groups"]] == \
        ["view", "look", "box", "clip"]


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK", name)
            n += 1
    print("all scene-params tests passed (%d)" % n)
