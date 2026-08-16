# -*- coding: utf-8 -*-
#
# Isoliner - грид и изолинии (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Статические проверки viewer3d.py без запуска QGIS/pyqtgraph.

Ловит класс ошибок «локальная переменная затеняет функцию-замыкание»:
однажды `tr = np.column_stack(...)` внутри rebuild() сделал `tr` локальной
на всю функцию, и вызов tr("…") в конце падал UnboundLocalError. Тест
проверяет, что ни одна функция не вызывает tr(...) и одновременно не
присваивает tr как локальную переменную.
"""
import ast
import os

HERE = os.path.dirname(os.path.abspath(__file__))
VIEWER = os.path.join(os.path.dirname(HERE), "viewer3d.py")


def _own_nodes(fn):
    """Узлы тела функции, не спускаясь во вложенные функции/лямбды."""
    stack = list(fn.body)
    while stack:
        node = stack.pop()
        yield node
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.Lambda)):
                continue
            stack.append(child)


def _assigned_names(fn):
    names = set()
    for node in _own_nodes(fn):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            if isinstance(node.target, ast.Name):
                names.add(node.target.id)
        elif isinstance(node, ast.For) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _calls_name(fn, name):
    for node in _own_nodes(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == name:
            return True
    return False


def test_tr_not_shadowed():
    tree = ast.parse(open(VIEWER, encoding="utf-8").read())
    bad = []
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _calls_name(fn, "tr") and "tr" in _assigned_names(fn):
                bad.append(fn.name)
    assert not bad, "tr() затенён локальной переменной в: %s" % ", ".join(bad)


def test_no_qt_finddata():
    """Штатный findData не должен использоваться.

    Он сравнивает данные пункта через QVariant и на кортежах Python
    молча возвращает -1: выбранная окраска подменялась палитрой при
    переходе на другой слой, хотя в сцене оставалась прежней. Свой
    `_find_data` сравнивает объекты Python напрямую.
    """
    src = open(VIEWER, encoding="utf-8").read()
    bad = []
    for num, line in enumerate(src.split("\n"), 1):
        if ".findData(" in line and "def _find_data" not in line:
            bad.append("%d: %s" % (num, line.strip()))
    assert not bad, ("используйте _find_data вместо findData:\n  %s"
                     % "\n  ".join(bad))


def test_find_data_matches_tuples():
    """Сам поиск обязан находить кортеж, ради которого затевался."""
    ns = {}
    src = open(VIEWER, encoding="utf-8").read()
    start = src.index("def _find_data(")
    end = src.index("def _fmt_n(")
    exec(compile(src[start:end], "viewer3d", "exec"), ns)   # nosec
    find = ns["_find_data"]

    class Combo(object):
        def __init__(self, data):
            self._data = data

        def count(self):
            return len(self._data)

        def itemData(self, i):
            return self._data[i]

    combo = Combo([("palette", None), ("solid", None),
                   ("tex", "osm_1"), ("raster", "dem_2")])
    assert find(combo, ("tex", "osm_1")) == 2
    assert find(combo, ("palette", None)) == 0
    assert find(combo, ("tex", "нет такого")) == -1


def test_dialog_methods_exist():
    """Все self._методы диалога должны быть определены.

    Диалог перестраивался целиком, и висячий вызов исчезнувшего метода
    компиляция не заметит: он всплывёт нажатием кнопки у пользователя.
    """
    src = open(VIEWER, encoding="utf-8").read()
    tree = ast.parse(src)
    cls = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "ViewerDialog":
            cls = node
    assert cls is not None, "класс ViewerDialog не найден"
    defined = {m.name for m in ast.walk(cls)
               if isinstance(m, ast.FunctionDef)}
    attrs = set()
    for node in ast.walk(cls):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if (isinstance(tgt, ast.Attribute)
                        and getattr(tgt.value, "id", "") == "self"):
                    attrs.add(tgt.attr)
    called = {node.attr for node in ast.walk(cls)
              if isinstance(node, ast.Attribute)
              and getattr(node.value, "id", "") == "self"}
    missing = sorted(a for a in called
                     if a.startswith("_") and not a.startswith("__")
                     and a not in defined and a not in attrs)
    assert not missing, "нет таких методов: %s" % ", ".join(missing)


def test_vector_params_are_gated():
    """Несовместимые параметры слоя должны гаситься, а не выбираться.

    Проверяется статикой: сам диалог headless не собрать, но правила
    доступности лежат в одном методе, и их отсутствие видно по коду.
    """
    src = open(VIEWER, encoding="utf-8").read()
    start = src.index("def _sync_vec_enabled")
    end = src.index("def _save_vec_opts", start)
    body = src[start:end]
    rules = {
        "тип точки только для точечных слоёв":
            "self.vec_kind.setEnabled(is_point)",
        "источник высоты не для скважин":
            "self.vec_zsrc.setEnabled(not wells)",
        "поле отметки только при высоте из поля":
            'self.vec_zfield.setEnabled(not wells and zsrc == "field")',
        "поля отметок только для скважин":
            "self.wells_fields.setEnabled(wells)",
        "своя Z гаснет у слоя без Z":
            "has_z = _layer_has_z(lyr)",
    }
    missing = [name for name, mark in rules.items() if mark not in body]
    assert not missing, "нет правил доступности: %s" % ", ".join(missing)


def test_sync_called_after_every_change():
    """Правила пересчитываются и при загрузке, и при любой правке."""
    src = open(VIEWER, encoding="utf-8").read()
    for fn in ("_load_vec_opts", "_save_vec_opts"):
        start = src.index("def %s" % fn)
        end = src.index("        def ", start + 10)
        assert "_sync_vec_enabled()" in src[start:end], fn


def test_checked_lists_filter_by_type():
    """Список один, поэтому отбор слоёв обязан фильтровать по типу.

    Без фильтра векторный слой уходил в чтение как растр, не
    открывался и попадал в «Пропущено», хотя рисовался телами.
    """
    src = open(VIEWER, encoding="utf-8").read()
    assert "_checked_of(QgsRasterLayer)" in src
    assert "_checked_of(QgsVectorLayer)" in src
    start = src.index("def _checked_of")
    end = src.index("        def ", start + 10)
    body = src[start:end]
    assert "isinstance(lyr, cls)" in body, "нет проверки типа"
    assert "_SCENE_KEY" in body, "строка «Сцена» должна пропускаться"


def test_vopts_read_through_defaults():
    """Показ обязан читать настройки слоя с умолчаниями.

    Прямое чтение словаря давало пустые настройки слою, свойства
    которого ни разу не открывали: полигоны с Z уходили в линии вместо
    тела. Заводить умолчания вправе только диалог и `_opts_of`.
    """
    src = open(VIEWER, encoding="utf-8").read()
    tree = ast.parse(src)
    allowed = {"_opts_of", "_load_vec_opts", "_save_vec_opts",
               "_pick_vec_color", "__init__"}
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name in allowed:
            continue
        for sub in _own_nodes(node):
            if isinstance(sub, ast.Attribute) and sub.attr == "_vopts":
                bad.append(node.name)
                break
    assert not bad, ("настройки читаются мимо умолчаний в %s"
                     % ", ".join(sorted(set(bad))))


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("ok:", fn.__name__)
    print("all %d tests passed" % len(fns))


if __name__ == "__main__":
    _run()
