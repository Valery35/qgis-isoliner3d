# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Облёт сцены для видео: позы камеры по кадрам.

Два пути. Оборот - камера идёт вокруг центра сцены на заданный угол
за заданное время, удаление и наклон не меняются. Облёт по видам -
камера переходит от одного запомненного вида к другому и на каждом
виде стоит паузу, как тур PlanetX.

Камера - словарь, как его пишет окно просмотра (_camera_state):
center [x, y, z], distance, azimuth, elevation, fov, ortho.

Переход между видами плавный: доля пути идёт по кривой smoothstep,
камера трогается и останавливается без рывка. Азимут идёт короткой
дугой: от 350° к 10° камера проходит 20°, а не 340° в обратную
сторону. Удаление меняется в логарифме: подлёт от 10 км к 100 м
не проскакивает ближнюю часть за один кадр.

Модуль Qt и QGIS не знает.
"""

import math

FPS = 25


def frame_count(seconds, fps=FPS):
    """Число кадров на отрезок seconds: не меньше одного."""
    return max(1, int(round(float(seconds) * fps)))


def smoothstep(t):
    """Плавная доля пути: 0 и 1 с нулевой скоростью на концах."""
    t = min(max(float(t), 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def turn(a, b):
    """Поворот от азимута a к b короткой дугой, градусы, -180..180."""
    d = (float(b) - float(a)) % 360.0
    return d - 360.0 if d > 180.0 else d


def _cam(cam):
    """Камера с полным набором ключей."""
    c = cam.get("center") or [0.0, 0.0, 0.0]
    return {"center": [float(c[0]), float(c[1]), float(c[2])],
            "distance": max(float(cam.get("distance", 10.0)), 1e-9),
            "azimuth": float(cam.get("azimuth", 0.0)),
            "elevation": float(cam.get("elevation", 30.0)),
            "fov": float(cam.get("fov", 60.0)),
            "ortho": bool(cam.get("ortho", False))}


def blend(a, b, t):
    """Камера между видами a и b на доле t (уже сглаженной)."""
    a, b = _cam(a), _cam(b)
    t = min(max(float(t), 0.0), 1.0)
    center = [a["center"][k] + (b["center"][k] - a["center"][k]) * t
              for k in range(3)]
    dist = math.exp(math.log(a["distance"])
                    + (math.log(b["distance"]) - math.log(a["distance"]))
                    * t)
    az = (a["azimuth"] + turn(a["azimuth"], b["azimuth"]) * t) % 360.0
    return {"center": center, "distance": dist, "azimuth": az,
            "elevation": a["elevation"]
            + (b["elevation"] - a["elevation"]) * t,
            "fov": a["fov"] + (b["fov"] - a["fov"]) * t,
            # проекция не плавает: переключается на середине перехода
            "ortho": b["ortho"] if t >= 0.5 else a["ortho"]}


def orbit(cam, degrees=360.0, seconds=12.0, fps=FPS):
    """Кадры оборота вокруг центра камеры cam.

    Последний кадр оборота на 360° не повторяет первый: ролик,
    пущенный по кругу, иначе запинается на стыке.
    """
    cam = _cam(cam)
    n = frame_count(seconds, fps)
    full = abs(abs(float(degrees)) - 360.0) < 1e-9
    steps = n if full else max(n - 1, 1)
    out = []
    for i in range(n):
        c = dict(cam)
        c["center"] = list(cam["center"])
        c["azimuth"] = (cam["azimuth"] + float(degrees) * i / steps) % 360.0
        out.append(c)
    return out


def tour(views, leg=4.0, pause=1.0, fps=FPS):
    """Кадры облёта по видам views: пауза на виде, переход, пауза...

    Один вид - только пауза на нём. Пустой список - пустой облёт.
    """
    views = [_cam(v) for v in views or []]
    if not views:
        return []
    hold = frame_count(pause, fps) if pause > 0 else 0
    move = frame_count(leg, fps)
    out = []
    for i, v in enumerate(views):
        out.extend(dict(v, center=list(v["center"])) for _ in range(hold))
        if i + 1 < len(views):
            nxt = views[i + 1]
            for k in range(1, move + 1):
                out.append(blend(v, nxt, smoothstep(k / move)))
    if not out:
        out.append(dict(views[-1]))
    return out


def duration(frames, fps=FPS):
    """Длительность ролика из frames кадров, секунды."""
    return len(frames) / float(fps)
