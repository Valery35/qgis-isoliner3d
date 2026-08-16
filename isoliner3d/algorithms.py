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

GROUP4 = _tr("Пласт и блочная модель")
GROUP4_ID = "bed_block_model"
GRP_MESH3D = _tr("Поверхности 3D")

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
                     band_names=None):
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
            fields.append(QgsField(nm, tp))
        for nm in pnames:
            fields.append(QgsField(nm, QVariant.Double))
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
                    continue
                v = ft[field] if field in [f.name() for f in src.fields()] \
                    else None
                d[key] = (float(v) if v is not None else 0.0, ft.geometry())
            return d

        db = _key_vals(before)
        da = _key_vals(after)
        fields = QgsFields()
        for nm in ("row", "col", "lay"):
            fields.append(QgsField(nm, QVariant.Int))
        for nm in ("before", "after", "delta"):
            fields.append(QgsField(nm, QVariant.Double))
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
    LIKE, PIXEL, CELLS, FIELDS = "LIKE", "PIXEL", "CELLS", "FIELDS"
    OUTPUT_MAP = "OUTPUT_MAP"
    EXTENT = "EXTENT"
    NX = "NX"
    THICKNESS = "THICKNESS"
    BASE = "BASE"
    N_BEDS = "N_BEDS"
    AS_TIN = "AS_TIN"
    OUTPUT = "OUTPUT"

    _KINDS = ("bed", "suite", "cube", "tetra", "map")

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
                     self.tr("Куб"), self.tr("Тетраэдр"),
                     self.tr("Карта (растр для текстуры)")],
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
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Тело (демо)"),
            QgsProcessing.SourceType.TypeVectorPolygon, optional=True))
        self.addParameter(QgsProcessingParameterRasterDestination(
            self.OUTPUT_MAP, self.tr("Карта (демо)"), optional=True))

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
                pr.addAttributes([QgsField("bed", QVariant.Int),
                                  QgsField("watertight", QVariant.Int)])
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

    def _process(self, parameters, context, feedback):
        from . import polyhedral as poly
        feedback.pushInfo(_version_line())
        _saved = dict(parameters)
        idx = self.parameterAsEnum(parameters, self.EXAMPLE, context)
        kind = self._KINDS[idx]
        if kind == "map":
            res = self._make_map(parameters, context, feedback)
            _save_values(self, _saved)
            return res
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
        fields.append(QgsField("name", QVariant.String))
        fields.append(QgsField("kind", QVariant.String))
        fields.append(QgsField("patches", QVariant.Int))
        fields.append(QgsField("watertight", QVariant.Int))
        fields.append(QgsField("bed", QVariant.Int))
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


ALGORITHMS = [
    BedAssembleAlgorithm,
    BedCalculatorAlgorithm,
    BedToBlockModelAlgorithm,
    SectionSurfacesToMeshAlgorithm,
    DomainsToGridAlgorithm,
    ReserveDeltaAlgorithm,
    PolyhedralDemoAlgorithm,
]
