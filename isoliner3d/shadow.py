# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Солнце сцены и тени от рельефа и объектов.

Одно Солнце на всю сцену: по нему считается и отмывка рельефа,
и тени. Тени отбрасывают все меши сцены (рельеф, тела, выработки,
скважины) друг на друга. Счёт идёт на процессоре, картой глубины
со стороны Солнца, как в shadow mapping:

1. Сцена смотрится вдоль лучей Солнца. Каждая точка получает две
   координаты в плоскости, поперёк лучей, и глубину - насколько она
   ближе к Солнцу.
2. Треугольники засеваются точками с шагом не крупнее ячейки карты,
   и в каждой ячейке запоминается самая близкая к Солнцу глубина.
3. Вершина в тени, если в её ячейке есть что-то ближе к Солнцу,
   чем она сама, с запасом на наклон. Соседние ячейки дают долю
   тени, и край тени выходит мягким, а не ступенькой.

Тень ложится на цвета вершин, как и отмывка: видеокарта и шейдеры
не меняются. Без Qt и QGIS.
"""
import math

import numpy as np

# Солнце по умолчанию: то же направление, что у прежней отмывки
# (viewer_core.LIGHT_DIR), округлённое до целых градусов.
SUN_AZIMUTH = 218.0
SUN_ALTITUDE = 55.0
SHADOW_STRENGTH = 50       # процентов: насколько темнее тень
MAP_SIDE = 1024            # ячеек карты глубины по длинной стороне
MAX_SAMPLES = 4000000      # потолок точек засева на всю сцену


def sun_vector(azimuth, altitude):
    """Единичный вектор на Солнце: x на восток, y на север, z вверх.

    Азимут в градусах от севера по часовой стрелке, высота в градусах
    над горизонтом.
    """
    az = math.radians(float(azimuth))
    alt = math.radians(float(np.clip(altitude, 0.5, 90.0)))
    return np.array([math.sin(az) * math.cos(alt),
                     math.cos(az) * math.cos(alt),
                     math.sin(alt)])


def light_basis(sun):
    """Оси карты глубины: две поперёк лучей и одна вдоль, на Солнце."""
    w = np.asarray(sun, dtype=float)
    w = w / np.linalg.norm(w)
    up = np.array([0.0, 0.0, 1.0]) if abs(w[2]) < 0.99 else \
        np.array([0.0, 1.0, 0.0])
    u = np.cross(up, w)
    u /= np.linalg.norm(u)
    v = np.cross(w, u)
    return u, v, w


def sample_triangles(verts, faces, step, cap=MAX_SAMPLES):
    """Точки на треугольниках с шагом около step: вершины, центры
    и равномерный засев крупных граней.

    Крупная грань выработки или тела без засева оставила бы в карте
    дыру размером с саму грань, и тень от неё не легла бы.
    """
    v = np.asarray(verts, dtype=float)
    f = np.asarray(faces, dtype=np.int64)
    if not len(v) or not len(f):
        return np.zeros((0, 3))
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    out = [v, (a + b + c) / 3.0]
    n = np.ceil(area / max(step * step * 0.5, 1e-12)).astype(np.int64)
    n = np.minimum(n, 4096)
    big = n > 1
    total = int(n[big].sum())
    if total > cap:
        n[big] = np.maximum(1, (n[big] * cap // max(total, 1)))
        total = int(n[big].sum())
    if total:
        idx = np.repeat(np.nonzero(big)[0], n[big])
        rng = np.random.default_rng(7)
        r1 = np.sqrt(rng.random(len(idx)))
        r2 = rng.random(len(idx))
        out.append(a[idx] * (1 - r1)[:, None] +
                   b[idx] * (r1 * (1 - r2))[:, None] +
                   c[idx] * (r1 * r2)[:, None])
    return np.vstack(out)


class ShadowMap(object):
    """Карта глубины сцены со стороны Солнца."""

    def __init__(self, meshes, sun, side=MAP_SIDE):
        self.u, self.v, self.w = light_basis(sun)
        pts = [np.asarray(m[0], dtype=float) for m in meshes if len(m[0])]
        if not pts:
            self.depth = None
            return
        allp = np.vstack(pts)
        pu, pv = allp @ self.u, allp @ self.v
        self.u0, self.v0 = float(pu.min()), float(pv.min())
        span = max(float(pu.max() - self.u0), float(pv.max() - self.v0),
                   1e-9)
        self.cell = span / float(side)
        self.nu = int(math.ceil((pu.max() - self.u0) / self.cell)) + 1
        self.nv = int(math.ceil((pv.max() - self.v0) / self.cell)) + 1
        depth = np.full(self.nu * self.nv, -np.inf)
        cap = MAX_SAMPLES // max(len(meshes), 1)
        for verts, faces in meshes:
            s = sample_triangles(verts, faces, self.cell * 0.7, cap)
            if not len(s):
                continue
            iu, iv = self._cells(s)
            np.maximum.at(depth, iu * self.nv + iv, s @ self.w)
        self.depth = depth.reshape(self.nu, self.nv)

    def _cells(self, p):
        iu = np.clip(((p @ self.u - self.u0) / self.cell).astype(np.int64),
                     0, self.nu - 1)
        iv = np.clip(((p @ self.v - self.v0) / self.cell).astype(np.int64),
                     0, self.nv - 1)
        return iu, iv

    def shade(self, points, normals=None):
        """Доля тени в точках: 0 - свет, 1 - полная тень.

        Запас по глубине гасит самозатенение. Поверхность, засеянная
        точками, в своей и соседних ячейках чуть ближе к Солнцу, чем
        вершина, и тем ближе, чем косее на неё падает свет: на низком
        Солнце ровная земля иначе затеняла бы сама себя. Поэтому запас
        растёт с тангенсом угла между нормалью и лучом. Без нормалей
        поверхность считается горизонтальной. Склоны, отвёрнутые от
        Солнца, темнит отмывка.
        """
        p = np.asarray(points, dtype=float)
        if self.depth is None or not len(p):
            return np.zeros(len(p))
        own = np.zeros(len(p))
        fade = np.ones(len(p))
        if normals is None:
            cos = np.full(len(p), abs(float(self.w[2])))
        else:
            nn = np.asarray(normals, dtype=float)
            ln = np.maximum(np.linalg.norm(nn, axis=1), 1e-12)
            # Поверхность рисуется с обеих сторон, и куда смотрит её
            # нормаль, зависит от обхода треугольников. Нормаль
            # поворачивается вверх: у рельефа и пласта верх и есть
            # лицевая сторона.
            sgn = np.where(nn[:, 2] < 0.0, -1.0, 1.0)
            lam = sgn * (nn @ self.w) / ln
            lam = np.where(np.linalg.norm(nn, axis=1) > 1e-12, lam, 1.0)
            # Склон, отвёрнутый от Солнца, в собственной тени. Без
            # этого он сравнивался бы сам с собой в карте глубины,
            # и на теневых склонах шла бы рябь.
            own = np.clip(-lam / 0.15, 0.0, 1.0)
            # На склоне, куда свет падает вскользь, соседняя ячейка
            # карты - это участок склона за десятки метров, и тень
            # оттуда шла рябью. Такой склон и так тёмен от отмывки,
            # поэтому брошенная тень на нём плавно гасится.
            fade = np.clip((lam - 0.03) / 0.2, 0.0, 1.0)
            cos = np.abs(lam)
        cos = np.clip(cos, 0.1, 1.0)
        tan = np.sqrt(1.0 - cos * cos) / cos
        iu, iv = self._cells(p)
        d = p @ self.w + self.cell * (1.5 + 2.2 * tan)
        hits = np.zeros(len(p))
        n = 0
        for du in (-1, 0, 1):
            for dv in (-1, 0, 1):
                ju = np.clip(iu + du, 0, self.nu - 1)
                jv = np.clip(iv + dv, 0, self.nv - 1)
                hits += self.depth[ju, jv] > d
                n += 1
        return np.maximum(hits / float(n) * fade, own)


def darken(colors, shade, strength):
    """Притемнить цвета вершин тенью. strength - от 0 до 1."""
    c = np.asarray(colors, dtype=float).copy()
    if not len(c):
        return c
    k = 1.0 - float(np.clip(strength, 0.0, 1.0)) * np.asarray(shade)
    c[:, :3] = np.clip(c[:, :3] * k[:, None], 0.0, 1.0)
    return c
