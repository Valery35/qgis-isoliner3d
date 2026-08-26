# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Объёмная заливка куба: передаточная функция значение - цвет.

Рендер объёма умеет ровно одно: показать массив цвета с прозрачностью,
глядя сквозь него. Всё, что решает, будет там видно тело или мутный
ящик, решает передаточная функция.

Правил у неё два. Ниже отсечки заливки нет вовсе: без этого виден весь
ящик целиком и в тумане не разглядеть ничего. Выше отсечки
непрозрачность растёт со значением, потому что показывать надо
содержание, а не его отсутствие.

Заливка не заменяет оболочку, а дополняет её. Оболочка отвечает,
где граница тела, заливка отвечает, как значение меняется внутри
и вокруг. На картинке они и стоят рядом: оболочки внутри, свечение
вокруг.

Считается на голом NumPy, QGIS здесь не нужен.
"""

import numpy as np

# Потолок по ячейкам. Массив цвета это четыре байта на ячейку, и куб
# двести на двести на сто это шестьдесят четыре мегабайта только
# под него, не считая работы видеокарты.
MAX_CELLS = 40 * 10 ** 6


def rgba(vol, cutoff=None, density=0.6, colors=None, max_cells=MAX_CELLS):
    """Массив цвета с прозрачностью для рендера объёма.

    Возвращает массив байтов в порядке (x, y, z, RGBA): куб у нас лежит
    как (уровень, строка, столбец), и оси разворачиваются здесь, иначе
    заливка выйдет перевёрнутой.

    Возвращает None, если заливать нечего или куб крупнее потолка:
    пустая сцена лучше, чем съеденная память.

    `cutoff` отсекает низ по значению, `density` правит непрозрачность
    целиком. Пропуски в данных прозрачны: пустота это не ноль.
    """
    vol = np.asarray(vol, dtype=float)
    if vol.ndim != 3 or vol.size == 0:
        return None
    if vol.size > int(max_cells):
        return None
    good = np.isfinite(vol)
    if not good.any():
        return None

    lo = float(np.nanmin(vol))
    hi = float(np.nanmax(vol))
    base = float(cutoff) if cutoff is not None else lo
    span = hi - base
    if span > 1e-12:
        t = np.clip((np.where(good, vol, base) - base) / span, 0.0, 1.0)
    else:
        # Размаха нет: все значения одинаковы. Расти нечему, и заливка
        # берётся ровной, а не пропадает совсем.
        t = np.where(good, 1.0, 0.0)

    if colors is None:
        from .viewer3d import colormap
        cols = colormap(t.ravel())
        rgb = (np.clip(cols[:, :3], 0.0, 1.0) * 255.0).astype(np.uint8)
        rgb = rgb.reshape(vol.shape + (3,))
    else:
        rgb = np.asarray(colors, dtype=np.uint8).reshape(vol.shape + (3,))

    a = t * float(density)
    a = np.where(good, a, 0.0)
    if cutoff is not None:
        # Ровно на отсечке заливки ещё нет: иначе у тела появляется
        # плёнка по всей границе куба, где значение случайно совпало.
        a = np.where(vol > float(cutoff), a, 0.0)
    alpha = (np.clip(a, 0.0, 1.0) * 255.0).astype(np.uint8)

    out = np.empty(vol.shape + (4,), dtype=np.uint8)
    out[..., :3] = rgb
    out[..., 3] = alpha
    # (уровень, строка, столбец) -> (x, y, z)
    return np.ascontiguousarray(np.transpose(out, (2, 1, 0, 3)))
