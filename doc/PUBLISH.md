# Публикация выпусков Isoliner3D

Журнал публикаций модуля QGIS Isoliner3D. Заведён 12 ноября 2026 года,
до этого записей о модуле не вели нигде.

## Правила

Общие правила и группы площадок - в разделе «Правила» журнала
`C:\Dev\planetx-lite\doc\PUBLISH.md` и в навыке `publish-release`.
Здесь только то, что касается этого модуля.

- Площадки группы «Всегда»: выпуск GitHub, каталог QGIS, Dropbox,
  Telegram @qgis_isolines. Сайт и соцсети (ВК, Mastodon, X, LinkedIn,
  Facebook) - когда в выпуске есть что показать. Выпуск из одного
  исправления туда не идёт.
- Площадки группы «Иногда» (OSGeo Discourse, форум OSM, linux.org.ru,
  Reddit) - только по слову автора.
- Тег выпуска без буквы `v`, просто номер: `1.4.14`.
- Выпуск GitHub называется `Isoliner3D <номер>`, к нему прикрепляется
  рабочий `isoliner3d.zip`. Внизу заметок строка установки из ZIP.
- В каталог идёт выгрузочный `isoliner3d_upload.zip`, без
  `isoliner3d/tests`. После загрузки каталог проверяет архив сам
  и присылает итог автору письмом.
- Пост в Telegram приходит сам, ботом по выпуску GitHub. Помощник
  только проверяет его на `t.me/s/qgis_isolines`.
- В Dropbox `ИИ\Isoliner3D` лежат три архива последнего выпуска:
  рабочий, выгрузочный и дельта. Прежние переносятся
  в `arhiv\старые_сборки_<номер>`.

## Площадки

| Площадка | Учётная запись | Как публиковать |
|---|---|---|
| GitHub, выпуск | Valery35 | `releases/new?tag=<номер>`, архив во второй `input[type=file]`, проверка через `api.github.com/repos/Valery35/qgis-isoliner3d/releases/tags/<номер>` |
| Каталог QGIS | Valery35 | `plugins.qgis.org/plugins/isoliner3d/version/add/`, архив в «Plugin Package», первые шесть флажков подтверждения, Save. Готовность - страница `/plugins/isoliner3d/version/<номер>/` отвечает 200 |
| Telegram @qgis_isolines | бот | Пост по выпуску GitHub |
| Dropbox | - | `C:\Users\ValH\Dropbox\ИИ\Isoliner3D` |

## Журнал

### 1.5.1 - 13 ноября 2026 года

Кнопка **Открыть в Isoliner Scene**. Тексты постов -
`site/posts_1.5.1_social.md`. Посты в соцсетях ждут выпуска
Isoliner Scene 0.2.0: в 0.1.0 нет перечитывания пакета.

| Площадка | Запись |
|---|---|
| GitHub | https://github.com/Valery35/qgis-isoliner3d/releases/tag/1.5.1 |
| Каталог QGIS | архив прикреплён к форме, флажки согласия и Save ставит автор |
| Telegram | https://t.me/qgis_isolines/210 |
| Dropbox | `ИИ\Isoliner3D`, три архива, 1.5.0 в `arhiv\старые_сборки_1.5.0` |
| ВК, Mastodon, X, LinkedIn, Facebook | ждут Isoliner Scene 0.2.0 |
| OSGeo, linux.org.ru, форум OSM | не публикуются в этом выпуске |
| Сайт informpp.ru | страницу обновляет основная сессия |

### 1.5.0 - 12 ноября 2026 года

Обрезка с крышками во всех режимах, длинные грани, пакет сцены
.i3dscene с точками и линиями, восемь инструментов объектами.
Тексты постов - `site/posts_1.5.0_social.md`.

| Площадка | Запись |
|---|---|
| GitHub | https://github.com/Valery35/qgis-isoliner3d/releases/tag/1.5.0 |
| Каталог QGIS | архив прикреплён к форме, флажки согласия и Save ставит автор |
| Telegram | https://t.me/qgis_isolines/209 |
| Dropbox | `ИИ\Isoliner3D`, три архива, 1.4.14 в `arhiv\старые_сборки_1.4.14` |
| ВК | https://vk.ru/wall-241229428_67 (запись на стене, без статьи) |
| Mastodon | https://en.osm.town/@Vaery35/117605004632525490 |
| X | https://x.com/Valery35/status/2120954749331608026 |
| LinkedIn | https://www.linkedin.com/feed/update/urn:li:activity:7526721033442238465/ |
| Facebook | https://www.facebook.com/valery35/posts/pfbid02gFomceA8Zx4gE1rEqgJYHAsFnuaJEVBLp9kXBdtZ8vqRKnsgUZPpgd2G6WXNtG8Tl |
| linux.org.ru | https://www.linux.org.ru/news/opensource/18420037 (ждёт модератора) |
| OSGeo Discourse | не опубликовано, в Chrome нет входа на discourse.osgeo.org |
| Форум OSM | не публиковалось, в выпуске нет ничего про данные OSM |
| Reddit | текст в файле постов, публикует автор |
| Сайт informpp.ru | не публиковалось, у модуля нет страницы на сайте |

### 1.4.14 - 12 ноября 2026 года

Выпуск из одного исправления: импорт сцен из другого проекта QGIS
без сущностей XML (замечания B405 и B314 сканера каталога).

| Площадка | Запись |
|---|---|
| GitHub | https://github.com/Valery35/qgis-isoliner3d/releases/tag/1.4.14 |
| Каталог QGIS | https://plugins.qgis.org/plugins/isoliner3d/version/1.4.14/ (сохранена, идёт проверка каталога) |
| Telegram | https://t.me/qgis_isolines/207 |
| Dropbox | `ИИ\Isoliner3D`, три архива |
| Сайт и соцсети | не публиковались, выпуск из одного исправления |

### 1.4.13 - 11 ноября 2026 года

Видео из окна сцены, инструменты 2.23 и 2.24. Записи собраны задним
числом 12 ноября по самим площадкам.

| Площадка | Запись |
|---|---|
| GitHub | https://github.com/Valery35/qgis-isoliner3d/releases/tag/1.4.13 |
| Каталог QGIS | https://plugins.qgis.org/plugins/isoliner3d/version/1.4.13/ (Approved) |
| Telegram | пост «Isoliner3D 1.4.13» в @qgis_isolines |
| Dropbox | сборки в `arhiv\старые_сборки_1.4.13` |
| Сайт и соцсети | сведений нет |
