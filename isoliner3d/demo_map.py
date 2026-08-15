# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Это свободная программа: вы можете распространять её и/или изменять на
# условиях Стандартной общественной лицензии GNU (GNU GPL) версии 2 либо
# (на ваше усмотрение) любой более поздней версии. Полный текст - в LICENSE.
"""Рисование демонстрационной карты для проверки наложения текстуры.

Картинка нарочно сделана проверочной, а не красивой. Наложение текстуры
ошибается тремя типовыми способами, и каждый из них эта карта показывает
сразу:

- переворот по вертикали (у растра начало отсчёта сверху, у текстурной
  оси снизу) виден по разным меткам в углах;
- перекос и сдвиг видны по координатной сетке, на цветных пятнах их
  не заметить;
- растяжение по одной оси видно по квадратности клеток сетки.

Чистый NumPy, вывода на диск здесь нет: функция возвращает массив
(H, W, 3) байтов, писать его в GeoTIFF - дело инструмента.
"""
import numpy as np

# поля геологической карты: тёплые пастельные тона, как в легенде
FIELDS = [
    (222, 205, 135), (205, 178, 120), (176, 196, 145), (150, 180, 175),
    (190, 165, 175), (215, 190, 160), (165, 175, 200), (200, 210, 165),
]
LINE = (70, 60, 50)        # изолинии
GRID = (40, 40, 40)        # координатная сетка
MARKS = [(200, 40, 40), (40, 140, 60), (40, 90, 200), (230, 170, 30)]


def _bands(ny, nx, n_fields, seed):
    """Поля пластов: наклонные полосы с волной, чтобы граница была кривой."""
    yy, xx = np.mgrid[0:ny, 0:nx]
    u = (xx / float(nx)) + 0.45 * (yy / float(ny))
    rng = np.random.default_rng(int(seed))
    phase = rng.uniform(0.0, 6.283)
    amp = 0.06
    u = u + amp * np.sin(6.0 * np.pi * yy / float(ny) + phase)
    idx = np.floor(u * n_fields).astype(int) % len(FIELDS)
    return idx


def _contours(ny, nx, seed, n=14):
    """Тонкие изолинии: маска там, где гладкое поле переходит уровень."""
    yy, xx = np.mgrid[0:ny, 0:nx]
    rng = np.random.default_rng(int(seed) + 1)
    a, b = rng.uniform(1.5, 3.0, size=2)
    f = (np.sin(a * np.pi * xx / float(nx))
         * np.cos(b * np.pi * yy / float(ny)))
    lev = f * n
    return np.abs(lev - np.round(lev)) < 0.045


def _corner_mark(img, cy, cx, color, size):
    """Залить квадратную метку, не выходя за края картинки."""
    ny, nx = img.shape[:2]
    y0 = max(0, min(ny - 1, cy - size))
    y1 = max(0, min(ny, cy + size))
    x0 = max(0, min(nx - 1, cx - size))
    x1 = max(0, min(nx, cx + size))
    img[y0:y1, x0:x1] = color


def demo_map(nx=1024, ny=1024, cells=10, n_fields=6, seed=1):
    """Демонстрационная карта как массив (ny, nx, 3) байтов.

    `cells` - число клеток координатной сетки по длинной стороне.
    Углы помечены разными цветами по часовой стрелке от левого верхнего:
    красный, зелёный, синий, жёлтый.
    """
    nx = int(max(64, nx))
    ny = int(max(64, ny))
    n_fields = int(max(2, min(len(FIELDS), n_fields)))
    idx = _bands(ny, nx, n_fields, seed)
    img = np.zeros((ny, nx, 3), dtype=np.uint8)
    for k in range(n_fields):
        img[idx == k] = FIELDS[k]
    img[_contours(ny, nx, seed)] = LINE

    # координатная сетка: шаг одинаковый по обеим осям, клетки квадратные
    cells = int(max(2, cells))
    step = max(8, int(max(nx, ny) / float(cells)))
    img[::step, :] = GRID
    img[:, ::step] = GRID
    img[-1, :] = GRID
    img[:, -1] = GRID

    m = max(8, int(min(nx, ny) * 0.045))
    _corner_mark(img, m, m, MARKS[0], m)                 # левый верхний
    _corner_mark(img, m, nx - m, MARKS[1], m)            # правый верхний
    _corner_mark(img, ny - m, nx - m, MARKS[2], m)       # правый нижний
    _corner_mark(img, ny - m, m, MARKS[3], m)            # левый нижний
    return img
