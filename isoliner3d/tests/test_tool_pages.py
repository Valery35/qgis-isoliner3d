# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Страницы инструментов (tools/tool_pages.py) и руководство.

Разделы инструментов-объектов в manual.md и manual_en.md собираются
из тех же страниц, что уходят в RustGIS. Руками поправленный раздел
разошёлся бы с RustGIS молча, проверка это ловит.

Сборщик и руководство лежат в корне хранилища, в рабочем архиве
модуля их нет: там проверки пропускаются.

Запуск:  python isoliner3d/tests/test_tool_pages.py
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
GEN = os.path.join(ROOT, "tools", "tool_pages.py")


def _gen():
    spec = importlib.util.spec_from_file_location("tool_pages", GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tool(code="2.24"):
    return {"code": code, "name": "x", "group": "2",
            "title": {"ru": "Тело", "en": "Body"},
            "help": {"ru": "Первый.\n\nВторой.", "en": "One.\n\nTwo."},
            "params": [{"label": {"ru": "Ось", "en": "Axis"},
                        "hint": {"ru": "Линия.", "en": "A line."}}]}


def test_page_has_heading_help_and_table():
    if not os.path.isfile(GEN):
        return
    text = _gen().page(_tool(), "en")
    assert text == ("## 2.24 Body\n\nOne.\n\nTwo.\n\n"
                    "| Field | What it sets |\n|---|---|\n"
                    "| **Axis** | A line. |\n"), text


def test_sync_keeps_the_handwritten_part():
    if not os.path.isfile(GEN):
        return
    tp = _gen()
    data = {"tools": [_tool()]}
    man = ("# Tools\r\n\r\n## 2.24 Old\r\n\r\nold text\r\n\r\n"
           "### How to use\r\n\r\nby hand\r\n\r\n# Neighbouring plugins"
           "\r\n")
    got = tp.sync(man, "en", data, "<!-- c -->\n# Isoliner3D in RustGIS\n")
    assert "old text" not in got
    assert "### How to use\r\n\r\nby hand" in got
    assert "\n" not in got.replace("\r\n", "")
    assert got.index(tp.BEGIN) < got.index("# Neighbouring plugins")
    assert "<!-- c -->" not in got
    # второй прогон ничего не меняет, глава не задваивается
    assert tp.sync(got, "en", data, "# Isoliner3D in RustGIS\n") == got


def test_missing_section_is_an_error():
    if not os.path.isfile(GEN):
        return
    try:
        _gen().sync("# Tools\n", "ru", {"tools": [_tool()]})
    except ValueError:
        return
    raise AssertionError("раздел без заголовка прошёл молча")


def test_manual_matches_the_pages():
    if not os.path.isfile(GEN):
        return
    tp = _gen()
    if not all(os.path.isfile(p) for p in tp.MANUALS.values()):
        return
    bad = tp.stale(tp.load())
    assert not bad, ("разделы инструментов в руководстве (%s) разошлись "
                     "со страницами: python tools/tool_pages.py --manual"
                     % ", ".join(bad))


def test_rustgis_chapter_is_in_both_manuals():
    if not os.path.isfile(GEN):
        return
    tp = _gen()
    for path in tp.MANUALS.values():
        if not os.path.isfile(path):
            continue
        text = open(path, encoding="utf-8").read()
        assert text.count(tp.BEGIN) == 1 and text.count(tp.END) == 1, path


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
