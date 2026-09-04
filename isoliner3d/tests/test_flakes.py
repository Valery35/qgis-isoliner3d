# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Неопределённые имена и мёртвые импорты во всех модулях.

Зачем отдельный тест. `algorithms.py` импортирует QGIS на верхнем уровне,
поэтому headless не выполняется, а компиляция ловит только синтаксис:
обращение к несуществующему имени она пропускает и падает лишь во время
работы, у пользователя. Именно так при переносе группы инструментов
из Isoliner потерялись `QVariant`, `GRP_MESH3D`, `_KEEP_ALIVE`
и `_Mesh3DPostProcessor`: код компилировался, а инструмент 1.04 упал бы
при первом запуске.

pyflakes разбирает файл статически и такие места находит. Если его нет
в окружении, тест сообщает об этом и не падает: это проверка разработчика,
а не пользователя.

Запуск:  python isoliner3d/tests/test_flakes.py
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)

# libs заморожены и проверяются отдельно, tests содержат намеренные заглушки
MODULES = ("algorithms.py", "viewer3d.py", "texmesh.py", "plugin.py",
           "provider.py", "i18n.py", "mesh3d.py", "polyhedral.py",
           "demo_map.py", "trace.py", "gltf.py", "iso3d.py", "interp3d.py",
           "demo3d.py", "voxel.py",
           "variogram.py", "kriging.py",
           "slice3d.py", "volume.py", "flatten.py",
           "cleanup.py", "axes.py", "mba.py",
           "glyphs.py", "cadmesh.py", "about.py", "section3d.py",
           "lights.py", "demo_drift.py", "boolean3d.py",
           "viewer_core.py", "viewer_dialog.py",
           "__init__.py")

# коды, которые считаем ошибкой сборки
FATAL = ("undefined name", "unable to detect undefined names",
         "imported but unused", "redefinition of unused",
         "local variable", "f-string is missing placeholders")


def _pyflakes_available():
    try:
        import importlib
        importlib.import_module("pyflakes.api")
        return True
    except Exception:
        return False


def _check(path):
    """Список замечаний pyflakes по файлу."""
    import io as _io
    from pyflakes.api import check
    from pyflakes.reporter import Reporter
    out, err = _io.StringIO(), _io.StringIO()
    with open(path, encoding="utf-8") as fh:
        code = fh.read()
    check(code, os.path.basename(path), Reporter(out, err))
    lines = [ln for ln in out.getvalue().split("\n") if ln.strip()]
    lines += [ln for ln in err.getvalue().split("\n") if ln.strip()]
    # Строку с `noqa` пропускаем: так помечен переэкспорт имён,
    # вынесенных в viewer_core. Снаружи модуль должен остаться прежним,
    # и неиспользованными эти имена только выглядят.
    src = code.split("\n")
    keep = []
    for ln in lines:
        parts = ln.split(":")
        try:
            n = int(parts[1])
        except (IndexError, ValueError):
            keep.append(ln)
            continue
        # у многострочного импорта noqa стоит на первой строке
        window = "\n".join(src[n - 1:n + 60])
        if "noqa" not in window.split("\n")[0] and "noqa" not in window[:200]:
            keep.append(ln)
    return keep


def test_no_undefined_names():
    if not _pyflakes_available():
        print("  pyflakes не установлен, проверка пропущена")
        return
    bad = []
    for name in MODULES:
        path = os.path.join(PKG, name)
        if not os.path.isfile(path):
            continue
        for line in _check(path):
            if any(word in line for word in FATAL):
                bad.append(line)
    assert not bad, "pyflakes нашёл %d замечаний:\n  %s" % (
        len(bad), "\n  ".join(bad))


def test_every_module_is_listed():
    """Новый модуль обязан попасть в проверку, а не остаться в стороне."""
    on_disk = {f for f in os.listdir(PKG) if f.endswith(".py")}
    missing = sorted(on_disk - set(MODULES))
    assert not missing, (
        "модули без проверки pyflakes: %s. Добавьте их в MODULES."
        % ", ".join(missing))


# конструкции, на которых сканер каталога plugins.qgis.org отклоняет
# загрузку: B110 (except/pass) и B112 (except/continue)
BLOCKERS = (("continue", "B112"), ("pass", "B110"))


def test_no_scanner_blockers():
    """В своём коде нет except/pass и except/continue без метки nosec.

    Сканер каталога на них отклоняет загрузку, а узнаётся это только
    при отправке. Дважды уже ловили руками, поэтому проверка здесь.
    Метка `# nosec` сканером уважается и допускается.
    """
    import ast
    bad = []
    for name in MODULES:
        path = os.path.join(PKG, name)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        lines = src.split("\n")
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.ExceptHandler):
                continue
            body = node.body
            if len(body) != 1:
                continue
            for kind, code in BLOCKERS:
                hit = (isinstance(body[0], ast.Continue)
                       if kind == "continue"
                       else isinstance(body[0], ast.Pass))
                if not hit:
                    continue
                line = lines[node.lineno - 1]
                tail = lines[body[0].lineno - 1]
                if "nosec" in line or "nosec" in tail:
                    continue
                bad.append("%s:%d %s" % (name, node.lineno, code))
    assert not bad, ("сканер каталога отклонит загрузку:\n  %s"
                     % "\n  ".join(bad))


def test_no_numpy_one_removals():
    """Нет вызовов, снятых в NumPy 2.

    У массивов убрали метод ptp и ещё несколько. На старой NumPy
    такой код работает и молчит, а у человека с новой падает
    посреди расчёта - у нас так и вышло на первом же прогоне 2.09.
    """
    import re
    gone_methods = ("ptp", "itemset", "newbyteorder")
    gone_names = ("np.float_", "np.int0", "np.alltrue", "np.sometrue",
                  "np.product", "np.cumproduct", "np.NaN", "np.Inf")
    bad = []
    for root, _dirs, files in os.walk(PKG):
        if "libs" in root:
            continue
        for name in files:
            if not name.endswith(".py"):
                continue
            if name == os.path.basename(__file__):
                continue      # в самой проверке эти имена перечислены
            path = os.path.join(root, name)
            for num, line in enumerate(open(path, encoding="utf-8"), 1):
                code = line.split("#")[0]
                for meth in gone_methods:
                    for m in re.finditer(
                            r"(\w+)\s*(\[[^\]]*\])?\s*\.%s\s*\("
                            % meth, code):
                        if m.group(1) not in ("np", "numpy"):
                            bad.append("%s:%d %s" % (name, num, meth))
                for nm in gone_names:
                    if nm in code:
                        bad.append("%s:%d %s" % (name, num, nm))
    assert not bad, "снято в NumPy 2: %s" % "; ".join(bad[:6])


def test_trace_is_wired_end_to_end():
    """Журнал заведён, пишет и открывается: путь, запись, кнопка.

    Половина этой цепочки однажды была снята как «код без вызовов»:
    вызова не было потому, что цепочку не довели, а не потому, что она
    лишняя. Проверка держит её целиком.
    """
    import importlib.util
    root = os.path.dirname(PKG)
    for name, must in (
            ("trace.py", ("def setup", "def write", "def step")),
            ("plugin.py", ("trace.setup()",)),
            ("about.py", ("trace.path()", "def open_log"))):
        src = open(os.path.join(PKG, name), encoding="utf-8").read()
        for token in must:
            assert token in src, "%s: нет %s" % (name, token)
    assert os.path.isdir(root)


if __name__ == "__main__":
    ok = 0
    for nm, fn in sorted(globals().items()):
        if nm.startswith("test_") and callable(fn):
            fn()
            print("OK", nm)
            ok += 1
    print("all flakes tests passed (%d)" % ok)
