# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Покрытие таблицы переводов: у каждой строки в tr() есть английский.

Запуск:  python isoliner3d/tests/test_i18n.py
QGIS не требуется: i18n.py не импортирует QGIS на верхнем уровне, а строки
из кода извлекаются разбором AST, без выполнения модулей.
"""
import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import i18n  # noqa: E402

SOURCES = ("viewer3d.py", "plugin.py", "i18n.py",
           "algorithms.py", "provider.py", "texmesh.py",
           "demo_map.py")


def _tr_strings(path):
    """Все строковые литералы, обёрнутые в tr() или _tr() в файле."""
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    out = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = getattr(fn, "id", None) or getattr(fn, "attr", None)
        if name not in ("tr", "_tr") or not node.args:
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            out.add(arg.value)
    return out


def collect():
    keys = set()
    for name in SOURCES:
        path = os.path.join(PKG, name)
        if os.path.isfile(path):
            keys |= _tr_strings(path)
    return keys


def test_every_string_has_translation():
    keys = collect()
    assert keys, "ни одной строки в tr() не найдено - сломался разбор"
    missing = i18n.missing_keys(keys)
    assert not missing, (
        "нет английского перевода для %d строк:\n  %s"
        % (len(missing), "\n  ".join(sorted(missing))))


def test_no_empty_translations():
    bad = [k for k, v in i18n.TRANSLATIONS.items() if not str(v).strip()]
    assert not bad, "пустой перевод у: %s" % ", ".join(bad)


def test_table_has_no_dead_keys():
    """Ключи таблицы, которых нет в коде, безвредны, но их стоит видеть."""
    dead = sorted(set(i18n.TRANSLATIONS) - collect())
    if dead:
        print("  предупреждение: %d ключей нет в коде:" % len(dead))
        for k in dead:
            print("    -", k)


def test_switching_language():
    i18n.set_language("ru")
    assert i18n.tr("Сцена") == "Сцена"
    i18n.set_language("en")
    assert i18n.tr("Сцена") == "Scene"
    assert i18n.tr("строки нет в таблице") == "строки нет в таблице"
    i18n.set_language(None)


if __name__ == "__main__":
    ok = 0
    for nm, fn in sorted(globals().items()):
        if nm.startswith("test_") and callable(fn):
            fn()
            print("OK", nm)
            ok += 1
    print("all i18n tests passed (%d)" % ok)
