# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Двуязычие интерфейса (RU/EN).

Простой словарный слой: исходные строки в коде - русские, при английской
локали QGIS они подменяются на английские по таблице TRANSLATIONS. Если
перевода нет, возвращается исходная (русская) строка - плагин остаётся
рабочим. Модуль не импортирует QGIS на верхнем уровне, поэтому таблицу
переводов можно проверять обычным Python (см. tests).

Язык определяется по настройкам QGIS один раз, лениво, при первом вызове tr().
Для тестов и принудительного переключения есть set_language().
"""

_LANG = None  # 'ru' | 'en' (None = ещё не определён)


def set_language(lang):
    """Принудительно задать язык ('ru'/'en'/'en_US'/...). None - сбросить."""
    global _LANG
    if lang is None:
        _LANG = None
        return
    code = str(lang).strip().lower().replace("-", "_").split("_")[0]
    _LANG = "ru" if code == "ru" else "en"


def language():
    """Текущий язык ('ru'/'en'); инициализирует по QGIS при необходимости."""
    if _LANG is None:
        init_from_qgis()
    return _LANG or "en"


def init_from_qgis():
    """Определить язык интерфейса по настройкам QGIS. По умолчанию 'en'."""
    loc = ""
    try:
        from qgis.core import QgsApplication
        loc = QgsApplication.instance().locale() or ""
    except Exception:
        loc = ""
    if not loc:
        try:
            from qgis.PyQt.QtCore import QSettings
            s = QSettings()
            override = s.value("locale/overrideFlag", False, type=bool)
            loc = s.value("locale/userLocale", "") if override else ""
        except Exception:
            loc = ""
    set_language(loc or "en")
    return _LANG


def tr(s):
    """Перевести строку s на активный язык. RU - исходник, EN - по таблице."""
    if _LANG is None:
        init_from_qgis()
    if _LANG == "en":
        return TRANSLATIONS.get(s, s)
    return s


def missing_keys(keys):
    """Какие из переданных русских строк не имеют английского перевода.

    Удобно для теста покрытия: keys - множество строк, реально обёрнутых в
    _tr()/tr() в коде (извлекается AST-обходом)."""
    return [k for k in keys if k not in TRANSLATIONS]


# --- Таблица переводов RU -> EN -------------------------------------------
# Ключ - русская строка ровно как в коде (включая %d/%s, переносы, символы).
# Значение - английский перевод. Покрывает статический интерфейс:
# имена инструментов, подписи параметров, варианты списков, панели справки,
# живые подписи виджетов. Логи и HTML-отчёты переводятся отдельным проходом.

# --- Таблица переводов RU -> EN (только 3D-просмотр) --------------------
TRANSLATIONS = {
    '(нет)': '(none)',
    '1.01 Собрать грид пласта': '1.01 Assemble a bed grid',
    '1.02 Калькулятор пласта': '1.02 Bed calculator',
    '1.03 Грид пласта в блочную модель': '1.03 Bed grid to a block model',
    '1.04 Поверхности в 3D (меши)': '1.04 Surfaces to 3D (meshes)',
    '1.05 Домены в канал пласта': '1.05 Domains to a bed band',
    '1.06 Разность запасов (списание)': '1.06 Reserve difference (write-off)',
    '1.07 Создать пример данных (демо)': '1.07 Create sample data (demo)',
    '3D-просмотр недоступен в этой установке плагина.':
        'The 3D viewer is not available in this plugin installation.',
    '3D-просмотр поверхностей': '3D surface viewer',
    '3D-просмотр поверхностей Isoliner': 'Isoliner 3D surface viewer',
    '3D-просмотр поверхностей…': '3D surface viewer…',
    'HTML-файлы (*.html)': 'HTML files (*.html)',
    'Isoliner3D': 'Isoliner3D',
    'Isoliner3D - 3D-просмотр поверхностей': 'Isoliner3D - 3D surface viewer',
    'Isoliner3D развивается на задачах реальных предприятий. Если вашему '
    'производству не хватает функции - напишите нам: '
    'https://www.informpp.ru/главная-страница/предприятиям':
        'Isoliner3D grows on the tasks of real mining operations. If your '
        'production is missing a feature - contact us: '
        'https://www.informpp.ru/главная-страница/предприятиям',
    'Авто': 'Auto',
    'Блоков выгружено: %d.': 'Blocks exported: %d.',
    'Блочная модель (центроиды)': 'Block model (centroids)',
    'Блочная модель: %s': 'Block model: %s',
    'В определении разреза нет полей ox и oy: чертёж наложить не по чему. '
    'Постройте разрез текущей версией Isoliner.':
        'The section definition has no ox and oy fields: there is nothing to '
        'drape the drawing by. Build the section with the current version of '
        'Isoliner.',
    'Векторы': 'Vectors',
    'Вертикальное преувеличение': 'Vertical exaggeration',
    'Все': 'All',
    'Выдать как TIN (триангулировать)': 'Output as TIN (triangulate)',
    'Граней: %d.': 'Patches: %d.',
    'Грид не открылся.': 'The grid did not open.',
    'Грид не открылся: %s': 'Grid could not be opened: %s',
    'Грид пласта': 'Bed grid',
    'Грид пласта (канал 1 кровля, канал 2 подошва)':
        'Bed grid (band 1 roof, band 2 bottom)',
    'Грид пласта записан: каналов %d.': 'Bed grid written: %d bands.',
    'Грид пласта с каналом domain': 'Bed grid with a domain band',
    'Грид пласта с мощностью и запасами':
        'Bed grid with thickness and reserves',
    'Грид пропущен (мал или пуст): %s':
        'Grid skipped (too small or empty): %s',
    'Гриды не открылись.': 'The grids could not be opened.',
    'Группа: %s': 'Group: %s',
    'Диапазон Z: %.3f .. %.3f (ед. карты).':
        'Z range: %.3f .. %.3f (map units).',
    'Для текстуры нет видимых слоёв карты.':
        'There are no visible map layers for the texture.',
    'Домены записаны в канал %d. Ячеек в доменах: %d.':
        'Domains written to band %d. Cells in domains: %d.',
    'Загружено алгоритмов: %d': 'Algorithms loaded: %d',
    'Задайте грид или охват: карте нужны границы.':
        'Give a grid or an extent: the map needs its bounds.',
    'Задать свой цвет': 'Set a custom colour',
    'Запасы металла': 'Metal reserves',
    'Запасы руды': 'Ore reserves',
    'Инструмент: %s': 'Tool: %s',
    'Калькулятор пласта': 'Bed calculator',
    'Канал атрибута': 'Attribute band',
    'Канал высот (Z)': 'Elevation band (Z)',
    'Канал кровли': 'Roof band',
    'Канал плотности (пусто - брать значение выше)':
        'Density band (empty - use the value above)',
    'Канал подошвы': 'Bottom band',
    'Канал содержания (пусто - без содержания)':
        'Content band (empty - no content)',
    'Канал содержания вне грида.': 'The content band is outside the grid.',
    'Карта (демо)': 'Map (demo)',
    'Карта (растр для текстуры)': 'Map (raster for a texture)',
    'Карта для текстуры не отрисовалась.':
        'The map for the texture did not render.',
    'Карта проекта (текстура)': 'Project map (texture)',
    'Карта: %d на %d пикселей.': 'The map: %d by %d pixels.',
    'Карта: клеток координатной сетки': 'Map: graticule cells',
    'Карта: по охвату грида (растр)': 'Map: by the extent of a grid (raster)',
    'Карта: полей пластов': 'Map: bed fields',
    'Карта: сторона картинки, пикселей': 'Map: image side, pixels',
    'Контур подсчёта (полигоны, необязательно)':
        'Reserve contour (polygons, optional)',
    'Кровля (растр)': 'Roof (raster)',
    'Куб': 'Cube',
    'Куб (демо)': 'Cube (demo)',
    'Масштаб Z (вертикальное преувеличение)':
        'Z scale (vertical exaggeration)',
    'Меш записан: %s (узлов %d, треугольников %d).':
        'Mesh written: %s (%d nodes, %d triangles).',
    'Модель «было» (центроиды)': 'The "before" model (centroids)',
    'Модель «стало» (центроиды)': 'The "after" model (centroids)',
    'Мощность средняя / мин / макс': 'Thickness mean / min / max',
    'Мощность, ед. карты': 'Thickness, map units',
    'Нативный тип {0} на этой сборке недоступен - вывод как MultiPolygon Z. '
    'Нативный PolyhedralSurface / TIN и QSFCGAL доступны с QGIS 3.40.':
        'The native {0} type is unavailable on this build, output as '
        'MultiPolygon Z. Native PolyhedralSurface / TIN and QSFCGAL are '
        'available from QGIS 3.40.',
    'Не задан выходной слой. Укажите «Тело (демо)» (например, временный '
    'слой).':
        'No output layer is set. Specify "Body (demo)" (for example, a '
        'temporary layer).',
    'Не удалось добавить %s: %s': 'Could not add %s: %s',
    'Не удалось разнести свиту по слоям (%s) - вывод одним слоем.':
        'Could not split the suite into layers (%s) - output as one layer.',
    'Не удалось собрать геометрию из WKT.':
        'Could not build geometry from WKT.',
    'Ничего': 'None',
    'Нужен многоканальный грид пласта (каналы 1 и 2).':
        'A multiband bed grid is required (bands 1 and 2).',
    'Нужен хотя бы один грид.': 'At least one grid is required.',
    'Обновить сцену': 'Update the scene',
    'Оболочка НЕ замкнута: открытых рёбер %d.':
        'Shell is NOT closed: open edges %d.',
    'Оболочка замкнута (водонепроницаема).': 'Shell is closed (watertight).',
    'Объектов: %d, граней всего: %d.': 'Objects: %d, faces total: %d.',
    'Объём': 'Volume',
    'Окраска': 'Colouring',
    'Окраска: %s [%.4g … %.4g].': 'Colour: %s [%.4g … %.4g].',
    'Отметка залегания (подошва), ед. карты':
        'Base elevation (floor), map units',
    'Отметьте растр на вкладке «Слои» или тело на вкладке «Тела».':
        'Tick a raster on the «Layers» tab or a body on the «Bodies» tab.',
    'Отчёт (HTML)': 'Report (HTML)',
    'Охват (окно вида) - размещение и размер':
        'Extent (map view) - placement and size',
    'Палитра': 'Palette',
    'Папка для мешей (2DM)': 'Folder for meshes (2DM)',
    'Параметры (растры, берётся канал 1)':
        'Parameters (rasters, band 1 is taken)',
    'Параметры слоя': 'Layer settings',
    'Переводит многоканальный грид пласта в блочную модель: точку-центроид '
    'на каждую валидную ячейку. Атрибуты: строка и столбец ячейки, '
    'координаты, верх (top), низ (bot), мощность (thick), объём (vol), '
    'тоннаж руды (ore_t) через плотность и все каналы параметров под их '
    'именами из описаний.\n\nДальше работает векторный аппарат QGIS: фильтры '
    'выражениями, join внешних таблиц, калькулятор полей - модель '
    'наращивается атрибутами без пересоздания. Контур ограничивает выгрузку '
    'подсчётным блоком или доменом.\n\nПараметр «Слоёв по вертикали» делит '
    'каждую колонку на N блоков между кровлей и подошвой: у каждого свои '
    'z_from, z_to, номер слоя lay и доля объёма. Содержание копируется в '
    'под-блоки (по вертикали оно не разбурено). Это заготовка настоящей '
    '3D-модели.\n\nПлотность берётся из числа выше или, если задан «Канал '
    'плотности», из этого канала грида поячеечно - для переменной по площади '
    'плотности руды.':
        'Turns a multiband bed grid into a block model: a centroid point per '
        'valid cell. Attributes: the cell row and column, the coordinates, '
        'the top, the bottom (bot), the thickness (thick), the volume (vol), '
        'the ore tonnage (ore_t) via the density and all the parameter bands '
        'under their names from the descriptions.\n\nThen the QGIS vector '
        'toolbox works: expression filters, joins of external tables, the '
        'field calculator - the model grows by attributes without a rebuild. '
        'The contour limits the export to a reserve block or a '
        'domain.\n\nThe "Vertical layers" parameter splits every column into '
        'N blocks between the roof and the bottom: each gets its own z_from, '
        'z_to, the layer number lay and a share of the volume. The content '
        'is copied into the sub-blocks (it is not drilled vertically). This '
        'is a groundwork for a true 3D model.\n\nThe density is taken from '
        'the number above or, if a "Density band" is set, from that grid '
        'band per cell - for an areally variable ore density.',
    'Перестройка сцены: всего %.2f с (%s). Треугольников %s, вершин %s, '
    'объектов %d, прочитано гридов %d, взято из кэша %d.':
        'Scene rebuild: %.2f s in total (%s). Triangles %s, vertices %s, '
        'items %d, grids read %d, taken from cache %d.',
    'Пласт (демо)': 'Bed (demo)',
    'Пласт и блочная модель': 'Bed and block model',
    'Пластов в свите': 'Beds in the suite',
    'Плоскостей разреза: %d.': 'Section planes: %d.',
    'Плоскость разреза (линия)': 'Section plane (line)',
    'Плотность': 'Density',
    'Плотность руды, т/м³': 'Ore density, t/m³',
    'Площадь подсчёта': 'Computed area',
    'Поверхности 3D': '3D surfaces',
    'Поверхности-гриды': 'Surface grids',
    'Поверхность': 'Surface',
    'Подошва (растр)': 'Bottom (raster)',
    'Показано поверхностей: %d.': 'Surfaces shown: %d.',
    'Поле запаса': 'Reserve field',
    'Поле кода домена (число, необязательно)':
        'Domain code field (numeric, optional)',
    'Поле подписи скважин': 'Borehole label field',
    'Полигональные слои с Z (полиэдр, TIN, MultiPolygon Z). Отметьте тела '
    'для показа и нажмите «Обновить сцену».':
        'Polygon layers with Z (polyhedral, TIN, MultiPolygon Z). Tick the '
        'bodies to show and press «Rebuild scene».',
    'Полигоны доменов': 'Domain polygons',
    'Поля отметок': 'Elevation fields',
    'Пример': 'Example',
    'Прозрачность поверхностей (процентов)': 'Surface transparency (percent)',
    'Пропущено: %s': 'Skipped: %s',
    'Прореживание узлов (каждый N-й)': 'Node thinning (every Nth)',
    'Разбиение тела пласта (ячеек по стороне)':
        'Bed body resolution (cells per side)',
    'Разнос по Z (шаг вниз)': 'Z spacing (step down)',
    'Разнос по Z (шаг на каждый следующий грид)':
        'Z spacing (step per next grid)',
    'Разность (центроиды)': 'Difference (centroids)',
    'Растеризует полигоны доменов в добавочный канал грида пласта: каждой '
    'ячейке присваивается код домена, в который она попадает (0 - вне '
    'доменов). Код берётся из числового поля слоя или, если поле не задано, '
    'это порядковый номер объекта от 1. Каналы исходного грида сохраняются, '
    'канал «domain» дописывается последним.\n\nДальше домен работает как '
    'обычный параметр: калькулятор пласта считает по контуру домена, блочная '
    'модель фильтруется по коду. Списание запасов - это разность двух '
    'состояний домена: посчитайте запасы по контуру до и после погашения, '
    'вычтите. Контуры доменов должны лежать в той же системе координат, что '
    'и грид.':
        'Rasterises domain polygons into an extra band of the bed grid: each '
        'cell gets the code of the domain it falls into (0 - outside the '
        'domains). The code is taken from a numeric field of the layer or, '
        'if no field is set, it is the feature order number from 1. The '
        'source grid bands are kept, the "domain" band is appended '
        'last.\n\nThen the domain works as an ordinary parameter: the bed '
        'calculator sums over the domain contour, the block model is '
        'filtered by the code. Reserve write-off is the difference of two '
        'domain states: compute the reserves over the contour before and '
        'after the mining, subtract. The domain contours must be in the same '
        'CRS as the grid.',
    'Режим': 'Mode',
    'Руководство Isoliner3D в формате PDF': 'The Isoliner3D manual in PDF',
    'Сбоку': 'Side view',
    'Сверху': 'Top view',
    'Свита (стопка складчатых пластов)': 'Suite (stack of folded beds)',
    'Свита x%d (демо)': 'Suite x%d (demo)',
    'Свита загружена отдельными слоями по пласту: %d.':
        'Suite loaded as separate per-bed layers: %d.',
    'Свита: пласт %d': 'Suite: bed %d',
    'Свой цвет': 'Custom colour',
    'Свой цвет слоя': 'Custom layer colour',
    'Скважин: %d.': 'Boreholes: %d.',
    'Скважины (точки)': 'Boreholes (points)',
    'Слои': 'Layers',
    'Слой меша не загрузился: %s': 'Mesh layer failed to load: %s',
    'Слоёв по вертикали (деление колонки)': 'Vertical layers (column split)',
    'Смещение Z': 'Z offset',
    'Снимок PNG…': 'PNG snapshot…',
    'Снимок сохранён: %s': 'Snapshot saved: %s',
    'Собирает многоканальный грид пласта по конвенции плагина: канал 1 - '
    'кровля, канал 2 - подошва, каналы 3 и далее - параметры (содержание, '
    'минтип и любые другие). Кровля задаёт сетку результата; подошва и '
    'параметры билинейно приводятся к ней, поэтому исходные гриды могут '
    'иметь разные сетки. Имена каналов записываются в описания: «кровля», '
    '«подошва», далее имена слоёв параметров.\n\nОдин собранный файл кормит '
    '«Состав пласта на разрез» (каналы 1/2/3), 3D-просмотр (тела пластов) и '
    'экспорт в меши - это шаг к блочной модели, где новые параметры '
    'добавляются каналами.':
        'Assembles a multiband bed grid by the plugin convention: band 1 - '
        'the roof, band 2 - the bottom, bands 3 and further - parameters '
        '(content, mineral type and any others). The roof sets the output '
        'grid; the bottom and the parameters are resampled to it bilinearly, '
        'so the input grids may have different grids. The band names are '
        'written into the descriptions: roof, bottom, then the names of the '
        'parameter layers.\n\nOne assembled file feeds Bed composition on a '
        'section (bands 1/2/3), the 3D viewer (bed bodies) and the mesh '
        'export - a step towards a block model where new parameters are '
        'added as bands.',
    'Содержание (взвешенное по мощности)': 'Content (thickness-weighted)',
    'Создано: %s': 'Created: %s',
    'Создаёт демонстрационную полиэдральную поверхность, чтобы посмотреть '
    'сам тип геометрии в 3D и проверить его на своей сборке QGIS. Варианты '
    'примера: тело пласта, свита (стопка складчатых пластов, каждый пласт '
    'грузится отдельным слоем для управления видимостью и красится своим '
    'цветом), куб и тетраэдр. Тело пласта - водонепроницаемая оболочка из '
    'кровли, подошвы и боковой юбки, тот же приём, что и в будущем экспорте '
    'тела пласта. Плановое положение и размер берутся из охвата (окна вида), '
    'по вертикали тело занимает от отметки залегания до отметки плюс '
    'мощность. Тип геометрии плоский, поэтому в 2D-виде Z не виден - '
    'диапазон Z печатается в журнал, а само тело удобно смотреть в окне '
    'Модули - Isoliner3D - 3D-просмотр поверхностей, вкладка Тела. Нативный '
    'PolyhedralSurface Z доступен с QGIS 3.40, там же работает плагин '
    'QSFCGAL (резка и булевы операции над телами). На более старых сборках '
    'вывод деградирует до MultiPolygon Z. Флаг TIN выдаёт триангулированную '
    'поверхность (тип TIN Z).':
        'Creates a demonstration polyhedral surface so you can see the '
        'geometry type in 3D and check it on your QGIS build. Example '
        'options: a bed body, a suite (a stack of folded beds, each bed '
        'loaded as a separate layer for visibility control and coloured on '
        'its own), a cube and a tetrahedron. The bed body is a watertight '
        'shell of roof, floor and side skirt, the same approach as the '
        'upcoming bed-body export. The plan position and size come from the '
        'extent (map view); vertically the body spans from the base '
        'elevation up to that elevation plus the thickness. The geometry '
        'type is flat, so Z is not visible in the 2D view - the Z range is '
        'printed to the log, and the body itself is best viewed in Plugins - '
        'Isoliner - 3D surface viewer, the Bodies tab. A native '
        'PolyhedralSurface Z is available from QGIS 3.40, where the QSFCGAL '
        'plugin also works (cutting and boolean operations on bodies). On '
        'older builds the output degrades to MultiPolygon Z. The TIN flag '
        'outputs a triangulated surface (TIN Z type).',
    'Создаёт демонстрационные данные, чтобы проверить показ на своей сборке '
    'QGIS, не трогая рабочие слои.\n\nТела с высотой Z: тело пласта '
    '(водонепроницаемая оболочка из кровли, подошвы и боковой юбки), свита '
    'складчатых пластов (каждый грузится отдельным слоем и красится своим '
    'цветом), куб и тетраэдр. Плановое положение и размер берутся из охвата, '
    'по вертикали тело занимает от отметки залегания до отметки плюс '
    'мощность. Тип геометрии плоский, поэтому в 2D-виде Z не виден, диапазон '
    'печатается в журнал, а само тело удобно смотреть в окне Модули - '
    'Isoliner3D - 3D-просмотр поверхностей, вкладка Тела. Нативный '
    'PolyhedralSurface Z доступен с QGIS 3.40, на более старых сборках вывод '
    'деградирует до MultiPolygon Z. Флаг TIN выдаёт триангулированную '
    'поверхность.\n\nКарта (растр для текстуры): трёхканальная картинка для '
    'проверки наложения текстуры на поверхность. Сделана нарочно '
    'проверочной: цветные поля пластов с кривой границей, тонкие изолинии, '
    'координатная сетка квадратными клетками и разные по цвету метки в '
    'четырёх углах (по часовой стрелке от левого верхнего: красная, зелёная, '
    'синяя, жёлтая). Наложение ошибается тремя типовыми способами, и каждый '
    'эта карта показывает сразу. Переворот по вертикали виден по меткам в '
    'углах, сдвиг и перекос по сетке, растяжение по одной оси по '
    'неквадратности клеток. Охват для карты лучше задавать полем «Карта: по '
    'охвату грида»: она ляжет ровно по границам поверхности.':
        'Creates demonstration data, so that you can check the display on '
        'your own QGIS build without touching the working layers.\n\nBodies '
        'with a Z elevation: a bed body (a watertight shell of a roof, a '
        'bottom and a side skirt), a suite of folded beds (each loaded as '
        'its own layer with its own colour), a cube and a tetrahedron. The '
        'plan position and the size come from the extent, vertically the '
        'body runs from the base elevation up to the base plus the '
        'thickness. The geometry type is flat, so Z is not visible in the 2D '
        'view, the range is printed to the log, and the body itself is best '
        'looked at in Plugins - Isoliner3D - 3D surface viewer, the Bodies '
        'tab. A native PolyhedralSurface Z is available from QGIS 3.40, on '
        'older builds the output degrades to MultiPolygon Z. The TIN flag '
        'yields a triangulated surface.\n\nMap (raster for a texture): a '
        'three-band image to check the draping of a texture onto a surface. '
        'It is deliberately a test pattern: coloured bed fields with a '
        'curved boundary, thin contour lines, a graticule of square cells '
        'and differently coloured marks in the four corners (clockwise from '
        'the top left: red, green, blue, yellow). Draping fails in three '
        'typical ways, and this map shows each of them at once. A vertical '
        'flip shows up in the corner marks, a shift or a skew in the '
        'graticule, a stretch along one axis in cells that stop being '
        'square. The extent for the map is best set by the «Map: by the '
        'extent of a grid» field: it will land exactly on the surface '
        'bounds.',
    'Сохранить снимок': 'Save the snapshot',
    'Справка (руководство PDF)…': 'Help (PDF manual)…',
    'Сторона текстуры (пикселей)': 'Texture side (pixels)',
    'Сторона текстуры по длинной оси охвата. Больше значение - детальнее '
    'карта на поверхности и больше видеопамяти.':
        'The texture side along the longer axis of the extent. A larger '
        'value means a more detailed map on the surface and more video '
        'memory.',
    'Суммарное списание по полю %s: %.6g.':
        'Total write-off by the %s field: %.6g.',
    'Сцена: %s треугольников, объектов %d, %.2f с.':
        'Scene: %s triangles, %d items, %.2f s.',
    'Считает по многоканальному гриду пласта (канал 1 - кровля, канал 2 - '
    'подошва): мощность, объём, тоннаж руды через плотность и, если задан '
    'канал содержания, средневзвешенное по мощности содержание и тоннаж '
    'металла. Сводка - по всей площади пласта или внутри контура (полигоны '
    'подсчётного блока, домена).\n\nРезультат - грид пласта с дописанными '
    'каналами «мощность» и «запасы руды, т/ячейку» и HTML-отчёт со сводкой. '
    'Ячейки с мощностью меньше нуля (пересечение поверхностей) обнуляются и '
    'считаются отдельно.':
        'Computes over a multiband bed grid (band 1 - the roof, band 2 - the '
        'bottom): the thickness, the volume, the ore tonnage via the density '
        'and, if a content band is set, the thickness-weighted mean content '
        'and the metal tonnage. The summary covers the whole bed area or the '
        'inside of a contour (polygons of a reserve block or a '
        'domain).\n\nThe result is a bed grid with the appended bands '
        '"thickness" and "ore, t/cell" plus an HTML report. Cells with a '
        'negative thickness (crossing surfaces) are zeroed and counted '
        'separately.',
    'Считает разность двух блочных моделей по ячейкам с одинаковыми row и '
    'col: сколько запаса убыло между состояниями «было» и «стало». Для '
    'каждой ячейки вычитается выбранное поле (по умолчанию ore_t), результат '
    '- точки со значениями delta (было минус стало), before и after.\n\nЭто '
    'прямой путь оперативного списания: модель до погашения камер минус '
    'модель после - и сумма delta по контуру даёт списанный тоннаж. Модели '
    'должны быть построены из одного грида (совпадающая нарезка row и col).':
        'Computes the difference of two block models over the cells with the '
        'same row and col: how much reserve was lost between the "before" '
        'and "after" states. For each cell the chosen field (ore_t by '
        'default) is subtracted, the result is points with delta (before '
        'minus after), before and after values.\n\nThis is the direct path '
        'of operational write-off: the model before mining the chambers '
        'minus the model after - and the sum of delta over the contour gives '
        'the written-off tonnage. The models must be built from the same '
        'grid (a matching row and col split).',
    'Текстур: %d (из кэша %d).': 'Textures: %d (%d from cache).',
    'Текстура не построена: %s': 'The texture was not built: %s',
    'Текстура: %s': 'Texture: %s',
    'Тел пластов: %d.': 'Bed bodies: %d.',
    'Тел: %d.': 'Bodies: %d.',
    'Тела': 'Bodies',
    'Тело (демо)': 'Body (demo)',
    'Тело пласта': 'Bed body',
    'Тетраэдр': 'Tetrahedron',
    'Тетраэдр (демо)': 'Tetrahedron (demo)',
    'Тип геометрии: %s Z.': 'Geometry type: %s Z.',
    'Укажите файл для карты в поле «Карта (демо)».':
        'Give a file for the map in the «Map (demo)» field.',
    'Файл руководства не найден: %s': 'The manual file was not found: %s',
    'Фильтр слоёв…': 'Filter layers…',
    'Чертежа для разреза %d в выбранных слоях нет: похоже, чертёж и '
    'определение из разных построений.':
        'There is no drawing for section %d in the chosen layers: the '
        'drawing and the definition appear to come from different builds.',
    'Чертежи: %s.': 'Drawings: %s.',
    'Чертёж разреза (слой или группа)': 'Section drawing (layer or group)',
    'Чертёж разреза в координатах «расстояние вдоль линии на отметку». '
    'Ложится текстурой на ленту разреза. Годится группа слоёв целиком.':
        'The section drawing in «distance along the line by elevation» '
        'coordinates. It is draped as a texture onto the section ribbon. A '
        'whole layer group will do.',
    'Чертёж разреза не наложился: %s':
        'The section drawing was not draped: %s',
    'Чертёж разреза не отрисовался.': 'The section drawing did not render.',
    'Экспортирует гриды поверхностей в mesh-слои стандартного формата 2DM '
    '(MDAL). Такие слои понимают профильный инструмент QGIS, '
    'mesh-калькулятор, штатный 3D-вид и сторонние программы, а пачка '
    'горизонтов кровля-подошва уходит в меши без ручных конвертаций.\n\nК '
    'отметкам при записи применяется вертикальное преобразование Z\' = Z * '
    'масштаб + смещение: масштаб даёт вертикальное преувеличение, смещение '
    'разносит горизонты по высоте. Разнос по Z сдвигает каждый следующий '
    'грид на шаг вниз, превращая слипшуюся стопку в читаемую этажерку. '
    'Прореживание уменьшает количество узлов на крупных гридах.\n\nСлои '
    'загружаются в проект и получают 3D-отображение автоматически. Если '
    'сцена уже открыта, включите новые слои в её списке. Ячейки без данных '
    'пропускаются.':
        'Exports surface grids into mesh layers of the standard 2DM format '
        '(MDAL). Such layers are understood by the QGIS profile tool, the '
        'mesh calculator, the built-in 3D view and third-party software, and '
        'a stack of top-bottom horizons goes to meshes without manual '
        'conversions.\n\nA vertical transform Z\' = Z * scale + offset is '
        'applied on write: the scale gives vertical exaggeration, the offset '
        'separates horizons in height. The Z spacing shifts every next grid '
        'one step down, turning a collapsed stack into a readable shelf. '
        'Thinning reduces the node count on large grids.\n\nThe layers are '
        'loaded into the project and get 3D rendering automatically. If a '
        'scene is already open, enable the new layers in its layer list. '
        'Cells without data are skipped.',
    'Ячеек с отрицательной мощностью': 'Cells with a negative thickness',
    'векторы': 'vectors',
    'запасы руды, т/ячейку': 'ore, t/cell',
    'канал %d': 'band %d',
    'кровля': 'roof',
    'меши': 'meshes',
    'мощность': 'thickness',
    'окраска': 'colouring',
    'подошва': 'bottom',
    'сцена': 'scene',
    'чтение': 'reading',
}
