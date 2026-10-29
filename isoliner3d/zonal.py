# -*- coding: utf-8 -*-
"""Статистика атрибута по объектам внутри тела (2.14).

Сумма атрибута по телу - это запас, когда атрибут уже металл блока.
Для содержания сумма бессмысленна: нужно среднее, разброс и квантили.
Просьба Василия Швалёва.

Вес объекта: у точек и полигонов единица, у линий длина их части
внутри тела. Так интервалы опробования, вошедшие в рудное тело
наполовину, дают содержание, взвешенное по длине внутри, как при
подсчёте по композитам.

Разброс - стандартное отклонение со взвешиванием, без поправки
на число проб: это разброс самих значений внутри тела, а не оценка
по выборке. Квантиль взвешенный: значения сортируются, каждому
отводится доля веса, и квантиль берётся линейно между серединами
долей. При равных весах это обычный квантиль по Хазену.

Считается на голом NumPy, QGIS не нужен.
"""

import numpy as np

# ключ, суффикс поля, русское название пункта
STATS = (
    ("sum", "_sum", "Сумма"),
    ("mean", "_mean", "Среднее"),
    ("min", "_min", "Минимум"),
    ("max", "_max", "Максимум"),
    ("std", "_std", "Стандартное отклонение"),
    ("med", "_med", "Медиана"),
    ("quart", ("_p25", "_p75"), "Квартили 25 и 75 %"),
    ("decile", ("_p10", "_p90"), "Квантили 10 и 90 %"),
)

KEYS = tuple(k for k, _s, _t in STATS)


def suffixes(keys):
    """Суффиксы полей для выбранных показателей, в порядке STATS."""
    out = []
    for k, suf, _t in STATS:
        if k in keys:
            out.extend(suf if isinstance(suf, tuple) else (suf,))
    return out


def wquantile(values, weights, q):
    """Взвешенный квантиль `q` (0..1) или None без значений."""
    v = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    ok = np.isfinite(v) & np.isfinite(w) & (w > 0)
    v, w = v[ok], w[ok]
    if not len(v):
        return None
    if len(v) == 1:
        return float(v[0])
    order = np.argsort(v, kind="stable")
    v, w = v[order], w[order]
    mid = (np.cumsum(w) - 0.5 * w) / w.sum()
    return float(np.interp(q, mid, v))


def stats(values, weights, keys):
    """Показатели по значениям с весами: {суффикс: число или None}.

    Пустые значения (None, NaN) не участвуют ни в чём, кроме суммы,
    где они просто не прибавляются. Без единого значения всё пусто,
    кроме суммы: у тела без проб сумма ноль.
    """
    v = np.array([np.nan if x is None else x for x in values], dtype=float)
    w = np.asarray(weights, dtype=float)
    if len(w) != len(v):
        raise ValueError("values and weights differ in length")
    ok = np.isfinite(v) & np.isfinite(w) & (w > 0)
    vv, ww = v[ok], w[ok]
    out = {}
    has = len(vv) > 0
    if "sum" in keys:
        # сумма как и раньше без весов: запас тела - сумма металла
        # блоков, а не средний металл
        out["_sum"] = float(np.nansum(v[np.isfinite(w) & (w > 0)])) \
            if len(v) else 0.0
    mean = float(np.average(vv, weights=ww)) if has else None
    if "mean" in keys:
        out["_mean"] = mean
    if "min" in keys:
        out["_min"] = float(vv.min()) if has else None
    if "max" in keys:
        out["_max"] = float(vv.max()) if has else None
    if "std" in keys:
        out["_std"] = float(np.sqrt(np.average((vv - mean) ** 2,
                                               weights=ww))) if has else None
    if "med" in keys:
        out["_med"] = wquantile(vv, ww, 0.5)
    if "quart" in keys:
        out["_p25"] = wquantile(vv, ww, 0.25)
        out["_p75"] = wquantile(vv, ww, 0.75)
    if "decile" in keys:
        out["_p10"] = wquantile(vv, ww, 0.10)
        out["_p90"] = wquantile(vv, ww, 0.90)
    return out
