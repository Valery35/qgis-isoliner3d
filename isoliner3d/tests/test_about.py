# -*- coding: utf-8 -*-
"""Проверка окна «О плагине».

Qt здесь не поднимается: проверяется то, что можно проверить без него -
чтение метаданных, выбор руководства по языку и связность с меню.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d import about   # noqa: E402


def test_metadata_is_read():
    """Версия и история берутся из metadata.txt.

    Отдельный файл истории не нужен: канонический список уже там,
    и второй завёл бы расхождение между ними.
    """
    meta = about.read_metadata()
    assert meta.get("version"), meta.keys()
    assert meta.get("changelog"), "истории нет"
    assert meta.get("homepage", "").startswith("http")
    assert meta.get("tracker", "").startswith("http")


def test_manual_is_found():
    """Руководство находится, и это настоящий файл."""
    p = about.manual_path()
    assert p and os.path.isfile(p), p
    assert p.lower().endswith(".pdf")


def test_manual_falls_back_to_the_other_language():
    """Нет руководства нужного языка - берём второе.

    Руководство на чужом языке полезнее его отсутствия.
    """
    src = open(os.path.join(PKG, "about.py"), encoding="utf-8").read()
    i = src.index("def manual_path")
    body = src[i:src.index("\ndef ", i + 20)]
    assert "names.reverse()" in body
    assert body.count("Isoliner3D") >= 1
    # перебираем оба имени, а не одно
    assert "for name in names:" in body


def test_about_shows_the_three_buttons():
    """В окне те же три кнопки, что у соседнего плагина."""
    src = open(os.path.join(PKG, "about.py"), encoding="utf-8").read()
    i = src.index("def show_about")
    body = src[i:]
    for text in ('tr("История изменений")', 'tr("Руководство (PDF)")',
                 'tr("Журнал")'):
        assert text in body, text
    assert "www.informpp.ru" in body
    assert "Информ++" in body


def test_about_is_on_the_toolbar():
    """Пункт «О плагине» стоит и на панели, а не только в меню.

    В меню плагина его ищут, а на панели он под рукой - так же,
    как у соседнего Isoliner.
    """
    src = open(os.path.join(PKG, "plugin.py"), encoding="utf-8").read()
    i = src.index('tr("О плагине…")')
    body = src[i:i + 500]
    assert "toolbar=True" in body, body


def test_manual_images_are_all_used():
    """В папке руководства нет картинок, на которые никто не ссылается.

    Старые снимки вводят в заблуждение сильнее, чем их отсутствие:
    окно давно другое, а картинка показывает прежнее.
    """
    import re
    root = os.path.dirname(PKG)
    used = set()
    for name in ("manual.md", "manual_en.md"):
        text = open(os.path.join(root, "manual", name),
                    encoding="utf-8").read()
        used |= set(re.findall(r"images/([\w.\-]+)", text))
    have = set(os.listdir(os.path.join(root, "manual", "images")))
    extra = sorted(have - used)
    assert not extra, "не используются: %s" % ", ".join(extra)


def test_log_is_started_on_load():
    """Журнал заводится при загрузке плагина, а не сам собой.

    Путь подставляется снаружи. Пока этого никто не делает, всё, что
    модуль пишет, уходит в никуда, и кнопка «Журнал» отвечает,
    что его нет.
    """
    src = open(os.path.join(PKG, "plugin.py"), encoding="utf-8").read()
    i = src.index("def initGui")
    body = src[i:i + 900]
    assert "trace.setup()" in body, body
    # и заводится первым: дальнейшее должно в него попасть
    assert body.index("trace.setup()") < body.index("initProcessing()")


def test_log_setup_writes_a_file():
    """Заведение журнала и правда создаёт файл."""
    import tempfile
    from isoliner3d import trace
    folder = tempfile.mkdtemp()
    path = trace.setup(folder)
    assert path and os.path.isfile(path), path
    trace.step("проверка")
    text = open(path, encoding="utf-8").read()
    assert "проверка" in text
    # некуда писать - пустой путь, а не падение
    assert trace.setup("") == ""


def test_every_menu_item_has_its_own_icon():
    """У каждого пункта меню свой значок.

    Одинаковые значки в меню неразличимы, и человек жмёт наугад.
    Отличаться они должны формой, а не только цветом: в меню значки
    мелкие.
    """
    import re
    src = open(os.path.join(PKG, "plugin.py"), encoding="utf-8").read()
    used = re.findall(r"QAction\((\w+),", src)
    assert len(used) >= 3, used
    assert len(set(used)) == len(used), "значки повторяются: %s" % used
    for name in ("icon.svg", "icon_about.svg", "icon_help.svg"):
        assert os.path.isfile(os.path.join(PKG, name)), name


def test_menu_item_is_wired():
    """Пункт меню заведён и не роняет интерфейс при ошибке."""
    src = open(os.path.join(PKG, "plugin.py"), encoding="utf-8").read()
    assert 'tr("О плагине…")' in src
    assert "self._show_about" in src
    i = src.index("def _show_about")
    body = src[i:src.index("\n    def ", i + 20)]
    assert "about.show_about(" in body
    assert "except Exception" in body


def test_qt_is_imported_lazily():
    """Qt тянется внутри функций: модуль читается и без QGIS."""
    src = open(os.path.join(PKG, "about.py"), encoding="utf-8").read()
    head = src[:src.index("def read_metadata")]
    assert "qgis" not in head, head
    assert "PyQt" not in head


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all about tests passed")


if __name__ == "__main__":
    _run()
