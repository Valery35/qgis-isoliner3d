# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Сборка руководства под Windows: тот же рецепт, что build_pdf.sh.

pandoc с xelatex (MiKTeX), сжатие Ghostscript на 150 dpi. Шрифты
DejaVu в Windows не стоят, поэтому берутся файлами по пути: из папки,
заданной DEJAVU, или из matplotlib в составе QGIS. Путь с пробелами
xelatex не любит, шрифты копируются во временную папку.

Запуск из корня репозитория:
    python manual/build_pdf_win.py
Нужны в PATH или рядом: pandoc, xelatex, gswin64c (есть в bin QGIS).
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "isoliner3d", "doc")


def _find(name, extra=()):
    found = shutil.which(name)
    if found:
        return found
    for pattern in extra:
        hits = sorted(glob.glob(pattern))
        if hits:
            return hits[-1]
    sys.exit("не найдено: %s" % name)


def _fonts(tmp):
    src = os.environ.get("DEJAVU") or (glob.glob(
        r"C:\Program Files\QGIS*\apps\Python3*\Lib\site-packages"
        r"\matplotlib\mpl-data\fonts\ttf") or [""])[-1]
    dst = os.path.join(tmp, "fonts")
    os.makedirs(dst, exist_ok=True)
    for f in glob.glob(os.path.join(src, "DejaVu*.ttf")):
        shutil.copy(f, dst)
    if not os.path.isfile(os.path.join(dst, "DejaVuSerif.ttf")):
        sys.exit("нет шрифтов DejaVu: задайте папку в DEJAVU")
    return dst.replace("\\", "/") + "/"


def _font_vars(path):
    out = []
    for var, name, it, bit in (
            ("mainfont", "DejaVuSerif", "Italic", "BoldItalic"),
            ("sansfont", "DejaVuSans", "Oblique", "BoldOblique"),
            ("monofont", "DejaVuSansMono", "Oblique", "BoldOblique")):
        out += ["-V", "%s=%s" % (var, name)]
        for opt in ("Path=" + path, "Extension=.ttf", "UprightFont=*",
                    "BoldFont=*-Bold", "ItalicFont=*-" + it,
                    "BoldItalicFont=*-" + bit):
            out += ["-V", "%soptions=%s" % (var, opt)]
    return out


def build(src, lang, out, tools, fonts, tmp):
    pandoc, xelatex, gs = tools
    raw = os.path.join(tmp, "_raw_" + out)
    print(">> %s -> %s (lang=%s)" % (src, out, lang))
    cmd = [pandoc, src, "-o", raw, "--pdf-engine=" + xelatex,
           "--toc", "--toc-depth=3", "-V", "geometry:margin=2.2cm",
           "-V", "colorlinks=true", "-V", "lang=" + lang,
           "-V", "header-includes=\\usepackage{float}"
                 "\\floatplacement{figure}{H}"] + _font_vars(fonts)
    subprocess.run(cmd, cwd=HERE, check=True)
    subprocess.run([gs, "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.5",
                    "-dPDFSETTINGS=/ebook", "-dColorImageResolution=150",
                    "-dGrayImageResolution=150",
                    "-dMonoImageResolution=150", "-dNOPAUSE", "-dQUIET",
                    "-dBATCH", "-sOutputFile=" + os.path.join(OUT, out),
                    raw], check=True)


def main():
    local = os.environ.get("LOCALAPPDATA", "")
    tools = (_find("pandoc", [os.path.join(local, "Pandoc", "pandoc.exe")]),
             _find("xelatex", [os.path.join(
                 local, "Programs", "MiKTeX", "miktex", "bin", "x64",
                 "xelatex.exe")]),
             _find("gswin64c", [r"C:\Program Files\QGIS*\bin\gswin64c.exe"]))
    os.makedirs(OUT, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        fonts = _fonts(tmp)
        build("manual.md", "ru", "Isoliner3D.pdf", tools, fonts, tmp)
        build("manual_en.md", "en", "Isoliner3D_en.pdf", tools, fonts, tmp)
    print("готово:", os.path.abspath(OUT))


if __name__ == "__main__":
    main()
