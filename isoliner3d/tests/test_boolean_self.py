# -*- coding: utf-8 -*-
#
# Isoliner3D - объёмная визуализация (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Булевы операции тела с самим собой (2.11).

Пустой результат при подаче одного тела в оба поля числился за ошибкой.
Разбор показал другое: пустым он выходит при ВЫЧИТАНИИ, а вычитание тела
из самого себя и обязано давать пустоту. Оно же стоит действием по
умолчанию, поэтому запуск без выбора действия попадает именно на него.

Здесь закреплены обе половины: пересечение и объединение тела с собой
возвращают то же тело целиком, вычитание возвращает пустоту. Если
когда-нибудь пересечение с собой снова обнулится, это будет уже ошибка,
и тест её покажет.

Проверка идёт на ядре boolean3d, без QGIS.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import boolean3d  # noqa: E402


def _cube(x0=0.0, y0=0.0, z0=0.0, side=10.0):
    """Замкнутый куб: восемь вершин, двенадцать треугольников."""
    s = side
    v = np.array([
        [x0, y0, z0], [x0 + s, y0, z0], [x0 + s, y0 + s, z0],
        [x0, y0 + s, z0], [x0, y0, z0 + s], [x0 + s, y0, z0 + s],
        [x0 + s, y0 + s, z0 + s], [x0, y0 + s, z0 + s]], float)
    f = np.array([
        [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
        [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]], np.int64)
    return v, f


def _bounds(v):
    return (float(v[:, 0].min()), float(v[:, 0].max()),
            float(v[:, 1].min()), float(v[:, 1].max()),
            float(v[:, 2].min()), float(v[:, 2].max()))


def _occ_pair(op, cell=1.0):
    va, fa = _cube()
    vb, fb = va.copy(), fa.copy()
    gt, z0, dz, shape = boolean3d.common_box(_bounds(va), _bounds(vb),
                                             cell, op)
    occ_a = boolean3d.shell_occupancy(va, fa, gt, z0, dz, shape)
    occ_b = boolean3d.shell_occupancy(vb, fb, gt, z0, dz, shape)
    return occ_a, occ_b, boolean3d.combine(occ_a, occ_b, op)


def test_the_body_is_not_empty_to_begin_with():
    """Контроль: без него равенства ниже выполнялись бы на пустоте."""
    occ_a, occ_b, _ = _occ_pair("intersection")
    assert occ_a.sum() > 100, "куб не залился, проверять нечего"
    assert np.array_equal(occ_a, occ_b), (
        "одно и то же тело залилось по-разному, дело не в операции")


def test_intersection_with_itself_keeps_the_whole_body():
    occ_a, _occ_b, res = _occ_pair("intersection")
    assert np.array_equal(res, occ_a), (
        "пересечение тела с самим собой потеряло ячейки: было %d, стало %d"
        % (occ_a.sum(), res.sum()))


def test_union_with_itself_keeps_the_whole_body():
    occ_a, _occ_b, res = _occ_pair("union")
    assert np.array_equal(res, occ_a)


def test_difference_with_itself_is_empty_and_that_is_correct():
    """Пустота тут не дефект: из тела вычли его же."""
    _occ_a, _occ_b, res = _occ_pair("difference")
    assert res.sum() == 0


def test_difference_is_the_default_action():
    """Именно поэтому запуск без выбора действия и давал пустоту.

    Порядок в OPS обязан совпадать с порядком вариантов в окне: сдвиг на
    единицу означал бы, что человек выбирает одно, а считается другое.
    """
    assert boolean3d.OPS[0] == "difference"
    assert boolean3d.OPS == ("difference", "union", "intersection")
