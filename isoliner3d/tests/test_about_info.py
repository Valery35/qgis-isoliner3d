# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Окно «О программе»: общий список about_info.py.

Ссылки проверяются по форме: только https, только наши домены,
без пробелов и кириллицы в адресе. Ссылка на страницу модуля
совпадает с той, что стоит в README.

Запуск:  python isoliner3d/tests/test_about_info.py
"""
import json
import os
import sys
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

from isoliner3d import about_info as ab  # noqa: E402

DOMAINS = {"www.informpp.ru", "github.com", "plugins.qgis.org", "t.me",
           "vk.ru", "en.osm.town", "x.com", "www.facebook.com"}


def test_links_are_well_formed():
    for link in ab.LINKS:
        u = link["url"]
        p = urlsplit(u)
        assert p.scheme == "https", u
        assert p.netloc in DOMAINS, u
        assert " " not in u and u.isascii(), u
        assert link["ru"] and link["en"], u
        assert link["where"] in ("both", "pro", "lite"), u


def test_module_page_is_the_readme_link():
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as fh:
        readme = fh.read()
    page = [x["url"] for x in ab.LINKS
            if x["url"].endswith("/qgis-isoliner3d")
            and "informpp" in x["url"]]
    assert page and page[0] in readme, page


def test_each_app_gets_title_license_and_issues():
    for app in ("pro", "lite"):
        got = ab.for_app(app)
        assert len(got["title"]) == 1, app
        assert sum("GPL" in t["ru"] or "Apache" in t["ru"]
                   for t in got["text"]) == 1, app
        assert sum(x["url"].endswith("/issues")
                   for x in got["links"]) == 1, app
    assert "GPL" in str(ab.for_app("pro")["text"])
    assert "Apache" in str(ab.for_app("lite")["text"])


def test_json_is_plain():
    data = json.loads(json.dumps(ab.as_json(), ensure_ascii=False))
    assert data["version"] == ab.VERSION
    assert data["window"]["en"] == "About"


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK", name)
            n += 1
    print("all about-info tests passed (%d)" % n)
