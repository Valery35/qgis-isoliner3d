#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Страницы инструментов-объектов: одна на инструмент и язык.

Страница - начало раздела инструмента в руководстве: заголовок
«## 2.24 Тело вдоль выработки», справка и таблица полей. Всё, что
ниже, с первого подзаголовка («### Как пользоваться» и прочие),
пишется руками и генератору не принадлежит.

Одни и те же страницы идут в manual.md и manual_en.md модуля и
в расширение RustGIS (fixtures/docs/tools/<код>.<язык>.md хранилища
isoliner-scene), поэтому QGIS и RustGIS говорят слово в слово.
Глава «Isoliner3D в RustGIS» берётся из isoliner-scene
(doc/manual/rustgis.<язык>.md) и встаёт в руководство копией между
метками rustgis:begin и rustgis:end.

Вход - описание из tools.json (tools/export_tools.py), страницы
строятся по нему, а не по коду напрямую.

Запуск:
    python3 tools/tool_pages.py --fixtures C:/Dev/isoliner-scene/fixtures
    python3 tools/tool_pages.py --manual [--rustgis <папка глав>]
    python3 tools/tool_pages.py --check     (руководство не устарело)
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MANUALS = {"ru": os.path.join(ROOT, "manual", "manual.md"),
           "en": os.path.join(ROOT, "manual", "manual_en.md")}
HEAD = {"ru": ("Поле", "Что задаёт"), "en": ("Field", "What it sets")}
# глава RustGIS встаёт перед этим заголовком, если меток ещё нет
RUSTGIS_BEFORE = {"ru": "# Соседние плагины",
                  "en": "# Neighbouring plugins"}
BEGIN, END = "<!-- rustgis:begin -->", "<!-- rustgis:end -->"


def load(path=None):
    """Описание инструментов: из файла tools.json или собранное."""
    if path:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    sys.path.insert(0, HERE)
    import export_tools
    return export_tools.build()


def page(tool, lang):
    """Страница инструмента на языке: заголовок, справка, таблица."""
    out = ["## %s %s" % (tool["code"], tool["title"][lang]), ""]
    for par in tool["help"][lang].strip().split("\n\n"):
        out += [par.strip(), ""]
    out += ["| %s | %s |" % HEAD[lang], "|---|---|"]
    for p in tool["params"]:
        out.append("| **%s** | %s |" % (p["label"][lang],
                                        p["hint"][lang] or "-"))
    return "\n".join(out) + "\n"


def pages(data, lang):
    """Страницы всех инструментов-объектов: {код: текст}."""
    return {t["code"]: page(t, lang) for t in data["tools"]}


def write_fixtures(data, dest):
    """Страницы в dest/docs/tools и список index.json рядом."""
    folder = os.path.join(dest, "docs", "tools")
    os.makedirs(folder, exist_ok=True)
    index = []
    for t in data["tools"]:
        for lang in ("ru", "en"):
            name = os.path.join(folder, "%s.%s.md" % (t["code"], lang))
            with open(name, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(page(t, lang))
        index.append({"code": t["code"], "name": t["name"],
                      "group": t["group"], "title": t["title"]})
    with open(os.path.join(folder, "index.json"), "w", encoding="utf-8",
              newline="\n") as fh:
        json.dump({"format": 1, "version": data["version"],
                   "tools": index}, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    return len(index)


def _block(lines, code):
    """Начало и конец раздела инструмента до первого подзаголовка."""
    head = re.compile(r"^## %s " % re.escape(code))
    found = [i for i, s in enumerate(lines) if head.match(s)]
    if len(found) != 1:
        raise ValueError("раздел %s найден %d раз" % (code, len(found)))
    start = found[0]
    end = start + 1
    while end < len(lines) and not lines[end].startswith("#"):
        end += 1
    return start, end


def _chapter(text):
    """Глава RustGIS без служебных комментариев в начале файла."""
    lines = text.replace("\r\n", "\n").split("\n")
    while lines and (lines[0].startswith("<!--") or not lines[0].strip()):
        lines.pop(0)
    return "\n".join(lines).strip() + "\n"


def sync(text, lang, data, chapter=None):
    """Руководство с разделами инструментов из страниц.

    chapter - текст главы RustGIS или None (метки не трогаются).
    """
    if "\r\n" in text:
        # руководство хранится с CRLF, страницы с LF: правим в LF
        # и возвращаем перевод строки файла
        return sync(text.replace("\r\n", "\n"), lang, data,
                    chapter).replace("\n", "\r\n")
    lines = text.split("\n")
    for code, body in pages(data, lang).items():
        start, end = _block(lines, code)
        lines[start:end] = body.split("\n")
    out = "\n".join(lines)
    if chapter is None:
        return out
    block = "%s\n\n%s\n%s" % (BEGIN, _chapter(chapter), END)
    if BEGIN in out:
        a = out.index(BEGIN)
        b = out.index(END, a) + len(END)
        return out[:a] + block + out[b:]
    anchor = "\n%s\n" % RUSTGIS_BEFORE[lang]
    if out.count(anchor) != 1:
        raise ValueError("нет места для главы RustGIS: %s" % anchor)
    return out.replace(anchor, "\n%s\n%s" % (block, anchor), 1)


def stale(data):
    """Языки, где разделы руководства разошлись со страницами."""
    bad = []
    for lang, path in MANUALS.items():
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        if sync(text, lang, data) != text:
            bad.append(lang)
    return bad


def main(argv):
    data = load()
    if "--fixtures" in argv:
        dest = argv[argv.index("--fixtures") + 1]
        n = write_fixtures(data, dest)
        sys.stderr.write("страниц: %d x 2 -> %s\n" % (n, dest))
    if "--manual" in argv:
        src = None
        if "--rustgis" in argv:
            src = argv[argv.index("--rustgis") + 1]
        for lang, path in MANUALS.items():
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            chapter = None
            if src:
                with open(os.path.join(src, "rustgis.%s.md" % lang),
                          encoding="utf-8") as fh:
                    chapter = fh.read()
            new = sync(text, lang, data, chapter)
            if new != text:
                with open(path, "w", encoding="utf-8",
                          newline="\n") as fh:
                    fh.write(new)
                sys.stderr.write("обновлено: %s\n" % path)
    if "--check" in argv:
        bad = stale(data)
        if bad:
            sys.stderr.write("руководство устарело: %s\n" % ", ".join(bad))
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
