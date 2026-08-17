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


def test_scene_items_know_their_layer():
    """Каждый элемент сцены кладётся через приёмник с хозяином.

    Без этого галка видимости не знает, что прятать, и приходится
    пересобирать сцену целиком.
    """
    src = open(VIEWER, encoding="utf-8").read()
    # прямое добавление допустимо в двух местах: внутри самого приёмника
    # и для метки опроса кликом, которая живёт вне списка сцены
    lines = src.split("\n")
    start = src[:src.index("def _add_item")].count("\n")
    end = start + 20
    direct = []
    for num, line in enumerate(lines, 1):
        if "self.view.addItem(" not in line:
            continue
        if start < num <= end:
            continue          # тело приёмника
        tail = "\n".join(lines[num - 3:num + 1])
        if "_pick_marker" in tail or "mk" in line:
            continue          # метка опроса кликом
        if "_draw_" in line:
            continue          # предпросмотр рисуемого контура
        direct.append(num)
    assert not direct, "элементы мимо _add_item в строках %s" % direct
    assert "def _add_item(self, item, owner=None)" in src


def test_toggle_hides_without_rebuild():
    """Переключение галки не должно звать полную пересборку."""
    src = open(VIEWER, encoding="utf-8").read()
    start = src.index("def _item_toggled")
    end = src.index("        def _schedule_rebuild", start)
    body = src[start:end]
    assert "setVisible(on)" in body, "видимость не переключается"
    assert "self.rebuild()" not in body, "галка зовёт полную пересборку"


def test_auto_rebuild_is_optional():
    """Автопересборку можно выключить: на тяжёлой сцене она мешает."""
    src = open(VIEWER, encoding="utf-8").read()
    start = src.index("def _schedule_rebuild")
    end = src.index("        def ", start + 10)
    body = src[start:end]
    assert "self.auto_rebuild.isChecked()" in body
    assert "_rebuild_timer.start" in body, "нет задержки перед сборкой"


def test_no_self_call_cycles():
    """Метод диалога не должен вызывать сам себя по кругу.

    Ловит рекурсию вроде той, что случилась при массовой замене вызовов:
    приёмник элементов сцены стал вызывать сам себя, и сборка падала
    с maximum recursion depth exceeded.
    """
    src = open(VIEWER, encoding="utf-8").read()
    tree = ast.parse(src)
    cls = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "ViewerDialog":
            cls = node
    assert cls is not None
    calls = {}
    for m in cls.body:
        if not isinstance(m, ast.FunctionDef):
            continue
        calls[m.name] = {
            n.func.attr for n in ast.walk(m)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and getattr(n.func.value, "id", "") == "self"}

    def cycle(start, path, seen):
        for nxt in calls.get(path[-1], ()):
            if nxt not in calls:
                continue
            if nxt == start:
                return path + [nxt]
            if nxt in seen:
                continue
            found = cycle(start, path + [nxt], seen | {nxt})
            if found:
                return found
        return None

    bad = []
    for name in calls:
        found = cycle(name, [name], {name})
        if found:
            bad.append(" -> ".join(found))
    assert not bad, "вызовы по кругу:\n  %s" % "\n  ".join(bad[:5])


def test_busy_cursor_wraps_the_rebuild():
    """Сборка ставит курсор ожидания и обязательно снимает его.

    Без finally часы остались бы висеть после сбоя, и окно выглядело бы
    вечно занятым. Снимается курсор только в одном месте, чтобы это
    нельзя было забыть.
    """
    src = open(VIEWER, encoding="utf-8").read()
    start = src.index("def rebuild(self):")
    end = src.index("        def _rebuild_scene", start)
    body = src[start:end]
    assert "self._busy(True)" in body
    assert "finally:" in body and "self._busy(False)" in body
    assert src.count("restoreOverrideCursor") == 1


def test_rebuild_button_only_without_autoupdate():
    """Кнопка сборки нужна только при снятой галке автообновления."""
    src = open(VIEWER, encoding="utf-8").read()
    assert "self.btn.setVisible(False)" in src
    assert "self.btn.setVisible(not on)" in src


def test_drawing_is_a_mode_not_a_query():
    """В режиме рисования клик ставит вершину, а не опрашивает модель.

    Иначе каждый клик печатал бы значения каналов и ставил красный шарик
    вместо того, чтобы строить контур.
    """
    src = open(VIEWER, encoding="utf-8").read()
    start = src.index("def _pick_at")
    end = src.index("        def ", start + 10)
    body = src[start:end]
    assert "if self._draw_mode:" in body
    assert "self._draw_add(" in body


def test_drawn_contour_feeds_the_clip():
    """Замкнутый контур сразу становится обрезкой."""
    src = open(VIEWER, encoding="utf-8").read()
    start = src.index("def _clip_rings")
    end = src.index("        def ", start + 10)
    assert "_DRAWN_KEY" in src[start:end]
    assert 'self.clip_combo.addItem(tr("Нарисованный контур")' in src


def test_hint_survives_the_whole_drawing():
    """Подсказка не должна гаснуть после первой же вершины."""
    src = open(VIEWER, encoding="utf-8").read()
    start = src.index("def _draw_status")
    end = src.index("        def ", start + 10)
    body = src[start:end]
    assert "Рисую контур" in body and "Вершин: %d." in body
    for fn in ("_draw_add", "_draw_undo"):
        s = src.index("def %s" % fn)
        e = src.index("        def ", s + 10)
        assert "_draw_status()" in src[s:e], fn


def test_right_button_belongs_to_drawing():
    """В режиме рисования правая кнопка снимает вершину, а не крутит."""
    src = open(VIEWER, encoding="utf-8").read()
    start = src.index("def mousePressEvent")
    end = src.index("        def mouseReleaseEvent", start)
    body = src[start:end]
    assert "self.draw_mode" in body and "self.undo_cb()" in body
    assert "ev.accept()" in body


def test_contour_follows_the_scene_centre():
    """Контур перерисовывается после каждой сборки сцены.

    Он живёт в координатах сцены, а центр меняется вместе с данными:
    после обрезки охват уменьшается, и линия, нарисованная по прежнему
    центру, повисает в стороне от модели.
    """
    src = open(VIEWER, encoding="utf-8").read()
    start = src.index("def _rebuild_scene")
    body = src[start:]
    assert "self._draw_refresh(" in body


def test_sketches_are_removed_not_just_forgotten():
    """Наброски убираются из сцены, а не только теряются ссылкой.

    Иначе прежняя линия остаётся висеть поверх модели навсегда:
    она живёт вне списка элементов сцены и сама не удаляется.
    """
    src = open(VIEWER, encoding="utf-8").read()
    start = src.index("def _rebuild_scene")
    end = src.index("            layers = self._checked_layers()", start)
    body = src[start:end]
    assert "self.view.removeItem(it)" in body
    assert "self._draw_line = self._draw_dots = None" in body


def test_click_respects_the_clip():
    """Клик не должен попадать по обрезанной части модели."""
    src = open(VIEWER, encoding="utf-8").read()
    assert "def _point_kept" in src
    start = src.index("def _hit_at")
    end = src.index("        def _pick_at", start)
    assert "self._point_kept(" in src[start:end]


def test_qt_enums_are_taken_by_name():
    """Перечисления Qt берутся через getattr, а не точкой.

    В Qt6 они стали вложенными, и неквалифицированное имя ломает модуль
    на новых сборках QGIS. Ветвление через hasattr не спасает: короткое
    имя всё равно остаётся в коде и попадает в проверки совместимости.
    """
    import re
    src = open(VIEWER, encoding="utf-8").read()
    names = ("Antialiasing", "Box", "Copy", "Checked", "Unchecked",
             "WaitCursor", "StrongFocus", "CustomContextMenu",
             "RightButton", "Key_Escape", "Key_Backspace",
             "ItemIsUserCheckable", "ItemIsEnabled")
    pat = re.compile(r"\b(QPainter|QFrame|QKeySequence|Qt)\.(%s)\b"
                     % "|".join(names))
    bad = []
    for num, line in enumerate(src.split("\n"), 1):
        if "getattr" in line:
            continue
        if pat.search(line):
            bad.append("%d: %s" % (num, line.strip()))
    assert not bad, "перечисления Qt точкой:\n  %s" % "\n  ".join(bad)


def test_no_exec_underscore():
    """exec_ снят в Qt6: вызываем exec, беря метод по имени."""
    src = open(VIEWER, encoding="utf-8").read()
    bad = [num for num, line in enumerate(src.split("\n"), 1)
           if ".exec_(" in line]
    assert not bad, "вызов exec_ в строках %s" % bad


def _load_clip_run():
    src = open(VIEWER, encoding="utf-8").read()
    s = src.index("        def _clip_run(self, pts):")
    e = src.index("        def _feature_z", s)
    body = src[s:e].replace("        def _clip_run", "def _clip_run")
    body = "\n".join(row[4:] if row.startswith("    ") else row
                     for row in body.split("\n"))
    ns = {}
    exec(compile(body, "viewer3d", "exec"), ns)   # nosec
    return ns["_clip_run"]


class _ClipDlg(object):
    def __init__(self, keep):
        self._keep = keep

    def _clip_ctx(self):
        return ([[(0, 0)]], [])

    def _point_kept(self, x, y):
        return self._keep(x, y)


def test_clip_splits_lines_into_runs():
    """Обрезка режет и векторы: линия рвётся там, где выходит из куска.

    Иначе изолинии и разломы торчали бы за краем обрезанной модели.
    """
    _ClipDlg._clip_run = _load_clip_run()
    pts = [(i, 0.0, 0.0) for i in range(10)]
    runs = _ClipDlg(lambda x, y: 3 <= x <= 6)._clip_run(pts)
    assert [[p[0] for p in r] for r in runs] == [[3, 4, 5, 6]]
    runs = _ClipDlg(lambda x, y: x < 2 or x > 7)._clip_run(pts)
    assert [[p[0] for p in r] for r in runs] == [[0, 1], [8, 9]]
    assert _ClipDlg(lambda x, y: False)._clip_run(pts) == []


def test_clip_context_is_computed_once():
    """Контур обрезки считается раз за сборку, а не на каждую вершину."""
    src = open(VIEWER, encoding="utf-8").read()
    assert "def _clip_ctx" in src
    start = src.index("def _point_kept")
    end = src.index("        def _hit_at", start)
    assert "self._clip_ctx()" in src[start:end]


def test_state_is_created_before_widgets():
    """Все поля состояния заводятся до первого виджета.

    Виджеты шлют сигналы уже при сборке окна: включённая по умолчанию
    кнопка показа разметки вызывала перерисовку раньше, чем появлялось
    поле сцены, и окно не открывалось вовсе.
    """
    src = open(VIEWER, encoding="utf-8").read()
    tree = ast.parse(src)
    cls = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "ViewerDialog":
            cls = node
    init = None
    for m in cls.body:
        if isinstance(m, ast.FunctionDef) and m.name == "__init__":
            init = m
    assert init is not None
    first_widget, state = None, {}
    for node in ast.walk(init):
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            if not (isinstance(tgt, ast.Attribute)
                    and getattr(tgt.value, "id", "") == "self"):
                continue
            # виджетом считаем только создание объекта: заглушка
            # вроде `self.view = None` это тоже состояние
            is_widget = isinstance(node.value, ast.Call)
            if not is_widget or tgt.attr.startswith("_"):
                state.setdefault(tgt.attr, node.lineno)
            elif first_widget is None or node.lineno < first_widget:
                first_widget = node.lineno
    late = sorted(k for k, v in state.items()
                  if first_widget and v > first_widget)
    assert not late, "состояние заводится после виджетов: %s" % ", ".join(late)


def test_handlers_survive_early_calls():
    """Обработчики, трогающие сцену, проверяют, что она уже есть.

    Виджет шлёт сигнал в момент создания, и обработчик выполняется
    посреди сборки окна. Дважды на этом падало открытие окна.
    """
    src = open(VIEWER, encoding="utf-8").read()
    assert "self.view = None" in src, "сцена не объявлена заранее"
    for fn in ("_draw_refresh", "_copy_png"):
        start = src.index("def %s" % fn)
        end = src.index("        def ", start + 10)
        assert "if self.view is None" in src[start:end], fn


def test_drawing_works_without_raster_surfaces():
    """Размечать можно и там, где растровых поверхностей нет.

    В сцене могут лежать одни изолинии: вершина берётся с уровня
    середины сцены, плановое положение от этого не меняется.
    """
    src = open(VIEWER, encoding="utf-8").read()
    assert "def _hit_plane" in src
    start = src.index("def _hit_at")
    end = src.index("        def _pick_at", start)
    assert "self._hit_plane(" in src[start:end]


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("ok:", fn.__name__)
    print("all %d tests passed" % len(fns))


if __name__ == "__main__":
    _run()
