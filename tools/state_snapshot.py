#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Снимок состояния репозитория для AGENTS.md.

Числа в договоре с разработчиком нельзя писать руками. Проверено дважды
за сутки: сторонние разборы кода нашли в AGENTS.md версию 0.1.0 при
живой 1.1.0, «кригинга здесь нет» при двух работающих инструментах
кригинга, «десять тестов» при тридцати четырёх. Документ читается как
договор, а половина его утверждений оказалась снимком годичной
давности.

Поэтому раздел состояния собирается отсюда, из самого репозитория,
и вставляется между метками. Правила остаются написанными от руки -
их писать и надо от руки, - а числа считаются.

Запуск: python tools/state_snapshot.py [--check]
"""
import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PKG = os.path.join(ROOT, "isoliner3d")
BEGIN = "<!-- СНИМОК НАЧАЛО: собирается tools/state_snapshot.py -->"
END = "<!-- СНИМОК КОНЕЦ -->"


def _version():
    for line in open(os.path.join(PKG, "metadata.txt"), encoding="utf-8"):
        if line.startswith("version="):
            return line.split("=", 1)[1].strip()
    return "?"


def _flag(name):
    for line in open(os.path.join(PKG, "metadata.txt"), encoding="utf-8"):
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip()
    return "?"


def _tools():
    """Номер и подпись каждого инструмента, разбором algorithms.py."""
    src = open(os.path.join(PKG, "algorithms.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    listed = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and \
                getattr(node.targets[0], "id", "") == "ALGORITHMS":
            listed = [e.id for e in node.value.elts
                      if isinstance(e, ast.Name)]
    out = []
    for cls in listed:
        i = src.index("class %s(" % cls)
        j = src.find("\nclass ", i + 10)
        seg = src[i:j if j > 0 else len(src)]
        k = seg.find("def displayName")
        title = "?"
        if k >= 0:
            m = re.search(r'"([^"]+)"', seg[k:k + 400])
            if m:
                title = m.group(1)
        out.append((cls, title))
    return out


def _sizes():
    rows = []
    for nm in ("viewer_dialog.py", "algorithms.py", "viewer3d.py",
               "viewer_core.py", "i18n.py"):
        p = os.path.join(PKG, nm)
        if os.path.isfile(p):
            n = sum(1 for _ in open(p, encoding="utf-8"))
            rows.append((nm, n))
    return rows


def _tests():
    d = os.path.join(PKG, "tests")
    return sorted(f for f in os.listdir(d)
                  if f.startswith("test_") and f.endswith(".py"))


def _libs_mb():
    total = 0
    for root, _dirs, files in os.walk(os.path.join(PKG, "libs")):
        for f in files:
            total += os.path.getsize(os.path.join(root, f))
    return total / (1024.0 * 1024.0)


def build():
    tools = _tools()
    nums = []
    for _cls, title in tools:
        m = re.match(r"(\d+\.\d+)", title)
        nums.append(m.group(1) if m else "?")
    first = [n for n in nums if n.startswith("1.")]
    second = [n for n in nums if n.startswith("2.")]
    lines = [BEGIN, "",
             "Раздел собран из репозитория, руками не правится.", "",
             "| Что | Сейчас |", "|---|---|",
             "| Версия | %s |" % _version(),
             "| `experimental` | %s |" % _flag("experimental"),
             "| Инструментов Processing | %d: группа 1 (%s-%s), "
             "группа 2 (%s-%s) |"
             % (len(tools), first[0], first[-1], second[0], second[-1]),
             "| Файлов тестов | %d |" % len(_tests()),
             "| `libs/` | %.0f МБ |" % _libs_mb(),
             ""]
    lines += ["Размеры ключевых файлов, строк:", "",
              "| Файл | Строк |", "|---|---|"]
    for nm, n in _sizes():
        lines.append("| `%s` | %d |" % (nm, n))
    lines += ["", "Инструменты:", "", "| Номер | Подпись | Класс |",
              "|---|---|---|"]
    for (cls, title), num in zip(tools, nums):
        name = title[len(num):].strip() if title.startswith(num) else title
        lines.append("| %s | %s | `%s` |" % (num, name, cls))
    lines += ["", END]
    return "\n".join(lines) + "\n"


def apply(check=False):
    p = os.path.join(ROOT, "AGENTS.md")
    text = open(p, encoding="utf-8").read()
    fresh = build()
    if BEGIN in text and END in text:
        i = text.index(BEGIN)
        j = text.index(END) + len(END) + 1
        merged = text[:i] + fresh + text[j:]
    else:
        raise SystemExit("в AGENTS.md нет меток снимка")
    if check:
        return merged == text
    if merged != text:
        open(p, "w", encoding="utf-8").write(merged)
    return True


if __name__ == "__main__":
    if "--check" in sys.argv:
        ok = apply(check=True)
        print("снимок актуален" if ok else "снимок устарел")
        sys.exit(0 if ok else 1)
    apply()
    print("снимок обновлён")
