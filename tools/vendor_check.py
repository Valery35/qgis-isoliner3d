# -*- coding: utf-8 -*-
"""
Сверяет вложенные библиотеки с эталоном на PyPI.

    python tools/vendor_check.py            # проверить
    python tools/vendor_check.py --freeze   # записать текущее как эталонное

Зачем. В libs лежат pyqtgraph и PyOpenGL, изменённые нами: часть папок
вырезана под сканер каталога, часть файлов заглушена, кое-где проставлены
метки nosec, а в pyqtgraph есть и содержательные правки совместимости.
При обновлении библиотеки всё это легко потерять молча: код продолжит
работать у разработчика и сломается у пользователя либо на сканере
каталога.

Инструмент качает эталон с PyPI и раскладывает различия на три кучи:
удалённые файлы (так и задумано), лишние файлы (быть не должно) и правленые
файлы. Правки сверяются со списком известных в tools/vendor.json: новая
правка или пропавшая известная это повод остановиться и разобраться.

Нужна сеть. Без неё инструмент сообщает об этом и не притворяется, что
проверка прошла.
"""

import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIBS = os.path.join(ROOT, "isoliner3d", "libs")
MANIFEST = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "vendor.json")

# Что сверяем: имя пакета на PyPI, версия, папка внутри libs.
PACKAGES = [
    ("pyqtgraph", "0.14.0", "pyqtgraph"),
    ("PyOpenGL", "3.1.10", "OpenGL"),
]


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _index(root):
    """Все .py файла дерева: путь относительно корня -> хеш."""
    out = {}
    for base, _dirs, files in os.walk(root):
        for name in files:
            if not name.endswith(".py"):
                continue
            full = os.path.join(base, name)
            out[os.path.relpath(full, root).replace("\\", "/")] = _sha(full)
    return out


def _pypi_url(name, version):
    """Ссылка на дистрибутив: сначала колесо, потом исходники."""
    api = "https://pypi.org/pypi/%s/%s/json" % (name, version)
    with urllib.request.urlopen(api, timeout=60) as fh:   # nosec
        data = json.load(fh)
    urls = data.get("urls", [])
    for kind in ("bdist_wheel", "sdist"):
        for item in urls:
            if item.get("packagetype") == kind:
                return item["url"], kind
    raise RuntimeError("нет дистрибутива для %s %s" % (name, version))


def _fetch(name, version, package_dir, work):
    """Скачать и распаковать эталон, вернуть путь к папке пакета."""
    url, kind = _pypi_url(name, version)
    blob = urllib.request.urlopen(url, timeout=180).read()   # nosec
    dest = os.path.join(work, name)
    os.makedirs(dest, exist_ok=True)
    if kind == "bdist_wheel":
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            zf.extractall(dest)     # nosec
        return os.path.join(dest, package_dir)
    import tarfile
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
        tf.extractall(dest)         # nosec
    for entry in os.listdir(dest):
        candidate = os.path.join(dest, entry, package_dir)
        if os.path.isdir(candidate):
            return candidate
    raise RuntimeError("не нашёл папку %s в архиве %s" % (package_dir, name))


def _strip_nosec(text):
    """Убрать метки nosec: они не меняют поведения, только гасят сканер."""
    out = []
    for line in text.split("\n"):
        cut = line.find("# nosec")
        if cut >= 0:
            line = line[:cut].rstrip()
        out.append(line)
    return out


def _classify(src_dir, our_dir, path):
    """Правка косметическая (только метки nosec) или содержательная.

    Сравниваем файлы, из которых метки вычищены: если после этого они
    совпадают, правка косметическая. Простой подсчёт строк с меткой
    в дифе не годится, потому что одна такая правка даёт две строки, плюс
    и минус, и минус метки не содержит.
    """
    import difflib
    with open(os.path.join(src_dir, path), encoding="utf-8",
              errors="replace") as fh:
        a = fh.read()
    with open(os.path.join(our_dir, path), encoding="utf-8",
              errors="replace") as fh:
        b = fh.read()
    diff = [ln for ln in difflib.unified_diff(a.split("\n"), b.split("\n"),
                                              lineterm="", n=0)
            if ln[:1] in "+-" and ln[:3] not in ("+++", "---")]
    same = _strip_nosec(a) == _strip_nosec(b)
    return ("nosec" if same else "patch"), len(diff)


def compare(work):
    """Сводка по всем пакетам."""
    report = {}
    for name, version, package_dir in PACKAGES:
        our_dir = os.path.join(LIBS, package_dir)
        if not os.path.isdir(our_dir):
            raise RuntimeError("нет папки %s" % our_dir)
        src_dir = _fetch(name, version, package_dir, work)
        src, ours = _index(src_dir), _index(our_dir)
        removed = sorted(set(src) - set(ours))
        extra = sorted(set(ours) - set(src))
        changed = {}
        for path in sorted(set(src) & set(ours)):
            if src[path] != ours[path]:
                kind, lines = _classify(src_dir, our_dir, path)
                changed[path] = {"kind": kind, "lines": lines}
        report[name] = {"version": version, "removed": len(removed),
                        "extra": extra, "changed": changed}
    return report


def load_manifest():
    if not os.path.isfile(MANIFEST):
        return {}
    with open(MANIFEST, encoding="utf-8") as fh:
        return json.load(fh)


def main():
    freeze = "--freeze" in sys.argv
    work = tempfile.mkdtemp(prefix="vendor_")
    try:
        try:
            report = compare(work)
        except Exception as err:
            print("Сверка не выполнена: %s" % err)
            print("Нужна сеть: pypi.org и files.pythonhosted.org.")
            return 2
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if freeze:
        with open(MANIFEST, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1,
                      sort_keys=True)
        print("Эталонное состояние записано в %s"
              % os.path.relpath(MANIFEST, ROOT))
        return 0

    known = load_manifest()
    problems = []
    for name, data in sorted(report.items()):
        was = known.get(name, {})
        print("%s %s: вырезано %d файлов, правлено %d"
              % (name, data["version"], data["removed"],
                 len(data["changed"])))
        if data["extra"]:
            problems.append("%s: лишние файлы, которых нет в эталоне: %s"
                            % (name, ", ".join(data["extra"][:5])))
        if was.get("version") and was["version"] != data["version"]:
            problems.append("%s: версия в манифесте %s, сверяли %s"
                            % (name, was["version"], data["version"]))
        old_changed = was.get("changed", {})
        for path, info in sorted(data["changed"].items()):
            mark = " " if path in old_changed else "!"
            print("   %s %-42s %s, строк %d"
                  % (mark, path, info["kind"], info["lines"]))
            if path not in old_changed:
                problems.append("%s: новая правка в %s" % (name, path))
        for path in sorted(set(old_changed) - set(data["changed"])):
            problems.append("%s: пропала известная правка в %s"
                            % (name, path))
    if not known:
        print("\nМанифест пуст. Запустите с --freeze, чтобы записать "
              "текущее состояние как эталонное.")
        return 0
    if problems:
        print("\nРасхождения с манифестом:")
        for line in problems:
            print("  -", line)
        return 1
    print("\nВсё сходится с манифестом.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
