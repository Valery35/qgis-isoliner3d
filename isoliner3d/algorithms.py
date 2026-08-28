# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей и блочная модель (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Это свободная программа: вы можете распространять её и/или изменять на
# условиях Стандартной общественной лицензии GNU (GNU GPL) версии 2 либо
# (на ваше усмотрение) любой более поздней версии. Полный текст - в LICENSE.
"""Группа Processing «Пласт и блочная модель».

Семь инструментов, работающих с многоканальным гридом пласта (канал 1 -
кровля, канал 2 - подошва, дальше параметры):

  1.01 Собрать грид пласта          - кровля и подошва в один растр
  1.02 Калькулятор пласта           - мощность, объём, тоннаж, содержание
  1.03 Грид пласта в блочную модель - центроиды ячеек с запасами
  1.04 Поверхности в 3D (меши)      - экспорт в 2DM
  1.05 Домены в канал пласта        - полигоны доменов отдельным каналом
  1.06 Разность запасов (списание)  - разность двух блочных моделей
  1.07 Создать пример данных (демо) - тела с Z и карта для текстуры

Расчёт идёт на NumPy и GDAL, кригинг и построение изолиний здесь не нужны.
Единственные внутренние зависимости - mesh3d и polyhedral.
"""
import configparser
import json
import os

import numpy as np
from osgeo import gdal

from qgis.PyQt.QtCore import QUrl, QVariant

from .i18n import tr as _tr   # нужен до констант уровня модуля

from qgis.core import (
    QgsProcessing,
    QgsProcessingLayerPostProcessorInterface,
    QgsRasterLayer,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingContext,
    QgsProcessingParameterBand,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterString,
    QgsProcessingParameterEnum,
    QgsProcessingParameterExtent,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterDefinition,
    QgsProject,
    QgsSettings,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsMeshLayer,
    QgsPointXY,
    QgsVectorLayer,
    QgsWkbTypes,
)

from .mesh3d import grid_to_2dm, polygon_mask, sample_bilinear

GROUP4 = _tr("1. Пласт и блочная модель")
GROUP4_ID = "bed_block_model"
GRP_MESH3D = _tr("Поверхности 3D")
GROUP5 = _tr("2. 3D-интерполяция")
GROUP5_ID = "interp3d"

# держим пост-процессоры живыми, иначе их соберёт сборщик мусора Python
_KEEP_ALIVE = []


def _finalize_layer(layer, history):
    """Свернуть узел растра в дереве и записать историю создания.

    Стопка гридов иначе раздувает панель слоёв, а история нужна, чтобы
    через полгода было видно, каким инструментом и когда сделан слой.
    """
    try:
        if isinstance(layer, QgsRasterLayer):
            node = QgsProject.instance().layerTreeRoot().findLayer(
                layer.id())
            if node is not None:
                node.setExpanded(False)
    except Exception:  # nosec
        pass
    try:
        if history:
            md = layer.metadata()
            for line in history:
                md.addHistoryItem(line)
            layer.setMetadata(md)
    except Exception:  # nosec
        pass


class _Mesh3DPostProcessor(QgsProcessingLayerPostProcessorInterface):
    """Включает mesh-слою 3D-отображение, если сборка QGIS его поддерживает.

    `qgis._3d` импортируется лениво и под защитой: в headless и в сборках
    без 3D пост-процессор просто ничего не делает.
    """

    def postProcessLayer(self, layer, context, feedback):
        try:
            from qgis._3d import QgsMeshLayer3DRenderer, QgsMesh3DSymbol
            sym = QgsMesh3DSymbol()
            try:
                sym.setSmoothedTriangles(True)
            except Exception:  # nosec
                pass
            r = QgsMeshLayer3DRenderer(sym)
            r.setLayer(layer)
            layer.set3DRenderer(r)
        except Exception:  # nosec
            pass
        _finalize_layer(layer, getattr(self, "history", None) or [])


_VERSION_CACHE = None


CREDIT = ("\n\n- - -\nРазработано при поддержке ООО «Информ++» "
          "(www.informpp.ru).\nСтраница плагина: "
          "www.informpp.ru/главная-страница/qgis-isoliner")


_PERSIST_DENY = {"INPUT", "OUTPUT", "OUTPUT_POLYGONS", "EXTENT", "MASK"}


def _plugin_version():
    """Версия модуля из metadata.txt рядом с этим файлом (кэшируется)."""
    global _VERSION_CACHE
    if _VERSION_CACHE is None:
        ver = ""
        try:
            cp = configparser.ConfigParser(interpolation=None)
            cp.read(os.path.join(os.path.dirname(__file__), "metadata.txt"),
                    encoding="utf-8")
            ver = cp.get("general", "version", fallback="").strip()
        except Exception:
            ver = ""
        _VERSION_CACHE = ver
    return _VERSION_CACHE


def _help_version(text):
    """Дописать версию и приглашение в конец справки инструмента."""
    v = _plugin_version()
    text = "" if text is None else str(text)
    invite = _tr("Isoliner3D развивается на задачах реальных предприятий. "
                 "Если вашему производству не хватает функции - напишите "
                 "нам: https://www.informpp.ru/главная-страница/"
                 "предприятиям")
    tail = ("\n\nIsoliner3D v" + v) if v else ""
    return text + tail + "\n" + invite


def _help_url():
    """file:// ссылка на руководство в комплекте (для кнопки «Справка»).

    На английской локали открывается Isoliner_en.pdf, если он есть; иначе -
    русское Isoliner.pdf. Так одна кнопка даёт справку на языке интерфейса."""
    from .i18n import language as _lang  # текущий язык интерфейса
    doc = os.path.join(os.path.dirname(__file__), "doc")
    candidates = []
    try:
        if _lang() == "en":
            candidates.append("Isoliner3D_en.pdf")
    except Exception:  # nosec
        pass
    candidates.append("Isoliner3D.pdf")
    for fname in candidates:
        p = os.path.join(doc, fname)
        if os.path.exists(p):
            return QUrl.fromLocalFile(p).toString()
    return ""


def _credit():
    """Подпись «Разработано при поддержке…» на активном языке."""
    return _tr(CREDIT)


def _version_line():
    """Строка для Журнала."""
    v = _plugin_version()
    return ("Isoliner3D " + v) if v else "Isoliner3D"


def _provenance(alg, parameters=None):
    """История создания слоя: версия плагина, инструмент, дата."""
    import datetime
    h = []
    try:
        h.append(_version_line())
    except Exception:  # nosec
        pass
    try:
        h.append(_tr("Инструмент: %s") % alg.displayName())
    except Exception:  # nosec
        pass
    try:
        h.append(_tr("Создано: %s")
                 % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    except Exception:  # nosec
        pass
    return h


def _safe_filename(s, used):
    s = (s or "mesh").strip()
    for ch in '<>:"/\\|?*':
        s = s.replace(ch, "_")
    s = s.strip(". ") or "mesh"
    base, k = s, 2
    while s.lower() in used:
        s = "%s_%d" % (base, k)
        k += 1
    used.add(s.lower())
    return s


def _set_output_name(context, path, name):
    """Задаёт имя слоя в дереве, подмешивая имя источника."""
    try:
        if path and context.willLoadLayerOnCompletion(path):
            context.layerToLoadOnCompletionDetails(path).name = name
    except Exception:  # nosec
        pass


def _read_surface(lyr, band=1):
    """Поверхность первым каналом: массив и геопривязка.

    Годится и обычный грид отметок, и кровля пласта
    из многоканального.
    """
    import numpy as np
    ds = gdal.Open(lyr.source())
    if ds is None or ds.RasterCount < band:
        return None, None
    b = ds.GetRasterBand(band)
    arr = b.ReadAsArray().astype(float)
    nd = b.GetNoDataValue()
    if nd is not None:
        arr[arr == nd] = np.nan
    gt = ds.GetGeoTransform()
    ds = None
    return arr, gt


def _read_samples(alg, parameters, context, feedback):
    """Разбор точечных проб: координаты, отметка, значение.

    Общий для 2.02 и 2.05: оба берут один и тот же слой одинаково,
    и разойтись им нельзя. Источник отметки, поле, поверхность
    и отбраковка пропусков читаются здесь один раз.

    Точка, для которой отметку получить не удалось, в расчёт не идёт,
    и число таких пишется в журнал.
    """
    import numpy as np
    from .interp3d import resolve_z, Z_SOURCES

    src = alg.parameterAsSource(parameters, "INPUT", context)
    field = alg.parameterAsString(parameters, "FIELD", context)
    zsrc = Z_SOURCES[alg.parameterAsEnum(parameters, "ZSRC", context)]
    zfield = alg.parameterAsString(parameters, "ZFIELD", context)
    zsurf = alg.parameterAsRasterLayer(parameters, "ZSURF", context)
    if zsrc in ("field", "depth") and not zfield:
        raise QgsProcessingException(alg.tr(
            "Для этого источника отметки нужно поле."))
    surf_arr = surf_gt = None
    if zsrc == "depth":
        if zsurf is None:
            raise QgsProcessingException(alg.tr(
                "Для глубины нужна поверхность отсчёта."))
        # Поверхность читаем первым каналом: годится и обычный грид
        # отметок, и кровля пласта из многоканального.
        ds = gdal.Open(zsurf.source())
        if ds is not None:
            band = ds.GetRasterBand(1)
            surf_arr = band.ReadAsArray().astype(float)
            nd = band.GetNoDataValue()
            if nd is not None:
                surf_arr[surf_arr == nd] = np.nan
            surf_gt = ds.GetGeoTransform()
            ds = None
        if surf_arr is None:
            raise QgsProcessingException(alg.tr(
                "Поверхность отсчёта не открылась."))

    xs, ys, zs, vals = [], [], [], []
    skipped_z = 0
    for ft in src.getFeatures():
        g = ft.geometry()
        if g is None or g.isEmpty():
            continue
        p = g.constGet()
        if zsrc == "geom":
            try:
                z = float(p.z())
            except Exception:  # nosec
                z = float("nan")
        else:
            try:
                fv = float(ft[zfield])
            except (TypeError, ValueError, KeyError):
                fv = float("nan")
            if zsrc == "field":
                z = fv
            else:
                sv = sample_bilinear(surf_arr, surf_gt,
                                     np.array([p.x()]),
                                     np.array([p.y()]))[0]
                z = float(resolve_z("depth", surf=[sv], depth=[fv])[0])
        if z != z:
            skipped_z += 1
            continue
        try:
            v = float(ft[field])
        except (TypeError, ValueError, KeyError):
            v = float("nan")    # не except/continue: сканер даёт B112
        if v != v:
            continue
        xs.append(float(p.x()))
        ys.append(float(p.y()))
        zs.append(z)
        vals.append(v)
    if skipped_z:
        feedback.pushInfo(alg.tr("Без отметки пропущено точек: %d.")
                          % skipped_z)
    if len(vals) < 2:
        raise QgsProcessingException(
            alg.tr("Точек с высотой и значением меньше двух."))
    if len(set(np.round(zs, 6).tolist())) < 2:
        raise QgsProcessingException(alg.tr(
            "Все точки на одной отметке: куб не построить. "
            "Проверьте источник отметки."))
    return xs, ys, zs, vals


def _hints(alg, mapping):
    """Подсказки к полям: по одной на строку ввода.

    Общая справка инструмента лежит сбоку и читается один раз, а решать
    «что сюда писать» приходится у каждого поля. Подсказка отвечает
    ровно на этот вопрос и говорит, чем плох другой выбор.

    Раскладываются одним проходом по уже собранным параметрам, чтобы
    не утяжелять сам список: там и без того по десять строк.
    """
    for prm in alg.parameterDefinitions():
        text = mapping.get(prm.name())
        if not text:
            continue
        try:
            prm.setHelp(alg.tr(text))
        except AttributeError:  # nosec
            return


def _field(name, kind):
    """Поле слоя без устаревшего конструктора.

    В новых сборках QGIS `_field(name, QVariant.Type)` объявлен
    устаревшим и сыплет предупреждениями в журнал. Новый путь через
    `QMetaType.Type`, но он есть не везде, поэтому со скатом
    на прежний.
    """
    try:
        from qgis.PyQt.QtCore import QMetaType
        conv = {QVariant.Int: QMetaType.Type.Int,
                QVariant.Double: QMetaType.Type.Double,
                QVariant.String: QMetaType.Type.QString}
        if kind in conv:
            return QgsField(name, conv[kind])
    except (ImportError, AttributeError):  # nosec
        pass
    return QgsField(name, kind)


def _advanced(param):
    try:
        # QGIS 3.x
        flag = QgsProcessingParameterDefinition.Flag.FlagAdvanced
    except AttributeError:
        from qgis.core import Qgis
        flag = Qgis.ProcessingParameterFlag.Advanced             # QGIS 4
    param.setFlags(param.flags() | flag)
    return param


def _dv(alg, key, fallback):
    """Значение по умолчанию: ранее сохранённое или запасное."""
    return getattr(alg, "_defaults", {}).get(key, fallback)


def _settings_key(alg):
    return "isoliner3d/last/" + alg.name()


def _load_defaults(alg):
    try:
        raw = QgsSettings().value(_settings_key(alg), "")
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def _save_values(alg, parameters):
    try:
        d = {k: v for k, v in parameters.items()
             if k not in _PERSIST_DENY
             and isinstance(v, (int, float, str, bool))}
        QgsSettings().setValue(_settings_key(alg), json.dumps(d))
    except Exception:  # nosec
        pass


def _write_grid_tiff(path, array, geotr, crs_wkt, nodata, nx, ny,
                     band_names=None, meta=None):
    """Пишет Float32 GeoTIFF с геопривязкой и nodata. array - один 2D-массив
    (один канал) или список массивов (многоканальный грид); band_names -
    подписи каналов той же длины."""
    arrs = list(array) if isinstance(array, (list, tuple)) else [array]
    driver = gdal.GetDriverByName("GTiff")
    ds = driver.Create(path, nx, ny, len(arrs), gdal.GDT_Float32,
                       options=["COMPRESS=LZW", "TILED=YES"])
    ds.SetGeoTransform(geotr)
    if crs_wkt:
        ds.SetProjection(crs_wkt)
    if meta:
        # конвенция куба: отметка первого уровня и шаг по вертикали.
        # Без них потребитель не знает, на какой высоте лежит канал
        ds.SetMetadata({str(k): str(v) for k, v in meta.items()})
    for i, a in enumerate(arrs, 1):
        band = ds.GetRasterBand(i)
        band.SetNoDataValue(nodata)
        band.WriteArray(a)
        if band_names:
            band.SetDescription(band_names[i - 1])
        band.FlushCache()
    ds = None


class IsolinerAlgorithm(QgsProcessingAlgorithm):
    """Базовый класс инструментов Isoliner. Оборачивает расчёт журналом
    (trace): имя инструмента, параметры, время, а при сбое - трейсбек на диск
    рядом с окном Processing. Наследники держат тело в _process."""

    def processAlgorithm(self, parameters, context, feedback):
        import time
        from . import trace
        name = self.displayName()
        trace.step("Инструмент: %s" % name)
        trace.data("Параметры: %s" % self._short_params(parameters))
        started = time.time()
        try:
            result = self._process(parameters, context, feedback)
            trace.step("Готово за %.1f с" % (time.time() - started))
            return result
        except Exception as exc:
            trace.fail("%s: расчёт прерван: %s" % (name, exc), exc)
            try:
                feedback.reportError(
                    "Расчёт прерван: %s\n\nПодробности в журнале:\n%s"
                    % (exc, trace.path() or "журнал не заведён"))
            except Exception:  # nosec
                pass
            raise

    def tr(self, text, *args):
        """Перевод строки инструмента.

        В QGIS 4 базовый класс Processing этот метод больше не даёт,
        а им пользуются все инструменты, поэтому держим свой.
        """
        return _tr(text)

    def _process(self, parameters, context, feedback):
        raise NotImplementedError

    def _short_params(self, parameters):
        parts = []
        try:
            for key, value in sorted(parameters.items()):
                text = getattr(value, "name", None)
                text = text() if callable(text) else (text or value)
                parts.append("%s=%s" % (key, text))
        except Exception:
            return str(parameters)
        return ", ".join(parts)


class BedAssembleAlgorithm(IsolinerAlgorithm):
    """Собирает многоканальный грид пласта из горизонтов и параметров:
    канал 1 - кровля, канал 2 - подошва, каналы 3+ - параметры. Все входы
    приводятся к сетке кровли билинейной выборкой; имена каналов пишутся
    в описания (у параметров - имена слоёв)."""

    ROOF, BOTTOM = "ROOF", "BOTTOM"
    ROOF_BAND, BOTTOM_BAND = "ROOF_BAND", "BOTTOM_BAND"
    PARAMS = "PARAMS"
    OUTPUT = "OUTPUT"

    def tr(self, s): return _tr(s)
    def createInstance(self): return BedAssembleAlgorithm()
    def name(self): return "assemble_bed_grid"
    def displayName(self): return self.tr("1.01 Собрать грид пласта")
    def helpUrl(self): return _help_url()
    def group(self): return self.tr(GROUP4)
    def groupId(self): return GROUP4_ID

    def shortHelpString(self):
        return _help_version(self.tr(
            "Собирает многоканальный грид пласта по конвенции плагина: "
            "канал 1 - кровля, канал 2 - подошва, каналы 3 и далее - "
            "параметры (содержание, минтип и любые другие). Кровля задаёт "
            "сетку результата; подошва и параметры билинейно приводятся к "
            "ней, поэтому исходные гриды могут иметь разные сетки. Имена "
            "каналов записываются в описания: «кровля», «подошва», далее "
            "имена слоёв параметров.\n\nОдин собранный файл кормит "
            "«Состав пласта на разрез» (каналы 1/2/3), 3D-просмотр (тела "
            "пластов) и экспорт в меши - это шаг к блочной модели, где "
            "новые параметры добавляются каналами.") + _credit())

    def initAlgorithm(self, config=None):
        self._defaults = _load_defaults(self)
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.ROOF, self.tr("Кровля (растр)")))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.BOTTOM, self.tr("Подошва (растр)")))
        self.addParameter(QgsProcessingParameterMultipleLayers(
            self.PARAMS, self.tr("Параметры (растры, берётся канал 1)"),
            layerType=QgsProcessing.SourceType.TypeRaster, optional=True))
        self.addParameter(_advanced(QgsProcessingParameterBand(
            self.ROOF_BAND, self.tr("Канал кровли"),
            defaultValue=_dv(self, self.ROOF_BAND, 1),
            parentLayerParameterName=self.ROOF)))
        self.addParameter(_advanced(QgsProcessingParameterBand(
            self.BOTTOM_BAND, self.tr("Канал подошвы"),
            defaultValue=_dv(self, self.BOTTOM_BAND, 1),
            parentLayerParameterName=self.BOTTOM)))
        self.addParameter(QgsProcessingParameterRasterDestination(
            self.OUTPUT, self.tr("Грид пласта")))
        _hints(self, HINTS_1_01)

    @staticmethod
    def _read_band(path, band):
        ds = gdal.Open(path)
        if ds is None or band > ds.RasterCount:
            return None, None
        b = ds.GetRasterBand(band)
        arr = b.ReadAsArray().astype(float)
        nd = b.GetNoDataValue()
        if nd is not None:
            arr = np.where(arr == nd, np.nan, arr)
        gt = ds.GetGeoTransform()
        ds = None
        return arr, gt

    def _process(self, parameters, context, feedback):
        feedback.pushInfo(_version_line())
        _saved = dict(parameters)
        roof_l = self.parameterAsRasterLayer(parameters, self.ROOF, context)
        bot_l = self.parameterAsRasterLayer(parameters, self.BOTTOM, context)
        params = self.parameterAsLayerList(
            parameters, self.PARAMS, context) or []
        rb = self.parameterAsInt(parameters, self.ROOF_BAND, context)
        bb = self.parameterAsInt(parameters, self.BOTTOM_BAND, context)
        out = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

        roof, gt = self._read_band(roof_l.source(), rb)
        if roof is None:
            raise QgsProcessingException(self.tr("Гриды не открылись."))
        ny, nx = roof.shape
        xs = gt[0] + (np.arange(nx) + 0.5) * gt[1]
        ys = gt[3] + (np.arange(ny) + 0.5) * gt[5]
        XX, YY = np.meshgrid(xs, ys)

        def to_frame(lyr, band):
            arr, g2 = self._read_band(lyr.source(), band)
            if arr is None:
                return None
            if arr.shape == roof.shape and np.allclose(g2, gt):
                return arr
            return sample_bilinear(arr, g2, XX.ravel(), YY.ravel()) \
                .reshape(roof.shape)

        bot = to_frame(bot_l, bb)
        if bot is None:
            raise QgsProcessingException(self.tr("Гриды не открылись."))
        stack = [roof, bot]
        bnames = [self.tr("кровля"), self.tr("подошва")]
        for lyr in params:
            a = to_frame(lyr, 1)
            if a is None:
                feedback.pushWarning(
                    _tr("Грид не открылся: %s") % lyr.name())
                continue
            stack.append(a)
            bnames.append(lyr.name())
        nod = -9999.0
        stack = [np.where(np.isfinite(a), a, nod).astype(np.float32)
                 for a in stack]
        crs_wkt = roof_l.crs().toWkt() if roof_l.crs().isValid() else ""
        _write_grid_tiff(out, stack, gt, crs_wkt, nod, nx, ny,
                         band_names=bnames)
        feedback.pushInfo(
            _tr("Грид пласта записан: каналов %d.") % len(stack))
        _save_values(self, _saved)
        return {self.OUTPUT: out}


class BedCalculatorAlgorithm(IsolinerAlgorithm):
    """Подсчёт по гриду пласта: мощность из каналов кровли и подошвы,
    объём, тоннаж руды и металла, средневзвешенное содержание; сводка по
    всей площади или внутри контура. Мощность и запасы дописываются
    каналами в новый грид пласта."""

    BED = "BED"
    CONTENT_BAND = "CONTENT_BAND"
    DENSITY = "DENSITY"
    CONTOUR = "CONTOUR"
    OUTPUT, REPORT = "OUTPUT", "REPORT"

    def tr(self, s): return _tr(s)
    def createInstance(self): return BedCalculatorAlgorithm()
    def name(self): return "bed_calculator"
    def displayName(self): return self.tr("1.02 Калькулятор пласта")
    def helpUrl(self): return _help_url()
    def group(self): return self.tr(GROUP4)
    def groupId(self): return GROUP4_ID

    def shortHelpString(self):
        return _help_version(self.tr(
            "Считает по многоканальному гриду пласта (канал 1 - кровля, "
            "канал 2 - подошва): мощность, объём, тоннаж руды через "
            "плотность и, если задан канал содержания, средневзвешенное по "
            "мощности содержание и тоннаж металла. Сводка - по всей площади "
            "пласта или внутри контура (полигоны подсчётного блока, "
            "домена).\n\nРезультат - грид пласта с дописанными каналами "
            "«мощность» и «запасы руды, т/ячейку» и HTML-отчёт со сводкой. "
            "Ячейки с мощностью меньше нуля (пересечение поверхностей) "
            "обнуляются и считаются отдельно.") + _credit())

    def initAlgorithm(self, config=None):
        self._defaults = _load_defaults(self)
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.BED,
            self.tr("Грид пласта (канал 1 кровля, канал 2 подошва)")))
        self.addParameter(QgsProcessingParameterBand(
            self.CONTENT_BAND,
            self.tr("Канал содержания (пусто - без содержания)"),
            defaultValue=_dv(self, self.CONTENT_BAND, 3),
            parentLayerParameterName=self.BED, optional=True))
        self.addParameter(QgsProcessingParameterNumber(
            self.DENSITY, self.tr("Плотность руды, т/м³"),
            QgsProcessingParameterNumber.Type.Double,
            defaultValue=_dv(self, self.DENSITY, 2.1), minValue=0.01))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.CONTOUR, self.tr("Контур подсчёта (полигоны, необязательно)"),
            [QgsProcessing.SourceType.TypeVectorPolygon], optional=True))
        self.addParameter(QgsProcessingParameterRasterDestination(
            self.OUTPUT, self.tr("Грид пласта с мощностью и запасами")))
        self.addParameter(QgsProcessingParameterFileDestination(
            self.REPORT, self.tr("Отчёт (HTML)"),
            self.tr("HTML-файлы (*.html)"), optional=True,
            createByDefault=True))
        _hints(self, HINTS_1_02)

    def _process(self, parameters, context, feedback):
        feedback.pushInfo(_version_line())
        _saved = dict(parameters)
        bed_l = self.parameterAsRasterLayer(parameters, self.BED, context)
        cband = self.parameterAsInt(parameters, self.CONTENT_BAND, context)
        dens = self.parameterAsDouble(parameters, self.DENSITY, context)
        contour = self.parameterAsSource(parameters, self.CONTOUR, context)
        out = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)
        report = self.parameterAsFileOutput(parameters, self.REPORT, context)

        ds = gdal.Open(bed_l.source())
        if ds is None or ds.RasterCount < 2:
            raise QgsProcessingException(
                self.tr("Нужен многоканальный грид пласта (каналы 1 и 2)."))
        gt = ds.GetGeoTransform()
        ny, nx = ds.RasterYSize, ds.RasterXSize

        def band(i):
            b = ds.GetRasterBand(i)
            a = b.ReadAsArray().astype(float)
            nd = b.GetNoDataValue()
            if nd is not None:
                a = np.where(a == nd, np.nan, a)
            return a, (b.GetDescription() or "")

        stack, names = [], []
        for i in range(1, ds.RasterCount + 1):
            a, nm = band(i)
            stack.append(a)
            names.append(nm or str(i))
        ds = None
        roof, bot = stack[0], stack[1]
        thick = roof - bot
        neg = int(np.nansum(thick < 0))
        thick = np.where(np.isfinite(thick), np.maximum(thick, 0.0), np.nan)

        cell = abs(gt[1] * gt[5])
        mask = np.isfinite(thick)
        if contour is not None:
            rings = []
            for ft in contour.getFeatures():
                g = ft.geometry()
                if g is None or g.isEmpty():
                    continue
                try:
                    polys = g.asMultiPolygon()
                except Exception:
                    polys = []
                if not polys:
                    try:
                        p1 = g.asPolygon()
                    except Exception:
                        p1 = []
                    polys = [p1] if p1 else []
                for poly in polys:
                    for ring in poly:
                        rings.append([(p.x(), p.y()) for p in ring])
            if rings:
                mask &= polygon_mask(rings, gt, (ny, nx))

        area = float(mask.sum()) * cell
        vol = float(np.nansum(np.where(mask, thick, 0.0))) * cell
        ore_t = vol * dens
        t_valid = thick[mask]
        t_mean = float(np.nanmean(t_valid)) if t_valid.size else 0.0
        t_min = float(np.nanmin(t_valid)) if t_valid.size else 0.0
        t_max = float(np.nanmax(t_valid)) if t_valid.size else 0.0

        grade_mean = metal_t = None
        if cband > 0:
            if cband > len(stack):
                raise QgsProcessingException(
                    self.tr("Канал содержания вне грида."))
            grade = stack[cband - 1]
            w = np.where(mask & np.isfinite(grade), thick, 0.0)
            sw = float(np.nansum(w))
            if sw > 0:
                grade_mean = float(np.nansum(
                    np.where(mask & np.isfinite(grade),
                             thick * grade, 0.0))) / sw
                metal_t = ore_t * grade_mean / 100.0

        ore_cell = np.where(mask, thick * cell * dens, np.nan)
        out_stack = stack + [thick, ore_cell]
        out_names = names + [self.tr("мощность"),
                             self.tr("запасы руды, т/ячейку")]
        nod = -9999.0
        out_stack = [np.where(np.isfinite(a), a, nod).astype(np.float32)
                     for a in out_stack]
        crs_wkt = bed_l.crs().toWkt() if bed_l.crs().isValid() else ""
        _write_grid_tiff(out, out_stack, gt, crs_wkt, nod, nx, ny,
                         band_names=out_names)

        rows = [
            (self.tr("Площадь подсчёта"), "%.4g м²" % area),
            (self.tr("Мощность средняя / мин / макс"),
             "%.2f / %.2f / %.2f м" % (t_mean, t_min, t_max)),
            (self.tr("Объём"), "%.4g м³" % vol),
            (self.tr("Плотность"), "%.3g т/м³" % dens),
            (self.tr("Запасы руды"), "%.4g т" % ore_t),
        ]
        if grade_mean is not None:
            rows.append((self.tr("Содержание (взвешенное по мощности)"),
                         "%.3f" % grade_mean))
            rows.append((self.tr("Запасы металла"), "%.4g т" % metal_t))
        if neg:
            rows.append((self.tr("Ячеек с отрицательной мощностью"),
                         str(neg)))
        for k, v in rows:
            feedback.pushInfo("%s: %s" % (k, v))
        if report:
            html = ["<html><head><meta charset='utf-8'><style>",
                    "body{font-family:sans-serif;margin:2em}",
                    "table{border-collapse:collapse}",
                    "td{border:1px solid #999;padding:6px 12px}",
                    "</style></head><body>",
                    "<h2>%s</h2>" % self.tr("Калькулятор пласта"),
                    "<p>%s</p>" % bed_l.name(), "<table>"]
            for k, v in rows:
                html.append("<tr><td>%s</td><td>%s</td></tr>" % (k, v))
            html.append("</table></body></html>")
            with open(report, "w", encoding="utf-8") as f:
                f.write("\n".join(html))
        _save_values(self, _saved)
        res = {self.OUTPUT: out}
        if report:
            res[self.REPORT] = report
        return res


class BedToBlockModelAlgorithm(IsolinerAlgorithm):
    """Грид пласта -> блочная модель: точка-центроид на каждую валидную
    ячейку с атрибутами верха, низа, мощности, объёма, тоннажа и всех
    каналов параметров по их именам. Схема наращивается атрибутами
    (join, калькулятор полей) и готова к делению колонок по вертикали."""

    BED = "BED"
    DENSITY = "DENSITY"
    DENS_BAND = "DENS_BAND"
    CONTOUR = "CONTOUR"
    NZ = "NZ"
    OUTPUT = "OUTPUT"

    def tr(self, s): return _tr(s)
    def createInstance(self): return BedToBlockModelAlgorithm()
    def name(self): return "bed_to_block_model"
    def displayName(self): return self.tr("1.03 Грид пласта в блочную модель")
    def helpUrl(self): return _help_url()
    def group(self): return self.tr(GROUP4)
    def groupId(self): return GROUP4_ID

    def shortHelpString(self):
        return _help_version(self.tr(
            "Переводит многоканальный грид пласта в блочную модель: точку-"
            "центроид на каждую валидную ячейку. Атрибуты: строка и столбец "
            "ячейки, координаты, верх (top), низ (bot), мощность (thick), "
            "объём (vol), тоннаж руды (ore_t) через плотность и все каналы "
            "параметров под их именами из описаний.\n\nДальше работает "
            "векторный аппарат QGIS: фильтры выражениями, join внешних "
            "таблиц, калькулятор полей - модель наращивается атрибутами без "
            "пересоздания. Контур ограничивает выгрузку подсчётным блоком "
            "или доменом.\n\nПараметр «Слоёв по вертикали» делит каждую "
            "колонку на N блоков между кровлей и подошвой: у каждого свои "
            "z_from, z_to, номер слоя lay и доля объёма. Содержание "
            "копируется в под-блоки (по вертикали оно не разбурено). Это "
            "заготовка настоящей 3D-модели.\n\nПлотность берётся из "
            "числа выше или, если задан «Канал плотности», из этого канала "
            "грида поячеечно - для переменной по площади плотности руды.")
            + _credit())

    def initAlgorithm(self, config=None):
        self._defaults = _load_defaults(self)
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.BED,
            self.tr("Грид пласта (канал 1 кровля, канал 2 подошва)")))
        self.addParameter(QgsProcessingParameterNumber(
            self.DENSITY, self.tr("Плотность руды, т/м³"),
            QgsProcessingParameterNumber.Type.Double,
            defaultValue=_dv(self, self.DENSITY, 2.1), minValue=0.01))
        self.addParameter(_advanced(QgsProcessingParameterBand(
            self.DENS_BAND,
            self.tr("Канал плотности (пусто - брать значение выше)"),
            parentLayerParameterName=self.BED, optional=True)))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.CONTOUR, self.tr("Контур подсчёта (полигоны, необязательно)"),
            [QgsProcessing.SourceType.TypeVectorPolygon], optional=True))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            self.NZ, self.tr("Слоёв по вертикали (деление колонки)"),
            QgsProcessingParameterNumber.Type.Integer,
            defaultValue=_dv(self, self.NZ, 1), minValue=1, maxValue=100)))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Блочная модель (центроиды)"),
            QgsProcessing.SourceType.TypeVectorPoint))
        _hints(self, HINTS_1_03)

    def _process(self, parameters, context, feedback):
        feedback.pushInfo(_version_line())
        _saved = dict(parameters)
        bed_l = self.parameterAsRasterLayer(parameters, self.BED, context)
        dens = self.parameterAsDouble(parameters, self.DENSITY, context)
        _db = self.parameterAsString(parameters, self.DENS_BAND, context)
        try:
            dens_band = int(_db) if _db not in (None, "") else 0
        except (TypeError, ValueError):
            dens_band = 0
        contour = self.parameterAsSource(parameters, self.CONTOUR, context)
        nz = max(self.parameterAsInt(parameters, self.NZ, context), 1)

        ds = gdal.Open(bed_l.source())
        if ds is None or ds.RasterCount < 2:
            raise QgsProcessingException(
                self.tr("Нужен многоканальный грид пласта (каналы 1 и 2)."))
        gt = ds.GetGeoTransform()
        ny, nx = ds.RasterYSize, ds.RasterXSize
        stack, names = [], []
        for i in range(1, ds.RasterCount + 1):
            b = ds.GetRasterBand(i)
            a = b.ReadAsArray().astype(float)
            nd = b.GetNoDataValue()
            if nd is not None:
                a = np.where(a == nd, np.nan, a)
            stack.append(a)
            names.append(b.GetDescription() or ("band%d" % i))
        ds = None
        roof, bot = stack[0], stack[1]
        thick = np.where(np.isfinite(roof - bot),
                         np.maximum(roof - bot, 0.0), np.nan)
        if dens_band and dens_band <= len(stack):
            dens_arr = stack[dens_band - 1]
        else:
            dens_arr = np.full_like(roof, dens, dtype=float)
        cell = abs(gt[1] * gt[5])
        mask = np.isfinite(thick)
        if contour is not None:
            rings = []
            for ft in contour.getFeatures():
                g = ft.geometry()
                if g is None or g.isEmpty():
                    continue
                try:
                    polys = g.asMultiPolygon()
                except Exception:
                    polys = []
                if not polys:
                    try:
                        p1 = g.asPolygon()
                    except Exception:
                        p1 = []
                    polys = [p1] if p1 else []
                for poly in polys:
                    for ring in poly:
                        rings.append([(p.x(), p.y()) for p in ring])
            if rings:
                mask &= polygon_mask(rings, gt, (ny, nx))

        def _safe(nm, used):
            s = nm.strip() or "band"
            for ch in ' ,;:/\\()"\'':
                s = s.replace(ch, "_")
            base, k = s, 2
            while s in used:
                s = "%s_%d" % (base, k)
                k += 1
            used.add(s)
            return s

        used = {"bid", "row", "col", "lay", "x", "y", "top", "bot",
                "z_from", "z_to", "thick", "vol", "dens", "ore_t"}
        pnames = [_safe(nm, used) for nm in names[2:]]
        fields = QgsFields()
        for nm, tp in (("bid", QVariant.Int), ("row", QVariant.Int),
                       ("col", QVariant.Int), ("lay", QVariant.Int),
                       ("x", QVariant.Double), ("y", QVariant.Double),
                       ("top", QVariant.Double), ("bot", QVariant.Double),
                       ("z_from", QVariant.Double), ("z_to", QVariant.Double),
                       ("thick", QVariant.Double), ("vol", QVariant.Double),
                       ("dens", QVariant.Double), ("ore_t", QVariant.Double)):
            fields.append(_field(nm, tp))
        for nm in pnames:
            fields.append(_field(nm, QVariant.Double))
        sink, dest = self.parameterAsSink(
            parameters, self.OUTPUT, context, fields,
            QgsWkbTypes.Type.Point, bed_l.crs())

        idx = np.argwhere(mask)
        total = len(idx)
        bid = 0
        for n, (i, j) in enumerate(idx):
            if feedback.isCanceled():
                break
            if total and n % 5000 == 0:
                feedback.setProgress(100.0 * n / total)
            x = gt[0] + (j + 0.5) * gt[1]
            y = gt[3] + (i + 0.5) * gt[5]
            r_top = float(roof[i, j])
            r_bot = float(bot[i, j])
            th_full = float(thick[i, j])
            d_ij = float(dens_arr[i, j])
            if not (d_ij == d_ij) or d_ij <= 0:
                d_ij = dens
            dz = th_full / nz
            params = [(float(a[i, j]) if a[i, j] == a[i, j] else None)
                      for a in stack[2:]]
            for L in range(nz):
                zf = r_top - L * dz          # сверху вниз
                zt = r_top - (L + 1) * dz
                bid += 1
                vol = dz * cell
                f = QgsFeature(fields)
                f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
                attrs = [bid, int(i), int(j), L, float(x), float(y),
                         r_top, r_bot, zf, zt, dz, vol, d_ij, vol * d_ij]
                attrs.extend(params)
                f.setAttributes(attrs)
                sink.addFeature(f)
        _set_output_name(context, dest,
                         self.tr("Блочная модель: %s") % bed_l.name())
        feedback.pushInfo(_tr("Блоков выгружено: %d.") % bid)
        _save_values(self, _saved)
        return {self.OUTPUT: dest}


class SectionSurfacesToMeshAlgorithm(IsolinerAlgorithm):
    """Гриды поверхностей -> mesh-слои 2DM для штатного 3D-вида QGIS. Растровых
    поверхностей в 3D-сцене может быть только одна (террейн), а mesh-слоёв -
    сколько угодно, каждый на своих абсолютных Z. Инструмент пишет каждый грид
    отдельным 2DM и загружает mesh-слои в проект, применяя вертикальное
    преобразование Z' = Z * масштаб + смещение."""

    GRIDS, ZSCALE, ZOFFSET, STEP = "GRIDS", "ZSCALE", "ZOFFSET", "STEP"
    ZBAND = "ZBAND"
    SPACING = "SPACING"
    FOLDER = "FOLDER"

    def tr(self, s): return _tr(s)
    def createInstance(self): return SectionSurfacesToMeshAlgorithm()
    def name(self): return "surfaces_to_mesh3d"
    def displayName(self): return self.tr("1.04 Поверхности в 3D (меши)")
    def helpUrl(self): return _help_url()
    def group(self): return self.tr(GROUP4)
    def groupId(self): return GROUP4_ID

    def shortHelpString(self):
        return _help_version(self.tr(
            "Экспортирует гриды поверхностей в mesh-слои стандартного формата "
            "2DM (MDAL). Такие слои понимают профильный инструмент QGIS, "
            "mesh-калькулятор, штатный 3D-вид и сторонние программы, а пачка "
            "горизонтов кровля-подошва уходит в меши без ручных "
            "конвертаций.\n\nК отметкам при записи "
            "применяется вертикальное преобразование "
            "Z' = Z * масштаб + смещение: масштаб даёт вертикальное "
            "преувеличение, смещение разносит горизонты по высоте. "
            "Разнос по Z сдвигает каждый следующий грид на шаг вниз, "
            "превращая слипшуюся стопку в читаемую этажерку. Прореживание "
            "уменьшает количество узлов на крупных гридах.\n\n"
            "Слои загружаются в проект и получают 3D-отображение "
            "автоматически. Если сцена уже открыта, включите новые слои "
            "в её списке. Ячейки без "
            "данных пропускаются.") + _credit())

    def initAlgorithm(self, config=None):
        self._defaults = _load_defaults(self)
        self.addParameter(QgsProcessingParameterMultipleLayers(
            self.GRIDS, self.tr("Поверхности-гриды"),
            layerType=QgsProcessing.SourceType.TypeRaster))
        self.addParameter(QgsProcessingParameterNumber(
            self.ZSCALE, self.tr("Масштаб Z (вертикальное преувеличение)"),
            QgsProcessingParameterNumber.Type.Double,
            defaultValue=_dv(self, self.ZSCALE, 1.0)))
        self.addParameter(QgsProcessingParameterNumber(
            self.ZOFFSET, self.tr("Смещение Z"),
            QgsProcessingParameterNumber.Type.Double,
            defaultValue=_dv(self, self.ZOFFSET, 0.0)))
        self.addParameter(QgsProcessingParameterNumber(
            self.SPACING, self.tr(
                "Разнос по Z (шаг на каждый следующий грид)"),
            QgsProcessingParameterNumber.Type.Double,
            defaultValue=_dv(self, self.SPACING, 0.0)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            self.STEP, self.tr("Прореживание узлов (каждый N-й)"),
            QgsProcessingParameterNumber.Type.Integer,
            defaultValue=_dv(self, self.STEP, 1), minValue=1)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            self.ZBAND, self.tr("Канал высот (Z)"),
            QgsProcessingParameterNumber.Type.Integer,
            defaultValue=_dv(self, self.ZBAND, 1), minValue=1)))
        self.addParameter(QgsProcessingParameterFolderDestination(
            self.FOLDER, self.tr("Папка для мешей (2DM)")))
        _hints(self, HINTS_1_04)

    def _process(self, parameters, context, feedback):
        feedback.pushInfo(_version_line())
        _saved = dict(parameters)
        grids = self.parameterAsLayerList(parameters, self.GRIDS, context)
        if not grids:
            raise QgsProcessingException(self.tr("Нужен хотя бы один грид."))
        zscale = self.parameterAsDouble(parameters, self.ZSCALE, context)
        zoffset = self.parameterAsDouble(parameters, self.ZOFFSET, context)
        spacing = self.parameterAsDouble(parameters, self.SPACING, context)
        step = self.parameterAsInt(parameters, self.STEP, context)
        folder = self.parameterAsString(parameters, self.FOLDER, context)
        os.makedirs(folder, exist_ok=True)

        used, written = set(), 0
        for k, lyr in enumerate(grids):
            if feedback.isCanceled():
                break
            ds = gdal.Open(lyr.source())
            zband = self.parameterAsInt(parameters, self.ZBAND, context)
            if ds is None or zband > ds.RasterCount:
                feedback.pushWarning(_tr("Грид не открылся: %s") % lyr.name())
                continue
            b = ds.GetRasterBand(zband)
            arr = b.ReadAsArray().astype(float)
            nd = b.GetNoDataValue()
            if nd is not None:
                arr = np.where(arr == nd, np.nan, arr)
            gt = ds.GetGeoTransform()
            ds = None
            fn = os.path.join(folder,
                              _safe_filename(lyr.name(), used) + ".2dm")
            try:
                nv, nt = grid_to_2dm(arr, gt, fn, zscale,
                                     zoffset - spacing * k, step)
            except ValueError:
                feedback.pushWarning(
                    _tr("Грид пропущен (мал или пуст): %s") % lyr.name())
                continue
            feedback.pushInfo(
                _tr("Меш записан: %s (узлов %d, треугольников %d).")
                % (os.path.basename(fn), nv, nt))
            written += 1
            ml = QgsMeshLayer(fn, lyr.name(), "mdal")
            if not ml.isValid():
                feedback.pushWarning(
                    _tr("Слой меша не загрузился: %s") % os.path.basename(fn))
                continue
            try:
                ml.setCrs(lyr.crs())
            except Exception:  # nosec
                pass
            context.temporaryLayerStore().addMapLayer(ml)
            det = QgsProcessingContext.LayerDetails(
                lyr.name(), context.project(), self.FOLDER)
            det.groupName = GRP_MESH3D
            pp = _Mesh3DPostProcessor()
            pp.history = _provenance(self, parameters)
            _KEEP_ALIVE.append(pp)
            det.setPostProcessor(pp)
            context.addLayerToLoadOnCompletion(ml.id(), det)
        if written == 0:
            raise QgsProcessingException(self.tr("Гриды не открылись."))
        _save_values(self, _saved)
        return {self.FOLDER: folder}


class DomainsToGridAlgorithm(IsolinerAlgorithm):
    """Полигоны доменов -> добавочный канал грида пласта с кодом домена
    в каждой ячейке. Дальше калькулятор и блочная модель считают по
    доменам, а разность двух состояний даёт списание запасов."""

    BED = "BED"
    DOMAINS = "DOMAINS"
    FIELD = "FIELD"
    OUTPUT = "OUTPUT"

    def tr(self, s): return _tr(s)
    def createInstance(self): return DomainsToGridAlgorithm()
    def name(self): return "domains_to_grid"
    def displayName(self): return self.tr("1.05 Домены в канал пласта")
    def helpUrl(self): return _help_url()
    def group(self): return self.tr(GROUP4)
    def groupId(self): return GROUP4_ID

    def shortHelpString(self):
        return _help_version(self.tr(
            "Растеризует полигоны доменов в добавочный канал грида пласта: "
            "каждой ячейке присваивается код домена, в который она попадает "
            "(0 - вне доменов). Код берётся из числового поля слоя или, если "
            "поле не задано, это порядковый номер объекта от 1. Каналы "
            "исходного грида сохраняются, канал «domain» дописывается "
            "последним.\n\nДальше домен работает как обычный параметр: "
            "калькулятор пласта считает по контуру домена, блочная модель "
            "фильтруется по коду. Списание запасов - это разность двух "
            "состояний домена: посчитайте запасы по контуру до и после "
            "погашения, вычтите. Контуры доменов должны лежать в той же "
            "системе координат, что и грид.") + _credit())

    def initAlgorithm(self, config=None):
        self._defaults = _load_defaults(self)
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.BED, self.tr("Грид пласта")))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.DOMAINS, self.tr("Полигоны доменов"),
            [QgsProcessing.SourceType.TypeVectorPolygon]))
        self.addParameter(_advanced(QgsProcessingParameterField(
            self.FIELD, self.tr("Поле кода домена (число, необязательно)"),
            parentLayerParameterName=self.DOMAINS, optional=True,
            type=QgsProcessingParameterField.DataType.Numeric)))
        self.addParameter(QgsProcessingParameterRasterDestination(
            self.OUTPUT, self.tr("Грид пласта с каналом domain")))
        _hints(self, HINTS_1_05)

    def _process(self, parameters, context, feedback):
        feedback.pushInfo(_version_line())
        _saved = dict(parameters)
        bed_l = self.parameterAsRasterLayer(parameters, self.BED, context)
        domains = self.parameterAsSource(parameters, self.DOMAINS, context)
        field = self.parameterAsString(parameters, self.FIELD, context)
        out = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

        ds = gdal.Open(bed_l.source())
        if ds is None:
            raise QgsProcessingException(self.tr("Грид не открылся."))
        gt = ds.GetGeoTransform()
        ny, nx = ds.RasterYSize, ds.RasterXSize
        stack, names = [], []
        for i in range(1, ds.RasterCount + 1):
            b = ds.GetRasterBand(i)
            a = b.ReadAsArray().astype(np.float32)
            nd = b.GetNoDataValue()
            if nd is not None:
                a = np.where(a == nd, np.nan, a).astype(np.float32)
            stack.append(a)
            names.append(b.GetDescription() or ("band%d" % i))
        ds = None

        domain = np.zeros((ny, nx), dtype=np.float32)
        n_assigned = 0
        for k, ft in enumerate(domains.getFeatures(), start=1):
            if feedback.isCanceled():
                break
            g = ft.geometry()
            if g is None or g.isEmpty():
                continue
            code = k
            if field:
                v = ft[field]
                if v is not None:
                    try:
                        code = float(v)
                    except (TypeError, ValueError):
                        code = k
            rings = []
            try:
                mp = g.asMultiPolygon()
            except Exception:
                mp = []
            if not mp:
                try:
                    p1 = g.asPolygon()
                except Exception:
                    p1 = []
                mp = [p1] if p1 else []
            for poly in mp:
                for ring in poly:
                    rings.append([(p.x(), p.y()) for p in ring])
            if not rings:
                continue
            m = polygon_mask(rings, gt, (ny, nx))
            domain[m] = code
            n_assigned += int(m.sum())

        stack.append(domain)
        names.append("domain")
        crs_wkt = bed_l.crs().toWkt() if bed_l.crs().isValid() else ""
        _write_grid_tiff(out, stack, gt, crs_wkt, -9999.0, nx, ny,
                         band_names=names)
        feedback.pushInfo(
            _tr("Домены записаны в канал %d. Ячеек в доменах: %d.")
            % (len(stack), n_assigned))
        _save_values(self, _saved)
        return {self.OUTPUT: out}


class ReserveDeltaAlgorithm(IsolinerAlgorithm):
    """Разность двух блочных моделей по совпадающим ячейкам: списание
    запасов между состояниями (было -> стало)."""

    BEFORE = "BEFORE"
    AFTER = "AFTER"
    FIELD = "FIELD"
    OUTPUT = "OUTPUT"

    def tr(self, s): return _tr(s)
    def createInstance(self): return ReserveDeltaAlgorithm()
    def name(self): return "reserve_delta"
    def displayName(self): return self.tr("1.06 Разность запасов (списание)")
    def helpUrl(self): return _help_url()
    def group(self): return self.tr(GROUP4)
    def groupId(self): return GROUP4_ID

    def shortHelpString(self):
        return _help_version(self.tr(
            "Считает разность двух блочных моделей по ячейкам с одинаковыми "
            "row и col: сколько запаса убыло между состояниями «было» и "
            "«стало». Для каждой ячейки вычитается выбранное поле (по "
            "умолчанию ore_t), результат - точки со значениями delta "
            "(было минус стало), before и after.\n\nЭто прямой путь "
            "оперативного списания: модель до погашения камер минус модель "
            "после - и сумма delta по контуру даёт списанный тоннаж. Модели "
            "должны быть построены из одного грида (совпадающая нарезка row "
            "и col).") + _credit())

    def initAlgorithm(self, config=None):
        self._defaults = _load_defaults(self)
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.BEFORE, self.tr("Модель «было» (центроиды)"),
            [QgsProcessing.SourceType.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.AFTER, self.tr("Модель «стало» (центроиды)"),
            [QgsProcessing.SourceType.TypeVectorPoint]))
        self.addParameter(_advanced(QgsProcessingParameterField(
            self.FIELD, self.tr("Поле запаса"),
            parentLayerParameterName=self.BEFORE,
            defaultValue="ore_t",
            type=QgsProcessingParameterField.DataType.Numeric)))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Разность (центроиды)"),
            QgsProcessing.SourceType.TypeVectorPoint))
        _hints(self, HINTS_1_06)

    def _process(self, parameters, context, feedback):
        feedback.pushInfo(_version_line())
        _saved = dict(parameters)
        before = self.parameterAsSource(parameters, self.BEFORE, context)
        after = self.parameterAsSource(parameters, self.AFTER, context)
        field = self.parameterAsString(parameters, self.FIELD, context) \
            or "ore_t"

        def _key_vals(src):
            d = {}
            for ft in src.getFeatures():
                try:
                    key = (ft["row"], ft["col"], ft["lay"]
                           if "lay" in [f.name() for f in src.fields()]
                           else 0)
                except KeyError:
                    key = None   # не except/continue: сканер даёт B112
                if key is None:
                    continue
                v = ft[field] if field in [f.name() for f in src.fields()] \
                    else None
                d[key] = (float(v) if v is not None else 0.0, ft.geometry())
            return d

        db = _key_vals(before)
        da = _key_vals(after)
        fields = QgsFields()
        for nm in ("row", "col", "lay"):
            fields.append(_field(nm, QVariant.Int))
        for nm in ("before", "after", "delta"):
            fields.append(_field(nm, QVariant.Double))
        sink, dest = self.parameterAsSink(
            parameters, self.OUTPUT, context, fields,
            QgsWkbTypes.Type.Point, before.sourceCrs())
        total_delta = 0.0
        for key, (vb, geom) in db.items():
            va = da.get(key, (0.0, None))[0]
            delta = vb - va
            total_delta += delta
            f = QgsFeature(fields)
            f.setGeometry(geom)
            f.setAttributes([int(key[0]), int(key[1]), int(key[2]),
                             vb, va, delta])
            sink.addFeature(f)
        feedback.pushInfo(
            _tr("Суммарное списание по полю %s: %.6g.") % (field, total_delta))
        _set_output_name(context, dest, self.tr("Разность (центроиды)"))
        _save_values(self, _saved)
        return {self.OUTPUT: dest}


class PolyhedralDemoAlgorithm(IsolinerAlgorithm):
    """Демо полиэдральной поверхности: тело пласта, куб или тетраэдр как
    нативный PolyhedralSurface Z (QGIS 3.40+) или TIN Z. На сборках до 3.40
    вывод деградирует до MultiPolygon Z с предупреждением. Задача - показать
    сам тип геометрии и проверить, что сборка QGIS и плагин QSFCGAL с ним
    работают."""

    EXAMPLE = "EXAMPLE"
    EXTENT = "EXTENT"
    NX = "NX"
    THICKNESS = "THICKNESS"
    BASE = "BASE"
    N_BEDS = "N_BEDS"
    AS_TIN = "AS_TIN"
    OUTPUT = "OUTPUT"

    _KINDS = ("bed", "suite", "cube", "tetra")

    def tr(self, s): return _tr(s)
    def createInstance(self): return PolyhedralDemoAlgorithm()
    def name(self): return "polyhedral_demo"

    def displayName(self):
        return self.tr("1.07 Создать пример данных (демо)")

    def helpUrl(self): return _help_url()
    def group(self): return self.tr(GROUP4)
    def groupId(self): return GROUP4_ID

    def shortHelpString(self):
        return _help_version(self.tr(
            "Создаёт демонстрационные данные, чтобы проверить показ "
            "на своей сборке QGIS, не трогая рабочие слои.\n\n"
            "Тела с высотой Z: тело пласта (водонепроницаемая оболочка "
            "из кровли, подошвы и боковой юбки), свита складчатых пластов "
            "(каждый грузится отдельным слоем и красится своим цветом), "
            "куб и тетраэдр. Плановое положение и размер берутся из "
            "охвата, по вертикали тело занимает от отметки залегания "
            "до отметки плюс мощность. Тип геометрии плоский, поэтому "
            "в 2D-виде Z не виден, диапазон печатается в журнал, а само "
            "тело удобно смотреть в окне Модули - Isoliner3D - "
            "3D-просмотр поверхностей, вкладка Тела. Нативный "
            "PolyhedralSurface Z доступен с QGIS 3.40, на более старых "
            "сборках вывод деградирует до MultiPolygon Z. Флаг TIN выдаёт "
            "триангулированную поверхность.\n\n"
            "Карта (растр для текстуры): трёхканальная картинка для "
            "проверки наложения текстуры на поверхность. Сделана нарочно "
            "проверочной: цветные поля пластов с кривой границей, тонкие "
            "изолинии, координатная сетка квадратными клетками и разные "
            "по цвету метки в четырёх углах (по часовой стрелке от левого "
            "верхнего: красная, зелёная, синяя, жёлтая). Наложение "
            "ошибается тремя типовыми способами, и каждый эта карта "
            "показывает сразу. Переворот по вертикали виден по меткам "
            "в углах, сдвиг и перекос по сетке, растяжение по одной оси "
            "по неквадратности клеток. Охват для карты лучше задавать "
            "полем «Карта: по охвату грида»: она ляжет ровно по границам "
            "поверхности."
        ) + _credit())

    def initAlgorithm(self, config=None):
        self._defaults = _load_defaults(self)
        self.addParameter(QgsProcessingParameterEnum(
            self.EXAMPLE, self.tr("Пример"),
            options=[self.tr("Тело пласта"),
                     self.tr("Свита (стопка складчатых пластов)"),
                     self.tr("Куб"), self.tr("Тетраэдр")],
            defaultValue=_dv(self, self.EXAMPLE, 0)))
        self.addParameter(QgsProcessingParameterExtent(
            self.EXTENT, self.tr("Охват (окно вида) - размещение и размер"),
            optional=True))
        self.addParameter(QgsProcessingParameterNumber(
            self.THICKNESS, self.tr("Мощность, ед. карты"),
            QgsProcessingParameterNumber.Type.Double,
            defaultValue=_dv(self, self.THICKNESS, 25.0), minValue=0.001))
        self.addParameter(QgsProcessingParameterNumber(
            self.NX, self.tr("Разбиение тела пласта (ячеек по стороне)"),
            QgsProcessingParameterNumber.Type.Integer,
            defaultValue=_dv(self, self.NX, 8), minValue=2, maxValue=80))
        self.addParameter(QgsProcessingParameterBoolean(
            self.AS_TIN, self.tr("Выдать как TIN (триангулировать)"),
            defaultValue=_dv(self, self.AS_TIN, False)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            self.BASE, self.tr("Отметка залегания (подошва), ед. карты"),
            QgsProcessingParameterNumber.Type.Double,
            defaultValue=_dv(self, self.BASE, 0.0))))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            self.N_BEDS, self.tr("Пластов в свите"),
            QgsProcessingParameterNumber.Type.Integer,
            defaultValue=_dv(self, self.N_BEDS, 3), minValue=2, maxValue=8)))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Тело (демо)"),
            QgsProcessing.SourceType.TypeVectorPolygon, optional=True))
        _hints(self, HINTS_1_07)

    @staticmethod
    def _resolve_wkb(*names):
        """Первый доступный enum QgsWkbTypes из перечисленных имён."""
        for nm in names:
            t = getattr(QgsWkbTypes, nm, None)
            if t is not None:
                return t, nm
        return None, None

    def _load_suite_layers(self, beds, crs, context, feedback):
        """Разносит пласты свиты по отдельным слоям в проекте (управление
        видимостью). Возвращает True при успехе. При любой проблеме с API
        загрузки возвращает False - вызывающий пишет свиту одним слоем."""
        try:
            from . import polyhedral as poly
            from qgis.core import QgsProcessingContext
            authid = crs.authid() if crs is not None else ""
            uri = "MultiPolygonZ" + (("?crs=%s" % authid) if authid else "")
            store = context.temporaryLayerStore()
            proj = QgsProject.instance()
            for k, bp in enumerate(beds, 1):
                g = QgsGeometry.fromWkt(
                    poly.patches_to_wkt(bp, "MULTIPOLYGON"))
                if g is None or g.isNull():
                    return False
                nm = self.tr("Свита: пласт %d") % k
                lyr = QgsVectorLayer(uri, nm, "memory")
                if not lyr.isValid():
                    return False
                pr = lyr.dataProvider()
                pr.addAttributes([_field("bed", QVariant.Int),
                                  _field("watertight", QVariant.Int)])
                lyr.updateFields()
                _ne, n_open = poly.edge_audit(bp)
                ft = QgsFeature(lyr.fields())
                ft.setGeometry(g)
                ft.setAttributes([k, 1 if n_open == 0 else 0])
                pr.addFeature(ft)
                lyr.updateExtents()
                store.addMapLayer(lyr)
                details = QgsProcessingContext.LayerDetails(nm, proj, nm)
                context.addLayerToLoadOnCompletion(lyr.id(), details)
            feedback.pushInfo(self.tr(
                "Свита загружена отдельными слоями по пласту: %d.")
                % len(beds))
            return True
        except Exception as e:
            feedback.pushInfo(self.tr(
                "Не удалось разнести свиту по слоям (%s) - вывод одним "
                "слоем.") % e)
            return False

    def _process(self, parameters, context, feedback):
        from . import polyhedral as poly
        feedback.pushInfo(_version_line())
        _saved = dict(parameters)
        idx = self.parameterAsEnum(parameters, self.EXAMPLE, context)
        kind = self._KINDS[idx]
        nx = self.parameterAsInt(parameters, self.NX, context)
        thickness = self.parameterAsDouble(parameters, self.THICKNESS, context)
        base = self.parameterAsDouble(parameters, self.BASE, context)
        n_beds = self.parameterAsInt(parameters, self.N_BEDS, context)
        as_tin = self.parameterAsBool(parameters, self.AS_TIN, context)

        # footprint берётся из охвата (окна вида); пустой охват - дефолт
        crs = QgsProject.instance().crs()
        ext = self.parameterAsExtent(parameters, self.EXTENT, context, crs)
        if ext is None or ext.isEmpty() or ext.width() <= 0 \
                or ext.height() <= 0:
            cx = cy = 0.0
            size = 200.0
        else:
            cx, cy = ext.center().x(), ext.center().y()
            size = min(ext.width(), ext.height())

        # общий вертикальный размах: подошва - base, кровля - base + мощность
        cz = base + thickness / 2.0
        x0, y0 = cx - size / 2.0, cy - size / 2.0

        # свита: пробуем разнести пласты по отдельным слоям (управление
        # видимостью); при неудаче API загрузки - свита одним слоем ниже
        if kind == "suite":
            beds = poly.suite_beds(
                n=n_beds, nx=nx, ny=nx, size=size, x0=x0, y0=y0,
                base=base, thickness=thickness)
            if as_tin:
                beds = [poly._triangulate(bp) for bp in beds]
            if self._load_suite_layers(beds, crs, context, feedback):
                allp = [p for bp in beds for p in bp]
                zmin, zmax = poly.z_range(allp)
                feedback.pushInfo(self.tr(
                    "Диапазон Z: %.3f .. %.3f (ед. карты).") % (zmin, zmax))
                _save_values(self, _saved)
                return {}
            wkt_kind = "TIN" if as_tin else "POLYHEDRALSURFACE"
            objs = []
            for k, bp in enumerate(beds, 1):
                _ne, n_open = poly.edge_audit(bp)
                objs.append(dict(patches=bp, name="suite_bed_%d" % k, bed=k,
                                 np=len(bp), watertight=(n_open == 0),
                                 open=n_open))
        else:
            if kind == "bed":
                patches, wkt_kind, meta = poly.build_example(
                    "bed", as_tin=as_tin, nx=nx, ny=nx, size=size,
                    x0=x0, y0=y0, base=base + thickness, thickness=thickness)
            elif kind == "cube":
                patches, wkt_kind, meta = poly.build_example(
                    "cube", as_tin=as_tin, cx=cx, cy=cy, cz=cz,
                    sx=size, sy=size, sz=thickness)
            else:  # tetra
                patches, wkt_kind, meta = poly.build_example(
                    "tetra", as_tin=as_tin, cx=cx, cy=cy, cz=cz, size=size)
            objs = [dict(patches=patches, name=meta["name"], bed=1,
                         np=meta["patches"], watertight=meta["watertight"],
                         open=meta["open_edges"])]

        # желаемый нативный тип, решаем по первому объекту
        if wkt_kind == "TIN":
            native_wkb, _nm = self._resolve_wkb("TINZ", "TinZ", "TIN")
        else:
            native_wkb, _nm = self._resolve_wkb(
                "PolyhedralSurfaceZ", "PolyhedralSurface")
        mpoly_wkb, _ = self._resolve_wkb("MultiPolygonZ")

        use_native = False
        if native_wkb is not None:
            g0 = QgsGeometry.fromWkt(
                poly.patches_to_wkt(objs[0]["patches"], wkt_kind))
            use_native = g0 is not None and not g0.isNull()
        if use_native:
            used_kind, used_wkb = wkt_kind, native_wkb
        else:
            used_kind, used_wkb = "MULTIPOLYGON", mpoly_wkb
            feedback.pushWarning(self.tr(
                "Нативный тип {0} на этой сборке недоступен - вывод как "
                "MultiPolygon Z. Нативный PolyhedralSurface / TIN и QSFCGAL "
                "доступны с QGIS 3.40.").format(wkt_kind))

        for o in objs:
            g = QgsGeometry.fromWkt(
                poly.patches_to_wkt(o["patches"], used_kind))
            if g is None or g.isNull():
                raise QgsProcessingException(self.tr(
                    "Не удалось собрать геометрию из WKT."))
            o["geom"] = g

        fields = QgsFields()
        fields.append(_field("name", QVariant.String))
        fields.append(_field("kind", QVariant.String))
        fields.append(_field("patches", QVariant.Int))
        fields.append(_field("watertight", QVariant.Int))
        fields.append(_field("bed", QVariant.Int))
        sink, dest = self.parameterAsSink(
            parameters, self.OUTPUT, context, fields, used_wkb, crs)
        if sink is None:
            raise QgsProcessingException(self.tr(
                "Не задан выходной слой. Укажите «Тело (демо)» "
                "(например, временный слой)."))

        for o in objs:
            f = QgsFeature(fields)
            f.setGeometry(o["geom"])
            f.setAttributes([o["name"], used_kind, int(o["np"]),
                             1 if o["watertight"] else 0, int(o["bed"])])
            sink.addFeature(f)

        titles = {
            "bed": self.tr("Пласт (демо)"),
            "suite": self.tr("Свита x%d (демо)") % n_beds,
            "cube": self.tr("Куб (демо)"),
            "tetra": self.tr("Тетраэдр (демо)"),
        }
        _set_output_name(context, dest, titles[kind])

        total_np = sum(o["np"] for o in objs)
        feedback.pushInfo(self.tr("Тип геометрии: %s Z.") % used_kind)
        if len(objs) > 1:
            feedback.pushInfo(self.tr("Объектов: %d, граней всего: %d.")
                              % (len(objs), total_np))
        else:
            feedback.pushInfo(self.tr("Граней: %d.") % total_np)
        allp = [p for o in objs for p in o["patches"]]
        zmin, zmax = poly.z_range(allp)
        feedback.pushInfo(self.tr("Диапазон Z: %.3f .. %.3f (ед. карты).")
                          % (zmin, zmax))
        n_open_total = sum(o["open"] for o in objs)
        if n_open_total == 0:
            feedback.pushInfo(self.tr("Оболочка замкнута (водонепроницаема)."))
        else:
            feedback.pushWarning(self.tr(
                "Оболочка НЕ замкнута: открытых рёбер %d.") % n_open_total)
        _save_values(self, _saved)
        return {self.OUTPUT: dest}


# --- 2. Топография -----------------------------------------------------


HINTS_2_02 = {
    "INPUT": "Слой проб. Отметка берётся из геометрии, из поля или "
             "считается от поверхности, это задаётся ниже.",
    "FIELD": "Числовое поле, значение которого раскладывается по кубу: "
             "содержание, концентрация, влажность. У демонстрационных "
             "данных из 2.01 это grade, а не hole: иначе куб выйдет "
             "по номерам скважин.",
    "ZSRC": "Плоский слой отдаёт нулевую Z у каждой точки. Если брать "
            "её из геометрии, все пробы лягут в одну плоскость и куб "
            "выйдет бессмысленным.",
    "ZFIELD": "Для отметки из поля это сама отметка, для глубины это "
              "глубина вниз от поверхности.",
    "ZSURF": "Грид, от которого отсчитывается глубина. Нужен почвенным "
             "и подобным пробам, где записана глубина, а не отметка.",
    "REF": "Кровля или подошва пласта. С ней вертикаль отсчитывается "
           "от поверхности, и интерполяция идёт вдоль напластования, "
           "а не поперёк. У пласта со складкой это меняет не точность "
           "на проценты, а осмысленность результата.",
    "REF_FLOOR": "Вторая поверхность. С ней отметка становится долей "
                 "мощности: ноль на кровле, единица на подошве. Так "
                 "сопоставляются пачки разной мощности, и раздув "
                 "не размазывает связь. Анизотропия тогда считается "
                 "по доле, а не по метрам.",
    "METHOD": "Ближний сосед даёт ступени и годится для проверки "
              "данных. Обратные расстояния дают сглаженное поле.",
    "CELL": "Ноль берёт пятую часть расстояния между точками плана. "
            "Мельче делать незачем: данных в промежутке всё равно нет, "
            "а число узлов растёт как квадрат.",
    "CELLZ": "Ноль берёт половину шага опробования. Крупнее значит "
             "слить соседние замеры и потерять различие по глубине.",
    "MAXPTS": "Ноль берёт на одного больше, чем замеров в одной точке "
              "плана. Больше значит смешать все уровни сразу "
              "и сгладить аномалию по глубине.",
    "ANISO": "Ноль замеряет вариограмму по данным и берёт отношение "
             "вертикальной длины связи к плановой. Это тот случай, "
             "когда гадать не нужно. Своё число задаёт масштаб "
             "вручную: большое сглаживает по вертикали, малое "
             "сохраняет различие по глубине.",
    "RADIUS": "Ноль берёт четверть охвата данных. Узел, где точек "
              "в радиусе не набралось, остаётся пропуском.",
    "POWER": "Чем больше степень, тем сильнее ближняя точка "
             "перевешивает дальние. Двойка это обычный выбор.",
    "MINPTS": "Узел, где точек в радиусе меньше этого числа, остаётся "
              "пропуском: пустота лучше выдуманного значения.",
    "SECTORS": "Ноль берёт от данных: у скважин деление нужно, иначе "
               "все соседи окажутся в одном стволе, а у проб в плане "
               "оно только рвёт поле. Граница сектора идёт лучом "
               "от узла, и на ней набор соседей меняется скачком: "
               "отсюда звёзды на почвенных пробах.",
    "OUTPUT": "Многоканальный грид: канал это горизонтальный уровень, "
              "отметка первого уровня и шаг пишутся в метаданные.",
}

HINTS_2_03 = {
    "CUBE": "Куб значений из 2.02: каналы это уровни, отметка первого "
            "уровня и шаг лежат в метаданных.",
    "USE_CUTOFF": "Без отсечки выгружаются все ячейки с данными, "
                  "с отсечкой только те, что не ниже её.",
    "CUTOFF": "Значение, ниже которого ячейка в модель не идёт. Работает,\n"
              "только когда отсечка включена галкой выше.",
    "CONTOUR": "Полигоны, за пределами которых ячейки не выгружаются: "
               "подсчётный блок, лицензионная площадь.",
    "TOPSURF": "Поверхность сверху: остаются точки ниже неё. Так "
               "отсекают всё выше дневного рельефа или выше кровли "
               "пласта.",
    "BOTSURF": "Поверхность снизу: остаются точки выше неё. Вместе "
               "с верхней остаётся только пласт.",
    "CLASSES": "На сколько интервалов разложить значение. Номер "
               "интервала пишется в поле cls и годится для окраски.",
    "DENS": "При заданной плотности к каждому блоку добавляется масса "
            "в полях dens и ore_t.",
    "OUTPUT": "Точка-центроид на занятую ячейку с размером блока, "
              "объёмом и значением.",
}

HINTS_2_04 = {
    "CUBE": "Куб значений из 2.02: каналы это уровни, отметка первого "
            "уровня и шаг лежат в метаданных.",
    "CUTOFF": "Ячейка не ниже отсечки считается телом. Отсечку для "
              "демонстрационных данных печатает 2.01.",
    "CONTOUR": "Полигоны, за пределами которых ячейки в тело не идут:\n"
               "подсчётный блок, лицензионная площадь.",
    "CLASSES": "Ноль строит одно тело. Несколько интервалов дают объект "
               "на каждый, и тело можно раскрасить по содержанию. "
               "Не читается, если заданы свои границы.",
    "EDGES": "Свои границы интервалов через пробел: 0 5 10 15. "
             "Задают разбивку вместо равных долей. Запятая внутри "
             "числа это знак дроби: 2,5 3 3,5 читается как два "
             "с половиной, три и три с половиной. Порядок и повторы "
             "не важны. Ячейка выше последней границы остаётся "
             "в последнем интервале, терять её нельзя.",
    "LABELS": "Названия интервалов через запятую: низкое, среднее, "
              "высокое. Пишутся в поле name. Недостающие остаются "
              "пустыми, лишние отбрасываются.",
    "MERGE": "Слияние делает слой в разы легче, но рвёт границу тела "
             "Т-образными стыками. Такое тело нельзя ни посчитать "
             "по объёму, ни разрезать в сцене: срез останется "
             "открытым, крышку поставить не на что. Для подсчёта "
             "и для разрезов флаг снимайте.",
    "UNPINCH": "Защип это касание двух ячеек одной диагональю. Дырой он "
               "не является, но ребро в нём принадлежит четырём граням, "
               "и проверка замкнутости такое тело отвергает.",
    "OUTPUT": "MULTIPOLYGON Z, объект на интервал окраски. Поля cls,\n"
              "vmin, vmax, faces и shell.",
}

HINTS_1_01 = {
    "ROOF": "Грид кровли пласта. Отметки в метрах, шаг и охват должны "
            "совпадать с подошвой: иначе мощность считать не по чему.",
    "BOTTOM": "Грид подошвы. Там, где подошва выше кровли, мощность "
              "выходит отрицательной и ячейка уходит в пропуск.",
    "PARAMS": "Дополнительные гриды, которые лягут отдельными каналами: "
              "содержание, плотность, домен. Берётся первый канал "
              "каждого.",
    "ROOF_BAND": "Канал кровли в исходном гриде. Нужен, когда кровля "
                 "лежит не первым каналом, а внутри многоканального.",
    "BOTTOM_BAND": "Канал подошвы в исходном гриде. Нужен, когда "
                   "подошва лежит внутри многоканального.",
    "OUTPUT": "Многоканальный грид: канал 1 кровля, канал 2 подошва, "
              "дальше параметры. Этот порядок читают все остальные "
              "инструменты и окно просмотра.",
}

HINTS_1_02 = {
    "BED": "Грид пласта из 1.01. Первый канал кровля, второй подошва, "
           "по ним и считается мощность.",
    "CONTENT_BAND": "Канал содержания. Пусто означает считать только "
                    "объём и мощность, без запасов.",
    "DENSITY": "Плотность руды. На неё умножается объём, чтобы получить "
               "массу: без неё в отчёте будут кубометры, а не тонны.",
    "CONTOUR": "Полигоны, за пределами которых ячейки в подсчёт "
               "не идут: подсчётный блок, лицензионная площадь.",
    "OUTPUT": "Тот же грид пласта с добавленными каналами мощности "
              "и запасов на ячейку.",
    "REPORT": "Сводка по контуру: площадь, объём, масса, среднее "
              "содержание. Открывается в браузере.",
}

HINTS_1_03 = {
    "BED": "Грид пласта из 1.01. Колонка между кровлей и подошвой "
           "делится на блоки.",
    "DENSITY": "Плотность руды, если её нет отдельным каналом. "
               "На неё умножается объём блока.",
    "DENS_BAND": "Канал плотности в гриде. Пусто означает брать одно "
                 "значение, заданное выше, на весь пласт.",
    "CONTOUR": "Полигоны, за пределами которых блоки не выгружаются: "
               "подсчётный блок, лицензионная площадь.",
    "NZ": "На сколько блоков делить колонку по вертикали. Один блок "
          "даёт модель без вертикальной разбивки, а мощность пласта "
          "тогда вся уходит в один слой.",
    "OUTPUT": "Точка-центроид на блок с размером, объёмом и массой. "
              "Дальше работает обычный векторный аппарат QGIS.",
}

HINTS_1_04 = {
    "GRIDS": "Гриды, которые надо отдать мешем. Каждый становится "
             "отдельным файлом 2DM.",
    "ZSCALE": "Вертикальное преувеличение. Пласт в метр на площади "
              "в километр без него не разглядеть, но объём по такому "
              "мешу считать уже нельзя.",
    "ZOFFSET": "Сдвиг всех отметок по вертикали. Нужен, чтобы разнести "
               "пласты свиты и увидеть их по отдельности.",
    "STEP": "Прореживание узлов. Каждый второй узел это вчетверо "
            "меньше треугольников, а форма пласта на глаз та же.",
    "SPACING": "Разнос поверхностей по вертикали. Пласты свиты иначе "
               "лежат вплотную и спорят за глубину.",
    "ZBAND": "Канал отметок в гриде. Для грида пласта это кровля "
             "или подошва, смотря что показывать.",
    "FOLDER": "Куда положить файлы. Имя файла берётся от имени грида.",
}

HINTS_1_05 = {
    "BED": "Грид пласта, к которому добавится канал домена.",
    "DOMAINS": "Полигоны доменов: сорта руды, участки, зоны. Ячейка "
               "получает код того домена, внутрь которого попала.",
    "FIELD": "Числовое поле с кодом домена. Пусто означает нумеровать "
             "полигоны по порядку.",
    "OUTPUT": "Тот же грид с добавленным каналом domain. Дальше по нему "
              "фильтруют подсчёт и красят сцену.",
}

HINTS_1_06 = {
    "BEFORE": "Блочная модель на начало периода. Сравнение идёт "
              "по совпадающим блокам, поэтому обе модели должны быть "
              "собраны на одной сетке.",
    "AFTER": "Блочная модель на конец периода. Блок, которого в ней "
             "нет, считается отработанным целиком.",
    "FIELD": "Поле запаса, разность которого считается: масса, объём, "
             "металл.",
    "OUTPUT": "Центроиды с разностью по каждому блоку. Сумма поля "
              "по слою и есть списание за период.",
}

HINTS_1_07 = {
    "EXAMPLE": "Что именно создать: тело пласта, свиту складчатых "
               "пластов, куб или тетраэдр. Карта для текстуры вынесена "
               "в отдельный инструмент 1.08.",
    "EXTENT": "Куда положить пример и какого размера. Пусто означает "
              "взять охват окна вида.",
    "THICKNESS": "Мощность пласта в единицах карты. От неё зависит, "
                 "видно ли тело при обычном вертикальном масштабе.",
    "NX": "На сколько ячеек делится сторона тела. Мельче значит "
          "плавнее форма и больше треугольников.",
    "AS_TIN": "Триангулировать тело. Без этого выходят четырёхугольные "
              "грани, которые не всякий просмотрщик покажет.",
    "BASE": "Отметка подошвы. Свита строится вверх от неё.",
    "N_BEDS": "Сколько пластов в свите. Каждый ложится своим телом "
              "со своим содержанием.",
    "OUTPUT": "Слой с телами: полигоны с Z, годные для сцены и для "
              "подсчёта объёма.",
}


HINTS_2_01 = {
    "KIND": "Пласт со складкой и падением показывает главное: "
            "горизонтальные уровни куба режут залежь поперёк. Линза "
            "изотропна и проще всех, жила это обратный крайний случай.",
    "HOLES": "Сеть строится со сбивкой, а не правильной сеткой: "
             "правильная даёт интерполяции слишком лёгкую задачу.",
    "SAMPLE": "Проба длиннее мощности залежи пропустит её между "
              "замерами. На пласте в двадцать шесть метров десять "
              "метров это уже много.",
    "EXTENT": "Площадка, на которой ставятся скважины. Пусто означает "
              "километр от начала координат, об этом пишется в журнал.",
    "TOP": "Средняя отметка дневной поверхности. Устья ставятся "
           "по пологому рельефу вокруг неё.",
    "DEPTH": "Глубина разбуривания вниз от поверхности. Пропорции тела "
             "считаются от неё же.",
    "NOISE": "Доля логнормального шума опробования. Ноль даёт данные "
             "без шума, на них видно саму модель.",
    "SEED": "Одно и то же зерно даёт одни и те же данные: с ним можно "
            "сравнивать методы на неизменной выборке.",
    "CORE": "Содержание в ядре сверх фона. Граница тела проходит там, "
            "где содержание падает до половины от него.",
    "BACK": "Фон во вмещающих породах. От него и от содержания в ядре\n"
            "считается отсечка, которой отделяется тело.",
    "TREND": "Общий наклон содержаний по площадке. Нужен, чтобы данные "
             "не сводились к одному телу.",
    "SHORT": "Доля недобуренных скважин. Нужна, чтобы у куба были "
             "места без данных, как на настоящей разведке.",
    "INCLINE": "Наклон стволов от вертикали. Ноль даёт вертикальные "
               "скважины.",
    "OUTPUT": "Пробы с полями hole, from_m, to_m, grade, truth, zone.",
}


class Demo3DPointsAlgorithm(IsolinerAlgorithm):
    """Демонстрационные скважины с опробованием по интервалам.

    Данные с известной истиной внутри: содержание задано моделью,
    шум добавляется отдельно. На таких точках сравнивают методы
    объёмной интерполяции, потому что ошибку считают по расхождению
    с заложенной моделью, а не на глаз.

    Типов залежи три. Пласт со складкой и падением показывает главное:
    горизонтальные уровни куба режут залежь поперёк. Линза даёт простой
    случай, крутая жила - обратный крайний.
    """

    KIND = "KIND"
    HOLES = "HOLES"
    SAMPLE = "SAMPLE"
    EXTENT = "EXTENT"
    TOP = "TOP"
    DEPTH = "DEPTH"
    CORE = "CORE"
    BACK = "BACK"
    TREND = "TREND"
    NOISE = "NOISE"
    INCLINE = "INCLINE"
    SHORT = "SHORT"
    SEED = "SEED"
    OUTPUT = "OUTPUT"

    def name(self):
        return "demo_points_3d"

    def displayName(self):
        return self.tr("2.01 Демонстрационные скважины в объёме")

    def group(self):
        return self.tr(GROUP5)

    def groupId(self):
        return GROUP5_ID

    def helpUrl(self):
        return _help_url()

    def shortHelpString(self):
        return _help_version(self.tr(
            "Создаёт скважины с опробованием по интервалам: сеть со "
            "сбивкой, разная глубина, часть скважин недобурена, устья "
            "по рельефу.\n\nТип залежи задаёт геометрию тела. Пласт со "
            "складкой и падением нужен, чтобы увидеть, как уровни куба "
            "режут залежь поперёк. Линза изотропна и проще всех. Крутая "
            "жила проверяет обратный случай, когда тело почти "
            "вертикально.\n\nПоля: hole (номер скважины), from_m и to_m "
            "(интервал пробы от устья вниз), grade (содержание с шумом), "
            "truth (содержание по модели, без шума), zone (единица "
            "внутри тела).\n\nШум логнормальный, отрицательных "
            "содержаний не возникает. Граница тела проходит там, где "
            "содержание падает до половины ядра над фоном - это и есть "
            "отсечка, она печатается в журнал.")
            + _credit())

    def createInstance(self):
        return Demo3DPointsAlgorithm()

    def initAlgorithm(self, config=None):
        self._defaults = _load_defaults(self)
        self.addParameter(QgsProcessingParameterEnum(
            self.KIND, self.tr("Тип залежи"),
            options=[self.tr("Пласт со складкой и падением"),
                     self.tr("Линза"),
                     self.tr("Крутая жила")],
            defaultValue=_dv(self, self.KIND, 0)))
        self.addParameter(QgsProcessingParameterNumber(
            self.HOLES, self.tr("Скважин"),
            QgsProcessingParameterNumber.Type.Integer,
            defaultValue=_dv(self, self.HOLES, 25),
            minValue=2, maxValue=2000))
        self.addParameter(QgsProcessingParameterNumber(
            self.SAMPLE, self.tr("Длина пробы, м"),
            QgsProcessingParameterNumber.Type.Double,
            defaultValue=_dv(self, self.SAMPLE, 3.0), minValue=0.05))
        self.addParameter(QgsProcessingParameterExtent(
            self.EXTENT, self.tr("Охват площадки"),
            optional=True))
        self.addParameter(QgsProcessingParameterNumber(
            self.TOP, self.tr("Отметка поверхности, м"),
            QgsProcessingParameterNumber.Type.Double,
            defaultValue=_dv(self, self.TOP, 0.0)))
        self.addParameter(QgsProcessingParameterNumber(
            self.DEPTH, self.tr("Глубина разбуривания, м"),
            QgsProcessingParameterNumber.Type.Double,
            defaultValue=_dv(self, self.DEPTH, 200.0), minValue=1.0))
        self.addParameter(QgsProcessingParameterNumber(
            self.NOISE, self.tr("Шум опробования, доля"),
            QgsProcessingParameterNumber.Type.Double,
            defaultValue=_dv(self, self.NOISE, 0.12),
            minValue=0.0, maxValue=2.0))
        self.addParameter(QgsProcessingParameterNumber(
            self.SEED, self.tr("Зерно случайности"),
            QgsProcessingParameterNumber.Type.Integer,
            defaultValue=_dv(self, self.SEED, 1)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            self.CORE, self.tr("Содержание в ядре сверх фона"),
            QgsProcessingParameterNumber.Type.Double,
            defaultValue=_dv(self, self.CORE, 8.0), minValue=0.001)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            self.BACK, self.tr("Фон во вмещающих породах"),
            QgsProcessingParameterNumber.Type.Double,
            defaultValue=_dv(self, self.BACK, 0.3), minValue=0.0)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            self.TREND, self.tr("Общий наклон содержаний, доля"),
            QgsProcessingParameterNumber.Type.Double,
            defaultValue=_dv(self, self.TREND, 0.15),
            minValue=0.0, maxValue=2.0)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            self.SHORT, self.tr("Доля недобуренных скважин"),
            QgsProcessingParameterNumber.Type.Double,
            defaultValue=_dv(self, self.SHORT, 0.15),
            minValue=0.0, maxValue=0.9)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            self.INCLINE, self.tr("Наклон стволов, градусов"),
            QgsProcessingParameterNumber.Type.Double,
            defaultValue=_dv(self, self.INCLINE, 0.0),
            minValue=0.0, maxValue=60.0)))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Пробы с содержаниями"),
            QgsProcessing.SourceType.TypeVectorPoint))

        _hints(self, HINTS_2_01)

    def _process(self, parameters, context, feedback):
        from qgis.core import (QgsFields, QgsFeature, QgsGeometry,
                               QgsPoint, QgsWkbTypes)
        from . import demo3d

        feedback.pushInfo(_version_line())
        _saved = dict(parameters)
        kind = demo3d.KINDS[self.parameterAsEnum(
            parameters, self.KIND, context)]
        holes = self.parameterAsInt(parameters, self.HOLES, context)
        sample = self.parameterAsDouble(parameters, self.SAMPLE, context)
        ext = self.parameterAsExtent(parameters, self.EXTENT, context)
        if ext is not None and not ext.isEmpty():
            x0, y0 = ext.xMinimum(), ext.yMinimum()
            w, h = ext.width(), ext.height()
        else:
            # Инструмент демонстрационный, и требовать охват до первого
            # запуска незачем: даём километр от начала координат
            # и говорим об этом в журнале.
            x0 = y0 = 0.0
            w = h = 1000.0
            feedback.pushInfo(self.tr(
                "Площадка по умолчанию: %.0f x %.0f м от начала "
                "координат. Задайте охват, чтобы положить пример "
                "на своё место.") % (w, h))
        top = self.parameterAsDouble(parameters, self.TOP, context)
        depth = self.parameterAsDouble(parameters, self.DEPTH, context)
        core = self.parameterAsDouble(parameters, self.CORE, context)
        back = self.parameterAsDouble(parameters, self.BACK, context)
        trend = self.parameterAsDouble(parameters, self.TREND, context)
        noise = self.parameterAsDouble(parameters, self.NOISE, context)
        incline = self.parameterAsDouble(parameters, self.INCLINE, context)
        short = self.parameterAsDouble(parameters, self.SHORT, context)
        seed = self.parameterAsInt(parameters, self.SEED, context)

        model = demo3d.make_model(kind, x0, y0, w, h, top, depth,
                                  core=core, back=back)
        rng = np.random.RandomState(seed)
        xs, ys, collar, length = demo3d.hole_layout(
            model, holes, rng, short_share=short)
        feedback.setProgress(15)
        if feedback.isCanceled():
            return {self.OUTPUT: None}
        data = demo3d.hole_samples(model, xs, ys, collar, length, rng,
                                   sample=sample, noise=noise,
                                   incline=incline, trend=trend)
        feedback.setProgress(55)

        fields = QgsFields()
        fields.append(_field("hole", QVariant.Int))
        fields.append(_field("from_m", QVariant.Double))
        fields.append(_field("to_m", QVariant.Double))
        fields.append(_field("grade", QVariant.Double))
        fields.append(_field("truth", QVariant.Double))
        fields.append(_field("zone", QVariant.Int))
        sink, dest = self.parameterAsSink(
            parameters, self.OUTPUT, context, fields,
            QgsWkbTypes.Type.PointZ, context.project().crs())
        if sink is None:
            raise QgsProcessingException(
                self.tr("Не удалось создать слой проб."))

        total = int(data["hole"].size)
        step = max(total // 40, 1)
        for i in range(total):
            if feedback.isCanceled():
                break
            ft = QgsFeature(fields)
            ft.setGeometry(QgsGeometry(QgsPoint(
                float(data["x"][i]), float(data["y"][i]),
                float(data["z"][i]))))
            ft.setAttributes([int(data["hole"][i]),
                              float(data["from_m"][i]),
                              float(data["to_m"][i]),
                              float(data["grade"][i]),
                              float(data["truth"][i]),
                              int(data["zone"][i])])
            sink.addFeature(ft)
            if i % step == 0:
                feedback.setProgress(55 + 45.0 * i / max(total, 1))
        _set_output_name(context, dest, self.tr("Пробы с содержаниями"))

        cut = demo3d.cutoff_for(model)
        in_zone = int(data["zone"].sum())
        feedback.pushInfo(self.tr("Скважин: %d, проб: %d, длина пробы %.2f м.")
                          % (int(xs.size), total, sample))
        feedback.pushInfo(self.tr("Площадка: %.0f x %.0f м от (%.0f, %.0f).")
                          % (w, h, x0, y0))
        feedback.pushInfo(self.tr("Устья: %.1f .. %.1f м, забои: %.1f .. "
                                  "%.1f м.")
                          % (float(collar.min()), float(collar.max()),
                             float((collar - length).min()),
                             float((collar - length).max())))
        feedback.pushInfo(self.tr("Содержание: %.3f .. %.3f, отсечка %.3f.")
                          % (float(data["grade"].min()),
                             float(data["grade"].max()), cut))
        feedback.pushInfo(self.tr("Проб внутри тела: %d из %d.")
                          % (in_zone, total))
        # Расшифровка полей нужна там, где данные только что созданы:
        # по именам не видно, какое поле содержание, а какое номер
        # скважины, и в 2.02 подставляется первое числовое.
        feedback.pushInfo(self.tr(
            "Поля слоя: hole номер скважины, from_m и to_m интервал "
            "пробы от устья вниз, grade содержание с шумом, truth "
            "содержание по модели без шума, zone единица внутри "
            "тела.\nДля интерполяции берите grade. Поле truth нужно, "
            "чтобы отделить ошибку метода от шума опробования, "
            "а hole - чтобы исключать скважину целиком в 2.05."))
        if total > 2000:
            feedback.pushWarning(self.tr(
                "Проб много: интерполяция в объёме считает узел по всем "
                "пробам, и время растёт с их числом. Увеличьте длину "
                "пробы или уменьшите число скважин."))
        if in_zone == 0:
            feedback.pushWarning(self.tr(
                "Ни одна проба не попала в тело: проверьте глубину "
                "разбуривания и охват площадки."))
        _save_values(self, _saved)
        return {self.OUTPUT: dest}


HINTS_2_07 = {
    "INPUT": "Точки замеров: скважинные пробы, интервалы, что угодно "
             "с отметкой и значением.",
    "FIELD": "Поле со значением, которое раскладывается по объёму.",
    "ZSRC": "Откуда брать отметку пробы: из высоты геометрии, "
            "из поля или как глубину от поверхности.",
    "ZFIELD": "Поле отметки либо глубины, если она не в геометрии.",
    "ZSURF": "Поверхность, от которой отсчитывается глубина.",
    "OUTPUT": "Многоканальный грид: канал это горизонтальный уровень "
              "куба. Его читают 2.03, 2.04 и сцена.",
    "GRID": "Начальная решётка по плану: с неё метод начинает и дальше "
            "удваивает её на каждом уровне. Мельче начальная - точнее "
            "первое приближение, но и памяти больше.",
    "GRIDZ": "Начальная решётка по вертикали. Разведочные данные "
             "вытянуты, и решётка не обязана быть кубической: "
             "километры в плане и метры по мощности это разные вещи. "
             "Меньшее число здесь и растягивает влияние вдоль пласта, "
             "и бережёт память.",
    "LEVELS": "Сколько раз удваивать решётку. Каждый уровень "
              "подхватывает то, что не смог предыдущий: невязка падает "
              "быстро, а память последнего уровня растёт кубом.",
    "TOL": "Остановка по невязке: как только наибольшее отклонение "
           "от замеров опустится ниже, уровни дальше не строятся. "
           "Ноль означает строить все.",
    "CELL": "Шаг куба по горизонтали. Ноль берёт от сети опробования.",
    "CELLZ": "Шаг куба по вертикали. Ноль берёт от сети.",
    "VMIN": "Наименьшее возможное значение: содержание не бывает ниже "
            "нуля, а метод за диапазон выходит. Что вышло, прижимается "
            "к краю, и на месте выброса получается плато - форма там "
            "теряется. Оставьте пустым, если ограничения нет.",
    "VMAX": "Наибольшее возможное значение. Число прижатых узлов "
            "печатается в журнал: по нему видно, годится ли модель.",
}


class Interp3DAlgorithm(IsolinerAlgorithm):
    """Интерполяция точек в объёме: куб значений многоканальным гридом.

    Канал это горизонтальный уровень, отметка первого уровня и шаг
    пишутся в метаданные. Конвенция та же, что у блочной модели,
    поэтому куб сразу читается остальными инструментами и показывается
    изоповерхностью в окне просмотра.

    Методы пока два, ближний сосед и обратные расстояния. Кригинг
    встанет третьим в ту же обвязку.
    """

    def name(self):
        return "interpolate_3d"

    def displayName(self):
        return self.tr("2.02 Интерполяция точек в объёме")

    def group(self):
        return self.tr(GROUP5)

    def groupId(self):
        return GROUP5_ID

    def shortHelpString(self):
        return self.tr(
            "Считает значение в узлах объёмной сетки по точкам "
            "с высотой.\n\n"
            "Анизотропия это отношение вертикального масштаба "
            "к горизонтальному. Без неё ближайшей точкой окажется "
            "соседняя скважина, а не соседний замер в той же точке "
            "плана.\n\n"
            "Узлы, где точек в радиусе меньше нужного, остаются "
            "пропуском: пустота лучше выдуманного значения.\n\n"
            "Соседи набираются по секторам: окружность вокруг узла "
            "делится на равные части, и из каждой берётся своя доля "
            "ближайших точек. Без этого при анизотропии все соседи "
            "оказываются в одной скважине, потому что проба в стволе "
            "в сотни раз ближе соседней скважины, и обратные "
            "расстояния вырождаются в ближайшего соседа. Один сектор "
            "отключает деление.\n\n"
            "Источник отметки задаётся отдельно. Плоский слой отдаёт "
            "нулевую Z у каждой точки, поэтому брать её из геометрии "
            "нельзя: все пробы легли бы в одну плоскость. Поле отметки "
            "годится, когда отметка посчитана, а глубина от поверхности "
            "нужна пробам, где записана глубина, а не отметка. Точка, "
            "для которой отметку получить не удалось, в расчёт не идёт, "
            "и число таких пишется в журнал."
        )

    def createInstance(self):
        return Interp3DAlgorithm()

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            "INPUT", self.tr("Точки с высотой"),
            [QgsProcessing.SourceType.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterField(
            "FIELD", self.tr("Поле значения"),
            parentLayerParameterName="INPUT",
            type=QgsProcessingParameterField.DataType.Numeric))
        self.addParameter(QgsProcessingParameterEnum(
            "ZSRC", self.tr("Источник отметки"),
            options=[self.tr("Высота геометрии (Z)"),
                     self.tr("Поле отметки"),
                     self.tr("Глубина от поверхности")],
            defaultValue=0))
        self.addParameter(QgsProcessingParameterField(
            "ZFIELD", self.tr("Поле отметки или глубины"),
            parentLayerParameterName="INPUT", optional=True,
            type=QgsProcessingParameterField.DataType.Numeric))
        self.addParameter(QgsProcessingParameterRasterLayer(
            "ZSURF", self.tr("Поверхность для отсчёта глубины"),
            optional=True))
        self.addParameter(QgsProcessingParameterEnum(
            "METHOD", self.tr("Метод"),
            options=[self.tr("Ближний сосед"),
                     self.tr("Обратные расстояния")], defaultValue=1))
        # Ноль означает «взять от данных». Постоянные умолчания
        # не подходят никому: на почвенных пробах через триста метров
        # шаг в двадцать пять метров мельче самих данных, а на площадке
        # в двадцать семь километров он даёт сорок пять миллионов узлов.
        self.addParameter(QgsProcessingParameterNumber(
            "CELL", self.tr("Шаг по горизонтали, м (0 - от данных)"),
            QgsProcessingParameterNumber.Type.Double, defaultValue=0.0,
            minValue=0.0))
        self.addParameter(QgsProcessingParameterNumber(
            "CELLZ", self.tr("Шаг по вертикали, м (0 - от данных)"),
            QgsProcessingParameterNumber.Type.Double, defaultValue=0.0,
            minValue=0.0))
        self.addParameter(QgsProcessingParameterNumber(
            "MAXPTS", self.tr("Наибольшее число точек (0 - от данных)"),
            QgsProcessingParameterNumber.Type.Integer, defaultValue=0,
            minValue=0))
        # Ниже настройка самого метода. К исходным данным она отношения
        # не имеет, и в основном списке только мешает выбирать.
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            "ANISO", self.tr("Анизотропия (0 - от данных)"),
            QgsProcessingParameterNumber.Type.Double, defaultValue=20.0,
            minValue=0.0)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            "RADIUS", self.tr("Радиус поиска, м (0 - авто)"),
            QgsProcessingParameterNumber.Type.Double, defaultValue=0.0,
            minValue=0.0)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            "POWER", self.tr("Степень обратных расстояний"),
            QgsProcessingParameterNumber.Type.Double, defaultValue=2.0,
            minValue=0.1, maxValue=10.0)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            "MINPTS", self.tr("Наименьшее число точек"),
            QgsProcessingParameterNumber.Type.Integer, defaultValue=1,
            minValue=1)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            "SECTORS", self.tr("Секторов поиска (0 - от данных)"),
            QgsProcessingParameterNumber.Type.Integer, defaultValue=0,
            minValue=0, maxValue=32)))
        self.addParameter(QgsProcessingParameterRasterDestination(
            "OUTPUT", self.tr("Куб значений")))

        _hints(self, HINTS_2_02)

    def _process(self, parameters, context, feedback):
        import numpy as np
        from .interp3d import (interpolate, grid_nodes, sampling_spacing,
                               grid_advice, auto_grid, auto_sectors)
        from .flatten import to_flat, flat_span
        from .variogram import auto_fit, assemble

        src = self.parameterAsSource(parameters, "INPUT", context)
        method = ("nearest", "idw")[
            self.parameterAsEnum(parameters, "METHOD", context)]
        cell = self.parameterAsDouble(parameters, "CELL", context)
        cellz = self.parameterAsDouble(parameters, "CELLZ", context)
        aniso = self.parameterAsDouble(parameters, "ANISO", context)
        radius = self.parameterAsDouble(parameters, "RADIUS", context)
        power = self.parameterAsDouble(parameters, "POWER", context)
        maxp = self.parameterAsInt(parameters, "MAXPTS", context)
        minp = self.parameterAsInt(parameters, "MINPTS", context)
        sectors = self.parameterAsInt(parameters, "SECTORS", context)
        out_path = self.parameterAsOutputLayer(parameters, "OUTPUT",
                                               context)
        xs, ys, zs, vals = _read_samples(self, parameters, context,
                                         feedback)
        net = sampling_spacing(np.column_stack([xs, ys, zs]))
        auto = auto_grid(*net) if net else None
        # Ноль в поле означает «взять от данных». Что подставили,
        # печатается: иначе непонятно, почему сетка вышла такой.
        if sectors <= 0:
            sectors = auto_sectors(net[2] if net else None)
            feedback.pushInfo(self.tr(
                "Секторов поиска от данных: %d.") % sectors)
        if cell <= 0:
            cell = auto["cell"] if auto else 25.0
            feedback.pushInfo(self.tr("Шаг по горизонтали от данных: "
                                      "%.1f м.") % cell)
        if cellz <= 0:
            cellz = auto["cellz"] if auto else 5.0
            feedback.pushInfo(self.tr("Шаг по вертикали от данных: "
                                      "%.2f м.") % cellz)
        if maxp <= 0:
            maxp = auto["max_points"] if auto else 16
            feedback.pushInfo(self.tr("Наибольшее число точек "
                                      "от данных: %d.") % maxp)
        if net is not None:
            dz_n, dxy_n, per_n = net
            feedback.pushInfo(self.tr(
                "Сеть: шаг по вертикали %.2f м, шаг в плане %.0f м, "
                "замеров в одной точке плана %d.")
                % (dz_n, dxy_n, per_n))
            feedback.pushInfo(self.tr(
                "Анизотропия сжимает вертикаль: большая сглаживает "
                "по вертикали, малая сохраняет различие по глубине. "
                "Сейчас %.3f.") % aniso)
            if maxp > per_n > 1:
                feedback.pushWarning(self.tr(
                    "Наибольшее число точек %d, а замеров в одной "
                    "точке плана всего %d. В среднее попадут все "
                    "уровни сразу, и различие по глубине сгладится. "
                    "Поставьте не больше %d.")
                    % (maxp, per_n, per_n + 1))
        if len(set(np.round(zs, 6).tolist())) < 2:
            raise QgsProcessingException(self.tr(
                "Все точки на одной отметке: куб не построить. "
                "Проверьте источник отметки."))

        pts = np.column_stack([xs, ys, zs])
        vals = np.asarray(vals, dtype=float)
        pad = cell
        x0, x1 = pts[:, 0].min() - pad, pts[:, 0].max() + pad
        y0, y1 = pts[:, 1].min() - pad, pts[:, 1].max() + pad
        z0, z1 = pts[:, 2].min() - cellz, pts[:, 2].max() + cellz
        nx = max(int(np.ceil((x1 - x0) / cell)), 1)
        ny = max(int(np.ceil((y1 - y0) / cell)), 1)
        nz = max(int(np.ceil((z1 - z0) / cellz)) + 1, 1)
        feedback.pushInfo(self.tr("Сетка: %d x %d x %d, узлов %d")
                          % (nx, ny, nz, nx * ny * nz))
        for note in grid_advice(nx, ny, nz, cell,
                                net[1] if net else None):
            feedback.pushWarning(self.tr("Сетка: %s.") % note)

        # Спрямление: вертикаль отсчитывается от опорной поверхности.
        # Пробы и узлы переводятся одинаково, а сетка остаётся
        # в настоящих отметках, поэтому куб читается всем прочим.
        ref = self.parameterAsRasterLayer(parameters, "REF", context)
        ref_fl = self.parameterAsRasterLayer(parameters, "REF_FLOOR",
                                             context)
        roof_a = roof_gt = floor_a = None
        if ref is not None:
            roof_a, roof_gt = _read_surface(ref)
            if roof_a is None:
                raise QgsProcessingException(self.tr(
                    "Опорная поверхность не открылась."))
            if ref_fl is not None:
                floor_a, _gt2 = _read_surface(ref_fl)
                if floor_a is None or floor_a.shape != roof_a.shape:
                    raise QgsProcessingException(self.tr(
                        "Подошва не открылась либо не совпадает "
                        "с кровлей по сетке."))
            fz = to_flat(pts[:, 0], pts[:, 1], pts[:, 2], roof_a,
                         roof_gt, floor=floor_a)
            keep = np.isfinite(fz)
            if int(keep.sum()) < 2:
                raise QgsProcessingException(self.tr(
                    "Опорная поверхность не покрывает пробы."))
            if int(keep.sum()) < len(fz):
                feedback.pushWarning(self.tr(
                    "Вне опорной поверхности пропущено проб: %d.")
                    % int((~keep).sum()))
            span = flat_span(pts[:, 0], pts[:, 1], pts[:, 2], roof_a,
                             roof_gt, floor=floor_a)
            if span:
                feedback.pushInfo(self.tr(
                    "Спрямление: размах отметки %.2f, был %.2f м, "
                    "спрямлено проб %d.") % span)
            pts = np.column_stack([pts[keep, 0], pts[keep, 1],
                                   fz[keep]])
            vals = vals[keep]

        if aniso <= 0:
            # Отношение длин связи в плане и по вертикали и есть
            # анизотропия. Меряется после спрямления: в тех же
            # координатах, в которых пойдёт расчёт.
            plan = auto_fit(pts, vals, nlags=12, direction="plan")
            vert = auto_fit(pts, vals, nlags=12, direction="vert")
            vm = assemble(plan, vert, float(np.var(vals)))
            aniso = vm["anisotropy"]
            feedback.pushInfo(self.tr(
                "Вариограмма: длина связи в плане %.0f, по вертикали "
                "%.1f, анизотропия %.4f.")
                % (plan["range"], vert["range"], aniso))
            if not np.isfinite(aniso) or aniso <= 0:
                aniso = 1.0
                feedback.pushWarning(self.tr(
                    "Анизотропию замерить не удалось, взята единица."))

        nodes = grid_nodes(x0, y1, z0, nx, ny, nz, cell, cell, cellz)
        vol = np.full(nx * ny * nz, np.nan)
        step = max(nz // 20, 1)
        per_level = nx * ny
        for k in range(nz):
            if feedback.isCanceled():
                break
            a, b = k * per_level, (k + 1) * per_level
            here = nodes[a:b]
            if roof_a is not None:
                nz_f = to_flat(here[:, 0], here[:, 1], here[:, 2],
                               roof_a, roof_gt, floor=floor_a)
                here = np.column_stack([here[:, 0], here[:, 1], nz_f])
            vol[a:b] = interpolate(
                pts, vals, here, method=method,
                radius=(radius if radius > 0 else None), anisotropy=aniso,
                power=power, max_points=maxp, min_points=minp,
                sectors=sectors)
            if k % step == 0:
                feedback.setProgress(100.0 * k / max(nz, 1))
        vol = vol.reshape(nz, ny, nx)

        filled = int(np.isfinite(vol).sum())
        feedback.pushInfo(self.tr("Заполнено узлов: %d из %d")
                          % (filled, vol.size))

        gt = (x0, cell, 0.0, y1, 0.0, -cell)
        crs = src.sourceCrs()
        _write_grid_tiff(out_path, [vol[k] for k in range(nz)], gt,
                         crs.toWkt() if crs is not None else "",
                         float("nan"), nx, ny,
                         [self.tr("уровень %d") % (k + 1)
                          for k in range(nz)],
                         meta={"Z0": "%.6f" % z0, "DZ": "%.6f" % cellz})
        return {"OUTPUT": out_path}


def _read_cube(path):
    """Куб значений из многоканального грида.

    Канал это горизонтальный уровень. Отметка первого уровня и шаг
    лежат в метаданных, их пишет инструмент 2.02. Если метаданных нет,
    считаем от нуля с единичным шагом: лучше показать форму, чем
    отказаться совсем.
    """
    ds = gdal.Open(path)
    if ds is None or ds.RasterCount < 2:
        return None, None, 0.0, 1.0
    gt = ds.GetGeoTransform()
    meta = ds.GetMetadata() or {}
    z0 = float(meta.get("Z0", meta.get("z0", 0.0)) or 0.0)
    dz = float(meta.get("DZ", meta.get("dz", 1.0)) or 1.0)
    bands = []
    for b in range(1, ds.RasterCount + 1):
        band = ds.GetRasterBand(b)
        arr = band.ReadAsArray().astype(float)
        nd = band.GetNoDataValue()
        if nd is not None:
            arr[arr == nd] = np.nan
        bands.append(arr)
    ds = None
    return np.stack(bands, axis=0), gt, z0, dz


def _contour_rings(alg, parameters, key, context):
    """Кольца полигонов контура, если слой задан."""
    lyr = alg.parameterAsVectorLayer(parameters, key, context)
    if lyr is None:
        return []
    rings = []
    for ft in lyr.getFeatures():
        g = ft.geometry()
        if g is None or g.isEmpty():
            continue
        try:
            polys = g.asMultiPolygon()
        except Exception:  # nosec
            polys = []
        if not polys:
            try:
                one = g.asPolygon()
            except Exception:  # nosec
                one = []
            polys = [one] if one else []
        for poly in polys:
            for ring in poly:
                rings.append([(p.x(), p.y()) for p in ring])
    return rings


class CubeToBlocksAlgorithm(IsolinerAlgorithm):
    """Куб значений в блочную модель: точка-центроид на ячейку.

    Куб как набор каналов ничем не адресуется: канал это не отметка,
    а номер, и ни фильтр выражением, ни таблица атрибутов по нему
    не работают. Блочная модель возвращает ячейке номер, координаты,
    размер и значение, и дальше работает обычный векторный аппарат
    QGIS.

    Выгружаются только занятые ячейки. Пропуски и всё, что не прошло
    отсечку, в слой не идут: разреженная модель весит на порядок
    меньше полного параллелепипеда с пустыми краями.
    """

    CUBE = "CUBE"
    CUTOFF = "CUTOFF"
    USE_CUTOFF = "USE_CUTOFF"
    CONTOUR = "CONTOUR"
    TOPSURF = "TOPSURF"
    BOTSURF = "BOTSURF"
    CLASSES = "CLASSES"
    DENS = "DENS"
    OUTPUT = "OUTPUT"

    def name(self):
        return "cube_to_block_model"

    def displayName(self):
        return self.tr("2.03 Куб в блочную модель")

    def group(self):
        return self.tr(GROUP5)

    def groupId(self):
        return GROUP5_ID

    def helpUrl(self):
        return _help_url()

    def shortHelpString(self):
        return _help_version(self.tr(
            "Переводит куб значений в блочную модель: точку-центроид "
            "на каждую занятую ячейку.\n\nПоля: bid (номер блока), lev "
            "(уровень), row и col (ячейка грида), x, y, z (центр "
            "блока), dx, dy, dz (размер блока), vol (объём), val "
            "(значение), cls (номер интервала окраски), при заданной "
            "плотности ещё dens и ore_t.\n\nПропуски и ячейки ниже "
            "отсечки не выгружаются. Модель выходит разреженной, "
            "и весит она на порядок меньше полного параллелепипеда "
            "с пустыми краями.\n\nДальше работает векторный аппарат "
            "QGIS: фильтры выражениями, соединение внешних таблиц, "
            "калькулятор полей. Тот же слой показывается коробками "
            "в окне просмотра.")
            + _credit())

    def createInstance(self):
        return CubeToBlocksAlgorithm()

    def initAlgorithm(self, config=None):
        self._defaults = _load_defaults(self)
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.CUBE, self.tr("Куб значений (каналы это уровни)")))
        self.addParameter(QgsProcessingParameterBoolean(
            self.USE_CUTOFF, self.tr("Применять отсечку"),
            defaultValue=_dv(self, self.USE_CUTOFF, False)))
        self.addParameter(QgsProcessingParameterNumber(
            self.CUTOFF, self.tr("Отсечка"),
            QgsProcessingParameterNumber.Type.Double,
            defaultValue=_dv(self, self.CUTOFF, 0.0)))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.CONTOUR, self.tr("Контур подсчёта"),
            [QgsProcessing.SourceType.TypeVectorPolygon], optional=True))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.TOPSURF, self.tr("Отсечка сверху (поверхность)"),
            optional=True))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.BOTSURF, self.tr("Отсечка снизу (поверхность)"),
            optional=True))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            self.CLASSES, self.tr("Интервалов окраски (0 - без классов)"),
            QgsProcessingParameterNumber.Type.Integer,
            defaultValue=_dv(self, self.CLASSES, 8),
            minValue=0, maxValue=64)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            self.DENS, self.tr("Плотность, т/м3 (0 - без пересчёта)"),
            QgsProcessingParameterNumber.Type.Double,
            defaultValue=_dv(self, self.DENS, 0.0), minValue=0.0)))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Блочная модель"),
            QgsProcessing.SourceType.TypeVectorPoint))

        _hints(self, HINTS_2_03)

    def _process(self, parameters, context, feedback):
        from qgis.core import (QgsFields, QgsFeature, QgsGeometry,
                               QgsPoint, QgsWkbTypes)
        from . import voxel

        feedback.pushInfo(_version_line())
        _saved = dict(parameters)
        lyr = self.parameterAsRasterLayer(parameters, self.CUBE, context)
        if lyr is None:
            raise QgsProcessingException(self.tr("Не задан куб значений."))
        vol, gt, z0, dz = _read_cube(lyr.source())
        if vol is None:
            raise QgsProcessingException(self.tr(
                "Слою нужен многоканальный грид: каналы это уровни куба."))
        nz, ny, nx = vol.shape
        feedback.pushInfo(self.tr("Куб: %d x %d x %d, отметка первого "
                                  "уровня %.3f, шаг %.3f.")
                          % (nx, ny, nz, z0, dz))

        rings = _contour_rings(self, parameters, self.CONTOUR, context)
        if rings:
            flat = polygon_mask(rings, gt, (ny, nx))
            vol = np.where(flat[None, :, :], vol, np.nan)
            feedback.pushInfo(self.tr("Контур оставил ячеек в плане: %d "
                                      "из %d.")
                              % (int(flat.sum()), flat.size))

        use_cut = self.parameterAsBool(parameters, self.USE_CUTOFF, context)
        cut = self.parameterAsDouble(parameters, self.CUTOFF, context)
        if use_cut:
            occ = voxel.occupancy(vol, cut)
        else:
            occ = np.isfinite(vol)
        n_cells = int(occ.sum())
        if not n_cells:
            raise QgsProcessingException(self.tr(
                "Занятых ячеек не осталось: проверьте отсечку и контур."))

        nclass = self.parameterAsInt(parameters, self.CLASSES, context)
        vals_in = vol[occ]
        vmin, vmax = float(vals_in.min()), float(vals_in.max())
        if nclass > 1 and vmax > vmin:
            edges = np.linspace(vmin, vmax, nclass + 1)[1:-1]
            cls = voxel.quantize(vol, edges)
        else:
            cls = np.zeros(vol.shape, dtype=np.int32)
        dens = self.parameterAsDouble(parameters, self.DENS, context)

        dx = abs(gt[1])
        dy = abs(gt[5])
        cell_vol = dx * dy * abs(dz)
        fields = QgsFields()
        for nm, tp in (("bid", QVariant.Int), ("lev", QVariant.Int),
                       ("row", QVariant.Int), ("col", QVariant.Int),
                       ("x", QVariant.Double), ("y", QVariant.Double),
                       ("z", QVariant.Double), ("dx", QVariant.Double),
                       ("dy", QVariant.Double), ("dz", QVariant.Double),
                       ("vol", QVariant.Double), ("val", QVariant.Double),
                       ("cls", QVariant.Int)):
            fields.append(_field(nm, tp))
        if dens > 0:
            fields.append(_field("dens", QVariant.Double))
            fields.append(_field("ore_t", QVariant.Double))
        sink, dest = self.parameterAsSink(
            parameters, self.OUTPUT, context, fields,
            QgsWkbTypes.Type.PointZ, lyr.crs())
        if sink is None:
            raise QgsProcessingException(
                self.tr("Не удалось создать слой блочной модели."))

        idx = np.argwhere(occ)
        # Отсечка поверхностями: точки выше кровли или ниже подошвы
        # в модель не идут. Одной отметкой этого не заменить,
        # поверхности меняются по площади.
        top_l = self.parameterAsRasterLayer(parameters, self.TOPSURF,
                                            context)
        bot_l = self.parameterAsRasterLayer(parameters, self.BOTSURF,
                                            context)
        if (top_l is not None or bot_l is not None) and len(idx):
            from .flatten import keep_between
            ta, tg = _read_surface(top_l) if top_l is not None \
                else (None, None)
            ba, bg = _read_surface(bot_l) if bot_l is not None \
                else (None, None)
            if top_l is not None and ta is None:
                raise QgsProcessingException(
                    self.tr("Поверхность отсечки сверху не открылась."))
            if bot_l is not None and ba is None:
                raise QgsProcessingException(
                    self.tr("Поверхность отсечки снизу не открылась."))
            px = gt[0] + (idx[:, 2] + 0.5) * gt[1]
            py = gt[3] + (idx[:, 1] + 0.5) * gt[5]
            pz = z0 + idx[:, 0] * dz
            keep = keep_between(px, py, pz, ta, tg, ba, bg)
            cut = int((~keep).sum())
            idx = idx[keep]
            feedback.pushInfo(self.tr(
                "Отсечка поверхностями убрала точек: %d, осталось %d.")
                % (cut, len(idx)))
            if not len(idx):
                raise QgsProcessingException(self.tr(
                    "Отсечка поверхностями убрала всё. Проверьте, "
                    "что кровля выше подошвы и что поверхности "
                    "накрывают куб."))
        step = max(len(idx) // 50, 1)
        for n, (k, i, j) in enumerate(idx):
            if feedback.isCanceled():
                break
            x = gt[0] + (j + 0.5) * gt[1]
            y = gt[3] + (i + 0.5) * gt[5]
            z = z0 + k * dz
            val = float(vol[k, i, j])
            attrs = [n + 1, int(k) + 1, int(i), int(j), float(x), float(y),
                     float(z), dx, dy, abs(dz), cell_vol, val,
                     int(cls[k, i, j])]
            if dens > 0:
                attrs.extend([dens, cell_vol * dens])
            ft = QgsFeature(fields)
            ft.setGeometry(QgsGeometry(QgsPoint(float(x), float(y),
                                                float(z))))
            ft.setAttributes(attrs)
            sink.addFeature(ft)
            if n % step == 0:
                feedback.setProgress(100.0 * n / max(len(idx), 1))
        _set_output_name(context, dest, self.tr("Блочная модель"))
        feedback.pushInfo(self.tr("Блоков: %d из %d ячеек куба, "
                                  "объём блока %.3f м3.")
                          % (n_cells, vol.size, cell_vol))
        feedback.pushInfo(self.tr("Значения: %.3f .. %.3f.") % (vmin, vmax))
        if dens > 0:
            feedback.pushInfo(self.tr("Суммарная масса: %.0f т.")
                              % (n_cells * cell_vol * dens))
        _save_values(self, _saved)
        return {self.OUTPUT: dest}


class CubeVoxelBodyAlgorithm(IsolinerAlgorithm):
    """Тело куба вокселями: слой граней вместо набора каналов.

    То же, что показывается в окне просмотра, но слоем: MULTIPOLYGON Z
    из прямоугольных граней. Слой открывается в любом просмотрщике,
    режется и считается обычными средствами.

    Строятся только видимые грани. Соседние грани одного интервала
    сливаются в прямоугольник, и на этом сцена делается лёгкой.
    Слияние стоит замкнутости: длинный прямоугольник упирается
    в два коротких, общего ребра у них нет. Для подсчёта объёма
    слияние надо выключить.
    """

    CUBE = "CUBE"
    CUTOFF = "CUTOFF"
    CONTOUR = "CONTOUR"
    CLASSES = "CLASSES"
    EDGES = "EDGES"
    LABELS = "LABELS"
    MERGE = "MERGE"
    UNPINCH = "UNPINCH"
    OUTPUT = "OUTPUT"

    def name(self):
        return "cube_voxel_body"

    def displayName(self):
        return self.tr("2.04 Тело куба вокселями")

    def group(self):
        return self.tr(GROUP5)

    def groupId(self):
        return GROUP5_ID

    def helpUrl(self):
        return _help_url()

    def shortHelpString(self):
        return _help_version(self.tr(
            "Строит тело по отсечке коробками ячеек: MULTIPOLYGON Z, "
            "объект на интервал окраски.\n\nСтроятся только видимые "
            "грани. Грань между двумя занятыми соседями не видна "
            "никогда, поэтому её отбрасывают: на кубе двести на двести "
            "на сто это сто двадцать шесть тысяч граней вместо "
            "двадцати четырёх миллионов.\n\nФлаг «Сливать соседние "
            "грани» делает сцену лёгкой, но ломает замкнутость: "
            "длинный прямоугольник упирается в два коротких, общего "
            "ребра у них нет. Для подсчёта объёма и проверки "
            "замкнутости флаг надо снять, тогда каждое ребро "
            "принадлежит ровно двум граням.\n\nПоля: cls (интервал "
            "окраски), vmin и vmax (границы интервала), faces (граней "
            "в объекте), shell (единица у тела).\n\nЗащип по ребру "
            "это касание двух ячеек одной диагональю. Дырой он "
            "не является и объём не портит, но ребро в нём принадлежит "
            "четырём граням, и проверка замкнутости такое тело "
            "отвергает. Флаг «Убирать защипы по ребру» заполняет угол "
            "одной ячейкой, и касание становится по грани.")
            + _credit())

    def createInstance(self):
        return CubeVoxelBodyAlgorithm()

    def initAlgorithm(self, config=None):
        self._defaults = _load_defaults(self)
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.CUBE, self.tr("Куб значений (каналы это уровни)")))
        self.addParameter(QgsProcessingParameterNumber(
            self.CUTOFF, self.tr("Отсечка"),
            QgsProcessingParameterNumber.Type.Double,
            defaultValue=_dv(self, self.CUTOFF, 0.0)))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.CONTOUR, self.tr("Контур подсчёта"),
            [QgsProcessing.SourceType.TypeVectorPolygon], optional=True))
        self.addParameter(QgsProcessingParameterNumber(
            self.CLASSES, self.tr("Интервалов окраски (0 - одним телом)"),
            QgsProcessingParameterNumber.Type.Integer,
            defaultValue=_dv(self, self.CLASSES, 0),
            minValue=0, maxValue=64))
        self.addParameter(QgsProcessingParameterString(
            self.EDGES, self.tr("Свои границы интервалов, через пробел"),
            optional=True))
        self.addParameter(QgsProcessingParameterString(
            self.LABELS, self.tr("Названия интервалов, через запятую"),
            optional=True))
        self.addParameter(QgsProcessingParameterBoolean(
            self.MERGE, self.tr("Сливать соседние грани"),
            defaultValue=_dv(self, self.MERGE, True)))
        self.addParameter(QgsProcessingParameterBoolean(
            self.UNPINCH, self.tr("Убирать защипы по ребру"),
            defaultValue=_dv(self, self.UNPINCH, True)))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Тело вокселями"),
            QgsProcessing.SourceType.TypeVectorPolygon))

        _hints(self, HINTS_2_04)

    def _process(self, parameters, context, feedback):
        from qgis.core import (QgsFields, QgsFeature, QgsGeometry,
                               QgsPoint, QgsPolygon, QgsLineString,
                               QgsMultiPolygon, QgsWkbTypes)
        from . import voxel

        feedback.pushInfo(_version_line())
        _saved = dict(parameters)
        lyr = self.parameterAsRasterLayer(parameters, self.CUBE, context)
        if lyr is None:
            raise QgsProcessingException(self.tr("Не задан куб значений."))
        vol, gt, z0, dz = _read_cube(lyr.source())
        if vol is None:
            raise QgsProcessingException(self.tr(
                "Слою нужен многоканальный грид: каналы это уровни куба."))
        nz, ny, nx = vol.shape
        rings = _contour_rings(self, parameters, self.CONTOUR, context)
        if rings:
            flat = polygon_mask(rings, gt, (ny, nx))
            vol = np.where(flat[None, :, :], vol, np.nan)

        cut = self.parameterAsDouble(parameters, self.CUTOFF, context)
        occ = voxel.occupancy(vol, cut)
        n_cells = int(occ.sum())
        if not n_cells:
            raise QgsProcessingException(self.tr(
                "По отсечке ячеек не осталось."))
        nclass = self.parameterAsInt(parameters, self.CLASSES, context)
        merge = self.parameterAsBool(parameters, self.MERGE, context)
        pinches = voxel.pinch_edges(occ)
        if pinches:
            feedback.pushInfo(self.tr("Защипов по ребру: %d.") % pinches)
        if pinches and self.parameterAsBool(parameters, self.UNPINCH,
                                            context):
            occ, added = voxel.unpinch(occ)
            n_cells = int(occ.sum())
            feedback.pushInfo(self.tr("Защипы убраны, добавлено ячеек: %d.")
                              % added)
        elif pinches:
            feedback.pushWarning(self.tr(
                "Защипы оставлены: рёбра в них принадлежат четырём "
                "граням, и замкнутой оболочка не будет."))
        vals_in = vol[occ]
        vmin, vmax = float(vals_in.min()), float(vals_in.max())
        # Свои границы важнее числа интервалов: человек задал разбивку
        # руками, и подменять её равными долями значит решать за него.
        own = voxel.parse_edges(
            self.parameterAsString(parameters, self.EDGES, context))
        if own:
            bounds = np.asarray(own, dtype=float)
            cls = voxel.quantize(vol, bounds[1:-1]) if len(bounds) > 2 \
                else voxel.quantize(vol, bounds[1:])
            nclass = len(bounds) - 1
            feedback.pushInfo(self.tr("Свои границы интервалов: %s.")
                              % ", ".join("%g" % b for b in bounds))
        elif nclass > 1 and vmax > vmin:
            bounds = np.linspace(vmin, vmax, nclass + 1)
            cls = voxel.quantize(vol, bounds[1:-1])
        else:
            nclass = 1
            bounds = np.array([vmin, vmax])
            cls = np.zeros(vol.shape, dtype=np.int32)
        names = voxel.parse_labels(
            self.parameterAsString(parameters, self.LABELS, context),
            nclass)

        feedback.setProgress(20)
        verts, faces, tri_cls, over = voxel.voxel_mesh(
            occ, gt, z0, dz, classes=cls, merge=merge)
        if over:
            raise QgsProcessingException(self.tr(
                "Модель слишком велика: поднимите отсечку или уменьшите "
                "число интервалов."))
        feedback.setProgress(60)
        feedback.pushInfo(self.tr("Ячеек: %d, видимых граней: %d, "
                                  "треугольников: %d.")
                          % (n_cells, voxel.visible_faces(occ), len(faces)))

        fields = QgsFields()
        for nm, tp in (("cls", QVariant.Int), ("name", QVariant.String),
                       ("vmin", QVariant.Double),
                       ("vmax", QVariant.Double), ("faces", QVariant.Int),
                       ("shell", QVariant.Int)):
            fields.append(_field(nm, tp))
        sink, dest = self.parameterAsSink(
            parameters, self.OUTPUT, context, fields,
            QgsWkbTypes.Type.MultiPolygonZ, lyr.crs())
        if sink is None:
            raise QgsProcessingException(
                self.tr("Не удалось создать слой тела."))

        made = 0
        for c in range(nclass):
            sel = tri_cls == c
            if not sel.any():
                continue
            mp = QgsMultiPolygon()
            for tri in faces[sel]:
                ring = QgsLineString()
                for vi in (tri[0], tri[1], tri[2], tri[0]):
                    p = verts[vi]
                    ring.addVertex(QgsPoint(float(p[0]), float(p[1]),
                                            float(p[2])))
                poly = QgsPolygon()
                poly.setExteriorRing(ring)
                mp.addGeometry(poly)
            ft = QgsFeature(fields)
            ft.setGeometry(QgsGeometry(mp))
            nm_c = names[c] if 0 <= c < len(names) else ""
            ft.setAttributes([c, nm_c, float(bounds[c]),
                              float(bounds[c + 1]),
                              int(sel.sum()), 1])
            sink.addFeature(ft)
            made += 1
            feedback.setProgress(60 + 40.0 * made / max(nclass, 1))
        _set_output_name(context, dest, self.tr("Тело вокселями"))
        feedback.pushInfo(self.tr("Объектов: %d.") % made)
        if merge:
            feedback.pushInfo(self.tr(
                "Грани слиты. Замкнутой такая оболочка не будет: "
                "для подсчёта объёма снимите флаг слияния."))
        _save_values(self, _saved)
        return {self.OUTPUT: dest}


HINTS_2_05 = {
    "INPUT": "Тот же слой проб, что подаётся в 2.02. Проверка идёт "
             "по самим пробам, куб для неё не нужен.",
    "FIELD": "Поле значения, по которому строится куб. Именно его "
             "и проверяем. У демонстрационных данных из 2.01 это "
             "grade.",
    "ZSRC": "Источник отметки должен совпадать с тем, что задан в 2.02: "
            "иначе проверяется не та расстановка точек.",
    "ZFIELD": "Для отметки из поля это сама отметка, для глубины это "
              "глубина вниз от поверхности.",
    "ZSURF": "Грид, от которого отсчитывается глубина. Тот же, что "
             "и в 2.02.",
    "GROUP": "Номер скважины. С ним из выборки убирается ствол "
             "целиком, и проверка меряет умение попасть между "
             "скважинами. Без него убирается одна проба, соседи "
             "берутся из того же ствола, и ошибка выходит в разы "
             "меньше настоящей.",
    "METHOD": "Метод, который собираетесь применять в 2.02. Проверка "
              "и нужна, чтобы выбрать между ними по числам, а не "
              "на глаз.",
    "MAXPTS": "Ноль берёт на одного больше, чем замеров в одной точке "
              "плана. Это тот же подбор, что и в 2.02.",
    "ANISO": "Отношение вертикального масштаба к горизонтальному. "
             "Подбирается как раз по ошибке проверки.",
    "RADIUS": "Ноль берёт четверть охвата данных. Проба, вокруг которой "
              "точек не нашлось, остаётся непроверенной.",
    "POWER": "Степень обратных расстояний. Подбирается по ошибке "
             "проверки вместе с анизотропией.",
    "MINPTS": "Проба, вокруг которой точек меньше этого числа, остаётся "
              "непроверенной и в ошибку не идёт.",
    "SECTORS": "Ноль берёт от данных: у скважин деление нужно, иначе "
               "все соседи окажутся в одном стволе, а у одиночных проб "
               "в плане оно только рвёт поле.",
    "OUTPUT": "Пробы с полями value, model, resid и aresid. По ним "
              "видно не только величину промаха, но и где он случился.",
}


class Mba3DAlgorithm(IsolinerAlgorithm):
    """MBA в объёме: куб значений мультисеточными B-сплайнами.

    Метод не решает систему уравнений вовсе: коэффициент решётки
    считается явно, взвешенной суммой по попавшим в него точкам.
    Поэтому работа линейна по числу замеров, и там, где кригинг встаёт,
    MBA считает.

    Чего он не даёт: ни ошибки оценки, ни модели ковариации, ни весов.
    Это приближение, а не оценка, и в журнале это говорится прямо.
    Рядом с кригингом он хорош как тренд, который дальше уточняют
    кригингом остатков.
    """

    def name(self):
        return "mba3d"

    def displayName(self):
        return self.tr("2.07 MBA в объёме")

    def group(self):
        return self.tr(GROUP5)

    def groupId(self):
        return GROUP5_ID

    def createInstance(self):
        return Mba3DAlgorithm()

    def shortHelpString(self):
        return self.tr(
            "Строит куб значений по разбросанным точкам "
            "мультисеточными B-сплайнами.\n\n"
            "Грубая решётка приближает данные, остаток приближается "
            "решёткой вдвое мельче, и так уровень за уровнем. Система "
            "уравнений не решается: работа линейна по числу точек, "
            "и на сотнях тысяч замеров метод считает там, где кригинг "
            "встаёт.\n\n"
            "Метод приближает, а не оценивает. Точного попадания "
            "в замеры нет, ошибки оценки он не даёт. Рядом с кригингом "
            "он хорош как тренд, который дальше уточняют кригингом "
            "остатков.\n\n"
            "За пределами облака точек поверхность уходит куда угодно: "
            "у краевых коэффициентов нет данных. Обрезайте результат "
            "контуром или поверхностями.")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            "INPUT", self.tr("Точки с высотой"),
            [QgsProcessing.SourceType.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterField(
            "FIELD", self.tr("Поле значения"),
            parentLayerParameterName="INPUT",
            type=QgsProcessingParameterField.DataType.Numeric))
        self.addParameter(QgsProcessingParameterEnum(
            "ZSRC", self.tr("Источник отметки"),
            options=[self.tr("Высота геометрии (Z)"),
                     self.tr("Поле отметки"),
                     self.tr("Глубина от поверхности")],
            defaultValue=0))
        self.addParameter(QgsProcessingParameterField(
            "ZFIELD", self.tr("Поле отметки или глубины"),
            parentLayerParameterName="INPUT", optional=True,
            type=QgsProcessingParameterField.DataType.Numeric))
        self.addParameter(QgsProcessingParameterRasterLayer(
            "ZSURF", self.tr("Поверхность для отсчёта глубины"),
            optional=True))
        self.addParameter(QgsProcessingParameterNumber(
            "GRID", self.tr("Начальная решётка по плану"),
            QgsProcessingParameterNumber.Type.Integer,
            defaultValue=8, minValue=1, maxValue=256))
        self.addParameter(QgsProcessingParameterNumber(
            "GRIDZ", self.tr("Начальная решётка по вертикали"),
            QgsProcessingParameterNumber.Type.Integer,
            defaultValue=2, minValue=1, maxValue=256))
        self.addParameter(QgsProcessingParameterNumber(
            "LEVELS", self.tr("Уровней"),
            QgsProcessingParameterNumber.Type.Integer,
            defaultValue=5, minValue=1, maxValue=12))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            "TOL", self.tr("Остановка по невязке (0 - все уровни)"),
            QgsProcessingParameterNumber.Type.Double,
            defaultValue=0.0, minValue=0.0)))
        self.addParameter(QgsProcessingParameterNumber(
            "CELL", self.tr("Шаг куба по горизонтали (0 - от данных)"),
            QgsProcessingParameterNumber.Type.Double,
            defaultValue=0.0, minValue=0.0))
        self.addParameter(QgsProcessingParameterNumber(
            "CELLZ", self.tr("Шаг куба по вертикали (0 - от данных)"),
            QgsProcessingParameterNumber.Type.Double,
            defaultValue=0.0, minValue=0.0))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            "VMIN", self.tr("Наименьшее значение (пусто - без края)"),
            QgsProcessingParameterNumber.Type.Double, optional=True)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            "VMAX", self.tr("Наибольшее значение (пусто - без края)"),
            QgsProcessingParameterNumber.Type.Double, optional=True)))
        self.addParameter(QgsProcessingParameterRasterDestination(
            "OUTPUT", self.tr("Куб значений")))
        _hints(self, HINTS_2_07)

    def _process(self, parameters, context, feedback):
        from . import mba
        from .interp3d import sampling_spacing, auto_grid

        src = self.parameterAsSource(parameters, "INPUT", context)
        gx = self.parameterAsInt(parameters, "GRID", context)
        gz = self.parameterAsInt(parameters, "GRIDZ", context)
        levels = self.parameterAsInt(parameters, "LEVELS", context)
        tol = self.parameterAsDouble(parameters, "TOL", context)
        cell = self.parameterAsDouble(parameters, "CELL", context)
        cellz = self.parameterAsDouble(parameters, "CELLZ", context)
        out_path = self.parameterAsOutputLayer(parameters, "OUTPUT",
                                               context)
        xs, ys, zs, vals = _read_samples(self, parameters, context,
                                         feedback)
        net = sampling_spacing(np.column_stack([xs, ys, zs]))
        auto = auto_grid(*net) if net else None
        if cell <= 0:
            cell = auto["cell"] if auto else 25.0
            feedback.pushInfo(self.tr("Шаг по горизонтали от данных: "
                                      "%.1f м.") % cell)
        if cellz <= 0:
            cellz = auto["cellz"] if auto else 5.0
            feedback.pushInfo(self.tr("Шаг по вертикали от данных: "
                                      "%.2f м.") % cellz)

        x0, x1 = float(np.min(xs)), float(np.max(xs))
        y0, y1 = float(np.min(ys)), float(np.max(ys))
        z0, z1 = float(np.min(zs)), float(np.max(zs))
        pad = max(cell, 1e-9)
        x0, x1 = x0 - pad, x1 + pad
        y0, y1 = y0 - pad, y1 + pad
        z0, z1 = z0 - cellz, z1 + cellz

        # Память последнего уровня растёт кубом, и считать её надо
        # до выделения, а не после отказа.
        need = mba.volume_memory(gx, gx, gz, levels)
        feedback.pushInfo(self.tr(
            "Решётка %dx%dx%d, уровней %d: последняя %dx%dx%d, "
            "память решёток около %.0f МБ.")
            % (gx, gx, gz, levels,
               gx * 2 ** (levels - 1), gx * 2 ** (levels - 1),
               gz * 2 ** (levels - 1), need / 1048576.0))
        if need > 2 * 1024 ** 3:
            raise QgsProcessingException(self.tr(
                "Решётке нужно больше двух гигабайт. Убавьте число "
                "уровней или начальную решётку."))

        pts = np.column_stack([xs, ys, zs])
        lat = mba.fit(pts, vals, lo=[x0, y0, z0], hi=[x1, y1, z1],
                      grid=(gx, gx, gz), levels=levels,
                      tol=(tol if tol > 0 else None))
        # Отчёт по уровням возвращает словари, а не строки: собираем
        # строку сами. По невязке видно, когда дробить пора прекратить -
        # если уровень её почти не уменьшил, дальше он ловит шум.
        for k, rep in enumerate(mba.levels_report(lat, pts, vals)):
            feedback.pushInfo(self.tr(
                "Уровень %d, решётка %s: наибольшая невязка %.4g, "
                "средняя квадратичная %.4g.")
                % (k + 1, "x".join(str(v) for v in rep["cells"]),
                   rep["max"], rep["rms"]))
        feedback.setProgress(60)

        nx = max(int(np.ceil((x1 - x0) / cell)), 1)
        ny = max(int(np.ceil((y1 - y0) / cell)), 1)
        nz = max(int(np.ceil((z1 - z0) / cellz)) + 1, 2)
        gt = (x0, cell, 0.0, y0 + ny * cell, 0.0, -cell)
        vol = mba.volume_on_grid(lat, gt, nx, ny, nz, z0, cellz)
        # Края значений: метод приближает и за диапазон выходит,
        # а содержание не бывает ниже нуля.
        vmin = self.parameterAsDouble(parameters, "VMIN", context) \
            if parameters.get("VMIN") is not None else None
        vmax = self.parameterAsDouble(parameters, "VMAX", context) \
            if parameters.get("VMAX") is not None else None
        if vmin is not None or vmax is not None:
            try:
                vol, n_cut = mba.clamp_values(vol, vmin, vmax)
            except ValueError as e:
                raise QgsProcessingException(str(e))
            if n_cut:
                feedback.pushWarning(self.tr(
                    "Прижато к краям узлов: %d из %d. Много прижатых "
                    "значит, что модель уходит за диапазон, и лучше "
                    "убавить число уровней.") % (n_cut, vol.size))
        feedback.pushInfo(self.tr("Куб: %d x %d x %d, узлов %d.")
                          % (nx, ny, nz, vol.size))
        feedback.pushInfo(self.tr(
            "Метод приближает, а не оценивает: ошибки оценки и весов "
            "он не даёт. Для оценки берите кригинг в объёме (2.06)."))

        crs = src.sourceCrs()
        _write_grid_tiff(out_path, [vol[k] for k in range(nz)], gt,
                         crs.toWkt() if crs is not None else "",
                         float("nan"), nx, ny,
                         [self.tr("уровень %d") % (k + 1)
                          for k in range(nz)],
                         meta={"Z0": "%.6f" % z0, "DZ": "%.6f" % cellz})
        return {"OUTPUT": out_path}


class CrossValidateAlgorithm(IsolinerAlgorithm):
    """Проверка интерполяции с исключением по одной пробе.

    Каждая проба по очереди убирается из выборки, значение в её точке
    считается по остальным, и разность с настоящим значением идёт
    в невязку. Другого способа узнать, можно ли верить кубу, у нас нет:
    сравнивать построенное не с чем, а на глаз одинаково убедительно
    выглядят и хорошая модель, и вымысел.

    По невязкам подбирают анизотропию, степень и число соседей: у этих
    параметров нет правильного значения вообще, есть только лучшее
    на этих данных.
    """

    def name(self):
        return "cross_validate_3d"

    def displayName(self):
        return self.tr("2.05 Проверка интерполяции")

    def group(self):
        return self.tr(GROUP5)

    def groupId(self):
        return GROUP5_ID

    def helpUrl(self):
        return _help_url()

    def shortHelpString(self):
        return _help_version(self.tr(
            "Убирает пробы из выборки, считает значение в их точках "
            "по остальным и сравнивает с настоящим.\n\n"
            "ЗАЧЕМ. Это единственный способ узнать, можно ли верить "
            "кубу. Сравнивать построенное не с чем: настоящего "
            "распределения содержаний никто не видел, а на глаз "
            "одинаково убедительно выглядят и хорошая модель, "
            "и вымысел.\n\n"
            "ЧТО ИСКЛЮЧАТЬ. Без поля скважины убирается одна проба. "
            "На разведочной сети это льстит модели: соседей она берёт "
            "из того же ствола в трёх метрах, и меряется связность "
            "по стволу, а не умение попасть между скважинами. "
            "На демонстрационных данных разница шестикратная: ошибка "
            "по пробам 0.17, по скважинам 1.10. Задав поле скважины, "
            "убираем ствол целиком, и проверка отвечает на нужный "
            "вопрос.\n\n"
            "ЧИСЛА В ЖУРНАЛЕ. Средняя ошибка это обычный промах "
            "по модулю. Среднеквадратичная тяжелее наказывает редкие "
            "крупные промахи: если она заметно больше средней, модель "
            "иногда мажет сильно. Смещение показывает, уводит ли "
            "модель в одну сторону: положительное значит завышает. "
            "Разброс и односторонний увод выглядят одинаково, "
            "а лечатся по-разному, поэтому смещение вынесено "
            "отдельно. Доля ошибки от размаха данных ставит её "
            "в масштаб: единица это много на содержаниях до двух "
            "и мало на содержаниях до ста.\n\n"
            "ЧТО ПОДБИРАТЬ. Меняя анизотропию, степень, число соседей "
            "и сектора и смотря на ошибку, эти параметры выбирают "
            "по числам. Правильного значения у них нет вообще, есть "
            "только лучшее на конкретных данных. Осторожно "
            "с проверкой по одной пробе: отбор ближайших от "
            "анизотропии почти не зависит, пока ближайшая точка своя "
            "же по стволу, и по такой проверке нельзя выбирать "
            "ничего, что касается плана.\n\n"
            "РАДИУС. При исключении по скважине до соседней бывает "
            "дальше, чем автоматический радиус, и тогда проверять "
            "оказывается нечего. Инструмент скажет об этом, "
            "и радиус придётся задать вручную.\n\n"
            "СЛОЙ. Поля: value настоящее значение, model посчитанное, "
            "resid разность, aresid её модуль. Раскрасив по aresid, "
            "видно, в каком углу площадки модель мажет: числа этого "
            "не говорят.")
            + _credit())

    def createInstance(self):
        return CrossValidateAlgorithm()

    def initAlgorithm(self, config=None):
        self._defaults = _load_defaults(self)
        self.addParameter(QgsProcessingParameterFeatureSource(
            "INPUT", self.tr("Точки с высотой"),
            [QgsProcessing.SourceType.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterField(
            "FIELD", self.tr("Поле значения"),
            parentLayerParameterName="INPUT",
            type=QgsProcessingParameterField.DataType.Numeric))
        self.addParameter(QgsProcessingParameterEnum(
            "ZSRC", self.tr("Источник отметки"),
            options=[self.tr("Высота геометрии (Z)"),
                     self.tr("Поле отметки"),
                     self.tr("Глубина от поверхности")],
            defaultValue=0))
        self.addParameter(QgsProcessingParameterField(
            "ZFIELD", self.tr("Поле отметки или глубины"),
            parentLayerParameterName="INPUT", optional=True,
            type=QgsProcessingParameterField.DataType.Numeric))
        self.addParameter(QgsProcessingParameterRasterLayer(
            "ZSURF", self.tr("Поверхность для отсчёта глубины"),
            optional=True))
        self.addParameter(QgsProcessingParameterField(
            "GROUP", self.tr("Поле скважины (0 - по одной пробе)"),
            parentLayerParameterName="INPUT", optional=True))
        self.addParameter(QgsProcessingParameterEnum(
            "METHOD", self.tr("Метод"),
            options=[self.tr("Ближний сосед"),
                     self.tr("Обратные расстояния")], defaultValue=1))
        self.addParameter(QgsProcessingParameterNumber(
            "MAXPTS", self.tr("Наибольшее число точек (0 - от данных)"),
            QgsProcessingParameterNumber.Type.Integer, defaultValue=0,
            minValue=0))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            "ANISO", self.tr("Анизотропия (вертикаль к горизонтали)"),
            QgsProcessingParameterNumber.Type.Double, defaultValue=20.0,
            minValue=1e-6)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            "RADIUS", self.tr("Радиус поиска, м (0 - авто)"),
            QgsProcessingParameterNumber.Type.Double, defaultValue=0.0,
            minValue=0.0)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            "POWER", self.tr("Степень обратных расстояний"),
            QgsProcessingParameterNumber.Type.Double, defaultValue=2.0,
            minValue=0.1, maxValue=10.0)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            "MINPTS", self.tr("Наименьшее число точек"),
            QgsProcessingParameterNumber.Type.Integer, defaultValue=1,
            minValue=1)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            "SECTORS", self.tr("Секторов поиска (0 - от данных)"),
            QgsProcessingParameterNumber.Type.Integer, defaultValue=0,
            minValue=0, maxValue=32)))
        self.addParameter(QgsProcessingParameterFeatureSink(
            "OUTPUT", self.tr("Невязки проверки"),
            QgsProcessing.SourceType.TypeVectorPoint))
        _hints(self, HINTS_2_05)

    def _process(self, parameters, context, feedback):
        import numpy as np
        from qgis.core import (QgsFields, QgsFeature, QgsGeometry,
                               QgsPoint, QgsWkbTypes)
        from .interp3d import (cross_validate, cv_report, sampling_spacing,
                               auto_grid, auto_sectors)

        feedback.pushInfo(_version_line())
        _saved = dict(parameters)
        src = self.parameterAsSource(parameters, "INPUT", context)
        method = ("nearest", "idw")[
            self.parameterAsEnum(parameters, "METHOD", context)]
        aniso = self.parameterAsDouble(parameters, "ANISO", context)
        radius = self.parameterAsDouble(parameters, "RADIUS", context)
        power = self.parameterAsDouble(parameters, "POWER", context)
        maxp = self.parameterAsInt(parameters, "MAXPTS", context)
        minp = self.parameterAsInt(parameters, "MINPTS", context)
        sectors = self.parameterAsInt(parameters, "SECTORS", context)
        gfield = self.parameterAsString(parameters, "GROUP", context)

        xs, ys, zs, vals = _read_samples(self, parameters, context,
                                         feedback)
        groups = None
        if gfield:
            groups = []
            for ft in src.getFeatures():
                try:
                    groups.append(str(ft[gfield]))
                except (TypeError, ValueError, KeyError):
                    groups.append("")
            if len(groups) != len(vals):
                # Разбор проб выбрасывает точки без отметки, и номера
                # перестают совпадать. Молча сдвинуть их значило бы
                # проверить не то.
                feedback.pushWarning(self.tr(
                    "Поле скважины пропущено: часть проб отброшена "
                    "при разборе отметок, и номера разошлись."))
                groups = None
            else:
                feedback.pushInfo(self.tr("Исключаем по скважине, их %d.")
                                  % len(set(groups)))
        net = sampling_spacing(np.column_stack([xs, ys, zs]))
        auto = auto_grid(*net) if net else None
        if sectors <= 0:
            sectors = auto_sectors(net[2] if net else None)
            feedback.pushInfo(self.tr(
                "Секторов поиска от данных: %d.") % sectors)
        if maxp <= 0:
            maxp = auto["max_points"] if auto else 16
            feedback.pushInfo(self.tr("Наибольшее число точек "
                                      "от данных: %d.") % maxp)
        pts = np.column_stack([xs, ys, zs])
        val = np.array(vals, dtype=float)
        feedback.pushInfo(self.tr("Проверяется проб: %d.") % len(val))
        feedback.setProgress(10)

        res, _mae, _rmse = cross_validate(
            pts, val, method=method,
            radius=(radius if radius > 0 else None),
            anisotropy=aniso, power=power, max_points=maxp,
            min_points=minp, sectors=sectors, groups=groups)
        feedback.setProgress(80)
        rep = cv_report(res, val)

        fields = QgsFields()
        for nm in ("value", "model", "resid", "aresid"):
            fields.append(_field(nm, QVariant.Double))
        sink, dest = self.parameterAsSink(
            parameters, "OUTPUT", context, fields,
            QgsWkbTypes.Type.PointZ, src.sourceCrs())
        if sink is None:
            raise QgsProcessingException(
                self.tr("Не удалось создать слой невязок."))
        for i in range(len(val)):
            r = float(res[i])
            ft = QgsFeature(fields)
            ft.setGeometry(QgsGeometry(QgsPoint(float(xs[i]), float(ys[i]),
                                                float(zs[i]))))
            ft.setAttributes([float(val[i]),
                              float(val[i] + r) if r == r else None,
                              r if r == r else None,
                              abs(r) if r == r else None])
            sink.addFeature(ft)
        _set_output_name(context, dest, self.tr("Невязки проверки"))

        if rep["n"] < len(val):
            feedback.pushWarning(self.tr(
                "Проверено %d проб из %d: у остальных соседей "
                "не нашлось. При исключении по скважине до соседней "
                "бывает дальше, чем автоматический радиус: задайте "
                "радиус вручную.") % (rep["n"], len(val)))
        feedback.pushInfo(self.tr(
            "Ошибка: средняя %.4f, среднеквадратичная %.4f, "
            "смещение %+.4f.") % (rep["mae"], rep["rmse"], rep["bias"]))
        if rep["spread"] > 0:
            feedback.pushInfo(self.tr(
                "Размах данных %.4f, средняя ошибка это %.1f процента "
                "от него.") % (rep["spread"], 100.0 * rep["mae_share"]))
        feedback.pushInfo(self.tr(
            "Меняйте анизотропию, степень и число точек и смотрите "
            "на эти числа: правильного значения у них нет, есть "
            "лучшее на ваших данных."))
        _save_values(self, _saved)
        return {"OUTPUT": dest}


HINTS_1_08 = {
    "LIKE": "Растр, по охвату которого делать карту. Нужен, чтобы "
            "текстура легла ровно на существующий грид.",
    "EXTENT": "Границы карты, когда грид не задан. Пусто означает взять "
              "охват окна вида.",
    "PIXEL": "Сторона картинки в пикселях. Крупнее значит чётче "
             "текстура и тяжелее файл.",
    "CELLS": "Сколько клеток координатной сетки нарисовать на карте.",
    "FIELDS": "Сколько полей пластов нарисовать на карте.",
    "OUTPUT_MAP": "Картинка для текстуры: её можно натянуть "
                  "на поверхность в окне просмотра.",
}


class DemoMapAlgorithm(IsolinerAlgorithm):
    """Проверочная карта-растр для наложения текстуры.

    Отделена от 1.07: у карты и у тел общего только охват, а поля
    у каждого набора свои. В одном инструменте это были тринадцать
    строк, из которых при любом выборе работала половина, и понять
    по списку, какие из них про твой случай, было нельзя.
    """

    LIKE, PIXEL, CELLS, FIELDS = "LIKE", "PIXEL", "CELLS", "FIELDS"
    EXTENT = "EXTENT"
    OUTPUT_MAP = "OUTPUT_MAP"

    def name(self):
        return "demo_map"

    def displayName(self):
        return self.tr("1.08 Карта для текстуры (демо)")

    def group(self):
        return self.tr(GROUP4)

    def groupId(self):
        return GROUP4_ID

    def helpUrl(self):
        return _help_url()

    def shortHelpString(self):
        return _help_version(self.tr(
            "Рисует проверочную карту с координатной сеткой и полями "
            "пластов.\n\nНужна, чтобы посмотреть, как ложится текстура "
            "на поверхность в окне просмотра: на настоящей карте "
            "перекосы и растяжения видно хуже, чем на клетках.\n\n"
            "Охват берётся из готового грида, если он задан, иначе "
            "из поля охвата: карта тогда ляжет ровно по границам "
            "поверхности.")
            + _credit())

    def createInstance(self):
        return DemoMapAlgorithm()

    def initAlgorithm(self, config=None):
        self._defaults = _load_defaults(self)
        self.addParameter(QgsProcessingParameterExtent(
            self.EXTENT, self.tr("Охват (если грид не задан)"),
            optional=True))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.LIKE, self.tr("Карта: по охвату грида (растр)"),
            optional=True))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            self.PIXEL, self.tr("Карта: сторона картинки, пикселей"),
            QgsProcessingParameterNumber.Type.Integer,
            defaultValue=_dv(self, self.PIXEL, 1024),
            minValue=64, maxValue=8192)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            self.CELLS, self.tr("Карта: клеток координатной сетки"),
            QgsProcessingParameterNumber.Type.Integer,
            defaultValue=_dv(self, self.CELLS, 10),
            minValue=2, maxValue=100)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            self.FIELDS, self.tr("Карта: полей пластов"),
            QgsProcessingParameterNumber.Type.Integer,
            defaultValue=_dv(self, self.FIELDS, 6),
            minValue=2, maxValue=8)))
        self.addParameter(QgsProcessingParameterRasterDestination(
            self.OUTPUT_MAP, self.tr("Карта (демо)"), optional=True))
        _hints(self, HINTS_1_08)

    def _process(self, parameters, context, feedback):
        feedback.pushInfo(_version_line())
        _saved = dict(parameters)
        res = self._make_map(parameters, context, feedback)
        _save_values(self, _saved)
        return res

    def _make_map(self, parameters, context, feedback):
        """Проверочная карта-растр для наложения текстуры.

        Охват берётся из готового грида, если он задан, иначе из общего
        параметра охвата: карта тогда ляжет ровно по границам поверхности.
        """
        from .demo_map import demo_map
        like = self.parameterAsRasterLayer(parameters, self.LIKE, context)
        if like is not None:
            ext, crs = like.extent(), like.crs()
        else:
            crs = QgsProject.instance().crs()
            ext = self.parameterAsExtent(parameters, self.EXTENT, context,
                                         crs)
        if ext is None or ext.isEmpty():
            raise QgsProcessingException(self.tr(
                "Задайте грид или охват: карте нужны границы."))
        side = int(self.parameterAsInt(parameters, self.PIXEL, context))
        cells = int(self.parameterAsInt(parameters, self.CELLS, context))
        nfields = int(self.parameterAsInt(parameters, self.FIELDS, context))
        w, h = ext.width(), ext.height()
        if w >= h:
            nx, ny = side, max(64, int(round(side * h / (w or 1.0))))
        else:
            nx, ny = max(64, int(round(side * w / (h or 1.0)))), side
        img = demo_map(nx=nx, ny=ny, cells=cells, n_fields=nfields)
        out = self.parameterAsOutputLayer(parameters, self.OUTPUT_MAP,
                                          context)
        if not out:
            raise QgsProcessingException(self.tr(
                "Укажите файл для карты в поле «Карта (демо)»."))
        drv = gdal.GetDriverByName("GTiff")
        ds = drv.Create(out, nx, ny, 3, gdal.GDT_Byte,
                        options=["COMPRESS=LZW", "TILED=YES"])
        ds.SetGeoTransform((ext.xMinimum(), w / float(nx), 0.0,
                            ext.yMaximum(), 0.0, -h / float(ny)))
        try:
            ds.SetProjection(crs.toWkt())
        except Exception:  # nosec
            pass
        for i in range(3):
            band = ds.GetRasterBand(i + 1)
            band.WriteArray(img[:, :, i])
            band.SetDescription(["red", "green", "blue"][i])
            band.FlushCache()
        ds = None
        feedback.pushInfo(self.tr("Карта: %d на %d пикселей.") % (nx, ny))
        _set_output_name(context, out, self.tr("Карта (демо)"))
        return {self.OUTPUT_MAP: out}


HINTS_2_06 = {
    "REF": "Кровля или подошва пласта. С ней вертикаль отсчитывается "
           "от поверхности, и расчёт идёт вдоль напластования. "
           "Вариограмма меряется уже в спрямлённых координатах: "
           "замерив в абсолютных, а посчитав в спрямлённых, получишь "
           "модель не от этих данных.",
    "REF_FLOOR": "Вторая поверхность. С ней отметка становится долей "
                 "мощности: ноль на кровле, единица на подошве.",
    "INPUT": "Тот же слой проб, что подаётся в 2.02. Отметка задаётся "
             "ниже так же, как там.",
    "FIELD": "Числовое поле, значение которого раскладывается по кубу. "
             "У демонстрационных данных из 2.01 это grade.",
    "ZSRC": "Плоский слой отдаёт нулевую Z у каждой точки. Если брать "
            "её из геометрии, все пробы лягут в одну плоскость и куб "
            "выйдет бессмысленным.",
    "ZFIELD": "Для отметки из поля это сама отметка, для глубины это "
              "глубина вниз от поверхности.",
    "ZSURF": "Грид, от которого отсчитывается глубина. Нужен пробам, "
             "где записана глубина, а не отметка.",
    "CELL": "Ноль берёт пятую часть расстояния между точками плана. "
            "Мельче делать незачем: данных в промежутке всё равно нет, "
            "а число узлов растёт как квадрат.",
    "CELLZ": "Ноль берёт половину шага опробования. Крупнее значит "
             "слить соседние замеры и потерять различие по глубине.",
    "MAXPTS": "Соседей на узел. Кригинг решает систему размером "
              "с их число, поэтому цена растёт как куб: шестнадцать "
              "это обычный выбор, тридцать два уже заметно дороже.",
    "AUTOVG": "Вариограмма замеряется по самим данным: длина связи "
              "из планового замера, самородок из вертикального. "
              "Задавать три числа на глаз бессмысленно, их и надо "
              "было замерить.",
    "NUGGET": "Разброс, который не убывает даже у соседних проб: "
              "ошибка опробования и изменчивость мельче сети. Читается, "
              "только если снят автоматический замер.",
    "SILL": "Общий разброс данных, к которому вариограмма выходит "
            "на больших расстояниях.",
    "RANGE": "Расстояние, после которого пробы уже ничего не знают "
             "друг о друге.",
    "VGMODEL": "Вид модели. Разница между ними невелика, важнее "
               "поведение у нуля: гауссова даёт слишком гладкое поле "
               "там, где данные шумят.",
    "ANISO": "Ноль берёт отношение вертикальной длины связи "
             "к плановой, замеренное по данным. Это тот случай, когда "
             "гадать не нужно.",
    "RADIUS": "Ноль берёт четверть охвата данных. Узел, где точек "
              "в радиусе не набралось, остаётся пропуском.",
    "SECTORS": "Ноль берёт от данных: у скважин деление нужно, иначе "
               "все соседи окажутся в одном стволе, а у проб в плане "
               "оно только рвёт поле. Граница сектора идёт лучом "
               "от узла, и на ней набор соседей меняется скачком: "
               "отсюда звёзды на почвенных пробах.",
    "OUTPUT": "Куб значений: канал это горизонтальный уровень.",
    "OUTVAR": "Куб дисперсии оценки, тех же размеров. В самой пробе "
              "ноль, дальше от данных растёт. Это карта доверия, "
              "и она единственное, что кригинг даёт всегда, независимо "
              "от густоты сети.",
}


class Kriging3DAlgorithm(IsolinerAlgorithm):
    """Обычный кригинг в объёме с замером вариограммы по данным.

    Отличается от обратных расстояний двумя вещами. Веса учитывают, что
    соседи знают друг про друга: две пробы рядом несут почти одно и то
    же, и двойного голоса им не даётся. И выдаётся дисперсия оценки,
    то есть карта доверия.

    Выигрыш по точности не безусловен: он появляется, когда шаг сети
    меньше примерно половины длины связи. На редкой сети соседние
    скважины уже почти ничего не знают друг о друге, веса выходят почти
    равными у любого метода, и разница уходит в шум.
    """

    def name(self):
        return "kriging_3d"

    def displayName(self):
        return self.tr("2.06 Кригинг в объёме")

    def group(self):
        return self.tr(GROUP5)

    def groupId(self):
        return GROUP5_ID

    def helpUrl(self):
        return _help_url()

    def shortHelpString(self):
        return _help_version(self.tr(
            "Считает куб значений кригингом и вторым выходом даёт куб "
            "дисперсии оценки.\n\n"
            "ЧЕМ ОТЛИЧАЕТСЯ ОТ 2.02. Обратные расстояния взвешивают "
            "по одному расстоянию: им всё равно, на каком расстоянии "
            "связь пропадает и сколько разброса приходится на ошибку "
            "опробования. Кригинг берёт веса из вариограммы, поэтому "
            "знает и то, и другое. Ещё он учитывает, что соседи знают "
            "друг про друга: две пробы рядом несут почти одно и то же, "
            "и двойного голоса им не даётся.\n\n"
            "КОГДА ЭТО ОКУПАЕТСЯ. Не всегда. На демонстрационных "
            "данных при густой сети кригинг выигрывает у обратных "
            "расстояний до восьми процентов, при редкой проигрывает "
            "до девяти. Перелом там, где шаг сети около половины длины "
            "связи. Причина проста: когда скважины стоят реже, "
            "соседние уже почти ничего не знают друг о друге, веса "
            "выходят почти равными у любого метода, и разница уходит "
            "в шум. Числа сети и длины связи инструмент печатает "
            "в журнал, так что решение видно сразу.\n\n"
            "ДИСПЕРСИЯ. Второй куб даёт то, чего у обратных расстояний "
            "нет вовсе: в самой пробе она ноль, дальше от данных "
            "растёт. Это карта доверия, и на редкой сети она "
            "единственная причина брать кригинг.\n\n"
            "ВАРИОГРАММА. Замеряется по самим данным. Длина связи "
            "берётся из планового замера, самородок из вертикального, "
            "анизотропия как отношение длин. Самородок из планового "
            "замера брать нельзя: в плане пар ближе шага сети нет "
            "вовсе, первый интервал начинается там же, и самородок "
            "оттуда это продолжение прямой к нулю через пустоту. "
            "По стволу пары есть с трёх метров.\n\n"
            "ПРОВЕРКА. Насколько верить получившемуся, отвечает 2.05. "
            "Задавайте там поле скважины: проверка по одной пробе "
            "льстит модели в разы, потому что соседей она берёт "
            "из того же ствола.")
            + _credit())

    def createInstance(self):
        return Kriging3DAlgorithm()

    def initAlgorithm(self, config=None):
        self._defaults = _load_defaults(self)
        self.addParameter(QgsProcessingParameterFeatureSource(
            "INPUT", self.tr("Точки с высотой"),
            [QgsProcessing.SourceType.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterField(
            "FIELD", self.tr("Поле значения"),
            parentLayerParameterName="INPUT",
            type=QgsProcessingParameterField.DataType.Numeric))
        self.addParameter(QgsProcessingParameterEnum(
            "ZSRC", self.tr("Источник отметки"),
            options=[self.tr("Высота геометрии (Z)"),
                     self.tr("Поле отметки"),
                     self.tr("Глубина от поверхности")],
            defaultValue=0))
        self.addParameter(QgsProcessingParameterField(
            "ZFIELD", self.tr("Поле отметки или глубины"),
            parentLayerParameterName="INPUT", optional=True,
            type=QgsProcessingParameterField.DataType.Numeric))
        self.addParameter(QgsProcessingParameterRasterLayer(
            "ZSURF", self.tr("Поверхность для отсчёта глубины"),
            optional=True))
        self.addParameter(QgsProcessingParameterRasterLayer(
            "REF", self.tr("Опорная поверхность (спрямление)"),
            optional=True))
        self.addParameter(QgsProcessingParameterRasterLayer(
            "REF_FLOOR", self.tr("Подошва для доли мощности"),
            optional=True))
        self.addParameter(QgsProcessingParameterNumber(
            "CELL", self.tr("Шаг по горизонтали, м (0 - от данных)"),
            QgsProcessingParameterNumber.Type.Double, defaultValue=0.0,
            minValue=0.0))
        self.addParameter(QgsProcessingParameterNumber(
            "CELLZ", self.tr("Шаг по вертикали, м (0 - от данных)"),
            QgsProcessingParameterNumber.Type.Double, defaultValue=0.0,
            minValue=0.0))
        self.addParameter(QgsProcessingParameterNumber(
            "MAXPTS", self.tr("Соседей на узел"),
            QgsProcessingParameterNumber.Type.Integer, defaultValue=16,
            minValue=2, maxValue=64))
        self.addParameter(QgsProcessingParameterBoolean(
            "AUTOVG", self.tr("Замерить вариограмму по данным"),
            defaultValue=True))
        self.addParameter(_advanced(QgsProcessingParameterEnum(
            "VGMODEL", self.tr("Модель вариограммы"),
            options=[self.tr("Сферическая"), self.tr("Показательная"),
                     self.tr("Гауссова")], defaultValue=0)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            "NUGGET", self.tr("Самородковый эффект"),
            QgsProcessingParameterNumber.Type.Double, defaultValue=0.0,
            minValue=0.0)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            "SILL", self.tr("Порог"),
            QgsProcessingParameterNumber.Type.Double, defaultValue=1.0,
            minValue=1e-9)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            "RANGE", self.tr("Длина связи, м"),
            QgsProcessingParameterNumber.Type.Double, defaultValue=100.0,
            minValue=1e-6)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            "ANISO", self.tr("Анизотропия (0 - от данных)"),
            QgsProcessingParameterNumber.Type.Double, defaultValue=0.0,
            minValue=0.0)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            "RADIUS", self.tr("Радиус поиска, м (0 - авто)"),
            QgsProcessingParameterNumber.Type.Double, defaultValue=0.0,
            minValue=0.0)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            "SECTORS", self.tr("Секторов поиска (0 - от данных)"),
            QgsProcessingParameterNumber.Type.Integer, defaultValue=0,
            minValue=0, maxValue=32)))
        self.addParameter(QgsProcessingParameterRasterDestination(
            "OUTPUT", self.tr("Куб значений")))
        self.addParameter(QgsProcessingParameterRasterDestination(
            "OUTVAR", self.tr("Куб дисперсии оценки")))
        _hints(self, HINTS_2_06)

    def _process(self, parameters, context, feedback):
        import numpy as np
        from .interp3d import (grid_nodes, sampling_spacing, grid_advice,
                               auto_grid, auto_sectors)
        from .variogram import auto_fit, assemble, MODELS
        from .kriging import ordinary
        from .flatten import to_flat

        feedback.pushInfo(_version_line())
        _saved = dict(parameters)
        src = self.parameterAsSource(parameters, "INPUT", context)
        cell = self.parameterAsDouble(parameters, "CELL", context)
        cellz = self.parameterAsDouble(parameters, "CELLZ", context)
        maxp = self.parameterAsInt(parameters, "MAXPTS", context)
        auto_vg = self.parameterAsBool(parameters, "AUTOVG", context)
        aniso = self.parameterAsDouble(parameters, "ANISO", context)
        radius = self.parameterAsDouble(parameters, "RADIUS", context)
        sectors = self.parameterAsInt(parameters, "SECTORS", context)
        out_path = self.parameterAsOutputLayer(parameters, "OUTPUT",
                                               context)
        var_path = self.parameterAsOutputLayer(parameters, "OUTVAR",
                                               context)
        xs, ys, zs, vals = _read_samples(self, parameters, context,
                                         feedback)
        pts = np.column_stack([xs, ys, zs])
        vals = np.asarray(vals, dtype=float)
        feedback.pushInfo(self.tr("Проб: %d.") % len(vals))
        if len(vals) > 20000:
            feedback.pushWarning(self.tr(
                "Проб очень много. Кригинг держит матрицы размером "
                "с число проб, узлы считаются мелкими порциями, "
                "и счёт будет долгим. Проредите пробы либо "
                "укрупните шаг сетки."))

        # Спрямление идёт до замера вариограммы: модель должна быть
        # снята в тех же координатах, в которых пойдёт расчёт.
        ref = self.parameterAsRasterLayer(parameters, "REF", context)
        ref_fl = self.parameterAsRasterLayer(parameters, "REF_FLOOR",
                                             context)
        roof_a = roof_gt = floor_a = None
        if ref is not None:
            roof_a, roof_gt = _read_surface(ref)
            if roof_a is None:
                raise QgsProcessingException(self.tr(
                    "Опорная поверхность не открылась."))
            if ref_fl is not None:
                floor_a, _gt2 = _read_surface(ref_fl)
                if floor_a is None or floor_a.shape != roof_a.shape:
                    raise QgsProcessingException(self.tr(
                        "Подошва не открылась либо не совпадает "
                        "с кровлей по сетке."))
            fz = to_flat(pts[:, 0], pts[:, 1], pts[:, 2], roof_a,
                         roof_gt, floor=floor_a)
            keep = np.isfinite(fz)
            if int(keep.sum()) < 2:
                raise QgsProcessingException(self.tr(
                    "Опорная поверхность не покрывает пробы."))
            if int(keep.sum()) < len(fz):
                feedback.pushWarning(self.tr(
                    "Вне опорной поверхности пропущено проб: %d.")
                    % int((~keep).sum()))
            pts = np.column_stack([pts[keep, 0], pts[keep, 1],
                                   fz[keep]])
            vals = vals[keep]

        net = sampling_spacing(pts)
        auto = auto_grid(*net) if net else None
        if sectors <= 0:
            sectors = auto_sectors(net[2] if net else None)
            feedback.pushInfo(self.tr(
                "Секторов поиска от данных: %d.") % sectors)
        if cell <= 0:
            cell = auto["cell"] if auto else 25.0
            feedback.pushInfo(self.tr("Шаг по горизонтали от данных: "
                                      "%.1f м.") % cell)
        if cellz <= 0:
            cellz = auto["cellz"] if auto else 5.0
            feedback.pushInfo(self.tr("Шаг по вертикали от данных: "
                                      "%.2f м.") % cellz)
        if net:
            feedback.pushInfo(self.tr(
                "Сеть: шаг по вертикали %.2f м, шаг в плане %.0f м, "
                "замеров в одной точке плана %d.") % net)

        if auto_vg:
            plan = auto_fit(pts, vals, nlags=12, direction="plan")
            vert = auto_fit(pts, vals, nlags=12, direction="vert")
            vm = assemble(plan, vert, float(np.var(vals)))
            feedback.pushInfo(self.tr(
                "Вариограмма в плане: %s, длина связи %.0f м, пар %d.")
                % (plan["kind"], plan["range"], plan["n_pairs"]))
            feedback.pushInfo(self.tr(
                "Вариограмма по вертикали: длина связи %.1f м, "
                "самородок %.3f, пар %d.")
                % (vert["range"], vert["nugget"], vert["n_pairs"]))
            if aniso <= 0:
                aniso = vm["anisotropy"]
        else:
            vm = {"kind": MODELS[self.parameterAsEnum(
                      parameters, "VGMODEL", context)],
                  "nugget": self.parameterAsDouble(parameters, "NUGGET",
                                                   context),
                  "sill": self.parameterAsDouble(parameters, "SILL",
                                                 context),
                  "range": self.parameterAsDouble(parameters, "RANGE",
                                                  context)}
            if aniso <= 0:
                aniso = 1.0
        feedback.pushInfo(self.tr(
            "Модель: %s, самородок %.3f, порог %.3f, длина связи "
            "%.0f м, анизотропия %.3f.")
            % (vm["kind"], vm["nugget"], vm["sill"], vm["range"], aniso))
        if net and net[1] > 0.5 * vm["range"]:
            feedback.pushWarning(self.tr(
                "Шаг сети %.0f м больше половины длины связи %.0f м. "
                "На такой сети кригинг обычно не точнее обратных "
                "расстояний: соседние скважины почти ничего не знают "
                "друг о друге. Дисперсия оценки при этом остаётся "
                "полезной.") % (net[1], vm["range"]))

        pad = cell
        x0, x1 = pts[:, 0].min() - pad, pts[:, 0].max() + pad
        y0, y1 = pts[:, 1].min() - pad, pts[:, 1].max() + pad
        z0, z1 = pts[:, 2].min() - cellz, pts[:, 2].max() + cellz
        nx = max(int(np.ceil((x1 - x0) / cell)), 1)
        ny = max(int(np.ceil((y1 - y0) / cell)), 1)
        nz = max(int(np.ceil((z1 - z0) / cellz)) + 1, 1)
        feedback.pushInfo(self.tr("Сетка: %d x %d x %d, узлов %d")
                          % (nx, ny, nz, nx * ny * nz))
        for note in grid_advice(nx, ny, nz, cell,
                                net[1] if net else None):
            feedback.pushWarning(self.tr("Сетка: %s.") % note)

        nodes = grid_nodes(x0, y1, z0, nx, ny, nz, cell, cell, cellz)
        vol = np.full(nx * ny * nz, np.nan)
        dsp = np.full(nx * ny * nz, np.nan)
        per_level = nx * ny
        step = max(nz // 20, 1)
        for k in range(nz):
            if feedback.isCanceled():
                break
            a, b = k * per_level, (k + 1) * per_level
            here = nodes[a:b]
            if roof_a is not None:
                nz_f = to_flat(here[:, 0], here[:, 1], here[:, 2],
                               roof_a, roof_gt, floor=floor_a)
                here = np.column_stack([here[:, 0], here[:, 1], nz_f])
            est, var = ordinary(pts, vals, here, vm,
                                radius=(radius if radius > 0 else None),
                                max_points=maxp, sectors=sectors,
                                anisotropy=aniso)
            vol[a:b] = est
            dsp[a:b] = var
            if k % step == 0:
                feedback.setProgress(100.0 * k / max(nz, 1))
        vol = vol.reshape(nz, ny, nx)
        dsp = dsp.reshape(nz, ny, nx)

        filled = int(np.isfinite(vol).sum())
        feedback.pushInfo(self.tr("Заполнено узлов: %d из %d")
                          % (filled, vol.size))
        if filled:
            feedback.pushInfo(self.tr(
                "Дисперсия оценки: %.4f .. %.4f, среднее %.4f.")
                % (float(np.nanmin(dsp)), float(np.nanmax(dsp)),
                   float(np.nanmean(dsp))))
            lo, hi = float(np.nanmin(vol)), float(np.nanmax(vol))
            dlo, dhi = float(vals.min()), float(vals.max())
            feedback.pushInfo(self.tr(
                "Значения: %.3f .. %.3f, в пробах %.3f .. %.3f.")
                % (lo, hi, dlo, dhi))
            if lo < dlo or hi > dhi:
                # Веса кригинга бывают отрицательными, и оценка может
                # выйти за размах данных. Для содержаний это означает
                # отрицательные значения там, где их быть не может.
                feedback.pushWarning(self.tr(
                    "Оценка вышла за размах проб. У кригинга веса "
                    "бывают отрицательными, и на содержаниях это даёт "
                    "значения ниже нуля. Гауссова модель к этому "
                    "склонна сильнее прочих: попробуйте сферическую "
                    "или поднимите самородок."))

        gt = (x0, cell, 0.0, y1, 0.0, -cell)
        crs = src.sourceCrs()
        wkt = crs.toWkt() if crs is not None else ""
        names = [self.tr("уровень %d") % (k + 1) for k in range(nz)]
        meta = {"Z0": "%.6f" % z0, "DZ": "%.6f" % cellz}
        _write_grid_tiff(out_path, [vol[k] for k in range(nz)], gt, wkt,
                         float("nan"), nx, ny, names, meta=meta)
        _write_grid_tiff(var_path, [dsp[k] for k in range(nz)], gt, wkt,
                         float("nan"), nx, ny, names, meta=meta)
        _save_values(self, _saved)
        return {"OUTPUT": out_path, "OUTVAR": var_path}


ALGORITHMS = [
    BedAssembleAlgorithm,
    BedCalculatorAlgorithm,
    BedToBlockModelAlgorithm,
    SectionSurfacesToMeshAlgorithm,
    DomainsToGridAlgorithm,
    ReserveDeltaAlgorithm,
    Demo3DPointsAlgorithm,
    Interp3DAlgorithm,
    Mba3DAlgorithm,
    CubeToBlocksAlgorithm,
    CubeVoxelBodyAlgorithm,
    CrossValidateAlgorithm,
    Kriging3DAlgorithm,
    PolyhedralDemoAlgorithm,
    DemoMapAlgorithm,
]
