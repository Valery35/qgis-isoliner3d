# -*- coding: utf-8 -*-
"""Проверка воксельной модели: отбрасывание граней и слияние.

Считается на голом NumPy, QGIS не нужен. Проверяется то, ради чего
модель и строится: невидимых граней в выводе нет, оболочка замкнута,
грани смотрят наружу, а слияние не путает классы.
"""

import os
import sys

import numpy as np

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import voxel   # noqa: E402
from isoliner3d.iso3d import is_watertight   # noqa: E402

GT = (0.0, 10.0, 0.0, 100.0, 0.0, -10.0)


def _cube(n=4):
    return np.ones((n, n, n), dtype=bool)


def test_solid_cube_keeps_only_the_outer_shell():
    """У сплошного куба остаются только наружные грани."""
    occ = _cube(4)
    assert voxel.visible_faces(occ) == 6 * 4 * 4


def test_single_cell_has_six_faces():
    occ = np.zeros((3, 3, 3), dtype=bool)
    occ[1, 1, 1] = True
    assert voxel.visible_faces(occ) == 6
    verts, tris, _cls, over = voxel.voxel_mesh(occ, GT, 0.0, 5.0)
    assert not over
    assert tris.shape[0] == 12
    assert verts.shape[0] == 24


def test_solid_cube_merges_into_six_quads():
    """Слияние сводит грань сплошного куба к одному прямоугольнику."""
    verts, tris, _cls, _over = voxel.voxel_mesh(_cube(5), GT, 0.0, 5.0)
    assert tris.shape[0] == 12, tris.shape
    assert verts.shape[0] == 24


def _stepped():
    """Тело со ступенькой: на таком слияние даёт Т-образные стыки."""
    occ = np.zeros((4, 6, 6), dtype=bool)
    occ[0:4, 1:5, 1:5] = True
    occ[3, 2:4, 2:4] = False
    return occ


def test_unmerged_mesh_is_watertight():
    """Без слияния каждое ребро принадлежит ровно двум граням.

    Это и есть форма, годная для подсчёта объёма и выгрузки телом.
    """
    verts, tris, _cls, _over = voxel.voxel_mesh(_stepped(), GT, 0.0, 5.0,
                                                merge=False)
    assert is_watertight(verts, tris)


def test_merging_costs_watertightness():
    """Слияние ломает замкнутость и сильно облегчает сцену.

    Проверка закрепляет размен, а не дефект: длинный прямоугольник
    упирается в два коротких, общего ребра у них нет.
    """
    occ = _stepped()
    v_m, t_m, _c, _o = voxel.voxel_mesh(occ, GT, 0.0, 5.0)
    _v_u, t_u, _c2, _o2 = voxel.voxel_mesh(occ, GT, 0.0, 5.0, merge=False)
    assert t_m.shape[0] < t_u.shape[0]
    assert not is_watertight(v_m, t_m)


def test_merged_box_stays_watertight():
    """У сплошной коробки стыков не возникает и слияние безопасно."""
    occ = np.zeros((5, 5, 5), dtype=bool)
    occ[1:4, 1:4, 1:4] = True
    verts, tris, _cls, _over = voxel.voxel_mesh(occ, GT, 0.0, 5.0)
    assert is_watertight(verts, tris)


def test_faces_point_outward():
    """Нормали смотрят наружу: иначе коробка выглядит вывернутой."""
    occ = np.zeros((5, 5, 5), dtype=bool)
    occ[1:4, 1:4, 1:4] = True
    verts, tris, _cls, _over = voxel.voxel_mesh(occ, GT, 0.0, 5.0)
    centre = verts.reshape(-1, 3).mean(axis=0)
    a, b, c = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    nrm = np.cross(b - a, c - a)
    mid = (a + b + c) / 3.0
    dot = np.einsum("ij,ij->i", nrm, mid - centre)
    assert (dot > 0).all(), int((dot <= 0).sum())


def test_cell_size_follows_the_grid():
    """Ячейка занимает шаг грида по горизонтали и шаг уровней по Z."""
    occ = np.zeros((3, 3, 3), dtype=bool)
    occ[1, 1, 1] = True
    verts, _t, _c, _o = voxel.voxel_mesh(occ, GT, 500.0, 4.0)
    span = verts.max(axis=0) - verts.min(axis=0)
    assert abs(span[0] - 10.0) < 1e-6, span
    assert abs(span[1] - 10.0) < 1e-6, span
    assert abs(span[2] - 4.0) < 1e-6, span
    zmid = (verts[:, 2].min() + verts[:, 2].max()) / 2.0
    assert abs(zmid - (500.0 + 4.0)) < 1e-6, zmid


def test_classes_are_not_merged_together():
    """Грани разных классов не сливаются в один прямоугольник."""
    occ = np.ones((1, 1, 4), dtype=bool)
    cls = np.array([[[0, 0, 1, 1]]], dtype=np.int32)
    _v, tris_one, _c, _o = voxel.voxel_mesh(occ, GT, 0.0, 5.0)
    _v2, tris_two, cls2, _o2 = voxel.voxel_mesh(occ, GT, 0.0, 5.0,
                                                classes=cls)
    assert tris_two.shape[0] > tris_one.shape[0]
    assert set(np.unique(cls2).tolist()) == {0, 1}


def test_class_survives_on_every_face():
    occ = np.ones((2, 2, 2), dtype=bool)
    cls = np.zeros((2, 2, 2), dtype=np.int32)
    cls[1] = 3
    _v, _t, tri_cls, _o = voxel.voxel_mesh(occ, GT, 0.0, 5.0, classes=cls)
    assert set(np.unique(tri_cls).tolist()) == {0, 3}


def test_missing_values_are_not_occupied():
    """Пропуск телом не считается."""
    vol = np.array([[[1.0, np.nan], [5.0, 0.0]]])
    occ = voxel.occupancy(vol, 0.5)
    assert occ.tolist() == [[[True, False], [True, False]]]


def test_below_cutoff_mode():
    vol = np.array([[[1.0, 9.0]]])
    assert voxel.occupancy(vol, 5.0, below=True).tolist() == [[[True, False]]]


def test_quantize_buckets_and_keeps_gaps():
    cls = voxel.quantize(np.array([0.0, 1.5, 4.0, np.nan]), [1.0, 3.0])
    assert cls.tolist() == [0, 1, 2, -1]


def test_greedy_merges_a_rectangle():
    key = np.zeros((3, 4), dtype=np.int32)
    rects = voxel.greedy_rects(key)
    assert rects == [(0, 2, 0, 3, 0)], rects


def test_greedy_keeps_holes_apart():
    key = np.zeros((3, 3), dtype=np.int32)
    key[1, 1] = -1
    rects = voxel.greedy_rects(key)
    covered = sum((r1 - r0 + 1) * (c1 - c0 + 1)
                  for r0, r1, c0, c1, _c in rects)
    assert covered == 8, rects


def test_greedy_does_not_overlap():
    rng = np.random.RandomState(0)
    key = rng.randint(-1, 3, (12, 15)).astype(np.int32)
    seen = np.zeros(key.shape, dtype=int)
    for r0, r1, c0, c1, cls in voxel.greedy_rects(key):
        assert (key[r0:r1 + 1, c0:c1 + 1] == cls).all()
        seen[r0:r1 + 1, c0:c1 + 1] += 1
    assert (seen[key >= 0] == 1).all()
    assert (seen[key < 0] == 0).all()


def _pinched():
    """Две ячейки, соприкасающиеся одной диагональю."""
    occ = np.zeros((1, 3, 3), dtype=bool)
    occ[0, 0, 0] = True
    occ[0, 1, 1] = True
    return occ


def test_pinch_is_counted():
    """Касание диагональю находится и считается."""
    assert voxel.pinch_edges(_pinched()) == 1
    assert voxel.pinch_edges(np.ones((2, 2, 2), dtype=bool)) == 0


def test_pinch_breaks_watertightness():
    """В защипе ребро принадлежит четырём граням, а не двум.

    Дырой это не является, но проверка замкнутости такое тело
    отвергает, поэтому защип надо находить, а не списывать
    на погрешность.
    """
    verts, tris, _c, _o = voxel.voxel_mesh(_pinched(), GT, 0.0, 5.0,
                                           merge=False)
    assert not is_watertight(verts, tris)


def test_unpinch_closes_the_body():
    """После заполнения угла оболочка замыкается."""
    fixed, added = voxel.unpinch(_pinched())
    assert added > 0
    assert voxel.pinch_edges(fixed) == 0
    verts, tris, _c, _o = voxel.voxel_mesh(fixed, GT, 0.0, 5.0,
                                           merge=False)
    assert is_watertight(verts, tris)


def test_unpinch_only_adds_cells():
    """Заполнение углов ничего не убирает: тело не худеет."""
    occ = _pinched()
    fixed, _added = voxel.unpinch(occ)
    assert (fixed | occ == fixed).all()
    assert fixed.sum() > occ.sum()


def test_unpinch_leaves_clean_bodies_alone():
    occ = np.zeros((4, 4, 4), dtype=bool)
    occ[1:3, 1:3, 1:3] = True
    fixed, added = voxel.unpinch(occ)
    assert added == 0
    assert (fixed == occ).all()


def test_empty_input_gives_empty_mesh():
    occ = np.zeros((3, 3, 3), dtype=bool)
    verts, tris, cls, over = voxel.voxel_mesh(occ, GT, 0.0, 1.0)
    assert verts.shape == (0, 3) and tris.shape == (0, 3)
    assert cls.size == 0 and not over


def test_overflow_is_reported():
    """Слишком большая модель прекращает работу с признаком."""
    rng = np.random.RandomState(1)
    occ = rng.random((30, 30, 30)) > 0.5
    _v, tris, _c, over = voxel.voxel_mesh(occ, GT, 0.0, 1.0, max_quads=50)
    assert over and tris.shape[0] == 0


def test_culling_beats_the_naive_count():
    """Отбрасывание невидимых граней даёт выигрыш в разы."""
    occ = np.zeros((40, 40, 40), dtype=bool)
    occ[5:35, 5:35, 5:35] = True
    naive = int(occ.sum()) * 6
    assert voxel.visible_faces(occ) * 20 < naive


def test_unmerged_body_is_watertight_after_welding():
    """Тело без слияния замкнуто, если склеить вершины.

    Меш выходит несклеенным: у каждого треугольника свои вершины,
    и по номерам каждое ребро выглядит краевым. Замкнутость есть,
    но увидеть её можно только после склейки.
    """
    import collections
    from isoliner3d.iso3d import weld
    occ = np.zeros((4, 5, 6), dtype=bool)
    occ[1:3, 1:4, 1:5] = True
    gt = (0.0, 10.0, 0.0, 50.0, 0.0, -10.0)
    v, f, _c, _o = voxel.voxel_mesh(occ, gt, 0.0, 5.0, merge=False)

    def border(vv, ff):
        e = collections.Counter()
        for tri in ff:
            for a, b in ((tri[0], tri[1]), (tri[1], tri[2]),
                         (tri[2], tri[0])):
                e[(a, b) if a < b else (b, a)] += 1
        return sum(1 for n in e.values() if n == 1)

    # несклеенный меш: краевых рёбер много, замкнутости не видно
    assert border(v, f) > len(f), border(v, f)
    vw, fw = weld(v, f)
    assert border(vw, fw) == 0, border(vw, fw)
    assert len(vw) < len(v) / 2


def test_merged_body_keeps_t_junctions():
    """Со слиянием даже склейка не закрывает всё: остаются стыки.

    Длинный прямоугольник упирается в два коротких, общего ребра
    у них нет. Это и есть та плата за лёгкость, что заложена в 2.04.
    """
    import collections
    from isoliner3d.iso3d import weld
    rs = np.random.RandomState(0)
    occ = rs.rand(6, 8, 9) > 0.45
    gt = (0.0, 10.0, 0.0, 80.0, 0.0, -10.0)
    v, f, _c, _o = voxel.voxel_mesh(occ, gt, 0.0, 5.0, merge=True)
    vw, fw = weld(v, f)
    e = collections.Counter()
    for tri in fw:
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]),
                     (tri[2], tri[0])):
            e[(a, b) if a < b else (b, a)] += 1
    assert sum(1 for n in e.values() if n == 1) > 0


def _loops(v, f):
    """Краевые рёбра и число узлов, где кольцо рвётся."""
    import collections
    e = collections.Counter()
    for tri in f:
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]),
                     (tri[2], tri[0])):
            e[(a, b) if a < b else (b, a)] += 1
    border = [k for k, n in e.items() if n == 1]
    d = collections.Counter()
    for a, b in border:
        d[a] += 1
        d[b] += 1
    return len(border), sum(1 for x in d.values() if x != 2)


def _rough_body(merge):
    """Изрезанное тело, похожее на настоящее, а не кубик."""
    from isoliner3d.iso3d import weld
    rs = np.random.RandomState(4)
    occ = rs.rand(8, 14, 16) > 0.4
    gt = (0.0, 10.0, 0.0, 140.0, 0.0, -10.0)
    v, f, _c, _o = voxel.voxel_mesh(occ, gt, 0.0, 5.0, merge=merge)
    return weld(v, f)


def test_unmerged_body_is_closed_before_the_cut():
    """Тело без слияния замкнуто: ни одного краевого ребра.

    Это и есть условие, при котором крышку на срезе вообще можно
    построить.
    """
    v, f = _rough_body(False)
    assert _loops(v, f) == (0, 0)


def test_merged_border_is_broken_much_worse():
    """Слияние рвёт границу на порядок сильнее самой резки.

    У тела без слияния рвутся только углы, где ячейки касаются
    ребром. У слитого граница разорвана всюду и до всякой резки.
    """
    v0, f0 = _rough_body(False)
    v1, f1 = _rough_body(True)
    keep0 = v0[:, 0] < 70.0
    cut0 = f0[keep0[f0].sum(axis=1) == 3]
    _b0, broken_cut = _loops(v0, cut0)
    _b1, broken_merge = _loops(v1, f1)
    assert broken_merge > 5 * broken_cut, (broken_merge, broken_cut)


def test_merged_body_cannot_be_capped():
    """У слитого тела граница разорвана ещё до всякой резки.

    Значит крышку на срезе не построить никаким алгоритмом: чинить
    надо выше, при сборке тела. Проверка закрепляет это как свойство
    геометрии, чтобы его не искали как ошибку в резчике.
    """
    v, f = _rough_body(True)
    border, broken = _loops(v, f)
    assert border > 0, border
    assert broken > 0, broken


def test_each_class_body_is_closed_on_its_own():
    """Тело каждого интервала замкнуто само по себе.

    Инструмент 2.04 пишет объект на интервал окраски. Если грань
    между двумя занятыми ячейками отбрасывать независимо от их
    интервала, на стыке интервалов её нет ни у одного куска: каждое
    тело выходит дырявым, и срез в сцене нечем закрыть.
    """
    import collections
    from isoliner3d.iso3d import weld
    rs = np.random.RandomState(3)
    vol = rs.rand(6, 10, 12) * 10.0
    occ = voxel.occupancy(vol, 3.0)
    cls = voxel.quantize(vol, np.linspace(3.0, 10.0, 5))
    gt = (0.0, 10.0, 0.0, 100.0, 0.0, -10.0)
    v, f, tri_cls, _o = voxel.voxel_mesh(occ, gt, 0.0, 5.0,
                                         classes=cls, merge=False)

    def border(vv, ff):
        e = collections.Counter()
        for tri in ff:
            for a, b in ((tri[0], tri[1]), (tri[1], tri[2]),
                         (tri[2], tri[0])):
                e[(a, b) if a < b else (b, a)] += 1
        return sum(1 for n in e.values() if n == 1)

    tri_cls = np.asarray(tri_cls)
    for c in sorted(set(tri_cls.tolist())):
        vc, fc = weld(v, f[tri_cls == c])
        assert border(vc, fc) == 0, (c, border(vc, fc))


def test_class_interface_gets_two_faces():
    """На стыке двух интервалов грань есть у обоих, а не ни у кого.

    Иначе оба тела дырявые, а вместе они выглядят целыми - беда
    вылезает только при разрезе.
    """
    occ = np.ones((1, 1, 2), dtype=bool)
    cls = np.array([[[1, 2]]])
    gt = (0.0, 10.0, 0.0, 10.0, 0.0, -10.0)
    _v, f, tri_cls, _o = voxel.voxel_mesh(occ, gt, 0.0, 5.0,
                                          classes=cls, merge=False)
    tri_cls = np.asarray(tri_cls)
    # у куба две ячейки: по 6 граней у каждой, стык считается дважды
    assert len(f) == 24, len(f)
    assert (tri_cls == 1).sum() == 12
    assert (tri_cls == 2).sum() == 12


def test_edges_are_parsed_from_text():
    """Границы интервалов читаются строкой, как их пишет человек."""
    assert voxel.parse_edges("0,5,10,15") == [0.0, 5.0, 10.0, 15.0]
    assert voxel.parse_edges(" 0 ; 5 ; 10 ") == [0.0, 5.0, 10.0]
    assert voxel.parse_edges("0 5 10") == [0.0, 5.0, 10.0]


def test_edges_are_sorted_and_deduped():
    """Границы вразнобой и с повторами приводятся к порядку."""
    assert voxel.parse_edges("10,0,5,5") == [0.0, 5.0, 10.0]


def test_bad_edges_are_refused():
    """Мусор и одна граница не годятся: интервала из них не выйдет."""
    assert voxel.parse_edges("") is None
    assert voxel.parse_edges("5") is None
    assert voxel.parse_edges("abc, def") is None


def test_labels_follow_the_intervals():
    """Названий столько же, сколько интервалов, лишние отброшены."""
    got = voxel.parse_labels("низкое, среднее, высокое", 3)
    assert got == ["низкое", "среднее", "высокое"]
    assert voxel.parse_labels("низкое", 3)[1:] == ["", ""]
    assert voxel.parse_labels("a,b,c,d", 2) == ["a", "b"]
    assert voxel.parse_labels("", 2) == ["", ""]


def test_quantize_by_own_edges():
    """Ячейка попадает в свой интервал по заданным границам."""
    vol = np.array([[[-1.0, 0.0, 4.9, 5.0, 9.9, 20.0]]])
    cls = voxel.quantize(vol, np.array([0.0, 5.0, 10.0]))
    assert cls[0, 0, 1] == 1 and cls[0, 0, 2] == 1
    assert cls[0, 0, 3] == 2 and cls[0, 0, 4] == 2
    # ниже первой границы нулевой класс, выше последней последний:
    # ячейка выше верхней границы всё равно в теле, и терять её нельзя
    assert cls[0, 0, 0] == 0
    assert cls[0, 0, 5] == 3


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all voxel tests passed")


if __name__ == "__main__":
    _run()
