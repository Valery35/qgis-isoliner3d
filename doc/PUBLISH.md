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
