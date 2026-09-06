# -*- coding: utf-8 -*-
#
# Isoliner3D - объёмная визуализация (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Зарисовки бортов 2.09: кольцо замкнуто, полигон вертикальный.

Проверку геометрии QGIS зарисовки не проходят, и это выглядит как порча
слоя. Разбор показал другое: борт выработки идёт по прямой, поэтому в
плане все вершины зарисовки лежат на одной линии и площадь в плане равна
нулю. Штатная проверка считает площадь именно в плане, и вертикальный
полигон она обязана назвать некорректным - как назвала бы любую
вертикальную стенку от любого инструмента.

Значит, чинить в геометрии нечего, а сказать об этом человеку надо.
Здесь закреплено и то и другое: кольцо действительно замкнуто (вот это
было бы настоящей порчей), вершины действительно лежат в одной
вертикальной плоскости, и инструмент об этом предупреждает.

Проверка идёт без QGIS.
"""
import ast
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import demo_drift as dd  # noqa: E402


def _model():
    return dd.make_model()


def _rings():
    model = _model()
    out = []
    for w in dd.walls(model):
        for bed in dd.BEDS:
            ring = dd.wall_ring(model, bed, w, step=1.0)
            if ring is not None:
                out.append(ring)
    return out


def test_rings_are_produced_at_all():
    rings = _rings()
    assert rings, "демо не отдало ни одной зарисовки"


def test_every_ring_is_closed():
    """Незамкнутое кольцо было бы настоящей порчей, а не свойством."""
    for i, ring in enumerate(_rings()):
        assert np.allclose(ring[0], ring[-1]), (
            "кольцо %d не замкнуто: первая вершина %s, последняя %s"
            % (i, ring[0], ring[-1]))
        assert len(ring) >= 4, "в кольце %d меньше четырёх вершин" % i


def test_every_ring_is_vertical_in_plan():
    """Все вершины лежат на одной прямой в плане, площадь в плане нулевая.

    Отсюда и берётся «некорректная геометрия» у штатной проверки.
    """
    for i, ring in enumerate(_rings()):
        x, y = ring[:, 0], ring[:, 1]
        # удвоенная площадь многоугольника в плане
        area2 = float(np.abs(np.dot(x, np.roll(y, -1))
                             - np.dot(y, np.roll(x, -1))))
        span = float(max(x.max() - x.min(), y.max() - y.min())) or 1.0
        assert area2 / (span * span) < 1e-9, (
            "зарисовка %d не вертикальна: площадь в плане не нулевая" % i)


def test_rings_have_real_thickness_in_height():
    """Вертикальность не должна означать вырождение: по Z стенка есть."""
    for i, ring in enumerate(_rings()):
        z = ring[:, 2]
        assert float(z.max() - z.min()) > 0.05, (
            "у зарисовки %d нет высоты, это уже не стенка" % i)


def test_tool_warns_that_the_check_will_complain():
    """Инструмент обязан сказать об этом в журнале.

    Иначе человек запускает проверку геометрии, видит красное и решает,
    что слой испорчен. Разбор по исходнику, без запуска QGIS.
    """
    with open(os.path.join(PKG, "algorithms.py"), encoding="utf-8") as fh:
        text = fh.read()
    for node in ast.walk(ast.parse(text)):
        if (isinstance(node, ast.ClassDef)
                and node.name == "DemoDriftAlgorithm"):
            body = ast.get_source_segment(text, node) or ""
            break
    else:
        raise AssertionError("класс демонстрационной выработки не найден")
    assert "вертикальные полигоны" in body, (
        "2.09 снова молчит о том, что проверка геометрии назовёт "
        "зарисовки некорректными")
