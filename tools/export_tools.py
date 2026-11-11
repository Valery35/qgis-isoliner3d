#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Описания инструментов-объектов в tools.json.

Файл читают приложения без Python: сцена на Rust и RustGIS строят
по нему окно инструмента (поля, подписи, подсказки, справку на двух
языках) и сверяют свои расчёты с кодами и полями модуля. Расчёт
в файл не входит, его переносят на Rust по тексту tools/*.py.

Запуск: python3 tools/export_tools.py [путь]   (без пути - в stdout)
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

FORMAT = 1


def _version():
    path = os.path.join(ROOT, "isoliner3d", "metadata.txt")
    for line in open(path, encoding="utf-8"):
        if line.startswith("version="):
            return line.split("=", 1)[1].strip()
    return "?"


def _both(text, table):
    """Строка на двух языках: русский оригинал и английский перевод."""
    return {"ru": text, "en": table.get(text, text)}


def _messages(tool, spec_texts):
    """Строки N_() из кода расчёта, кроме строк описания: сообщения
    отчёта и ошибок. Их шаблоны в стиле printf (%d, %.1f, %s)."""
    import ast
    import importlib
    mod = importlib.import_module(tool.run.__module__)
    tree = ast.parse(open(mod.__file__, encoding="utf-8").read())
    out = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and getattr(node.func, "id", "") == "N_" and node.args
                and isinstance(node.args[0], ast.Constant)):
            text = node.args[0].value
            if text not in spec_texts and text not in out:
                out.append(text)
    return out


def build():
    """Описание всех инструментов-объектов словарём для JSON."""
    from isoliner3d.i18n import TRANSLATIONS as tr
    from isoliner3d.tools import TOOLS
    tools = []
    for t in TOOLS:
        d = t.to_dict()
        d["title"] = _both(t.title, tr)
        d["help"] = _both(t.help, tr)
        for p, pd in zip(t.params, d["params"]):
            pd["label"] = _both(p.label, tr)
            pd["hint"] = _both(p.hint, tr)
            if p.options:
                pd["options"] = [_both(o, tr) for o in p.options]
        spec_texts = {t.title, t.help}
        for p in t.params:
            spec_texts |= {p.label, p.hint} | set(p.options)
        d["messages"] = [_both(m, tr) for m in _messages(t, spec_texts)]
        tools.append(d)
    return {"format": FORMAT, "module": "isoliner3d",
            "version": _version(), "tools": tools}


def main(argv):
    text = json.dumps(build(), ensure_ascii=False, indent=1) + "\n"
    if len(argv) > 1:
        with open(argv[1], "w", encoding="utf-8") as fh:
            fh.write(text)
        sys.stderr.write("инструментов: %d -> %s\n"
                         % (len(build()["tools"]), argv[1]))
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main(sys.argv)
