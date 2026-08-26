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

import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
VIEWER = os.path.join(os.path.dirname(HERE), "viewer3d.py")
CORE = os.path.join(os.path.dirname(HERE), "viewer_core.py")
DIALOG = os.path.join(os.path.dirname(HERE), "viewer_dialog.py")


def _viewer_src():
    """Исходник окна вместе с вынесенными частями.

    Окно разделено на три файла: сам диалог, расчётная часть и точка
    входа. Проверки, которые ищут в тексте, должны видеть все три:
    иначе они находят не всё и молча слабеют.

    Диалог вернулся с отступом в четыре пробела: раньше оба класса
    жили внутри функции, и методы стояли на восьми. Проверки ищут
    по этому отступу, а он к поведению отношения не имеет.
    """
    out = []
    for path, pad in ((VIEWER, ""), (DIALOG, "    "), (CORE, "")):
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        if pad:
            text = "\n".join(
                pad + ln if ln.strip() else ln
                for ln in text.split("\n"))
        out.append(text)
    return "\n".join(out)


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
    tree = ast.parse(_viewer_src())
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
    src = _viewer_src()
    bad = []
    for num, line in enumerate(src.split("\n"), 1):
        if ".findData(" in line and "def _find_data" not in line:
            bad.append("%d: %s" % (num, line.strip()))
    assert not bad, ("используйте _find_data вместо findData:\n  %s"
                     % "\n  ".join(bad))


def test_find_data_matches_tuples():
    """Сам поиск обязан находить кортеж, ради которого затевался."""
    ns = {}
    src = _viewer_src()
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
    src = _viewer_src()
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
    src = _viewer_src()
    start = src.index("def _sync_vec_enabled")
    end = src.index("def _save_vec_opts", start)
    body = src[start:end]
    rules = {
        "тип точки только для точечных слоёв":
            "self._row(self.vec_kind, is_point)",
        "источник высоты не для скважин":
            "self._row(self.vec_zsrc, not wells)",
        "поле отметки только при высоте из поля или у призмы":
            "self._row(self.vec_zfield,",
        "поля отметок только для скважин":
            "self._row(self.wells_fields, wells)",
        "своя Z гаснет у слоя без Z":
            "has_z = _layer_has_z(lyr)",
    }
    missing = [name for name, mark in rules.items() if mark not in body]
    assert not missing, "нет правил доступности: %s" % ", ".join(missing)


def test_sync_called_after_every_change():
    """Правила пересчитываются и при загрузке, и при любой правке."""
    src = _viewer_src()
    for fn in ("_load_vec_opts", "_save_vec_opts"):
        start = src.index("def %s" % fn)
        end = src.index("        def ", start + 10)
        assert "_sync_vec_enabled()" in src[start:end], fn


def test_checked_lists_filter_by_type():
    """Список один, поэтому отбор слоёв обязан фильтровать по типу.

    Без фильтра векторный слой уходил в чтение как растр, не
    открывался и попадал в «Пропущено», хотя рисовался телами.
    """
    src = _viewer_src()
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
    src = _viewer_src()
    tree = ast.parse(src)
    # сохранение и чтение состояния работают со словарём целиком,
    # умолчания к ним отношения не имеют
    allowed = {"_opts_of", "_load_vec_opts", "_save_vec_opts",
               "_pick_vec_color", "__init__",
               "_state_save", "_state_load"}
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
    src = _viewer_src()
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
    src = _viewer_src()
    start = src.index("def _item_toggled")
    end = src.index("        def _schedule_rebuild", start)
    body = src[start:end]
    assert "setVisible(on)" in body, "видимость не переключается"
    assert "self.rebuild()" not in body, "галка зовёт полную пересборку"


def test_auto_rebuild_is_optional():
    """Автопересборку можно выключить: на тяжёлой сцене она мешает."""
    src = _viewer_src()
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
    src = _viewer_src()
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
    src = _viewer_src()
    start = src.index("def rebuild(self):")
    end = src.index("        def _rebuild_scene", start)
    body = src[start:end]
    assert "self._busy(True)" in body
    assert "finally:" in body and "self._busy(False)" in body
    assert src.count("restoreOverrideCursor") == 1


def test_lines_take_colour_from_the_layer_style():
    """Линии красятся по стилю слоя, как и тела.

    Изолинии почти всегда раскрашены по отметке. Один цвет на слой
    стирал раскраску целиком: вместо шкалы глубин в сцене шла ровная
    бурая паутина.
    """
    src = _viewer_src()
    start = src.index("def _vec_lines")
    end = src.index("        def _vec_points", start)
    body = src[start:end]
    assert "self._layer_colors(lyr)" in body
    assert "self._style_color(by_style, ft)" in body


def test_line_colour_falls_back_when_style_is_silent():
    """Если стиль цвета не дал, берётся запасной, а не пустота."""
    src = _viewer_src()
    start = src.index("def _vec_lines")
    body = src[start:src.index("\n        def ", start + 20)]
    assert 'fcol = self._style_color(by_style, ft) or "#7a5c3c"' in body


def test_lines_are_grouped_by_layer_and_colour():
    """Элемент сцены заводится на пару слой-цвет.

    Иначе разные цвета одного слоя слились бы в один элемент
    и получили общий цвет.
    """
    src = _viewer_src()
    start = src.index("# --- линии векторных слоёв")
    body = src[start:start + 1200]
    assert "by_layer.setdefault((lid_v, col)" in body


def test_elevation_can_come_from_a_surface():
    """Отметку можно брать с растрового слоя."""
    src = _viewer_src()
    assert '(tr("Отметка с поверхности"), "surf")' in src
    assert "def _zsurf_of" in src and "def _drape" in src
    assert 'o["zsurf"] = self.vec_zsurf.currentData()' in src
    assert 'self._row(self.vec_zsurf, not wells and zsrc == "surf")' in src


def test_drape_reads_every_vertex():
    """Отметка читается в каждой вершине, а не одна на объект.

    Иначе линия встала бы на общую отметку и повисла над рельефом
    или ушла под него.
    """
    src = _viewer_src()
    start = src.index("def _drape(self, pts, surf")
    body = src[start:src.index("\n        def ", start + 20)]
    assert "self._sample_layer(lyr, arr, gt, xs, ys," in body


def test_missing_elevation_cuts_the_feature():
    """Там, где у поверхности нет данных, объект обрезается.

    Ноль это отметка, а не отсутствие отметки: посадить туда вершину
    значило бы вживить её в чужой уровень.
    """
    src = _viewer_src()
    start = src.index("def _drape(self, pts, surf")
    body = src[start:src.index("\n        def ", start + 20)]
    assert "runs.append(cur)" in body and "cur = []" in body
    start2 = src.index("def _drape_mesh")
    mesh = src[start2:src.index("\n        def ", start2 + 20)]
    assert "good[f].all(axis=1)" in mesh


def test_surface_source_is_checked_before_use():
    """Слой без выбранной поверхности отказывается, а не молчит."""
    src = _viewer_src()
    start = src.index("def _z_available")
    body = src[start:src.index("\n        def ", start + 20)]
    assert 'zsrc == "surf"' in body
    assert "не выбрана поверхность" in body


def test_drape_reaches_points_lines_and_bodies():
    """Отметка с поверхности работает у точек, линий и тел."""
    src = _viewer_src()
    for name in ("def _vec_points", "def _vec_lines"):
        start = src.index(name)
        body = src[start:src.index("\n        def ", start + 20)]
        assert "self._zsurf_of(o)" in body, name
        assert "self._drape(pts, surf, off)" in body, name
    start = src.index("def _body_meshes")
    body = src[start:src.index("        def _vec_lines", start)]
    assert "surf_z = self._zsurf_of(o)" in body
    assert "self._drape_mesh(v, f, surf_z," in body


def test_surface_source_survives_a_flat_layer():
    """Слой без своей Z не теряет точки при укладке.

    Вершина без отметки отсеивается ещё при разборе геометрии,
    поэтому источнику с поверхности нужна временная отметка:
    настоящую даст поверхность.
    """
    src = _viewer_src()
    start = src.index("def _feature_z")
    body = src[start:src.index("\n        def ", start + 20)]
    at_surf = body.index('zsrc == "surf"')
    assert "return 0.0" in body[at_surf:at_surf + 400]


def test_drape_fills_the_edge_cell():
    """У края данных отметка добирается ближайшей ячейкой.

    Билинейной выборке нужны четыре соседа, и на границе она молчит
    даже там, где ячейка есть: это лишние разрывы линий.
    """
    src = _viewer_src()
    start = src.index("def _sample_layer")
    body = src[start:src.index("\n        def ", start + 20)]
    assert "nearest=False" in src[start:start + 200]
    assert "np.round((cx - gt[0]) / gt[1] - 0.5)" in body
    start2 = src.index("def _drape(self, pts, surf")
    drape = src[start2:src.index("\n        def ", start2 + 20)]
    assert "nearest=True" in drape


def test_vertical_offset_applies_to_every_source():
    """Сдвиг по вертикали работает поверх любого источника высоты."""
    src = _viewer_src()
    assert 'tr("Смещение по вертикали, м")' in src
    assert 'o["zoff"] = float(self.vec_zoff.value())' in src
    assert "def _zoff_of" in src
    start = src.index("def _feature_z")
    body = src[start:src.index("\n        def ", start + 20)]
    assert "off = self._zoff_of(opts)" in body
    assert "+ off" in body and "return off" in body
    start2 = src.index("def _drape(self, pts, surf")
    drape = src[start2:src.index("\n        def ", start2 + 20)]
    assert "z + off" in drape


def test_point_size_comes_from_style_or_parameter():
    """Размер точки берётся из стиля слоя либо задаётся числом.

    Размер маркера на карте задан в миллиметрах печати и в сцене сам
    по себе ничего не значит, поэтому пересчитывается от обычных двух
    миллиметров.
    """
    src = _viewer_src()
    assert 'tr("Размер точки, px (0 - из стиля)")' in src
    assert "def _style_size" in src
    start = src.index("def _vec_points")
    body = src[start:src.index("\n        def ", start + 20)]
    assert 'psz = float(o.get("psize", 0.0) or 0.0)' in body
    assert "7.0 * (float(mm) / 2.0)" in body


def test_point_size_reaches_the_scene():
    """Размер доезжает до элемента сцены отдельным массивом."""
    src = _viewer_src()
    start = src.index("for x, y, z, c, lid_v, psz, txt in vpoints")
    body = src[start:start + 2600]
    assert "sizes = np.array([r[2] for r in rows]" in body
    assert "size=sizes" in body


def test_style_reader_returns_colour_and_size():
    """Стиль отдаёт пару, а скрытый класс по-прежнему пустоту."""
    src = _viewer_src()
    start = src.index("def _layer_colors")
    body = src[start:src.index("\n        @staticmethod", start)]
    assert "out[ft.id()] = (sym.color().name(), size)" in body
    assert "out[ft.id()] = None" in body
    assert "self._style_color(by_style, ft)" in src


def test_point_record_is_read_by_slice():
    """Запись точки читается срезом, а не жёсткой распаковкой.

    В записи лежат координаты, цвет, слой, размер и подпись. Жёсткая
    распаковка ломалась на каждом новом поле, и сборка сцены падала
    с «too many values to unpack».
    """
    src = _viewer_src()
    start = src.index("def _rebuild_scene")
    body = src[start:]
    assert "tuple(p[:3]) for p in vpoints" in body
    assert "for x, y, z, _c, _l in vpoints" not in body


def test_point_record_length_is_consistent():
    """Запись точки собирается и разбирается одинаковым числом полей."""
    src = _viewer_src()
    start = src.index("def _vec_points")
    body = src[start:src.index("\n        def ", start + 20)]
    made = body[body.index("out.append(("):]
    made = made[:made.index("))") + 2]
    assert made.count(",") == 6, made
    assert "for x, y, z, c, lid_v, psz, txt in vpoints" in src


def test_point_labels_have_their_own_field():
    """Обычный точечный слой подписывается своим полем."""
    src = _viewer_src()
    assert 'tr("Поле подписи точек")' in src
    assert 'o["label"] = self.vec_label.currentData()' in src
    assert "self._row(self.vec_label, is_point and not wells)" in src
    start = src.index("def _vec_points")
    body = src[start:src.index("\n        def ", start + 20)]
    assert 'lbl_field = o.get("label")' in body


def test_marker_shape_is_a_setting():
    """Вид маркера выбирается в свойствах и доходит до сборки."""
    src = _viewer_src()
    assert 'tr("Вид маркера")' in src
    assert 'o["shape"] = self.vec_shape.currentData() or "circle"' in src
    start = src.index("def _rebuild_scene")
    body = src[start:]
    assert "flat = flat_marker_mesh(" in body
    assert "if flat is not None:" in body


def test_marker_size_row_follows_the_shape():
    """У круга размер в пикселях, у плоского значка в метрах.

    Обе строки сразу показывать незачем: единица у них разная,
    и видна должна быть та, что сейчас работает.
    """
    src = _viewer_src()
    start = src.index("def _sync_vec_enabled")
    body = src[start:src.index("\n        def _save_vec_opts", start)]
    assert 'flat = (self.vec_shape.currentData() or "circle") != "circle"' \
        in body
    assert "self._row(self.vec_msize, is_point and not wells and flat)" \
        in body
    assert "self._row(self.vec_psize, is_point and not wells and not flat)" \
        in body


def test_label_count_is_a_setting():
    """Число подписей задаётся слоем и ограничено потолком модуля."""
    src = _viewer_src()
    assert 'tr("Подписей не более")' in src
    assert 'o["nlab"] = int(self.vec_nlab.value())' in src
    start = src.index("def _rebuild_scene")
    body = src[start:]
    assert "lbl_cap = min(lbl_cap, int(n))" in body
    assert "self._add_point_labels(pt_labels, span, lbl_cap)" in body
    start2 = src.index("def _add_point_labels")
    lbl = src[start2:src.index("\n        def ", start2 + 20)]
    assert "cap <= 0" in lbl
    assert "shown >= cap" in lbl


def test_point_labels_are_thinned_and_capped():
    """Подписи прореживаются и имеют потолок.

    На слое в тысячи точек подписи налезают друг на друга и не
    читается ни одна, а каждая подпись это отдельный элемент сцены.
    """
    src = _viewer_src()
    assert "_MAX_POINT_LABELS" in src
    start = src.index("def _add_point_labels")
    body = src[start:src.index("\n        def ", start + 20)]
    assert "thin_labels_xy(" in body
    assert "shown >= cap" in body
    assert "_halo_text_item(gl)" in body


def test_labels_have_a_halo():
    """Подпись обводится контрастным цветом и не тонет в фоне.

    Одноцветный текст пропадает на пёстрой сцене: тёмный на тёмном,
    светлый на светлом.
    """
    src = _viewer_src()
    assert "def _halo_text_item" in src
    start = src.index("def _halo_text_item")
    body = src[start:src.index("\ndef _map_order", start)]
    assert "QPainterPath" in body
    assert "path.addText(pos, self.font, self.text)" in body
    assert "setWidthF(self.halo_width)" in body
    assert 'self.setGLOptions("translucent")' in body
    assert "self.offset" in body
    assert "TextItem = _halo_text_item(gl)" in src


def _dirty_hint_calls(body):
    """Ставит ли этот кусок кода подсказку о накопленных правках."""
    return "self._info_dirty(" in body


def test_elevation_clip_reaches_every_source():
    """Обрезка по отметке доходит до тел, линий, точек, поверхностей
    и вокселей.

    Контур и коридор режут только в плане, к высоте они отношения
    не имеют, поэтому отбор по отметке идёт отдельным шагом везде.
    """
    src = _viewer_src()
    assert "def z_range_mask" in src
    assert "def _z_kept" in src and "def _z_bounds" in src
    start = src.index("def _clip_tris")
    body = src[start:src.index("\n        def ", start + 20)]
    assert "self._z_kept(v[:, 2])" in body
    scene = src[src.index("def _rebuild_scene"):]
    assert "self._z_kept(top)" in scene and "self._z_kept(arr)" in scene
    vox = src[src.index("        def _vox_mesh"):]
    vox = vox[:vox.index("\n        def ")]
    assert "z_range_mask(zc, lo_z, hi_z)" in vox
    lines = src[src.index("def _vec_lines"):]
    lines = lines[:lines.index("\n        def ")]
    assert "self._z_kept([p[2]])" in lines


def test_graduated_style_is_read_by_ranges():
    """Градуированный стиль читается диапазонами, а не по объекту.

    На полумиллионе объектов запрос символа у каждого это полмиллиона
    вызовов QGIS. Диапазоны известны заранее: цвет находится по
    значению поля разом, поиском по границам.
    """
    src = _viewer_src()
    start = src.index("def _style_by_ranges")
    body = src[start:src.index("def _layer_colors", start)]
    assert "QgsGraduatedSymbolRenderer" in body
    assert "searchsorted" in body
    assert "classAttribute" in body
    # быстрый путь вызывается из чтения стиля
    lc = src[src.index("def _layer_colors"):]
    assert "self._style_by_ranges(lyr, rnd)" in lc


def test_categorized_style_is_read_by_value():
    """Категорийный стиль читается таблицей значение-цвет."""
    src = _viewer_src()
    start = src.index("def _style_by_ranges")
    body = src[start:src.index("def _layer_colors", start)]
    assert "QgsCategorizedSymbolRenderer" in body


def test_single_symbol_style_is_not_read_per_feature():
    """У слоя с одним символом цвет не спрашивается у каждого объекта.

    На блочной модели в полмиллиона точек это полмиллиона вызовов
    ради одного и того же цвета.
    """
    src = _viewer_src()
    start = src.index("def _layer_colors")
    body = src[start:src.index("\n        def ", start + 20)]
    assert "QgsSingleSymbolRenderer" in body
    assert "_OneStyle" in body


def test_one_style_answers_for_any_feature():
    """Единый стиль отвечает одинаково на любой номер объекта."""
    with open(os.path.join(os.path.dirname(HERE), "viewer_dialog.py"),
              encoding="utf-8") as fh:
        src = fh.read()
    start = src.index("class _OneStyle")
    body = src[start:src.index("class _PickView", start)]
    for name in ("def get", "def __contains__", "def __getitem__"):
        assert name in body, name


def test_one_style_reads_like_a_normal_style():
    """Единый стиль читается теми же местами, что и обычный.

    Иначе пришлось бы различать случай в каждом читателе, а это
    четыре места, и одно из них забыть проще простого.
    """
    with open(os.path.join(os.path.dirname(HERE), "viewer_dialog.py"),
              encoding="utf-8") as fh:
        src = fh.read()
    a = src.index("class _OneStyle")
    b = src.index("class _PickView", a)
    ns = {}
    exec(compile(src[a:b], "vd", "exec"), ns)   # nosec
    one = ns["_OneStyle"](("#28bceb", 2.0))
    empty = ns["_OneStyle"](None)

    class _Ft(object):
        def __init__(self, i):
            self._i = i

        def id(self):
            return self._i

    assert one.get(1) == one.get(999999) == ("#28bceb", 2.0)
    assert 42 in one and one[7] == ("#28bceb", 2.0)
    # снятый в легенде класс: пусто, значит объект не показываем
    assert empty.get(5) is None
    assert 5 in empty and empty[5] is None


def test_style_request_skips_geometry():
    """Стиль читается без геометрии и только по нужным полям.

    Геометрия для цвета не нужна, а на полумиллионе объектов её
    чтение это основная цена.
    """
    src = _viewer_src()
    start = src.index("def _layer_colors")
    body = src[start:src.index("\n        def ", start + 20)]
    assert "QgsFeatureRequest" in body
    assert "NoGeometry" in body
    assert "setSubsetOfAttributes" in body


def test_nothing_borrows_from_the_surface_loop():
    """Ниже обхода поверхностей не читают имён, заведённых только в нём.

    В сцене без поверхностей этот обход не выполняется ни разу,
    и всё, что читают тела, линии и точки, до него не доживает.
    Так падало дважды: сперва на прозрачности, потом на режиме
    отрисовки, поэтому проверка ищет весь класс, а не имена по одному.
    """
    src = open(os.path.join(os.path.dirname(HERE), "viewer_dialog.py"),
               encoding="utf-8").read()
    tree = ast.parse(src)
    fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and \
                node.name == "_rebuild_scene":
            fn = node
    assert fn is not None

    # обход поверхностей: самый ранний цикл по meshes
    loops = [st for st in ast.walk(fn)
             if isinstance(st, ast.For)
             and isinstance(st.iter, ast.Call)
             and getattr(st.iter.func, "id", "") == "enumerate"
             and "verts" in ast.dump(st.target)]
    assert loops, "цикл поверхностей не найден"
    loop = min(loops, key=lambda x: x.lineno)

    def names(node, ctx):
        return {n.id for n in ast.walk(node)
                if isinstance(n, ast.Name) and isinstance(n.ctx, ctx)}

    in_loop = names(loop, ast.Store) | names(loop.target, ast.Store)
    outside = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            if not (loop.lineno <= n.lineno <= loop.end_lineno):
                outside.add(n.id)
    bad = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) \
                and n.lineno > loop.end_lineno \
                and n.id in in_loop and n.id not in outside:
            bad.add("%s (строка %d)" % (n.id, n.lineno))
    assert not bad, "берут из обхода поверхностей: %s" % (
        ", ".join(sorted(bad)))


def test_every_toolbar_button_is_placed():
    """Кнопка панели попадает в панель, а не висит углом окна.

    `tool` только создаёт кнопку с родителем-диалогом; не добавив её
    в раскладку, получаешь кнопку в левом верхнем углу поверх всего.
    """
    import re
    src = _viewer_src()
    start = src.index("def tool(kind, text, slot")
    body = src[start:src.index("self.view.cancel_cb", start)]
    stray = re.findall(r"^\s+tool\(", body, re.M)
    assert not stray, "кнопка создана и не добавлена: %d шт." % len(stray)


def test_cap_is_built_by_polygonising_the_edges():
    """Крышка собирается из сети рёбер, а не обходом колец.

    У слитых граней стыки Т-образные: длинный прямоугольник упирается
    в два коротких, общего конца у рёбер нет, и кольцо не замыкается.
    Сеть рёбер сначала сшивается по узлам, потом из неё строятся
    полигоны, и порядок обхода не нужен вовсе.
    """
    src = _viewer_src()
    start = src.index("def _cap_cut")
    body = src[start:src.index("\n        def ", start + 20)]
    assert "polygonize" in body
    assert "unaryUnion" in body or "Union" in body
    assert "Т-образ" in body or "стык" in body


def test_ring_walking_breaks_on_a_t_junction():
    """Обход колец на Т-образном стыке рвётся, и это не лечится.

    Числовое обоснование замены: у слитых граней ребро низа не разбито
    там, где к нему подходит стенка. Узел стенки повисает со степенью
    один, кольцо через него не проходит, и крышка не строится.
    """
    import collections
    edges = [((0, 0), (10, 0)), ((10, 0), (10, 5)),
             ((10, 5), (5, 5)), ((5, 5), (0, 5)), ((0, 5), (0, 0)),
             ((5, 0), (5, 2))]          # стенка в середине низа
    adj = collections.defaultdict(list)
    for a, b in edges:
        adj[a].append(b)
        adj[b].append(a)
    deg = {k: len(x) for k, x in adj.items()}
    assert deg[(5, 0)] == 1, deg[(5, 0)]
    assert sum(1 for d in deg.values() if d == 1) == 2


def test_cap_edges_go_to_the_path_plane():
    """Рёбра среза переводятся в плоскость «путь вдоль линии - отметка».

    В ней срез плоский, и его можно собрать как обычный полигон.
    """
    src = _viewer_src()
    start = src.index("def _cap_cut")
    body = src[start:src.index("\n        def ", start + 20)]
    assert "lineLocatePoint" in body
    assert "interpolate" in body


def test_points_are_filtered_in_one_go():
    """Точки отбираются разом, а не по одной.

    На каждую точку шли два вызова отбора, и каждый строил массивы
    ради одного числа. На ста девяноста тысячах точек это давало
    пятьдесят пять секунд из шестидесяти.
    """
    src = _viewer_src()
    start = src.index("def _vec_points")
    body = src[start:src.index("\n        def ", start + 20)]
    assert "self._point_kept(" not in body
    assert "self._points_kept(" in body
    assert "self._z_kept(" in body


def test_budget_counts_what_lands_in_the_scene():
    """Бюджет вершин считается по построенному, а не по исходному.

    В слое каждый четырёхугольник несёт свои вершины, а в сцене после
    склейки их вдвое меньше. Считая по исходным, одно тело съедало
    весь предел, занимая на деле половину.
    """
    src = _viewer_src()
    start = src.index("def _body_meshes")
    body = src[start:src.index("def _vec_lines", start)]
    assert "used_verts" in body
    assert "nCoordinates" not in body
    # предел проверяется после сборки тела, а не до
    # предел проверяется после сборки тела, а не до
    at_build = body.index("v, f = weld(v, f)")
    at_check = body.index("used_verts + len(v) > budget")
    assert at_build < at_check, (at_build, at_check)


def test_body_is_welded_before_the_edge_test():
    """Тело склеивается до разбора рёбер.

    Меш приходит несклеенным: у каждого треугольника свои вершины,
    и по номерам каждое ребро выглядит краевым. Оболочка никогда
    не признавалась замкнутой, и крышка не строилась ни разу
    ни у кого. Заодно вершин становится втрое меньше.
    """
    src = _viewer_src()
    start = src.index("def _body_meshes")
    body = src[start:src.index("def _vec_lines", start)]
    at_weld = body.index("weld(")
    at_closed = body.index("_closed_and_border(")
    assert at_weld < at_closed, (at_weld, at_closed)
    assert "несклеен" in body or "склеива" in body


def test_cut_is_capped_even_when_not_watertight():
    """Крышка на срезе пробуется и у незамкнутой оболочки.

    Тело вокселей со слиянием граней не замкнуто по построению,
    и раньше срез оставался открытым: видно нутро, а тело выглядит
    россыпью плит. Хуже от попытки не станет: не вышло - остаётся
    как было.
    """
    src = _viewer_src()
    start = src.index("def _body_meshes")
    body = src[start:src.index("def _vec_lines", start)]
    at_cap = body.index("self._cap_cut(")
    head = body[:at_cap]
    # крышка больше не за условием замкнутости
    assert "_is_closed(v, f) and (rings0 or lines0)" not in head
    assert "не замкнут" in body or "незамкнут" in body


def test_open_cut_is_reported():
    """Если крышка не встала, об этом говорится.

    Иначе открытый срез выглядит поломкой тела, а причина в том,
    что оболочку собрали со слиянием граней.
    """
    src = _viewer_src()
    start = src.index("def _body_meshes")
    body = src[start:src.index("def _vec_lines", start)]
    assert "self._cap_open" in body


def test_vertical_faces_survive_the_clip():
    """Отвесная грань не теряется при резке по контуру.

    У вокселей стенки ячеек отвесные, и в плане такой треугольник
    вырождается в отрезок нулевой площади. Пересечение с контуром
    даёт пусто, и стенки пропадали целиком: у тела оставались одни
    горизонтальные грани, то есть низ.
    """
    src = _viewer_src()
    start = src.index("def _clip_tris")
    body = src[start:src.index("def _cap_cut", start)]
    assert "_plan_area" in body or "вырожд" in body
    assert "flat_tri" in body or "degen" in body


def _load_clip_tris():
    """Резчик граней с подставным диалогом: QGIS для него не нужен."""
    src = open(os.path.join(os.path.dirname(HERE), "viewer_dialog.py"),
               encoding="utf-8").read()
    a = src.index("    def _clip_tris")
    b = src.index("    def _cap_cut")
    body = "\n".join(ln[4:] if ln.startswith("    ") else ln
                     for ln in src[a:b].split("\n"))
    ns = {}
    exec(compile("import numpy as np\n" + body, "vd", "exec"), ns)  # nosec
    return ns["_clip_tris"]


def test_wall_is_cut_not_kept_whole():
    """Отвесная грань режется точно, а не остаётся целиком.

    Оставленная целиком, она торчит за контур, соседняя
    горизонтальная обрезана по нему, и между ними щель. Это и были
    дырки в теле.
    """
    import numpy as np
    from isoliner3d.viewer_core import clip_wall
    tri = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0],
                    [10.0, 0.0, 5.0]])
    v, f = clip_wall(tri, [(0.0, 0.5)])
    assert len(f) >= 1
    assert v[:, 0].max() <= 5.0 + 1e-9, v[:, 0].max()
    v2, f2 = clip_wall(tri, [(0.0, 1.0)])
    assert abs(v2[:, 0].max() - 10.0) < 1e-9
    assert len(clip_wall(tri, [])[1]) == 0
    # отметка сохраняется: стенка не оседает
    assert abs(v[:, 2].max() - 2.5) < 1e-6, v[:, 2].max()


def test_wall_clipping_is_wired_into_the_cutter():
    """Резчик правда зовёт точную резку стенок."""
    src = _viewer_src()
    start = src.index("def _clip_tris")
    body = src[start:src.index("def _clip_boundary", start)]
    assert "wall_cut" in body
    assert "clip_wall(tri, spans)" in body
    assert "keep_all | wall_cut" in body     # запасной путь без cg


def test_clip_makes_no_holes_inside_the_body():
    """Резка не рвёт тело в стороне от среза.

    Сквозная проверка на числах: тело вокселей строится, склеивается,
    режется, склеивается снова. Все краевые рёбра обязаны лежать
    в зоне среза. Хоть одно в глубине тела - значит резка теряет
    грани, и дырки оттуда.
    """
    import collections
    import numpy as np
    from isoliner3d import voxel
    from isoliner3d.iso3d import weld
    clip = _load_clip_tris()

    class _Dlg(object):
        _clip_seen = 0
        _clip_kept = 0

        class _S(object):
            def currentData(self):
                return "in"

        clip_side = _S()

        def _clip_geom(self):
            return None

        def _points_kept(self, xs, ys):
            return np.asarray(xs) < 40.0

        def _z_kept(self, zs):
            return np.ones(np.asarray(zs).shape, dtype=bool)

    _Dlg._clip_tris = clip
    occ = np.zeros((5, 7, 9), dtype=bool)
    occ[1:4, 1:6, 1:8] = True
    gt = (0.0, 10.0, 0.0, 70.0, 0.0, -10.0)
    v, f, _c, _o = voxel.voxel_mesh(occ, gt, 0.0, 5.0, merge=False)
    v, f = weld(v, f)
    v2, f2 = _Dlg()._clip_tris(v, f)
    v2, f2 = weld(v2, f2)
    e = collections.Counter()
    for tri in f2:
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]),
                     (tri[2], tri[0])):
            e[(a, b) if a < b else (b, a)] += 1
    border = [k for k, n in e.items() if n == 1]
    assert border, "срез не состоялся"
    # зона среза это последний уцелевший столбец ячеек, 30..40
    deep = [k for k in border
            if v2[k[0]][0] < 29.9 and v2[k[1]][0] < 29.9]
    assert not deep, "дырки в глубине тела: %d рёбер" % len(deep)


def test_voxel_wall_is_not_lost_by_the_corridor():
    """Стенка ячейки переживает обрезку коридором.

    У вокселей стенки отвесные, и в плане они вырождаются в отрезок.
    Раньше такие грани уходили в резку по контуру, где пересечение
    давало пусто, и от тела оставались одни горизонтальные грани.
    """
    import numpy as np
    clip = _load_clip_tris()

    class _Dlg(object):
        _clip_seen = 0
        _clip_kept = 0

        class _S(object):
            def currentData(self):
                return "corridor"

        clip_side = _S()

        def _clip_geom(self):
            return None

        def _points_kept(self, xs, ys):
            return np.asarray(xs) <= 10.0

        def _z_kept(self, zs):
            return np.ones(np.asarray(zs).shape, dtype=bool)

    _Dlg._clip_tris = clip
    d = _Dlg()
    wall = np.array([[8.0, 0.0, 0.0], [12.0, 0.0, 0.0],
                     [12.0, 0.0, 5.0], [8.0, 0.0, 5.0]])
    f = np.array([[0, 1, 2], [0, 2, 3]])
    _v, kept = d._clip_tris(wall, f)
    assert len(kept) == 2, len(kept)


def test_degenerate_triangle_is_kept_by_vertices():
    """Вырожденную грань решают по вершинам, а не резкой.

    Резать в плане её нечем: площадь нулевая. Оставляем целиком,
    если хоть одна вершина внутри: перелёт не больше ячейки.
    """
    src = _viewer_src()
    start = src.index("def _clip_tris")
    body = src[start:src.index("def _cap_cut", start)]
    assert "n_in > 0" in body or "n_in >= 1" in body


def test_window_title_carries_the_version():
    """Номер сборки виден в заголовке окна.

    Без него не отличить, какая версия стоит, и разбор чужого журнала
    начинается с гадания, а не с дела.
    """
    src = _viewer_src()
    start = src.index("self.setWindowTitle(")
    body = src[start - 900:start + 200]
    assert "metadata.txt" in body
    assert "version=" in body


def test_cap_line_is_printed_even_when_empty():
    """Строка о крышке печатается всегда, с причиной раннего выхода.

    Молчание нельзя отличить от старой сборки: и там и там строки
    просто нет.
    """
    src = _viewer_src()
    rep = src[src.index("def _clip_report"):]
    rep = rep[:rep.index("def _clip_geom")]
    assert "if self._cap_edges_seen:" not in rep
    assert "Ранний выход" in rep
    cap = src[src.index("def _cap_cut"):]
    cap = cap[:cap.index("\n        def ", 20)]
    assert "self._cap_why" in cap


def test_ring_walking_handles_the_real_cases():
    """Обход колец: вразнобой, несколько колец, незамкнутое.

    У замкнутой оболочки срез даёт замкнутые кольца, и обход точен.
    Полигонизация нужна только там, где кольцо рвётся: она посредник
    и решает за нас, где площадь.
    """
    from isoliner3d.viewer_core import walk_rings
    ring = [((0, 0), (10, 0)), ((10, 5), (10, 0)),
            ((10, 5), (0, 5)), ((0, 5), (0, 0))]
    got = walk_rings(ring)
    assert len(got) == 1 and len(got[0]) == 4, got
    two = ring + [((20, 0), (30, 0)), ((30, 0), (30, 5)),
                  ((30, 5), (20, 5)), ((20, 5), (20, 0))]
    assert len(walk_rings(two)) == 2
    assert walk_rings([((0, 0), (1, 0)), ((1, 0), (2, 0))]) == []


def test_cap_tries_rings_before_polygonize():
    """Точное идёт раньше посредника."""
    src = _viewer_src()
    start = src.index("def _cap_cut")
    body = src[start:src.index("\n        def ", start + 20)]
    at_walk = body.index("walk_rings(pairs)")
    at_poly = body.index("polygonize(")
    assert at_walk < at_poly, (at_walk, at_poly)


def test_clip_boundary_does_not_rely_on_one_call():
    """Граница области обрезки собирается из колец, если надо.

    Штатный вызов границы у полигона в некоторых сборках QGIS
    возвращает пусто. Тогда крышку строить не на чем, а грани поперёк
    границы выбрасываются целиком: отсюда дырки.
    """
    src = _viewer_src()
    assert "def _clip_boundary" in src
    start = src.index("def _clip_boundary")
    body = src[start:src.index("def _cap_cut", start)]
    assert "cg.boundary()" in body
    assert "asMultiPolygon" in body and "asPolygon" in body
    cap = src[src.index("def _cap_cut"):]
    assert "self._clip_boundary(cg)" in cap


def test_clip_area_is_repaired_when_invalid():
    """Негодная по геометрии область исправляется.

    Пересечение с негодной даёт пусто, и грани поперёк границы
    пропадают целиком.
    """
    src = _viewer_src()
    start = src.index("def _clip_geom")
    body = src[start:src.index("\n    def ", start + 20)]
    assert "isGeosValid" in body and "makeValid" in body


def test_cap_reports_its_own_numbers():
    """Крышка отчитывается: рёбра, отрезки на контуре, полигоны.

    По картинке не понять, чего не хватило: рёбра не нашлись, они
    не легли на контур, полигоны не собрались или не разбились.
    Четыре числа различают все четыре случая.
    """
    src = _viewer_src()
    start = src.index("def _cap_cut")
    end = src.index("\n        def ", start + 20)
    body = src[start:end]
    for name in ("_cap_edges_seen", "_cap_segs", "_cap_polys",
                 "_cap_bad"):
        assert name in body, name
    rep = src[src.index("def _clip_report"):]
    rep = rep[:rep.index("def _clip_geom")]
    assert "Крышка: краевых рёбер" in rep


def test_clipping_reports_what_it_cut():
    """Обрезка отчитывается: сколько срезано и чем именно.

    Когда от сцены остаётся горстка треугольников, по картинке
    не понять, кто их срезал: контур, коридор, сторона от линии или
    диапазон отметок. Отчёт называет источник, режим и оба числа.
    """
    src = _viewer_src()
    assert "def _clip_report" in src
    start = src.index("def _clip_report")
    body = src[start:src.index("def _clip_geom", start)]
    for part in ("Источник", "режим", "полуширина"):
        assert part in body, part
    scene = src[src.index("def _rebuild_scene"):]
    assert "self._clip_report(" in scene


def test_corridor_reports_the_distance_to_the_line():
    """Отчёт называет расстояние от линии до данных.

    Без него «срезало почти всё» не отличить от «линия проведена
    мимо»: числа одинаковые, а причины разные.
    """
    src = _viewer_src()
    start = src.index("def _clip_report")
    body = src[start:src.index("def _clip_geom", start)]
    assert "self._clip_dmin" in body and "self._clip_dmax" in body
    assert "мимо данных" in body
    keep = src[src.index("def _points_kept"):]
    keep = keep[:keep.index("def _point_kept")]
    assert "self._clip_dmin = min(" in keep


def test_clip_report_counts_both_sides():
    """В отчёте и что было, и что осталось: одно число без другого
    ничего не говорит."""
    src = _viewer_src()
    start = src.index("def _clip_report")
    body = src[start:src.index("def _clip_geom", start)]
    assert "self._clip_seen" in body and "self._clip_kept" in body


def test_elevation_clip_works_without_a_contour():
    """Отбор по отметке режет и сам по себе.

    Резка граней вызывалась только когда задан контур или коридор,
    и диапазон отметок без них не срабатывал вовсе: тело оставалось
    целым, а человек видел, что верхняя и нижняя плоскости не режут.
    """
    src = _viewer_src()
    start = src.index("def _body_meshes")
    body = src[start:src.index("def _vec_lines", start)]
    assert "self._z_active()" in body
    assert "rings0 or lines0 or self._z_active()" in body


def test_swapped_elevation_bounds_are_named():
    """Перепутанные границы называются, а не дают молча пустоту.

    z≥ -50 вместе с z≤ -100 невыполнимы, и сцена выходит пустой.
    Молчать об этом значит отправить человека искать причину
    в данных.
    """
    src = _viewer_src()
    assert "def _z_active" in src
    start = src.index("def _z_active")
    body = src[start:src.index("\n        def ", start + 20)]
    assert "lo > hi" in body or "hi < lo" in body


def test_elevation_bounds_can_be_cleared():
    """Обрезку по отметке можно снять одним движением.

    «Без границы» это минимум диапазона, минус десять миллионов.
    Спустить туда со ста метров можно было только набрав это число
    руками, то есть снять обрезку было нечем.
    """
    src = _viewer_src()
    assert "def _z_clear" in src
    start = src.index("def _z_clear")
    body = src[start:src.index("\n        def ", start + 20)]
    assert "for w in (self.zlo, self.zhi):" in body
    assert "w.setValue(-1e7)" in body
    # снимается и общей кнопкой очистки, и своей
    clear = src[src.index("def _clip_clear_all"):]
    clear = clear[:clear.index("\n        def ")]
    assert "self._z_clear(" in clear
    assert 'tool("zclear"' in src or "self._z_clear)" in src


def test_elevation_bounds_have_a_no_bound_value():
    """У полей есть значение «без границы», а не только числа."""
    src = _viewer_src()
    assert 'setSpecialValueText(tr("(нет)"))' in src
    start = src.index("def _z_bounds")
    body = src[start:src.index("\n        def ", start + 20)]
    assert "None if lo <= -1e7 + 1 else lo" in body


def test_drawing_result_keeps_the_rebuild_hint():
    """Готовая линия и контур не стирают подсказку об обновлении.

    Выбор нарисованной линии в списке обрезки помечает сцену
    устаревшей, и строка состояния говорит нажать «Обновить сцену».
    Следом сообщение о готовой линии затирало эту строку, и обрезка
    выглядела нерабочей: линия готова, а в сцене ничего не изменилось.
    """
    src = _viewer_src()
    for name in ("def _draw_line_done", "def _draw_close"):
        if name not in src:
            continue
        start = src.index(name)
        body = src[start:src.index("\n        def ", start + 20)]
        assert _dirty_hint_calls(body), name


def test_info_dirty_appends_the_hint():
    """Подсказка добавляется к сообщению, а не заменяет его."""
    src = _viewer_src()
    assert "def _info_dirty" in src
    start = src.index("def _info_dirty")
    body = src[start:src.index("\n        def ", start + 20)]
    assert '_dirty' in body
    assert "setText" in body


def test_props_do_not_decide_by_stale_widgets():
    """Подбор строк не запускается из показа свойств.

    Значения в виджетах к этому моменту могут принадлежать прежнему
    слою, и решать по ним, что показывать, нельзя. Строки подбираются
    в конце загрузки свойств, когда виджеты уже заполнены.
    """
    src = _viewer_src()
    start = src.index("def _sync_props")
    body = src[start:src.index("\n        def ", start + 20)]
    assert "self._sync_vec_enabled()" not in body
    load = src.index("def _load_vec_opts")
    lbody = src[load:src.index("\n        @staticmethod", load)]
    at_sync = lbody.index("self._sync_vec_enabled()")
    at_props = lbody.index("self._sync_props()")
    assert at_sync < at_props


def test_props_title_is_set_first():
    """Заголовок ставится раньше остального.

    Если дальше что-то сорвётся, окно скажет, чьи свойства в нём,
    а не останется с именем приложения в шапке.
    """
    src = _viewer_src()
    start = src.index("def _sync_props")
    body = src[start:src.index("\n        def ", start + 20)]
    assert (body.index("self._props.setWindowTitle(title)")
            < body.index("self.scene_box.setVisible(scene)"))


def test_source_switch_only_while_loading():
    """Источник высоты подменяется только во время загрузки свойств.

    Вне её значения в виджетах могут относиться к другому слою,
    и подмена записала бы чужую настройку.
    """
    src = _viewer_src()
    start = src.index("def _sync_vec_enabled")
    body = src[start:src.index("\n        def _save_vec_opts", start)]
    assert 'zsrc == "geom" and self._loading_opts' in body


def test_vector_properties_are_adaptive():
    """Строка, не относящаяся к слою, убирается, а не гасится.

    Погашенная строка занимает место и заставляет гадать, отчего она
    серая: у точечного слоя призмы не будет никогда.
    """
    src = _viewer_src()
    assert "def _row(widget, on)" in src
    start = src.index("def _sync_vec_enabled")
    body = src[start:src.index("\n        def ", start + 20)]
    for w in ("vec_kind", "vec_poly", "vec_zsrc", "vec_zfield",
              "vec_zsurf", "vec_zoff", "vec_base", "vec_htop",
              "vec_ztop", "wells_label", "wells_fields"):
        assert "self._row(self.%s," % w in body, w
    assert "setEnabled" not in body.replace(
        "self.draw_combo.setEnabled(self.sec_on.isChecked())", "")


def test_row_hides_its_label_too():
    """Прячется и подпись: одно поле спрятать мало."""
    src = _viewer_src()
    start = src.index("def _row(widget, on)")
    body = src[start:src.index("\n        def ", start + 20)]
    assert "labelForField" in body
    assert "lab.setVisible(on)" in body


def test_layer_colour_comes_only_from_the_style():
    """Своего цвета у векторного слоя больше нет.

    Он дублировал оформление слоя и стирал раскраску по отметке,
    а задаётся оно всё равно в самом слое.
    """
    src = _viewer_src()
    assert "vec_color_btn" not in src
    assert "_pick_vec_color" not in src
    assert "_sync_vec_swatch" not in src
    assert 'o.get("color")' not in src
    assert "col or by_style" not in src


def test_layer_list_follows_the_map_tree():
    """Список сцены строится в порядке дерева карты.

    `mapLayers` отдаёт словарь без порядка, и список выходил
    случайным: ни найти слой, ни понять, что рисуется поверх чего.
    """
    src = _viewer_src()
    assert "def _map_order" in src
    start = src.index("def refresh_layers")
    body = src[start:src.index("        def _opts_of", start)] \
        if "        def _opts_of" in src[start:] else src[start:start + 4000]
    assert "for lyr in _map_order(proj)" in body
    assert "proj.mapLayers().values()" not in body.split(
        "clip_combo")[0]


def test_map_order_prefers_the_tree():
    """Берётся порядок отрисовки дерева, а не словарь слоёв."""
    src = _viewer_src()
    start = src.index("def _map_order")
    body = src[start:src.index("def _layer_budget", start)]
    assert "layerOrder()" in body
    assert "findLayers()" in body
    assert "mapLayers().values()" in body


def test_upper_layers_are_drawn_over_lower():
    """Верхний слой карты получает больший подъём в сцене.

    Совпадающая геометрия иначе спорит за глубину: изолинии то видны,
    то тонут в поверхности, на которой лежат.
    """
    src = _viewer_src()
    assert "def _z_priority" in src and "def _draw_rank" in src
    start = src.index("def _z_priority")
    body = src[start:start + 800]
    assert "(n - rank)" in body
    start2 = src.index("def _rebuild_scene")
    scene = src[start2:]
    assert scene.count("self._z_priority(") >= 4


def test_query_point_can_be_cleared():
    """Точку опроса можно убрать: кликом мимо, клавишей и кнопкой."""
    src = _viewer_src()
    assert "def _pick_clear" in src
    start = src.index("def _pick_at")
    body = src[start:start + 700]
    assert "self._pick_clear()" in body
    start2 = src.index("def _draw_cancel")
    body2 = src[start2:start2 + 600]
    assert "self._pick_clear()" in body2
    assert 'tr("Снять обрезку, наброски и точку опроса")' in src
    assert "self._clip_clear_all" in src


def test_scene_list_follows_tree_changes():
    """Список обновляется сам при правке дерева карты."""
    src = _viewer_src()
    assert "def _tree_changed" in src
    for sig in ("layersAdded", "layersRemoved", "layerOrderChanged",
                "addedChildren", "removedChildren"):
        assert sig + ".connect(self._tree_changed)" in src, sig
    start = src.index("def _tree_changed")
    body = src[start:start + 700]
    assert "self.refresh_layers()" in body
    assert "self._mark_dirty(True)" in body


def test_scene_lives_in_the_project_crs():
    """Слои приводятся к системе координат проекта.

    Смена СК слоя не двигает записанные координаты, она меняет их
    толкование. Без преобразования слой в другой системе уезжал
    в сторону, и обновление сцены ничего не меняло.
    """
    src = _viewer_src()
    assert "def _xform" in src and "QgsCoordinateTransform" in src
    for name, tail in (("def _body_meshes", "        def _vec_lines"),
                       ("def _vec_lines", "        def _vec_points"),
                       ("def _vec_points", "        def _apply_filter"),
                       ("def _well_points", "        def _checked_of")):
        start = src.index(name)
        body = src[start:src.index(tail, start)]
        assert "tr_ = self._xform(lyr)" in body, name
        assert "g.transform(tr_)" in body, name


def test_raster_surface_is_reprojected():
    """Сетка растра строится в его координатах и переводится в проект."""
    src = _viewer_src()
    start = src.index("def _rebuild_scene")
    body = src[start:]
    assert "tr_r = self._xform(lyr)" in body
    assert "verts[:, 0], verts[:, 1] = self._xform_xy(" in body


def test_raster_is_sampled_in_its_own_crs():
    """Значения растра читаются в его системе, а не в системе сцены.

    Иначе окраска и опрос по клику брали бы значения мимо данных.
    """
    src = _viewer_src()
    start = src.index("def _sample_layer")
    body = src[start:start + 800]
    assert "self._xform(lyr, back=True)" in body
    start2 = src.index("            vals = {}")
    end2 = src.index('prof.add("color")', start2)
    colour = src[start2:end2]
    assert "sample_bilinear(" not in colour
    assert colour.count("self._sample_layer(") == 3


def test_clip_is_taken_back_to_the_layer_crs():
    """Обрезка растра считается по его сетке, значит и контур туда же."""
    src = _viewer_src()
    assert "def _clip_for_layer" in src
    start = src.index("def _rebuild_scene")
    body = src[start:]
    assert "lclip, lclip_lines = self._clip_for_layer(" in body
    assert "self._clip_array(top, gt, lclip)" in body
    assert "self._clip_array(arr, gt, lclip)" in body


def test_clip_rings_come_in_project_crs():
    """Контур обрезки приводится к системе проекта при чтении."""
    src = _viewer_src()
    start = src.index("def _clip_rings")
    body = src[start:src.index("        def _clip_by_lines", start)]
    assert "tr_ = self._xform(lyr)" in body
    assert "g.transform(tr_)" in body


def test_surface_takes_the_layer_ramp():
    """Поверхность красится шкалой самого слоя.

    Читается то же оформление, что рисует карту, поэтому растр
    на холсте и поверхность в сцене выходят одной расцветки.
    """
    src = _viewer_src()
    assert "def _ramp_from_renderer" in src
    assert "def ramp_colors" in src
    start = src.index("            vals = {}")
    end = src.index('prof.add("color")', start)
    body = src[start:end]
    assert "_ramp_from_renderer(lyr_c)" in body
    assert "self._style_ramp[lid] = ramp_colors(" in body


def test_explicit_colour_source_beats_the_layer_ramp():
    """Заданный канал окраски и внешний растр главнее шкалы слоя.

    Их выбрали руками, и подменять этот выбор оформлением нельзя.
    """
    src = _viewer_src()
    start = src.index("            vals = {}")
    end = src.index('prof.add("color")', start)
    body = src[start:end]
    at_band = body.index("if cband > 0:")
    at_attr = body.index("if alayer is not None:")
    at_ramp = body.index("_ramp_from_renderer(lyr_c)")
    assert at_band < at_attr < at_ramp


def test_layer_ramp_wins_over_the_shared_scale():
    """Своя шкала слоя главнее общей шкалы сцены.

    Общая шкала растягивается на все слои сразу, и расцветка ушла бы
    от карты именно там, где её просили повторить.
    """
    src = _viewer_src()
    start = src.index("ramp_c = self._style_ramp.get(lid)")
    body = src[start:start + 700]
    assert body.index("ramp_c is not None") < body.index("elif attr")


def test_ramp_colours_are_reset_every_rebuild():
    src = _viewer_src()
    start = src.index("def _rebuild_scene")
    assert "self._style_ramp = {}" in src[start:]


def test_points_are_drawn_opaque():
    """Точки рисуются непрозрачно.

    У точек в pyqtgraph по умолчанию аддитивное смешение. Фон сцены
    почти белый, и такие точки выцветают в него целиком: их просто
    не видно.
    """
    src = _viewer_src()
    start = src.index("GLScatterPlotItem(pos=arr")
    assert "glOptions='opaque'" in src[start:start + 300]


def test_points_take_colour_from_the_layer_style():
    """Точки красятся по стилю слоя, как линии и тела."""
    src = _viewer_src()
    start = src.index("def _vec_points")
    end = src.index("        def _apply_filter", start)
    body = src[start:end]
    assert "self._layer_colors(lyr)" in body
    assert "self._style_color(by_style, ft)" in body


def test_hidden_style_classes_stay_out_of_the_scene():
    """Снятый в легенде класс не попадает в сцену.

    Снимая класс на карте, пользователь убирает его отовсюду,
    и сцена не должна показывать то, чего на карте уже нет.
    """
    src = _viewer_src()
    assert "def _style_hides" in src
    for name, tail in (("def _body_meshes", "        def _vec_lines"),
                       ("def _vec_lines", "        def _vec_points"),
                       ("def _vec_points", "        def _apply_filter")):
        start = src.index(name)
        body = src[start:src.index(tail, start)]
        assert "self._style_hides(by_style, ft)" in body, name


def test_unreadable_style_does_not_hide_everything():
    """Нечитаемый стиль это не «спрятать всё».

    Объекта в таблице нет вовсе, и прятать его нельзя: иначе одна
    осечка чтения рендерера оставляла бы пустую сцену.
    """
    src = _viewer_src()
    start = src.index("def _style_hides")
    body = src[start:start + 700]
    assert "ft.id() in by_style and by_style[ft.id()] is None" in body


def test_budget_is_split_only_among_body_layers():
    """Бюджет вершин делится между слоями, которые идут телами.

    Отмеченный слой линий из этого бюджета не берёт ничего, а раньше
    попадал в делитель и забирал половину: тела показывались
    не полностью без всякой причины.
    """
    src = _viewer_src()
    assert "def _body_layer_count" in src
    start = src.index("def _body_meshes")
    end = src.index("        def _vec_lines", start)
    body = src[start:end]
    assert "self._body_layer_count()" in body
    assert "len(self._checked_vec_layers())" not in body


def test_budget_message_names_the_numbers():
    """Сообщение об урезании называет вершины и предел.

    Без чисел «показаны первые 237» читается как нехватка памяти,
    и крутить пользователю нечего.
    """
    src = _viewer_src()
    start = src.index("def _body_meshes")
    end = src.index("        def _vec_lines", start)
    body = src[start:end]
    assert "набрано %d вершин из %d" in body


def test_vertex_cap_is_a_setting():
    """Предел вершин задаётся в свойствах сцены и живёт в проекте."""
    src = _viewer_src()
    assert 'tr("Предел вершин в сцене (тысяч)")' in src
    assert '"vert_cap": int(self.vert_cap.value())' in src
    assert 'state.get(' in src and '"vert_cap"' in src
    assert "def _vert_cap" in src


def test_rebuild_is_a_button_not_a_side_effect():
    """Сцена считается по кнопке, а не на каждую отметку.

    Отметка видимости и ползунок только записывают, что показать.
    Автосборка остаётся галкой и по умолчанию снята: на тяжёлом кубе
    пересборка на каждый щелчок и выглядит зависанием.
    """
    src = _viewer_src()
    assert "self.auto_rebuild.setChecked(False)" in src
    assert "self.btn.setVisible(False)" not in src
    assert "self.auto_rebuild.toggled.connect(self._auto_toggled)" in src


def test_rebuild_button_comes_first_and_is_separated():
    """Кнопка обновления стоит первой и отделена от остальных."""
    src = _viewer_src()
    start = src.index("tb.setSpacing(2)")
    end = src.index('self.tools.setObjectName', start)
    body = src[start:end]
    at_btn = body.index("tb.addWidget(self.btn)")
    at_sep = body.index("tb.addWidget(sep)")
    at_rest = body.index("for b in (btn_top")
    assert at_btn < at_sep < at_rest


def test_pending_changes_are_marked():
    """Накопленные правки видны на кнопке и в строке состояния.

    Без отметки снятая автосборка выглядела бы поломкой: настройки
    поменялись, картинка прежняя, и почему - непонятно.
    """
    src = _viewer_src()
    start = src.index("def _schedule_rebuild")
    end = src.index("        def _load_opts", start)
    body = src[start:end]
    assert "self._mark_dirty(True)" in body
    assert 'setProperty("dirty"' in body
    assert 'dirty=\\"yes\\"' in src or 'dirty=\"yes\"' in src


def test_dirty_flag_is_cleared_after_rebuild():
    """После сборки отметка снимается, иначе подсветка не погаснет."""
    src = _viewer_src()
    start = src.index("def rebuild(self")
    end = src.index("        def _rebuild_scene", start)
    body = src[start:end]
    assert "self._mark_dirty(False)" in body
    assert body.index("finally:") < body.index("self._mark_dirty(False)")


def test_drawing_is_a_mode_not_a_query():
    """В режиме рисования клик ставит вершину, а не опрашивает модель.

    Иначе каждый клик печатал бы значения каналов и ставил красный шарик
    вместо того, чтобы строить контур.
    """
    src = _viewer_src()
    start = src.index("def _pick_at")
    end = src.index("        def ", start + 10)
    body = src[start:end]
    assert "if self._draw_mode:" in body
    assert "self._draw_add(" in body


def test_drawn_contour_feeds_the_clip():
    """Замкнутый контур сразу становится обрезкой."""
    src = _viewer_src()
    start = src.index("def _clip_rings")
    end = src.index("        def ", start + 10)
    assert "_DRAWN_KEY" in src[start:end]
    assert 'self.clip_combo.addItem(tr("Нарисованный контур")' in src


def test_hint_survives_the_whole_drawing():
    """Подсказка не должна гаснуть после первой же вершины."""
    src = _viewer_src()
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
    src = _viewer_src()
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
    src = _viewer_src()
    start = src.index("def _rebuild_scene")
    body = src[start:]
    assert "self._draw_refresh(" in body


def test_sketches_are_removed_not_just_forgotten():
    """Наброски убираются из сцены, а не только теряются ссылкой.

    Иначе прежняя линия остаётся висеть поверх модели навсегда:
    она живёт вне списка элементов сцены и сама не удаляется.
    """
    src = _viewer_src()
    start = src.index("def _rebuild_scene")
    end = src.index("            layers = self._checked_layers()", start)
    body = src[start:end]
    assert "self.view.removeItem(it)" in body
    assert "self._draw_line = self._draw_dots = None" in body


def test_click_respects_the_clip():
    """Клик не должен попадать по обрезанной части модели."""
    src = _viewer_src()
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
    src = _viewer_src()
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
    src = _viewer_src()
    bad = [num for num, line in enumerate(src.split("\n"), 1)
           if ".exec_(" in line]
    assert not bad, "вызов exec_ в строках %s" % bad


def _load_clip_run():
    src = _viewer_src()
    s = src.index("        def _clip_run(self, pts):")
    # До следующего метода, какой бы он ни был: привязка к имени
    # соседа ломалась каждый раз, когда рядом появлялся новый.
    e = src.index("\n        def ", s + 20) + 1
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
    src = _viewer_src()
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
    src = _viewer_src()
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
    src = _viewer_src()
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
    src = _viewer_src()
    assert "def _hit_plane" in src
    start = src.index("def _hit_at")
    end = src.index("        def _pick_at", start)
    assert "self._hit_plane(" in src[start:end]


def test_prism_is_clipped_by_geometry_not_by_centre():
    """Призма режется контуром, а не выбрасывается целиком по центру.

    Пересечение даёт новый контур, и призма строится по нему заново
    вместе с крышками: срез получается закрытым, а не дырой в оболочке.
    """
    src = _viewer_src()
    assert "def _clip_geom" in src
    start = src.index('if mode == "prism":')
    end = src.index("zb = self._base_z", start)
    body = src[start:end]
    assert "self._clip_geom()" in body
    assert "g.intersection(cg)" in body and "g.difference(cg)" in body


def test_clipped_prism_skips_the_cache():
    """У обрезанного объекта геометрия своя, ключ кэша по объекту соврёт."""
    src = _viewer_src()
    start = src.index('if mode == "prism":')
    end = src.index("out.append((v, f, nm,", start)
    body = src[start:end]
    assert "_tessellate(g, zt)" in body and "_tri_cached(" in body


def _load_kept():
    src = _viewer_src()

    def grab(name, nxt):
        s = src.index("        def %s(" % name)
        e = src.index("        def %s(" % nxt, s)
        body = src[s:e].replace("        def ", "def ", 1)
        rows = [row[4:] if row.startswith("    ") else row
                for row in body.split("\n")]
        return "\n".join(rows)

    ns = {}
    code = ("import numpy as np\n"
            + grab("_points_kept", "_point_kept") + "\n"
            + grab("_point_kept", "_hit_plane"))
    exec(compile(code, "viewer3d", "exec"), ns)   # nosec
    return ns["_points_kept"], ns["_point_kept"]


class _Combo(object):
    def __init__(self, value):
        self._value = value

    def currentData(self):
        return self._value


class _Width(object):
    def __init__(self, value):
        self._value = value

    def value(self):
        return self._value


class _KeptDlg(object):
    def __init__(self, rings, lines, mode, width=250.0):
        self._rings, self._lines = rings, lines
        self.clip_side = _Combo(mode)
        self.clip_width = _Width(width)
        # счётчики отчёта: отбор их ведёт, и без них он падает
        self._clip_dmin = float("inf")
        self._clip_dmax = 0.0

    def _clip_ctx(self):
        return (self._rings, self._lines)


def test_vector_and_point_selection_agree():
    """Отбор разом по массиву обязан совпадать с поточечным.

    Поточечная проверка на десятках тысяч треугольников занимала десятки
    секунд, поэтому появился массовый вариант, и он не должен расходиться
    с прежним ни на одной точке.
    """
    import numpy as np
    many, one = _load_kept()
    _KeptDlg._points_kept = many
    _KeptDlg._point_kept = one
    rng = np.random.RandomState(0)
    xs = rng.uniform(-5, 15, 300)
    ys = rng.uniform(-5, 15, 300)
    ring = [(0, 0), (10, 0), (10, 10), (0, 10)]
    for dlg in (_KeptDlg([ring], [], "in"),
                _KeptDlg([ring], [], "out"),
                _KeptDlg([], [[(0, 5), (10, 5)]], "corridor", 2.0),
                _KeptDlg([], [[(0, 5), (10, 5)]], "left")):
        a = dlg._points_kept(xs, ys)
        b = np.array([dlg._point_kept(x, y) for x, y in zip(xs, ys)])
        assert (a == b).all()


def test_old_solid_clipping_is_gone():
    """Прежние подходы к срезу убраны, а не оставлены рядом.

    Отбор по центру с лентой между отметками давал рваную оболочку.
    Работает разрезка граней по контуру с крышкой по кольцам среза,
    и две реализации одного и того же держать рядом незачем.
    """
    src = _viewer_src()
    assert "def _clip_solid" not in src
    assert "cap_ribbon" not in src
    assert "def _cap_cut" in src


def _load_ring_normal():
    """Нормаль кольца вынесена в viewer_core и импортируется.

    Раньше здесь вырезался кусок исходника, потому что импорт окна
    тянет QGIS.
    """
    from isoliner3d.viewer_core import _ring_normal
    return _ring_normal


def test_ring_normal_handles_vertical_walls():
    """Нормаль кольца берётся по всему кольцу, а не по трём точкам.

    Вертикальная стенка в плане вырождается в линию, поэтому разбивка
    по плану давала мусор: кольцо надо класть в его собственную
    плоскость.
    """
    normal = _load_ring_normal()
    wall = [(0, 0, 0), (10, 0, 0), (10, 0, 5), (0, 0, 5)]
    n = normal(wall)
    assert abs(float(n[2])) < 1e-9, n
    flat = [(0, 0, 7), (10, 0, 7), (10, 10, 7), (0, 10, 7)]
    assert abs(abs(float(normal(flat)[2])) - 1.0) < 1e-9
    assert normal([(0, 0, 0), (1, 0, 0), (2, 0, 0)]) is None


def test_solid_rings_are_triangulated_in_plane():
    """Объект с переменной Z разбирается по кольцам, а не по плану.

    Разбор идёт через кэш, но именно по кольцам: у плоской разбивки
    вертикальная стенка вырождается в линию и даёт мусор.
    """
    src = _viewer_src()
    assert "def _tris_from_geometry" in src
    start = src.index("def _body_meshes")
    end = src.index("        def _vec_lines", start)
    body = src[start:end]
    assert "spatial=True" in body
    tri = src[src.index("def _tri_cached"):src.index("def tri_cache_clear")]
    assert "_tris_from_geometry(geom) if spatial" in tri


def test_body_triangulation_goes_through_the_cache():
    """Разбор тел не повторяется на каждую сборку.

    Слой из 237 тел собирался семнадцать секунд, и ровно столько же
    уходило на каждое нажатие кнопки обновления.
    """
    src = _viewer_src()
    start = src.index("def _body_meshes")
    end = src.index("        def _vec_lines", start)
    body = src[start:end]
    assert "_tris_from_geometry(g)" not in body
    assert "_tri_cached(lyr, ft, g, None, prof," in body


def test_spatial_key_is_separate():
    """У разбора по кольцам свой ключ кэша, не отметка."""
    src = _viewer_src()
    tri = src[src.index("def _tri_cached"):src.index("def tri_cache_clear")]
    assert '"3d" if spatial else zfix' in tri
    key = src[src.index("def _tri_key"):src.index("def _tri_cached")]
    assert "isinstance(zfix, str)" in key


def test_faces_are_turned_up_not_duplicated():
    """Грани разворачиваются нормалью вверх, а не дублируются.

    Копия грани ложится ровно на оригинал, и две грани начинают спорить
    за глубину: появляются полосы, а цвет уходит в чёрный.
    """
    src = _viewer_src()
    start = src.index("def _tris_from_geometry")
    end = src.index("def _flat_z", start)
    body = src[start:end]
    assert "flip = nz < 0" in body
    assert "np.vstack([f_all, f_all[:, ::-1]])" not in body


def test_face_orientation_flips_only_downward():
    """Грань нормалью вверх остаётся, грань вниз разворачивается."""
    import numpy as np
    src = _viewer_src()
    start = src.index("    v_all, f_all = np.vstack(verts), np.vstack(faces)")
    end = src.index("    return v_all, f_all", start)
    end += len("    return v_all, f_all")
    body = src[start:end].replace(
        "    v_all, f_all = np.vstack(verts), np.vstack(faces)\n", "")
    ns = {"np": np}
    exec(compile("def orient(v_all, f_all, both_sides=True):\n" + body,
                 "viewer3d", "exec"), ns)          # nosec
    v = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], float)
    up = np.array([[0, 1, 2]], np.int64)
    dn = np.array([[0, 2, 1]], np.int64)
    assert ns["orient"](v, up)[1].tolist() == [[0, 1, 2]]
    assert ns["orient"](v, dn)[1].tolist() != [[0, 2, 1]]


def test_colours_come_from_the_layer_style():
    """Цвет объекта берётся из стиля слоя, своей легенды не заводим.

    Раскраска уже лежит в стиле и сохраняется вместе с проектом,
    поэтому карта и объём выглядят одинаково.
    """
    src = _viewer_src()
    assert "def _layer_colors" in src
    start = src.index("def _layer_colors")
    end = src.index("        def _body_meshes", start)
    assert "symbolForFeature" in src[start:end]
    body = src[src.index("def _body_meshes"):]
    assert "self._style_color(by_style, ft)" in body


def test_belts_are_clipped_by_geometry():
    """Пояса режутся по контуру, а не выбрасываются по центру объекта.

    Это открытые поверхности, крышка на срезе им не нужна, поэтому
    режутся сами грани и край проходит по контуру обрезки.
    """
    src = _viewer_src()
    start = src.index("def _body_meshes")
    end = src.index("        def _vec_lines", start)
    body = src[start:end]
    assert "self._clip_tris(v, f)" in body
    assert "_point_kept(cxx" not in body


def test_barycentric_z_restores_heights():
    """Новая вершина на линии реза берёт высоту из плоскости грани.

    Иначе обрезанный треугольник ложился бы на нулевую отметку
    и пояс рвался бы по высоте.
    """
    import numpy as np
    src = _viewer_src()
    a = src.index("def _bary_z(")
    b = src.index("def _flat_z(")
    ns = {}
    exec(compile("import numpy as np\n" + src[a:b],   # nosec
                 "viewer3d", "exec"), ns)
    bary = ns["_bary_z"]
    tri = np.array([[0, 0, 0], [10, 0, 10], [0, 10, 20]], float)
    for (x, y), want in zip(tri[:, :2], (0.0, 10.0, 20.0)):
        got = float(bary(tri, np.array([x]), np.array([y]))[0])
        assert abs(got - want) < 1e-6, (x, y, got, want)
    mid = float(bary(tri, np.array([10 / 3.0]), np.array([10 / 3.0]))[0])
    assert abs(mid - 10.0) < 1e-6, mid


def test_edge_triangles_are_cut_not_dropped():
    """Грань, пересечённая контуром, режется, а не отбирается по центру.

    У пояса встречаются треугольники крупнее коридора: по центру они
    либо торчали за краем, либо пропадали целиком.
    """
    src = _viewer_src()
    start = src.index("def _clip_tris")
    end = src.index("        def _clip_geom", start)
    body = src[start:end]
    assert "n_in == 3" in body and "(n_in > 0) & (n_in < 3)" in body
    assert "_bary_z(tri" in body


def test_closed_shell_is_recognised():
    """Замкнутая оболочка отличается от открытого пояса по рёбрам.

    Поясу крышка на срезе не нужна и портит картинку, телу обязательна:
    без неё сквозь срез видна изнанка.
    """
    import numpy as np
    src = _viewer_src()
    a = src.index("def _is_closed(")
    b = src.index("def _bary_z(")
    ns = {}
    exec(compile(src[a:b], "viewer3d", "exec"), ns)      # nosec
    closed = ns["_is_closed"]
    v = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                  [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], float)
    f = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
                  [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
                  [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]], np.int64)
    assert closed(v, f) is True
    assert closed(v, f[2:]) is False
    assert closed(v, np.zeros((0, 3), np.int64)) is False


def test_cap_is_tried_and_its_failure_is_named():
    """Крышка пробуется всегда, а неудача называется числом.

    Раньше она строилась только замкнутым телам, а замкнутых
    не бывало вовсе: меш приходил несклеенным. Теперь попытка идёт
    всегда, а если оболочка разорвана, в журнал идёт число краевых
    рёбер и что с этим делать.
    """
    src = _viewer_src()
    start = src.index("def _body_meshes")
    end = src.index("        def _vec_lines", start)
    body = src[start:end]
    assert "_closed_and_border(v, f)" in body
    assert "self._cap_cut(v, f)" in body
    assert "self._cap_border" in body


def test_every_surface_branch_is_exported():
    """Все ветки поверхностей попадают в выгрузку.

    Текстурированная поверхность рисуется своей веткой и пропускала
    выгрузку: в файле оставались только те слои, что рисуются цветом.
    """
    src = _viewer_src()
    start = src.index("def _rebuild_scene")
    body = src[start:]
    assert body.count("self._keep_for_export(") >= 3


def test_iso_mode_is_wired():
    """Режим изоповерхности доходит от свойств до сборки сцены."""
    src = _viewer_src()
    assert '(tr("Изоповерхность по кубу"), "iso")' in src
    assert "def _iso_mesh" in src
    start = src.index("def _rebuild_scene")
    body = src[start:]
    assert 'if mode == "iso":' in body
    assert "self._iso_mesh(\n                            lyr, o, prof)" in body


def test_iso_uses_cube_convention():
    """Отметка первого уровня и шаг берутся из метаданных грида.

    Чтение куба вынесено в общий разбор, изоповерхность и воксели
    берут его оттуда и потому читают одну и ту же конвенцию.
    """
    src = _viewer_src()
    start = src.index("        def _iso_mesh")
    body = src[start:src.index("\n        def ", start + 20)]
    assert "self._cube_arrays(lyr)" in body
    assert "isosurface_levels(" in body
    cube = src[src.index("        def _cube_arrays"):]
    cube = cube[:cube.index("\n        def ")]
    assert '"Z0"' in cube and '"DZ"' in cube


def test_iso_levels_are_coloured_and_layered():
    """Несколько оболочек красятся шкалой, наружная прозрачнее.

    Иначе внутренних не видно вовсе, а ради них всё и строится.
    """
    src = _viewer_src()
    assert 'tr("Оболочек по отсечке")' in src
    assert 'o["iso_count"]' in src or "iso_count=int(" in src
    start = src.index("        def _iso_mesh")
    body = src[start:src.index("\n        def ", start + 20)]
    assert "np.linspace(base" in body
    assert "colormap(" in body
    assert "alpha = 1.0 - 0.62" in body
    scene = src[src.index("def _rebuild_scene"):]
    assert 'alpha = alpha0 * float(o.get("alpha", 1.0) or 1.0)' in scene


def test_dialog_lives_in_its_own_module():
    """Классы окна вынесены из функции в свой модуль.

    Раньше оба класса жили внутри `_build_dialog`, чтобы отложить
    импорт Qt: модуль читается и там, где QGIS ещё не поднят. Приём
    остался, но перенесён на уровень выше - откладывается импорт
    модуля, а не определение класса.
    """
    src = open(VIEWER, encoding="utf-8").read()
    start = src.index("def _build_dialog")
    nxt = src.find("\ndef ", start + 20)
    body = src[start:] if nxt < 0 else src[start:nxt]
    assert "from .viewer_dialog import ViewerDialog" in body
    assert "class ViewerDialog" not in src
    assert len(body.split("\n")) < 20, len(body.split("\n"))
    dlg = os.path.join(os.path.dirname(HERE), "viewer_dialog.py")
    with open(dlg, encoding="utf-8") as fh:
        d = fh.read()
    assert d.count("\nclass ViewerDialog") == 1
    assert d.count("\nclass _PickView") == 1


def test_qt_is_not_imported_at_read_time():
    """Точка входа не тянет Qt при чтении модуля.

    Модуль читается при запуске QGIS, а окно открывают редко. Тянуть
    Qt на верхнем уровне значило бы платить за это всегда.
    """
    import ast as _ast
    src = open(VIEWER, encoding="utf-8").read()
    tree = _ast.parse(src)
    bad = []
    for node in tree.body:      # только верхний уровень
        mods = []
        if isinstance(node, _ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, _ast.ImportFrom):
            mods = [node.module or ""]
        for m in mods:
            if m.startswith("qgis.PyQt") or m.split(".")[0] in (
                    "PyQt5", "PyQt6", "PySide2", "PySide6"):
                bad.append(m)
    assert not bad, "Qt тянется при чтении: %s" % ", ".join(bad)


def test_core_is_free_of_qgis():
    """Расчётная часть не тянет QGIS и Qt.

    В этом весь смысл разделения: то, что считается числами, должно
    импортироваться в проверках напрямую, а не вырезаться из исходника
    текстом.
    """
    core = os.path.join(os.path.dirname(HERE), "viewer_core.py")
    with open(core, encoding="utf-8") as fh:
        src = fh.read()
    tree = ast.parse(src)
    bad = []
    for node in ast.walk(tree):
        mods = []
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mods = [node.module or ""]
        for m in mods:
            head = m.split(".")[0]
            if head in ("qgis", "PyQt5", "PyQt6", "PySide2", "PySide6"):
                bad.append(m)
    assert not bad, "ядро тянет окно: %s" % ", ".join(sorted(set(bad)))


def test_window_re_exports_the_core():
    """Снаружи окно видно прежним: имена продолжают жить и в нём.

    Разделение не должно ломать чужой код и наши же проверки, которые
    берут эти имена из viewer3d.
    """
    src = open(VIEWER, encoding="utf-8").read()
    assert "from .viewer_core import (" in src
    assert "# noqa: F401" in src
    core = os.path.join(os.path.dirname(HERE), "viewer_core.py")
    with open(core, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    head = src[src.index("from .viewer_core import ("):]
    head = head[:head.index(")\n")]
    missing = sorted(n for n in names if n not in head)
    assert not missing, "не переэкспортированы: %s" % ", ".join(missing)


def test_fog_mode_is_wired():
    """Объёмная заливка доходит от свойств до сборки сцены."""
    src = _viewer_src()
    assert '(tr("Объёмная заливка"), "fog")' in src
    assert "def _fog_item" in src
    start = src.index("def _rebuild_scene")
    body = src[start:]
    assert 'if mode == "fog":' in body
    assert "self._fog_item(lyr_f, o_f, cx, cy, cz, vex, prof)" in body


def test_fog_is_built_after_the_centre_is_known():
    """Заливка строится после обхода слоёв, а не в нём.

    Ей нужен центр сцены, а он известен только когда собраны все
    вершины. Иначе ящик встал бы мимо.
    """
    src = _viewer_src()
    start = src.index("def _rebuild_scene")
    body = src[start:]
    at_collect = body.index('if mode == "fog":')
    at_centre = body.index("cx = 0.5 * (min(xs) + max(xs))")
    at_build = body.index("self._fog_item(lyr_f")
    assert at_collect < at_centre < at_build


def test_fog_extends_the_scene_extent():
    """Углы куба идут в общий охват: своих вершин у заливки нет."""
    src = _viewer_src()
    assert "def _cube_box" in src
    start = src.index("def _rebuild_scene")
    body = src[start:]
    assert "for _l, _o, box in fogs:" in body
    assert "vsets.append(np.array(box, dtype=float))" in body


def test_wall_mode_is_wired():
    """Режим стенки доходит от свойств до сборки сцены."""
    src = _viewer_src()
    assert '(tr("Стенка по линии"), "wall")' in src
    assert "def _wall_mesh" in src
    start = src.index("def _rebuild_scene")
    body = src[start:]
    assert 'if mode == "wall":' in body
    assert "self._wall_mesh(lyr, o, clip_lines," in body


def test_wall_takes_the_line_from_the_clip_list():
    """Линия берётся из списка обрезки, а не заводится своя.

    Рисовать её отдельным способом незачем, она там уже есть,
    и второй способ рисования пришлось бы объяснять.
    """
    src = _viewer_src()
    start = src.index("        def _wall_mesh")
    body = src[start:src.index("\n        def ", start + 20)]
    assert "if not clip_lines:" in body
    assert "нарисуйте её или" in body


def test_wall_colours_by_value():
    """Стенка красится по значению, иначе показывать её незачем."""
    src = _viewer_src()
    start = src.index("        def _wall_mesh")
    body = src[start:src.index("\n        def ", start + 20)]
    assert "colormap(" in body
    assert "section_mesh(" in body


def test_vox_mode_is_wired():
    """Режим вокселей доходит от свойств до сборки сцены."""
    src = _viewer_src()
    assert '(tr("Воксели по кубу"), "vox")' in src
    assert "def _vox_mesh" in src
    start = src.index("def _rebuild_scene")
    body = src[start:]
    assert 'if mode == "vox":' in body
    assert "self._vox_mesh(lyr, o, clip" in body


def test_vox_reads_the_cube_convention():
    """Воксели читают куб так же, как изоповерхность."""
    src = _viewer_src()
    start = src.index("def _cube_arrays")
    end = src.index("        def _vox_mesh", start)
    body = src[start:end]
    assert '"Z0"' in body and '"DZ"' in body


def test_vox_faces_are_flat_shaded():
    """У коробок грани плоские: сглаживание скруглило бы рёбра."""
    src = _viewer_src()
    start = src.index("vox_col = self._vox_colors.get(lid)")
    body = src[start:start + 900]
    assert "smooth=False" in body
    assert "setVertexColors" in body


def test_vox_colors_are_reset_every_rebuild():
    """Цвета вокселей не переносятся между пересборками сцены."""
    src = _viewer_src()
    start = src.index("def _rebuild_scene")
    body = src[start:]
    assert "self._vox_colors = {}" in body


def test_vox_estimates_before_building():
    """Размер оценивается до сборки, а не после.

    Счёт видимых граней идёт на NumPy и стоит доли секунды, сборка
    же при миллионах граней уводит окно в неотзывчивость. Проверка
    закрепляет порядок: сначала оценка и выход, потом меш.
    """
    src = _viewer_src()
    assert "_VOX_FACE_LIMIT" in src
    start = src.index("        def _vox_mesh")
    end = src.index("        def _keep_for_export", start)
    body = src[start:end]
    at_est = body.index("vis = voxel.visible_faces(occ)")
    at_mesh = body.index("voxel.voxel_mesh(")
    assert at_est < at_mesh, "оценка должна идти до сборки"
    assert "_VOX_FACE_LIMIT" in body[at_est:at_mesh]


def test_vox_merge_switch_reaches_the_core():
    """Флаг слияния доходит от свойств до ядра.

    Без него нельзя получить замкнутую оболочку, а по слитой
    объём считать нельзя.
    """
    src = _viewer_src()
    assert 'tr("Сливать соседние грани")' in src
    assert 'vox_merge=bool(self.vox_merge.isChecked())' in src
    start = src.index("        def _vox_mesh")
    end = src.index("        def _keep_for_export", start)
    body = src[start:end]
    assert 'opts.get("vox_merge", True)' in body
    assert "merge=merge" in body


def test_vox_clipping_is_passed_through():
    """Обрезка контуром и линиями доходит до вокселей.

    У вокселей обрезка это отбор ячеек, крышка не нужна, и терять
    её по дороге незачем.
    """
    src = _viewer_src()
    start = src.index("        def _vox_mesh")
    end = src.index("        def _keep_for_export", start)
    body = src[start:end]
    assert "self._clip_array" in body
    assert "self._clip_by_lines" in body


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("ok:", fn.__name__)
    print("all %d tests passed" % len(fns))


if __name__ == "__main__":
    _run()
