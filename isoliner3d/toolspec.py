# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Инструмент как объект: описание и расчёт без QGIS.

Инструмент Isoliner3D состоит из двух частей. Описание: код («2.23»),
имя для Processing, название, справка, поля с подписями и подсказками.
Расчёт: функция run(значения, отчёт) на простых данных - массивах
NumPy, словарях и списках. Ни то ни другое не знает QGIS.

QGIS подключается одной обёрткой (SpecAlgorithm в algorithms.py):
она строит поля Processing по описанию, переводит слои в данные
для run и записывает результат в слои. Та же пара описание-расчёт
потом уходит в RustGIS: описание выгружается в tools.json
(tools/export_tools.py), а расчёт переносится на Rust с теми же
кодами и полями.

Данные полей на входе run:

- mesh   - весь слой полигонов с Z одним телом: {"verts", "faces"};
- lines  - линии: список {"id", "parts": [массивы (n, 3)], "attrs"},
           у линий без Z третий столбец NaN;
- points - точки: список {"id", "xyz": (3,), "attrs"};
- field  - имя поля или пустая строка;
- number, integer - число; enum - номер выбранного пункта;
- sink   - выход, на входе run его нет.

Результат run - словарь {ключ выхода: Result}. Result несёт поля
(имя, тип), объекты (геометрия, значения) и признак keep_source:
выход начинается полями объекта источника.

Строки, которые видит пользователь, помечены N_(): по этой метке
их находит проверка переводов, а переводит обёртка при показе.
Сообщения отчёта - шаблон с аргументами, тоже переводятся при показе.
"""


def N_(text):
    """Метка строки для перевода: перевод делается при показе."""
    return text


KINDS = ("mesh", "lines", "points", "field", "number", "integer",
         "enum", "sink")


class Param(object):
    """Поле инструмента."""

    def __init__(self, key, kind, label, hint, default=None, options=(),
                 optional=False, parent=None, minimum=None, maximum=None,
                 numeric=False, geometry=None):
        if kind not in KINDS:
            raise ValueError("unknown kind %r" % (kind,))
        self.key = key
        self.kind = kind
        self.label = label
        self.hint = hint
        self.default = default
        self.options = tuple(options)
        self.optional = bool(optional)
        self.parent = parent
        self.minimum = minimum
        self.maximum = maximum
        self.numeric = bool(numeric)
        self.geometry = geometry

    def to_dict(self):
        out = {"key": self.key, "kind": self.kind, "label": self.label,
               "hint": self.hint}
        for name in ("default", "parent", "minimum", "maximum",
                     "geometry"):
            val = getattr(self, name)
            if val is not None:
                out[name] = val
        if self.options:
            out["options"] = list(self.options)
        if self.optional:
            out["optional"] = True
        if self.numeric:
            out["numeric"] = True
        return out


class Result(object):
    """Выход инструмента: поля и объекты.

    fields - [(имя, тип)], тип "double", "int" или "string".
    features - [(геометрия, значения)]; геометрия тела -
    {"verts", "faces"}. keep_source - объекты несут сначала значения
    объекта источника (значения в начале списка), потом свои.
    """

    def __init__(self, fields, features=None, keep_source=None,
                 name=None):
        self.fields = list(fields)
        self.features = list(features or [])
        self.keep_source = keep_source
        self.name = name

    def add(self, geometry, values):
        self.features.append((geometry, list(values)))


class Report(object):
    """Отчёт расчёта: сведения, предупреждения, прогресс, отмена.

    Обёртка QGIS переопределяет методы и передаёт строки в журнал
    Processing. Без QGIS отчёт копит строки в list, так их видят
    тесты.
    """

    def __init__(self):
        self.lines = []

    def info(self, template, *args):
        self.lines.append(("info", template % args if args else template))

    def warn(self, template, *args):
        self.lines.append(("warn", template % args if args else template))

    def progress(self, share):
        pass

    def canceled(self):
        return False


class ToolError(Exception):
    """Расчёт невозможен: шаблон сообщения и аргументы для перевода."""

    def __init__(self, template, *args):
        Exception.__init__(self, template % args if args else template)
        self.template = template
        self.args_ = args


class Tool(object):
    """Описание инструмента и его расчёт."""

    def __init__(self, code, name, title, group, help, params, run):
        self.code = code
        self.name = name
        self.title = title
        self.group = group
        self.help = help
        self.params = list(params)
        self.run = run
        keys = [p.key for p in self.params]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate field in %s" % name)

    def display_name(self):
        """Название с кодом, как в панели Processing."""
        return "%s %s" % (self.code, self.title)

    def param(self, key):
        for p in self.params:
            if p.key == key:
                return p
        raise KeyError(key)

    def defaults(self):
        """Значения полей по умолчанию: для тестов и для run без QGIS."""
        return {p.key: p.default for p in self.params
                if p.kind != "sink"}

    def to_dict(self):
        return {"code": self.code, "name": self.name, "title": self.title,
                "group": self.group, "help": self.help,
                "params": [p.to_dict() for p in self.params]}
