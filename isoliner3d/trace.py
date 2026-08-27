# -*- coding: utf-8 -*-
"""Журнал шагов модуля.

Когда у заказчика «ничего не происходит», понять что именно не происходит
невозможно: ни ошибки, ни следа. Поэтому модуль пишет каждый свой шаг в файл,
и на успехе тоже, а не только при сбое. Один файл отвечает сразу на всё:
какая версия работает, дошло ли дело до запроса, сколько строк вернула база,
создался ли слой, принял ли его проект.

Файл лежит рядом с профилем QGIS и открывается кнопкой в окне «О модуле»:
копировать ничего не нужно, достаточно приложить его к письму.

У каждого модуля свой файл (isoliner.log, geoconstructor.log и так
далее). Общий журнал был бы удобен только там, где модули стоят вместе, а у
большинства заказчиков установлен один.

Модуль не зависит от QGIS: путь подставляется снаружи, при загрузке плагина.
"""

import datetime
import traceback

_PATH = None
_ENABLED = True
_NAME = "Isoliner3D"


def path():
    return _PATH


def enable(value=True):
    global _ENABLED
    _ENABLED = bool(value)


def _line(mark, message):
    stamp = datetime.datetime.now().strftime("%H:%M:%S")
    return "%s  %-9s %s" % (stamp, mark, message)


def write(mark, message):
    """Дописывает строку.

    Молчит, если файл недоступен: журнал не должен мешать работе.
    """
    if not _ENABLED or not _PATH:
        return
    try:
        with open(_PATH, "a", encoding="utf-8") as fh:
            fh.write(_line(mark, message) + "\n")
    except Exception:  # nosec
        pass


def step(message):
    write("ШАГ", message)


def data(message):
    write("ДАННЫЕ", message)


def fail(message, exc=None):
    write("ОШИБКА", message)
    if exc is not None:
        for line in traceback.format_exc().rstrip().splitlines():
            write("", "    " + line)
