# -*- coding: utf-8 -*-
"""Проверка плоских значков точек.

Спрайт точки в pyqtgraph нарисован кругом прямо в шейдере, и другой
формы от него не добиться. Остальные виды делаются мешем, и проверяется
здесь именно он: считается на голом NumPy, QGIS не нужен.
"""

import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
VIEWER = os.path.join(PKG, "viewer3d.py")


def _load():
    """Вырезаем функцию: импорт модуля целиком тянет QGIS."""
    src = open(VIEWER, encoding="utf-8").read()
    a = src.index("MARKER_SHAPES = (")
    b = src.index("\ndef _map_order(")
    ns = {}
    exec(compile(src[a:b], "viewer3d", "exec"), ns)  # nosec
    return ns


ROWS = [((0.0, 0.0, 5.0), "#fff", 7.0),
        ((100.0, 50.0, 7.0), "#fff", 7.0)]


def test_circle_is_not_a_mesh():
    """Круг остаётся экранным значком: меш для него не строится."""
    ns = _load()
    assert ns["flat_marker_mesh"](ROWS, "circle", 20.0) is None


def test_shapes_are_known():
    ns = _load()
    assert set(ns["MARKER_SHAPES"]) == {"circle", "square", "diamond",
                                        "triangle", "cross"}


def test_every_shape_builds():
    """У каждого вида свой меш, и все они дешёвые."""
    ns = _load()
    want = {"square": 2, "diamond": 2, "triangle": 1, "cross": 4}
    for shape, per in want.items():
        v, f = ns["flat_marker_mesh"](ROWS, shape, 20.0)
        assert len(f) == per * len(ROWS), shape
        assert f.max() < len(v), shape


def test_marker_lies_in_plan():
    """Значок плоский: вся его высота равна нулю.

    Иначе он торчал бы из поверхности и спорил с ней за глубину.
    """
    ns = _load()
    for shape in ("square", "diamond", "triangle", "cross"):
        v, _f = ns["flat_marker_mesh"](ROWS, shape, 20.0)
        first = v[:len(v) // 2]
        assert abs(first[:, 2].max() - first[:, 2].min()) < 1e-9, shape
        assert abs(first[:, 2].max() - 5.0) < 1e-9, shape


def test_size_is_the_width_in_metres():
    ns = _load()
    v, _f = ns["flat_marker_mesh"](ROWS, "square", 30.0)
    first = v[:len(v) // 2]
    assert abs((first[:, 0].max() - first[:, 0].min()) - 30.0) < 1e-9


def test_marker_is_centred_on_the_point():
    """Значок стоит вокруг точки, а не сбоку от неё."""
    ns = _load()
    v, _f = ns["flat_marker_mesh"](ROWS, "square", 20.0)
    second = v[len(v) // 2:]
    assert abs(second[:, 0].mean() - 100.0) < 1e-9
    assert abs(second[:, 1].mean() - 50.0) < 1e-9


def test_faces_do_not_cross_between_points():
    """Треугольники одной точки не цепляют вершины другой."""
    ns = _load()
    v, f = ns["flat_marker_mesh"](ROWS, "cross", 20.0)
    per = len(v) // len(ROWS)
    for tri in f:
        assert len(set(int(i) // per for i in tri)) == 1, tri


def test_empty_input_gives_nothing():
    ns = _load()
    assert ns["flat_marker_mesh"]([], "square", 20.0) is None


def test_unknown_shape_falls_back_to_the_sprite():
    """Неизвестный вид не роняет сборку, а уходит в экранный значок."""
    ns = _load()
    assert ns["flat_marker_mesh"](ROWS, "что-то", 20.0) is None


def test_colour_repeat_matches_the_vertex_count():
    """Вершин на точку поровну: цвета раскладываются повтором."""
    ns = _load()
    for shape in ("square", "diamond", "triangle", "cross"):
        v, _f = ns["flat_marker_mesh"](ROWS, shape, 20.0)
        assert len(v) % len(ROWS) == 0, shape
        per = len(v) // len(ROWS)
        cols = np.repeat(np.array([[1.0, 0, 0, 1], [0, 1.0, 0, 1]]),
                         per, axis=0)
        assert len(cols) == len(v), shape


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all marker tests passed")


if __name__ == "__main__":
    _run()
