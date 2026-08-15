# -*- coding: utf-8 -*-
"""
Собирает страницу Isoliner3D для сайта.

Страница самодостаточная: схемы встраиваются в неё как base64, поэтому файл
можно открыть как есть, положить на хостинг или вставить кодом на страницу
сайта. Внешних запросов нет, кроме шрифтов.

    python tools/build_site.py

Результат: site/isoliner3d_landing.html

Оформление держится того же семейства, что страницы Isoliner и Topoliner:
одна палитра и те же шрифты, чтобы продукты читались как один набор.
"""

import base64
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIGURES = os.path.join(ROOT, "doc", "figures")
OUT_DIR = os.path.join(ROOT, "site")
OUT = os.path.join(OUT_DIR, "isoliner3d_landing.html")


def figure(name, language):
    """Схема как data-URL, чтобы страница осталась самодостаточной."""
    path = os.path.join(FIGURES, "%s_%s.png" % (name, language))
    with open(path, "rb") as fh:
        data = base64.b64encode(fh.read()).decode()
    return "data:image/png;base64," + data


def figure_pair(name):
    """
    Обе версии схемы для переключателя языка.

    Подписи внутри схем нарисованы, а не выведены текстом, поэтому картинка
    меняется вместе с языком: иначе на английской странице остаются русские
    рисунки.
    """
    return (' data-fig-ru="%s" data-fig-en="%s" src="%s"'
            % (figure(name, "ru"), figure(name, "en"), figure(name, "ru")))


def read_version():
    path = os.path.join(ROOT, "isoliner3d", "metadata.txt")
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("version="):
                return line.split("=", 1)[1].strip()
    return ""


# Тексты страницы. Ключ, русский, английский.
# Хранятся в одном месте, чтобы версии не разъезжались: страница
# переключается на лету, без перезагрузки.
TEXTS = {
"title":      ("Isoliner3D - 3D-просмотр и блочная модель для QGIS · Информ++",
               "Isoliner3D - 3D viewer and block model for QGIS · Inform++"),
"desc":       ("Isoliner3D показывает геологические поверхности и тела "
               "пластов в объёме, накладывает на них карты текстурой "
               "и считает запасы по блочной модели. Плагин QGIS.",
               "Isoliner3D shows geological surfaces and bed bodies in three "
               "dimensions, drapes maps onto them as textures and computes "
               "reserves from a block model. A QGIS plugin."),
"brand.sub":  ("для QGIS", "for QGIS"),
"nav.idea":   ("Идея", "Idea"),
"nav.tools":  ("Инструменты", "Tools"),
"nav.cases":  ("Возможности", "Capabilities"),
"nav.docs":   ("Документация", "Documentation"),

"hero.eyebrow": ("Плагин QGIS · 3D и Processing",
                 "QGIS plugin · 3D and Processing"),
"hero.h1":    ("Модель пласта видна целиком, а не по одному горизонту",
               "The bed model is seen as a whole, not one horizon "
               "at a time"),
"hero.lead":  ("Кровля, подошва, скважины и разрез существуют по отдельности "
               "и сходятся только в голове у геолога. Isoliner3D собирает их "
               "в одну сцену: тела пластов, стволы скважин насквозь, чертёж "
               "разреза на своём месте в пространстве и карта, натянутая "
               "на рельеф.",
               "A roof, a bottom, boreholes and a section exist separately "
               "and come together only in the geologist's head. Isoliner3D "
               "assembles them into one scene: bed bodies, borehole stems "
               "running through them, the section drawing in its place "
               "in space and a map draped over the relief."),
"cta.install":("Установить в QGIS", "Install in QGIS"),
"cta.code":   ("Исходный код", "Source code"),
"cta.code2":  ("Исходный код и релизы", "Source code and releases"),

"idea.eyebrow":("Как устроен показ", "How the display works"),
"idea.h2":    ("Пласт это один файл, а не два грида",
               "A bed is one file rather than two grids"),
"idea.sub":   ("Многоканальный грид несёт кровлю первым каналом, подошву "
               "вторым, дальше параметры. Из такой пары строится замкнутая "
               "оболочка с боковой юбкой по границе данных: тело правильно "
               "выглядит с любой стороны и правильно режется плоскостью "
               "разреза. Тот же файл принимают калькулятор запасов "
               "и блочная модель.",
               "A multiband grid carries the roof in band 1, the bottom in "
               "band 2, then the parameters. Such a pair yields a watertight "
               "shell with a side skirt along the data boundary: the body "
               "looks right from any side and is cut correctly by the "
               "section plane. The same file is accepted by the reserve "
               "calculator and the block model."),
"idea.c1.h":  ("Своё окно, а не штатный 3D-вид",
               "A window of its own, not the built-in 3D view"),
"idea.c1.p":  ("Рендер идёт на pyqtgraph и PyOpenGL, они лежат внутри "
               "плагина. Ни Qt3D, ни внешних установок не требуется, "
               "и поведение одинаково на Qt5 и Qt6.",
               "Rendering runs on pyqtgraph and PyOpenGL bundled inside the "
               "plugin. Neither Qt3D nor any external installation is "
               "needed, and behaviour is the same on Qt5 and Qt6."),
"idea.c2.h":  ("Показ отделён от расчёта", "Display is separate from compute"),
"idea.c2.p":  ("Кригинг, изолинии, рельеф и разрезы остаются за Isoliner. "
               "Isoliner3D читает готовые гриды, считает по ним объём "
               "и запасы и показывает результат.",
               "Kriging, isolines, relief and sections stay with Isoliner. "
               "Isoliner3D reads ready grids, computes volume and reserves "
               "from them and shows the result."),
"idea.fig":   ("Кровля и подошва в одном растре дают замкнутое тело. Юбка "
               "строится по границе фактических данных, поэтому пропуски "
               "не достраиваются, а честно остаются краем.",
               "A roof and a bottom in one raster yield a watertight body. "
               "The skirt follows the boundary of the actual data, so gaps "
               "are not filled in but stay an edge."),

"tex.eyebrow":("Наложение карты", "Draping a map"),
"tex.h2":     ("Карта на рельефе остаётся картой, а не мозаикой",
               "A map on the relief stays a map rather than a mosaic"),
"tex.sub":    ("Обычная окраска живёт в вершинах меша, поэтому детальность "
               "картинки упирается в плотность сетки, и прореженный грид "
               "превращает ортофото в мозаику. Isoliner3D кладёт настоящую "
               "текстуру: разрешение задаётся отдельно и от сетки "
               "не зависит. Цвет домножается на затенение по нормали, "
               "поэтому под картой по-прежнему читается форма.",
               "Ordinary colouring lives in the mesh vertices, so the image "
               "detail is capped by the mesh density and a thinned grid "
               "turns an orthophoto into a mosaic. Isoliner3D lays down a "
               "real texture: the resolution is set separately and does not "
               "depend on the mesh. The colour is multiplied by shading from "
               "the normal, so the shape still reads under the map."),
"tex.fig":    ("Слева цвет задан в узлах сетки, справа та же поверхность "
               "с текстурой. Узлы одни и те же.",
               "On the left the colour is set in the mesh nodes, on the "
               "right the same surface carries a texture. The nodes are "
               "the same."),
"tex.c1.h":   ("Что можно натянуть", "What can be draped"),
"tex.c1.p":   ("Ортофото, тайловую подложку, геологическую карту со всей "
               "символикой и подписями, отмывку рельефа. Рендерит сам QGIS, "
               "поэтому перепроецирование берёт на себя он же.",
               "An orthophoto, a tiled basemap, a geological map with all "
               "its symbology and labels, a hillshade. QGIS does the "
               "rendering, so it also handles the reprojection."),
"tex.c2.h":   ("Чертёж разреза", "The section drawing"),
"tex.c2.p":   ("Чертежи Isoliner строятся в координатах «расстояние вдоль "
               "линии на отметку», а лента разреза занимает ту же область "
               "пространства. Поэтому чертёж встаёт на своё место без "
               "пересчёта, и несколько разрезов показываются сразу.",
               "Isoliner drawings are built in «distance along the line by "
               "elevation» coordinates, and the section ribbon occupies the "
               "same region of space. The drawing therefore lands where it "
               "belongs with no recalculation, and several sections are "
               "shown at once."),
"tex.fig2":   ("Линия на плане, чертёж в координатах разреза и лента "
               "в сцене это одно и то же место, показанное трижды.",
               "The line on the plan, the drawing in section coordinates "
               "and the ribbon in the scene are one and the same place, "
               "shown three times."),

"tools.eyebrow":("Семь инструментов", "Seven tools"),
"tools.h2":   ("Группа «Пласт и блочная модель» в панели Обработки",
               "The «Bed and block model» group in the Processing toolbox"),
"tools.sub":  ("Считают на NumPy и GDAL, кригинг им не нужен, поэтому "
               "работают и без основного плагина. Конвейер простой: собрать "
               "грид пласта, посчитать по нему запасы, развернуть "
               "в блочную модель, получить списание разностью двух моделей.",
               "They compute on NumPy and GDAL and need no kriging, so they "
               "work without the main plugin. The pipeline is simple: "
               "assemble a bed grid, compute reserves from it, unfold it "
               "into a block model, get the write-off as the difference of "
               "two models."),
"g1":         ("Пласт и блочная модель", "Bed and block model"),
"t101.h":     ("Собрать грид пласта", "Assemble a bed grid"),
"t101.p":     ("Кровля, подошва и параметры в один многоканальный растр. "
               "Имена каналов берутся из имён слоёв.",
               "A roof, a bottom and parameters into one multiband raster. "
               "The band names come from the layer names."),
"t102.h":     ("Калькулятор пласта", "Bed calculator"),
"t102.p":     ("Мощность, объём, тоннаж руды и металла, средневзвешенное "
               "содержание. Сводка по контуру и отчёт HTML.",
               "Thickness, volume, ore and metal tonnage, the mean grade. "
               "A summary over a contour and an HTML report."),
"t103.h":     ("Грид пласта в блочную модель", "Bed grid to a block model"),
"t103.p":     ("Точка-центроид на ячейку со всеми параметрами. Деление "
               "колонки по вертикали с сохранением суммы запаса.",
               "A centroid point per cell with every parameter. A vertical "
               "split of the column that preserves the reserve sum."),
"t104.h":     ("Поверхности в 3D (меши)", "Surfaces to 3D (meshes)"),
"t104.p":     ("Экспорт гридов в 2DM: профильный инструмент QGIS, "
               "mesh-калькулятор, сторонние программы.",
               "Export of grids to 2DM: the QGIS profile tool, the mesh "
               "calculator, third-party software."),
"t105.h":     ("Домены в канал пласта", "Domains to a bed band"),
"t105.p":     ("Полигоны участков растеризуются в добавочный канал грида "
               "и дальше работают как обычный параметр.",
               "Area polygons are rasterised into an extra grid band and "
               "then behave like any other parameter."),
"t106.h":     ("Разность запасов (списание)", "Reserve difference"),
"t106.p":     ("Разность двух блочных моделей по совпадающим ячейкам. "
               "Прямой путь оперативного списания.",
               "The difference of two block models over matching cells. "
               "The direct route to operational write-off."),
"t107.h":     ("Создать пример данных (демо)", "Create sample data (demo)"),
"t107.p":     ("Тела с высотой Z и проверочная карта для текстуры: можно "
               "посмотреть показ, не трогая рабочие слои.",
               "Bodies with a Z elevation and a test map for the texture: "
               "the display can be checked without touching working "
               "layers."),

"cases.eyebrow":("Что видно в сцене", "What the scene shows"),
"cases.h2":   ("Скважины, разрез и запасы в одном пространстве",
               "Boreholes, a section and reserves in one space"),
"cases.sub":  ("Скважины рисуются стволами, интервалы окрашены по "
               "стратиграфическому положению, над устьем встаёт мачта "
               "с подписью, а густой фонд прореживается, чтобы подписи "
               "оставались читаемыми. Клик по сцене печатает имя слоя, "
               "координаты, значения всех каналов и мощность пласта.",
               "Boreholes are drawn as stems, the intervals are coloured by "
               "stratigraphic position, a mast with a label rises above the "
               "collar, and a dense stock is thinned so that the labels stay "
               "readable. A click on the scene prints the layer name, the "
               "coordinates, all band values and the bed thickness."),
"cases.fig":  ("Конвейер группы. Грид пласта, собранный первым "
               "инструментом, читается 3D-окном как тело: посчитали "
               "и сразу посмотрели.",
               "The pipeline of the group. The bed grid assembled by the "
               "first tool is read by the 3D window as a body: computed and "
               "looked at right away."),
"fact1":      ("треугольников в сцене из шести поверхностей собираются "
               "за доли секунды. Крупные гриды прореживаются автоматически, "
               "форма поверхности при этом сохраняется.",
               "triangles in a scene of six surfaces are assembled in a "
               "fraction of a second. Large grids are thinned automatically "
               "while the shape of the surface is preserved."),
"fact2":      ("столько занимает повторная сборка сцены вместо 0.77 с: "
               "прочитанные гриды и отрисованные карты берутся из памяти, "
               "а не с диска.",
               "is what a repeated scene rebuild takes instead of 0.77 s: "
               "the grids that were read and the maps that were rendered "
               "come from memory rather than from disk."),
"fact3":      ("внешних зависимостей. pyqtgraph и PyOpenGL идут в комплекте, "
               "устанавливать и настраивать нечего.",
               "external dependencies. pyqtgraph and PyOpenGL are bundled, "
               "there is nothing to install or configure."),

"docs.eyebrow":("Документация", "Documentation"),
"docs.h2":    ("Руководство в комплекте, на двух языках",
               "The manual ships with the plugin, in two languages"),
"docs.sub":   ("Пункт <b>Справка</b> в меню модуля открывает PDF на языке "
               "интерфейса и работает без сети. Интерфейс двуязычный, язык "
               "берётся из локали QGIS. Инструменты работают в моделях "
               "и в пакетном режиме.",
               "The <b>Help</b> entry in the module menu opens the PDF in "
               "the interface language and works without a network. The "
               "interface is bilingual, the language comes from the QGIS "
               "locale. The tools work in models and in batch mode."),

"ftr.line1":  ("лицензия GNU GPL v2 или новее · QGIS 3.16 и новее",
               "GNU GPL v2 or later · QGIS 3.16 and newer"),
"ftr.line2":  ("Разработано ООО «Информ++»", "Developed by Inform++ LLC"),
"ftr.line3":  ("Плагин развивается на задачах реальных предприятий. Если "
               "вашему производству не хватает функции, напишите нам.",
               "The plugin grows on the tasks of real enterprises. If your "
               "operation is missing a feature, write to us."),
}


def dictionary():
    """Словарь для встраивания в страницу."""
    import json
    data = {"ru": {}, "en": {}}
    for key, (ru, en) in TEXTS.items():
        data["ru"][key] = ru
        data["en"][key] = en
    return json.dumps(data, ensure_ascii=False)


def tool_row(number, key):
    return ('<div class="tool"><div class="num">%s</div><div class="txt">'
            '<b data-i18n="%s.h"></b><span data-i18n="%s.p"></span>'
            '</div></div>' % (number, key, key))


PAGE = """<!-- ============================================================ -->
<!-- Isoliner3D - лендинг для www.informpp.ru                       -->
<!-- Самодостаточная двуязычная страница: схемы встроены в файл,    -->
<!-- переключатель языка работает без перезагрузки.                 -->
<!-- Собирается скриптом tools/build_site.py, править лучше его:    -->
<!-- тексты обоих языков лежат там в одном месте.                   -->
<!-- ============================================================ -->
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" data-i18n-attr="desc" content="">
<title data-i18n="title"></title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Bitter:wght@500;600;700\\
&family=Golos+Text:wght@400;500;600&display=swap');

:root{
  --paper:#F1F3EE; --paper-2:#E7EBE3; --ink:#16221F; --ink-soft:#4C5A55;
  --teal:#0E7C66; --teal-deep:#0A5446; --amber:#C2622C;
  --line:rgba(22,34,31,.14); --r:14px; --maxw:1080px;
  --display:'Bitter',Georgia,serif;
  --body:'Golos Text','Segoe UI',system-ui,sans-serif;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
section[id],[id]{scroll-margin-top:74px}
body{margin:0;background:var(--paper);color:var(--ink);
  font-family:var(--body);font-size:17px;line-height:1.6;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:var(--maxw);margin:0 auto;padding:0 24px}
a{color:inherit}
h1,h2,h3{font-family:var(--display);font-weight:700;line-height:1.1;margin:0;
  letter-spacing:-.01em}
p{margin:0}
.eyebrow{font-size:13px;font-weight:600;letter-spacing:.16em;
  text-transform:uppercase;color:var(--teal-deep);margin-bottom:18px;
  display:inline-flex;gap:10px;align-items:center}
.eyebrow::before{content:"";width:26px;height:2px;background:var(--amber);
  display:inline-block}
.hdr{position:sticky;top:0;z-index:20;background:rgba(241,243,238,.86);
  backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
.hdr .wrap{display:flex;align-items:center;justify-content:space-between;
  height:62px;gap:18px}
.brand{display:flex;align-items:baseline;gap:10px;
  font-family:var(--display);font-weight:700;text-decoration:none;
  font-size:20px}
.brand span{font-family:var(--body);font-weight:500;font-size:13px;
  color:var(--ink-soft)}
.right{display:flex;align-items:center;gap:22px}
.nav{display:flex;gap:22px;font-size:15px}
.nav a{text-decoration:none;color:var(--ink-soft)}
.nav a:hover{color:var(--teal-deep)}
@media(max-width:860px){.nav{display:none}}
.lang{display:flex;border:1px solid var(--line);border-radius:10px;
  overflow:hidden;font-size:13px;font-weight:600}
.lang button{border:0;background:transparent;padding:6px 11px;cursor:pointer;
  font:inherit;color:var(--ink-soft)}
.lang button.on{background:var(--teal);color:#fff}
.hero{padding:74px 0 48px}
.hero h1{font-size:clamp(34px,5vw,56px);max-width:18ch}
.hero .lead{margin-top:22px;font-size:20px;max-width:64ch;
  color:var(--ink-soft)}
.cta{margin-top:34px;display:flex;gap:14px;flex-wrap:wrap}
.btn{display:inline-block;padding:13px 22px;border-radius:var(--r);
  text-decoration:none;font-weight:600;font-size:16px}
.btn-main{background:var(--teal);color:#fff}
.btn-main:hover{background:var(--teal-deep)}
.btn-ghost{border:1px solid var(--line);color:var(--ink)}
.btn-ghost:hover{border-color:var(--teal)}
section{padding:56px 0;border-top:1px solid var(--line)}
section h2{font-size:clamp(26px,3.3vw,38px);max-width:24ch}
section .sub{margin-top:16px;max-width:70ch;color:var(--ink-soft)}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:28px;margin-top:34px}
@media(max-width:860px){.pair{grid-template-columns:1fr}}
.card{background:var(--paper-2);border:1px solid var(--line);
  border-radius:var(--r);padding:22px 24px}
.card h3{font-size:19px;margin-bottom:10px}
.card p{color:var(--ink-soft);font-size:16px}
figure{margin:30px 0 0}
figure img{width:100%;height:auto;display:block;border-radius:var(--r);
  border:1px solid var(--line);background:#fff}
figcaption{margin-top:10px;font-size:14px;color:var(--ink-soft)}
.tools{margin-top:34px;border:1px solid var(--line);border-radius:var(--r);
  overflow:hidden;background:#fff}
.group{background:var(--paper-2);padding:10px 20px;font-weight:600;
  font-size:14px;letter-spacing:.04em;border-bottom:1px solid var(--line)}
.tool{display:grid;grid-template-columns:88px 1fr;gap:10px;padding:14px 20px;
  border-bottom:1px solid var(--line)}
.tool:last-child{border-bottom:0}
.num{font-family:var(--display);font-weight:700;color:var(--teal-deep)}
.txt b{display:block;font-size:16px}
.txt span{color:var(--ink-soft);font-size:15px}
.facts{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;
  margin-top:40px}
@media(max-width:860px){.facts{grid-template-columns:1fr}}
.fact b{display:block;font-family:var(--display);font-size:30px;
  line-height:1.1}
.fact span{color:var(--ink-soft);font-size:15px}
.ftr{padding:40px 0 60px;border-top:1px solid var(--line);
  color:var(--ink-soft);font-size:15px}
.ftr a{color:var(--teal-deep)}
</style>

<header class="hdr">
  <div class="wrap">
    <a class="brand" href="#">Isoliner3D
      <span data-i18n="brand.sub"></span></a>
    <div class="right">
      <nav class="nav">
        <a href="#idea" data-i18n="nav.idea"></a>
        <a href="#texture" data-i18n="nav.cases"></a>
        <a href="#tools" data-i18n="nav.tools"></a>
        <a href="#docs" data-i18n="nav.docs"></a>
      </nav>
      <div class="lang">
        <button type="button" data-lang="ru">RU</button>
        <button type="button" data-lang="en">EN</button>
      </div>
    </div>
  </div>
</header>

<div class="wrap hero">
  <div class="eyebrow" data-i18n="hero.eyebrow"></div>
  <h1 data-i18n="hero.h1"></h1>
  <p class="lead" data-i18n="hero.lead"></p>
  <div class="cta">
    <a class="btn btn-main" data-i18n="cta.install"
       href="https://plugins.qgis.org/plugins/isoliner3d/"></a>
    <a class="btn btn-ghost" data-i18n="cta.code"
       href="https://github.com/Valery35/qgis-isoliner3d"></a>
  </div>
</div>

<section id="idea">
  <div class="wrap">
    <div class="eyebrow" data-i18n="idea.eyebrow"></div>
    <h2 data-i18n="idea.h2"></h2>
    <p class="sub" data-i18n="idea.sub"></p>
    <div class="pair">
      <div class="card"><h3 data-i18n="idea.c1.h"></h3>
        <p data-i18n="idea.c1.p"></p></div>
      <div class="card"><h3 data-i18n="idea.c2.h"></h3>
        <p data-i18n="idea.c2.p"></p></div>
    </div>
    <figure>
      <img alt=""__PAIR_bed_body__>
      <figcaption data-i18n="idea.fig"></figcaption>
    </figure>
  </div>
</section>

<section id="texture">
  <div class="wrap">
    <div class="eyebrow" data-i18n="tex.eyebrow"></div>
    <h2 data-i18n="tex.h2"></h2>
    <p class="sub" data-i18n="tex.sub"></p>
    <figure><img alt=""__PAIR_texture__>
      <figcaption data-i18n="tex.fig"></figcaption></figure>
    <div class="pair">
      <div class="card"><h3 data-i18n="tex.c1.h"></h3>
        <p data-i18n="tex.c1.p"></p></div>
      <div class="card"><h3 data-i18n="tex.c2.h"></h3>
        <p data-i18n="tex.c2.p"></p></div>
    </div>
    <figure><img alt=""__PAIR_section__>
      <figcaption data-i18n="tex.fig2"></figcaption></figure>
  </div>
</section>

<section id="tools">
  <div class="wrap">
    <div class="eyebrow" data-i18n="tools.eyebrow"></div>
    <h2 data-i18n="tools.h2"></h2>
    <p class="sub" data-i18n="tools.sub"></p>
    <div class="tools">
      <div class="group" data-i18n="g1"></div>
      __ROWS1__
    </div>
  </div>
</section>

<section id="cases">
  <div class="wrap">
    <div class="eyebrow" data-i18n="cases.eyebrow"></div>
    <h2 data-i18n="cases.h2"></h2>
    <p class="sub" data-i18n="cases.sub"></p>
    <figure><img alt=""__PAIR_pipeline__>
      <figcaption data-i18n="cases.fig"></figcaption></figure>
    <div class="facts">
      <div class="fact"><b>311&thinsp;912</b><span data-i18n="fact1"></span>
        </div>
      <div class="fact"><b>0.02 &sect;</b><span data-i18n="fact2"></span></div>
      <div class="fact"><b>0</b><span data-i18n="fact3"></span></div>
    </div>
  </div>
</section>

<section id="docs">
  <div class="wrap">
    <div class="eyebrow" data-i18n="docs.eyebrow"></div>
    <h2 data-i18n="docs.h2"></h2>
    <p class="sub" data-i18n="docs.sub"></p>
    <div class="cta">
      <a class="btn btn-main" data-i18n="cta.install"
         href="https://plugins.qgis.org/plugins/isoliner3d/"></a>
      <a class="btn btn-ghost" data-i18n="cta.code2"
         href="https://github.com/Valery35/qgis-isoliner3d"></a>
    </div>
  </div>
</section>

<footer class="ftr">
  <div class="wrap">
    Isoliner3D __VERSION__ &middot; <span data-i18n="ftr.line1"></span><br>
    <span data-i18n="ftr.line2"></span>,
    <a href="https://www.informpp.ru/">www.informpp.ru</a><br>
    <span data-i18n="ftr.line3"></span>
  </div>
</footer>

<script>
var TEXTS = __DICT__;

function apply(lang){
  var d = TEXTS[lang] || TEXTS.ru;
  document.documentElement.lang = lang;
  document.querySelectorAll('[data-i18n]').forEach(function(el){
    var value = d[el.getAttribute('data-i18n')];
    if (value !== undefined) el.innerHTML = value;
  });
  document.querySelectorAll('[data-i18n-attr]').forEach(function(el){
    var value = d[el.getAttribute('data-i18n-attr')];
    if (value !== undefined) el.setAttribute('content', value);
  });
  // Подписи внутри схем нарисованы, поэтому картинки меняются с языком.
  document.querySelectorAll('img[data-fig-' + lang + ']').forEach(
    function(img){
      img.src = img.getAttribute('data-fig-' + lang);
    });
  document.querySelectorAll('.lang button').forEach(function(b){
    b.classList.toggle('on', b.getAttribute('data-lang') === lang);
  });
  try { localStorage.setItem('isoliner3d-lang', lang); } catch (e) {}
}

document.querySelectorAll('.lang button').forEach(function(b){
  b.addEventListener('click', function(){
    apply(b.getAttribute('data-lang'));
  });
});

// По умолчанию русский: страница живёт на русском сайте.
// Английский включается кнопкой, выбор запоминается.
var saved = null;
try { saved = localStorage.getItem('isoliner3d-lang'); } catch (e) {}
apply(saved || 'ru');
</script>
"""


def main():
    if not os.path.isdir(FIGURES):
        print("Нет doc/figures, сначала запустите tools/make_figures.py")
        return 1

    page = PAGE
    for name in ("bed_body", "texture", "section", "pipeline"):
        page = page.replace("__PAIR_%s__" % name, figure_pair(name))
    rows1 = "".join(tool_row(n, k) for n, k in (
        ("1.01", "t101"), ("1.02", "t102"), ("1.03", "t103"),
        ("1.04", "t104"), ("1.05", "t105"), ("1.06", "t106"),
        ("1.07", "t107")))
    page = page.replace("__ROWS1__", rows1)
    page = page.replace("__DICT__", dictionary())
    page = page.replace("__VERSION__", read_version())

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(page)
    print("%-32s %7.1f КБ" % (os.path.relpath(OUT, ROOT),
                              os.path.getsize(OUT) / 1024.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
