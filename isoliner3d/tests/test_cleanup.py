# -*- coding: utf-8 -*-
"""Проверка чистки поверхности: сглаживание и отброс мелочи.

Маршевая поверхность идёт ступенями по ячейкам, и мелкие обрывки на ней
шумят. Лечится это прямо на поверхности: сгладить вершины и выбросить
куски мельче заданного числа граней. Сшивать изолинии между уровнями
для этого не нужно.

Считается на голом NumPy, QGIS не нужен.
"""

import os
import sys

import numpy as np

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import cleanup   # noqa: E402


def _two_parts():
    """Большой квадрат и крохотный треугольник в стороне."""
    v = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0],
                  [0.0, 1.0, 0.0],
                  [9.0, 9.0, 0.0], [9.1, 9.0, 0.0], [9.0, 9.1, 0.0]])
    f = np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6]])
    return v, f


def test_small_part_is_dropped():
    """Кусок мельче порога выбрасывается целиком."""
    v, f = _two_parts()
    _v2, f2 = cleanup.drop_small(v, f, min_faces=2)
    assert len(f2) == 2, len(f2)


def test_big_part_survives():
    v, f = _two_parts()
    _v2, f2 = cleanup.drop_small(v, f, min_faces=1)
    assert len(f2) == 3


def test_dropping_everything_is_refused():
    """Порог выше всего оставляет поверхность как была.

    Пустая сцена вместо тела это не чистка, а потеря: лучше показать
    как есть и дать человеку убавить порог.
    """
    v, f = _two_parts()
    _v2, f2 = cleanup.drop_small(v, f, min_faces=100)
    assert len(f2) == len(f)


def test_parts_are_counted():
    v, f = _two_parts()
    assert cleanup.count_parts(v, f) == 2


def test_smoothing_pulls_a_spike_in():
    """Ступень сглаживается: выброс тянется к соседям.

    Выброс берём внутренним: краевая вершина стоит на месте
    по построению, и на ней сглаживания не увидеть.
    """
    xs, ys = np.meshgrid(np.arange(3.0), np.arange(3.0))
    v = np.column_stack([xs.ravel(), ys.ravel(),
                         np.zeros(9)])
    v[4, 2] = 5.0                      # середина поднята
    f = []
    for r in range(2):
        for c in range(2):
            a = r * 3 + c
            f += [[a, a + 1, a + 4], [a, a + 4, a + 3]]
    f = np.array(f, dtype=np.int64)
    v2 = cleanup.smooth(v, f, rounds=3, strength=0.5)
    assert v2[4, 2] < 2.0, v2[4, 2]


def test_smoothing_keeps_the_border():
    """Края не двигаются: иначе срез перестанет лежать в плоскости.

    Крышка на срезе строится по краевым рёбрам, и стоит их сдвинуть,
    как она перестанет сходиться с телом.
    """
    v = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0],
                  [0.0, 1.0, 0.0], [0.5, 0.5, 3.0]])
    f = np.array([[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]])
    v2 = cleanup.smooth(v, f, rounds=5, strength=1.0)
    assert np.allclose(v2[:4], v[:4]), v2[:4]
    assert v2[4, 2] < 3.0


def test_smoothing_zero_rounds_changes_nothing():
    v, f = _two_parts()
    assert np.allclose(cleanup.smooth(v, f, rounds=0), v)


def test_smoothing_survives_an_empty_mesh():
    v = np.zeros((0, 3))
    f = np.zeros((0, 3), dtype=np.int64)
    assert len(cleanup.smooth(v, f, rounds=2)) == 0
    assert len(cleanup.drop_small(v, f, 3)[1]) == 0


def _cube(x0, x1, y0, y1, z0, z1):
    """Замкнутый ящик из двенадцати треугольников."""
    v = np.array([[x, y, z] for x in (x0, x1) for y in (y0, y1)
                  for z in (z0, z1)], dtype=float)
    f = np.array([[0, 2, 3], [0, 3, 1], [4, 5, 7], [4, 7, 6],
                  [0, 1, 5], [0, 5, 4], [2, 6, 7], [2, 7, 3],
                  [0, 4, 6], [0, 6, 2], [1, 3, 7], [1, 7, 5]],
                 dtype=np.int64)
    return v, f


def test_volume_needs_consistent_winding():
    """Обход граней согласуется перед счётом объёма.

    Формула складывает подписанные объёмы тетраэдров, и грань,
    обойдённая в другую сторону, вычитается вместо сложения. У маршевой
    поверхности с крышками обход вразнобой, и без согласования объём
    выходит втрое меньше настоящего.
    """
    v, f = _cube(0.0, 10.0, 0.0, 10.0, 0.0, 10.0)
    mixed = f.copy()
    mixed[::2] = mixed[::2][:, ::-1]      # половину вывернули
    assert abs(cleanup.mesh_volume(v, mixed) - 1000.0) < 1e-6


def test_orient_returns_a_consistent_mesh():
    v, f = _cube(0.0, 10.0, 0.0, 10.0, 0.0, 10.0)
    mixed = f.copy()
    mixed[1::3] = mixed[1::3][:, ::-1]
    got = cleanup.orient_faces(v, mixed)
    assert got.shape == f.shape
    a, b, c = v[got[:, 0]], v[got[:, 1]], v[got[:, 2]]
    signed = np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0
    assert abs(abs(signed) - 1000.0) < 1e-6, signed


def test_volume_of_a_box():
    """Объём замкнутой оболочки считается точно.

    Считать его по ячейкам нельзя: оболочка режет ячейки пополам,
    и сумма по целым даёт ступенчатую ошибку.
    """
    v, f = _cube(0.0, 10.0, 0.0, 20.0, 0.0, 5.0)
    got = cleanup.mesh_volume(v, f)
    assert abs(got - 1000.0) < 1e-6, got


def test_volume_ignores_face_direction():
    """Вывернутая наизнанку оболочка даёт тот же объём, а не минус."""
    v, f = _cube(0.0, 10.0, 0.0, 10.0, 0.0, 10.0)
    flipped = f[:, ::-1].copy()
    assert abs(cleanup.mesh_volume(v, flipped) - 1000.0) < 1e-6


def test_split_returns_one_shape_always():
    """Длина кортежа одна всегда, с меткой и без.

    Возврат разной длины ловится только падением на месте вызова:
    без метки шли пары, а выгрузка ждала тройки, и слой переставал
    создаваться вовсе.
    """
    v, f = _cube(0.0, 1.0, 0.0, 1.0, 0.0, 1.0)
    plain = cleanup.split_bodies(v, f)
    tagged = cleanup.split_bodies(v, f, tag=np.zeros(len(f), np.int64))
    assert len(plain[0]) == 3 and len(tagged[0]) == 3
    assert plain[0][2] is None
    assert tagged[0][2] is not None


def test_split_into_separate_bodies():
    """Куски, не связанные гранями, разделяются.

    Разбиение составной геометрии в QGIS даёт отдельные треугольники:
    связность там не считается, и тела не выходят.
    """
    v1, f1 = _cube(0.0, 10.0, 0.0, 10.0, 0.0, 10.0)
    v2, f2 = _cube(50.0, 60.0, 0.0, 10.0, 0.0, 10.0)
    v = np.vstack([v1, v2])
    f = np.vstack([f1, f2 + len(v1)])
    parts = cleanup.split_bodies(v, f)
    assert len(parts) == 2, len(parts)
    vols = sorted(cleanup.mesh_volume(pv, pf)
                  for pv, pf, _t in parts)
    assert abs(vols[0] - 1000.0) < 1e-6
    assert abs(vols[1] - 1000.0) < 1e-6


def test_split_welds_before_counting():
    """Вершины склеиваются: несклеенный меш распадётся на грани.

    Слой пишет треугольники поштучно, и без склейки каждый из них
    окажется отдельным телом.
    """
    v, f = _cube(0.0, 10.0, 0.0, 10.0, 0.0, 10.0)
    # разъединяем: у каждой грани свои вершины, как в слое
    vv = v[f.ravel()]
    ff = np.arange(len(vv), dtype=np.int64).reshape(-1, 3)
    parts = cleanup.split_bodies(vv, ff)
    assert len(parts) == 1, len(parts)


def test_degenerate_faces_are_dropped():
    """Схлопнувшиеся грани убираются до счёта.

    После склейки вершин часть треугольников вырождается в линию:
    два номера совпадают. Такая грань считает своё ребро дважды,
    и счёт рёбер врёт - на настоящем теле она выдумала двадцать пять
    защипов и спрятала дыру из трёх рёбер, показав одно.

    Площади у неё нет, объёму она не нужна, а мешает всему.
    """
    v, f = _cube(0.0, 10.0, 0.0, 10.0, 0.0, 10.0)
    bad = np.vstack([f, [[0, 0, 1], [2, 3, 3]]])
    holes, pinch = cleanup.shell_defects(v, bad)
    assert (holes, pinch) == (0, 0), (holes, pinch)
    assert abs(cleanup.mesh_volume(v, bad) - 1000.0) < 1e-6
    kept = cleanup.drop_degenerate(v, f)
    assert len(kept) == len(f)
    assert len(cleanup.drop_degenerate(v, bad)) == len(f)


def test_pinch_is_not_a_hole():
    """Защип это не дыра: объём по такому телу считается.

    Замкнутость по правилу «у каждого ребра ровно две грани» валит
    в одну кучу два разных случая. У дыры есть рёбра с одной гранью,
    и объём по ней бессмыслен. У защипа рёбра с тремя и более, дыр
    нет, и объём считается точно.
    """
    v1, f1 = _cube(0.0, 10.0, 0.0, 10.0, 0.0, 10.0)
    v2, f2 = _cube(10.0, 20.0, 10.0, 20.0, 0.0, 10.0)
    v = np.vstack([v1, v2])
    f = np.vstack([f1, f2 + len(v1)])
    holes, pinch = cleanup.shell_defects(v, f)
    assert holes == 0, holes
    assert pinch > 0, pinch


def test_defects_count_a_real_hole():
    v, f = _cube(0.0, 10.0, 0.0, 10.0, 0.0, 10.0)
    holes, pinch = cleanup.shell_defects(v, f[:-2])
    assert holes > 0
    assert pinch == 0


def test_small_hole_is_stitched():
    """Мелкая дыра зашивается веером по её краю.

    На оболочке в сорок тысяч граней остаётся пара рваных рёбер -
    вырожденная ячейка на стыке крышки с поверхностью. Искать причину
    по одному случаю дороже, чем зашить остаток.
    """
    v, f = _cube(0.0, 10.0, 0.0, 10.0, 0.0, 10.0)
    torn = f[:-1]                     # убрали одну грань
    holes, _p = cleanup.shell_defects(v, torn)
    assert holes == 3, holes
    vv, ff, n = cleanup.close_holes(v, torn)
    assert n == 1, n
    assert cleanup.shell_defects(vv, ff)[0] == 0
    assert abs(cleanup.mesh_volume(vv, ff) - 1000.0) < 1e-6


def test_stitching_starts_from_an_end():
    """Обход края начинается с конца, а не с середины.

    Попав в середину, обход уходит в одну сторону, и вторая половина
    края остаётся необойдённой: дыра не зашивается вовсе. Порядок
    вершин в словаре тут решает всё, а он произволен.
    """
    v = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [10.0, 10.0, 0.0],
                  [0.0, 10.0, 0.0], [5.0, 5.0, 8.0]], dtype=float)
    # пирамида без одной боковой грани: край это путь из трёх вершин
    f = np.array([[0, 1, 4], [1, 2, 4], [2, 3, 4],
                  [0, 1, 2], [0, 2, 3]], dtype=np.int64)
    holes, _p = cleanup.shell_defects(v, f)
    assert holes > 0, holes
    _vv, ff, n = cleanup.close_holes(v, f)
    assert n == 1, n
    assert cleanup.shell_defects(v, ff)[0] == 0
    # и то же кольцом, а не путём: обход обязан справиться с обоими
    ring = np.array([[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]],
                    dtype=np.int64)
    _v2, f2, n2 = cleanup.close_holes(v, ring)
    assert n2 == 1 and cleanup.shell_defects(v, f2)[0] == 0


def test_stitching_leaves_a_whole_mesh_alone():
    v, f = _cube(0.0, 10.0, 0.0, 10.0, 0.0, 10.0)
    vv, ff, n = cleanup.close_holes(v, f)
    assert n == 0
    assert len(ff) == len(f)


def test_stitching_spares_a_big_hole():
    """Большую дыру веером не закрыть: это уже не мелкий изъян.

    Затянув пол-оболочки плоской заплатой, получишь объём, который
    выглядит настоящим и неверен.
    """
    v, f = _cube(0.0, 10.0, 0.0, 10.0, 0.0, 10.0)
    torn = f[:4]
    # у прорехи край в четыре ребра: с порогом три её не трогаем
    assert cleanup.shell_defects(v, torn)[0] == 8
    _vv, ff, n = cleanup.close_holes(v, torn, max_edges=3)
    assert n == 0
    assert len(ff) == len(torn)


def test_open_shell_is_reported():
    """У незамкнутой оболочки объём не считается вслепую."""
    v, f = _cube(0.0, 10.0, 0.0, 10.0, 0.0, 10.0)
    assert cleanup.is_closed_mesh(v, f)
    assert not cleanup.is_closed_mesh(v, f[:-2])


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all cleanup tests passed")


if __name__ == "__main__":
    _run()
