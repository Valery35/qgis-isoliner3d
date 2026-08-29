# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Окно «О плагине»: версия, ссылки, история изменений, журнал.

Версия и история читаются из `metadata.txt`. Отдельный файл истории
не нужен: канонический список изменений уже там, и заводить второй
значит завести и расхождение между ними.

Qt импортируется внутри функций, а не наверху: модуль читается и там,
где QGIS не поднят, - в проверках, которые идут без него.
"""

import os

_HERE = os.path.dirname(__file__)
_SITE = "https://www.informpp.ru/"


def read_metadata():
    """Раздел [general] из metadata.txt: версия, история, ссылки."""
    import configparser
    cp = configparser.ConfigParser(interpolation=None)
    with open(os.path.join(_HERE, "metadata.txt"), encoding="utf-8") as f:
        cp.read_file(f)
    return dict(cp["general"])


def manual_path():
    """Путь к руководству по языку интерфейса.

    Если нужного языка нет, берётся второе: руководство на чужом языке
    полезнее его отсутствия.
    """
    from .i18n import language
    names = ["Isoliner3D.pdf", "Isoliner3D_en.pdf"]
    try:
        if language() == "en":
            names.reverse()
    except Exception:  # nosec
        pass
    for name in names:
        path = os.path.join(_HERE, "doc", name)
        if os.path.isfile(path):
            return path
    return ""


def open_manual(parent=None):
    """Открыть руководство системным просмотрщиком."""
    from qgis.PyQt.QtCore import QUrl
    from qgis.PyQt.QtGui import QDesktopServices
    from qgis.PyQt.QtWidgets import QMessageBox
    from .i18n import tr
    path = manual_path()
    if path:
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
    else:
        QMessageBox.warning(parent, "Isoliner3D",
                            tr("Руководство не найдено."))


def open_log(parent=None):
    """Открыть журнал работы системным приложением."""
    from qgis.PyQt.QtCore import QUrl
    from qgis.PyQt.QtGui import QDesktopServices
    from qgis.PyQt.QtWidgets import QMessageBox
    from .i18n import tr
    path = ""
    try:
        from . import trace
        path = trace.path()
    except Exception:  # nosec
        path = ""
    if path and os.path.isfile(path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
    else:
        QMessageBox.information(parent, "Isoliner3D",
                                tr("Журнал ещё не заведён."))


def show_changelog(parent=None):
    """История изменений из metadata.txt, с прокруткой."""
    from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout,
                                     QPlainTextEdit, QDialogButtonBox)
    from .i18n import tr
    meta = read_metadata()
    dlg = QDialog(parent)
    dlg.setWindowTitle(tr("История изменений"))
    dlg.resize(680, 520)
    lay = QVBoxLayout(dlg)
    txt = QPlainTextEdit(dlg)
    txt.setReadOnly(True)
    txt.setPlainText(meta.get("changelog", ""))
    lay.addWidget(txt)
    box = QDialogButtonBox(
        getattr(getattr(QDialogButtonBox, "StandardButton",
                        QDialogButtonBox), "Close"), dlg)
    box.rejected.connect(dlg.reject)
    lay.addWidget(box)
    dlg.exec()


def show_about(parent=None):
    """Окно «О плагине»: значок, версия, ссылки, кнопки."""
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtGui import QIcon
    from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                                     QLabel, QPushButton,
                                     QDialogButtonBox)
    from .i18n import tr
    meta = read_metadata()
    ver = meta.get("version", "?")
    home = meta.get("homepage", "")
    tracker = meta.get("tracker", "")

    dlg = QDialog(parent)
    dlg.setWindowTitle(tr("О плагине"))
    lay = QVBoxLayout(dlg)

    head = QHBoxLayout()
    icon = QLabel(dlg)
    for name in ("icon_3d.svg", "icon.svg"):
        ipath = os.path.join(_HERE, name)
        if os.path.isfile(ipath):
            icon.setPixmap(QIcon(ipath).pixmap(56, 56))
            break
    head.addWidget(icon)
    head.addWidget(QLabel(
        "<b>Isoliner3D</b><br>%s<br>© ООО «Информ++»"
        % (tr("Версия %s") % ver), dlg), 1)
    lay.addLayout(head)

    links = QLabel(
        '<a href="%s">www.informpp.ru</a> · '
        '<a href="%s">%s</a> · <a href="%s">%s</a>'
        % (_SITE, home, tr("Исходный код"),
           tracker, tr("Сообщить об ошибке")), dlg)
    links.setOpenExternalLinks(True)
    links.setTextInteractionFlags(
        getattr(getattr(Qt, "TextInteractionFlag", Qt),
                "TextBrowserInteraction"))
    lay.addWidget(links)

    row = QHBoxLayout()
    for text, slot in ((tr("История изменений"),
                        lambda: show_changelog(dlg)),
                       (tr("Руководство (PDF)"),
                        lambda: open_manual(dlg)),
                       (tr("Журнал"), lambda: open_log(dlg))):
        btn = QPushButton(text, dlg)
        btn.clicked.connect(slot)
        row.addWidget(btn)
    lay.addLayout(row)

    box = QDialogButtonBox(
        getattr(getattr(QDialogButtonBox, "StandardButton",
                        QDialogButtonBox), "Close"), dlg)
    box.rejected.connect(dlg.reject)
    lay.addWidget(box)
    dlg.exec()
