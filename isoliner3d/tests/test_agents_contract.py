# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""AGENTS.md как проверяемый договор, а не как рассказ о прошлом.

Дважды за сутки сторонний разбор кода ловил этот файл на устаревших
числах: версия 0.1.0 при живой 1.1.0, «кригинга здесь нет» при двух
работающих инструментах кригинга, десять тестов при тридцати четырёх.
Документ читается как договор, и человек, поверивший ему, начинает
с неверной картины.

Отсюда два теста. Первый: снимок состояния собран из репозитория
и не устарел. Второй: каждое правило в таблице названо вместе
со сторожем, и сторож этот существует.

Запуск: python -m pytest isoliner3d/tests/test_agents_contract.py -q
"""
import importlib.util
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
ROOT = os.path.dirname(PKG)
AGENTS = os.path.join(ROOT, "AGENTS.md")
GEN = os.path.join(ROOT, "tools", "state_snapshot.py")


def _load_gen():
    spec = importlib.util.spec_from_file_location("state_snapshot", GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_state_snapshot_is_fresh():
    """Снимок состояния совпадает с тем, что даёт репозиторий сейчас.

    Числа в договоре руками не пишутся. Если этот тест упал, надо
    не править цифру, а выполнить `python tools/state_snapshot.py`.
    """
    if not os.path.isfile(AGENTS) or not os.path.isfile(GEN):
        return                      # в архиве модуля этих файлов нет
    mod = _load_gen()
    assert mod.apply(check=True), (
        "снимок устарел: выполните python tools/state_snapshot.py")


def test_rules_name_living_guards():
    """У каждого правила есть сторож, и сторож этот существует.

    Правило без теста живёт до первой спешки. Поэтому таблица правил
    хранит имя теста, а тест - проверяет, что имя не осыпалось.
    """
    if not os.path.isfile(AGENTS):
        return
    text = open(AGENTS, encoding="utf-8").read()
    start = text.index("## Правила и их сторожа")
    end = text.index("Правила, за которыми сторожа пока нет", start)
    rows = re.findall(r"\|\s*`(test_[a-z0-9_]+)`\s*\|",
                      text[start:end])
    assert len(rows) >= 8, "таблица правил подозрительно короткая"

    have = set()
    for f in os.listdir(HERE):
        if f.startswith("test_") and f.endswith(".py"):
            src = open(os.path.join(HERE, f), encoding="utf-8").read()
            have |= set(re.findall(r"def (test_[a-z0-9_]+)\(", src))
    missing = [r for r in rows if r not in have]
    assert not missing, "сторожа нет, а правило обещает: %s" % missing


def test_agents_does_not_repeat_the_numbers_by_hand():
    """Числа состояния не дублируются прозой мимо снимка.

    Ровно так файл и разошёлся с кодом: количество инструментов
    и тестов было написано словами в двух местах, и оба устарели.
    """
    if not os.path.isfile(AGENTS):
        return
    text = open(AGENTS, encoding="utf-8").read()
    i = text.index("<!-- СНИМОК НАЧАЛО")
    j = text.index("<!-- СНИМОК КОНЕЦ")
    outside = text[:i] + text[j:]
    for bad in ("Тридцать файлов", "все десять", "версия 0.1.0",
                "16 инструментов", "шестнадцать инструментов"):
        assert bad not in outside, "снова число прозой: %s" % bad


if __name__ == "__main__":
    for nm, fn in sorted(globals().items()):
        if nm.startswith("test_") and callable(fn):
            fn()
            print("OK", nm)
    print("all agents contract tests passed")
