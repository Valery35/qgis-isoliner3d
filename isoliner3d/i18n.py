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
    'Система координат местная (%s), пересчёт не делается: '
    'у неё нет привязки к земле. Задайте слою и проекту одну '
    'систему, если они в разных.':
        'The coordinate system is a local one (%s), so no '
        'reprojection is done: it has no tie to the earth. Give the '
        'layer and the project the same system if they differ.',
    'не задана': 'not set',
    'Грид пластов показывается вертикальным разрезом '
    'по выбранной линии: сквозь всю пачку сразу, с кровлей '
    'и подошвой каждого пласта. Это чертёж разреза, '
    'поставленный в сцену, а не поверхность, натянутая на линию. '
    'Линия берётся та же, что и для обрезки.':
        'A grid of beds is shown as a vertical section along the '
        'chosen line: through the whole stack at once, with the '
        'roof and the floor of every bed. It is the section drawing '
        'set into the scene, not a surface stretched over the line. '
        'The line is the same one used for clipping.',
    'Коридор строится по линии, а выбран слой с полигонами. '
    'Поставьте «Что оставить» на внутренность или наружное, '
    'либо выберите линейный слой.':
        'A corridor is built along a line, and a polygon layer was '
        'chosen. Set «What to keep» to the inside or the outside, '
        'or choose a line layer.',
    'Выбран линейный слой: у линии нет внутренности. Поставьте '
    '«Что оставить» на коридор вдоль линии.':
        'A line layer was chosen: a line has no inside. Set «What '
        'to keep» to a corridor along the line.',
    'Забор %s не построен: линия мимо данных.':
        'The fence %s was not built: the line misses the data.',
    'Забор %s: пластов %d, граней %d.':
        'Fence %s: %d beds, %d faces.',
    ' У %d тел объём вышел больше их габарита - это сбой счёта, '
    'и он не записан.':
        ' For %d bodies the volume came out larger than their own '
        'bounding box - that is a failure of the computation, and '
        'it was not written.',
    'Контуром или линией': 'By an outline or a line',
    'Что оставить': 'What to keep',
    'Сверху и снизу (растры)': 'Above and below (rasters)',
    'По маске (растр)': 'By a mask (raster)',
    'Маска и заборы': 'Mask and fences',
    'Показать заборами по линии': 'Show as fences along the line',
    'Маска %s не прочиталась.': 'The mask %s could not be read.',
    'Обрезка по контуру или линии: остаётся то, что внутри. '
    'Годится любой полигональный слой проекта, а также '
    'нарисованное прямо в сцене - его можно сохранить слоем '
    'кнопкой на плашке и выбрать здесь.':
        'Clipping by an outline or a line: what is inside stays. Any '
        'polygon layer of the project will do, as will something '
        'drawn in the scene itself - save it as a layer with the '
        'toolbar button and choose it here.',
    'Что оставить от контура: внутренность, наружное или коридор '
    'вдоль линии заданной полуширины.':
        'What to keep of the outline: the inside, the outside, or a '
        'corridor of the given half-width along the line.',
    'Верхняя поверхность отсечки: всё выше неё не показывается. '
    'Растр, а не отметка: кровля меняется по площади.':
        'The upper clipping surface: everything above it is not '
        'shown. A raster, not an elevation: a roof changes over the '
        'area.',
    'Нижняя поверхность отсечки: всё ниже неё не показывается.':
        'The lower clipping surface: everything below it is not '
        'shown.',
    'Растр-маска: тело остаётся там, где значение не меньше '
    'порога. Полигон задаёт границу линией, а маска - площадью: '
    'так удобнее, когда границу посчитал инструмент, а не рисовал '
    'человек.':
        'A raster mask: the body stays where the value is not less '
        'than the threshold. A polygon gives the boundary as a line, '
        'a mask as an area: that is handier when the boundary was '
        'computed by a tool rather than drawn by hand.',
    'Порог маски: что не меньше - внутри. Пропуск в маске '
    'считается «снаружи».':
        'The threshold of the mask: not less means inside. A gap in '
        'the mask counts as outside.',
    'В режиме тела пласта это ПЕРВЫЙ канал пары: за ним идёт '
    'подошва, дальше следующая пара. Грид пластов показывается '
    'всеми парами сразу, а этот канал говорит, с какого пласта '
    'начать.':
        'In bed-body mode this is the FIRST band of a pair: the floor '
        'follows it, then the next pair. A grid of beds is shown by '
        'all its pairs at once, and this band says which bed to '
        'start from.',
    'Тело пласта %s: пар каналов %d.':
        'Bed body %s: %d pairs of bands.',
    '%s пласта %s':
        '%s of bed %s',
    '2.08 Пласты по разрезам':
        '2.08 Beds from sections',
    'Грид %d x %d, ячейка %.1f м, уровней %d.':
        'Grid %d x %d, cell %.1f m, %d levels.',
    'Грид пластов':
        'Grid of the beds',
    'Каналов: %d, по кровле и подошве на пласт. Сцена показывает такой грид '
    'телом пласта, 1.02 и 1.03 считают по нему мощность, блоки и объёмы.':
        '%d bands, a roof and a floor per bed. The scene shows such a grid as'
        ' a bed body, and 1.02 and 1.03 compute the thickness, the blocks and'
        ' the volumes from it.',
    'Многоканальный грид: на каждый пласт кровля и подошва, в порядке '
    'номеров. Сцена показывает такой грид телом пласта, 1.02 считает по нему '
    'мощность, 1.03 - блоки и объёмы.':
        'A multiband grid: a roof and a floor per bed, in order of the '
        'numbers. The scene shows such a grid as a bed body, 1.02 computes '
        'the thickness from it and 1.03 the blocks and the volumes.',
    'Ни одного пласта не построено.':
        'Not a single bed was built.',
    'Пласт %s: кровлю и подошву не разобрать.':
        'Bed %s: the roof and the floor cannot be told apart.',
    'Пласт %s: местами подошва выше кровли. Там мощность отрицательна, и '
    'объём по ней считать нельзя.':
        'Bed %s: in places the floor is above the roof. The thickness there '
        'is negative and no volume can be computed from it.',
    'Пласт %s: мощность по площади %.2f .. %.2f м.':
        'Bed %s: thickness over the area %.2f .. %.2f m.',
    'Допуск склейки контактов, м':
        'Contact gluing tolerance, m',
    'Допуск, в пределах которого подошва верхнего пласта и кровля нижнего '
    'считаются одной поверхностью и строятся один раз. Две независимо '
    'построенные поверхности между разрезами расходятся, и в модели встаёт '
    'щель или нахлёст, которых на разрезе нет. Ноль отключает склейку: '
    'тогда каждая поверхность своя.':
        'The tolerance within which the floor of the upper bed and the roof '
        'of the lower one count as one surface and are built once. Two '
        'surfaces built independently drift apart between the sections, and '
        'the model gets a gap or an overlap that the section does not have. '
        'Zero switches the gluing off: then every surface is its own.',
    'Порядок пластов сверху вниз: %s.':
        'The beds from the top down: %s.',
    'Контакт пластов %s и %s: общих мест не нашлось, поверхности строятся '
    'порознь. Контуры нарисованы в разных местах плана дальше шага '
    'опробования.':
        'The contact of beds %s and %s: no shared places were found, the '
        'surfaces are built separately. The contours are drawn in different '
        'places of the plan, further apart than the sampling step.',
    'Контакт пластов %s и %s: на разрезах расходится до %.3f м, '
    'наибольшее в точке %.2f, %.2f.':
        'The contact of beds %s and %s: on the sections it differs by up to '
        '%.3f m, the largest at the point %.2f, %.2f.',
    'Контакт пластов %s и %s строится одной поверхностью: расхождение '
    'в пределах допуска %.3f м.':
        'The contact of beds %s and %s is built as one surface: the '
        'difference is within the tolerance of %.3f m.',
    'Контакт пластов %s и %s больше допуска %.3f м, поверхности строятся '
    'порознь. Между разрезами они разойдутся, и в модели встанет щель '
    'или нахлёст.':
        'The contact of beds %s and %s exceeds the tolerance of %.3f m, the '
        'surfaces are built separately. Between the sections they will drift '
        'apart, and the model will get a gap or an overlap.',
    'Маска области (полигоны, необязательно)':
        'Area mask (polygons, optional)',
    'Запас наружу от маски, м':
        'Margin outwards from the mask, m',
    'Слой полигонов, которым обрезается результат. За его пределами грида '
    'не будет вовсе. Между разрезами данных нет, и поверхность там идёт '
    'туда, куда её провела интерполяция: маской задаётся, докуда этому '
    'верить. Обычно это контур выработки, шурфа или подсчётного блока. '
    'Пусто - грид на весь охват контуров.':
        'A polygon layer the result is clipped by. Outside it there is no '
        'grid at all. Between the sections there are no data, and the '
        'surface goes where the interpolation drew it: the mask says how '
        'far to trust that. Usually it is the outline of a working, a pit '
        'or a block. Empty - the grid covers the whole extent of the '
        'contours.',
    'Запас наружу от маски. Пласт обычно продолжается за контур выработки, '
    'и обрезка ровно по нему срезала бы то, что есть в данных.':
        'A margin outwards from the mask. The bed usually continues beyond '
        'the outline of a working, and clipping exactly along it would cut '
        'away what the data do hold.',
    'Маска не дала ни одного кольца, обрезки не будет.':
        'The mask yielded no ring at all, there will be no clipping.',
    'Маска не накрыла ни одной ячейки грида. Обычно это разные системы '
    'координат у маски и у контуров либо маска в стороне от участка.':
        'The mask covered no cell of the grid. Usually the mask and the '
        'contours are in different coordinate systems, or the mask lies '
        'away from the area.',
    'Обрезано маской: осталось %.1f процента ячеек. За её пределами грида '
    'нет: между разрезами данных нет, и маской задано, докуда поверхности '
    'верить.':
        'Clipped by the mask: %.1f percent of the cells are left. Outside '
        'it there is no grid: between the sections there are no data, and '
        'the mask says how far to trust the surfaces.',
    'Пласт %s: контуров %d на %d плоскостях разреза. Вложенные контуры '
    'разобраны по внешней границе: кровля по самому верхнему, подошва '
    'по самому нижнему.':
        'Bed %s: %d outlines on %d section planes. The nested outlines are '
        'taken by the outer boundary: the roof from the topmost, the floor '
        'from the lowest.',
    'Пласт %s: точек %d, мощность на разрезах %.2f .. %.2f м.':
        'Bed %s: %d points, thickness on the sections %.2f .. %.2f m.',
    'Пласт %s, %s: разрезы сошлись не меньше чем в %d местах, отметки '
    'расходятся до %.2f м, наибольшее в точке %.2f, %.2f.':
        'Bed %s, %s: the sections meet in at least %d places, the marks '
        'disagree by up to %.2f m, the largest at the point %.2f, %.2f.',
    'Пласт %s, %s: расхождение больше наименьшей мощности пласта. '
    'Интерполяция усреднит его молча, и модель выйдет правдоподобной '
    'и неверной.':
        'Bed %s, %s: the disagreement is larger than the smallest thickness '
        'of the bed. The interpolation will average it silently, and the '
        'model will come out plausible and wrong.',
    'Поле номера пласта. Каждый пласт даёт в гриде два канала: кровлю и '
    'подошву.':
        'The field of the bed number. Every bed gives two bands in the grid: '
        'a roof and a floor.',
    'Слой контуров на разрезах: полигоны с настоящими Z. Положение разрезов '
    'берётся из самой геометрии, по вершинам контура, и нигде не '
    'спрашивается. Плоский чертёжный разрез не годится: у него X и Y это '
    'координаты на листе, а отметок нет вовсе. Тип геометрии должен быть '
    'PolygonZ или MultiPolygonZ.':
        'A layer of outlines on sections: polygons with real Z. The position '
        'of the sections is taken from the geometry itself, from the vertices'
        ' of the outline, and is never asked for. A flat drawn section is no '
        'good: its X and Y are coordinates on the sheet and there are no '
        'elevations at all. The geometry type must be PolygonZ or '
        'MultiPolygonZ.',
    'Строит грид пластов по контурам, нарисованным на разрезах.\n\nКаждое '
    'кольцо идёт по кровле вперёд и по подошве назад, поэтому из него берутся'
    ' две поверхности. Они интерполируются по площади мультисеточными '
    'B-сплайнами, и пространство между разрезами заполняется.\n\nПоложение '
    'разрезов в пространстве берётся из самой геометрии, по вершинам '
    'контуров. Задавать линии разрезов отдельно не надо. Плоский чертёжный '
    'разрез не годится: у него нет настоящих отметок.\n\nНа выходе '
    'многоканальный грид: на каждый пласт кровля и подошва. Такой грид сцена '
    'показывает телом пласта, а 1.02 и 1.03 считают по нему мощность, блоки и'
    ' объёмы.\n\nПодошва верхнего пласта и кровля нижнего это одна граница, '
    'если геолог провёл их одной линией. Такая граница строится один раз '
    'по обоим наборам точек: построенные порознь, они между разрезами '
    'расходятся, и в модели встаёт щель или нахлёст, которых на разрезе нет. '
    'Порог склейки задаётся допуском.\n\nМаска области обрезает результат: '
    'между разрезами данных нет, и ею задаётся, докуда поверхностям '
    'верить.\n\nМежду разрезами поверхность идёт так, как её провела '
    'интерполяция: данных там нет. Где разрезы пересекаются, отметки на них '
    'должны сойтись. Расхождения считаются и печатаются в журнал вместе '
    'с координатами места, где они наибольшие: с одним числом искать '
    'съехавшую вершину негде.':
        'Builds a grid of beds from the outlines drawn on sections.\n\nEvery '
        'ring runs along the roof one way and along the floor back, so two '
        'surfaces are taken from it. They are interpolated over the area with'
        ' multilevel B-splines, and the space between the sections is '
        'filled.\n\nThe position of the sections is taken from the geometry '
        'itself, from the vertices of the outlines. The lines of the sections'
        ' need not be given separately. A flat drawn section is no good: it '
        'has no real elevations.\n\nThe output is a multiband grid: a roof '
        'and a floor per bed. The scene shows such a grid as a bed body, and '
        '1.02 and 1.03 compute the thickness, the blocks and the volumes from'
        ' it.\n\nThe floor of the upper bed and the roof of the lower one '
        'are one and the same boundary if the geologist drew them as one '
        'line. Such a boundary is built once from both sets of points: built '
        'separately, they drift apart between the sections, and the model '
        'gets a gap or an overlap that the section does not have. The '
        'threshold of the gluing is set by the tolerance.\n\nThe area mask '
        'clips the result: between the sections there is no data, and the '
        'mask says how far to trust the surfaces.\n\nBetween the sections '
        'the surface goes where the interpolation put it: there is no data '
        'there. Where the sections cross, the elevations on them must agree. '
        'The disagreements are counted and go to the log together with the '
        'coordinates of the place where they are largest: with a number '
        'alone there is nowhere to look for the vertex that slipped.',
    'Уровней в мультисеточном приближении. Мало уровней - гладкая '
    'поверхность, много - она ближе к отметкам на разрезах.':
        'Levels in the multilevel approximation. Few levels give a smooth '
        'surface, many bring it closer to the elevations on the sections.',
    'Шаг грида от данных: %.1f м.':
        'Grid step from the data: %.1f m.',
    'Шаг грида по площади. Ноль берёт двухсотую долю охвата.':
        'The step of the grid over the area. Zero takes a two-hundredth of '
        'the extent.',
    'Шаг грида, м (0 - от данных)':
        'Grid step, m (0 means from the data)',
    '2.08 Куб по разрезам': '2.08 A cube from sections',
    'Куб пласта %s': 'Cube of bed %s',
    'Слой не открылся сам: %s': 'The layer did not open by itself: %s',
    'Папка для кубов по пластам': 'Folder for the per-bed cubes',
    'Задайте папку для кубов.': 'Give a folder for the cubes.',
    'Папка, куда лягут кубы: по файлу на пласт, cube_<номер>.tif. '
    'В каждом ноль это граница пласта, и каждый ставится в сцену '
    'изоповерхностью по нулю. Один файл на все пласты не годится: '
    'сцена читает куб целиком и пласты в нём не различит.':
        'The folder the cubes go into: one file per bed, cube_<number>.tif. '
        'In each of them zero is the boundary of the bed, and each '
        'goes into the scene as an isosurface at zero. One file for '
        'all the beds is no good: the scene reads a cube as a whole '
        'and will not tell the beds apart.',
    'Пласт %s: точек опробования %d, из них внутри контуров %d, '
    'шаг %.1f м.':
        'Bed %s: %d sampling points, %d of them inside the outlines, '
        'step %.1f m.',
    'Пласт %s: внутрь контуров не попала ни одна точка. Дело '
    'не в решётке: опробование не нашло внутренности. Проверьте, '
    'что контуры замкнуты и что у пласта есть мощность.':
        'Bed %s: not a single point fell inside the outlines. The '
        'lattice is not to blame: the sampling found no interior. '
        'Check that the outlines are closed and that the bed has '
        'a thickness.',
    'Папка не создана: %s': 'The folder was not created: %s',
    'Записан куб пласта %s: %s': 'Cube of bed %s written: %s',
    'Кубов записано: %d, по одному на пласт. Каждый ставится '
    'в сцену изоповерхностью по уровню ноль.':
        '%d cubes written, one per bed. Each goes into the scene as '
        'an isosurface at level zero.',
    'уровень %d': 'level %d',
    'Решётка %dx%dx%d, уровней %d: ячейка %.1f x %.1f x %.2f м, '
    'память %.0f МБ.':
        'Lattice %dx%dx%d, %d levels: cell %.1f x %.1f x %.2f m, '
        '%.0f MB.',
    'Решётке нужно больше двух гигабайт. Убавьте число уровней '
    'или увеличьте шаг опробования.':
        'The lattice needs more than two gigabytes. Reduce the '
        'number of levels or increase the sampling step.',
    'Пласт %s: куб %.3f .. %.3f.': 'Bed %s: cube %.3f .. %.3f.',
    'Пласт %s: ноль в кубе не встретился, тела не будет. Обычно '
    'это значит, что решётка крупнее пласта: убавьте шаг '
    'опробования или прибавьте уровней.':
        'Bed %s: zero never occurs in the cube, so there will be no '
        'body. Usually that means the lattice is coarser than the '
        'bed: reduce the sampling step or add levels.',
    'Точек очень много. Счёт займёт минуты: если это лишнее, '
    'увеличьте шаг опробования разреза.':
        'There are a great many points. The computation will take '
        'minutes: if that is more than you need, increase the '
        'sampling step on a section.',
    'Слой контуров на разрезах: полигоны с настоящими Z. Положение разрезов в'
    ' пространстве инструмент берёт из самой геометрии - по вершинам контура,'
    ' - и нигде не спрашивает. Плоский чертёжный разрез не годится: у него X '
    'и Y это координаты на листе, а не на местности, и отметок нет вовсе. В '
    'свойствах слоя тип геометрии должен быть PolygonZ или MultiPolygonZ. '
    'Такой даёт забор разреза из Isoliner либо своя оцифровка по трёхмерному '
    'разрезу.':
        'A layer of outlines on sections: polygons with real Z. The tool '
        'takes the position of the sections in space from the geometry '
        'itself, from the vertices of the outline, and never asks for it. A '
        'flat drawn section is no good: its X and Y are coordinates on the '
        'sheet, not on the ground, and there are no elevations at all. The '
        'geometry type must be PolygonZ or MultiPolygonZ. The section fence '
        'from Isoliner gives such a layer, as does your own digitising over a'
        ' three-dimensional section.',
    'Строит куб значений по контурам пластов, нарисованным на '
    'разрезах.\n\nКаждый контур лежит в своей вертикальной плоскости, и '
    'положение этой плоскости берётся из самой геометрии: по вершинам '
    'контура, у которых есть X, Y и Z. Задавать линии разрезов отдельно не '
    'надо.\n\nПлоскость каждого разреза размечается знаком: точке внутри '
    'контура плюс, снаружи минус. Интерполяция заполняет знаком весь объём '
    'между разрезами, и там, где поле меняет знак, проходит ноль. Этот ноль и'
    ' есть поверхность пласта: на самом разрезе он ложится на контур, а между'
    ' разрезами идёт туда, куда провела интерполяция.\n\nДальше куб читается '
    'сценой как изоповерхность, а тела и объёмы берутся кнопкой выгрузки '
    'оболочек.\n\nТочность решает частота разрезов, и никакой расчёт этого не'
    ' поправит: между двумя разрезами данных нет. На проверочном теле восемь '
    'разрезов дали ошибку объёма в два процента, четыре - двадцать '
    'один.\n\nГде разрезы пересекаются, границы на них должны сойтись. '
    'Расхождения считаются и печатаются в журнал: молча усреднив их, получишь'
    ' модель, которая выглядит правдоподобно и неверна.':
        'Builds a cube of values from the outlines of beds drawn on '
        'sections.\n\nEvery outline lies in its own vertical plane, and the '
        'position of that plane is taken from the geometry itself: from the '
        'vertices of the outline, which have X, Y and Z. The lines of the '
        'sections need not be given separately.\n\nThe plane of every section'
        ' is marked by sign: plus for a point inside the outline, minus '
        'outside. The interpolation fills the whole volume between the '
        'sections with that sign, and where the field changes sign it passes '
        'through zero. That zero is the surface of the bed: on the section '
        'itself it lies on the outline, and between the sections it goes '
        'where the interpolation put it.\n\nThe scene then reads the cube as '
        'an isosurface, and the bodies and volumes come from the shell export'
        ' button.\n\nThe accuracy is decided by how often the sections are '
        'spaced, and no computation can mend that: between two sections there'
        ' is no data. On a test body eight sections gave an error of two per '
        'cent in volume, four sections gave twenty-one.\n\nWhere the sections'
        ' cross, the boundaries on them must agree. The disagreements are '
        'counted and go to the log: averaging them silently gives a model '
        'that looks plausible and is wrong.',
    'Похоже, это слой оболочек, а не контуры на разрезах: %d '
    'полигонов, почти все треугольные. Инструменту нужны '
    'зарисовки пластов на разрезах - по контуру на пласт, а не '
    'грани готового тела.':
        'This looks like a layer of shells rather than outlines on '
        'sections: %d polygons, almost all of them triangles. The '
        'tool needs the beds drawn on sections - one outline per bed, '
        'not the faces of a finished body.',
    'Шаг куба по вертикали от данных: %.2f м.':
        'Cube step down the vertical from the data: %.2f m.',
    '%s уровень %d':
        '%s level %d',
    '2.09 Куб по разрезам':
        '2.09 A cube from sections',
    'Запас наружу от контура, где ставится минус. Без него интерполяция не '
    'знает, где тело кончается, и растянет его до края куба.':
        'The margin outside the outline where the minus is put. Without it '
        'the interpolation does not know where the body ends and stretches it'
        ' to the edge of the cube.',
    'Запас наружу от контура, м (0 - от шага)':
        'Margin outside the outline, m (0 means from the step)',
    'Контуров без высоты: %d, они пропущены. Разрез должен быть трёхмерным: у'
    ' чертёжного разреза настоящих отметок нет.':
        'Outlines without a height: %d, they were skipped. The section must '
        'be three-dimensional: a drawn section has no real elevations.',
    'Контуров с высотой не нашлось.':
        'No outlines with a height were found.',
    'Контуров: %d, пластов: %d.':
        'Outlines: %d, beds: %d.',
    'Контуры на разрезах (полигоны с Z)':
        'Outlines on sections (polygons with Z)',
    'Куб значений: ноль это граница пласта. Дальше он читается сценой как '
    'изоповерхность, а тела и объёмы берутся кнопкой выгрузки оболочек.':
        'A cube of values: zero is the boundary of the bed. The scene then '
        'reads it as an isosurface, and the bodies and volumes come from the '
        'shell export button.',
    'Номер пласта, если нужен один. Пусто - все.':
        'The number of the bed, if only one is wanted. Empty means all.',
    'Опробовать нечего: контуры лежат в одной плоскости.':
        'There is nothing to sample: the outlines lie in one plane.',
    'Пласт %s: разрезы расходятся в %d местах из %d общих. Там граница '
    'проведена по-разному, и она будет усреднена.':
        'Bed %s: the sections disagree in %d places out of %d shared ones. '
        'The boundary is drawn differently there and will be averaged.',
    'Пласт %s: точек %d.':
        'Bed %s: %d points.',
    'Пластов несколько, и каждый лёг своей стопкой каналов. Показывать их '
    'надо по одному: сцена читает куб целиком и пласты в нём не различит.':
        'There is more than one bed, and each went in as its own stack of '
        'bands. Show them one at a time: the scene reads the cube as a whole '
        'and will not tell the beds apart.',
    'Поле номера пласта':
        'The field of the bed number',
    'Поле номера пласта. Каждый номер считается отдельно и даёт свой канал в '
    'кубе: смешав пласты в один, получишь границу между ними там, где её нет.':
        'The field of the bed number. Every number is computed separately and'
        ' gives its own band in the cube: mixing the beds together puts a '
        'boundary where there is none.',
    'Слой контуров на разрезах: полигоны с настоящими Z. Такой даёт забор '
    'разреза из Isoliner либо своя оцифровка по чертежу.':
        'A layer of outlines on sections: polygons with real Z. The section '
        'fence from Isoliner gives one, as does your own digitising.',
    'Строит куб значений по контурам пластов, нарисованным на '
    'разрезах.\n\nПлоскость каждого разреза опробуется знаком: внутри контура'
    ' плюс, снаружи минус. Нулевой уровень куба и есть граница тела. Дальше '
    'куб читается сценой как изоповерхность, а тела и объёмы берутся кнопкой '
    'выгрузки оболочек.\n\nТочность решает частота разрезов, и никакой расчёт'
    ' этого не поправит: между двумя разрезами данных нет. На проверочном '
    'теле восемь разрезов дали ошибку объёма в два процента, четыре - '
    'двадцать один.\n\nГде разрезы пересекаются, границы на них должны '
    'сойтись. Расхождения считаются и печатаются в журнал: молча усреднив их,'
    ' получишь модель, которая выглядит правдоподобно и неверна.':
        'Builds a cube of values from the outlines of beds drawn on '
        'sections.\n\nThe plane of every section is sampled by sign: plus '
        'inside the outline, minus outside. The zero level of the cube is the'
        ' boundary of the body. The scene then reads the cube as an '
        'isosurface, and the bodies and volumes come from the shell export '
        'button.\n\nThe accuracy is decided by how often the sections are '
        'spaced, and no computation can mend that: between two sections there'
        ' is no data. On a test body eight sections gave an error of two per '
        'cent in volume, four sections gave twenty-one.\n\nWhere the sections'
        ' cross, the boundaries on them must agree. The disagreements are '
        'counted and go to the log: averaging them silently gives a model '
        'that looks plausible and is wrong.',
    'Только этот пласт (пусто - все)':
        'This bed only (empty means all)',
    'Уровней в мультисеточном приближении. Чем больше, тем ближе поверхность '
    'к контурам и тем больше памяти.':
        'Levels in the multilevel approximation. The more there are, the '
        'closer the surface follows the outlines and the more memory it '
        'takes.',
    'Шаг куба по вертикали. Ноль берёт от шага опробования.':
        'The cube step down the vertical. Zero takes it from the sampling '
        'step.',
    'Шаг куба по горизонтали. Ноль берёт от шага опробования.':
        'The cube step in plan. Zero takes it from the sampling step.',
    'Шаг опробования от данных: %.1f м.':
        'Sampling step from the data: %.1f m.',
    'Шаг опробования плоскости разреза. Мельче - точнее граница, но и точек '
    'больше. Ноль берёт от размера контуров.':
        'The step of sampling the plane of a section. Finer gives a more '
        'exact boundary but more points. Zero takes it from the size of the '
        'outlines.',
    'Шаг опробования разреза, м (0 - от данных)':
        'Sampling step on a section, m (0 means from the data)',
    'пласт':
        'bed',
    'О плагине…': 'About the plugin…',
    'О плагине': 'About the plugin',
    'Версия, ссылки, история изменений, журнал':
        'Version, links, changelog, log',
    'Версия %s': 'Version %s',
    'Исходный код': 'Source code',
    'Сообщить об ошибке': 'Report a bug',
    'История изменений': 'Changelog',
    'Руководство (PDF)': 'Manual (PDF)',
    'Журнал': 'Log',
    'Руководство не найдено.': 'The manual was not found.',
    'Журнал ещё не заведён.': 'No log has been started yet.',
    'Выгрузить сцену в файл: GLB, STL или OBJ':
        'Export the scene to a file: GLB, STL or OBJ',
    'glTF (*.glb);;STL (*.stl);;OBJ (*.obj)':
        'glTF (*.glb);;STL (*.stl);;OBJ (*.obj)',
    'Вращать сцену (ещё раз - остановить)':
        'Spin the scene (again to stop)',
    'Снять оборот кадрами PNG': 'Capture a turn as PNG frames',
    'Куда складывать кадры': 'Where to put the frames',
    'Снято кадров: %d, по %d градусов. Склейте их в видео любым '
    'средством: ffmpeg, редактор, что привычнее.':
        'Frames captured: %d, %d degrees apart. Join them into a '
        'video with any tool: ffmpeg, an editor, whatever you use.',
    'Оформление': 'Appearance',
    'Отмывка': 'Hillshade',
    'Градиентный фон': 'Gradient background',
    'Сглаживать края': 'Smooth the edges',
    'Отмывка по наклону поверхности. Поверхность, раскрашенная '
    'шкалой, рисуется одним цветом вершин без света вовсе, '
    'и рельеф внутри одного оттенка пропадает. Ноль - как было.':
        'Shading by the slope of the surface. A surface coloured '
        'by a ramp is drawn with vertex colours and no light at all, '
        'so the relief within one shade is lost. Zero means as before.',
    'Сглаживание краёв линий и подписей. Действует со следующего '
    'открытия окна: режим рисования выбирается при его создании.':
        'Smoothing of the edges of lines and labels. It takes effect '
        'from the next opening of the window: the drawing mode is '
        'chosen when the window is created.',
    'Прозрачность этого слоя. Общая настройка сцены правит '
    'только поверхности: тело не должно просвечивать оттого, '
    'что просвечивает поверхность над ним.':
        'The transparency of this layer. The shared scene setting '
        'governs the surfaces only: a body should not show through '
        'just because the surface above it does.',
    'Цвет слоя %s из поля %s: разобрано %d, не разобрано %d.':
        'Colour of layer %s from field %s: %d parsed, %d not parsed.',
    ' Зашито мелких дыр: %d.': ' Small holes stitched: %d.',
    ' Тел с дырами %d, объём у них не посчитан: в поле holes '
    'число рваных рёбер, в поле pinch - касаний тела самого себя, '
    'они объёму не мешают.':
        ' %d bodies with holes, no volume was computed for them: the '
        'holes field holds the number of torn edges, the pinch field '
        'the number of self-touches, which do not affect the volume.',
    'Тел в слой: %d, треугольников %d, объём %.0f м3.%s Слой '
    'временный, сохраните его в файл.':
        'Bodies into the layer: %d, %d triangles, volume %.0f m3.%s '
        'The layer is temporary, save it to a file.',
    'Незамкнутых тел: %d, объём у них не посчитан. Чтобы оболочка была '
    'замкнутой, включите в сцене «Закрывать выход на край куба».':
        'Open bodies: %d, no volume was computed for them. To make the shell '
        'watertight, switch on «Cap where the body meets the cube edge» in '
        'the scene.',
    'Плотность для подсчёта массы. Ноль означает считать только объём.':
        'The density for computing mass. Zero means compute the volume only.',
    'Разбирает слой оболочек на отдельные тела и считает объём '
    'каждого.\n\nРазбиение составной геометрии средствами QGIS даёт отдельные'
    ' треугольники: связность там не считается, и тел не выходит. Здесь '
    'вершины склеиваются, меш разбирается на связные куски, и каждый кусок '
    'становится своим объектом.\n\nОбъём считается точной формулой по '
    'замкнутой оболочке. У незамкнутого тела он не считается вовсе: число '
    'вышло бы, а смысла в нём нет. Чтобы оболочка была замкнутой, включите в '
    'сцене «Закрывать выход на край куба».':
        'Splits a layer of shells into separate bodies and computes the '
        'volume of each.\n\nSplitting a multipart geometry with the means of '
        'QGIS gives separate triangles: connectivity is not computed there '
        'and no bodies come out. Here the vertices are welded, the mesh is '
        'split into connected pieces, and every piece becomes its own '
        'feature.\n\nThe volume is computed by an exact formula over a '
        'watertight shell. For an open body it is not computed at all: a '
        'number would come out but it would mean nothing. To make the shell '
        'watertight, switch on «Cap where the body meets the cube edge» in '
        'the scene.',
    'Слой оболочек: полигоны с Z. Такой пишет кнопка выгрузки оболочек в '
    'сцене и инструмент 2.04.':
        'A shell layer: polygons with Z. Such a layer is written by the shell'
        ' export button in the scene and by tool 2.04.',
    'Тела':
        'Bodies',
    'Тела мельче этого числа граней не выгружаются: обрывки в полсотни граней'
    ' объёма не несут, а список засоряют.':
        'Bodies smaller than this number of faces are not written out: scraps'
        ' of fifty faces carry no volume and only clutter the list.',
    'Тело на объект: объём, число граней, замкнутость. Геометрия та же, '
    'полигоны с Z.':
        'A body per feature: volume, number of faces, watertightness. The '
        'geometry is the same, polygons with Z.',
    'Уровень %d, решётка %s: наибольшая невязка %.4g, средняя '
    'квадратичная %.4g.':
        'Level %d, lattice %s: largest residual %.4g, root mean square '
        '%.4g.',
    'Наименьшее значение (пусто - без края)':
        'Smallest value (empty means no bound)',
    'Наибольшее значение (пусто - без края)':
        'Largest value (empty means no bound)',
    'Наименьшее значение больше наибольшего.':
        'The smallest value is greater than the largest.',
    'Прижато к краям узлов: %d из %d. Много прижатых значит, '
    'что модель уходит за диапазон, и лучше убавить число '
    'уровней.':
        'Clamped to the bounds: %d nodes of %d. Many clamped means '
        'the model leaves the range, and it is better to reduce '
        'the number of levels.',
    'Наименьшее возможное значение: содержание не бывает ниже '
    'нуля, а метод за диапазон выходит. Что вышло, прижимается '
    'к краю, и на месте выброса получается плато - форма там '
    'теряется. Оставьте пустым, если ограничения нет.':
        'The smallest possible value: a grade is never below zero, '
        'while the method does leave the range. What leaves is '
        'pressed to the bound, and a plateau appears where the '
        'overshoot was - the shape is lost there. Leave it empty '
        'if there is no bound.',
    'Наибольшее возможное значение. Число прижатых узлов '
    'печатается в журнал: по нему видно, годится ли модель.':
        'The largest possible value. The number of clamped nodes '
        'goes to the log: it shows whether the model is any good.',
    '2.07 MBA в объёме':
        '2.07 MBA in volume',
    'Куб: %d x %d x %d, узлов %d.':
        'Cube: %d x %d x %d, %d nodes.',
    'Метод приближает, а не оценивает: ошибки оценки и весов он не даёт. Для '
    'оценки берите кригинг в объёме (2.06).':
        'The method approximates rather than estimates: it gives no '
        'estimation error and no weights. For estimation take kriging in '
        'volume (2.06).',
    'Многоканальный грид: канал это горизонтальный уровень куба. Его читают '
    '2.03, 2.04 и сцена.':
        'A multiband grid: a band is a horizontal level of the cube. It is '
        'read by 2.03, 2.04 and the scene.',
    'Начальная решётка по вертикали':
        'Initial lattice down the vertical',
    'Начальная решётка по вертикали. Разведочные данные вытянуты, и решётка '
    'не обязана быть кубической: километры в плане и метры по мощности это '
    'разные вещи. Меньшее число здесь и растягивает влияние вдоль пласта, и '
    'бережёт память.':
        'The initial lattice down the vertical. Exploration data is elongated'
        ' and the lattice need not be cubic: kilometres in plan and metres in'
        ' thickness are different things. A smaller number here both '
        'stretches the influence along the bed and saves memory.',
    'Начальная решётка по плану':
        'Initial lattice in plan',
    'Начальная решётка по плану: с неё метод начинает и дальше удваивает её '
    'на каждом уровне. Мельче начальная - точнее первое приближение, но и '
    'памяти больше.':
        'The initial lattice in plan: the method starts from it and doubles '
        'it at every level. A finer start gives a better first approximation '
        'but takes more memory.',
    'Остановка по невязке (0 - все уровни)':
        'Stop by residual (0 means all levels)',
    'Остановка по невязке: как только наибольшее отклонение от замеров '
    'опустится ниже, уровни дальше не строятся. Ноль означает строить все.':
        'Stopping by residual: once the largest deviation from the measured '
        'values falls below it, no further levels are built. Zero means build'
        ' them all.',
    'Откуда брать отметку пробы: из высоты геометрии, из поля или как глубину'
    ' от поверхности.':
        'Where the elevation of a sample comes from: the geometry height, a '
        'field, or a depth below a surface.',
    'Поверхность, от которой отсчитывается глубина.':
        'The surface the depth is measured from.',
    'Поле отметки либо глубины, если она не в геометрии.':
        'The field of elevation or depth, when it is not in the geometry.',
    'Поле со значением, которое раскладывается по объёму.':
        'The field with the value spread through the volume.',
    'Решётка %dx%dx%d, уровней %d: последняя %dx%dx%d, память решёток около '
    '%.0f МБ.':
        'Lattice %dx%dx%d, %d levels: the last is %dx%dx%d, the lattices take'
        ' about %.0f MB.',
    'Решётке нужно больше двух гигабайт. Убавьте число уровней или начальную '
    'решётку.':
        'The lattice needs more than two gigabytes. Reduce the number of '
        'levels or the initial lattice.',
    'Сколько раз удваивать решётку. Каждый уровень подхватывает то, что не '
    'смог предыдущий: невязка падает быстро, а память последнего уровня '
    'растёт кубом.':
        'How many times to double the lattice. Every level picks up what the '
        'previous one could not: the residual falls fast, while the memory of'
        ' the last level grows as a cube.',
    'Строит куб значений по разбросанным точкам мультисеточными '
    'B-сплайнами.\n\nГрубая решётка приближает данные, остаток приближается '
    'решёткой вдвое мельче, и так уровень за уровнем. Система уравнений не '
    'решается: работа линейна по числу точек, и на сотнях тысяч замеров метод'
    ' считает там, где кригинг встаёт.\n\nМетод приближает, а не оценивает. '
    'Точного попадания в замеры нет, ошибки оценки он не даёт. Рядом с '
    'кригингом он хорош как тренд, который дальше уточняют кригингом '
    'остатков.\n\nЗа пределами облака точек поверхность уходит куда угодно: у'
    ' краевых коэффициентов нет данных. Обрезайте результат контуром или '
    'поверхностями.':
        'Builds a cube of values from scattered points with multilevel '
        'B-splines.\n\nA coarse lattice approximates the data, the residual '
        'is approximated by a lattice twice as fine, and so on level by '
        'level. No system of equations is solved: the work is linear in the '
        'number of points, and on hundreds of thousands of measurements the '
        'method computes where kriging stalls.\n\nThe method approximates '
        'rather than estimates. It does not hit the measured values exactly '
        'and gives no estimation error. Next to kriging it is good as a '
        'trend, which is then refined by kriging the residuals.\n\nBeyond the'
        ' cloud of points the surface goes anywhere: the edge coefficients '
        'have no data. Clip the result by a contour or by surfaces.',
    'Точки замеров: скважинные пробы, интервалы, что угодно с отметкой и '
    'значением.':
        'Measured points: borehole samples, intervals, anything with an '
        'elevation and a value.',
    'Уровней':
        'Levels',
    'Шаг куба по вертикали (0 - от данных)':
        'Cube step down the vertical (0 means from the data)',
    'Шаг куба по вертикали. Ноль берёт от сети.':
        'The cube step down the vertical. Zero takes it from the net.',
    'Шаг куба по горизонтали (0 - от данных)':
        'Cube step in plan (0 means from the data)',
    'Шаг куба по горизонтали. Ноль берёт от сети опробования.':
        'The cube step in plan. Zero takes it from the sampling net.',
    'Выгружать нечего: в сцене нет тел.':
        'Nothing to export: there are no bodies in the scene.',
    'Выгружено тел: %d, из них замкнутых %d, файл %.1f МБ. '
    'Незамкнутое тело CAD покажет, но телом не сделает.':
        'Exported %d bodies, %d of them watertight, %.1f MB. '
        'CAD will show an open body but will not turn it into a solid.',
    'Оболочки выбранного слоя в слой проекта':
        'Shells of the selected layer into a project layer',
    'Выберите в списке слой-куб.': 'Select a cube layer in the '
        'list.',
    'Выберите в списке слой: куб в режиме изоповерхности либо грид пласта '
    'в режиме тела.':
        'Pick a layer in the list: a cube in isosurface mode or a bed grid '
        'in body mode.',
    'Слой не в режиме изоповерхности или тела пласта.':
        'The layer is not in isosurface or bed body mode.',
    'Слой не в режиме изоповерхности.':
        'The layer is not in isosurface mode.',
    'Оболочек не построено.': 'No shells were built.',
    'Оболочки: %s': 'Shells: %s',
    'Оболочек в слой: %d, треугольников %d. Слой временный, '
    'сохраните его в файл, если нужен назавтра.':
        'Shells into the layer: %d, %d triangles. The layer is '
        'temporary, save it to a file if you need it tomorrow.',
    'Прозрачность слоя': 'Layer transparency',
    'Прозрачность этого слоя поверх общей. Общая правит всю '
    'сцену разом, а здесь можно приглушить один слой, чтобы видеть '
    'тело под ним. Работает и на текстуру.':
        'The transparency of this layer on top of the shared one. '
        'The shared one governs the whole scene at once, while here '
        'a single layer can be dimmed to see the body beneath it. '
        'It works on a texture as well.',
    'Куб %s: отсечка поверхностями убрала ячеек %d, осталось %d.':
        'Cube %s: surface clipping removed %d cells, %d left.',
    'Непрозрачность, %': 'Opacity, %',
    'Цвет оболочки': 'Shell colour',
    'Удалить строку': 'Remove the row',
    'Строка на оболочку. Пустая ячейка берёт автоматическое: цвет '
    'по номеру оболочки, плотность растёт наружу. Снятая галка '
    'убирает оболочку, не стирая строку. Пустая таблица это отсечка '
    'и одна оболочка. Непрозрачность в процентах: сто это плотная '
    'оболочка. По цвету щёлкните дважды - откроется выбор. Правая '
    'кнопка на строке удаляет её.':
        'A row per shell. An empty cell takes the automatic value: the '
        'colour by the shell number, the opacity growing outwards. '
        'Clearing the box removes the shell without erasing the row. '
        'An empty table means the cutoff and one shell. Opacity is in '
        'percent: a hundred is a solid shell. Double-click the colour '
        'to pick one. The right button on a row removes it.',
    'Оболочки': 'Shells',
    'Уровень': 'Level',
    'Цвет': 'Colour',
    'Закрывать выход на край куба':
        'Cap where the body meets the cube edge',
    'Крышки на краю куба: граней %d.':
        'Caps at the cube edge: %d faces.',
    'Маршевая поверхность обрывается на границе куба: тело '
    'выглядит вскрытым, а объём по нему не посчитать. Крышка '
    'закрывает этот выход плоским куском на самой грани. По умолчанию '
    'выключено: крышка нужна не всегда, а на просмотр она добавляет '
    'граней.':
        'A marching surface breaks off at the cube boundary: the '
        'body looks cut open and no volume can be computed from it. '
        'A cap closes that opening with a flat piece on the face '
        'itself. Off by default: a cap is not always needed and it '
        'adds faces to the view.',
    'Слой %s: по уровням %s ничего не построено. Проверьте, '
    'что они лежат внутри размаха значений куба.':
        'Layer %s: nothing was built at levels %s. Check that they '
        'lie within the range of the cube values.',
    'Свои границы интервалов, через пробел':
        'Own interval bounds, space separated',
    'Свои границы интервалов через пробел: 0 5 10 15. Задают '
    'разбивку вместо равных долей. Запятая внутри числа это знак '
    'дроби: 2,5 3 3,5 читается как два с половиной, три и три '
    'с половиной. Порядок и повторы не важны. Ячейка выше '
    'последней границы остаётся в последнем интервале, терять '
    'её нельзя.':
        'Own interval bounds, space separated: 0 5 10 15. They set '
        'the split instead of equal shares. A comma inside a number '
        'is a decimal mark. Order and repeats do not matter. A cell '
        'above the last bound stays in the last interval, it must not '
        'be lost.',
    'Оболочки %s: уровни %s.': 'Shells %s: levels %s.',
    'есть': 'yes',
    'нету': 'no',
    'Подписи короба': 'Box labels',
    'В выгрузку: подписи, знаков %d.':
        'To the export: labels, %d glyphs.',
    'В выгрузку: короб, линий %d, с подписями.':
        'To the export: the box, %d lines, with labels.',
    'Выгружено: тел %d, короб %s, преувеличение %s, файл %.1f МБ.':
        'Exported: %d bodies, box %s, exaggeration %s, %.1f MB.',
    'Часть %s: вершин %d, граней %d, линий %d':
        'Part %s: %d vertices, %d faces, %d lines',
    'Выгрузка: преувеличение %s.': 'Export: exaggeration %s.',
    'применено': 'applied',
    'не применено': 'not applied',
    'Выгрузка с преувеличением %.2f, середина по отметке %.1f.':
        'Export with exaggeration %.2f, centre at elevation %.1f.',
    'Секторов поиска (0 - от данных)':
        'Search sectors (0 means from the data)',
    'Секторов поиска от данных: %d.':
        'Search sectors from the data: %d.',
    'Ноль берёт от данных: у скважин деление нужно, иначе все '
    'соседи окажутся в одном стволе, а у проб в плане оно только '
    'рвёт поле. Граница сектора идёт лучом от узла, и на ней набор '
    'соседей меняется скачком: отсюда звёзды на почвенных пробах.':
        'Zero takes it from the data: boreholes need the split, or all '
        'the neighbours land in one hole, while for samples in plan it '
        'only tears the field. A sector boundary runs as a ray from the '
        'node, and the set of neighbours changes across it in a jump: '
        'hence the stars on soil samples.',
    'Ноль берёт от данных: у скважин деление нужно, иначе все '
    'соседи окажутся в одном стволе, а у одиночных проб в плане оно '
    'только рвёт поле.':
        'Zero takes it from the data: boreholes need the split, or all '
        'the neighbours land in one hole, while for single samples in '
        'plan it only tears the field.',
    'Вид': 'View',
    'Обрезка': 'Clipping',
    'Координатный короб': 'Coordinate box',
    'По контуру': 'By contour',
    'По отметке': 'By elevation',
    'По поверхностям': 'By surfaces',
    'Сетка': 'Grid',
    'Координатная сетка': 'Coordinate grid',
    'Шаг сетки, м': 'Grid step, m',
    'Только короб': 'Box only',
    'Пол': 'Floor',
    'Пол и стены': 'Floor and walls',
    'Стены': 'Walls',
    '(от размаха)': '(from the span)',
    'Сетка: линий %d.': 'Grid: %d lines.',
    'На каких плоскостях короба рисовать сетку. Пол даёт масштаб '
    'в плане, стены - по отметкам, что для разреза важнее.':
        'On which planes of the box to draw the grid. The floor '
        'gives the scale in plan, the walls give it by elevation, '
        'which matters more for a section.',
    'Шаг сетки в единицах карты. Ноль берёт круглый шаг '
    'от размаха сцены. Слишком мелкий шаг укрупняется сам: сетка '
    'гуще самой сцены читать не помогает, а рисуется долго.':
        'The grid step in map units. Zero takes a round step from '
        'the span of the scene. Too fine a step is coarsened by '
        'itself: a grid denser than the scene does not help reading '
        'and takes long to draw.',
    'С': 'N',
    'Координатный короб: деления и подписи по осям':
        'Coordinate box: ticks and labels along the axes',
    'Подписей осей больше %d, остальные не ставим: они забили бы '
    'сцену.':
        'More than %d axis labels, the rest are not placed: they '
        'would clutter the scene.',
    'Сглаживание, проходов': 'Smoothing, rounds',
    'Отбросить куски мельче, граней':
        'Drop parts smaller than, faces',
    'Отброшено кусков: %d из %d.': 'Parts dropped: %d of %d.',
    'Сколько проходов сглаживания. Маршевая поверхность идёт '
    'ступенями по ячейкам куба, и сглаживание их сажает. Тело '
    'при этом слегка ужимается, поэтому для подсчёта объёма '
    'берите несглаженное.':
        'How many rounds of smoothing. A marching surface goes in '
        'steps of the cube cells, and smoothing settles them. The '
        'body shrinks a little in the process, so for volume '
        'computation take the unsmoothed one.',
    'Отбросить куски мельче этого числа граней. Мелкие обрывки '
    'на поверхности шумят и мешают читать форму. Если порог '
    'убирает всё, поверхность остаётся как была: пустая сцена '
    'это не чистка, а потеря.':
        'Drop parts smaller than this number of faces. Small scraps '
        'on the surface add noise and make the shape harder to '
        'read. If the threshold removes everything, the surface '
        'stays as it was: an empty scene is not cleaning but loss.',
    'Названия интервалов через запятую: низкое, среднее, высокое. Пишутся в '
    'поле name. Недостающие остаются пустыми, лишние отбрасываются.':
        'Interval names, comma separated: low, medium, high. They go into the'
        ' name field. Missing ones stay empty, extra ones are dropped.',
    'Названия интервалов, через запятую':
        'Interval names, comma separated',
    'Ноль строит одно тело. Несколько интервалов дают объект на каждый, и '
    'тело можно раскрасить по содержанию. Не читается, если заданы свои '
    'границы.':
        'Zero builds one body. Several intervals give a feature each, and the'
        ' body can be coloured by grade. Not read when own bounds are given.',
    'Отсечка поверхностями убрала всё. Проверьте, что кровля выше подошвы и '
    'что поверхности накрывают куб.':
        'Surface clipping removed everything. Check that the roof is above '
        'the floor and that the surfaces cover the cube.',
    'Отсечка поверхностями убрала точек: %d, осталось %d.':
        'Surface clipping removed %d points, %d left.',
    'Поверхность отсечки сверху не открылась.':
        'The upper clipping surface did not open.',
    'Поверхность отсечки снизу не открылась.':
        'The lower clipping surface did not open.',
    'Поверхность сверху: остаются точки ниже неё. Так отсекают всё выше '
    'дневного рельефа или выше кровли пласта.':
        'The surface above: the points below it stay. That is how everything '
        'above the ground surface or above the bed roof is cut off.',
    'Поверхность снизу: остаются точки выше неё. Вместе с верхней остаётся '
    'только пласт.':
        'The surface below: the points above it stay. Together with the upper'
        ' one only the bed is left.',
    'Свои границы интервалов через запятую: 0, 5, 10, 15. Задают разбивку '
    'вместо равных долей. Порядок и повторы не важны. Ячейка выше последней '
    'границы остаётся в последнем интервале, терять её нельзя.':
        'Own interval bounds, comma separated: 0, 5, 10, 15. They set the '
        'split instead of equal shares. Order and repeats do not matter. A '
        'cell above the last bound stays in the last interval, it must not be'
        ' lost.',
    'Свои границы интервалов: %s.':
        'Own interval bounds: %s.',
    'Отсечка сверху (поверхность)': 'Clip above (surface)',
    'Отсечка снизу (поверхность)': 'Clip below (surface)',
    'Поверхность сверху: остаётся то, что ниже неё. Так отсекают '
    'всё выше дневного рельефа или выше кровли пласта.':
        'The surface above: what lies below it stays. That is how '
        'everything above the ground surface or above the bed roof '
        'is cut off.',
    'Поверхность снизу: остаётся то, что выше неё. Вместе '
    'с верхней оставляет только пласт.':
        'The surface below: what lies above it stays. Together with '
        'the upper one it leaves the bed alone.',
    'Полуширина коридора, м': 'Corridor half-width, m',
    'Обрезка по отметке': 'Clipping by elevation',
    'Снять': 'Clear',
    'Обрезка по отметке. Контур и коридор режут только в плане, '
    'а разрез по пачке пластов задаётся отметками. Обе строки живут '
    'в свойствах сцены, рядом с остальной обрезкой. Снимаются '
    'кнопкой «Снять» или общей кнопкой очистки на плашке.':
        'Clipping by elevation. A contour and a corridor cut in plan '
        'only, while a section across a pile of beds is set by '
        'elevations. Both rows live in the scene properties, next to '
        'the rest of the clipping. They are cleared by the «Clear» '
        'button or by the general clear button on the toolbar.',
    'Полуширина коридора вдоль линии, в единицах карты. Профиль '
    'разреза и данные по обе стороны от него. Работает при режиме '
    '«Коридор вдоль линии».':
        'The half-width of the corridor along the line, in map units. '
        'The section profile and the data on both sides of it. Works '
        'in the «Corridor along a line» mode.',
    'Тело не замкнуто до резки: тел %d, краевых рёбер %d. '
    'Крышку на срезе такому телу не построить: кольцо не замыкается. '
    'Пересоберите тело в 2.04 этой версией со снятым слиянием '
    'соседних граней.':
        'The body is not watertight before the cut: %d bodies, %d '
        'boundary edges. Such a body cannot be capped: the ring '
        'does not close. Rebuild the body in 2.04 with this version '
        'and the merging of neighbouring faces cleared.',
    'Область обрезки была негодной по геометрии и исправлена.':
        'The clip area was geometrically invalid and was repaired.',
    'Крышка: вызовов %d, из них с гранями %d.':
        'Cap: %d calls, %d of them with faces.',
    'кольца среза не собрались': 'the cut rings did not close',
    'область обрезки не построилась': 'the clip area was not built',
    'после резки граней не осталось': 'no faces left after the cut',
    'у области обрезки нет границы': 'the clip area has no boundary',
    'краевых рёбер нет: срез не состоялся':
        'no boundary edges: the cut did not happen',
    ' Ранний выход: %s.': ' Early exit: %s.',
    'Крышка: краевых рёбер %d, на контуре среза %d, полигонов '
    'собрано %d, не разбилось %d.%s':
        'Cap: %d boundary edges, %d on the cut contour, %d polygons '
        'built, %d not tessellated.%s',
    'Границы отметок перепутаны: z\u2265 %.1f и z\u2264 %.1f '
    'навстречу друг другу. Сцена выйдет пустой.':
        'The elevation bounds are the wrong way round: z\u2265 %.1f '
        'and z\u2264 %.1f face each other. The scene will come out '
        'empty.',
    'Слияние делает слой в разы легче, но рвёт границу тела '
    'Т-образными стыками. Такое тело нельзя ни посчитать по объёму, '
    'ни разрезать в сцене: срез останется открытым, крышку поставить '
    'не на что. Для подсчёта и для разрезов флаг снимайте.':
        'Merging makes the layer many times lighter but tears the '
        'boundary of the body with T-junctions. Such a body can neither '
        'be measured by volume nor cut in the scene: the cut stays '
        'open, there is nothing to cap it with. For volumes and cuts '
        'clear the flag.',
    'Срез остался открытым у тел: %d, краевых рёбер до резки %d. '
    'Оболочка разорвана ещё до резки, и крышку не построить никаким '
    'способом: кольцо среза не замыкается. Соберите тело в 2.04 '
    'со снятым слиянием соседних граней - тогда оболочка замкнута '
    'и срез закрывается.':
        'The cut stayed open on %d bodies, %d boundary edges before '
        'the cut. The shell is torn before any cutting, and no method '
        'can cap it: the ring of the cut does not close. Build the body '
        'in 2.04 with the merging of neighbouring faces cleared - then '
        'the shell is watertight and the cut closes.',
    ' До линии: от %.0f до %.0f м.':
        ' To the line: from %.0f to %.0f m.',
    ' Линия проведена мимо данных: ближайшая грань дальше '
    'полуширины.':
        ' The line runs past the data: the nearest face is beyond '
        'the half-width.',
    'Обрезка: осталось %d граней из %d. Источник: %s, режим: %s, '
    'полуширина %.0f.%s%s':
        'Clip: %d faces left of %d. Source: %s, mode: %s, half-width '
        '%.0f.%s%s',
    ' Отметка: %s .. %s.': ' Elevation: %s .. %s.',
    'без границы': 'no bound',
    'нет': 'none',
    'Анизотропию замерить не удалось, взята единица.':
        'The anisotropy could not be measured, one was taken.',
    'Вариограмма: длина связи в плане %.0f, по вертикали %.1f, анизотропия '
    '%.4f.':
        'Variogram: range in plan %.0f, vertical %.1f, anisotropy %.4f.',
    'Вторая поверхность. С ней отметка становится долей мощности: ноль на '
    'кровле, единица на подошве.':
        'The second surface. With it the elevation becomes a fraction of the '
        'thickness: zero at the roof, one at the floor.',
    'Кровля или подошва пласта. С ней вертикаль отсчитывается от поверхности,'
    ' и расчёт идёт вдоль напластования. Вариограмма меряется уже в '
    'спрямлённых координатах: замерив в абсолютных, а посчитав в спрямлённых,'
    ' получишь модель не от этих данных.':
        'The roof or the floor of the bed. With it the vertical is counted '
        'from the surface and the computation runs along the bedding. The '
        'variogram is measured in the flattened coordinates already: '
        'measuring it in absolute ones and computing in flattened ones would '
        'give a model that does not belong to this data.',
    'Ноль замеряет вариограмму по данным и берёт отношение вертикальной длины'
    ' связи к плановой. Это тот случай, когда гадать не нужно. Своё число '
    'задаёт масштаб вручную: большое сглаживает по вертикали, малое сохраняет'
    ' различие по глубине.':
        'Zero measures the variogram on the data and takes the ratio of the '
        'vertical range to the plan one. This is the case where no guessing '
        'is needed. A value of your own sets the scale by hand: a large one '
        'smooths along the vertical, a small one keeps the difference with '
        'depth.',
    'Вне опорной поверхности пропущено проб: %d.':
        'Samples skipped outside the reference surface: %d.',
    'Вторая поверхность. С ней отметка становится долей мощности: ноль на '
    'кровле, единица на подошве. Так сопоставляются пачки разной мощности, и '
    'раздув не размазывает связь. Анизотропия тогда считается по доле, а не '
    'по метрам.':
        'The second surface. With it the elevation becomes a fraction of the '
        'thickness: zero at the roof, one at the floor. That is how packs of '
        'different thickness are matched, and a swell no longer smears the '
        'connection. Anisotropy is then counted in fractions rather than '
        'metres.',
    'Кровля или подошва пласта. С ней вертикаль отсчитывается от поверхности,'
    ' и интерполяция идёт вдоль напластования, а не поперёк. У пласта со '
    'складкой это меняет не точность на проценты, а осмысленность результата.':
        'The roof or the floor of the bed. With it the vertical is counted '
        'from the surface and the interpolation runs along the bedding rather'
        ' than across it. On a folded bed that changes not the accuracy by a '
        'few per cent but whether the result means anything at all.',
    'Опорная поверхность (спрямление)':
        'Reference surface (flattening)',
    'Опорная поверхность не открылась.':
        'The reference surface did not open.',
    'Опорная поверхность не покрывает пробы.':
        'The reference surface does not cover the samples.',
    'Подошва для доли мощности':
        'Floor for the thickness fraction',
    'Подошва не открылась либо не совпадает с кровлей по сетке.':
        'The floor did not open, or its grid does not match the roof.',
    'Спрямление: размах отметки %.2f, был %.2f м, спрямлено проб %d.':
        'Flattening: elevation span %.2f, was %.2f m, %d samples flattened.',
    'Стиль слоя %s: один символ на слой, %s.':
        'Layer style %s: one symbol for the layer, %s.',
    'пусто': 'empty',
    'Снять обрезку по отметке': 'Clear the elevation clip',
    'Обрезка по отметке снята.': 'The elevation clip is cleared.',
    'Проб: %d.': 'Samples: %d.',
    'Проб очень много. Кригинг держит матрицы размером с число проб, '
    'узлы считаются мелкими порциями, и счёт будет долгим. '
    'Проредите пробы либо укрупните шаг сетки.':
        'There are a great many samples. Kriging holds matrices the '
        'size of the sample count, nodes are computed in small batches, '
        'and the run will be slow. Thin the samples or coarsen the '
        'grid step.',
    'Поле значения, по которому строится куб. Именно его и проверяем. У '
    'демонстрационных данных из 2.01 это grade.':
        'The value field the cube is built from. That is what we check. On '
        'the demonstration data from 2.01 it is grade.',
    'Поля слоя: hole номер скважины, from_m и to_m интервал пробы от устья '
    'вниз, grade содержание с шумом, truth содержание по модели без шума, '
    'zone единица внутри тела.\nДля интерполяции берите grade. Поле truth '
    'нужно, чтобы отделить ошибку метода от шума опробования, а hole - чтобы '
    'исключать скважину целиком в 2.05.':
        'Layer fields: hole the borehole number, from_m and to_m the sample '
        'interval measured down from the collar, grade the assay with noise, '
        'truth the grade from the model without noise, zone one inside the '
        'body.\nFor interpolation take grade. The truth field is there to '
        'separate the error of the method from the sampling noise, and hole '
        'to remove a whole borehole in 2.05.',
    'Числовое поле, значение которого раскладывается по кубу. У '
    'демонстрационных данных из 2.01 это grade.':
        'The numeric field whose value is spread through the cube. On the '
        'demonstration data from 2.01 it is grade.',
    'Числовое поле, значение которого раскладывается по кубу: содержание, '
    'концентрация, влажность. У демонстрационных данных из 2.01 это grade, а '
    'не hole: иначе куб выйдет по номерам скважин.':
        'The numeric field whose value is spread through the cube: grade, '
        'concentration, moisture. On the demonstration data from 2.01 it is '
        'grade rather than hole: otherwise the cube comes out of borehole '
        'numbers.',
    'Объёмная заливка': 'Volume fill',
    'Плотность заливки': 'Fill density',
    'В этой сборке нет объёмной заливки.':
        'This build has no volume fill.',
    'Заливка %s: ячеек %d, плотность %.2f.':
        'Fill %s: %d cells, density %.2f.',
    'Слой %s: заливка не построена. Куб пуст либо крупнее предела.':
        'Layer %s: the fill was not built. The cube is empty or larger '
        'than the limit.',
    'Плотность объёмной заливки. Ниже отсечки заливки нет вовсе, '
    'выше неё непрозрачность растёт со значением. Заливка не заменяет '
    'оболочку, а дополняет её: оболочка отвечает, где граница тела, '
    'заливка - как значение меняется вокруг.':
        'The density of the volume fill. Below the cutoff there is no '
        'fill at all, above it the opacity grows with the value. The '
        'fill does not replace a shell but adds to it: the shell says '
        'where the boundary of the body is, the fill says how the '
        'value changes around it.',
    'Стенка по линии': 'Wall along a line',
    'Шаг стенки, м (0 - шаг грида)':
        'Wall step, m (0 means the grid step)',
    'Стенке нужна линия: нарисуйте её или выберите слой в списке '
    'обрезки.':
        'The wall needs a line: draw one or pick a layer in the clip '
        'list.',
    'Слой %s: стенка вышла пустой, линия за пределами куба.':
        'Layer %s: the wall came out empty, the line is outside the '
        'cube.',
    'Стенка %s: узлов %d, треугольников %d, значения %.3f .. %.3f.':
        'Wall %s: %d nodes, %d triangles, values %.3f .. %.3f.',
    'Шаг узлов стенки вдоль линии, в единицах карты. Ноль берёт шаг '
    'грида: мельче него данных всё равно нет. Линия берётся '
    'из списка обрезки, поэтому нарисуйте её или выберите слой '
    'там же.':
        'The step of the wall nodes along the line, in map units. Zero '
        'takes the grid step: finer than that there is no data anyway. '
        'The line comes from the clip list, so draw one or pick a '
        'layer there.',
    'Значения: %.3f .. %.3f, в пробах %.3f .. %.3f.':
        'Values: %.3f .. %.3f, in the samples %.3f .. %.3f.',
    'Оценка вышла за размах проб. У кригинга веса бывают '
    'отрицательными, и на содержаниях это даёт значения ниже нуля. '
    'Гауссова модель к этому склонна сильнее прочих: попробуйте '
    'сферическую или поднимите самородок.':
        'The estimate went outside the range of the samples. Kriging '
        'weights can be negative, and on grades that gives values '
        'below zero. The gaussian model is more prone to it than the '
        'others: try the spherical one or raise the nugget.',
    '2.06 Кригинг в объёме':
        '2.06 Kriging in three dimensions',
    'Анизотропия (0 - от данных)':
        'Anisotropy (0 means from the data)',
    'Вариограмма в плане: %s, длина связи %.0f м, пар %d.':
        'Variogram in plan: %s, range %.0f m, %d pairs.',
    'Вариограмма замеряется по самим данным: длина связи из планового замера,'
    ' самородок из вертикального. Задавать три числа на глаз бессмысленно, их'
    ' и надо было замерить.':
        'The variogram is measured on the data itself: the range from the '
        'plan measurement, the nugget from the vertical one. Setting three '
        'numbers by eye is pointless, measuring them was the whole idea.',
    'Вариограмма по вертикали: длина связи %.1f м, самородок %.3f, пар %d.':
        'Vertical variogram: range %.1f m, nugget %.3f, %d pairs.',
    'Вид модели. Разница между ними невелика, важнее поведение у нуля: '
    'гауссова даёт слишком гладкое поле там, где данные шумят.':
        'The kind of model. The difference between them is small, what '
        'matters more is the behaviour near zero: the gaussian one gives too '
        'smooth a field where the data is noisy.',
    'Гауссова':
        'Gaussian',
    'Грид, от которого отсчитывается глубина. Нужен пробам, где записана '
    'глубина, а не отметка.':
        'The grid the depth is measured from. Needed by samples that record a'
        ' depth rather than an elevation.',
    'Дисперсия оценки: %.4f .. %.4f, среднее %.4f.':
        'Estimation variance: %.4f .. %.4f, mean %.4f.',
    'Длина связи, м':
        'Range, m',
    'Для отметки из поля это сама отметка, для глубины это глубина вниз от '
    'поверхности.':
        'For elevation from a field this is the elevation itself, for depth '
        'it is the depth measured down from the surface.',
    'Замерить вариограмму по данным':
        'Measure the variogram on the data',
    'Куб дисперсии оценки':
        'Cube of the estimation variance',
    'Куб дисперсии оценки, тех же размеров. В самой пробе ноль, дальше от '
    'данных растёт. Это карта доверия, и она единственное, что кригинг даёт '
    'всегда, независимо от густоты сети.':
        'A cube of the estimation variance, of the same size. Zero at a '
        'sample, growing away from the data. It is a map of trust, and it is '
        'the one thing kriging always gives, whatever the density of the '
        'grid.',
    'Куб значений: канал это горизонтальный уровень.':
        'A cube of values: a band is a horizontal level.',
    'Модель вариограммы':
        'Variogram model',
    'Модель: %s, самородок %.3f, порог %.3f, длина связи %.0f м, анизотропия '
    '%.3f.':
        'Model: %s, nugget %.3f, sill %.3f, range %.0f m, anisotropy %.3f.',
    'Ноль берёт отношение вертикальной длины связи к плановой, замеренное по '
    'данным. Это тот случай, когда гадать не нужно.':
        'Zero takes the ratio of the vertical range to the plan one, measured'
        ' on the data. This is the case where no guessing is needed.',
    'Ноль берёт половину шага опробования. Крупнее значит слить соседние '
    'замеры и потерять различие по глубине.':
        'Zero takes half the sampling step. Coarser means merging '
        'neighbouring samples and losing the difference with depth.',
    'Ноль берёт пятую часть расстояния между точками плана. Мельче делать '
    'незачем: данных в промежутке всё равно нет, а число узлов растёт как '
    'квадрат.':
        'Zero takes a fifth of the distance between places in plan. Finer is '
        'pointless: there is no data in between anyway, and the node count '
        'grows as a square.',
    'Ноль берёт четверть охвата данных. Узел, где точек в радиусе не '
    'набралось, остаётся пропуском.':
        'Zero takes a quarter of the data extent. A node with too few points '
        'within the radius stays a gap.',
    'Общий разброс данных, к которому вариограмма выходит на больших '
    'расстояниях.':
        'The overall scatter of the data the variogram reaches at large '
        'distances.',
    'Окружность вокруг узла делится на равные части, из каждой берётся своя '
    'доля точек. Без этого при анизотропии все соседи оказываются в одной '
    'скважине.':
        'The circle around the node is split into equal parts and each gives '
        'its share of points. Without this, under anisotropy all the '
        'neighbours land in one borehole.',
    'Плоский слой отдаёт нулевую Z у каждой точки. Если брать её из '
    'геометрии, все пробы лягут в одну плоскость и куб выйдет бессмысленным.':
        'A flat layer gives a zero Z at every point. Taking it from the '
        'geometry would put every sample in one plane and the cube would be '
        'meaningless.',
    'Показательная':
        'Exponential',
    'Порог':
        'Sill',
    'Разброс, который не убывает даже у соседних проб: ошибка опробования и '
    'изменчивость мельче сети. Читается, только если снят автоматический '
    'замер.':
        'The scatter that does not fall even between neighbouring samples: '
        'sampling error and variability finer than the grid. Read only when '
        'the automatic measurement is off.',
    'Расстояние, после которого пробы уже ничего не знают друг о друге.':
        'The distance beyond which samples know nothing about each other.',
    'Самородковый эффект':
        'Nugget effect',
    'Соседей на узел':
        'Neighbours per node',
    'Соседей на узел. Кригинг решает систему размером с их число, поэтому '
    'цена растёт как куб: шестнадцать это обычный выбор, тридцать два уже '
    'заметно дороже.':
        'Neighbours per node. Kriging solves a system the size of their '
        'number, so the cost grows as a cube: sixteen is the usual choice, '
        'thirty two is already noticeably dearer.',
    'Сферическая':
        'Spherical',
    'Считает куб значений кригингом и вторым выходом даёт куб дисперсии '
    'оценки.\n\nЧЕМ ОТЛИЧАЕТСЯ ОТ 2.02. Обратные расстояния взвешивают по '
    'одному расстоянию: им всё равно, на каком расстоянии связь пропадает и '
    'сколько разброса приходится на ошибку опробования. Кригинг берёт веса из'
    ' вариограммы, поэтому знает и то, и другое. Ещё он учитывает, что соседи'
    ' знают друг про друга: две пробы рядом несут почти одно и то же, и '
    'двойного голоса им не даётся.\n\nКОГДА ЭТО ОКУПАЕТСЯ. Не всегда. На '
    'демонстрационных данных при густой сети кригинг выигрывает у обратных '
    'расстояний до восьми процентов, при редкой проигрывает до девяти. '
    'Перелом там, где шаг сети около половины длины связи. Причина проста: '
    'когда скважины стоят реже, соседние уже почти ничего не знают друг о '
    'друге, веса выходят почти равными у любого метода, и разница уходит в '
    'шум. Числа сети и длины связи инструмент печатает в журнал, так что '
    'решение видно сразу.\n\nДИСПЕРСИЯ. Второй куб даёт то, чего у обратных '
    'расстояний нет вовсе: в самой пробе она ноль, дальше от данных растёт. '
    'Это карта доверия, и на редкой сети она единственная причина брать '
    'кригинг.\n\nВАРИОГРАММА. Замеряется по самим данным. Длина связи берётся'
    ' из планового замера, самородок из вертикального, анизотропия как '
    'отношение длин. Самородок из планового замера брать нельзя: в плане пар '
    'ближе шага сети нет вовсе, первый интервал начинается там же, и '
    'самородок оттуда это продолжение прямой к нулю через пустоту. По стволу '
    'пары есть с трёх метров.\n\nПРОВЕРКА. Насколько верить получившемуся, '
    'отвечает 2.05. Задавайте там поле скважины: проверка по одной пробе '
    'льстит модели в разы, потому что соседей она берёт из того же ствола.':
        'Computes a cube of values by kriging and gives a cube of the '
        'estimation variance as a second output.\n\nHOW IT DIFFERS FROM 2.02.'
        ' Inverse distances weigh by distance alone: they do not care at what'
        ' distance the connection fades or how much of the scatter is '
        'sampling error. Kriging takes its weights from the variogram and so '
        'knows both. It also accounts for neighbours knowing about each '
        'other: two samples side by side carry almost the same thing and are '
        'not given a double vote.\n\nWHEN IT PAYS OFF. Not always. On the '
        'demonstration data kriging beats inverse distances by up to eight '
        'per cent on a dense grid and loses by up to nine on a sparse one. '
        'The turn is where the grid step is about half the range. The reason '
        'is simple: when holes stand farther apart, neighbouring ones know '
        'almost nothing about each other, the weights come out nearly equal '
        'for any method, and the difference goes into noise. The tool prints '
        'the grid step and the range to the log, so the decision is visible '
        'at once.\n\nTHE VARIANCE. The second cube gives what inverse '
        'distances lack entirely: zero at a sample, growing away from the '
        'data. It is a map of trust, and on a sparse grid it is the only '
        'reason to take kriging.\n\nTHE VARIOGRAM. It is measured on the data'
        ' itself. The range comes from the plan measurement, the nugget from '
        'the vertical one, the anisotropy as the ratio of the ranges. The '
        'nugget must not be taken from the plan measurement: in plan there '
        'are no pairs closer than the grid step at all, the first interval '
        'starts right there, and a nugget from it is a straight line '
        'continued to zero through emptiness. Down the hole there are pairs '
        'from three metres.\n\nTHE CHECK. How far to trust the result is '
        'answered by 2.05. Set the borehole field there: a check by single '
        'samples flatters the model several times over, because it takes '
        'neighbours from the same hole.',
    'Тот же слой проб, что подаётся в 2.02. Отметка задаётся ниже так же, как'
    ' там.':
        'The same layer of samples that goes into 2.02. The elevation is set '
        'below in the same way.',
    'Числовое поле, значение которого раскладывается по кубу.':
        'The numeric field whose value is spread through the cube.',
    'Шаг сети %.0f м больше половины длины связи %.0f м. На такой сети '
    'кригинг обычно не точнее обратных расстояний: соседние скважины почти '
    'ничего не знают друг о друге. Дисперсия оценки при этом остаётся '
    'полезной.':
        'The grid step of %.0f m is above half the range of %.0f m. On such a'
        ' grid kriging is usually no more accurate than inverse distances: '
        'neighbouring holes know almost nothing about each other. The '
        'estimation variance stays useful all the same.',
    'Исключаем по скважине, их %d.':
        'Removing whole boreholes, %d of them.',
    'Номер скважины. С ним из выборки убирается ствол целиком, и проверка '
    'меряет умение попасть между скважинами. Без него убирается одна проба, '
    'соседи берутся из того же ствола, и ошибка выходит в разы меньше '
    'настоящей.':
        'The borehole number. With it the whole hole is removed from the set '
        'and the check measures the ability to hit between holes. Without it '
        'one sample is removed, the neighbours come from the same hole, and '
        'the error comes out several times smaller than the real one.',
    'Поле скважины (0 - по одной пробе)':
        'Borehole field (empty means one sample at a time)',
    'Поле скважины пропущено: часть проб отброшена при разборе отметок, и '
    'номера разошлись.':
        'The borehole field is skipped: some samples were dropped while '
        'resolving elevations and the numbering no longer matches.',
    'Проверено %d проб из %d: у остальных соседей не нашлось. При исключении '
    'по скважине до соседней бывает дальше, чем автоматический радиус: '
    'задайте радиус вручную.':
        'Checked %d samples of %d: the rest found no neighbours. When a whole'
        ' hole is removed the neighbouring one may be farther than the '
        'automatic radius: set the radius by hand.',
    'Убирает пробы из выборки, считает значение в их точках по остальным и '
    'сравнивает с настоящим.\n\nЗАЧЕМ. Это единственный способ узнать, можно '
    'ли верить кубу. Сравнивать построенное не с чем: настоящего '
    'распределения содержаний никто не видел, а на глаз одинаково убедительно'
    ' выглядят и хорошая модель, и вымысел.\n\nЧТО ИСКЛЮЧАТЬ. Без поля '
    'скважины убирается одна проба. На разведочной сети это льстит модели: '
    'соседей она берёт из того же ствола в трёх метрах, и меряется связность '
    'по стволу, а не умение попасть между скважинами. На демонстрационных '
    'данных разница шестикратная: ошибка по пробам 0.17, по скважинам 1.10. '
    'Задав поле скважины, убираем ствол целиком, и проверка отвечает на '
    'нужный вопрос.\n\nЧИСЛА В ЖУРНАЛЕ. Средняя ошибка это обычный промах по '
    'модулю. Среднеквадратичная тяжелее наказывает редкие крупные промахи: '
    'если она заметно больше средней, модель иногда мажет сильно. Смещение '
    'показывает, уводит ли модель в одну сторону: положительное значит '
    'завышает. Разброс и односторонний увод выглядят одинаково, а лечатся по-'
    'разному, поэтому смещение вынесено отдельно. Доля ошибки от размаха '
    'данных ставит её в масштаб: единица это много на содержаниях до двух и '
    'мало на содержаниях до ста.\n\nЧТО ПОДБИРАТЬ. Меняя анизотропию, '
    'степень, число соседей и сектора и смотря на ошибку, эти параметры '
    'выбирают по числам. Правильного значения у них нет вообще, есть только '
    'лучшее на конкретных данных. Осторожно с проверкой по одной пробе: отбор'
    ' ближайших от анизотропии почти не зависит, пока ближайшая точка своя же'
    ' по стволу, и по такой проверке нельзя выбирать ничего, что касается '
    'плана.\n\nРАДИУС. При исключении по скважине до соседней бывает дальше, '
    'чем автоматический радиус, и тогда проверять оказывается нечего. '
    'Инструмент скажет об этом, и радиус придётся задать вручную.\n\nСЛОЙ. '
    'Поля: value настоящее значение, model посчитанное, resid разность, '
    'aresid её модуль. Раскрасив по aresid, видно, в каком углу площадки '
    'модель мажет: числа этого не говорят.':
        'Removes samples from the set, computes the value at their places '
        'from the rest and compares it with the real one.\n\nWHAT FOR. This '
        'is the only way to learn whether the cube can be trusted. There is '
        'nothing to compare the built model with: nobody has seen the real '
        'distribution of grades, and to the eye a good model and an invention'
        ' look equally convincing.\n\nWHAT TO REMOVE. Without a borehole '
        'field one sample is removed. On an exploration grid that flatters '
        'the model: it takes neighbours from the same hole three metres away,'
        ' and what is measured is continuity along the hole rather than the '
        'ability to hit between holes. On the demonstration data the '
        'difference is sixfold: the error by samples is 0.17, by holes 1.10. '
        'Given a borehole field, the whole hole is removed and the check '
        'answers the right question.\n\nTHE NUMBERS IN THE LOG. The mean '
        'error is the plain absolute miss. The root mean square one punishes '
        'rare large misses harder: if it is noticeably above the mean, the '
        'model sometimes misses badly. The bias shows whether the model leans'
        ' one way: positive means it overstates. Scatter and a one-sided lean'
        ' look the same and are cured differently, so the bias is kept apart.'
        ' The share of the error in the spread of the data puts it in scale: '
        'one is a lot on grades up to two and little on grades up to a '
        'hundred.\n\nWHAT TO PICK. By changing the anisotropy, the power, the'
        ' number of neighbours and the sectors and watching the error, these '
        'are chosen by numbers. There is no right value for them at all, only'
        ' the best one on the particular data. Beware the check by single '
        'samples: the choice of nearest points barely depends on the '
        'anisotropy while the nearest point is the layer\'s own down the '
        'hole, and such a check cannot decide anything about the plan.\n\nTHE'
        ' RADIUS. When a whole hole is removed, the neighbouring one is '
        'sometimes farther than the automatic radius, and then there is '
        'nothing to check. The tool says so, and the radius has to be set by '
        'hand.\n\nTHE LAYER. Fields: value the real value, model the computed'
        ' one, resid the difference, aresid its absolute value. Coloured by '
        'aresid, it shows in which corner of the site the model misses: the '
        'numbers do not say that.',
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
    'Выгрузить сцену': 'Export the scene',
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
    'Слой %s: у %d тел объём в поле volume больше их собственного '
    'габарита, то есть неверен. Такие слои выгружены сборкой до 0.74.1, '
    'где счёт объёма терял значащие цифры в настоящих координатах. '
    'Выгрузите оболочки заново.':
        'Layer %s: for %d bodies the volume in the volume field is larger '
        'than their own bounding box, so it is wrong. Such layers were '
        'exported by a build before 0.74.1, where the volume computation '
        'lost significant digits in real coordinates. Export the shells '
        'again.',
    'Слой %s: у %d объектов нет отметок низа или верха.':
        'The layer %s: %d features have no bottom or top elevation.',
    'Слой меша не загрузился: %s': 'Mesh layer failed to load: %s',
    'Слою %s нужен многоканальный грид: каналы это уровни куба.':
        'The layer %s needs a multiband grid: the bands are the levels of '
        'the cube.',
    'Слой %s - это грид пласта: каналы кровля и подошва, а не уровни куба. '
    'Разметки по Z у него нет. Кубовые режимы к нему неприменимы, для него '
    'режим «Тело пласта».':
        'The layer %s is a bed grid: its bands are a roof and a floor, not '
        'the levels of a cube, and it carries no Z marking. The cube modes '
        'do not apply to it, its mode is Bed body.',
    'У слоя %s нет разметки куба по Z (Z0 и DZ). Уровни взяты от нуля '
    'с шагом единица, и куб встанет не на своё место по высоте.':
        'The layer %s carries no Z marking of the cube (Z0 and DZ). The '
        'levels are taken from zero with a step of one, and the cube will '
        'stand at the wrong height.',
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
