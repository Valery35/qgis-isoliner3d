# -*- coding: utf-8 -*-
"""Проверка спрямления: отсчёт вертикали от опорной поверхности.

В абсолютных отметках интерполяция идёт поперёк напластования: у складки
соседи по вертикали лежат в другой пачке, а свои по пласту оказываются
далеко. Спрямление переводит отметку в отсчёт от кровли или подошвы,
там пласт горизонтален, и связь считается вдоль него.

Считается на голом NumPy, QGIS не нужен.
"""

import os
import sys

import numpy as np

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import flatten   # noqa: E402

# грид 10 на 10, ячейка 100 м, кровля наклонена по X
GT = (0.0, 100.0, 0.0, 1000.0, 0.0, -100.0)


def _roof():
    """Кровля с уклоном: на западе ноль, на востоке сто метров."""
    xs = GT[0] + (np.arange(10) + 0.5) * GT[1]
    return np.repeat((xs / 10.0)[None, :], 10, axis=0)


def test_offset_from_the_reference_is_the_difference():
    """Спрямлённая отметка это разность с опорной поверхностью."""
    ref = _roof()
    x = np.array([50.0, 950.0])
    y = np.array([500.0, 500.0])
    z = np.array([10.0, 100.0])
    got = flatten.to_flat(x, y, z, ref, GT)
    assert abs(got[0] - (10.0 - 5.0)) < 1e-6, got
    assert abs(got[1] - (100.0 - 95.0)) < 1e-6, got


def test_flat_and_back_returns_the_same():
    """Обратный перевод возвращает исходную отметку.

    Иначе куб нельзя вернуть в настоящие отметки, и он останется
    картинкой в выдуманных координатах.
    """
    ref = _roof()
    rs = np.random.RandomState(0)
    x = rs.uniform(0, 1000, 50)
    y = rs.uniform(0, 1000, 50)
    z = rs.uniform(-50, 150, 50)
    f = flatten.to_flat(x, y, z, ref, GT)
    back = flatten.from_flat(x, y, f, ref, GT)
    ok = np.isfinite(back) & np.isfinite(f)
    assert ok.sum() > 20, int(ok.sum())
    assert np.allclose(back[ok], z[ok], atol=1e-6)


def test_outside_the_reference_is_a_gap():
    """Там, где опорной поверхности нет, отметку не выдумываем."""
    ref = _roof().copy()
    ref[:, :3] = np.nan
    got = flatten.to_flat(np.array([50.0, 950.0]),
                          np.array([500.0, 500.0]),
                          np.array([10.0, 100.0]), ref, GT)
    assert not np.isfinite(got[0])
    assert np.isfinite(got[1])


def test_a_dipping_bed_becomes_horizontal():
    """Наклонный пласт в спрямлённых координатах ложится плоско.

    Это и есть смысл спрямления: разброс спрямлённой отметки внутри
    пласта должен быть много меньше, чем разброс абсолютной.
    """
    ref = _roof()
    rs = np.random.RandomState(1)
    x = rs.uniform(0, 1000, 400)
    y = rs.uniform(0, 1000, 400)
    # пробы лежат в пласте: пять метров под кровлей, плюс мелкий шум
    z = flatten.sample(x, y, ref, GT) - 5.0 + rs.normal(scale=0.3, size=400)
    f = flatten.to_flat(x, y, z, ref, GT)
    # У края грида пропуски: билинейной выборке нужны четыре соседа.
    ok = np.isfinite(f)
    assert ok.mean() > 0.6, ok.mean()
    assert np.std(f[ok]) < 0.2 * np.std(z[ok]), (np.std(f[ok]),
                                                 np.std(z[ok]))


def test_thickness_mode_normalises_between_two_surfaces():
    """По мощности отметка становится долей от кровли до подошвы.

    Так пачки разной мощности сопоставляются друг с другом: ноль
    на кровле, единица на подошве.
    """
    roof = _roof()
    floor = roof - 20.0
    x = np.array([500.0, 500.0, 500.0])
    y = np.full(3, 500.0)
    top = flatten.sample(x, y, roof, GT)
    z = np.array([top[0], top[1] - 10.0, top[2] - 20.0])
    got = flatten.to_flat(x, y, z, roof, GT, floor=floor)
    assert abs(got[0]) < 1e-6, got
    assert abs(got[1] - 0.5) < 1e-6, got
    assert abs(got[2] - 1.0) < 1e-6, got


def test_thickness_mode_survives_a_zero_thickness():
    """Нулевая мощность не роняет расчёт, а даёт пропуск."""
    roof = _roof()
    got = flatten.to_flat(np.array([500.0]), np.array([500.0]),
                          np.array([0.0]), roof, GT, floor=roof)
    assert not np.isfinite(got[0])


def test_thickness_mode_returns_back():
    """Из доли мощности отметка возвращается обратно."""
    roof = _roof()
    floor = roof - 20.0
    x = np.array([200.0, 800.0])
    y = np.array([300.0, 700.0])
    f = np.array([0.25, 0.75])
    z = flatten.from_flat(x, y, f, roof, GT, floor=floor)
    back = flatten.to_flat(x, y, z, roof, GT, floor=floor)
    assert np.allclose(back, f, atol=1e-6)


def test_between_surfaces_keeps_the_slab():
    """Между двумя поверхностями остаётся то, что внутри.

    Одной отметкой этого не заменить: кровля и подошва меняются
    по площади, а отметка плоская.
    """
    roof = _roof()
    floor = roof - 20.0
    x = np.array([500.0, 500.0, 500.0, 500.0])
    y = np.full(4, 500.0)
    top = flatten.sample(x, y, roof, GT)
    z = np.array([top[0] + 5.0, top[1] - 5.0, top[2] - 15.0,
                  top[3] - 25.0])
    keep = flatten.keep_between(x, y, z, roof, GT, floor, GT)
    assert keep.tolist() == [False, True, True, False], keep


def test_only_top_surface_cuts_from_above():
    """Одна поверхность сверху отсекает всё, что выше неё."""
    roof = _roof()
    x = np.array([500.0, 500.0])
    y = np.full(2, 500.0)
    top = flatten.sample(x, y, roof, GT)
    z = np.array([top[0] + 1.0, top[1] - 1.0])
    keep = flatten.keep_between(x, y, z, roof, GT, None, None)
    assert keep.tolist() == [False, True]


def test_only_bottom_surface_cuts_from_below():
    roof = _roof()
    x = np.array([500.0, 500.0])
    y = np.full(2, 500.0)
    base = flatten.sample(x, y, roof, GT)
    z = np.array([base[0] + 1.0, base[1] - 1.0])
    keep = flatten.keep_between(x, y, z, None, None, roof, GT)
    assert keep.tolist() == [True, False]


def test_outside_the_surface_is_dropped():
    """Точка без поверхности не остаётся: отсечь её нечем.

    Пропустить её значит показать данные там, где отсечка не работала,
    и человек не отличит одно от другого.
    """
    roof = _roof().copy()
    roof[:, :3] = np.nan
    keep = flatten.keep_between(np.array([50.0, 950.0]),
                                np.array([500.0, 500.0]),
                                np.array([0.0, 0.0]), roof, GT,
                                None, None)
    assert not keep[0]


def test_no_surfaces_keeps_everything():
    keep = flatten.keep_between(np.array([1.0, 2.0]),
                                np.array([1.0, 2.0]),
                                np.array([1.0, 2.0]),
                                None, None, None, None)
    assert keep.all()


def test_bounds_are_inclusive():
    """Точка ровно на поверхности остаётся: иначе пропадёт кровля."""
    roof = _roof()
    x = np.array([500.0])
    y = np.array([500.0])
    z = flatten.sample(x, y, roof, GT)
    assert flatten.keep_between(x, y, z, roof, GT, None, None)[0]


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all flatten tests passed")


if __name__ == "__main__":
    _run()
