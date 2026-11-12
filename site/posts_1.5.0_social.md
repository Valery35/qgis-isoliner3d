# Isoliner3D 1.5.0 - посты

Ссылки:

- выпуск https://github.com/Valery35/qgis-isoliner3d/releases/tag/1.5.0
- каталог https://plugins.qgis.org/plugins/isoliner3d/

## Русский (ВК, Facebook, сайт)

Isoliner3D 1.5.0 для QGIS

Обрезка сцены теперь режет тела и закрывает срез крышкой во всех
режимах. Контур, коридор вдоль линии, сторона слева или справа
от линии, полоса отметок. Вместо пустой изнанки видно сечение тела.

Длинные грани выработки при обрезке больше не пропадают целиком.
Стенка штрека режется ровно по границе, соседние грани сшиваются
без щели.

Новый формат выгрузки .i3dscene. В нём геометрия сцены, камера
и виды облёта в настоящих координатах. Точки проб и линии борозд
идут в пакет и в GLB так, как нарисованы в окне.

Восемь инструментов Processing переведены на общее описание без
QGIS. Результаты те же, каждый сверен с прежней версией.

Установка из каталога QGIS или из архива с GitHub.
https://github.com/Valery35/qgis-isoliner3d/releases/tag/1.5.0

#QGIS #геология #3D #ГИС

## English (LinkedIn, Mastodon)

Isoliner3D 1.5.0 for QGIS

Scene clipping now cuts bodies and closes the cut with a cap in every
mode. A contour, a corridor along a line, the side left or right of
a line, a band of elevations. The section of a body shows instead of
the inside of the shell.

Long faces of a mine working no longer vanish whole when clipped. The
wall of a drift is cut exactly along the boundary, and neighbouring
faces meet without a gap.

A new export format, .i3dscene, carries the scene geometry, the camera
and the flight views in true coordinates. Sample points and channel
lines go into the package and into GLB the way the window draws them.

Eight Processing tools moved to a shared description without QGIS.
The results are the same, each checked against the previous version.

https://github.com/Valery35/qgis-isoliner3d/releases/tag/1.5.0

#QGIS #geology #mining #3D #GIS #opensource

## X (до 280 знаков)

Isoliner3D 1.5.0 for QGIS. Clipping cuts bodies and caps the cut in
every mode, long faces of mine workings no longer vanish, new .i3dscene
export with points and lines. #QGIS #geology #3D
https://github.com/Valery35/qgis-isoliner3d/releases/tag/1.5.0

## Площадки группы «Иногда» (слово автора от 12 ноября)

Форум OSM - выпуск не касается данных OSM, поста нет.

### OSGeo Discourse, тема 155878

Isoliner3D 1.5.0 is out.

Scene clipping now cuts bodies and caps the cut in every mode. A contour,
a corridor along a line, the side left or right of a line and a band of
elevations all get the cap. Long faces of mine workings are cut along the boundary instead
of vanishing whole.

A new export format, .i3dscene, carries the geometry, the camera and the
flight views in true coordinates, so the scene opens in applications
without QGIS. Sample points and channel lines go into the package and into
GLB the way the window draws them.

Eight Processing tools moved to a shared description that does not depend
on QGIS. Each was checked against the previous version, the results match.

Release: https://github.com/Valery35/qgis-isoliner3d/releases/tag/1.5.0
Plugin: https://plugins.qgis.org/plugins/isoliner3d/

### linux.org.ru, Open Source

Заголовок: Isoliner3D 1.5.0 - 3D-просмотр геологии для QGIS

Ссылка: https://github.com/Valery35/qgis-isoliner3d/releases/tag/1.5.0
Текст ссылки: Выпуск на GitHub
Теги: qgis, gis, python, opengl, геология

Вышел Isoliner3D 1.5.0, свободный модуль QGIS для объёмного просмотра
геологических поверхностей, тел пластов, скважин и блочных моделей.
Рендер на pyqtgraph и PyOpenGL, от штатного 3D-вида QGIS модуль
не зависит. Лицензия GPL-2.0-or-later.

Что нового в выпуске.

- Обрезка сцены режет тела и закрывает срез крышкой во всех режимах
  (контур, коридор вдоль линии, сторона от линии, полоса отметок).
- Длинные грани выработок при обрезке режутся по границе, а не
  пропадают целиком.
- Новый формат выгрузки .i3dscene (GLB и описание сцены в JSON) для
  приложений без QGIS, в него идут и точки, и линии.
- Восемь инструментов Processing описаны отдельно от QGIS, расчёт
  на NumPy, результаты сверены с прежней версией.

Каталог модулей QGIS: https://plugins.qgis.org/plugins/isoliner3d/

### Reddit, r/QGIS и r/gis (публикует автор)

Заголовок: Isoliner3D 1.5.0 - clipping with caps and a scene package for apps without QGIS

Текст:

Isoliner3D is a free QGIS plugin for viewing geological surfaces, bed
bodies, boreholes and block models in 3D. It renders with bundled
pyqtgraph and PyOpenGL and does not depend on the built-in 3D map.

What is new in 1.5.0:

- **Clipping caps everywhere.** A contour, a corridor along a line, the
  side left or right of a line and a band of elevations all cut bodies
  and close the cut, so you see the section instead of the inside of
  the shell.
- **Long faces survive clipping.** A wall of a drift whose vertices are
  all outside the boundary is now cut along it instead of vanishing.
- **Scene package (.i3dscene).** GLB plus a JSON description with the
  camera and flight views in true coordinates. Points and lines go in
  as drawn.
- **Tools as objects.** Eight Processing tools now have a description
  and a computation that do not depend on QGIS. Results match the
  previous version.

Release: https://github.com/Valery35/qgis-isoliner3d/releases/tag/1.5.0
Plugin page: https://plugins.qgis.org/plugins/isoliner3d/
