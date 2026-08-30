# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Это свободная программа: вы можете распространять её и/или изменять на
# условиях Стандартной общественной лицензии GNU (GNU GPL) версии 2 либо
# (на ваше усмотрение) любой более поздней версии. Полный текст - в LICENSE.
"""Класс плагина Isoliner3D: провайдер Processing и 3D-просмотр.

Плагин делает две вещи. Регистрирует провайдер Processing с группой
«Пласт и блочная модель» (семь инструментов, см. algorithms.py) и добавляет
пункт меню с кнопкой тулбара для 3D-окна на pyqtgraph/PyOpenGL (обе
библиотеки идут в комплекте в libs/). Пункт 3D добавляется только если
рендер-стек доступен, провайдер регистрируется всегда: инструменты пласта
считают на NumPy и GDAL и в 3D не нуждаются.
"""
import os

from qgis.core import QgsApplication, QgsMessageLog

MENU = "Isoliner3D"


def _log(msg):
    try:
        QgsMessageLog.logMessage(msg, "Isoliner3D")
    except Exception:  # nosec
        pass


class Isoliner3DPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.actions = []
        self.toolbar = None
        self.provider = None

    def initProcessing(self):
        """Регистрирует провайдер. Сбой не должен мешать 3D-окну."""
        try:
            from .provider import Isoliner3DProvider
            self.provider = Isoliner3DProvider()
            QgsApplication.processingRegistry().addProvider(self.provider)
        except Exception as e:
            self.provider = None
            _log("Провайдер Processing не зарегистрирован: %s" % e)

    def initGui(self):
        # Журнал заводится первым: всё, что случится дальше, должно
        # в него попасть. Без этого путь пуст, записи уходят в никуда,
        # и кнопка «Журнал» отвечает, что его нет.
        try:
            from . import trace
            got = trace.setup()
            from .about import read_metadata
            trace.step("Isoliner3D %s: загрузка"
                       % read_metadata().get("version", "?"))
            if not got:
                _log("Журнал не заведён: некуда писать.")
        except Exception as e:  # nosec
            _log("Журнал не заведён: %s" % e)
        self.initProcessing()
        try:
            from qgis.PyQt.QtGui import QIcon
            try:
                from qgis.PyQt.QtGui import QAction       # Qt6 (QGIS 4)
            except ImportError:
                from qgis.PyQt.QtWidgets import QAction   # Qt5 (QGIS 3)
            from .i18n import tr, init_from_qgis
            from . import viewer3d
            init_from_qgis()
            here = os.path.dirname(__file__)
            icon = QIcon(os.path.join(here, "icon.svg"))
            # У каждого пункта свой значок: одинаковые в меню
            # неразличимы, и человек жмёт наугад.
            icon_about = QIcon(os.path.join(here, "icon_about.svg"))
            icon_help = QIcon(os.path.join(here, "icon_help.svg"))
            win = self.iface.mainWindow()
            self.toolbar = self.iface.addToolBar(tr("Isoliner3D"))
            self.toolbar.setObjectName("Isoliner3DToolbar")
            if viewer3d.is_available():
                a3d = QAction(icon,
                              tr("3D-просмотр поверхностей…"), win)
                a3d.setToolTip(tr("3D-просмотр поверхностей Isoliner"))
                a3d.triggered.connect(
                    lambda: viewer3d.show_viewer(self.iface))
                self._add(a3d, toolbar=True)
            else:
                _log("pyqtgraph/PyOpenGL недоступны - пункт 3D не добавлен.")
            aabout = QAction(icon_about, tr("О плагине…"), win)
            aabout.setToolTip(tr(
                "Версия, ссылки, история изменений, журнал"))
            aabout.triggered.connect(self._show_about)
            self._add(aabout, toolbar=True)
            ahelp = QAction(icon_help,
                            tr("Справка (руководство PDF)…"), win)
            ahelp.setToolTip(tr("Руководство Isoliner3D в формате PDF"))
            ahelp.triggered.connect(self._open_help)
            self._add(ahelp)
        except Exception as e:
            _log("Интерфейс Isoliner3D не создан: %s" % e)

    def _show_about(self):
        """Окно «О плагине». Ошибка здесь не должна ронять интерфейс."""
        try:
            from . import about
            about.show_about(self.iface.mainWindow())
        except Exception as e:  # nosec
            _log("Окно «О плагине» не открылось: %s" % e)

    def _open_help(self):
        """Открыть PDF руководства по языку интерфейса.

        Русское руководство - doc/Isoliner3D.pdf, английское - с суффиксом
        _en. Если файла нужного языка нет, берём второй, а если нет обоих,
        пишем в журнал: справка не должна ронять интерфейс.
        """
        from qgis.PyQt.QtCore import QUrl
        from qgis.PyQt.QtGui import QDesktopServices
        from .i18n import tr, language
        doc = os.path.join(os.path.dirname(__file__), "doc")
        names = (["Isoliner3D.pdf", "Isoliner3D_en.pdf"]
                 if language() == "ru" else
                 ["Isoliner3D_en.pdf", "Isoliner3D.pdf"])
        for name in names:
            path = os.path.join(doc, name)
            if os.path.isfile(path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
                return
        _log(tr("Файл руководства не найден: %s") % names[0])

    def _add(self, action, toolbar=False):
        self.iface.addPluginToMenu(MENU, action)
        if toolbar and self.toolbar is not None:
            self.toolbar.addAction(action)
        self.actions.append(action)

    def unload(self):
        if getattr(self, "provider", None) is not None:
            try:
                QgsApplication.processingRegistry().removeProvider(
                    self.provider)
            except Exception:  # nosec
                pass
            self.provider = None
        for a in getattr(self, "actions", []):
            try:
                self.iface.removePluginMenu(MENU, a)
            except Exception:  # nosec
                pass
        self.actions = []
        if self.toolbar is not None:
            try:
                self.toolbar.deleteLater()
            except Exception:  # nosec
                pass
            self.toolbar = None
