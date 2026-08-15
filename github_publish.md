# Isoliner3D на GitHub: с нуля

В GitHub Desktop репозитория `qgis-isoliner3d` нет. Сначала выясните,
существует ли он на GitHub: откройте `github.com/Valery35/qgis-isoliner3d`.

Дальше два пути. Выберите свой и делайте только его.

---

## Путь А. Страница открывается, репозиторий на GitHub есть

Значит, он просто не подключён к Desktop.

1. GitHub Desktop: **File - Clone repository**, вкладка **GitHub.com**.
2. Выберите `Valery35/qgis-isoliner3d`, укажите локальный путь, Clone.
3. Переходите к разделу **Наполнение** ниже.

---

## Путь Б. Ошибка 404, репозитория нет

Создаём его из локальной папки.

1. Сделайте пустую папку рядом с остальными репозиториями, например
   `qgis-isoliner3d`. Точное имя важно, оно попадёт в адрес.
2. GitHub Desktop: **File - New repository**.
   - Name: `qgis-isoliner3d`
   - Local path: папка, в которой лежит `qgis-isoliner3d`, то есть
     на уровень выше самой папки
   - Git ignore: None, свой файл придёт из архива
   - License: None, файл LICENSE уже лежит внутри модуля
   - Create repository
3. Переходите к разделу **Наполнение**. Публикация будет после него.

---

## Наполнение

1. Распакуйте `isoliner3d_repo_delta.zip` в корень папки репозитория.
   Появятся `README.md`, `AGENTS.md`, `.gitignore` и папка `manual`.
2. Распакуйте `isoliner3d.zip` туда же. Появится папка `isoliner3d`
   со всем модулем, включая `tests` и `doc`.

Должно получиться так:

    qgis-isoliner3d/
      .gitignore
      AGENTS.md
      README.md
      isoliner3d/        (модуль: код, libs, tests, doc)
      manual/            (исходник руководства и build_pdf.sh)

3. В GitHub Desktop проверьте список файлов. Ожидается около двух с
   половиной тысяч файлов, основная масса это `isoliner3d/libs`. Так и
   должно быть, библиотеки идут в комплекте.
4. В поле Summary напишите `Isoliner3D 0.5.1`, нажмите
   **Commit to main**.

### Публикация (только для пути Б)

5. Кнопка **Publish repository** вверху.
   - Name: `qgis-isoliner3d`
   - Description: короткая строка, например
     `3D-просмотр геологических поверхностей и блочная модель для QGIS`
   - **Снимите галку Keep this code private.** Каталог QGIS ссылается
     на репозиторий, он должен быть открыт.
   - Publish repository.

### Отправка (для пути А)

5. Кнопка **Push origin**.

---

## Релиз

1. **Repository - View on GitHub**, откроется страница в браузере.
2. Справа **Releases**, затем **Create a new release**.
3. **Choose a tag**: впишите `v0.5.1` и выберите
   **Create new tag: v0.5.1 on publish**.
4. Release title: `Isoliner3D 0.5.1`.
5. Description: возьмите блок `changelog` из `isoliner3d/metadata.txt`,
   он уже написан списком.
6. **Attach binaries**: перетащите `isoliner3d.zip`.
7. **Publish release**.

---

## Проверка после публикации

- На странице репозитория виден README с двумя языками.
- В корне лежат `isoliner3d`, `manual`, `AGENTS.md`.
- Внутри `isoliner3d/doc` два PDF.
- В релизе `v0.5.1` прикреплён `isoliner3d.zip`.
- Ссылки из `metadata.txt` открываются:
  `homepage` и `repository` ведут на страницу репозитория,
  `tracker` на вкладку Issues.

После этого можно грузить `isoliner3d_upload.zip` в каталог QGIS,
шаг 3 из предыдущей инструкции.
