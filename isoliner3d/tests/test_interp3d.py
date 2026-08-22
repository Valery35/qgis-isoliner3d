# -*- coding: utf-8 -*-
"""Проверка модели содержаний для демонстрационных данных.

Считается на голом Python: QGIS для этого не нужен, а сама модель
должна вести себя предсказуемо, иначе на ней нельзя сравнивать методы
интерполяции.
"""

import os
import sys

import numpy as np

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))


from isoliner3d import interp3d   # noqa: E402
from isoliner3d.interp3d import grid_nodes   # noqa: E402
from isoliner3d.demo3d import demo_grade   # noqa: E402


def _load_grade():
    """Модель содержаний живёт в demo3d, QGIS для неё не нужен."""
    return demo_grade


def test_core_is_richest():
    """Середина линзы богаче краёв: иначе проверять нечего."""
    grade = _load_grade()
    core = grade(500, 500, -100)
    assert core > grade(800, 500, -100)
    assert core > grade(500, 500, -60)
    assert core > grade(0, 0, 0)


def test_lens_is_flatter_than_tall():
    """Линза шире, чем толще.

    Это и делает данные пригодными для проверки анизотропии: без неё
    ближайшей точкой окажется соседняя скважина, а не соседний замер.
    """
    grade = _load_grade()
    side = grade(500 + 200, 500, -100)      # 200 м по горизонтали
    up = grade(500, 500, -100 + 20)         # 20 м по вертикали
    assert side > up, (side, up)


def test_trend_exists():
    """Есть общий наклон содержаний, а не только линза."""
    grade = _load_grade()
    assert grade(1000, 1000, 0) - grade(0, 0, 0) > 0.5


def test_values_are_finite_everywhere():
    grade = _load_grade()
    for x in (0, 250, 500, 750, 1000):
        for z in (0, -50, -100, -150, -200):
            v = grade(x, x, z)
            assert v == v and abs(v) < 1e6


def test_linear_field_is_reproduced():
    """На линейном поле оба метода дают близкое к истине значение."""
    import numpy as np
    from isoliner3d.interp3d import interpolate
    rng = np.random.RandomState(0)
    pts = rng.uniform(0, 100, (400, 3))
    pts[:, 2] = rng.uniform(-50, 0, 400)
    val = 2.0 * pts[:, 0] + 3.0 * pts[:, 1] - pts[:, 2]
    node = np.array([[50.0, 50.0, -25.0]])
    truth = 2 * 50 + 3 * 50 + 25
    for method in ("nearest", "idw"):
        got = interpolate(pts, val, node, method=method, radius=60,
                          max_points=12)[0]
        assert abs(got - truth) / truth < 0.1, (method, got, truth)


def test_point_itself_is_exact():
    """В самой точке значение совпадает: иначе метод не интерполирует."""
    import numpy as np
    from isoliner3d.interp3d import interpolate
    rng = np.random.RandomState(1)
    pts = rng.uniform(0, 50, (60, 3))
    val = rng.uniform(0, 10, 60)
    got = interpolate(pts, val, pts[:1], method="idw", radius=40)[0]
    assert abs(got - val[0]) < 1e-9


def test_far_node_stays_empty():
    """Там, где точек в радиусе нет, остаётся пропуск."""
    import numpy as np
    from isoliner3d.interp3d import interpolate
    pts = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 0.0]])
    val = np.array([1.0, 2.0])
    got = interpolate(pts, val, np.array([[1000.0, 1000.0, 0.0]]),
                      method="idw", radius=10)
    assert not np.isfinite(got[0])


def test_anisotropy_changes_the_neighbour():
    """Анизотропия меняет, кто ближе: замер в скважине или соседняя.

    Замер на 10 м выше в той же точке плана должен побеждать точку
    в 100 м по горизонтали, если вертикаль сжата.
    """
    import numpy as np
    from isoliner3d.interp3d import interpolate
    pts = np.array([[0.0, 0.0, -10.0],      # тот же ствол, ниже
                    [100.0, 0.0, 0.0]])     # соседняя скважина
    val = np.array([1.0, 2.0])
    node = np.array([[0.0, 0.0, 0.0]])
    same = interpolate(pts, val, node, method="nearest", radius=500,
                       anisotropy=20.0)[0]
    other = interpolate(pts, val, node, method="nearest", radius=500,
                        anisotropy=0.05)[0]
    assert same == 1.0 and other == 2.0, (same, other)


def test_grid_nodes_are_ordered_by_level():
    """Узлы идут уровнями: так же лежат каналы куба."""
    import numpy as np
    from isoliner3d.interp3d import grid_nodes
    nodes = grid_nodes(0.0, 100.0, -50.0, 4, 4, 3, 25.0, 25.0, 10.0)
    assert len(nodes) == 48
    level = nodes[:16, 2]
    assert np.allclose(level, -50.0)
    assert np.allclose(nodes[16:32, 2], -40.0)


def test_cross_validation_reports_error():
    """Проверка с исключением по одной считает ошибку."""
    import numpy as np
    from isoliner3d.interp3d import cross_validate
    rng = np.random.RandomState(2)
    pts = rng.uniform(0, 100, (40, 3))
    val = 2.0 * pts[:, 0] + pts[:, 1]
    _res, mae, rmse = cross_validate(pts, val, method="idw", radius=80,
                                     max_points=8)
    assert mae == mae and rmse >= mae


def test_dense_path_matches_the_cell_index():
    """Блочный расчёт совпадает с поштучным.

    Быстрый путь включается сам при небольшом числе точек, и разойтись
    с медленным он не имеет права: это одна и та же задача.
    """
    rng = np.random.RandomState(4)
    pts = rng.uniform(0, 500, (400, 3))
    vals = rng.uniform(0, 10, 400)
    nodes = grid_nodes(0.0, 500.0, 0.0, 8, 8, 6, 60.0, 60.0, 40.0)
    for method in ("idw", "nearest"):
        keep = interp3d._DENSE_LIMIT
        try:
            interp3d._DENSE_LIMIT = 0
            slow = interp3d.interpolate(pts, vals, nodes, method=method,
                                        radius=200.0, max_points=8)
            interp3d._DENSE_LIMIT = 20000
            fast = interp3d.interpolate(pts, vals, nodes, method=method,
                                        radius=200.0, max_points=8)
        finally:
            interp3d._DENSE_LIMIT = keep
        assert (np.isfinite(slow) == np.isfinite(fast)).all()
        both = np.isfinite(slow)
        assert np.allclose(slow[both], fast[both], atol=1e-8), method


def test_dense_path_keeps_empty_nodes_empty():
    """Узел без точек в радиусе остаётся пропуском и в блочном пути."""
    pts = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]])
    vals = np.array([1.0, 2.0])
    nodes = np.array([[0.0, 0.0, 0.0], [1000.0, 1000.0, 0.0]])
    got = interp3d.interpolate(pts, vals, nodes, radius=50.0,
                               max_points=4)
    assert abs(got[0] - 1.0) < 1e-9
    assert not np.isfinite(got[1])


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all interp3d tests passed")


if __name__ == "__main__":
    _run()
