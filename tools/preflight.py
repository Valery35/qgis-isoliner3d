#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Проверка metadata.txt перед отправкой в каталог QGIS.

Перенесена из PlanetX (tools/preflight.py): url_problems, url_answers
и tag_problems взяты оттуда, метки выпусков здесь без буквы v (1.5.7),
старые вида v1.2.3 тоже понимаются. Код модуля (импорты, pyflakes,
сканер каталога) здесь не проверяется: его стерегут тесты.

    python tools/preflight.py          без сети
    python tools/preflight.py --net    ещё адреса и метки выпусков

Без сети: подстановка «%» в полях, обязательные поля, адреса homepage,
repository и tracker (процент-кодировка, https, www у informpp.ru),
первая запись поля changelog с номером версии, номер первого раздела
CHANGELOG.md и номера версии в README. С --net адреса открываются,
метки берутся с GitHub, выданный номер и номер ниже последнего
выпуска - ошибка. Номера сравниваются числами: 1.10 выше 1.9.

Код возврата 1 означает ошибки.
"""

import configparser
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PLUGIN = "isoliner3d"

REQUIRED = ("name", "qgisMinimumVersion", "qgisMaximumVersion",
            "description", "version", "author", "email", "about",
            "repository", "tracker", "icon")
URL_FIELDS = ("homepage", "repository", "tracker")
VERSION = re.compile(r"\b(\d+\.\d+\.\d+)\b")
README = ("README.md", "README.ru.md", "README.en.md")
TAG = re.compile(r"v?(\d+\.\d+\.\d+)")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def url_problems(general):
    """Адреса metadata.txt без сети. Каталог не принял выпуск Routeliner
    с адресом страницы в процент-кодировке (ноябрь 2026 года), адрес
    кириллицей он берёт. Сайт без www не открывается."""
    out = []
    for field in URL_FIELDS:
        url = general.get(field, "").strip()
        if not url:
            continue
        if re.search(r"%[0-9A-Fa-f]{2}", url):
            out.append("metadata.txt: %s в процент-кодировке, каталог её "
                       "не принимает - адрес пишется буквами" % field)
        if not url.startswith("https://"):
            out.append("metadata.txt: %s не https - %s" % (field, url))
        if re.match(r"https?://informpp\.ru", url):
            out.append("metadata.txt: %s без www, сайт так не открывается"
                       % field)
    return out


def url_answers(general):
    """Ответ сервера по адресам metadata.txt - только с ключом --net."""
    import urllib.error
    import urllib.parse
    import urllib.request
    out = []
    for field in URL_FIELDS:
        url = general.get(field, "").strip()
        if not url:
            continue
        parts = urllib.parse.urlsplit(url)
        wire = urllib.parse.urlunsplit(parts._replace(
            path=urllib.parse.quote(parts.path, safe="/")))
        request = urllib.request.Request(
            wire, headers={"User-Agent": "Isoliner3D release check"})
        try:
            with urllib.request.urlopen(request, timeout=20) as reply:
                status = reply.status
        except urllib.error.HTTPError as error:
            status = error.code
        except (urllib.error.URLError, OSError) as error:
            out.append("metadata.txt: %s не открылся - %s" % (field, error))
            continue
        if status >= 400:
            out.append("metadata.txt: %s ответил %d" % (field, status))
    return out


def number(text):
    return tuple(int(part) for part in text.split("."))


def tag_problems(version):
    """Номер версии против меток выпусков - только с ключом --net,
    метки сначала берутся с GitHub. Выданный номер закрыт: метка этого
    номера на другом коммите значит, что номер не подняли."""
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    from gittool import GitError, git
    out = []
    try:
        try:
            git("fetch", "--tags", "--quiet", "origin")
        except GitError as error:
            out.append(("warn", "метки с GitHub не получены - %s"
                        % str(error).splitlines()[-1]))
        tags = [t.strip() for t in git("tag", "-l").splitlines()]
        valid = {}
        for t in tags:
            m = TAG.fullmatch(t)
            if m:
                valid[t] = m.group(1)
        head = git("rev-parse", "HEAD").strip()
        for t, num in valid.items():
            if num != version:
                continue
            at = git("rev-list", "-n", "1", t).strip()
            if at != head:
                out.append(("error", "номер %s уже выпущен меткой %s на "
                            "другом коммите - номер не поднят"
                            % (version, t)))
        if valid:
            last = max(valid, key=lambda t: number(valid[t]))
            if number(version) < number(valid[last]):
                out.append(("error", "номер %s меньше последнего выпуска %s"
                            % (version, last)))
    except GitError as error:
        out.append(("error", "метки выпусков не прочитаны - %s" % error))
    return out


def changelog_problems(general, version):
    """Первая запись поля changelog начинается с номера версии."""
    log = general.get("changelog", "").strip()
    if log and not re.match(r"%s(\s|$)" % re.escape(version), log):
        return ["metadata.txt: changelog начинается не с %s" % version]
    return []


def version_mentions(root=ROOT):
    """Место и номер: первый раздел CHANGELOG.md и версии в README."""
    found = []
    path = os.path.join(root, "CHANGELOG.md")
    if os.path.exists(path):
        for n, line in enumerate(read(path).split("\n"), 1):
            m = VERSION.search(line) if line.startswith("## ") else None
            if m:
                found.append(("CHANGELOG.md:%d" % n, m.group(1)))
                break
    for name in README:
        path = os.path.join(root, name)
        if not os.path.exists(path):
            continue
        for n, line in enumerate(read(path).split("\n"), 1):
            if re.search(r"Isoliner3D|[Вв]ерси|[Vv]ersion", line):
                for m in VERSION.finditer(line):
                    found.append(("%s:%d" % (name, n), m.group(1)))
    return found


def check(root=ROOT, net=False):
    """Ошибки и замечания проверки: два списка строк."""
    errors, warnings = [], []
    cp = configparser.ConfigParser()
    cp.read(os.path.join(root, PLUGIN, "metadata.txt"), encoding="utf-8")
    general = cp["general"]
    # каталог читает поля с подстановкой, одиночный «%» срывает загрузку
    for field in general:
        try:
            general.get(field)
        except configparser.InterpolationError as error:
            errors.append("metadata.txt: поле %s - %s" % (field, error))
    for field in REQUIRED:
        if not general.get(field, "").strip():
            errors.append("metadata.txt: не заполнено поле %s" % field)
    version = general.get("version", "").strip()
    errors += changelog_problems(general, version)
    for place, mention in version_mentions(root):
        if mention != version:
            errors.append("%s: версия %s, в metadata.txt %s"
                          % (place, mention, version))
    errors += url_problems(general)
    if general.get("experimental", "").lower() not in ("false", ""):
        warnings.append("модуль помечен как experimental")
    if net:
        errors += url_answers(general)
        for level, text in tag_problems(version):
            (errors if level == "error" else warnings).append(text)
    return version, errors, warnings


def main(argv=()):
    version, errors, warnings = check(net="--net" in argv)
    print("Проверка metadata.txt Isoliner3D %s" % (version or "?"))
    for title, lines in (("Ошибки", errors), ("Замечания", warnings)):
        if lines:
            print("\n%s:" % title)
            for line in lines:
                print("  " + line)
    if not errors and not warnings:
        print("\nВсё в порядке.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
