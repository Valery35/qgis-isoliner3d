# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Модель демонстрационной залежи и разбуривание её скважинами.

Считается на голом NumPy, QGIS здесь не нужен. Инструмент 2.01 только
раскладывает результат по объектам слоя, а сама модель живёт тут:
тогда проверки сравнивают интерполяцию с той же истиной, по которой
данные и построены.

Три типа залежи. Пласт со складкой и падением проверяет главное:
горизонтальные уровни куба режут залежь поперёк, и это видно.
Линза даёт простой изотропный случай для сравнения методов. Крутая
жила проверяет обратный крайний случай, когда тело почти вертикально.

Содержание построено с плоской вершиной и быстрым спадом: отсечка
по половине ядра даёт тело с чёткой границей, а не облако. Внутри
залежи содержание меняется по площади, поэтому методы интерполяции
расходятся между собой и есть что сравнивать.
"""

import math

import numpy as np

KINDS = ("bed", "lens", "vein")


def make_model(kind="bed", x0=0.0, y0=0.0, width=1000.0, height=1000.0,
               top=0.0, depth=200.0, core=8.0, back=0.3):
    """Описание залежи: тип, охват площадки, отметки, содержания.

    core это содержание в ядре сверх фона, back это фон во вмещающих
    породах. Пропорции тела задаются от размеров площадки, поэтому
    модель одинаково выглядит и на километре, и на десяти.
    """
    if kind not in KINDS:
        raise ValueError("неизвестный тип залежи: %r" % (kind,))
    return {
        "kind": kind,
        "x0": float(x0), "y0": float(y0),
        "w": float(width), "h": float(height),
        "top": float(top), "depth": float(depth),
        "core": float(core), "back": float(back),
    }


def _uv(x, y, m):
    """Координаты внутри площадки, от нуля до единицы."""
    u = (np.asarray(x, dtype=float) - m["x0"]) / max(m["w"], 1e-9)
    v = (np.asarray(y, dtype=float) - m["y0"]) / max(m["h"], 1e-9)
    return u, v


def surface_top(x, y, m):
    """Отметка дневной поверхности: пологий рельеф над площадкой."""
    u, v = _uv(x, y, m)
    amp = m["depth"] * 0.06
    return m["top"] + amp * (0.6 * np.sin(2 * math.pi * 1.3 * u + 0.4)
                             + 0.4 * np.cos(2 * math.pi * 0.9 * v + 1.7))


def bed_roof(x, y, m):
    """Кровля пласта: наклон на восток плюс складка."""
    u, v = _uv(x, y, m)
    fold = m["depth"] * 0.11
    mid = (m["top"] - m["depth"] * 0.42
           - m["depth"] * 0.30 * u
           + fold * np.sin(2 * math.pi * 1.4 * v + 0.6)
           + 0.5 * fold * np.sin(2 * math.pi * 0.9 * u + 2.0))
    return mid + bed_thickness(x, y, m) / 2.0


def bed_thickness(x, y, m):
    """Мощность пласта: меняется по площади, нигде не вырождается."""
    u, v = _uv(x, y, m)
    base = m["depth"] * 0.13
    wave = (0.5 + 0.5 * np.sin(2 * math.pi * 1.1 * u + 1.3)
            * np.cos(2 * math.pi * 0.8 * v + 0.4))
    return base * (0.55 + 0.9 * wave)


def body_coord(x, y, z, m):
    """Положение поперёк тела: ноль в середине, единица на границе.

    Одна величина на все три типа залежи, поэтому и содержание,
    и признак рудной зоны считаются потом одинаково.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    z = np.asarray(z, dtype=float)
    kind = m["kind"]
    if kind == "bed":
        thick = bed_thickness(x, y, m)
        mid = bed_roof(x, y, m) - thick / 2.0
        return (z - mid) / (thick / 2.0)
    if kind == "lens":
        cx = m["x0"] + m["w"] / 2.0
        cy = m["y0"] + m["h"] / 2.0
        cz = m["top"] - m["depth"] / 2.0
        side = min(m["w"], m["h"])
        rx = (x - cx) / (side * 0.28)
        ry = (y - cy) / (side * 0.28)
        rz = (z - cz) / (m["depth"] * 0.13)
        return np.sqrt(rx * rx + ry * ry + rz * rz)
    # vein: крутое тело с падением 75 градусов
    cx = m["x0"] + m["w"] / 2.0
    cy = m["y0"] + m["h"] / 2.0
    cz = m["top"] - m["depth"] / 2.0
    az = math.radians(35.0)
    across = (x - cx) * math.cos(az) + (y - cy) * math.sin(az)
    along = -(x - cx) * math.sin(az) + (y - cy) * math.cos(az)
    across = across - (z - cz) / math.tan(math.radians(75.0))
    side = min(m["w"], m["h"])
    half = side * 0.025 * (0.6 + 0.8 * (0.5 + 0.5 * np.cos(
        2 * math.pi * along / (side * 0.7))))
    return across / half


def richness(x, y, m):
    """Изменчивость содержаний по площади внутри залежи."""
    u, v = _uv(x, y, m)
    r = (1.0
         + 0.45 * np.sin(2 * math.pi * 2.3 * u + 0.7)
         * np.cos(2 * math.pi * 1.9 * v + 1.1)
         + 0.22 * np.sin(2 * math.pi * 3.7 * (u + 0.6 * v) + 2.4))
    return np.clip(r, 0.25, None)


def _profile(s):
    """Содержание поперёк тела: плоская вершина, быстрый спад.

    На границе тела ровно половина ядра, поэтому отсечка в половину
    даёт границу там же, где она заложена.
    """
    s2 = np.asarray(s, dtype=float) ** 2
    return 1.0 / (1.0 + s2 ** 3)


def grade_field(x, y, z, m, rich=True, trend=0.0):
    """Содержание в точке без шума.

    trend это общий наклон содержаний по площадке, доля от ядра
    на всю сторону. Нужен, чтобы данные не сводились к одному телу.
    """
    s = body_coord(x, y, z, m)
    val = _profile(s)
    if rich:
        val = val * richness(x, y, m)
    out = m["back"] + m["core"] * val
    if trend:
        u, v = _uv(x, y, m)
        out = out + trend * m["core"] * 0.5 * (u + v)
    return out


def demo_grade(x, y, z, size=1000.0, top=0.0, depth=200.0):
    """Прежняя модель линзы, оставлена для совместимости проверок."""
    m = make_model("lens", 0.0, 0.0, size, size, top, depth,
                   core=8.0, back=0.0)
    return float(grade_field(x, y, z, m, rich=False, trend=0.15))


def hole_layout(m, holes, rng, short_share=0.15):
    """Сеть скважин: разреженная сетка со сбивкой и разной глубиной.

    Правильная сетка без сбивки даёт интерполяции слишком лёгкую
    задачу, а часть недобуренных скважин нужна, чтобы у куба были
    места без данных.
    """
    holes = int(max(holes, 2))
    nx = int(math.ceil(math.sqrt(holes * m["w"] / max(m["h"], 1e-9))))
    nx = max(nx, 1)
    ny = int(math.ceil(holes / float(nx)))
    sx = m["w"] / float(nx)
    sy = m["h"] / float(ny)
    xs, ys = [], []
    for j in range(ny):
        for i in range(nx):
            xs.append(m["x0"] + (i + 0.5) * sx)
            ys.append(m["y0"] + (j + 0.5) * sy)
    xs = np.array(xs[:holes], dtype=float)
    ys = np.array(ys[:holes], dtype=float)
    xs = xs + rng.uniform(-0.3, 0.3, xs.size) * sx
    ys = ys + rng.uniform(-0.3, 0.3, ys.size) * sy
    xs = np.clip(xs, m["x0"], m["x0"] + m["w"])
    ys = np.clip(ys, m["y0"], m["y0"] + m["h"])

    collar = surface_top(xs, ys, m)
    base = m["top"] - m["depth"]
    length = (collar - base) * (1.0 + 0.10 * rng.normal(size=xs.size))
    length = np.maximum(length, m["depth"] * 0.2)
    n_short = int(round(short_share * xs.size))
    if n_short > 0:
        idx = rng.choice(xs.size, size=n_short, replace=False)
        length[idx] = length[idx] * rng.uniform(0.45, 0.7, n_short)
    return xs, ys, collar, length


def hole_samples(m, xs, ys, collar, length, rng, sample=2.0, noise=0.12,
                 incline=0.0, trend=0.0):
    """Опробование стволов по интервалам.

    Возвращает поля пробы: номер скважины, интервал от и до, координаты
    середины интервала, содержание с шумом, истину и признак рудной
    зоны. Шум логнормальный: содержания так и распределены,
    и отрицательных значений не возникает.
    """
    sample = float(max(sample, 1e-3))
    out = {"hole": [], "from_m": [], "to_m": [], "x": [], "y": [],
           "z": [], "grade": [], "truth": [], "zone": []}
    for k in range(xs.size):
        n = int(max(math.floor(length[k] / sample), 1))
        d0 = np.arange(n, dtype=float) * sample
        d1 = d0 + sample
        dm = (d0 + d1) / 2.0
        if incline > 0.0:
            az = rng.uniform(0.0, 2 * math.pi)
            tilt = math.radians(incline) * rng.uniform(0.3, 1.0)
            dx = dm * math.sin(tilt) * math.cos(az)
            dy = dm * math.sin(tilt) * math.sin(az)
            dz = dm * math.cos(tilt)
        else:
            dx = np.zeros(n)
            dy = np.zeros(n)
            dz = dm
        px = xs[k] + dx
        py = ys[k] + dy
        pz = collar[k] - dz
        truth = grade_field(px, py, pz, m, trend=trend)
        s = body_coord(px, py, pz, m)
        if noise > 0.0:
            sd = float(noise)
            val = truth * np.exp(sd * rng.normal(size=n) - sd * sd / 2.0)
        else:
            val = truth.copy()
        out["hole"].append(np.full(n, k + 1, dtype=int))
        out["from_m"].append(d0)
        out["to_m"].append(d1)
        out["x"].append(px)
        out["y"].append(py)
        out["z"].append(pz)
        out["grade"].append(val)
        out["truth"].append(truth)
        out["zone"].append((np.abs(s) <= 1.0).astype(int))
    return {k: np.concatenate(v) for k, v in out.items()}


def cutoff_for(m):
    """Отсечка, отделяющая тело: половина ядра над фоном."""
    return m["back"] + m["core"] * 0.5
