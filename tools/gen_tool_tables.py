#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Таблицы полей инструментов - из самого кода.

Руководство, писанное отдельно от кода, расходится с ним на первой же
правке: поле переименовали, а в тексте старое имя. Здесь таблицы
собираются разбором `algorithms.py`, и разойтись им не с чем.

Берётся: номер и название инструмента из `displayName`, порядок полей
из `initAlgorithm`, подписи из `self.tr(...)` при объявлении поля,
пояснения из словаря подсказок этого инструмента.

Запуск: python3 tools/gen_tool_tables.py [ru|en]
"""

import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(os.path.dirname(HERE), "isoliner3d")


def _str_of(node):
    """Строка из узла: голая, из tr(...) или из склейки кусков."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Call):
        if node.args:
            return _str_of(node.args[0])
        return None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        a = _str_of(node.left)
        b = _str_of(node.right)
        if a is not None and b is not None:
            return a + b
    if isinstance(node, ast.JoinedStr):
        return None
    return None


def _hints_of(tree, name):
    """Словарь подсказок по имени."""
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        tgt = node.targets[0]
        if getattr(tgt, "id", None) != name:
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        out = {}
        for k, v in zip(node.value.keys, node.value.values):
            key = _str_of(k)
            val = _str_of(v)
            if key:
                out[key] = val or ""
        return out
    return {}


def _params_of(fn, consts=None):
    """Поля инструмента в порядке объявления: (имя, подпись, вид).

    Имя поля бывает и строкой, и полем класса вроде `self.ROOF`:
    второе разрешается по собранным константам класса.
    """
    consts = consts or {}
    out = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        fname = getattr(node.func, "id", "") or getattr(
            node.func, "attr", "")
        if not fname.startswith("QgsProcessingParameter"):
            continue
        if len(node.args) < 2:
            continue
        key = _str_of(node.args[0])
        if key is None and isinstance(node.args[0], ast.Attribute):
            key = consts.get(node.args[0].attr)
        label = _str_of(node.args[1])
        if not key:
            continue
        kind = fname.replace("QgsProcessingParameter", "")
        out.append((key, label or key, kind))
    return out


def _hint_name(fn):
    """Имя словаря подсказок, переданное в `_hints`."""
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and getattr(
                node.func, "id", "") == "_hints":
            if len(node.args) >= 2:
                return getattr(node.args[1], "id", None)
    return None


def collect():
    """Инструменты с полями и подсказками, в порядке номеров."""
    src = open(os.path.join(PKG, "algorithms.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    tools = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        title = None
        init = None
        helps = None
        for sub in node.body:
            if not isinstance(sub, ast.FunctionDef):
                continue
            if sub.name == "displayName":
                for n2 in ast.walk(sub):
                    if isinstance(n2, ast.Return):
                        title = _str_of(n2.value)
            elif sub.name == "initAlgorithm":
                init = sub
            elif sub.name == "shortHelpString":
                for n2 in ast.walk(sub):
                    if isinstance(n2, ast.Return):
                        helps = _str_of(n2.value)
        if not title or init is None:
            continue
        # Константы объявляются и парами: ROOF, BOTTOM = "ROOF",
        # "BOTTOM". Разбирая только одиночные, потеряешь половину
        # полей, и таблица выйдет неполной - молча.
        consts = {}
        for sub in node.body:
            if not isinstance(sub, ast.Assign):
                continue
            tgt = sub.targets[0]
            if isinstance(tgt, ast.Tuple) and isinstance(sub.value,
                                                         ast.Tuple):
                for t, v in zip(tgt.elts, sub.value.elts):
                    nm = getattr(t, "id", None)
                    val = _str_of(v)
                    if nm and val:
                        consts[nm] = val
                continue
            nm = getattr(tgt, "id", None)
            val = _str_of(sub.value)
            if nm and val:
                consts[nm] = val
        hints = _hints_of(tree, _hint_name(init) or "")
        tools.append({
            "title": title,
            "help": helps or "",
            "params": [(k, lab, kind, hints.get(k, ""))
                       for k, lab, kind in _params_of(init, consts)],
        })
    tools.sort(key=lambda t: t["title"])
    return tools


def render(tools, lang="ru"):
    """Разделы руководства по инструментам."""
    head = {"ru": ("Поле", "Что задаёт"),
            "en": ("Field", "What it sets")}[lang]
    out = []
    group = None
    for t in tools:
        num = re.match(r"([\d.]+)", t["title"])
        g = num.group(1).split(".")[0] if num else "?"
        if g != group:
            group = g
            out.append("")
        out.append("## %s\n" % t["title"])
        if t["help"]:
            out.append(t["help"].strip() + "\n")
        if t["params"]:
            out.append("| %s | %s |" % head)
            out.append("|---|---|")
            for _k, lab, _kind, hint in t["params"]:
                out.append("| **%s** | %s |" % (lab, hint or "—"))
            out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    lang = sys.argv[1] if len(sys.argv) > 1 else "ru"
    got = collect()
    sys.stderr.write("инструментов: %d, полей: %d\n"
                     % (len(got), sum(len(t["params"]) for t in got)))
    print(render(got, lang))
