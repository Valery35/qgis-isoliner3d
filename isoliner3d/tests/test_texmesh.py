# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Чистая часть наложения текстуры: координаты, размер, демо-карта.

Сам рендер проверить headless нельзя, для него нужны OpenGL и живое окно.
А вот арифметика, на которой чаще всего и ошибаются (переворот по оси V,
пропорции, попадание углов), проверяется обычным Python.

Запуск:  python isoliner3d/tests/test_texmesh.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(PKG))

import numpy as np                          # noqa: E402
from isoliner3d import texmesh as tm        # noqa: E402
from isoliner3d.demo_map import demo_map     # noqa: E402

CORNERS = np.array([[0.0, 0.0, 0.0], [100.0, 0.0, 0.0],
                    [0.0, 50.0, 0.0], [100.0, 50.0, 0.0]])


def test_texcoords_map_corners_to_unit_square():
    uv = tm.texcoords(CORNERS, 0.0, 100.0, 0.0, 50.0)
    assert uv.shape == (4, 2) and uv.dtype == np.float32
    assert np.allclose(uv[0], [0.0, 0.0])
    assert np.allclose(uv[1], [1.0, 0.0])
    assert np.allclose(uv[2], [0.0, 1.0])
    assert np.allclose(uv[3], [1.0, 1.0])


def test_texcoords_v_grows_northward():
    """Ось V смотрит на север: у северной вершины V больше."""
    v = np.array([[50.0, 10.0, 0.0], [50.0, 40.0, 0.0]])
    uv = tm.texcoords(v, 0.0, 100.0, 0.0, 50.0)
    assert uv[1][1] > uv[0][1]


def test_texcoords_survive_degenerate_extent():
    """Нулевой охват не должен давать деление на ноль."""
    v = np.array([[5.0, 5.0, 0.0]])
    uv = tm.texcoords(v, 5.0, 5.0, 5.0, 5.0)
    assert np.isfinite(uv).all()


def test_texture_size_keeps_aspect():
    w, h = tm.fit_texture_size(1000.0, 250.0, 2048)
    assert w == 2048 and abs(h - 512) <= 1
    w, h = tm.fit_texture_size(250.0, 1000.0, 2048)
    assert h == 2048 and abs(w - 512) <= 1


def test_texture_size_respects_cap_and_floor():
    w, h = tm.fit_texture_size(100.0, 100.0, 99999, cap=4096)
    assert w == 4096 and h == 4096
    w, h = tm.fit_texture_size(100.0, 100.0, 1)
    assert w >= 64 and h >= 64


def test_demo_map_shape_and_corners():
    img = demo_map(nx=400, ny=200, cells=8)
    assert img.shape == (200, 400, 3) and img.dtype == np.uint8
    # четыре угла помечены четырьмя разными цветами
    marks = [tuple(img[5, 5]), tuple(img[5, -5]),
             tuple(img[-5, -5]), tuple(img[-5, 5])]
    assert len(set(marks)) == 4, marks


def test_demo_map_graticule_is_square():
    """Клетки сетки одинаковы по обеим осям: перекос будет видно глазом."""
    img = demo_map(nx=400, ny=200, cells=8)
    grid = np.array([40, 40, 40], dtype=np.uint8)
    rows = [y for y in range(img.shape[0])
            if (img[y] == grid).all(axis=1).mean() > 0.9]
    cols = [x for x in range(img.shape[1])
            if (img[:, x] == grid).all(axis=1).mean() > 0.9]
    assert len(rows) >= 2 and len(cols) >= 2
    assert np.diff(rows[:3]).tolist() == np.diff(cols[:3]).tolist()


def test_demo_map_is_not_flat():
    """На карте должны быть поля, линии и метки, а не одна заливка."""
    img = demo_map(nx=256, ny=256)
    assert len(np.unique(img.reshape(-1, 3), axis=0)) >= 8


def test_polyline_dists_accumulate():
    d = tm.polyline_dists([(0, 0), (30, 40), (30, 140)])
    assert np.allclose(d, [0.0, 50.0, 150.0])


def test_polyline_dists_short_input():
    assert np.allclose(tm.polyline_dists([(1, 1)]), [0.0])
    assert tm.polyline_dists([]).size == 0


def test_ribbon_texcoords_pairs_bottom_and_top():
    uv = tm.ribbon_texcoords([0.0, 50.0, 150.0])
    assert uv.shape == (6, 2)
    assert np.allclose(uv[0::2, 1], 0.0), "чётные вершины - низ ленты"
    assert np.allclose(uv[1::2, 1], 1.0), "нечётные - верх"
    # U одинаков в паре и растёт вдоль линии
    assert np.allclose(uv[0, 0], uv[1, 0])
    assert uv[0, 0] == 0.0 and uv[-1, 0] == 1.0
    assert np.allclose(uv[2, 0], 1.0 / 3.0)


def test_ribbon_texcoords_zero_length():
    """Вырожденная линия не должна давать деления на ноль."""
    uv = tm.ribbon_texcoords([0.0, 0.0])
    assert np.isfinite(uv).all()


def section_extent(length, zmin, zmax, vex, ox, oy):
    """Охват чертежа разреза по полям определения (как во вьювере)."""
    return (ox, ox + length, zmin * vex + oy, zmax * vex + oy)


def test_section_extent_accounts_for_vex():
    """Без учёта vex чертёж растянулся бы по вертикали."""
    ext = section_extent(1000.0, -200.0, 100.0, 5.0, 0.0, 0.0)
    assert ext == (0.0, 1000.0, -1000.0, 500.0)
    plain = section_extent(1000.0, -200.0, 100.0, 1.0, 0.0, 0.0)
    assert plain[3] - plain[2] == 300.0
    assert (ext[3] - ext[2]) == 5.0 * (plain[3] - plain[2])


def test_section_extent_shifts_by_layout():
    """Смещение раскладки переносит охват, не меняя размеров."""
    a = section_extent(800.0, 0.0, 100.0, 2.0, 0.0, 0.0)
    b = section_extent(800.0, 0.0, 100.0, 2.0, 5000.0, -300.0)
    assert (b[1] - b[0]) == (a[1] - a[0])
    assert (b[3] - b[2]) == (a[3] - a[2])
    assert b[0] - a[0] == 5000.0 and b[2] - a[2] == -300.0


def test_section_texture_aspect_matches_ribbon():
    """Пропорции картинки должны совпадать с пропорциями чертежа."""
    length, zmin, zmax, vex = 1200.0, -150.0, 50.0, 4.0
    ext = section_extent(length, zmin, zmax, vex, 0.0, 0.0)
    w, h = tm.fit_texture_size(ext[1] - ext[0], ext[3] - ext[2], 2048)
    want = (ext[1] - ext[0]) / (ext[3] - ext[2])
    assert abs((w / float(h)) / want - 1.0) < 0.01, (w, h, want)


def _load_parts_xyz():
    """Достаём разбор геометрии из viewer3d, не поднимая QGIS."""
    path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "viewer3d.py")
    src = "\n".join(
        open(os.path.join(os.path.dirname(path), n),
             encoding="utf-8").read()
        for n in ("viewer3d.py", "viewer_core.py"))
    start = src.index("def _parts_xyz(")
    end = src.index("\ndef ", src.index("def _parts_xyz(") + 20)
    ns = {}
    exec(compile("import numpy as np\n" + src[start:end],   # nosec
                 "viewer3d", "exec"), ns)
    return ns["_parts_xyz"]


class _V(object):
    def __init__(self, x, y, z):
        self._x, self._y, self._z = x, y, z

    def x(self):
        return self._x

    def y(self):
        return self._y

    def z(self):
        return self._z


class _Ring(object):
    def __init__(self, pts):
        self._pts = pts

    def vertices(self):
        return [_V(*p) for p in self._pts]


class _Poly(object):
    """Полигон с внешним кольцом и дырами."""

    def __init__(self, ext, holes):
        self._ext = _Ring(ext)
        self._holes = [_Ring(h) for h in holes]

    def exteriorRing(self):
        return self._ext

    def numInteriorRings(self):
        return len(self._holes)

    def interiorRing(self, i):
        return self._holes[i]


class _Geom(object):
    def __init__(self, parts):
        self._parts = parts

    def constParts(self):
        return self._parts


EXT = [(0, 0, 10), (10, 0, 10), (10, 10, 10), (0, 10, 10), (0, 0, 10)]
HOLE = [(3, 3, 10), (6, 3, 10), (6, 6, 10), (3, 3, 10)]


def test_rings_are_not_glued():
    """Дыра не должна соединяться с внешним кольцом одной ломаной.

    Иначе через фигуру тянется прямой штрих, а на слое контуров рельефа
    таких штрихов тысячи и картинка превращается в паутину.
    """
    parts_xyz = _load_parts_xyz()
    res = parts_xyz(_Geom([_Poly(EXT, [HOLE])]))
    assert len(res) == 2, "колец должно быть два, получено %d" % len(res)
    assert [len(r) for r in res] == [5, 4]


def test_field_elevation_wins_over_geometry():
    parts_xyz = _load_parts_xyz()
    res = parts_xyz(_Geom([_Poly(EXT, [HOLE])]), zfix=125.0)
    zs = {round(p[2], 1) for ring in res for p in ring}
    assert zs == {125.0}, zs


def test_plain_line_part_still_works():
    """Линия без колец разбирается как была."""
    parts_xyz = _load_parts_xyz()
    res = parts_xyz(_Geom([_Ring([(0, 0, 1), (5, 5, 2)])]))
    assert len(res) == 1 and len(res[0]) == 2


def test_clip_pieces_add_up_to_the_whole():
    """Кусок и остаток вместе дают целое, без потерь и наложений.

    Так проверяется обрезка сцены по контуру: «оставить внутри»
    и «убрать внутри» обязаны дополнять друг друга.
    """
    from isoliner3d.mesh3d import polygon_mask
    gt = (0.0, 1.0, 0.0, 10.0, 0.0, -1.0)
    ring = [(2, 2), (8, 2), (8, 8), (2, 8), (2, 2)]
    mask = polygon_mask([ring], gt, (10, 10))
    arr = np.ones((10, 10))
    inside = arr.copy()
    inside[~mask] = np.nan
    outside = arr.copy()
    outside[mask] = np.nan
    n_in = int(np.isfinite(inside).sum())
    n_out = int(np.isfinite(outside).sum())
    assert n_in == int(mask.sum()) and n_in > 0
    assert n_in + n_out == arr.size


def test_clip_by_ring_with_hole():
    """Дырка контура остаётся дыркой: правило чёт-нечет."""
    from isoliner3d.mesh3d import polygon_mask
    gt = (0.0, 1.0, 0.0, 10.0, 0.0, -1.0)
    outer = [(1, 1), (9, 1), (9, 9), (1, 9), (1, 1)]
    hole = [(4, 4), (6, 4), (6, 6), (4, 6), (4, 4)]
    full = polygon_mask([outer], gt, (10, 10)).sum()
    holed = polygon_mask([outer, hole], gt, (10, 10)).sum()
    assert holed < full, (holed, full)


def test_line_side_and_corridor():
    """Резка по линии: стороны дополняют друг друга, коридор симметричен.

    Идея коридора из практики: смотреть не голый профиль, а полосу
    заданной ширины по обе стороны от линии.
    """
    from isoliner3d.mesh3d import polyline_dist_side
    gt = (0.0, 1.0, 0.0, 10.0, 0.0, -1.0)
    d, s = polyline_dist_side([(0, 5), (10, 5)], gt, (10, 10))
    left = int((s > 0).sum())
    right = int((s < 0).sum())
    assert left == right and left + right == d.size
    band = d <= 2.0
    assert int(band.sum()) == 40, int(band.sum())


def test_line_distance_grows_with_offset():
    from isoliner3d.mesh3d import polyline_dist_side
    gt = (0.0, 1.0, 0.0, 10.0, 0.0, -1.0)
    d, _s = polyline_dist_side([(0, 5), (10, 5)], gt, (10, 10))
    assert d[4, 0] < d[2, 0] < d[0, 0]


def test_line_bend_switches_side_locally():
    """На изломе сторона меняется у ближайшего звена, а не по всей площади."""
    from isoliner3d.mesh3d import polyline_dist_side
    gt = (0.0, 1.0, 0.0, 10.0, 0.0, -1.0)
    d, s = polyline_dist_side([(0, 2), (5, 5), (10, 2)], gt, (10, 10))
    assert set(np.unique(s)) <= {-1.0, 0.0, 1.0}
    assert (s > 0).any() and (s < 0).any()


def test_glb_structure_is_valid():
    """Файл GLB собирается по формату: заголовок, JSON, двоичный кусок.

    Формат выбран из-за читателей: GLB открывают браузерные
    просмотрщики, Blender и Windows, поэтому модель можно просто
    отправить письмом.
    """
    import json
    import struct
    from isoliner3d.gltf import build_glb
    v = np.array([[0, 0, 0], [10, 0, 0], [10, 10, 5], [0, 10, 5]], float)
    f = np.array([[0, 1, 2], [0, 2, 3]], np.int64)
    c = np.tile(np.array([0.9, 0.4, 0.1, 1.0]), (4, 1))
    data = build_glb([{"verts": v, "faces": f, "colors": c,
                       "name": "пласт"}])
    magic, ver, total = struct.unpack("<III", data[:12])
    assert magic == 0x46546C67 and ver == 2
    assert total == len(data), (total, len(data))
    assert len(data) % 4 == 0
    jl, _jt = struct.unpack("<II", data[12:20])
    js = json.loads(data[20:20 + jl])
    assert len(js["meshes"]) == 1 and len(js["nodes"]) == 1
    attrs = js["meshes"][0]["primitives"][0]["attributes"]
    assert "POSITION" in attrs and "COLOR_0" in attrs


def test_glb_axes_are_swapped_for_viewers():
    """Оси переставляются в порядок glTF, иначе модель лежит на боку."""
    import json
    import struct
    from isoliner3d.gltf import build_glb
    v = np.array([[0, 0, 0], [1, 0, 0], [0, 0, 7]], float)
    f = np.array([[0, 1, 2]], np.int64)
    data = build_glb([{"verts": v, "faces": f}])
    jl, _jt = struct.unpack("<II", data[12:20])
    js = json.loads(data[20:20 + jl])
    # высота 7 должна оказаться по оси Y, а не по Z
    assert js["accessors"][0]["max"][1] == 7.0


def test_glb_skips_empty_parts():
    from isoliner3d.gltf import build_glb
    import json
    import struct
    data = build_glb([{"verts": np.zeros((0, 3)),
                       "faces": np.zeros((0, 3), np.int64)}])
    jl, _jt = struct.unpack("<II", data[12:20])
    js = json.loads(data[20:20 + jl])
    assert js["meshes"] == [] and js["nodes"] == []


def _load_prism():
    """Призма из viewer3d вместе с разбором геометрии.

    `_prism` работает с геометрией QGIS и остался в окне, а `_flat_z`
    вынесен в viewer_core: берём первое куском исходника, второе
    импортом.
    """
    from isoliner3d import viewer_core
    path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "viewer3d.py")
    src = open(path, encoding="utf-8").read()
    ns = {"_flat_z": viewer_core._flat_z,
          "_fill_z": viewer_core._fill_z}
    for name in ("_parts_xyz", "_prism"):
        a = src.index("def %s(" % name)
        b = src.index("\ndef ", a + 20)
        exec(compile("import numpy as np\n" + src[a:b],   # nosec
                     "viewer3d", "exec"), ns)
    return ns["_prism"]


SQUARE = [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0), (0, 0, 0)]
CAP_V = np.array([[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]], float)
CAP_F = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)


def test_prism_has_two_caps_and_walls():
    """Контур с полями низа и верха превращается в объём.

    Ступень рельефа, уступ карьера и подсчётный блок описывают не плиту,
    а призму: две крышки и вертикальные стенки по кольцам.
    """
    prism = _load_prism()
    v, f = prism(_Geom([_Poly(SQUARE, [])]), CAP_V, CAP_F, 100.0, 140.0)
    assert len(f) == 2 * len(CAP_F) + 8, len(f)
    zs = sorted(set(np.round(v[:, 2], 1).tolist()))
    assert zs == [100.0, 140.0], zs


def test_prism_indices_are_valid():
    """Битые индексы дали бы мусор в сцене вместо тела."""
    prism = _load_prism()
    v, f = prism(_Geom([_Poly(SQUARE, [])]), CAP_V, CAP_F, 0.0, 5.0)
    assert f.min() >= 0 and f.max() < len(v)


def test_prism_without_cap_is_empty():
    prism = _load_prism()
    v, f = prism(_Geom([_Poly(SQUARE, [])]), CAP_V,
                 np.zeros((0, 3), dtype=np.int64), 0.0, 5.0)
    assert len(f) == 0 and len(v) == 0


def _load_flat_z():
    """Распознавание плоского объекта: вынесено в viewer_core.

    Раньше здесь вырезался кусок исходника, потому что импорт окна
    тянул QGIS. Теперь это просто импорт.
    """
    from isoliner3d import viewer_core
    return viewer_core._flat_z


def test_flat_polygon_is_recognised():
    """Плоская ступень должна распознаваться и разбиваться верно.

    Веерная разбивка верна только для простых граней полиэдра, а на
    плоском контуре рельефа даёт лучи через всю фигуру.
    """
    flat_z = _load_flat_z()
    flat = _Geom([_Poly([(0, 0, 120), (10, 0, 120), (10, 10, 120),
                         (0, 0, 120)], [])])
    assert flat_z(flat) == 120.0


def test_tilted_face_is_not_flat():
    flat_z = _load_flat_z()
    tilt = _Geom([_Poly([(0, 0, 120), (10, 0, 140), (10, 10, 160),
                         (0, 0, 120)], [])])
    assert flat_z(tilt) is None


class _FakeLayer(object):
    """Двойник слоя: только идентификатор, без QGIS."""

    def __init__(self, lid):
        self._id = lid

    def id(self):
        return self._id


def test_texture_key_is_stable_and_rounds_extent():
    a = tm.texture_key((0.0, 100.0, 0.0, 50.0), 512, 256,
                       [_FakeLayer("l1")])
    b = tm.texture_key((1e-9, 100.0, 0.0, 50.0), 512, 256,
                       [_FakeLayer("l1")])
    assert a == b, "дрожание границ в микрон не должно ломать кэш"


def test_texture_key_separates_size_and_layers():
    base = (0.0, 100.0, 0.0, 50.0)
    k1 = tm.texture_key(base, 512, 256, [_FakeLayer("l1")])
    k2 = tm.texture_key(base, 1024, 512, [_FakeLayer("l1")])
    k3 = tm.texture_key(base, 512, 256, [_FakeLayer("l2")])
    k4 = tm.texture_key(base, 512, 256, [_FakeLayer("l1"),
                                         _FakeLayer("l2")])
    assert len({k1, k2, k3, k4}) == 4


def test_texture_cache_eviction_and_clear():
    tm.texture_cache_clear()
    saved = tm._TEX_LIMIT
    try:
        tm._TEX_LIMIT = 4096
        img = np.zeros((32, 32, 4), dtype=np.uint8)     # 4 КБ
        for k in range(4):
            tm._tex_put(("k%d" % k,), img.copy())
        count, nbytes = tm.texture_cache_size()
        assert nbytes <= tm._TEX_LIMIT, (count, nbytes)
        tm.texture_cache_clear()
        assert tm.texture_cache_size() == (0, 0)
    finally:
        tm._TEX_LIMIT = saved
        tm.texture_cache_clear()


def test_glb_can_write_lines():
    """Выгрузка умеет линии, а не только треугольники.

    Координатный короб это рёбра и штрихи: треугольниками их писать
    незачем, а без них в файле нет масштаба.
    """
    import numpy as np
    from isoliner3d.gltf import build_glb
    v = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
                  [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]])
    seg = np.array([[0, 1], [2, 3]], dtype=np.uint32)
    data = build_glb([{"name": "box", "verts": v, "lines": seg}])
    assert data[:4] == b"glTF"
    assert b'"mode": 1' in data or b'"mode":1' in data


def test_glb_lines_and_faces_together():
    """Линии и треугольники живут в одном файле."""
    import numpy as np
    from isoliner3d.gltf import build_glb
    v = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    parts = [{"name": "mesh", "verts": v,
              "faces": np.array([[0, 1, 2]], dtype=np.uint32)},
             {"name": "box", "verts": v,
              "lines": np.array([[0, 1]], dtype=np.uint32)}]
    data = build_glb(parts)
    assert data[:4] == b"glTF"
    assert data.count(b'"primitives"') == 2


def test_export_keeps_the_ramp_colours():
    """В выгрузку идёт та же раскраска, что и на экране.

    Ровный цвет слоя вместо шкалы делает файл нечитаемым: все
    поверхности выходят одинаковыми пятнами, и по ним ничего
    не разобрать.
    """
    src = open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "viewer_dialog.py"), encoding="utf-8").read()
    i = src.index("ramp_c = self._style_ramp.get(lid)")
    seg = src[i:i + 2200]
    assert seg.count("exp_col = vc") == 2, seg.count("exp_col = vc")
    assert "exp_col = None" in seg
    assert "out_col[:, 3] = 1.0" in seg
    # ровный цвет остаётся только там, где шкалы нет
    assert seg.index("exp_col = None") < seg.index("np.tile(")


def test_exported_box_carries_labels():
    """Подписи делений уходят в файл отрезками.

    В GLB текста не бывает: либо геометрия букв, либо картинка
    на плоскости. Картинка при повороте встаёт ребром и пропадает,
    а отрезки поворачиваются вместе с коробом.
    """
    src = open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "viewer_dialog.py"), encoding="utf-8").read()
    start = src.index("def _export_box")
    body = src[start:src.index("\n    def ", start + 20)]
    assert "from .glyphs import label_3d" in body
    assert "tick_label(val)" in body
    assert 'label_size(lo, hi, axis)' in body
    assert 'plane = "xz"' in body and 'plane = "xy"' in body
    # подписи полосками: толщину линий в glTF задать нельзя
    assert "ribbon(segs, gsz * 0.14, plane=plane)" in body
    assert '"faces": np.vstack(lab_f)' in body


def test_labels_add_real_geometry():
    """Подписи и правда добавляют отрезки, а не пустое место."""
    import numpy as np
    from isoliner3d.axes import box_edges, tick_marks, tick_label
    from isoliner3d.glyphs import label_3d
    lo, hi = (0.0, 0.0, -200.0), (1000.0, 800.0, 0.0)
    marks = tick_marks(lo, hi, want=5)
    base = len(box_edges(lo, hi)) + len(marks)
    span = max(hi[k] - lo[k] for k in range(3))
    from isoliner3d.glyphs import label_size
    extra = 0
    for axis, val, _a, b in marks:
        extra += len(label_3d(tick_label(val), b,
                              label_size(lo, hi, axis),
                              plane="xy" if axis in (0, 1) else "xz"))
    assert extra > base, (extra, base)
    assert np.isfinite(np.array(
        [q for seg in label_3d("-100", (0, 0, 0), 5.0)
         for q in seg])).all()


def test_box_goes_to_export_even_when_hidden():
    """Короб уходит в файл и когда его не показывают.

    В файле без него нет масштаба, а на экране он мешает: это разные
    решения, и связывать их одной кнопкой неверно.
    """
    src = open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "viewer_dialog.py"), encoding="utf-8").read()
    i = src.index("if self.btn_axes.isChecked():")
    seg = src[i:i + 500]
    assert "else:" in seg
    assert "self._export_box(box_lo, box_hi, None)" in seg


def test_no_numpy_array_in_boolean_context():
    """Массив numpy не проверяется на истинность.

    `arr or ()` бросает исключение: у массива из многих чисел нет
    однозначной истинности. В отчёте о выгрузке это роняло запись
    файла целиком, и три версии подряд файл не писался вовсе.
    """
    import re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bad = []
    for name in ("viewer_dialog.py", "viewer_core.py", "viewer3d.py",
                 "gltf.py", "cleanup.py", "axes.py", "slice3d.py",
                 "volume.py", "flatten.py", "kriging.py"):
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            for n, ln in enumerate(fh, 1):
                # ищем «что-то из get(...) or» и «faces or»
                if re.search(r'\.get\("(faces|lines|verts|colors)"[^)]*\)'
                             r'\s+or\s', ln):
                    bad.append("%s:%d" % (name, n))
    assert not bad, "массив в булевом виде: %s" % ", ".join(bad)


def test_export_log_survives_a_part_without_faces():
    """Отчёт о выгрузке не падает на части без граней.

    У короба только линии, и обращение к «faces» роняло всю выгрузку
    целиком: файл не писался вовсе.
    """
    src = open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "viewer_dialog.py"), encoding="utf-8").read()
    i = src.index('Часть %s: вершин')
    seg = src[i - 400:i + 300]
    assert 'part["faces"]' not in seg, seg
    assert 'part.get("faces"' in seg
    assert 'part.get("lines"' in seg


def test_box_goes_to_the_export_as_lines():
    """Короб уходит в выгрузку линиями, без подписей.

    В GLB текст это геометрия букв, и делать её ради чисел незачем.
    Рёбра, сетка и штрихи масштаб дают и без подписей.
    """
    src = open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "viewer_dialog.py"), encoding="utf-8").read()
    assert "def _export_box" in src
    start = src.index("def _export_box")
    body = src[start:src.index("\n    def ", start + 20)]
    assert '"lines": idx' in body
    assert "box_edges(lo, hi)" in body and "tick_marks(lo, hi" in body
    assert "grid_lines(lo, hi" in body
    # середина для преувеличения считается по телам, а не по коробу
    i = src.index("zs_all = [")
    assert '"faces" in pt' in src[i:i + 260]


def test_export_vex_uses_one_centre():
    """Преувеличение в выгрузке считается от общей середины.

    Масштабируя каждую часть вокруг своей середины, растянешь только
    рельеф внутри неё, а расстояния между частями останутся прежними.
    На глаз кажется, что преувеличение не применилось вовсе.
    """
    import re
    src = open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "viewer_dialog.py"), encoding="utf-8").read()
    i = src.index("if keep_vex:")
    seg = src[i:i + 700]
    assert "zc_all" in seg, seg[:400]
    # середина берётся один раз, до обхода частей
    assert seg.index("zc_all") < seg.index("for part in self._export")


def test_export_vex_scales_the_gap():
    """Разнос между частями растёт вместе с рельефом."""
    import numpy as np
    p1 = np.array([[0.0, 0.0, -100.0], [1.0, 0.0, -98.0],
                   [0.0, 1.0, -102.0]])
    p2 = np.array([[0.0, 0.0, -50.0], [1.0, 0.0, -49.0],
                   [0.0, 1.0, -51.0]])
    vex = 10.0
    zc = float(np.mean(np.concatenate([p1[:, 2], p2[:, 2]])))
    out = []
    for v in (p1, p2):
        w = v.copy()
        w[:, 2] = (w[:, 2] - zc) * vex + zc
        out.append(w)
    gap = float(np.mean(out[1][:, 2]) - np.mean(out[0][:, 2]))
    assert abs(gap - 500.0) < 1e-6, gap


if __name__ == "__main__":
    ok = 0
    for nm, fn in sorted(globals().items()):
        if nm.startswith("test_") and callable(fn):
            fn()
            print("OK", nm)
            ok += 1
    print("all texmesh tests passed (%d)" % ok)
