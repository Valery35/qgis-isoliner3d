# -*- coding: utf-8 -*-
#
# Isoliner3D (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Демо-генератор не должен рапортовать об успехе с пустым выходом.

«Создать пример данных» с разбиением на треугольники писал в слой ноль
объектов: writer отказывался от геометрии TIN, результат addFeature никто
не смотрел, и инструмент заканчивал строкой «Оболочка замкнута». Рядом
вторая мелочь: система координат берётся у проекта, и когда её у проекта
нет, демо-слой выходит без СК молча.

Проверка идёт по исходнику разбором AST, без запуска QGIS.
"""
import ast
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "algorithms.py")


def _class_source(name):
    with open(SRC, encoding="utf-8") as fh:
        text = fh.read()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return ast.get_source_segment(text, node) or ""
    raise AssertionError("класс %s пропал из algorithms.py" % name)


def test_demo_checks_that_features_were_written():
    body = _class_source("PolyhedralDemoAlgorithm")
    assert "if sink.addFeature(f):" in body, (
        "результат записи объекта снова не проверяется: пустой слой уйдёт "
        "как успех")
    assert "Ни один объект не записан" in body, (
        "нет отказа на полностью пустом выходе")


def test_demo_warns_about_missing_project_crs():
    body = _class_source("PolyhedralDemoAlgorithm")
    at = body.find("crs.isValid()")
    assert at != -1, "проверка системы координат проекта пропала"
    assert "pushWarning" in body[at:at + 400], (
        "про отсутствующую СК проекта инструмент снова молчит")


def test_bed_calculator_names_band_count():
    body = _class_source("BedCalculatorAlgorithm")
    assert "Канал содержания %d вне грида" in body, (
        "сообщение о канале снова не называет ни номер, ни число каналов")
