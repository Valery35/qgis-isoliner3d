# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Сторожа проверки metadata.txt перед каталогом (tools/preflight.py).

Перенесены из PlanetX. Адрес в процент-кодировке каталог не принял
у Routeliner, выданный номер версии закрыт. Сеть и git подменены.
Сборщик лежит в корне хранилища, в рабочем архиве модуля его нет:
там проверки пропускаются.

Запуск:  python isoliner3d/tests/test_preflight.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
TOOLS = os.path.join(ROOT, "tools")
HAVE = os.path.isfile(os.path.join(TOOLS, "preflight.py"))
if HAVE:
    sys.path.insert(0, TOOLS)
    import gittool    # noqa: E402
    import preflight  # noqa: E402


def test_percent_encoding_is_error():
    if not HAVE:
        return
    found = preflight.url_problems({
        "homepage": "https://www.informpp.ru/%D0%B3%D0%BB/isoliner3d"})
    assert any("процент" in f for f in found), found


def test_letters_pass_but_no_www_and_http_fail():
    if not HAVE:
        return
    assert preflight.url_problems({
        "homepage": "https://www.informpp.ru/главная-страница/isoliner3d",
        "tracker": "https://github.com/Valery35/qgis-isoliner3d/issues"}) \
        == []
    found = preflight.url_problems({
        "homepage": "https://informpp.ru/isoliner3d",
        "repository": "http://github.com/Valery35/qgis-isoliner3d"})
    assert len(found) == 2, found


def test_changelog_must_start_with_the_version():
    if not HAVE:
        return
    ok = {"changelog": "1.5.7\n    - исправление"}
    assert preflight.changelog_problems(ok, "1.5.7") == []
    old = {"changelog": "1.5.6\n    - прежнее"}
    assert preflight.changelog_problems(old, "1.5.7")
    # 1.5.70 не то же, что 1.5.7
    assert preflight.changelog_problems({"changelog": "1.5.70 x"}, "1.5.7")


def _tags(tags, head, tag_at, version):
    answers = {"tag": "\n".join(tags), "rev-parse": head,
               "rev-list": tag_at, "fetch": ""}

    def fake(*args):
        return answers[args[0]]
    saved = gittool.git
    gittool.git = fake
    try:
        return [text for level, text in preflight.tag_problems(version)
                if level == "error"]
    finally:
        gittool.git = saved


def test_new_number_passes():
    if not HAVE:
        return
    assert _tags(["1.5.6", "1.5.7"], "a", "b", "1.5.8") == []


def test_released_number_on_other_commit():
    if not HAVE:
        return
    assert len(_tags(["1.5.7"], "a", "b", "1.5.7")) == 1
    # старые метки с буквой v тоже понимаются
    assert len(_tags(["v1.5.7"], "a", "b", "1.5.7")) == 1


def test_tagged_head_passes():
    if not HAVE:
        return
    assert _tags(["1.5.7"], "a", "a", "1.5.7") == []


def test_number_below_last_release_compares_as_numbers():
    if not HAVE:
        return
    found = _tags(["1.9.0", "1.44.1"], "a", "b", "1.10.0")
    assert len(found) == 1 and "1.44.1" in found[0], found
    assert _tags(["1.9.0"], "a", "b", "1.10.0") == []


def _numbers(text):
    return [m.group(1) for m in preflight.VERSION.finditer(text)]


def test_prefixed_number_is_found():
    """Номер с приставкой «v» прежний шаблон \\b...\\b пропускал молча."""
    if not HAVE:
        return
    assert _numbers("Isoliner3D v1.5.7") == ["1.5.7"]
    assert _numbers("## [v0.5.4] - 2026") == ["0.5.4"]


def test_plain_and_archive_names():
    if not HAVE:
        return
    assert _numbers("Версия 1.5.7.") == ["1.5.7"]
    assert _numbers("isoliner3d-1.5.7.zip") == ["1.5.7"]
    # четыре части - не номер версии модуля
    assert _numbers("сборка 1.5.7.2") == []


def test_prefixed_mention_is_compared():
    """README с номером «v» - расхождение видно, а не пропущено."""
    if not HAVE:
        return
    import tempfile
    with tempfile.TemporaryDirectory() as root:
        with open(os.path.join(root, "README.md"), "w",
                  encoding="utf-8") as fh:
            fh.write("Isoliner3D v0.0.1\n")
        found = preflight.version_mentions(root)
    assert found == [("README.md:1", "0.0.1")], found


def test_our_metadata_passes_offline():
    if not HAVE:
        return
    version, errors, _warn = preflight.check()
    assert version and not errors, errors


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
