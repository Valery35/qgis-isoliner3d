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
    'Охват площадки': 'Site extent',
    'Площадка по умолчанию: %.0f x %.0f м от начала координат. '
    'Задайте охват, чтобы положить пример на своё место.':
        'Default site: %.0f x %.0f m from the origin. Set an extent '
        'to put the example in its place.',
    'Площадка, на которой ставятся скважины. Пусто означает '
    'километр от начала координат, об этом пишется в журнал.':
        'The site the boreholes are placed on. Empty means a kilometre '
        'from the origin, which is written to the log.',
    '1.08 Карта для текстуры (демо)':
        '1.08 A map for a texture (demo)',
    'Границы карты, когда грид не задан. Пусто означает взять охват окна '
    'вида.':
        'The bounds of the map when no grid is set. Empty means taking the '
        'extent of the view window.',
    'Охват (если грид не задан)':
        'Extent (when no grid is set)',
    'Рисует проверочную карту с координатной сеткой и полями '
    'пластов.\n\nНужна, чтобы посмотреть, как ложится текстура на поверхность'
    ' в окне просмотра: на настоящей карте перекосы и растяжения видно хуже, '
    'чем на клетках.\n\nОхват берётся из готового грида, если он задан, иначе'
    ' из поля охвата: карта тогда ляжет ровно по границам поверхности.':
        'Draws a check map with a coordinate grid and bed fields.\n\nIt is '
        'there to see how a texture lands on a surface in the viewer: on a '
        'real map skews and stretches show up worse than on squares.\n\nThe '
        'extent is taken from a ready grid when one is given, otherwise from '
        'the extent field: the map then lands exactly on the bounds of the '
        'surface.',
    'Что именно создать: тело пласта, свиту складчатых пластов, куб или '
    'тетраэдр. Карта для текстуры вынесена в отдельный инструмент 1.08.':
        'What exactly to create: a bed body, a pile of folded beds, a cube or'
        ' a tetrahedron. The map for a texture has moved to the separate tool'
        ' 1.08.',
    '2.05 Проверка интерполяции':
        '2.05 Check of the interpolation',
    'Грид, от которого отсчитывается глубина. Тот же, что и в 2.02.':
        'The grid the depth is measured from. The same one as in 2.02.',
    'Для отметки из поля это сама отметка, для глубины это глубина вниз от '
    'поверхности.':
        'For elevation from a field this is the elevation itself, for depth '
        'it is the depth measured down from the surface.',
    'Источник отметки должен совпадать с тем, что задан в 2.02: иначе '
    'проверяется не та расстановка точек.':
        'The elevation source must match the one set in 2.02, otherwise a '
        'different arrangement of points is checked.',
    'Меняйте анизотропию, степень и число точек и смотрите на эти числа: '
    'правильного значения у них нет, есть лучшее на ваших данных.':
        'Change the anisotropy, the power and the number of points and watch '
        'these numbers: there is no right value for them, only the best one '
        'on your data.',
    'Метод, который собираетесь применять в 2.02. Проверка и нужна, чтобы '
    'выбрать между ними по числам, а не на глаз.':
        'The method you intend to use in 2.02. The check is there to choose '
        'between them by numbers rather than by eye.',
    'Не удалось создать слой невязок.':
        'Could not create the residual layer.',
    'Невязки проверки':
        'Check residuals',
    'Ноль берёт на одного больше, чем замеров в одной точке плана. Это тот же'
    ' подбор, что и в 2.02.':
        'Zero takes one more than the number of samples at one place in plan.'
        ' This is the same choice as in 2.02.',
    'Ноль берёт четверть охвата данных. Проба, вокруг которой точек не '
    'нашлось, остаётся непроверенной.':
        'Zero takes a quarter of the data extent. A sample with no points '
        'around it stays unchecked.',
    'Окружность вокруг пробы делится на равные части. На скважинной сети без '
    'этого ошибка выходит заметно больше.':
        'The circle around the sample is split into equal parts. On a '
        'borehole grid the error is noticeably larger without this.',
    'Отношение вертикального масштаба к горизонтальному. Подбирается как раз '
    'по ошибке проверки.':
        'The ratio of the vertical scale to the horizontal one. It is picked '
        'exactly by the error of this check.',
    'Ошибка: средняя %.4f, среднеквадратичная %.4f, смещение %+.4f.':
        'Error: mean %.4f, root mean square %.4f, bias %+.4f.',
    'Поле значения, по которому строится куб. Именно его и проверяем.':
        'The value field the cube is built from. That is what we check.',
    'Проба, вокруг которой точек меньше этого числа, остаётся непроверенной и'
    ' в ошибку не идёт.':
        'A sample with fewer points around it than this stays unchecked and '
        'does not enter the error.',
    'Пробы с полями value, model, resid и aresid. По ним видно не только '
    'величину промаха, но и где он случился.':
        'Samples with the fields value, model, resid and aresid. They show '
        'not only how large the miss is but where it happened.',
    'Проверено %d проб из %d: у остальных соседей не нашлось.':
        'Checked %d samples of %d: the rest found no neighbours.',
    'Проверяется проб: %d.':
        'Samples under check: %d.',
    'Размах данных %.4f, средняя ошибка это %.1f процента от него.':
        'Data spread %.4f, the mean error is %.1f per cent of it.',
    'Степень обратных расстояний. Подбирается по ошибке проверки вместе с '
    'анизотропией.':
        'The power of inverse distances. It is picked by the error of this '
        'check together with the anisotropy.',
    'Тот же слой проб, что подаётся в 2.02. Проверка идёт по самим пробам, '
    'куб для неё не нужен.':
        'The same layer of samples that goes into 2.02. The check runs on the'
        ' samples themselves, no cube is needed for it.',
    'Убирает каждую пробу по очереди, считает значение в её точке по '
    'остальным и сравнивает с настоящим.\n\nЭто единственный способ узнать, '
    'можно ли верить кубу: сравнивать построенное не с чем, а на глаз '
    'одинаково убедительно выглядят и хорошая модель, и вымысел.\n\nПараметры'
    ' задаются те же, что в 2.02. Меняя их и смотря на ошибку, подбирают '
    'анизотропию, степень и число соседей: правильного значения у них нет '
    'вообще, есть только лучшее на этих данных.\n\nВ журнал идут средняя '
    'ошибка, среднеквадратичная, смещение и доля ошибки от размаха данных. '
    'Смещение показывает, уводит ли модель в одну сторону: разброс и '
    'односторонний увод лечатся по-разному.\n\nПоля слоя: value настоящее '
    'значение, model посчитанное, resid разность, aresid её модуль.':
        'Removes each sample in turn, computes the value at its place from '
        'the rest and compares it with the real one.\n\nThis is the only way '
        'to learn whether the cube can be trusted: there is nothing to '
        'compare the built model with, and to the eye a good model and an '
        'invention look equally convincing.\n\nThe parameters are the same as'
        ' in 2.02. By changing them and watching the error one picks the '
        'anisotropy, the power and the number of neighbours: there is no '
        'right value for them at all, only the best one on this data.\n\nThe '
        'log gets the mean error, the root mean square one, the bias and the '
        'share of the error in the spread of the data. The bias shows whether'
        ' the model leans one way: scatter and a one-sided lean are cured '
        'differently.\n\nLayer fields: value the real value, model the '
        'computed one, resid the difference, aresid its absolute value.',
    'Блочная модель на конец периода. Блок, которого в ней нет, считается '
    'отработанным целиком.':
        'The block model at the end of the period. A block absent from it '
        'counts as mined out entirely.',
    'Триангулировать тело. Без этого выходят четырёхугольные грани, которые '
    'не всякий просмотрщик покажет.':
        'Triangulate the body. Without it the faces come out quadrilateral, '
        'and not every viewer shows those.',
    'Отметка подошвы. Свита строится вверх от неё.':
        'The elevation of the floor. The pile is built upwards from it.',
    'Грид пласта из 1.01. Первый канал кровля, второй подошва, по ним и '
    'считается мощность.':
        'The bed grid from 1.01. The first band is the roof, the second the '
        'floor, and the thickness follows from them.',
    'Грид пласта из 1.01. Колонка между кровлей и подошвой делится на блоки.':
        'The bed grid from 1.01. The column between the roof and the floor is'
        ' split into blocks.',
    'Грид пласта, к которому добавится канал домена.':
        'The bed grid a domain band will be added to.',
    'Блочная модель на начало периода. Сравнение идёт по совпадающим блокам, '
    'поэтому обе модели должны быть собраны на одной сетке.':
        'The block model at the start of the period. Comparison goes by '
        'matching blocks, so both models must be built on one grid.',
    'Грид подошвы. Там, где подошва выше кровли, мощность выходит '
    'отрицательной и ячейка уходит в пропуск.':
        'The grid of the floor. Where the floor is above the roof the '
        'thickness comes out negative and the cell becomes a gap.',
    'Канал подошвы в исходном гриде. Нужен, когда подошва лежит внутри '
    'многоканального.':
        'The floor band in the source grid. Needed when the floor sits inside'
        ' a multiband one.',
    'Сколько клеток координатной сетки нарисовать на карте.':
        'How many cells of the coordinate grid to draw on the map.',
    'Канал содержания. Пусто означает считать только объём и мощность, без '
    'запасов.':
        'The grade band. Empty means computing only volume and thickness, '
        'without reserves.',
    'Полигоны, за пределами которых ячейки в подсчёт не идут: подсчётный '
    'блок, лицензионная площадь.':
        'Polygons outside which cells do not enter the computation: a '
        'computation block, a licence area.',
    'Полигоны, за пределами которых блоки не выгружаются: подсчётный блок, '
    'лицензионная площадь.':
        'Polygons outside which blocks are not written out: a computation '
        'block, a licence area.',
    'Плотность руды. На неё умножается объём, чтобы получить массу: без неё в'
    ' отчёте будут кубометры, а не тонны.':
        'The ore density. The volume is multiplied by it to get mass: without'
        ' it the report is in cubic metres rather than tonnes.',
    'Плотность руды, если её нет отдельным каналом. На неё умножается объём '
    'блока.':
        'The ore density, when there is no band for it. The block volume is '
        'multiplied by it.',
    'Канал плотности в гриде. Пусто означает брать одно значение, заданное '
    'выше, на весь пласт.':
        'The density band in the grid. Empty means taking the single value '
        'set above for the whole bed.',
    'Полигоны доменов: сорта руды, участки, зоны. Ячейка получает код того '
    'домена, внутрь которого попала.':
        'Domain polygons: ore types, sites, zones. A cell takes the code of '
        'the domain it falls into.',
    'Что именно создать: тело пласта, свиту, карту для текстуры. От выбора '
    'зависит, какие поля ниже читаются.':
        'What exactly to create: a bed body, a pile, a map for a texture. '
        'Which fields below are read depends on the choice.',
    'Куда положить пример и какого размера. Пусто означает взять охват окна '
    'вида.':
        'Where to put the example and of what size. Empty means taking the '
        'extent of the view window.',
    'Числовое поле с кодом домена. Пусто означает нумеровать полигоны по '
    'порядку.':
        'The numeric field with the domain code. Empty means numbering the '
        'polygons in order.',
    'Поле запаса, разность которого считается: масса, объём, металл.':
        'The reserve field whose difference is computed: mass, volume, metal.',
    'Сколько полей пластов нарисовать на карте.':
        'How many bed fields to draw on the map.',
    'Куда положить файлы. Имя файла берётся от имени грида.':
        'Where to put the files. The file name is taken from the grid name.',
    'Гриды, которые надо отдать мешем. Каждый становится отдельным файлом '
    '2DM.':
        'The grids to be given out as meshes. Each becomes a separate 2DM '
        'file.',
    'Растр, по охвату которого делать карту. Нужен, чтобы текстура легла '
    'ровно на существующий грид.':
        'The raster whose extent the map is made to. Needed so the texture '
        'lands exactly on an existing grid.',
    'На сколько ячеек делится сторона тела. Мельче значит плавнее форма и '
    'больше треугольников.':
        'How many cells the side of the body is split into. Finer means a '
        'smoother shape and more triangles.',
    'На сколько блоков делить колонку по вертикали. Один блок даёт модель без'
    ' вертикальной разбивки, а мощность пласта тогда вся уходит в один слой.':
        'How many blocks to split the column into vertically. One block gives'
        ' a model without vertical division, and the whole thickness then '
        'falls into a single layer.',
    'Сколько пластов в свите. Каждый ложится своим телом со своим '
    'содержанием.':
        'How many beds in the pile. Each lies as its own body with its own '
        'grade.',
    'Многоканальный грид: канал 1 кровля, канал 2 подошва, дальше параметры. '
    'Этот порядок читают все остальные инструменты и окно просмотра.':
        'A multiband grid: band 1 the roof, band 2 the floor, then the '
        'parameters. Every other tool and the viewer read this order.',
    'Тот же грид пласта с добавленными каналами мощности и запасов на ячейку.':
        'The same bed grid with added bands of thickness and reserves per '
        'cell.',
    'Точка-центроид на блок с размером, объёмом и массой. Дальше работает '
    'обычный векторный аппарат QGIS.':
        'A centroid point per block with its size, volume and mass. The usual'
        ' QGIS vector machinery works from there.',
    'Тот же грид с добавленным каналом domain. Дальше по нему фильтруют '
    'подсчёт и красят сцену.':
        'The same grid with an added domain band. Filters for the computation'
        ' and colouring of the scene work from it.',
    'Центроиды с разностью по каждому блоку. Сумма поля по слою и есть '
    'списание за период.':
        'Centroids with the difference per block. The sum of the field over '
        'the layer is the write-off for the period.',
    'Слой с телами: полигоны с Z, годные для сцены и для подсчёта объёма.':
        'A layer with bodies: polygons with Z, fit for the scene and for '
        'volume computation.',
    'Картинка для текстуры: её можно натянуть на поверхность в окне '
    'просмотра.':
        'A picture for a texture: it can be stretched over a surface in the '
        'viewer.',
    'Дополнительные гриды, которые лягут отдельными каналами: содержание, '
    'плотность, домен. Берётся первый канал каждого.':
        'Extra grids that will become separate bands: grade, density, domain.'
        ' The first band of each is taken.',
    'Сторона картинки в пикселях. Крупнее значит чётче текстура и тяжелее '
    'файл.':
        'The side of the picture in pixels. Larger means a sharper texture '
        'and a heavier file.',
    'Сводка по контуру: площадь, объём, масса, среднее содержание. '
    'Открывается в браузере.':
        'A summary over the contour: area, volume, mass, mean grade. Opens in'
        ' a browser.',
    'Грид кровли пласта. Отметки в метрах, шаг и охват должны совпадать с '
    'подошвой: иначе мощность считать не по чему.':
        'The grid of the bed roof. Elevations in metres; the step and extent '
        'must match the floor, or there is nothing to compute the thickness '
        'from.',
    'Канал кровли в исходном гриде. Нужен, когда кровля лежит не первым '
    'каналом, а внутри многоканального.':
        'The roof band in the source grid. Needed when the roof is not the '
        'first band but sits inside a multiband one.',
    'Разнос поверхностей по вертикали. Пласты свиты иначе лежат вплотную и '
    'спорят за глубину.':
        'The spread of surfaces along the vertical. Otherwise the beds of a '
        'pile lie flush and fight for depth.',
    'Прореживание узлов. Каждый второй узел это вчетверо меньше '
    'треугольников, а форма пласта на глаз та же.':
        'Thinning of the nodes. Every second node is four times fewer '
        'triangles, and the shape of the bed looks the same.',
    'Мощность пласта в единицах карты. От неё зависит, видно ли тело при '
    'обычном вертикальном масштабе.':
        'The bed thickness in map units. Whether the body is visible at the '
        'usual vertical scale depends on it.',
    'Канал отметок в гриде. Для грида пласта это кровля или подошва, смотря '
    'что показывать.':
        'The elevation band in the grid. For a bed grid it is the roof or the'
        ' floor, depending on what to show.',
    'Сдвиг всех отметок по вертикали. Нужен, чтобы разнести пласты свиты и '
    'увидеть их по отдельности.':
        'A shift of all elevations along the vertical. Needed to separate the'
        ' beds of a pile and see them apart.',
    'Вертикальное преувеличение. Пласт в метр на площади в километр без него '
    'не разглядеть, но объём по такому мешу считать уже нельзя.':
        'Vertical exaggeration. A bed of one metre over a kilometre cannot be'
        ' seen without it, but volume can no longer be computed on such a '
        'mesh.',
    'Отношение вертикального масштаба к горизонтальному. Большая сглаживает '
    'по вертикали, малая сохраняет различие по глубине.':
        'The ratio of the vertical scale to the horizontal one. A large value'
        ' smooths along the vertical, a small one keeps the difference with '
        'depth.',
    'Фон во вмещающих породах. От него и от содержания в ядре\nсчитается '
    'отсечка, которой отделяется тело.':
        'The background in the host rock. The cutoff that separates the body '
        'is computed from it and from the core grade.',
    'Ноль берёт пятую часть расстояния между точками плана. Мельче делать '
    'незачем: данных в промежутке всё равно нет, а число узлов растёт как '
    'квадрат.':
        'Zero takes a fifth of the distance between places in plan. Finer is '
        'pointless: there is no data in between anyway, and the node count '
        'grows as a square.',
    'Ноль берёт половину шага опробования. Крупнее значит слить соседние '
    'замеры и потерять различие по глубине.':
        'Zero takes half the sampling step. Coarser means merging '
        'neighbouring samples and losing the difference with depth.',
    'На сколько интервалов разложить значение. Номер интервала пишется в поле'
    ' cls и годится для окраски.':
        'How many intervals to split the value into. The interval number goes'
        ' into the cls field and suits colouring.',
    'Ноль строит одно тело. Несколько интервалов дают объект на каждый, и '
    'тело можно раскрасить по содержанию.':
        'Zero builds one body. Several intervals give a feature each, and the'
        ' body can be coloured by grade.',
    'Полигоны, за пределами которых ячейки не выгружаются: подсчётный блок, '
    'лицензионная площадь.':
        'Polygons outside which cells are not written out: a computation '
        'block, a licence area.',
    'Полигоны, за пределами которых ячейки в тело не идут:\nподсчётный блок, '
    'лицензионная площадь.':
        'Polygons outside which cells do not reach the body: a computation '
        'block, a licence area.',
    'Содержание в ядре сверх фона. Граница тела проходит там, где содержание '
    'падает до половины от него.':
        'The core grade above background. The boundary of the body is where '
        'the grade falls to half of it.',
    'Куб значений из 2.02: каналы это уровни, отметка первого уровня и шаг '
    'лежат в метаданных.':
        'A cube of values from 2.02: bands are levels, the elevation of the '
        'first level and the step live in the metadata.',
    'Куб значений из 2.02: каналы это уровни, отметка первого уровня и шаг '
    'лежат в метаданных.':
        'A cube of values from 2.02: bands are levels, the elevation of the '
        'first level and the step live in the metadata.',
    'Значение, ниже которого ячейка в модель не идёт. Работает,\nтолько когда'
    ' отсечка включена галкой выше.':
        'The value below which a cell does not reach the model.',
    'Ячейка не ниже отсечки считается телом. Отсечку для демонстрационных '
    'данных печатает 2.01.':
        'A cell not below the cutoff counts as a body. For the demonstration '
        'data the cutoff is printed by 2.01.',
    'При заданной плотности к каждому блоку добавляется масса в полях dens и '
    'ore_t.':
        'With a density given, mass is added to every block in the dens and '
        'ore_t fields.',
    'Глубина разбуривания вниз от поверхности. Пропорции тела считаются от '
    'неё же.':
        'The drilling depth down from the surface. The proportions of the '
        'body are taken from it as well.',
    'Если охват задан, он и берётся, а координаты угла и размеры ниже не '
    'читаются.':
        'When the extent is set, it wins, and the corner coordinates and '
        'sizes below are not read.',
    'Числовое поле, значение которого раскладывается по кубу: содержание, '
    'концентрация, влажность.':
        'The numeric field whose value is spread through the cube: grade, '
        'concentration, moisture.',
    'Сеть строится со сбивкой, а не правильной сеткой: правильная даёт '
    'интерполяции слишком лёгкую задачу.':
        'The grid is jittered rather than regular: a regular one gives '
        'interpolation too easy a task.',
    'Наклон стволов от вертикали. Ноль даёт вертикальные скважины.':
        'The tilt of the holes from the vertical. Zero gives vertical '
        'boreholes.',
    'Слой проб. Отметка берётся из геометрии, из поля или считается от '
    'поверхности, это задаётся ниже.':
        'The layer of samples. The elevation comes from the geometry, from a '
        'field or from a surface, which is set below.',
    'Пласт со складкой и падением показывает главное: горизонтальные уровни '
    'куба режут залежь поперёк. Линза изотропна и проще всех, жила это '
    'обратный крайний случай.':
        'A folded and dipping bed shows the main point: cube levels cut the '
        'deposit across. A lens is isotropic and the simplest, a vein is the '
        'opposite extreme.',
    'Ноль берёт на одного больше, чем замеров в одной точке плана. Больше '
    'значит смешать все уровни сразу и сгладить аномалию по глубине.':
        'Zero takes one more than the number of samples at one place in plan.'
        ' More means mixing all the levels at once and smoothing an anomaly '
        'with depth away.',
    'Слияние делает слой в разы легче, но ломает замкнутость: для подсчёта '
    'объёма флаг надо снять.':
        'Merging makes the layer many times lighter but breaks '
        'watertightness: for volume computation the flag must be cleared.',
    'Ближний сосед даёт ступени и годится для проверки данных. Обратные '
    'расстояния дают сглаженное поле.':
        'Nearest neighbour gives steps and suits checking the data. Inverse '
        'distances give a smoothed field.',
    'Узел, где точек в радиусе меньше этого числа, остаётся пропуском: '
    'пустота лучше выдуманного значения.':
        'A node with fewer points within the radius than this stays a gap: '
        'emptiness beats an invented value.',
    'Доля логнормального шума опробования. Ноль даёт данные без шума, на них '
    'видно саму модель.':
        'The share of lognormal sampling noise. Zero gives data without '
        'noise, where the model itself is visible.',
    'Пробы с полями hole, from_m, to_m, grade, truth, zone.':
        'Samples with the fields hole, from_m, to_m, grade, truth, zone.',
    'Многоканальный грид: канал это горизонтальный уровень, отметка первого '
    'уровня и шаг пишутся в метаданные.':
        'A multiband grid: a band is a horizontal level, and the elevation of'
        ' the first level and the step go into the metadata.',
    'Точка-центроид на занятую ячейку с размером блока, объёмом и значением.':
        'A centroid point per occupied cell with the block size, volume and '
        'value.',
    'MULTIPOLYGON Z, объект на интервал окраски. Поля cls,\nvmin, vmax, faces'
    ' и shell.':
        'MULTIPOLYGON Z, one feature per colour interval. Fields cls, vmin, '
        'vmax, faces and shell.',
    'Чем больше степень, тем сильнее ближняя точка перевешивает дальние. '
    'Двойка это обычный выбор.':
        'The larger the power, the more a near point outweighs the far ones. '
        'Two is the usual choice.',
    'Ноль берёт четверть охвата данных. Узел, где точек в радиусе не '
    'набралось, остаётся пропуском.':
        'Zero takes a quarter of the data extent. A node with too few points '
        'within the radius stays a gap.',
    'Проба длиннее мощности залежи пропустит её между замерами. На пласте в '
    'двадцать шесть метров десять метров это уже много.':
        'A sample longer than the thickness of the deposit will miss it '
        'between the readings. On a bed of twenty six metres, ten metres is '
        'already a lot.',
    'Окружность вокруг узла делится на равные части, из каждой берётся своя '
    'доля точек. Без этого при анизотропии все соседи оказываются в одной '
    'скважине.':
        'The circle around the node is split into equal parts and each gives '
        'its share of points. Without this, under anisotropy all the '
        'neighbours land in one borehole.',
    'Одно и то же зерно даёт одни и те же данные: с ним можно сравнивать '
    'методы на неизменной выборке.':
        'The same seed gives the same data: with it methods can be compared '
        'on an unchanged sample set.',
    'Доля недобуренных скважин. Нужна, чтобы у куба были места без данных, '
    'как на настоящей разведке.':
        'The share of holes stopped short. It is there so the cube has places'
        ' without data, as on real exploration.',
    'Ширина площадки в метрах. Читается, только когда охват\nне задан.':
        'The site width in metres. Read only when the extent is not set.',
    'Высота площадки. Ноль означает «как ширина».':
        'The site height. Zero means the same as the width.',
    'Средняя отметка дневной поверхности. Устья ставятся по пологому рельефу '
    'вокруг неё.':
        'The mean elevation of the ground surface. Collars are placed on a '
        'gentle relief around it.',
    'Общий наклон содержаний по площадке. Нужен, чтобы данные не сводились к '
    'одному телу.':
        'The overall grade trend across the site. It is there so the data '
        'does not reduce to a single body.',
    'Защип это касание двух ячеек одной диагональю. Дырой он не является, но '
    'ребро в нём принадлежит четырём граням, и проверка замкнутости такое '
    'тело отвергает.':
        'A pinch is two cells touching along a single diagonal. It is not a '
        'hole, but its edge belongs to four faces and a watertightness check '
        'rejects such a body.',
    'Без отсечки выгружаются все ячейки с данными, с отсечкой только те, что '
    'не ниже её.':
        'Without a cutoff every cell with data is written out, with one only '
        'those not below it.',
    'Левый нижний угол площадки по оси X. Читается, только когда\nохват не '
    'задан.':
        'The lower left corner of the site along X. Read only when the extent'
        ' is not set.',
    'Левый нижний угол площадки по оси Y. Читается, только когда\nохват не '
    'задан.':
        'The lower left corner of the site along Y. Read only when the extent'
        ' is not set.',
    'Для отметки из поля это сама отметка, для глубины это глубина вниз от '
    'поверхности.':
        'For elevation from a field this is the elevation itself, for depth '
        'it is the depth measured down from the surface.',
    'Плоский слой отдаёт нулевую Z у каждой точки. Если брать её из '
    'геометрии, все пробы лягут в одну плоскость и куб выйдет бессмысленным.':
        'A flat layer gives a zero Z at every point. Taking it from the '
        'geometry would put every sample in one plane and the cube would be '
        'meaningless.',
    'Грид, от которого отсчитывается глубина. Нужен почвенным и подобным '
    'пробам, где записана глубина, а не отметка.':
        'The grid the depth is measured from. Needed by soil and similar '
        'samples, which record a depth rather than an elevation.',
    'Шаг по горизонтали, м (0 - от данных)':
        'Step in plan, m (0 means from the data)',
    'Шаг по вертикали, м (0 - от данных)':
        'Vertical step, m (0 means from the data)',
    'Наибольшее число точек (0 - от данных)':
        'Largest number of points (0 means from the data)',
    'Шаг по горизонтали от данных: %.1f м.':
        'Step in plan from the data: %.1f m.',
    'Шаг по вертикали от данных: %.2f м.':
        'Vertical step from the data: %.2f m.',
    'Наибольшее число точек от данных: %d.':
        'Largest number of points from the data: %d.',
    'Оболочек по отсечке': 'Shells at the cutoff',
    'Оболочки %s: уровни %s, треугольников %d.':
        'Shells %s: levels %s, triangles %d.',
    'Сколько оболочек строить. Одна берётся по заданной отсечке, '
    'несколько раскладываются от неё до наибольшего значения куба. '
    'Цвет каждой берётся из шкалы, прозрачность растёт к наружным: '
    'внутренние видно сквозь них.':
        'How many shells to build. One is taken at the given cutoff, '
        'several are spread from it up to the largest value of the '
        'cube. Each takes its colour from the ramp, and the outer ones '
        'are more transparent so the inner ones show through.',
    'Обрезка по отметке. Контур и коридор режут только в плане, '
    'а разрез по пачке пластов задаётся отметками. Наименьшее '
    'значение означает «без границы».':
        'Clipping by elevation. A contour and a corridor cut in plan '
        'only, while a section across a pile of beds is set by elevations. '
        'The lowest value means «no bound».',
    'Нажмите «Обновить сцену».': 'Press «Rebuild the scene».',
    'Сетка: %s.': 'Grid: %s.',
    'Наибольшее число точек %d, а замеров в одной точке плана всего '
    '%d. В среднее попадут все уровни сразу, и различие по глубине '
    'сгладится. Поставьте не больше %d.':
        'The largest number of points is %d, while there are only %d '
        'samples at one place in plan. All the levels will fall into '
        'the average at once and the difference with depth will be '
        'smoothed away. Set it to %d at most.',
    'Сеть: шаг по вертикали %.2f м, шаг в плане %.0f м, замеров '
    'в одной точке плана %d.':
        'Sampling net: vertical step %.2f m, plan step %.0f m, '
        '%d samples at one place in plan.',
    'Анизотропия сжимает вертикаль: большая сглаживает по вертикали, '
    'малая сохраняет различие по глубине. Сейчас %.3f.':
        'Anisotropy squeezes the vertical: a large value smooths '
        'along it, a small one keeps the difference with depth. '
        'Now %.3f.',
    'Считает значение в узлах объёмной сетки по точкам с '
    'высотой.\n\nАнизотропия это отношение вертикального масштаба к '
    'горизонтальному. Без неё ближайшей точкой окажется соседняя скважина, а '
    'не соседний замер в той же точке плана.\n\nУзлы, где точек в радиусе '
    'меньше нужного, остаются пропуском: пустота лучше выдуманного '
    'значения.\n\nСоседи набираются по секторам: окружность вокруг узла '
    'делится на равные части, и из каждой берётся своя доля ближайших точек. '
    'Без этого при анизотропии все соседи оказываются в одной скважине, '
    'потому что проба в стволе в сотни раз ближе соседней скважины, и '
    'обратные расстояния вырождаются в ближайшего соседа. Один сектор '
    'отключает деление.\n\nИсточник отметки задаётся отдельно. Плоский слой '
    'отдаёт нулевую Z у каждой точки, поэтому брать её из геометрии нельзя: '
    'все пробы легли бы в одну плоскость. Поле отметки годится, когда отметка'
    ' посчитана, а глубина от поверхности нужна пробам, где записана глубина,'
    ' а не отметка. Точка, для которой отметку получить не удалось, в расчёт '
    'не идёт, и число таких пишется в журнал.':
        'Computes a value at the nodes of a volume grid from points with '
        'elevation.\n\nAnisotropy is the ratio of the vertical scale to the '
        'horizontal one. Without it the nearest point turns out to be the '
        'neighbouring borehole rather than the neighbouring sample at the '
        'same place in plan.\n\nNodes with fewer points within the radius '
        'than needed stay a gap: emptiness beats an invented '
        'value.\n\nNeighbours are gathered by sectors: the circle around the '
        'node is split into equal parts and each gives its share of the '
        'nearest points. Without this, under anisotropy all the neighbours '
        'land in one borehole, because a sample in the hole is hundreds of '
        'times closer than the neighbouring hole, and inverse distances '
        'degenerate into nearest neighbour. One sector switches the split '
        'off.\n\nThe elevation source is set separately. A flat layer gives a'
        ' zero Z at every point, so taking it from the geometry will not do: '
        'all the samples would land in one plane. An elevation field suits a '
        'computed elevation, and depth below a surface suits samples that '
        'record a depth rather than an elevation. A point whose elevation '
        'could not be obtained is left out, and the number of those is '
        'written to the log.',
    'Источник отметки': 'Elevation source',
    'Высота геометрии (Z)': 'Geometry elevation (Z)',
    'Глубина от поверхности': 'Depth below a surface',
    'Поле отметки или глубины': 'Elevation or depth field',
    'Поверхность для отсчёта глубины':
        'Surface the depth is measured from',
    'Для этого источника отметки нужно поле.':
        'This elevation source needs a field.',
    'Для глубины нужна поверхность отсчёта.':
        'Depth needs a surface to measure from.',
    'Поверхность отсчёта не открылась.':
        'The reference surface did not open.',
    'Без отметки пропущено точек: %d.':
        'Points skipped for want of an elevation: %d.',
    'Все точки на одной отметке: куб не построить. Проверьте '
    'источник отметки.':
        'All the points share one elevation: a cube cannot be built. '
        'Check the elevation source.',
    'Секторов поиска': 'Search sectors',
    'Считает значение в узлах объёмной сетки по точкам с '
    'высотой.\n\nАнизотропия это отношение вертикального масштаба к '
    'горизонтальному. Без неё ближайшей точкой окажется соседняя скважина, а '
    'не соседний замер в той же точке плана.\n\nУзлы, где точек в радиусе '
    'меньше наименьшего числа, остаются пропуском: пустота лучше выдуманного '
    'значения.\n\nСоседи набираются по секторам: окружность вокруг узла '
    'делится на равные части, и из каждой берётся своя доля ближайших точек. '
    'Без этого при анизотропии все соседи оказываются в одной скважине, '
    'потому что проба в стволе в сотни раз ближе соседней скважины, и '
    'обратные расстояния вырождаются в ближайшего соседа. Один сектор '
    'отключает деление.':
        'Computes a value at the nodes of a volume grid from points with '
        'elevation.\n\nAnisotropy is the ratio of the vertical scale to the '
        'horizontal one. Without it the nearest point turns out to be the '
        'neighbouring borehole rather than the neighbouring sample at the '
        'same place in plan.\n\nNodes with fewer points within the radius '
        'than the minimum stay a gap: emptiness beats an invented '
        'value.\n\nNeighbours are gathered by sectors: the circle around the '
        'node is split into equal parts and each gives its share of the '
        'nearest points. Without this, under anisotropy all the neighbours '
        'land in one borehole, because a sample in the hole is hundreds of '
        'times closer than the neighbouring hole, and inverse distances '
        'degenerate into nearest neighbour. One sector switches the split '
        'off.',
    'Вид маркера': 'Marker shape',
    'Круг (экранный)': 'Circle (on screen)',
    'Квадрат': 'Square',
    'Ромб': 'Diamond',
    'Треугольник': 'Triangle',
    'Крест': 'Cross',
    'Размер значка, м': 'Marker size, m',
    'Подписей не более': 'Labels at most',
    'Размер плоского значка в метрах, по ширине.':
        'The size of a flat marker in metres, across.',
    'Круг рисуется экранным значком: размер в пикселях, при '
    'приближении не растёт, стоит почти ничего. Остальные виды '
    'лежат в плане на отметке точки: размер в метрах, значок '
    'закрывается поверхностью и уходит под кровлю, но с высоты '
    'сплющивается.':
        'A circle is drawn as an on-screen marker: the size is in '
        'pixels, it does not grow when you zoom in and costs almost '
        'nothing. The other shapes lie in plan at the elevation of '
        'the point: the size is in metres, the marker is hidden by a '
        'surface and goes under a roof, but flattens when seen from '
        'above.',
    'Сколько подписей ставить, не больше. Каждая подпись это '
    'отдельный элемент отрисовки, поэтому число ограничено. Ноль '
    'означает «без подписей».':
        'How many labels to place at most. Every label is a separate '
        'drawing item, so the number is limited. Zero means «no '
        'labels».',
    'Поле подписи точек': 'Point label field',
    'Подписей точек: %d из %d.': 'Point labels: %d of %d.',
    'Поле, из которого берётся подпись точки. Подписи '
    'прореживаются: если рядом уже есть подписанная точка, текст '
    'не ставится, иначе они налезают друг на друга.':
        'The field the point label is taken from. Labels are thinned: '
        'if a labelled point is already near, the text is skipped, '
        'otherwise they overlap each other.',
    'Размер точки, px (0 - из стиля)':
        'Point size, px (0 means from the style)',
    'Размер точки в пикселях. Ноль означает «из стиля слоя»: размер '
    'маркера на карте задан в миллиметрах печати и пересчитывается '
    'от обычных двух миллиметров. Размер экранный, при приближении '
    'точка не растёт.':
        'Point size in pixels. Zero means «from the layer style»: the '
        'marker size on the map is set in print millimetres and is '
        'converted from the usual two. The size is on screen, so the '
        'point does not grow when you zoom in.',
    'Задать свой цвет': 'Set a custom colour',
    'Смещение по вертикали, м': 'Vertical offset, m',
    'Сдвиг слоя по вертикали в метрах, поверх выбранного источника '
    'высоты. Небольшой подъём убирает спор за глубину, когда линия '
    'лежит ровно на поверхности.':
        'A vertical shift of the layer in metres, applied on top of '
        'the chosen elevation source. A small lift removes the depth '
        'fight when a line lies exactly on the surface.',
    'Отметка с поверхности': 'Elevation from a surface',
    'Поверхность отметки': 'Elevation surface',
    'Поверхность, с которой берётся отметка. Значение читается '
    'в каждой вершине, поэтому объект ложится на рельеф, а не '
    'встаёт на общую отметку. Там, где у поверхности нет данных, '
    'объект обрезается.':
        'The surface the elevation is taken from. The value is read '
        'at every vertex, so the feature follows the relief instead '
        'of standing at one common elevation. Where the surface has '
        'no data, the feature is cut away.',
    'У слоя %s не выбрана поверхность отметки или она '
    'не открылась.':
        'Layer %s has no elevation surface chosen, or it did not '
        'open.',
    'Снять обрезку, наброски и точку опроса':
        'Clear the clip, the sketches and the query point',
    'Точка опроса убрана.': 'The query point is cleared.',
    'Перепроецировано слоёв: %d.': 'Layers reprojected: %d.',
    'шкала слоя %s': 'layer %s ramp',
    'Стиль слоя %s: цветов %d, скрыто классами %d, первые %s':
        'Layer %s style: %d colours, %d hidden by classes, first %s',
    'Предел вершин в сцене (тысяч)': 'Vertex limit for the scene (thousands)',
    'В слое %s объектов %d, показаны первые %d: набрано %d вершин '
    'из %d. Предел вершин меняется в свойствах сцены.':
        'Layer %s has %d features, the first %d are shown: %d vertices '
        'of %d were taken. The vertex limit is set in the scene '
        'properties.',
    'Сколько вершин отдаётся на всю сцену. Бюджет делится между '
    'слоями, и объекты, на которые его не хватило, в сцену не попадают: '
    'об этом пишет строка состояния. Поднимайте, если тела показаны '
    'не полностью.':
        'How many vertices the whole scene gets. The budget is split '
        'between layers, and features it did not stretch to are left '
        'out of the scene: the status line says so. Raise it if bodies '
        'are shown incomplete.',
    'Обновить сцену: настройки изменились':
        'Rebuild the scene: settings have changed',
    'Настройки изменились. Нажмите «Обновить сцену».':
        'Settings have changed. Press «Rebuild the scene».',
    'Обычно сцена считается по кнопке «Обновить сцену», а отметки '
    'и ползунки только записывают, что показать. С этой галкой '
    'сцена пересобирается сразу на каждую правку: удобно '
    'на лёгких данных.':
        'Normally the scene is computed by the «Rebuild the scene» '
        'button, and the check marks and sliders only record what '
        'to show. With this box ticked the scene is rebuilt on '
        'every edit at once: handy on light data.',
    'Проб много: интерполяция в объёме считает узел по всем '
    'пробам, и время растёт с их числом. Увеличьте длину пробы '
    'или уменьшите число скважин.':
        'There are many samples: interpolation in three dimensions '
        'weighs every node against all of them, and the time grows '
        'with their number. Raise the sample length or reduce the '
        'number of boreholes.',
    'Слой %s: видимых граней %d, это больше предела %d. Поднимите '
    'отсечку, уменьшите число интервалов окраски или загрубите '
    'куб.':
        'Layer %s: %d visible faces, which is above the limit of '
        '%d. Raise the cutoff, reduce the number of colour '
        'intervals, or coarsen the cube.',
    'Убирать защипы по ребру': 'Remove edge pinches',
    'Защипов по ребру: %d.': 'Edge pinches: %d.',
    'Защипы убраны, добавлено ячеек: %d.':
        'Pinches removed, cells added: %d.',
    'Защипы оставлены: рёбра в них принадлежат четырём граням, '
    'и замкнутой оболочка не будет.':
        'Pinches are kept: their edges belong to four faces, and '
        'the shell will not be watertight.',
    'Строит тело по отсечке коробками ячеек: MULTIPOLYGON Z, объект на '
    'интервал окраски.\n\nСтроятся только видимые грани. Грань между двумя '
    'занятыми соседями не видна никогда, поэтому её отбрасывают: на кубе '
    'двести на двести на сто это сто двадцать шесть тысяч граней вместо '
    'двадцати четырёх миллионов.\n\nФлаг «Сливать соседние грани» делает '
    'сцену лёгкой, но ломает замкнутость: длинный прямоугольник упирается в '
    'два коротких, общего ребра у них нет. Для подсчёта объёма и проверки '
    'замкнутости флаг надо снять, тогда каждое ребро принадлежит ровно двум '
    'граням.\n\nПоля: cls (интервал окраски), vmin и vmax (границы '
    'интервала), faces (граней в объекте), shell (единица у тела).\n\nЗащип '
    'по ребру это касание двух ячеек одной диагональю. Дырой он не является и'
    ' объём не портит, но ребро в нём принадлежит четырём граням, и проверка '
    'замкнутости такое тело отвергает. Флаг «Убирать защипы по ребру» '
    'заполняет угол одной ячейкой, и касание становится по грани.':
        'Builds a body from cells above the cutoff as boxes: MULTIPOLYGON Z, '
        'one feature per colour interval.\n\nOnly visible faces are built. A '
        'face between two occupied neighbours is never seen, so it is '
        'dropped: on a two hundred by two hundred by one hundred cube that is'
        ' one hundred and twenty six thousand faces instead of twenty four '
        'million.\n\nThe «Merge neighbouring faces» flag makes the scene '
        'light but breaks watertightness: a long rectangle meets two short '
        'ones and they share no edge. For volume computation and for a '
        'watertightness check the flag must be cleared, and then every edge '
        'belongs to exactly two faces.\n\nFields: cls (colour interval), vmin'
        ' and vmax (interval bounds), faces (faces in the feature), shell '
        '(one for a body).\n\nAn edge pinch is two cells touching along a '
        'single diagonal. It is not a hole and does not spoil the volume, but'
        ' its edge belongs to four faces and a watertightness check rejects '
        'such a body. The «Remove edge pinches» flag fills the corner with '
        'one cell, and the contact becomes a face contact.',
    '2.03 Куб в блочную модель': '2.03 Cube to a block model',
    '2.04 Тело куба вокселями': '2.04 Cube body as voxels',
    'Куб значений (каналы это уровни)':
        'Cube of values (bands are levels)',
    'Отсечка': 'Cutoff',
    'Применять отсечку': 'Apply the cutoff',
    'Контур подсчёта': 'Computation contour',
    'Интервалов окраски (0 - без классов)':
        'Colour intervals (0 means no classes)',
    'Интервалов окраски (0 - одним телом)':
        'Colour intervals (0 means a single body)',
    'Плотность, т/м3 (0 - без пересчёта)':
        'Density, t/m3 (0 means no conversion)',
    'Сливать соседние грани': 'Merge neighbouring faces',
    'Блочная модель': 'Block model',
    'Тело вокселями': 'Body as voxels',
    'Не задан куб значений.': 'No cube of values is set.',
    'Слою нужен многоканальный грид: каналы это уровни куба.':
        'The layer needs a multiband grid: bands are cube levels.',
    'Не удалось создать слой блочной модели.':
        'Could not create the block model layer.',
    'Не удалось создать слой тела.': 'Could not create the body layer.',
    'Занятых ячеек не осталось: проверьте отсечку и контур.':
        'No occupied cells are left: check the cutoff and the contour.',
    'По отсечке ячеек не осталось.': 'No cells are left at the cutoff.',
    'Модель слишком велика: поднимите отсечку или уменьшите число интервалов.':
        'The model is too large: raise the cutoff or reduce the number of '
        'intervals.',
    'Куб: %d x %d x %d, отметка первого уровня %.3f, шаг %.3f.':
        'Cube: %d x %d x %d, first level at %.3f, step %.3f.',
    'Контур оставил ячеек в плане: %d из %d.':
        'The contour left %d cells of %d in plan.',
    'Блоков: %d из %d ячеек куба, объём блока %.3f м3.':
        'Blocks: %d of %d cube cells, block volume %.3f m3.',
    'Значения: %.3f .. %.3f.': 'Values: %.3f .. %.3f.',
    'Суммарная масса: %.0f т.': 'Total mass: %.0f t.',
    'Ячеек: %d, видимых граней: %d, треугольников: %d.':
        'Cells: %d, visible faces: %d, triangles: %d.',
    'Объектов: %d.': 'Features: %d.',
    'Грани слиты. Замкнутой такая оболочка не будет: для подсчёта объёма '
    'снимите флаг слияния.':
        'Faces are merged. Such a shell will not be watertight: clear the '
        'merge flag to compute volume.',
    'Слияние делает сцену в разы легче, но оболочка перестаёт быть замкнутой:'
    ' длинный прямоугольник упирается в два коротких, общего ребра у них нет.'
    ' Снимите флаг, если по этой модели считается объём.':
        'Merging makes the scene many times lighter, but the shell stops '
        'being watertight: a long rectangle meets two short ones and they '
        'share no edge. Clear the flag if volume is computed on this model.',
    'Переводит куб значений в блочную модель: точку-центроид на каждую '
    'занятую ячейку.\n\nПоля: bid (номер блока), lev (уровень), row и col '
    '(ячейка грида), x, y, z (центр блока), dx, dy, dz (размер блока), vol '
    '(объём), val (значение), cls (номер интервала окраски), при заданной '
    'плотности ещё dens и ore_t.\n\nПропуски и ячейки ниже отсечки не '
    'выгружаются. Модель выходит разреженной, и весит она на порядок меньше '
    'полного параллелепипеда с пустыми краями.\n\nДальше работает векторный '
    'аппарат QGIS: фильтры выражениями, соединение внешних таблиц, '
    'калькулятор полей. Тот же слой показывается коробками в окне просмотра.':
        'Turns a cube of values into a block model: one centroid point per '
        'occupied cell.\n\nFields: bid (block number), lev (level), row and '
        'col (grid cell), x, y, z (block centre), dx, dy, dz (block size), '
        'vol (volume), val (value), cls (colour interval number), and dens '
        'with ore_t when a density is given.\n\nGaps and cells below the '
        'cutoff are not written out. The model comes out sparse and weighs an'
        ' order of magnitude less than a full box with empty edges.\n\nThe '
        'usual QGIS vector machinery works from there: expression filters, '
        'joins of external tables, the field calculator. The same layer is '
        'shown as boxes in the viewer.',
    'X левого нижнего угла': 'X of the lower left corner',
    'Y левого нижнего угла': 'Y of the lower left corner',
    'Ширина площадки, м': 'Site width, m',
    'Высота площадки, м (0 - как ширина)':
        'Site height, m (0 means the same as the width)',
    'Воксели по кубу': 'Voxels from the cube',
    'Отсечка куба': 'Cube cutoff',
    'Интервалов окраски': 'Colour intervals',
    'На сколько интервалов раскладывается содержание при окраске вокселей. '
    'Соседние грани одного интервала сливаются в один прямоугольник, поэтому '
    'чем меньше интервалов, тем легче сцена.':
        'How many intervals the grade is split into when colouring voxels. '
        'Neighbouring faces of one interval merge into a single rectangle, so'
        ' the fewer the intervals, the lighter the scene.',
    'Воксели %s: ячеек %d, видимых граней %d, прямоугольников %d.':
        'Voxels %s: cells %d, visible faces %d, rectangles %d.',
    'Слой %s: по отсечке %.3f ячеек не осталось.':
        'Layer %s: no cells left at the cutoff of %.3f.',
    'Слой %s: воксельная модель слишком велика. Поднимите отсечку или '
    'уменьшите число интервалов окраски.':
        'Layer %s: the voxel model is too large. Raise the cutoff or reduce '
        'the number of colour intervals.',
    '2.01 Демонстрационные скважины в объёме':
        '2.01 Demonstration boreholes in three dimensions',
    'Тип залежи': 'Deposit type',
    'Пласт со складкой и падением': 'Folded and dipping bed',
    'Линза': 'Lens',
    'Крутая жила': 'Steep vein',
    'Длина пробы, м': 'Sample length, m',
    'Отметка поверхности, м': 'Surface elevation, m',
    'Глубина разбуривания, м': 'Drilling depth, m',
    'Шум опробования, доля': 'Sampling noise, a share',
    'Содержание в ядре сверх фона': 'Core grade above background',
    'Фон во вмещающих породах': 'Background in the host rock',
    'Общий наклон содержаний, доля': 'Overall grade trend, a share',
    'Доля недобуренных скважин': 'Share of holes stopped short',
    'Наклон стволов, градусов': 'Hole inclination, degrees',
    'Пробы с содержаниями': 'Samples with grades',
    'Не удалось создать слой проб.':
        'Could not create the sample layer.',
    'Скважин: %d, проб: %d, длина пробы %.2f м.':
        'Boreholes: %d, samples: %d, sample length %.2f m.',
    'Площадка: %.0f x %.0f м от (%.0f, %.0f).':
        'Site: %.0f x %.0f m from (%.0f, %.0f).',
    'Устья: %.1f .. %.1f м, забои: %.1f .. %.1f м.':
        'Collars: %.1f .. %.1f m, hole bottoms: %.1f .. %.1f m.',
    'Содержание: %.3f .. %.3f, отсечка %.3f.':
        'Grade: %.3f .. %.3f, cutoff %.3f.',
    'Проб внутри тела: %d из %d.':
        'Samples inside the body: %d of %d.',
    'Ни одна проба не попала в тело: проверьте глубину разбуривания и охват '
    'площадки.':
        'No sample fell inside the body: check the drilling depth and the '
        'site extent.',
    'Создаёт скважины с опробованием по интервалам: сеть со сбивкой, разная '
    'глубина, часть скважин недобурена, устья по рельефу.\n\nТип залежи '
    'задаёт геометрию тела. Пласт со складкой и падением нужен, чтобы '
    'увидеть, как уровни куба режут залежь поперёк. Линза изотропна и проще '
    'всех. Крутая жила проверяет обратный случай, когда тело почти '
    'вертикально.\n\nПоля: hole (номер скважины), from_m и to_m (интервал '
    'пробы от устья вниз), grade (содержание с шумом), truth (содержание по '
    'модели, без шума), zone (единица внутри тела).\n\nШум логнормальный, '
    'отрицательных содержаний не возникает. Граница тела проходит там, где '
    'содержание падает до половины ядра над фоном - это и есть отсечка, она '
    'печатается в журнал.':
        'Creates boreholes sampled by intervals: a jittered grid, varying '
        'depth, some holes stopped short, collars following the '
        'relief.\n\nThe deposit type sets the shape of the body. A folded and'
        ' dipping bed shows the main point: cube levels cut the deposit '
        'across. A lens is isotropic and the simplest case. A steep vein is '
        'the opposite extreme, where the body is nearly vertical.\n\nFields: '
        'hole (borehole number), from_m and to_m (sample interval measured '
        'down from the collar), grade (assay with noise), truth (grade from '
        'the model, no noise), zone (one inside the body).\n\nNoise is '
        'lognormal, so no negative grades appear. The boundary of the body is'
        ' where the grade falls to half the core value above background - '
        'that is the cutoff, and it is printed to the log.',
    ' Вершин: %d.': ' Vertices: %d.',
    '(нет)': '(none)',
    '1. Пласт и блочная модель': '1. The bed and block model',
    '1.01 Собрать грид пласта': '1.01 Assemble a bed grid',
    '1.02 Калькулятор пласта': '1.02 Bed calculator',
    '1.03 Грид пласта в блочную модель': '1.03 Bed grid to a block model',
    '1.04 Поверхности в 3D (меши)': '1.04 Surfaces to 3D (meshes)',
    '1.05 Домены в канал пласта': '1.05 Domains to a bed band',
    '1.06 Разность запасов (списание)': '1.06 Reserve difference (write-off)',
    '1.07 Создать пример данных (демо)': '1.07 Create sample data (demo)',
    '2. 3D-интерполяция': '2. 3D interpolation',
    '2.02 Интерполяция точек в объёме': '2.02 Interpolating points in 3D',
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
    'Анизотропия (вертикаль к горизонтали)':
        'The anisotropy (vertical to horizontal)',
    'Ближний сосед': 'The nearest neighbour',
    'Блоков выгружено: %d.': 'Blocks exported: %d.',
    'Блочная модель (центроиды)': 'Block model (centroids)',
    'Блочная модель: %s': 'Block model: %s',
    'В выгрузку: %s, вершин %d, граней %d':
        'To the export: %s, %d vertices, %d faces',
    'В определении разреза нет полей ox и oy: чертёж наложить не по чему. '
    'Постройте разрез текущей версией Isoliner.':
        'The section definition has no ox and oy fields: there is nothing to '
        'drape the drawing by. Build the section with the current version of '
        'Isoliner.',
    'В слое %s объектов %d, показаны первые %d.':
        'The layer %s holds %d features, the first %d are shown.',
    'Вертикальное преувеличение': 'Vertical exaggeration',
    'Верх призмы': 'Prism top',
    'Верх: низ плюс высота из поля': 'Top: the bottom plus a height field',
    'Верх: поле верха': 'Top: the top field',
    'Вид сверху, план': 'Top view, a plan',
    'Вложенные контуры уровней осмысленно смотреть линиями. Заливка нужна '
    'телам пласта и полиэдрам.':
        'Nested level contours make sense as lines. The fill is for bed '
        'bodies and polyhedra.',
    'Все': 'All',
    'Выгружать нечего: сцена пуста.': 'Nothing to export: the scene is empty.',
    'Выгружено частей: %d, файл %.1f МБ.':
        'Exported parts: %d, the file is %.1f MB.',
    'Выгрузить сцену': 'Export the scene',
    'Выгрузить сцену в файл GLB': 'Export the scene to a GLB file',
    'Выгрузка не удалась: %s': 'The export failed: %s',
    'Выдать как TIN (триангулировать)': 'Output as TIN (triangulate)',
    'Глубина скважины, м': 'The depth of a hole, m',
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
    'Для контура нужно хотя бы три вершины.':
        'A contour needs at least three vertices.',
    'Для линии нужно хотя бы две вершины.':
        'A line needs at least two vertices.',
    'Для текстуры нет видимых слоёв карты.':
        'There are no visible map layers for the texture.',
    'Домены записаны в канал %d. Ячеек в доменах: %d.':
        'Domains written to band %d. Cells in domains: %d.',
    'Завершить линию и резать по ней': 'Finish the line and cut along it',
    'Загружено алгоритмов: %d': 'Algorithms loaded: %d',
    'Задайте грид или охват: карте нужны границы.':
        'Give a grid or an extent: the map needs its bounds.',
    'Замкнуть контур и обрезать сцену': 'Close the contour and clip the scene',
    'Запасы металла': 'Metal reserves',
    'Запасы руды': 'Ore reserves',
    'Заполнено узлов: %d из %d': 'Nodes filled: %d of %d',
    'Зерно случайности': 'The random seed',
    'Изоповерхность по кубу': 'An isosurface from a cube',
    'Инструмент: %s': 'Tool: %s',
    'Источник высоты': 'Elevation source',
    'Как есть': 'As is',
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
    'Контур (нарисован)': 'Contour (drawn)',
    'Контур ещё не нарисован.': 'No contour has been drawn yet.',
    'Контур замкнут: вершин %d.': 'The contour is closed: %d vertices.',
    'Контур подсчёта (полигоны, необязательно)':
        'Reserve contour (polygons, optional)',
    'Контур сохранён слоем проекта.':
        'The contour is saved as a project layer.',
    'Контуром': 'As outlines',
    'Коридор вдоль линии': 'A corridor along the line',
    'Коридор, полуширина': 'Corridor, half-width',
    'Кровля (растр)': 'Roof (raster)',
    'Куб': 'Cube',
    'Куб (демо)': 'Cube (demo)',
    'Куб значений': 'A cube of values',
    'Кусок': 'The piece',
    'Линий: %d.': 'Lines: %d.',
    'Линия готова: вершин %d, коридор %.0f.':
        'The line is ready: %d vertices, corridor %.0f.',
    'Линия становится вертикальной лентой от zmin до zmax из полей '
    'определения разреза.':
        'The line becomes a vertical ribbon from zmin to zmax taken from the '
        'section definition fields.',
    'Масштаб Z (вертикальное преувеличение)':
        'Z scale (vertical exaggeration)',
    'Метод': 'The method',
    'Меш записан: %s (узлов %d, треугольников %d).':
        'Mesh written: %s (%d nodes, %d triangles).',
    'Модель «было» (центроиды)': 'The "before" model (centroids)',
    'Модель «стало» (центроиды)': 'The "after" model (centroids)',
    'Мощность средняя / мин / макс': 'Thickness mean / min / max',
    'Мощность, ед. карты': 'Thickness, map units',
    'Наименьшее число точек': 'The smallest number of points',
    'Нарисованная линия': 'The drawn line',
    'Нарисованный контур': 'The drawn contour',
    'Настройки сцены взяты из проекта.':
        'The scene settings are taken from the project.',
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
    'Не удалось сохранить состояние сцены: %s':
        'The scene state could not be saved: %s',
    'Низ призмы берётся с этой поверхности: подошва дома садится на рельеф, '
    'а не на заданную отметку.':
        'The bottom of the prism is taken from this surface: a building sits '
        'on the relief rather than on a fixed elevation.',
    'Низ призмы с поверхности': 'Prism bottom from a surface',
    'Ничего': 'None',
    'Нужен многоканальный грид пласта (каналы 1 и 2).':
        'A multiband bed grid is required (bands 1 and 2).',
    'Нужен хотя бы один грид.': 'At least one grid is required.',
    'Обновить сцену': 'Update the scene',
    'Обновлять автоматически': 'Update automatically',
    'Оболочка НЕ замкнута: открытых рёбер %d.':
        'Shell is NOT closed: open edges %d.',
    'Оболочка замкнута (водонепроницаема).': 'Shell is closed (watertight).',
    'Обратные расстояния': 'Inverse distances',
    'Обрезка по контуру': 'Clip by a contour',
    'Обрезка снята, сцена показана целиком.':
        'The clip is off, the whole scene is shown.',
    'Объектов: %d, граней всего: %d.': 'Objects: %d, faces total: %d.',
    'Объём': 'Volume',
    'Окраска': 'Colouring',
    'Окраска: %s [%.4g … %.4g].': 'Colour: %s [%.4g … %.4g].',
    'Оставить внутри': 'Keep what is inside',
    'Отметка залегания (подошва), ед. карты':
        'Base elevation (floor), map units',
    'Отметка из поля': 'Elevation from a field',
    'Отметьте слой на вкладке «Слои» или «Векторы».':
        'Tick a layer on the «Layers» or the «Vectors» tab.',
    'Отсечка: внутрь тела попадает всё, что не меньше этого значения. Каналы '
    'грида считаются уровнями куба.':
        'The cutoff: everything not less than this value goes inside the '
        'body. The bands of the grid are taken as the levels of the cube.',
    'Отчёт (HTML)': 'Report (HTML)',
    'Охват (окно вида) - размещение и размер':
        'Extent (map view) - placement and size',
    'Палитра': 'Palette',
    'Папка для мешей (2DM)': 'Folder for meshes (2DM)',
    'Параллельная проекция вместо перспективной':
        'A parallel projection instead of a perspective one',
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
    'объектов %d, память около %.0f МБ, прочитано гридов %d, взято из кэша '
    '%d.':
        'Scene rebuild: %.2f s in total (%s). Triangles %s, vertices %s, '
        'items %d, memory about %.0f MB, grids read %d, taken from cache %d.',
    'Пласт (демо)': 'Bed (demo)',
    'Пластов в свите': 'Beds in the suite',
    'Плоско, на нуле': 'Flat, at zero',
    'Плоскостей разреза: %d.': 'Section planes: %d.',
    'Плотность': 'Density',
    'Плотность руды, т/м³': 'Ore density, t/m³',
    'Площадь подсчёта': 'Computed area',
    'Поверхности 3D': '3D surfaces',
    'Поверхности-гриды': 'Surface grids',
    'Поверхность': 'Surface',
    'Подошва (растр)': 'Bottom (raster)',
    'Показывать плоскостью разреза': 'Show as a section plane',
    'Показывать разметку: контур и линию разреза':
        'Show the markup: the contour and the section line',
    'Поле верха или высоты': 'The top or height field',
    'Поле верха призмы либо высоты над низом, смотря что выбрано строкой '
    'выше.':
        'The field of the prism top or of the height above the bottom, '
        'depending on the row above.',
    'Поле запаса': 'Reserve field',
    'Поле значения': 'The value field',
    'Поле кода домена (число, необязательно)':
        'Domain code field (numeric, optional)',
    'Поле отметки': 'Elevation field',
    'Поле подписи скважин': 'Borehole label field',
    'Полигональный слой': 'Polygon layer',
    'Полигональный слой, по которому режется сцена. Годится любой замкнутый '
    'контур: подсчётный блок, лицензионный участок, нарисованный от руки '
    'полигон.':
        'The polygon layer the scene is cut by. Any closed contour will do: '
        'a mining block, a licence area, a polygon drawn by hand.',
    'Полигоны доменов': 'Domain polygons',
    'Положить кадр сцены в буфер обмена (Ctrl+C)':
        'Put a frame of the scene on the clipboard (Ctrl+C)',
    'Полуширина коридора вдоль линии, в единицах карты. Профиль разреза и '
    'данные по обе стороны от него.':
        'The half-width of the corridor along the line, in map units. The '
        'section profile and the data on both sides of it.',
    'Поля отметок': 'Elevation fields',
    'Правка свойств сразу пересобирает сцену. На тяжёлой сцене снимите галку '
    'и пользуйтесь кнопкой.':
        'Editing the properties rebuilds the scene at once. On a heavy scene '
        'untick this and use the button.',
    'Призмой (от поля до поля)': 'As a prism (from field to field)',
    'Применить вертикальное преувеличение %.2f?\nДа - модель как на '
    'экране.\nНет - настоящие высоты, годные для расчёта.':
        'Apply the vertical exaggeration %.2f?\nYes - the model as on '
        'screen.\nNo - true elevations, fit for calculation.',
    'Пример': 'Example',
    'Прозрачность поверхностей (процентов)': 'Surface transparency (percent)',
    'Пропущено: %s': 'Skipped: %s',
    'Прореживание узлов (каждый N-й)': 'Node thinning (every Nth)',
    'Радиус поиска, м (0 - авто)': 'The search radius, m (0 is automatic)',
    'Разбиение тела пласта (ячеек по стороне)':
        'Bed body resolution (cells per side)',
    'Разнос по Z (шаг вниз)': 'Z spacing (step down)',
    'Разнос по Z (шаг на каждый следующий грид)':
        'Z spacing (step per next grid)',
    'Разность (центроиды)': 'Difference (centroids)',
    'Разрез': 'Section',
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
    'Рисование отменено.': 'The drawing is cancelled.',
    'Рисовать контур по поверхности: клик ставит вершину.':
        'Draw a contour on the surface: a click adds a vertex.',
    'Рисую контур. Клик ставит вершину, кнопки рядом: снять последнюю, '
    'замкнуть.':
        'Drawing a contour. A click adds a vertex, the buttons alongside '
        'remove the last one and close it.',
    'Руководство Isoliner3D в формате PDF': 'The Isoliner3D manual in PDF',
    'Сборка сцены не удалась: %s': 'The scene could not be built: %s',
    'Свита (стопка складчатых пластов)': 'Suite (stack of folded beds)',
    'Свита x%d (демо)': 'Suite x%d (demo)',
    'Свита загружена отдельными слоями по пласту: %d.':
        'Suite loaded as separate per-bed layers: %d.',
    'Свита: пласт %d': 'Suite: bed %d',
    'Свой цвет': 'Custom colour',
    'Свой цвет слоя': 'Custom layer colour',
    'Свойства': 'Properties',
    'Свойства слоя: %s': 'Layer properties: %s',
    'Свойства сцены': 'Scene properties',
    'Свойства сцены: двойной клик': 'Scene properties: double-click',
    'Свойства…': 'Properties…',
    'Своя высота геометрии (Z)': 'The geometry\'s own elevation (Z)',
    'Сетка: %d x %d x %d, узлов %d': 'The grid: %d x %d x %d, %d nodes',
    'Скважин': 'Holes',
    'Скважин: %d.': 'Boreholes: %d.',
    'Скважины (стволы по отметкам)': 'Boreholes (stems by elevations)',
    'Скопировать не удалось: %s': 'The copy failed: %s',
    'Слева от линии': 'To the left of the line',
    'Слой %s: все %d объектов плоские, отметки от %.1f до %.1f. Объёма в '
    'геометрии нет, для ступеней возьмите показ призмой.':
        'The layer %s: all %d features are flat, elevations from %.1f to '
        '%.1f. There is no volume in the geometry, use the prism display for '
        'steps.',
    'Слой %s: по отсечке %.3f ничего не построено.':
        'The layer %s: nothing was built at the cutoff %.3f.',
    'Слой %s: у %d объектов нет отметок низа или верха.':
        'The layer %s: %d features have no bottom or top elevation.',
    'Слой меша не загрузился: %s': 'Mesh layer failed to load: %s',
    'Слою %s нужен многоканальный грид: каналы это уровни куба.':
        'The layer %s needs a multiband grid: the bands are the levels of '
        'the cube.',
    'Слоёв по вертикали (деление колонки)': 'Vertical layers (column split)',
    'Смещение Z': 'Z offset',
    'Снимок скопирован в буфер обмена.': 'The snapshot is on the clipboard.',
    'Снимок сохранён: %s': 'Snapshot saved: %s',
    'Снять последнюю вершину': 'Remove the last vertex',
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
    'Собираю сцену…': 'Building the scene…',
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
    'Сохранить кадр сцены в файл PNG':
        'Save a frame of the scene to a PNG file',
    'Сохранить контур не удалось: %s': 'The contour could not be saved: %s',
    'Сохранить нарисованный контур слоем проекта':
        'Save the drawn contour as a project layer',
    'Сохранить снимок': 'Save the snapshot',
    'Справа от линии': 'To the right of the line',
    'Справка (руководство PDF)…': 'Help (PDF manual)…',
    'Степень обратных расстояний': 'The power of the inverse distances',
    'Сторона текстуры (пикселей)': 'Texture side (pixels)',
    'Сторона текстуры по длинной оси охвата. Больше значение - детальнее '
    'карта на поверхности и больше видеопамяти.':
        'The texture side along the longer axis of the extent. A larger '
        'value means a more detailed map on the surface and more video '
        'memory.',
    'Суммарное списание по полю %s: %.6g.':
        'Total write-off by the %s field: %.6g.',
    'Сцена': 'Scene',
    'Сцена: %s треугольников, объектов %d, %.2f с.':
        'Scene: %s triangles, %d items, %.2f s.',
    'Считает значение в узлах объёмной сетки по точкам с '
    'высотой.\n\nАнизотропия это отношение вертикального масштаба к '
    'горизонтальному. Без неё ближайшей точкой окажется соседняя скважина, а '
    'не соседний замер в той же точке плана.\n\nУзлы, где точек в радиусе '
    'меньше нужного, остаются пропуском: пустота лучше выдуманного '
    'значения.':
        'Computes the value at the nodes of a volumetric grid from points '
        'with an elevation.\n\nThe anisotropy is the ratio of the vertical '
        'scale to the horizontal one. Without it the nearest point turns out '
        'to be a neighbouring hole rather than the neighbouring sample in '
        'the same plan position.\n\nNodes where there are fewer points '
        'within the radius than required stay empty: emptiness is more '
        'honest than an invented value.',
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
    'Тело (демо)': 'Body (demo)',
    'Тело пласта': 'Bed body',
    'Телом (заливка)': 'As a body (filled)',
    'Тетраэдр': 'Tetrahedron',
    'Тетраэдр (демо)': 'Tetrahedron (demo)',
    'Тип геометрии: %s Z.': 'Geometry type: %s Z.',
    'Точек с высотой и значением меньше двух.':
        'There are fewer than two points with an elevation and a value.',
    'Точек: %d.': 'Points: %d.',
    'Точечный слой': 'Point layer',
    'Точки с высотой': 'Points with an elevation',
    'Триангуляций из кэша: %d.': 'Triangulations from cache: %d.',
    'У слоя %s не выбрано поле отметки.':
        'No elevation field is chosen for the layer %s.',
    'У слоя %s нет высоты Z, выберите отметку из поля.':
        'The layer %s has no Z elevation, choose an elevation field.',
    'Убрать внутри': 'Remove what is inside',
    'Укажите файл для карты в поле «Карта (демо)».':
        'Give a file for the map in the «Map (demo)» field.',
    'Файл руководства не найден: %s': 'The manual file was not found: %s',
    'Фильтр слоёв…': 'Filter layers…',
    'Цвет': 'Colour',
    'Часть %s: вершин %d, граней %d': 'Part %s: %d vertices, %d faces',
    'Чертежа для разреза %d в выбранных слоях нет: похоже, чертёж и '
    'определение из разных построений.':
        'There is no drawing for section %d in the chosen layers: the '
        'drawing and the definition appear to come from different builds.',
    'Чертежи: %s.': 'Drawings: %s.',
    'Чертёж разреза': 'Section drawing',
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
    'линии': 'lines',
    'меши': 'meshes',
    'мимо поверхности': 'missed the surface',
    'мощность': 'thickness',
    'окраска': 'colouring',
    'подошва': 'bottom',
    'полигоны': 'polygons',
    'растр': 'raster',
    'сцена': 'scene',
    'точки': 'points',
    'уровень %d': 'level %d',
    'чтение': 'reading',
}
