# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Инструменты Isoliner3D как объекты: реестр описаний.

Каждый модуль пакета задаёт SPEC (toolspec.Tool). Пакет не знает
QGIS: его берут обёртка Processing, выгрузка tools.json и тесты.
Инструменты переходят сюда по одному, остальные пока живут
классами в algorithms.py.
"""

from . import (bench_report, boolean_shells, density_3d, desurvey_holes,
               fill_volume, grid_to_shell, hole_intervals, select_by_shell,
               sweep_body, zonal_shell_stats)

TOOLS = [boolean_shells.SPEC, select_by_shell.SPEC, grid_to_shell.SPEC,
         zonal_shell_stats.SPEC, desurvey_holes.SPEC, hole_intervals.SPEC,
         fill_volume.SPEC, sweep_body.SPEC, density_3d.SPEC,
         bench_report.SPEC]


def by_name(name):
    """Описание по имени Processing."""
    for t in TOOLS:
        if t.name == name:
            return t
    raise KeyError(name)
