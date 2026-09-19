#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка прозы: пунктуация, лексика, длина предложений.

Правила стиля жили в AGENTS.md и проверялись глазами, поэтому
руководство набрало длинных тире, точек с запятой и стоп-слов.
Здесь они проверяются запуском, а результат считается числом.

Что проверяется:

- длинного тире нет;
- точки с запятой нет;
- стоп-слов нет;
- у русских текстов измеряется длина предложений: длиннее 34 слов
  быть не должно.

Ссылки на инструменты сверяются с подписями интерфейса: имя в тексте
обязано совпадать с тем, что человек видит в панели Обработки.

Запуск: python3 tools/check_prose.py
Выход ноль, если находок нет.
"""

import ast
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PKG = os.path.join(ROOT, "isoliner3d")

FILES = [
    os.path.join("manual", "manual.md"),
    os.path.join("manual", "manual_en.md"),
    "README.md",
    "README.en.md",
]

RU_FILES = {os.path.join("manual", "manual.md"), "README.md"}

STOP = [
    "честн", "врёт", "врут", "главные грабли", "софт", "кучк", "гладь",
    "скучн", "членение", "наблюдённ", "предъяв", "соблазн", "лесенк",
    "сходит с рук", "деваться некуда", "вперемешку", "крутить параметр",
    "руками", "кучу", "под рукой", "мелочь", "навигатор", "лечит",
    "лечил", "болезн",
]

LONG_SENTENCE = 34


def tool_titles():
    """Подписи инструментов: русские из кода, английские из таблицы."""
    src = open(os.path.join(PKG, "algorithms.py"), encoding="utf-8").read()
    ru = {}
    for node in ast.parse(src).body:
        if not isinstance(node, ast.ClassDef):
            continue
        for sub in node.body:
            if (isinstance(sub, ast.FunctionDef)
                    and sub.name == "displayName"):
                seg = ast.get_source_segment(src, sub) or ""
                m = re.search(r'tr\(\s*"([^"]+)"', seg)
                if m:
                    ru[m.group(1)[:4]] = m.group(1)[5:]
    table = open(os.path.join(PKG, "i18n.py"), encoding="utf-8").read()
    en = {}
    for num, title in ru.items():
        key = re.escape("%s %s" % (num, title))
        m = re.search(r"'" + key + r"':\s*'([^']*)'", table)
        if m:
            en[num] = m.group(1)[5:]
    return ru, en


def sentences(text):
    """Предложения прозы: таблицы, заголовки, списки и код пропущены."""
    out, buf = [], []
    skip = ("|", "#", "!", "```", "---", "title:", "lang:", "toc-")
    in_item = False
    for line in text.split("\n"):
        bullet = re.match(r"^\s*(?:[-*]|\d+[.)])\s", line)
        # Продолжение пункта списка идёт с отступом и предложением
        # не является: склеенное с соседями, оно даёт мнимую фразу
        # на сорок слов.
        cont = in_item and line.startswith(" ") and line.strip()
        if not line.strip():
            in_item = False
        elif bullet:
            in_item = True
        if line.startswith(skip) or bullet or cont or not line.strip():
            if buf:
                out.append(" ".join(buf))
                buf = []
            continue
        buf.append(line.strip())
    if buf:
        out.append(" ".join(buf))
    prose = re.sub(r"\*\*|\*|`", "", " ".join(out))
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", prose) if s.strip()]


def check(path, ru_titles, en_titles):
    """Находки по одному файлу списком строк."""
    full = os.path.join(ROOT, path)
    if not os.path.isfile(full):
        return []
    text = open(full, encoding="utf-8").read()
    found = []
    for i, line in enumerate(text.split("\n"), 1):
        if "—" in line:
            found.append("%s:%d длинное тире" % (path, i))
        if ";" in line:
            found.append("%s:%d точка с запятой" % (path, i))
        low = line.lower()
        for word in STOP:
            if word in low:
                found.append("%s:%d стоп-слово %s" % (path, i, word))

    titles = ru_titles if path in RU_FILES else en_titles
    for m in re.finditer(r"\*\*(\d\.\d\d)\s+([^*]+)\*\*", text):
        num = m.group(1)
        got = " ".join(m.group(2).split()).rstrip(".,")
        want = titles.get(num)
        if want and got != want:
            line = text[:m.start()].count("\n") + 1
            found.append("%s:%d инструмент назван %r вместо %r"
                         % (path, line, got, want))

    if path in RU_FILES:
        lens = [len(s.split()) for s in sentences(text)]
        for s in sentences(text):
            if len(s.split()) > LONG_SENTENCE:
                found.append("%s: предложение из %d слов: %s..."
                             % (path, len(s.split()), s[:60]))
        if lens:
            sys.stderr.write(
                "%s: предложений %d, средняя длина %.1f, длиннее 28 слов "
                "%d\n" % (path, len(lens), statistics.mean(lens),
                          sum(1 for x in lens if x > 28)))
    return found


def main():
    ru_titles, en_titles = tool_titles()
    found = []
    for path in FILES:
        found += check(path, ru_titles, en_titles)
    for line in found:
        print(line)
    print("находок: %d" % len(found))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
