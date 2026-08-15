# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей и блочная модель (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Это свободная программа: вы можете распространять её и/или изменять на
# условиях Стандартной общественной лицензии GNU (GNU GPL) версии 2 либо
# (на ваше усмотрение) любой более поздней версии. Полный текст - в LICENSE.
"""Провайдер Processing «Isoliner3D»: группа «Пласт и блочная модель».

Идентификатор провайдера isoliner3d, поэтому полные имена инструментов
выглядят как isoliner3d:assemble_bed_grid. С провайдером isoliner основного
плагина не пересекается, оба могут стоять рядом.
"""
import os

from qgis.core import QgsProcessingProvider, QgsMessageLog
from qgis.PyQt.QtGui import QIcon

from .algorithms import ALGORITHMS
from . import i18n


def _log(msg):
    try:
        QgsMessageLog.logMessage(msg, "Isoliner3D")
    except Exception:  # nosec
        pass


class Isoliner3DProvider(QgsProcessingProvider):
    def loadAlgorithms(self):
        i18n.init_from_qgis()  # язык выбираем до регистрации инструментов
        loaded = 0
        for cls in ALGORITHMS:
            try:
                self.addAlgorithm(cls())
                loaded += 1
            except Exception as e:  # один сбойный не валит всю группу
                _log(i18n.tr("Не удалось добавить %s: %s")
                     % (cls.__name__, e))
        _log(i18n.tr("Загружено алгоритмов: %d") % loaded)

    def id(self):
        return "isoliner3d"

    def name(self):
        return "Isoliner3D"

    def longName(self):
        return self.name()

    def icon(self):
        path = os.path.join(os.path.dirname(__file__), "icon.svg")
        return QIcon(path) if os.path.exists(path) else QIcon()
