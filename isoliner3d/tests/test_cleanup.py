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


def _fine_slab(nx=80, ny=80, thick=16.0, side=600.0):
    """Плита из многих граней: как настоящая оболочка пласта."""
    xs = np.linspace(0.0, side, nx)
    ys = np.linspace(0.0, side, ny)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    top = np.column_stack([X.ravel(), Y.ravel(),
                           np.full(X.size, thick)])
    bot = np.column_stack([X.ravel(), Y.ravel(), np.zeros(X.size)])
    v = np.vstack([top, bot])
    n = X.size
    f = []
    for i in range(nx - 1):
        for j in range(ny - 1):
            a = i * ny + j
            b, c, d = a + 1, a + ny, a + ny + 1
            f += [[a, b, d], [a, d, c]]                 # кровля
            f += [[n + a, n + d, n + b], [n + a, n + c, n + d]]
    # борта по краю, чтобы тело было замкнутым
    for i in range(nx - 1):
        for a, b in ((i * ny, (i + 1) * ny),
                     (i * ny + ny - 1, (i + 1) * ny + ny - 1)):
            f += [[a, b, n + b], [a, n + b, n + a]]
    for j in range(ny - 1):
        for a, b in ((j, j + 1), ((nx - 1) * ny + j,
                                  (nx - 1) * ny + j + 1)):
            f += [[a, b, n + b], [a, n + b, n + a]]
    return v, np.array(f, dtype=np.int64)


def test_volume_survives_far_coordinates():
    """Объём верен и в настоящих координатах, за тысячи километров.

    Формула складывает объёмы тетраэдров от начала координат. При
    координатах в шесть миллионов метров каждое слагаемое выходит
    порядка десяти в четырнадцатой, а сумма должна дать миллион:
    значащие цифры съедаются взаимным вычитанием. На настоящем теле
    из девяноста трёх тысяч граней так вышло восемь миллиардов
    кубометров - в тысячу триста раз больше собственного габарита.
    """
    v, f = _fine_slab()
    truth = 600.0 * 600.0 * 16.0
    near = cleanup.mesh_volume(v, f)
    assert abs(near - truth) / truth < 1e-6, near
    far = v + np.array([496000.0, 6209000.0, 130.0])
    got = cleanup.mesh_volume(far, f)
    assert abs(got - truth) / truth < 1e-6, (got, truth)


def test_volume_is_centred_before_summing():
    """Середина тела вычитается до счёта, а не после."""
    src = open(os.path.join(PKG, "cleanup.py"),
               encoding="utf-8").read()
    i = src.index("def mesh_volume")
    body = src[i:src.index("\ndef ", i + 20)]
    assert "v = v - v.mean(axis=0)" in body
    assert body.index("v.mean(axis=0)") < body.index("np.cross(")


def test_volume_cannot_exceed_its_own_box():
    """Объём не бывает больше габарита тела: это верный признак сбоя."""
    v, f = _cube(0.0, 10.0, 0.0, 20.0, 0.0, 5.0)
    far = v + np.array([496000.0, 6209000.0, 130.0])
    box = np.prod(far.max(axis=0) - far.min(axis=0))
    assert cleanup.mesh_volume(far, f) <= box + 1e-6


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


def test_volume_beyond_box_is_caught():
    """Объём больше собственного габарита - верный признак сбоя счёта.

    Слои, выгруженные до 0.74.1, несут такие числа: на присланном слое
    из 93 тел у 37 объём оказался больше габарита, у худшего
    в пятьдесят тысяч раз.
    """
    import numpy as np
    from isoliner3d.viewer_core import volume_beyond_box
    v = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [10.0, 5.0, 0.0],
                  [0.0, 5.0, 2.0]])
    assert volume_beyond_box(7.97e9, v)
    assert not volume_beyond_box(50.0, v)


def test_volume_check_keeps_quiet_on_junk():
    """Пустое поле, текст и ноль - не повод кричать."""
    import numpy as np
    from isoliner3d.viewer_core import volume_beyond_box
    v = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]])
    assert not volume_beyond_box(None, v)
    assert not volume_beyond_box("нет", v)
    assert not volume_beyond_box(0.0, v)
    assert not volume_beyond_box(float("nan"), v)
    assert not volume_beyond_box(1e9, np.zeros((0, 3)))


if __name__ == "__main__":
    _run()
