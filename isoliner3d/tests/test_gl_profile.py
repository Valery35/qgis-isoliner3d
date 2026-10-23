# -*- coding: utf-8 -*-
"""Сцена без старого конвейера OpenGL.

На AltLinux с QGIS 4.2 контекст OpenGL выдаётся в профиле core,
где старого конвейера нет: glMatrixMode, glBegin, glOrtho отвечают
«invalid operation». Фон сцены рисовался именно ими, и окно сцены
не открывалось вовсе. Теперь фон заливается очисткой с ножницами,
а сторож следит, чтобы старый конвейер не вернулся в код модуля.

Считается на голом NumPy, QGIS не нужен.
"""

import os
import re
import sys

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PKG))

from isoliner3d.viewer_core import gradient_bands   # noqa: E402

LEGACY = ("glMatrixMode", "glBegin", "glEnd(", "glOrtho", "glLoadIdentity",
          "glPushMatrix", "glPopMatrix", "glVertex2f", "glVertex3f",
          "glColor4f", "glVertexPointer", "glEnableClientState")


def test_no_fixed_function_calls_in_the_module():
    """Ни один файл модуля (кроме сторонних библиотек) не зовёт старый
    конвейер."""
    bad = []
    for name in sorted(os.listdir(PKG)):
        if not name.endswith(".py"):
            continue
        src = open(os.path.join(PKG, name), encoding="utf-8").read()
        code = re.sub(r'(?s)""".*?"""', "", src)
        code = "\n".join(l.split("#")[0] for l in code.splitlines())
        for word in LEGACY:
            if word in code:
                bad.append((name, word))
    assert not bad, bad


def test_bands_cover_the_frame_without_gaps():
    for h in (1, 3, 17, 480, 1268, 4000):
        b = gradient_bands(h, (0, 0, 0, 1), (1, 1, 1, 1))
        assert b[0][0] == 0
        for (y, bh, _c), (y2, _h2, _c2) in zip(b, b[1:]):
            assert y + bh == y2
        assert b[-1][0] + b[-1][1] == h
        assert len(b) <= 192


def test_bands_go_from_bottom_colour_to_top_colour():
    b = gradient_bands(800, (0.0, 0.2, 0.4, 1.0), (1.0, 0.6, 0.4, 1.0))
    r = [c[0] for _y, _h, c in b]
    assert r == sorted(r)
    assert r[0] < 0.01 and r[-1] > 0.99
    assert all(abs(c[2] - 0.4) < 1e-12 for _y, _h, c in b)


def test_gradient_is_drawn_by_scissored_clears():
    src = open(os.path.join(PKG, "viewer_dialog.py"), encoding="utf-8").read()
    i = src.index("def _paint_gradient")
    body = src[i:src.index("def projectionMatrix", i)]
    assert "GL.glScissor(" in body and "GL_SCISSOR_TEST" in body
    assert "except Exception" in body


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("all gl profile tests passed")


if __name__ == "__main__":
    _run()
