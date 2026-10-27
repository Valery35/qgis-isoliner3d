# -*- coding: utf-8 -*-
"""Поля по имени: как называют одно и то же Micromine, Datamine, Surpac.

Выгрузка из горно-геологической системы приходит со своими именами
полей: у Micromine центр блока EAST, NORTH, RL, у Datamine XC, YC, ZC.
Заставлять человека выбирать шесть полей руками на каждом прогоне
незачем: если поле не выбрано, оно узнаётся здесь по имени.

Сравнение без учёта регистра и без пробелов, подчёркиваний и точек
по краям. Порядок кандидатов - порядок предпочтения: первое найденное
имя берётся.

Считается без QGIS.
"""

ROLES = {
    # скважины
    "hole": ("hole", "holeid", "hole_id", "bhid", "dhid", "well",
             "скважина", "скв", "номер"),
    "collar_x": ("east", "x", "xcollar", "easting", "x_collar"),
    "collar_y": ("north", "y", "ycollar", "northing", "y_collar"),
    "collar_z": ("rl", "z", "zcollar", "elevation", "elev", "z_collar"),
    "eoh": ("eoh", "depth", "max_depth", "maxdepth", "totaldepth",
            "total_depth", "length", "td", "глубина"),
    "s_depth": ("depth", "at", "md", "dist", "distance", "глубина"),
    "s_azi": ("azimuth", "azi", "az", "brg", "bearing", "азимут"),
    "s_angle": ("dip", "inclination", "incl", "inc", "angle", "zenith",
                "угол"),
    "from": ("from", "from_m", "depth_from", "fromdepth", "samp_from",
             "от"),
    "to": ("to", "to_m", "depth_to", "todepth", "samp_to", "до"),
    # разрез 2D-инверсии: номер профиля
    "line": ("line", "line_id", "lineid", "profile", "prof", "profile_id",
             "профиль", "линия", "пр"),
    # блочная модель: центр
    "bx": ("east", "x", "xc", "xcentre", "xcenter", "x_centre",
           "x_center", "xcen", "centroid_x"),
    "by": ("north", "y", "yc", "ycentre", "ycenter", "y_centre",
           "y_center", "ycen", "centroid_y"),
    "bz": ("rl", "z", "zc", "zcentre", "zcenter", "z_centre",
           "z_center", "zcen", "centroid_z", "elev", "elevation"),
    # блочная модель: размер
    "sx": ("_east", "dx", "xinc", "x_inc", "xsize", "x_size", "size_x",
           "sizex", "dim_x", "east_size", "xdim", "xlength"),
    "sy": ("_north", "dy", "yinc", "y_inc", "ysize", "y_size", "size_y",
           "sizey", "dim_y", "north_size", "ydim", "ylength"),
    "sz": ("_rl", "dz", "zinc", "z_inc", "zsize", "z_size", "size_z",
           "sizez", "dim_z", "rl_size", "zdim", "zlength"),
}


def _norm(name):
    """Имя для сравнения: нижний регистр, без пробелов и точек по краям.

    Подчёркивание в начале значимо: у Micromine `_EAST` - размер
    блока, а `EAST` - его центр, поэтому оно не снимается.
    """
    return str(name).strip().strip(".").lower()


def guess(names, role, taken=()):
    """Имя поля из `names` для роли `role` или None.

    `taken` - уже занятые имена: поле `depth` в устьях - глубина
    скважины, и в той же таблице оно не станет ещё чем-то.
    """
    by_norm = {}
    for nm in names:
        by_norm.setdefault(_norm(nm), nm)
    busy = {_norm(t) for t in taken if t}
    for cand in ROLES[role]:
        nm = by_norm.get(cand)
        if nm is not None and cand not in busy:
            return nm
    return None


def resolve(chosen, names, role, taken=()):
    """Выбранное поле, если оно есть в слое, иначе угаданное по имени."""
    if chosen and chosen in names:
        return chosen
    return guess(names, role, taken)
