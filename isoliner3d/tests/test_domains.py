# -*- coding: utf-8 -*-
"""Тела толщ по контурам в любых плоскостях (2.15).

Случай Василия Швалева: три толщи лежат рядом, контакты крутые,
падение 75 градусов. Есть два параллельных разреза в четырёхстах
метрах друг от друга и карта толщ на дневной поверхности. 2.08 тут
не годится: он строит каждую толщу как пласт с кровлей и подошвой
над планом и растягивает все три на общую площадь.

Синтетика повторяет эту геометрию, но с известным ответом: контакты
заданы формулой и между разрезами меняют простирание, так что карта
несёт то, чего на разрезах нет.

Считается на голом NumPy, QGIS не нужен.
"""

import os
import sys

import numpy as np

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import domains                 # noqa: E402

TAN = np.tan(np.radians(75.0))
X1 = 600.0
YS = (0.0, 400.0)                  # разрезы
YMAP = (-60.0, 460.0)              # карта шире разрезов
CODES = (101, 203, 303)


def _topo(x, y):
    return 100.0 + 0.01 * np.asarray(x) + 0.005 * np.asarray(y)


def _c0(k, y):
    """Выход контакта k на дневную поверхность."""
    y = np.asarray(y, dtype=float)
    return (200.0 + 0.1 * y) if k == 0 else (400.0 + 0.05 * y)


def _contact_x(k, y, z):
    """Контакт k: падает на восток под 75 градусов от выхода."""
    x = _c0(k, y) + 0.0 * np.asarray(z)
    for _ in range(8):
        x = _c0(k, y) + (_topo(x, y) - z) / TAN
    return x


def _truth(x, y, z):
    """Код толщи в точке по формуле."""
    g0 = x - _contact_x(0, y, z)
    g1 = x - _contact_x(1, y, z)
    return np.where(g0 < 0, 101, np.where(g1 < 0, 203, 303))


def _section(y):
    """Три контура на вертикальном разрезе y = const."""
    zs = np.linspace(0.0, 1.0, 11)
    rings = []
    edges = [None, 0, 1, None]
    for u in range(3):
        a, b = edges[u], edges[u + 1]
        xa_top = 0.0 if a is None else float(_c0(a, y))
        xb_top = X1 if b is None else float(_c0(b, y))
        top_x = np.linspace(xa_top, xb_top, 9)
        top = np.column_stack([top_x, np.full(9, y), _topo(top_x, y)])
        if b is None:
            right = np.array([[X1, y, 0.0]])
        else:
            zz = _topo(xb_top, y) * (1.0 - zs)
            right = np.column_stack([_contact_x(b, y, zz),
                                     np.full(len(zz), y), zz])[1:]
        if a is None:
            left = np.array([[0.0, y, 0.0]])
        else:
            zz = _topo(xa_top, y) * zs
            left = np.column_stack([_contact_x(a, y, zz),
                                    np.full(len(zz), y), zz])[:-1]
        rings.append(np.vstack([top, right, left]))
    return rings


def _plan():
    """Карта толщ на дневной поверхности, с отметками рельефа."""
    ys = np.linspace(YMAP[0], YMAP[1], 14)
    rings = []
    edges = [None, 0, 1, None]
    for u in range(3):
        a, b = edges[u], edges[u + 1]
        xa = np.zeros_like(ys) if a is None else _c0(a, ys)
        xb = np.full_like(ys, X1) if b is None else _c0(b, ys)
        xs = np.concatenate([xa, xb[::-1]])
        yy = np.concatenate([ys, ys[::-1]])
        rings.append(np.column_stack([xs, yy, _topo(xs, yy)]))
    return rings


def _data(with_plan=True):
    rings, codes = [], []
    for y in YS:
        rings += _section(y)
        codes += list(CODES)
    if with_plan:
        rings += _plan()
        codes += list(CODES)
    return rings, codes


_CACHE = {}


def _model(with_plan=True):
    if with_plan not in _CACHE:
        rings, codes = _data(with_plan)
        _CACHE[with_plan] = domains.build(rings, codes, cell=10.0,
                                          cellz=5.0)
    return _CACHE[with_plan]


def _centres(m):
    gt, z0, dz = m["gt"], m["z0"], m["dz"]
    nz, ny, nx = m["shape"]
    ax = gt[0] + gt[1] * (np.arange(nx) + 0.5)
    ay = gt[3] + gt[5] * (np.arange(ny) + 0.5)
    az = z0 + dz * np.arange(nz)
    return np.meshgrid(az, ay, ax, indexing="ij")


def _accuracy(m):
    Z, Y, X = _centres(m)
    rock = m["cls"] >= 0
    got = np.array(m["codes"])[np.where(rock, m["cls"], 0)]
    true = _truth(X, Y, Z)
    return float((got[rock] == true[rock]).mean()), int(rock.sum())


def test_planes_are_recognised():
    """Два разреза и одна карта: три плоскости, род каждой верный."""
    m = _model()
    assert len(m["groups"]) == 3, m["groups"]
    assert sorted(m["kinds"]) == ["plan", "wall", "wall"], m["kinds"]


def test_every_voxel_gets_one_formation():
    """Щелей и нахлёстов нет: у каждого вокселя горной массы ровно одна
    толща, и все три толщи в модели есть."""
    m = _model()
    rock = m["rock"]
    assert rock.sum() > 1000
    assert (m["cls"][rock] >= 0).all()
    assert set(np.unique(m["cls"][rock]).tolist()) == {0, 1, 2}


def test_formations_are_where_the_formula_puts_them():
    """Толща определена верно не меньше чем в 95 процентах вокселей."""
    acc, n = _accuracy(_model())
    assert acc >= 0.95, (acc, n)


def test_contact_between_the_sections_stands_in_place():
    """Контакт посередине между разрезами, на середине глубины, стоит
    на своём месте с точностью до ячейки. Там нет ни одного разреза,
    контакт держат разрезы по краям и карта сверху."""
    m = _model()
    Z, Y, X = _centres(m)
    nz, ny, nx = m["shape"]
    k = int(round((50.0 - m["z0"]) / m["dz"]))
    j = int(np.argmin(np.abs(Y[0, :, 0] - 200.0)))
    row = m["cls"][k, j]
    xs = X[k, j]
    for c in (0, 1):
        flip = np.where((row[:-1] == c) & (row[1:] == c + 1))[0]
        assert len(flip), row
        got = 0.5 * (xs[flip[0]] + xs[flip[0] + 1])
        true = float(_contact_x(c, Y[k, j, 0], Z[k, 0, 0]))
        assert abs(got - true) <= m["gt"][1], (c, got, true)


def test_map_carries_what_the_sections_miss():
    """Без карты контакт между разрезами идёт по прямой от разреза к
    разрезу. Карта даёт его выход на поверхность и за пределами
    разрезов: на полосе карты вне разрезов модель с картой обязана
    быть заметно точнее."""
    def outside(m):
        Z, Y, X = _centres(m)
        rock = (m["cls"] >= 0) & ((Y < YS[0]) | (Y > YS[1]))
        got = np.array(m["codes"])[np.where(m["cls"] >= 0, m["cls"], 0)]
        return float((got[rock] == _truth(X, Y, Z)[rock]).mean()) \
            if rock.any() else 0.0
    a_plan = outside(_model(True))
    a_none = outside(_model(False))
    assert a_plan >= 0.95, a_plan
    assert a_plan >= a_none, (a_plan, a_none)


def test_relief_caps_the_bodies():
    """Над рельефом горной массы нет."""
    m = _model()
    Z, Y, X = _centres(m)
    over = Z > _topo(X, Y) + m["dz"]
    assert not (m["rock"] & over).any()


def test_body_shells_are_closed_and_add_up():
    """Оболочка каждой толщи без дыр, у каждой толщи одно тело, сумма
    объёмов тел равна объёму горной массы с точностью в несколько
    процентов. Защипы допустимы: это касание тела самого себя, объём
    по такой оболочке точен."""
    m = _model()
    cellv = abs(m["gt"][1] * m["gt"][5]) * m["dz"]
    total = 0.0
    for c in m["codes"]:
        got = domains.bodies(m["margin"][c], m["gt"], m["z0"], m["dz"])
        assert len(got) == 1, (c, len(got))
        _v, f, holes, _pinch, vol = got[0]
        assert len(f) and holes == 0, (c, holes)
        total += vol
    rock = float(m["rock"].sum()) * cellv
    assert abs(total - rock) / rock < 0.08, (total, rock)


def test_absent_formation_pinches_out():
    """Толща есть на одном разрезе и её нет на другом: между ними она
    выклинивается, а не тянется на всю длину."""
    rings, codes = [], []
    s0 = _section(0.0)
    s1 = _section(400.0)
    # на втором разрезе средней толщи нет: её место делят соседи
    rings += s0
    codes += list(CODES)
    left = s1[0].copy()
    right = s1[2].copy()
    mid = 0.5 * (_c0(0, 400.0) + _c0(1, 400.0))
    # сдвигаем контакты второго разреза к середине средней толщи
    left[:, 0] = np.where(left[:, 0] > 1.0, left[:, 0] + (mid - _c0(0, 400.0)), left[:, 0])
    right[:, 0] = np.where(right[:, 0] < X1 - 1.0, right[:, 0] - (_c0(1, 400.0) - mid), right[:, 0])
    rings += [left, right]
    codes += [101, 303]
    m = domains.build(rings, codes, cell=10.0, cellz=5.0)
    k = list(m["codes"]).index(203)
    Z, Y, X = _centres(m)
    near0 = (m["cls"] == k) & (Y < 50.0)
    near1 = (m["cls"] == k) & (Y > 350.0)
    assert near0.sum() > 5 * max(near1.sum(), 1), (near0.sum(), near1.sum())


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all domains tests passed")


if __name__ == "__main__":
    _run()
