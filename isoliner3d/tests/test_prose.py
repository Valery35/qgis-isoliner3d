# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Правила прозы как проверка, а не как память.

Стиль текстов был записан в AGENTS.md и проверялся глазами. За одну
редакцию руководство набрало два длинных тире, одиннадцать точек
с запятой, четыре стоп-слова и восемь ссылок на инструменты старыми
именами. Ровно тот случай, для которого в этом проекте у каждого
правила стоит сторож.

Проверка зовёт `tools/check_prose.py` и требует ноль находок. Файлов
`manual/` и `README.md` в архиве модуля нет, и там проверка молча
пропускается.

Запуск: python isoliner3d/tests/test_prose.py
"""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
ROOT = os.path.dirname(PKG)
CHECKER = os.path.join(ROOT, "tools", "check_prose.py")


def _load():
    spec = importlib.util.spec_from_file_location("check_prose", CHECKER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_prose_rules_hold():
    """Ни длинного тире, ни точки с запятой, ни стоп-слов.

    Сюда же попадают ссылки на инструменты: имя в тексте обязано
    совпадать с подписью в панели Обработки, иначе читатель ищет
    в списке то, чего там нет.
    """
    if not os.path.isfile(CHECKER):
        return                      # в архиве модуля файла нет
    mod = _load()
    if not os.path.isfile(os.path.join(ROOT, "manual", "manual.md")):
        return                      # руководства рядом нет
    ru, en = mod.tool_titles()
    found = []
    for path in mod.FILES:
        found += mod.check(path, ru, en)
    assert not found, "находки в прозе:\n  %s" % "\n  ".join(found[:12])


def test_the_checker_catches_a_planted_fault():
    """Сторож проверяется подменой: он обязан краснеть на образце.

    Проверка, которая ничего не ловит, неотличима от отсутствующей.
    Поэтому в текст подставляются заведомые нарушения, и находок
    должно стать ровно на их число больше.
    """
    if not os.path.isfile(CHECKER):
        return
    mod = _load()
    bad = ("Строка с длинным тире — вот оно.\n"
           "Строка с точкой с запятой; вот она.\n"
           "Строка со стоп-словом: правится руками.\n")
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        name = "planted.md"
        with open(os.path.join(tmp, name), "w", encoding="utf-8") as fh:
            fh.write(bad)
        saved = mod.ROOT
        try:
            mod.ROOT = tmp
            found = mod.check(name, {}, {})
        finally:
            mod.ROOT = saved
    kinds = {f.split(" ", 1)[1].split(" ")[0] for f in found}
    assert len(found) == 3, found
    assert kinds == {"длинное", "точка", "стоп-слово"}, kinds


if __name__ == "__main__":
    for nm, fn in sorted(globals().items()):
        if nm.startswith("test_") and callable(fn):
            fn()
            print("OK", nm)
    print("all prose tests passed")
