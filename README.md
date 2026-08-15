# Isoliner3D

Автономный 3D-просмотр геологических поверхностей и тел для QGIS плюс группа инструментов Processing «Пласт и блочная модель»: поверхности из растров, водонепроницаемые тела пластов, скважины, плоскости разреза, полиэдры, подсчёт запасов и блочная модель. Не зависит от штатного 3D-вида QGIS, рендер идёт на pyqtgraph и PyOpenGL, которые идут в комплекте. Плагин-спутник набора кригинга [Isoliner](https://github.com/Valery35/qgis-isoliner).

*Standalone 3D viewer for geological surfaces and bodies in QGIS, plus a "Bed and block model" Processing group: raster surfaces, watertight bed bodies, boreholes, section planes, polyhedra, reserve calculation and a block model. Independent of the built-in QGIS 3D view, it renders on the bundled pyqtgraph and PyOpenGL. A companion to the Isoliner kriging toolset.*

<!-- ![Isoliner3D](docs/screenshot.png) -->

## Возможности / Features

- Поверхности из растров проекта, каждый горизонт своим цветом, с вертикальным преувеличением и разносом по Z.
- Водонепроницаемые тела пластов из многоканальных гридов (канал 1 кровля, канал 2 подошва) с боковой юбкой по границе данных.
- Скважины цветными стволами с мачтами над устьем и авто-прореживаемыми подписями.
- Плоскость разреза с ярким следом сечения по поверхностям.
- Полиэдры / TIN / MultiPolygon Z как объёмные тела.
- Опрос кликом: имя слоя, координаты, значения всех каналов, мощность.
- Окраска палитрой, своим цветом, собственным каналом или внешним растром, снимок PNG для отчётов.
- Наложение карты текстурой с затенением: ортофото, подложка, геологическая карта со своей символикой.
- Чертёж разреза текстурой на ленте разреза, несколько разрезов сразу.
- pyqtgraph и PyOpenGL в комплекте, устанавливать ничего не нужно.

### Группа Processing «Пласт и блочная модель» / Bed and block model tools

| | |
|---|---|
| **1.01** Собрать грид пласта | кровля и подошва в один многоканальный грид |
| **1.02** Калькулятор пласта | мощность, объём, тоннаж руды и металла, HTML-отчёт |
| **1.03** Грид пласта в блочную модель | центроиды ячеек с запасами, деление по вертикали |
| **1.04** Поверхности в 3D (меши) | экспорт гридов в 2DM (MDAL) |
| **1.05** Домены в канал пласта | код домена отдельным каналом грида |
| **1.06** Разность запасов | списание как разность двух блочных моделей |
| **1.07** Создать пример данных (демо) | тела с Z и проверочная карта для текстуры |

## Установка / Installation

**Из ZIP:** Модули → Управление и установка модулей → Установить из ZIP → выберите `isoliner3d.zip`.

*From ZIP: Plugins → Manage and Install Plugins → Install from ZIP → select `isoliner3d.zip`.*

Требования / Requirements: **QGIS 3.16+** (Qt5/Qt6). Внешних зависимостей нет / no external dependencies.

## Использование / Usage

Кнопка на панели **Isoliner3D** или **Модули → Isoliner3D → 3D-просмотр поверхностей…**

*Toolbar button **Isoliner3D**, or **Plugins → Isoliner3D → 3D surface viewer…***

Руководство открывается пунктом **Модули → Isoliner3D → Справка (руководство PDF)…** Исходник лежит в [`manual/`](manual/), собранные PDF - в `isoliner3d/doc/`.

*The manual opens from **Plugins → Isoliner3D → Help (PDF manual)…** The source lives in [`manual/`](manual/), the built PDFs in `isoliner3d/doc/`.*

## Разработка / Development

Headless-тесты (QGIS не требуется) / headless tests (no QGIS required):

```bash
python isoliner3d/tests/test_mesh3d.py
python isoliner3d/tests/test_polyhedral.py
python isoliner3d/tests/test_viewer3d.py
python isoliner3d/tests/test_viewer3d_static.py
python isoliner3d/tests/test_i18n.py
python isoliner3d/tests/test_algorithms_static.py
python isoliner3d/tests/test_prof.py
python isoliner3d/tests/test_cache.py
python isoliner3d/tests/test_texmesh.py
```

Сборка руководства / building the manual: `manual/build_pdf.sh` (pandoc, xelatex, ghostscript).

Ядро (`mesh3d.py`, `polyhedral.py`, `demo_map.py`) это чистый NumPy без импорта QGIS. `viewer3d.py` и `texmesh.py` импортируют Qt, QGIS и pyqtgraph лениво, поэтому модули грузятся headless. `algorithms.py` тянет QGIS на верхнем уровне и проверяется статически, разбором AST.

Правила работы над модулем в [AGENTS.md](AGENTS.md).

## Лицензия / License

GPL-2.0-or-later. См. [LICENSE](isoliner3d/LICENSE).

© 2026 ООО «Информ++» ([informpp.ru](https://www.informpp.ru)).
