# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Кнопка «Открыть в Isoliner Scene»: путь пакета, поиск программы.

Isoliner Scene - отдельная программа на Rust, она открывает пакет
сцены .i3dscene и раз в полсекунды проверяет его на диске. Модуль
пишет пакет текущей сцены в постоянное место и запускает программу
один раз. Дальше каждое нажатие только переписывает пакет, а окно
сцены перечитывает его само, камера остаётся на месте.

Договор с программой записан в doc/PLAN.md хранилища isoliner-scene,
раздел «Договор кнопки». Здесь его расчётная часть без Qt и QGIS:
имя файла, порядок поиска программы, подмена файла переименованием.
"""

import os
import re
import shutil
import time

# Имя программы в PATH и её место после установки в Windows.
APP_NAME = "isoliner-scene"
APP_DIR = "Isoliner Scene"
APP_EXE = "isoliner-scene.exe"
# Где взять программу: страница выпусков хранилища.
DOWNLOAD_URL = "https://github.com/Valery35/isoliner-scene/releases"
# Ключ настроек QGIS с путём к программе, заданным человеком.
SETTINGS_KEY = "isoliner3d/scene_app"

_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def package_name(project_name):
    """Имя файла пакета по имени проекта.

    Знаки, которых не любят файловые системы, заменяются
    подчёркиванием. Проект без имени - «scene».
    """
    base = _BAD.sub("_", str(project_name or "")).strip(" ._")
    return (base or "scene") + ".i3dscene"


def package_path(project_name, tmpdir):
    """Постоянное место пакета: <временная папка>/isoliner3d/<имя>."""
    return os.path.join(tmpdir, "isoliner3d", package_name(project_name))


def find_app(configured="", which=shutil.which, localappdata=None,
             isfile=os.path.isfile):
    """Путь к программе или пустая строка.

    Порядок по договору: путь из настроек модуля, программа в PATH,
    место установки в %LOCALAPPDATA%\\Programs. Путь из настроек,
    которого нет на диске, пропускается: программу могли переставить.
    """
    if configured and isfile(configured):
        return configured
    found = which(APP_NAME)
    if found:
        return found
    if localappdata is None:
        localappdata = os.environ.get("LOCALAPPDATA", "")
    if localappdata:
        path = os.path.join(localappdata, "Programs", APP_DIR, APP_EXE)
        if isfile(path):
            return path
    return ""


def replace_file(src, dst, tries=10, delay=0.1, replace=os.replace,
                 sleep=time.sleep):
    """Поставить src на место dst переименованием, с повторами.

    Окно сцены в этот миг может читать прежний пакет, и Windows
    тогда не даёт его заменить. Ждём и пробуем снова: чтение
    короткое. Последняя неудача уходит наверх.
    """
    for k in range(max(int(tries), 1)):
        try:
            replace(src, dst)
            return k + 1
        except PermissionError:
            if k + 1 >= tries:
                raise
            sleep(delay)
    return 0


def temp_path(dst):
    """Временный файл рядом с постоянным: на том же диске, иначе
    переименование не атомарно."""
    return dst + ".part"


def is_running(proc):
    """Жив ли процесс, запущенный кнопкой. None - не запускали."""
    return proc is not None and proc.poll() is None
