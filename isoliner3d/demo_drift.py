# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Демонстрационная выработка: зарисовки бортов, скважины, борозды.

Набор с ЗАЛОЖЕННОЙ ИСТИНОЙ. Пласты заданы формулами, содержания тоже,
шум добавляется отдельно. Поэтому по любому построению видно не
«похоже», а величину промаха: объём тела по зарисовкам сравнивается
с истинным объёмом модели, а оценка содержания - с полем `truth`.

Выработка - штрек с двумя сбойками поперёк. Такая форма выбрана
не для красоты: у штрека два борта дают параллельные разрезы, сбойки
дают пересечения, где отметки обязаны сойтись, а между ними остаётся
площадь, которую интерполяции надо заполнить. На одном шурфе ни того,
ни другого не увидеть.

Пласты названы по-калийному: КрII, АБ и В. В набор нарочно заложены
случаи, на которых инструменты и спотыкались:

- подошва КрII и кровля АБ проведены ОДНОЙ линией - склейка контактов
  должна их узнать и построить одной поверхностью;
- между АБ и В лежит пропласток, и контакта там нет: склейки быть
  не должно, а расхождение должно попасть в журнал;
- внутри АБ на одном борту нарисована линза тем же номером пласта -
  границу тела она трогать не должна;
- пласт В выклинивается и на дальнюю сбойку не выходит вовсе, поэтому
  без обрезки по своим разрезам его растянет на всю площадь.

Содержаний два: KCl и нерастворимый остаток. Они связаны обратно -
там, где сильвина больше, остатка меньше, - и на них видно, как
в гриде живут несколько каналов сразу.

Модуль чистый: NumPy и ничего больше. QGIS появляется только
в инструменте, который раскладывает это по слоям.
"""
import numpy as np


BEDS = ("КрII", "АБ", "В")


def make_model(x0=0.0, y0=0.0, length=200.0, width=4.0, base=-250.0):
    """Модель залегания: три пласта над штреком, с падением и складкой.

    Отметки считаются формулами, а не случайными числами: истина должна
    быть воспроизводимой, иначе сравнивать построенное не с чем.

    Пласты идут сверху вниз: КрII, АБ, В. Подошва КрII и кровля АБ -
    ОДНА поверхность (общий контакт), между АБ и В лежит пропласток.
    """
    return {
        "x0": float(x0), "y0": float(y0),
        "length": float(length), "width": float(width),
        "base": float(base),
    }


def _u(model, x):
    """Доля вдоль штрека: ноль в начале, единица в конце."""
    return (np.asarray(x, dtype=float) - model["x0"]) / model["length"]


def roof_of(model, bed, x, y):
    """Отметка кровли пласта.

    Общий вид: пологое падение вдоль штрека плюс складка. Складка
    нужна, чтобы поверхность нельзя было угадать плоскостью: на плоской
    модели любая интерполяция выглядит одинаково хорошо.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    u = _u(model, x)
    dy = (y - model["y0"]) * 0.004
    fold = 0.9 * np.sin(2.0 * np.pi * u) + 0.35 * np.sin(6.3 * u)
    top = model["base"] + 6.0 - 3.5 * u + fold + dy
    if bed == "КрII":
        return top
    if bed == "АБ":
        return top - thickness_of(model, "КрII", x, y)
    # Между АБ и В пропласток: контакта нет, и склейке взяться неоткуда.
    return (top - thickness_of(model, "КрII", x, y)
            - thickness_of(model, "АБ", x, y) - parting_of(model, x, y))


def thickness_of(model, bed, x, y):
    """Мощность пласта. Меняется по площади, у В есть выклинивание."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    u = _u(model, x)
    if bed == "КрII":
        return 1.30 + 0.45 * np.sin(3.1 * u + 0.4) + 0.02 * (y - model["y0"])
    if bed == "АБ":
        return 2.10 + 0.60 * np.cos(2.2 * u) - 0.03 * (y - model["y0"])
    # В выклинивается к дальнему концу: к концу штрека мощность падает
    # до нуля, и там пласта нет вовсе.
    return np.maximum(1.60 * (1.0 - 1.55 * u), 0.0)


def parting_of(model, x, y):
    """Мощность пропластка между АБ и В."""
    u = _u(model, x)
    return 0.55 + 0.25 * np.sin(4.0 * u)


def floor_of(model, bed, x, y):
    return roof_of(model, bed, x, y) - thickness_of(model, bed, x, y)


def grades_at(model, bed, x, y, z):
    """Содержания в точке: KCl и нерастворимый остаток.

    Связаны обратно: где сильвина больше, остатка меньше. Это не
    украшение, а свойство сильвинитовой руды, и на паре каналов видно,
    что в гриде их живёт несколько сразу.

    Внутри пласта содержание меняется по мощности: у кровли и подошвы
    оно ниже, чем в середине. Иначе борозда по мощности показывала бы
    одно и то же число, и делить её на интервалы было бы незачем.
    """
    x = np.asarray(x, dtype=float)
    z = np.asarray(z, dtype=float)
    u = _u(model, x)
    core = {"КрII": 31.0, "АБ": 26.0, "В": 21.0}.get(bed, 20.0)
    top = roof_of(model, bed, x, y)
    thick = np.maximum(thickness_of(model, bed, x, y), 1e-6)
    # Доля мощности: ноль у кровли, единица у подошвы.
    t = np.clip((top - z) / thick, 0.0, 1.0)
    shape = 1.0 - 1.7 * (t - 0.5) ** 2
    kcl = core * shape * (1.0 + 0.10 * np.sin(5.0 * u))
    kcl = np.maximum(kcl, 0.5)
    no = np.maximum(24.0 - 0.55 * kcl + 2.0 * (1.0 - shape), 0.3)
    return kcl, no


def noisy(rng, values, share):
    """Логнормальный шум опробования: отрицательных содержаний не даёт."""
    v = np.asarray(values, dtype=float)
    if share <= 0:
        return v
    return v * np.exp(rng.normal(0.0, float(share), size=v.shape))


def walls(model, crosscuts=2, cross_len=20.0):
    """Борта выработки как отрезки в плане.

    Возвращает список (имя, (x1, y1), (x2, y2)). Штрек даёт два борта,
    каждая сбойка ещё два. Борта штрека параллельны, борта сбоек их
    пересекают - на пересечениях отметки и обязаны сойтись.
    """
    x0, y0 = model["x0"], model["y0"]
    L, w = model["length"], model["width"]
    out = [("штрек, левый борт", (x0, y0), (x0 + L, y0)),
           ("штрек, правый борт", (x0, y0 + w), (x0 + L, y0 + w))]
    n = max(int(crosscuts), 0)
    for k in range(n):
        cx = x0 + L * (k + 1.0) / (n + 1.0)
        half = float(cross_len) / 2.0
        out.append(("сбойка %d, ближний борт" % (k + 1),
                    (cx, y0 - half), (cx, y0 + w + half)))
        out.append(("сбойка %d, дальний борт" % (k + 1),
                    (cx + 2.0, y0 - half), (cx + 2.0, y0 + w + half)))
    return out


def wall_ring(model, bed, wall, step=1.0, flip=False):
    """Контур пласта на борту: кольцо по кровле вперёд и по подошве назад.

    Пласта на борту может не быть вовсе (выклинился) - тогда кольца нет
    и возвращается None. Так в наборе появляется пласт, встреченный
    не на всех бортах, а он и нужен для обрезки по своим разрезам.
    """
    _nm, (ax, ay), (bx, by) = wall
    n = max(int(np.hypot(bx - ax, by - ay) / max(step, 1e-6)) + 1, 2)
    t = np.linspace(0.0, 1.0, n)
    xs, ys = ax + (bx - ax) * t, ay + (by - ay) * t
    top = roof_of(model, bed, xs, ys)
    bot = floor_of(model, bed, xs, ys)
    good = (top - bot) > 0.05
    if good.sum() < 3:
        return None
    xs, ys, top, bot = xs[good], ys[good], top[good], bot[good]
    if flip:
        xs, ys, top, bot = xs[::-1], ys[::-1], top[::-1], bot[::-1]
    ring = np.vstack([
        np.column_stack([xs, ys, top]),
        np.column_stack([xs[::-1], ys[::-1], bot[::-1]])])
    return np.vstack([ring, ring[:1]])


def lens_ring(model, bed, wall, at=0.45, span=0.14):
    """Линза внутри пласта, нарисованная тем же номером.

    Кладётся в средней части борта и целиком внутри пласта: границу
    тела она трогать не должна, а раньше тянула кровлю к подошве.
    """
    _nm, (ax, ay), (bx, by) = wall
    t = np.linspace(max(at - span, 0.02), min(at + span, 0.98), 12)
    xs, ys = ax + (bx - ax) * t, ay + (by - ay) * t
    top = roof_of(model, bed, xs, ys)
    thick = thickness_of(model, bed, xs, ys)
    hi = top - 0.30 * thick
    lo = top - 0.62 * thick
    if np.any((hi - lo) < 0.05):
        return None
    ring = np.vstack([
        np.column_stack([xs, ys, hi]),
        np.column_stack([xs[::-1], ys[::-1], lo[::-1]])])
    return np.vstack([ring, ring[:1]])


def fan_holes(model, rng, stations=6, per_fan=5, length=12.0,
              sample=0.5, noise=0.10):
    """Скважины веером из штрека: пробы по интервалам.

    Из выработки бурят вверх и вбок, а не сверху вниз, поэтому стволы
    наклонные и веером. На таких данных видно, что интерполяции в объёме
    достаётся не сетка, а пучки.

    Возвращает словарь массивов: hole, from_m, to_m, x, y, z, kcl, no,
    kcl_truth, no_truth, bed.
    """
    x0, y0 = model["x0"], model["y0"]
    L, w = model["length"], model["width"]
    out = {k: [] for k in ("hole", "from_m", "to_m", "x", "y", "z",
                           "kcl", "no", "kcl_t", "no_t", "bed")}
    hole = 0
    for s in range(max(int(stations), 1)):
        sx = x0 + L * (s + 0.5) / max(int(stations), 1)
        sy = y0 + w * 0.5
        sz = roof_of(model, "В", sx, sy) - 0.5
        for k in range(max(int(per_fan), 1)):
            hole += 1
            # Веер раскрывается поперёк штрека и вверх: так вскрывают
            # пласты над выработкой.
            az = -60.0 + 120.0 * k / max(int(per_fan) - 1, 1)
            a = np.radians(az)
            dirv = np.array([0.15 * np.sin(a), np.sin(a), abs(np.cos(a))])
            dirv = dirv / np.linalg.norm(dirv)
            n_int = max(int(length / max(sample, 1e-3)), 1)
            for i in range(n_int):
                f, t = i * sample, (i + 1) * sample
                mid = (f + t) / 2.0
                p = np.array([sx, sy, sz]) + dirv * mid
                bed = bed_at(model, p[0], p[1], p[2])
                if bed is None:
                    continue
                kt, nt = grades_at(model, bed, p[0], p[1], p[2])
                out["hole"].append(hole)
                out["from_m"].append(f)
                out["to_m"].append(t)
                out["x"].append(p[0])
                out["y"].append(p[1])
                out["z"].append(p[2])
                out["kcl_t"].append(float(kt))
                out["no_t"].append(float(nt))
                out["kcl"].append(float(noisy(rng, kt, noise)))
                out["no"].append(float(noisy(rng, nt, noise)))
                out["bed"].append(bed)
    return {k: (np.asarray(v) if k != "bed" else v)
            for k, v in out.items()}


def grooves(model, rng, stations=8, sample=0.25, noise=0.08):
    """Борозды по мощности пласта на бортах штрека.

    Борозда бьётся от кровли до подошвы и делится на интервалы, у
    каждого своё содержание. Это основной вид опробования на калийном
    руднике, и геометрия у него та же: объект на борту с числами.
    """
    x0, y0 = model["x0"], model["y0"]
    L, w = model["length"], model["width"]
    out = {k: [] for k in ("groove", "bed", "wall", "from_m", "to_m",
                           "x", "y", "z", "kcl", "no", "kcl_t", "no_t",
                           "thick")}
    g = 0
    for s in range(max(int(stations), 1)):
        gx = x0 + L * (s + 0.5) / max(int(stations), 1)
        for side, gy in ((1, y0), (2, y0 + w)):
            for bed in BEDS:
                th = float(thickness_of(model, bed, gx, gy))
                if th < 0.15:
                    continue
                g += 1
                top = float(roof_of(model, bed, gx, gy))
                n_int = max(int(round(th / max(sample, 1e-3))), 1)
                step = th / n_int
                for i in range(n_int):
                    f, t = i * step, (i + 1) * step
                    z = top - (f + t) / 2.0
                    kt, nt = grades_at(model, bed, gx, gy, z)
                    out["groove"].append(g)
                    out["bed"].append(bed)
                    out["wall"].append(side)
                    out["from_m"].append(f)
                    out["to_m"].append(t)
                    out["x"].append(gx)
                    out["y"].append(gy)
                    out["z"].append(z)
                    out["thick"].append(th)
                    out["kcl_t"].append(float(kt))
                    out["no_t"].append(float(nt))
                    out["kcl"].append(float(noisy(rng, kt, noise)))
                    out["no"].append(float(noisy(rng, nt, noise)))
    return {k: (np.asarray(v) if k not in ("bed",) else v)
            for k, v in out.items()}


def bed_at(model, x, y, z):
    """В каком пласте лежит точка. Вне пластов - None."""
    for bed in BEDS:
        top = float(roof_of(model, bed, x, y))
        bot = float(floor_of(model, bed, x, y))
        if bot <= z <= top and (top - bot) > 0.05:
            return bed
    return None


def true_volume(model, bed, xa, xb, ya, yb, step=0.5):
    """Истинный объём пласта в прямоугольнике, прямым суммированием.

    Это и есть ответ, с которым сравнивают объём построенного тела.
    Без него демонстрация показывает картинку, а не точность.
    """
    xs = np.arange(xa + step / 2.0, xb, step)
    ys = np.arange(ya + step / 2.0, yb, step)
    if not len(xs) or not len(ys):
        return 0.0
    gx, gy = np.meshgrid(xs, ys)
    th = np.maximum(thickness_of(model, bed, gx, gy), 0.0)
    return float(th.sum() * step * step)
