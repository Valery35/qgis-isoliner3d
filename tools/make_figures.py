# -*- coding: utf-8 -*-
"""
Рисует схемы для страницы Isoliner3D.

Это не снимки экрана, а схемы: они объясняют понятие, а не показывают окно.
Снимки устаревают с каждой правкой интерфейса, схемы живут дольше
и читаются на печати.

    python tools/make_figures.py

Картинки складываются в doc/figures. Оттуда их берёт сборка страницы.
Каждая схема рисуется дважды, имя_ru.png и имя_en.png: подписи внутри
нарисованы, а не выведены текстом, поэтому картинка меняется вместе
с языком страницы.
"""

import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt              # noqa: E402
from matplotlib.patches import Polygon as MplPolygon   # noqa: E402
from matplotlib.patches import FancyArrow    # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "doc", "figures")

WORDS = {
    "roof":        ("канал 1: кровля", "band 1: roof"),
    "bottom":      ("канал 2: подошва", "band 2: bottom"),
    "params":      ("каналы 3+: содержание, минтип",
                    "bands 3+: grade, mineral type"),
    "two_grids":   ("два грида", "two grids"),
    "one_body":    ("одно тело", "one body"),
    "skirt":       ("боковая юбка по границе данных",
                    "side skirt along the data boundary"),
    "vertex_col":  ("цвет в вершинах", "colour in the vertices"),
    "texture":     ("текстура", "texture"),
    "coarse":      ("детальность = плотность сетки",
                    "detail = mesh density"),
    "fine":        ("детальность не зависит от сетки",
                    "detail is independent of the mesh"),
    "plan":        ("линия разреза на плане", "the section line on the plan"),
    "drawing":     ("чертёж: расстояние на отметку",
                    "the drawing: distance by elevation"),
    "ribbon":      ("лента в сцене", "the ribbon in the scene"),
    "same_area":   ("та же область пространства",
                    "the same region of space"),
    "grids_in":    ("грид пласта", "the bed grid"),
    "bed_grid":    ("грид пласта", "bed grid"),
    "reserves":    ("запасы и отчёт", "reserves and a report"),
    "blocks":      ("блочная модель", "block model"),
    "writeoff":    ("списание", "write-off"),
    "viewer":      ("3D-просмотр", "3D viewer"),
    "bed_grid_note": ("грид пласта читается 3D-окном как тело",
                      "the bed grid is read by the 3D window as a body"),
}

LANG = "ru"


def W(key):
    """Подпись на текущем языке."""
    return WORDS[key][0 if LANG == "ru" else 1]


# Палитра страницы: спокойные заливки, тёмный контур, бирюза как акцент.
FILL_A = "#cfe3f2"
FILL_B = "#f6ddc0"
FILL_C = "#d8ead3"
EDGE = "#2b3d52"
TEAL = "#0E7C66"
AMBER = "#C2622C"
GREY = "#8b98a5"


def new_axes(width=5.2, height=2.6):
    fig, ax = plt.subplots(figsize=(width, height))
    ax.set_aspect("equal")
    ax.axis("off")
    return fig, ax


def poly(ax, points, fill, alpha=1.0, lw=1.6, edge=EDGE, z=1):
    ax.add_patch(MplPolygon(points, closed=True, facecolor=fill,
                            edgecolor=edge, linewidth=lw, alpha=alpha,
                            zorder=z))


def line(ax, points, color=EDGE, lw=1.8, style="-", z=3):
    ax.plot([p[0] for p in points], [p[1] for p in points], color=color,
            linewidth=lw, linestyle=style, zorder=z, solid_capstyle="round")


def caption(ax, x, y, text, color=EDGE, size=8.5, ha="center"):
    ax.text(x, y, text, color=color, fontsize=size, ha=ha, va="center",
            zorder=6)


def arrow(ax, x0, y0, x1, y1, color=GREY):
    ax.add_patch(FancyArrow(x0, y0, x1 - x0, y1 - y0, width=0.02,
                            head_width=0.16, head_length=0.22,
                            length_includes_head=True, color=color,
                            zorder=4))


def save(fig, name):
    os.makedirs(OUT, exist_ok=True)
    stem, ext = os.path.splitext(name)
    path = os.path.join(OUT, "%s_%s%s" % (stem, LANG, ext))
    fig.savefig(path, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _wave(x0, x1, base, amp, n=60, phase=0.0):
    """Мягкая волна: горизонт всегда рисуется кривой, а не прямой."""
    import math
    pts = []
    for i in range(n + 1):
        t = i / float(n)
        x = x0 + (x1 - x0) * t
        y = base + amp * math.sin(3.1 * t + phase)
        pts.append((x, y))
    return pts


# ───────────────────────────────────────────────────────────────────────────
# Схемы
# ───────────────────────────────────────────────────────────────────────────

def fig_bed_body():
    """Конвенция многоканального грида: два канала дают замкнутое тело."""
    fig, ax = new_axes(6.4, 2.5)
    top = _wave(0.2, 3.6, 1.55, 0.16)
    bot = _wave(0.2, 3.6, 0.95, 0.12, phase=0.8)
    line(ax, top, TEAL, 2.2)
    line(ax, bot, AMBER, 2.2)
    caption(ax, 1.9, 1.95, W("roof"), TEAL, 8.5)
    caption(ax, 1.9, 0.62, W("bottom"), AMBER, 8.5)
    caption(ax, 1.9, 0.24, W("two_grids"), GREY, 8)

    arrow(ax, 3.9, 1.25, 4.5, 1.25)

    top2 = _wave(4.8, 8.2, 1.55, 0.16)
    bot2 = _wave(4.8, 8.2, 0.95, 0.12, phase=0.8)
    poly(ax, top2 + bot2[::-1], FILL_A, lw=1.4)
    line(ax, [(4.8, top2[0][1]), (4.8, bot2[0][1])], EDGE, 2.4)
    line(ax, [(8.2, top2[-1][1]), (8.2, bot2[-1][1])], EDGE, 2.4)
    caption(ax, 6.5, 1.95, W("one_body"), EDGE, 8.5)
    caption(ax, 6.5, 0.24, W("skirt"), GREY, 8)
    ax.set_xlim(0.0, 8.5)
    ax.set_ylim(0.1, 2.2)
    return save(fig, "bed_body.png")


def fig_texture():
    """Почему текстура, а не цвет по вершинам."""
    fig, ax = new_axes(6.4, 2.4)
    left = _wave(0.2, 3.6, 1.15, 0.22)
    # цвет по вершинам: крупные ступени по числу узлов сетки
    step = 8
    shades = ["#8fb8d6", "#b9d2e6", "#dbe8f2", "#a8c7de", "#c8dcec"]
    for k in range(0, len(left) - step, step):
        seg = left[k:k + step + 1]
        band = seg + [(seg[-1][0], 0.55), (seg[0][0], 0.55)]
        poly(ax, band, shades[(k // step) % len(shades)], lw=0.8, edge="white")
    line(ax, left, EDGE, 1.8)
    for k in range(0, len(left), step):
        ax.scatter([left[k][0]], [left[k][1]], s=18, c=EDGE, zorder=5)
    caption(ax, 1.9, 1.75, W("vertex_col"), EDGE, 8.5)
    caption(ax, 1.9, 0.3, W("coarse"), GREY, 8)

    arrow(ax, 3.9, 1.05, 4.5, 1.05)

    right = _wave(4.8, 8.2, 1.15, 0.22)
    poly(ax, right + [(8.2, 0.55), (4.8, 0.55)], "#eef3f7", lw=1.0,
         edge="white")
    # текстура: частая штриховка, шаг мельче узлов сетки
    import numpy as np
    for x in np.arange(4.85, 8.2, 0.085):
        i = int((x - 4.8) / 3.4 * (len(right) - 1))
        line(ax, [(x, 0.55), (x, right[i][1])], "#b9d2e6", 1.1, z=2)
    line(ax, right, EDGE, 1.8)
    for k in range(0, len(right), step):
        ax.scatter([right[k][0]], [right[k][1]], s=18, c=EDGE, zorder=5)
    caption(ax, 6.5, 1.75, W("texture"), TEAL, 8.5)
    caption(ax, 6.5, 0.3, W("fine"), GREY, 8)
    ax.set_xlim(0.0, 8.5)
    ax.set_ylim(0.2, 2.0)
    return save(fig, "texture.png")


def fig_section():
    """Чертёж разреза ложится на ленту без пересчёта."""
    fig, ax = new_axes(6.4, 2.6)
    # план с линией разреза
    poly(ax, [(0.3, 0.5), (3.3, 0.5), (3.3, 2.0), (0.3, 2.0)], "#f2f5f0",
         lw=1.2, edge=GREY)
    line(ax, [(0.7, 0.9), (1.7, 1.5), (2.9, 1.3)], AMBER, 2.4)
    caption(ax, 1.8, 0.26, W("plan"), GREY, 8)

    # чертёж в координатах разреза
    poly(ax, [(3.9, 0.7), (6.6, 0.7), (6.6, 1.9), (3.9, 1.9)], "white",
         lw=1.4, edge=EDGE)
    for y, fill in ((1.55, FILL_B), (1.25, FILL_A), (0.95, FILL_C)):
        poly(ax, [(3.9, y - 0.14), (6.6, y - 0.1), (6.6, y + 0.12),
                  (3.9, y + 0.1)], fill, lw=0.9)
    caption(ax, 5.25, 2.1, W("drawing"), EDGE, 8.5)

    arrow(ax, 6.9, 1.3, 7.5, 1.3)

    # лента в сцене: тот же чертёж, поставленный в пространство
    base = [(7.8, 0.75), (9.4, 1.15), (11.0, 0.95)]
    top = [(7.8, 1.75), (9.4, 2.15), (11.0, 1.95)]
    poly(ax, base + top[::-1], "white", lw=1.4, edge=EDGE)
    for d, fill in ((0.72, FILL_B), (0.46, FILL_A), (0.2, FILL_C)):
        band = [(x, y + d) for x, y in base]
        band += [(x, y + d + 0.2) for x, y in reversed(base)]
        poly(ax, band, fill, lw=0.9)
    caption(ax, 9.4, 2.42, W("ribbon"), TEAL, 8.5)
    caption(ax, 9.4, 0.42, W("same_area"), GREY, 8)
    ax.set_xlim(0.1, 11.3)
    ax.set_ylim(0.1, 2.6)
    return save(fig, "section.png")


def fig_pipeline():
    """Конвейер группы: от гридов до списания."""
    fig, ax = new_axes(7.2, 1.7)
    boxes = [("1.01", "grids_in", FILL_A),
             ("1.02", "reserves", FILL_C),
             ("1.03", "blocks", FILL_B),
             ("1.06", "writeoff", FILL_B)]
    x = 0.2
    for number, key, fill in boxes:
        poly(ax, [(x, 0.6), (x + 2.1, 0.6), (x + 2.1, 1.5), (x, 1.5)], fill,
             lw=1.4)
        caption(ax, x + 1.05, 1.28, number, EDGE, 10)
        caption(ax, x + 1.05, 0.92, W(key), EDGE, 7.6)
        if x > 0.3:
            arrow(ax, x - 0.5, 1.05, x - 0.06, 1.05)
        x += 2.6
    caption(ax, 0.2, 0.32, W("bed_grid_note"), GREY, 8, ha="left")
    ax.set_xlim(0.0, 10.5)
    ax.set_ylim(0.2, 1.7)
    return save(fig, "pipeline.png")


FIGURES = [fig_bed_body, fig_texture, fig_section, fig_pipeline]


def main():
    global LANG
    made = []
    for language in ("ru", "en"):
        LANG = language
        for func in FIGURES:
            made.append(func())
    LANG = "ru"
    print("Схем нарисовано: %d" % len(made))
    for path in made:
        print("  %-22s %6.1f КБ" % (os.path.basename(path),
                                    os.path.getsize(path) / 1024.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
