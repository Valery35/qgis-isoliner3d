# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Кэш прочитанных гридов: попадания, обесценивание, вытеснение.

GDAL в headless-окружении может отсутствовать, поэтому чтение подменяется
заглушкой: настоящий `_gdal_open` заменяется на фальшивый набор данных,
который считает, сколько раз его открыли. Проверяется именно логика кэша,
а не GDAL.

Запуск:  python isoliner3d/tests/test_cache.py
"""
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(PKG))

import numpy as np                       # noqa: E402
from isoliner3d import viewer3d as v3    # noqa: E402

OPENS = {"n": 0}


class _FakeBand(object):
    def __init__(self, arr, nodata):
        self._arr = arr
        self._nd = nodata

    def ReadAsArray(self):
        return self._arr.copy()

    def GetNoDataValue(self):
        return self._nd


class _FakeDS(object):
    """Минимальный двойник gdal.Dataset: один канал, известная сетка."""

    def __init__(self, arr, nodata=None, bands=1):
        self._arr = arr
        self._nd = nodata
        self.RasterCount = bands

    def GetRasterBand(self, i):
        return _FakeBand(self._arr, self._nd)

    def GetGeoTransform(self):
        return (0.0, 1.0, 0.0, 0.0, 0.0, -1.0)


def _install(arr, nodata=None, bands=1):
    """Подменить открытие набора данных и считать открытия."""
    OPENS["n"] = 0

    def fake_open(source):
        if not source:
            return None
        OPENS["n"] += 1
        return _FakeDS(arr, nodata, bands)

    v3._gdal_open = fake_open


def _tmpfile(name="grid.tif"):
    path = os.path.join(tempfile.mkdtemp(prefix="iso3d_"), name)
    with open(path, "wb") as fh:
        fh.write(b"x" * 16)
    return path


_ORIG_OPEN = v3._gdal_open


def setup():
    v3.cache_clear()


def teardown():
    v3._gdal_open = _ORIG_OPEN
    v3.cache_clear()


def test_second_read_comes_from_cache():
    setup()
    _install(np.arange(9.0).reshape(3, 3))
    p = _tmpfile()
    a1, g1 = v3._read_raster(p, 1)
    a2, g2 = v3._read_raster(p, 1)
    assert OPENS["n"] == 1, "второе чтение полезло на диск"
    assert a2 is a1 and g2 == g1
    teardown()


def test_profiler_counts_hits():
    setup()
    _install(np.zeros((4, 4)))
    p = _tmpfile()
    prof = v3._Prof()
    v3._read_raster(p, 1, prof)
    v3._read_raster(p, 1, prof)
    v3._read_raster(p, 1, prof)
    assert prof.counts.get("reads") == 1, prof.counts
    assert prof.counts.get("hits") == 2, prof.counts
    teardown()


def test_changed_file_is_reread():
    setup()
    _install(np.zeros((4, 4)))
    p = _tmpfile()
    v3._read_raster(p, 1)
    time.sleep(0.01)
    with open(p, "ab") as fh:      # правка файла меняет отметку
        fh.write(b"y")
    v3._read_raster(p, 1)
    assert OPENS["n"] == 2, "правленый грид обязан читаться заново"
    teardown()


def test_bands_are_cached_separately():
    setup()
    _install(np.zeros((4, 4)), bands=2)
    p = _tmpfile()
    v3._read_raster(p, 1)
    v3._read_raster(p, 2)
    v3._read_raster(p, 1)
    assert OPENS["n"] == 2, "каналы обязаны кэшироваться по отдельности"
    teardown()


def test_non_file_source_is_not_cached():
    """У сервиса или подзапроса нет отметки, кэшировать такое нельзя."""
    setup()
    _install(np.zeros((4, 4)))
    v3._read_raster("WMS:http://example/grid", 1)
    v3._read_raster("WMS:http://example/grid", 1)
    assert OPENS["n"] == 2
    assert v3.cache_size()[0] == 0
    teardown()


def test_nodata_becomes_nan_and_array_is_reused():
    setup()
    arr = np.array([[1.0, -9999.0], [3.0, 4.0]])
    _install(arr, nodata=-9999.0)
    p = _tmpfile()
    a1, _ = v3._read_raster(p, 1)
    assert np.isnan(a1[0, 1]), "nodata не превратилось в NaN"
    a2, _ = v3._read_raster(p, 1)
    assert np.isnan(a2[0, 1]), "в кэше лежит массив без NaN"
    teardown()


def test_eviction_keeps_cache_under_limit():
    setup()
    saved = v3._CACHE_LIMIT
    try:
        v3._CACHE_LIMIT = 8 * 1024          # маленький потолок
        big = np.zeros((32, 32))            # 8 КБ на массив
        _install(big)
        for k in range(4):
            v3._read_raster(_tmpfile("g%d.tif" % k), 1)
        count, nbytes = v3.cache_size()
        assert nbytes <= v3._CACHE_LIMIT, (count, nbytes)
        assert count >= 1
    finally:
        v3._CACHE_LIMIT = saved
        teardown()


def test_band_count_opens_once():
    setup()
    _install(np.zeros((4, 4)), bands=3)
    p = _tmpfile()
    assert v3._band_count(p) == 3
    assert v3._band_count(p) == 3
    assert OPENS["n"] == 1, "число каналов обязано кэшироваться"
    teardown()


# ─────────────────────────────────────────────────────────────────────────
# Кэш триангуляции полигонов
# ─────────────────────────────────────────────────────────────────────────

def _load_tri():
    """Кэш триангуляции из viewer3d с подменённой самой триангуляцией."""
    path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "viewer3d.py")
    src = open(path, encoding="utf-8").read()
    a = src.index("def _tessellate(")
    b = src.index("def _flat_z(")
    c = src.index("def _parts_xyz(")
    d = src.index("def _css_rgba(")
    ns = {}
    exec(compile("import numpy as np\n" + src[c:d] + "\n" + src[a:b],  # nosec
                 "viewer3d", "exec"), ns)
    calls = {"n": 0}

    def fake(geom, zfix=None):
        calls["n"] += 1
        return np.zeros((4, 3)), np.zeros((2, 3), dtype=np.int64)

    spatial = {"n": 0}

    def fake_spatial(geom, both_sides=True):
        spatial["n"] += 1
        return np.zeros((6, 3)), np.zeros((3, 3), dtype=np.int64)

    ns["_tessellate"] = fake
    ns["_tris_from_geometry"] = fake_spatial
    ns["tri_cache_clear"]()
    return ns, calls, spatial


class _Box(object):
    def xMinimum(self):
        return 0.0

    def yMinimum(self):
        return 0.0

    def xMaximum(self):
        return 10.0

    def yMaximum(self):
        return 10.0


class _Coords(object):
    def nCoordinates(self):
        return 100


class _Geom2(object):
    def constGet(self):
        return _Coords()

    def boundingBox(self):
        return _Box()


class _Lyr(object):
    def id(self):
        return "layer_1"


class _Feat(object):
    def __init__(self, fid):
        self._fid = fid

    def id(self):
        return self._fid


def test_triangulation_is_cached_per_feature():
    """Разбивка тех же объектов не должна повторяться на каждой сборке.

    На пятистах контурах она занимала шесть секунд и повторялась при
    каждом нажатии «Обновить сцену», хотя геометрия не менялась.
    """
    ns, calls, _sp = _load_tri()
    tri, lyr, geom = ns["_tri_cached"], _Lyr(), _Geom2()
    for _ in range(3):
        tri(lyr, _Feat(1), geom, None)
    assert calls["n"] == 1, calls
    tri(lyr, _Feat(2), geom, None)
    assert calls["n"] == 2, calls
    ns["tri_cache_clear"]()


def test_triangulation_key_separates_elevation():
    """Та же геометрия на другой отметке это другая разбивка."""
    ns, calls, _sp = _load_tri()
    tri, lyr, geom = ns["_tri_cached"], _Lyr(), _Geom2()
    tri(lyr, _Feat(1), geom, None)
    tri(lyr, _Feat(1), geom, 125.0)
    assert calls["n"] == 2, calls
    assert ns["tri_cache_size"]()[0] == 2
    ns["tri_cache_clear"]()
    assert ns["tri_cache_size"]() == (0, 0)


def test_spatial_triangulation_is_cached():
    """Тела с переменной отметкой тоже разбираются один раз.

    Именно этот путь и не был закэширован: слой из 237 тел собирался
    семнадцать секунд, и столько же на каждое нажатие кнопки.
    """
    ns, _calls, spatial = _load_tri()
    tri, lyr, geom = ns["_tri_cached"], _Lyr(), _Geom2()
    for _ in range(4):
        tri(lyr, _Feat(1), geom, None, spatial=True)
    assert spatial["n"] == 1, spatial
    tri(lyr, _Feat(2), geom, None, spatial=True)
    assert spatial["n"] == 2, spatial
    ns["tri_cache_clear"]()


def test_spatial_and_flat_keys_do_not_collide():
    """Разбивка по кольцам и разбивка в плане это разные результаты.

    У одного объекта они обе законны, и подменять одну другой нельзя:
    в плане вертикальная стенка вырождается в линию.
    """
    ns, calls, spatial = _load_tri()
    tri, lyr, geom = ns["_tri_cached"], _Lyr(), _Geom2()
    flat_v, _flat_f = tri(lyr, _Feat(1), geom, None)
    sp_v, _sp_f = tri(lyr, _Feat(1), geom, None, spatial=True)
    assert calls["n"] == 1 and spatial["n"] == 1
    assert len(flat_v) != len(sp_v)
    assert ns["tri_cache_size"]()[0] == 2
    ns["tri_cache_clear"]()


if __name__ == "__main__":
    ok = 0
    for nm, fn in sorted(globals().items()):
        if nm.startswith("test_") and callable(fn):
            fn()
            print("OK", nm)
            ok += 1
    print("all cache tests passed (%d)" % ok)
