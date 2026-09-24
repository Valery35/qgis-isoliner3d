# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Подписи и округление полей результата, без QGIS.

Запись подписи в GeoPackage и её установка на слой требуют QGIS
и GDAL. Их закрывает живой прогон, записанный в CHANGELOG. Здесь
проверяется то, что можно проверить headless: словарь, правило
округления и разбор ссылки на файл.

Запуск:  python isoliner3d/tests/test_fields.py
"""
import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import fields as F  # noqa: E402
from isoliner3d import i18n  # noqa: E402

WRITERS = ("algorithms.py", "viewer_dialog.py")


def _written_fields(path):
    """Имена полей, которые файл создаёт.

    Три записи встречаются в коде: `_field("имя", ...)`, пара
    `("имя", QVariant.Тип)` в перечне и цикл `for nm in ("а", "б")`
    с `_field(nm, ...)` внутри. Имена, собранные на лету, вроде
    `name + "_n"`, сюда не попадают: их закрывают подписи по хвосту.
    """
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    out = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and getattr(node.func, "id", None) == "_field"
                and node.args and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            out.add(node.args[0].value)
        elif isinstance(node, ast.Tuple) and len(node.elts) == 2:
            a, b = node.elts
            if (isinstance(a, ast.Constant) and isinstance(a.value, str)
                    and isinstance(b, ast.Attribute)
                    and getattr(b.value, "id", None) == "QVariant"):
                out.add(a.value)
        elif (isinstance(node, ast.For)
              and isinstance(node.iter, ast.Tuple)
              and all(isinstance(e, ast.Constant)
                      and isinstance(e.value, str)
                      for e in node.iter.elts)):
            body = ast.dump(ast.Module(body=node.body, type_ignores=[]))
            if "'_field'" in body:
                out |= {e.value for e in node.iter.elts}
    return out


def _all_written():
    got = {}
    for name in WRITERS:
        for fld in _written_fields(os.path.join(PKG, name)):
            got.setdefault(fld, name)
    return got


def test_every_written_field_has_a_label():
    """У каждого поля, которое пишет модуль, есть подпись.

    Поле без подписи видно в таблице атрибутов латиницей. Список
    собирается из исходников, чтобы новое поле нельзя было добавить
    молча.
    """
    got = _all_written()
    assert len(got) >= 50, "полей подозрительно мало: %d" % len(got)
    bad = sorted(n for n in got if F.label_for(n) is None)
    assert not bad, "нет подписи: %s" % bad


def test_no_dead_labels():
    """Подпись поля, которого никто не пишет, копится молча.

    Поле переименовали, а старая подпись осталась, и новое поле ходит
    без подписи, пока кто-нибудь не заметит латиницу в таблице.
    """
    got = _all_written()
    dead = sorted(set(F.LABELS) - set(got))
    assert not dead, "подписи без поля: %s" % dead


def test_guard_catches_a_planted_fault():
    """Проверка обязана краснеть, если у поля пропала подпись."""
    saved = F.LABELS.pop("grade")
    try:
        got = _all_written()
        bad = [n for n in got if F.label_for(n) is None]
        assert bad == ["grade"], bad
    finally:
        F.LABELS["grade"] = saved


def test_every_label_has_an_english_pair():
    """Подпись без перевода показала бы русское слово в английском QGIS.

    «X» и «Y» на обоих языках одинаковы, требовать им пару незачем.
    """
    need = [s for s in F.all_label_sources()
            if any("\u0400" <= ch <= "\u04ff" for ch in s)]
    missing = sorted(s for s in need if s not in i18n.TRANSLATIONS)
    assert not missing, "нет английской подписи: %s" % missing


def test_suffix_labels_carry_the_prefix():
    """Поля 2.14 подписываются с именем слоя, который считали."""
    assert F.label_for("blocks_n") == "%s: объектов внутри"
    assert F.label_prefix("blocks_n") == "blocks"
    assert F.label_prefix("faults_len") == "faults"
    assert F.label_for("_n") is None
    assert F.label_prefix("vol") is None
    assert F.label_for("своё_поле") is None


def test_metric_fields_round_to_centimetre():
    """Координаты и отметки до сантиметра, иначе X потерял бы сотни
    метров по правилу значащих цифр."""
    assert F.round_value("x", 6512345.678912) == 6512345.68
    assert F.round_value("z_from", -251.23456) == -251.23
    assert F.round_value("from_m", 12.005) in (12.0, 12.01)
    assert F.round_value("blocks_len", 33.4812) == 33.48


def test_values_keep_significant_digits():
    """Объёмы и содержания: четыре значащие, целая часть цела."""
    assert F.round_value("volume", 39524.12345678) == 39524.0
    assert F.round_value("grade", 25.374512) == 25.37
    assert F.round_value("grade", 0.0045678) == 0.004568
    assert F.round_value("resid", -0.00012345) == -0.0001234
    assert F.round_value("dens", 2.05) == 2.05
    assert F.round_value("ore_t", 1234567.89) == 1234568.0
    assert F.round_value("blocks_sum", 0.0) == 0.0


def test_integer_part_is_never_rounded():
    """Правило «четыре значащие» в чистом виде дало бы 39520."""
    for v in (39524.9, 123456.7, 98765432.1):
        r = F.round_value("volume", v)
        assert abs(r - v) <= 0.5, (v, r)


def test_non_floats_pass_through():
    """Целые, строки, пусто и NaN не трогаются."""
    assert F.round_value("bid", 7) == 7
    assert F.round_value("name", "КрII") == "КрII"
    assert F.round_value("volume", None) is None
    assert F.round_value("closed", True) is True
    nan = float("nan")
    assert F.round_value("volume", nan) != F.round_value("volume", nan)


def test_split_gpkg_ref():
    """Ссылка на слой: с именем слоя, без имени и мимо GeoPackage."""
    assert F.split_gpkg_ref("C:/d/a.gpkg|layername=b") == ("C:/d/a.gpkg",
                                                           "b")
    assert F.split_gpkg_ref("C:/d/a.gpkg") == ("C:/d/a.gpkg", None)
    assert F.split_gpkg_ref("C:/d/A.GPKG|layername=x") == ("C:/d/A.GPKG",
                                                           "x")
    assert F.split_gpkg_ref("memory:Тела") is None
    assert F.split_gpkg_ref("C:/d/a.shp") is None
    assert F.split_gpkg_ref("") is None
    assert F.split_gpkg_ref(None) is None


if __name__ == "__main__":
    ok = 0
    for nm, fn in sorted(globals().items()):
        if nm.startswith("test_") and callable(fn):
            fn()
            print("OK", nm)
            ok += 1
    print("all fields tests passed (%d)" % ok)
