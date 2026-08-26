# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Счётчики перестройки сцены: арифметика и формат строк.

Проверяется headless: `_Prof` и `_fmt_n` лежат на верхнем уровне viewer3d
и QGIS не требуют.

Запуск:  python isoliner3d/tests/test_prof.py
"""
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import i18n            # noqa: E402
from isoliner3d.viewer3d import _Prof, _fmt_n   # noqa: E402

NBSP = "\u00a0"


def test_fmt_groups_by_three():
    assert _fmt_n(1) == "1"
    assert _fmt_n(999) == "999"
    assert _fmt_n(1000) == "1" + NBSP + "000"
    assert _fmt_n(1234567) == "1" + NBSP + "234" + NBSP + "567"


def test_counts_accumulate():
    p = _Prof()
    p.count("tris", 10).count("tris", 5).count("reads")
    assert p.counts["tris"] == 15
    assert p.counts["reads"] == 1


def test_phases_accumulate_and_skip():
    p = _Prof()
    time.sleep(0.01)
    p.add("read")
    time.sleep(0.02)
    p.skip()               # это время не попадает никуда
    time.sleep(0.01)
    p.add("read")
    assert p.phases["read"] >= 0.015, p.phases
    assert p.phases["read"] < p.total()


def test_total_covers_phases():
    p = _Prof()
    time.sleep(0.01)
    p.add("read")
    time.sleep(0.01)
    p.add("mesh")
    assert p.total() >= sum(p.phases.values())


def test_brief_has_three_numbers():
    p = _Prof()
    p.count("tris", 1234).count("items", 3)
    for lang in ("ru", "en"):
        i18n.set_language(lang)
        s = p.brief()
        assert "1" + NBSP + "234" in s, s
        assert "3" in s and s.endswith(".")
    i18n.set_language(None)


def test_report_lists_only_used_phases():
    p = _Prof()
    time.sleep(0.01)
    p.add("read")
    i18n.set_language("ru")
    s = p.report()
    assert "чтение" in s
    assert "окраска" not in s, "пустые фазы в отчёт не попадают"
    i18n.set_language(None)


def test_report_survives_empty_run():
    """Пустая сцена не должна ронять отчёт делением или ключами."""
    p = _Prof()
    for lang in ("ru", "en"):
        i18n.set_language(lang)
        assert p.brief()
        assert re.search(r"\d", p.report())
    i18n.set_language(None)


def test_memory_estimate_grows_with_scene():
    """Оценка памяти должна расти вместе со сценой и ловить порядок."""
    p = _Prof()
    assert p.megabytes() == 0.0
    p.count("verts", 100000).count("tris", 200000)
    small = p.megabytes()
    assert 5 < small < 10, small
    p.count("texpx", 4096 * 4096)
    big = p.megabytes()
    assert big - small > 60, (small, big)   # текстура 4096 это 64 МБ


def test_layer_budget_shares_the_scene():
    """Бюджет вершин делится между слоями, но не ниже пола."""
    # Бюджет вынесен в viewer_core и теперь просто импортируется:
    # раньше здесь вырезался кусок исходника, потому что импорт окна
    # тянул QGIS.
    from isoliner3d.viewer_core import (_layer_budget, MIN_VERTS_LAYER,
                                        MAX_VERTS_SCENE)
    budget = _layer_budget
    one = budget(1)
    six = budget(6)
    many = budget(100)
    assert one > six > many, (one, six, many)
    assert many == MIN_VERTS_LAYER
    assert six * 6 <= MAX_VERTS_SCENE


if __name__ == "__main__":
    ok = 0
    for nm, fn in sorted(globals().items()):
        if nm.startswith("test_") and callable(fn):
            fn()
            print("OK", nm)
            ok += 1
    print("all prof tests passed (%d)" % ok)
