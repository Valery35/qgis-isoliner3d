# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Плашка окна сцены сходится с общим списком toolbar.py.

Тот же список Isoliner Scene берёт файлом toolbar.json и рисует свою
плашку теми же значками. Здесь сторона модуля: каждая кнопка плашки
есть в списке, в том же порядке, с тем же значком и подсказкой, а у
каждого значка списка есть рисунок в _tool_icon.

Запуск:  python isoliner3d/tests/test_toolbar.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from isoliner3d import toolbar  # noqa: E402
from isoliner3d.i18n import TRANSLATIONS  # noqa: E402


def _read(name):
    path = os.path.join(os.path.dirname(HERE), name)
    with open(path, encoding="utf-8") as fh:
        src = fh.read().replace("\r\n", "\n")
    # склеить строки, разнесённые по нескольким литералам
    return re.sub(r'"\s*\n\s*"', "", src)


def _tools():
    """Кнопки окна: имя переменной -> (значок, подсказка)."""
    src = _read("viewer_dialog.py")
    out = {}
    for var, kind, tip in re.findall(
            r'(\S+) = tool\(\s*"(\w+)",\s*tr\("([^"]*)"\)', src):
        out[var] = (kind, tip)
    return src, out


def _bar_order():
    src, tools = _tools()
    i = src.index("for b in (btn_params")
    names = src[src.index("(", i) + 1:src.index(")", i)]
    order = ["self.btn"] + [n.strip() for n in names.split(",")
                            if n.strip()]
    return [tools[n] for n in order]


def test_every_bar_button_is_in_the_list_in_order():
    got = _bar_order()
    want = [(b["icon"], b["ru"]) for b in toolbar.buttons()
            if b["where"] != "lite"]
    assert got == want, (got, want)


def test_separator_after_rebuild():
    assert toolbar.ITEMS[0]["key"] == "rebuild"
    assert toolbar.ITEMS[1].get("sep")
    src, _t = _tools()
    i = src.index("tb.addWidget(self.btn)")
    assert src.index("tb.addWidget(sep)", i) < src.index(
        "for b in (btn_params", i)


def test_every_icon_is_drawn():
    src = _read("viewer3d.py")
    for name in toolbar.icons():
        assert 'kind == "%s"' % name in src, name


def test_every_tip_has_english():
    for b in toolbar.buttons():
        assert b["ru"] in TRANSLATIONS, b["key"]
    data = toolbar.as_json()
    for i in data["items"]:
        if not i.get("sep"):
            assert i["en"] != i["ru"] and i["svg"].endswith(".svg")


def test_keys_are_unique_and_marks_are_known():
    keys = [b["key"] for b in toolbar.buttons()]
    assert len(keys) == len(set(keys))
    for b in toolbar.buttons():
        assert b["where"] in ("both", "pro", "lite"), b
        assert b.get("mode") in (None, "draw"), b


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK", name)
            n += 1
    print("all toolbar tests passed (%d)" % n)
