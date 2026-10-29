# -*- coding: utf-8 -*-
"""Несколько сцен в одном проекте и их перенос из другого проекта.

Просьба Ивана. Раньше в проекте жила одна сцена: набор слоёв
с настройками показа, обрезка, короб, камера. Теперь сцен сколько
угодно, у каждой имя, и между ними переключаются в окне просмотра.

Сцены лежат в проекте QGIS, в его записях: ключ «Isoliner3D/scenes» -
словарь имя -> состояние, ключ «Isoliner3D/scene» - имя текущей.
Прежний ключ «Isoliner3D/state» остаётся состоянием текущей сцены:
проект, сохранённый старой версией, открывается как проект с одной
сценой, а новый проект читается и старой версией.

Сцена ссылается на слои по их id в проекте. Поэтому перенос сцены
из другого проекта - это прежде всего перевод id: слой ищется
в текущем проекте по источнику данных, потом по id, потом по имени.
Слой, которого в текущем проекте нет, можно добавить из описания
в файле проекта.

Здесь только разбор и перевод, без QGIS: файл проекта .qgs - это XML,
.qgz - zip с этим XML внутри.
"""

import json
import os
import zipfile
import xml.etree.ElementTree as ET

DEFAULT_NAME = "Сцена 1"


def unique_name(name, taken):
    """Имя, которого ещё нет среди `taken`: «Имя», «Имя (2)» и так далее."""
    name = (name or "").strip() or DEFAULT_NAME
    if name not in taken:
        return name
    k = 2
    while "%s (%d)" % (name, k) in taken:
        k += 1
    return "%s (%d)" % (name, k)


def read_project_xml(path):
    """Текст XML проекта из .qgs или .qgz."""
    if path.lower().endswith(".qgz"):
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".qgs")]
            if not names:
                raise ValueError("в архиве проекта нет файла .qgs")
            return z.read(names[0]).decode("utf-8")
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _child(node, name):
    """Дочерний узел свойств по имени, в обоих видах записи.

    QGIS 3 пишет `<Isoliner3D><state>...`, QGIS 4 (и поздние 3.x) -
    `<properties name="Isoliner3D"><properties name="state">...`.
    """
    if node is None:
        return None
    for ch in node:
        if ch.tag == name or ch.get("name") == name:
            return ch
    return None


def _entry(props, key):
    """Значение записи Isoliner3D/<key> из узла <properties>."""
    node = _child(_child(props, "Isoliner3D"), key)
    return node.text if node is not None else None


def _json_or_none(raw):
    """Разобранный JSON или None, если записи нет или она битая."""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def parse_project(text):
    """Сцены и слои проекта из его XML.

    Возвращает (сцены {имя: состояние}, текущее имя или None,
    слои {id: {name, source, provider, type}}).
    """
    root = ET.fromstring(text)
    props = root.find("properties")
    scenes = {}
    got = _json_or_none(_entry(props, "scenes"))
    if isinstance(got, dict):
        scenes = {str(k): v for k, v in got.items() if isinstance(v, dict)}
    current = _entry(props, "scene")
    if not scenes:
        raw = _entry(props, "state")
        st = _json_or_none(raw)
        if isinstance(st, dict):
            current = current or DEFAULT_NAME
            scenes = {current: st}
    layers = {}
    for ml in root.iter("maplayer"):
        lid = (ml.findtext("id") or "").strip()
        if not lid:
            continue
        prov = ml.find("provider")
        layers[lid] = {
            "name": (ml.findtext("layername") or "").strip(),
            "source": (ml.findtext("datasource") or "").strip(),
            "provider": (prov.text or "").strip() if prov is not None
            else "",
            "type": ml.get("type", ""),
        }
    return scenes, current, layers


def absolute_source(source, project_dir):
    """Источник с относительным путём - в абсолютный от папки проекта.

    QGIS пишет пути от папки проекта: «./data/x.gpkg|layername=a».
    Путь до первой «|» переводится, хвост остаётся.
    """
    if not source:
        return source
    path, sep, tail = source.partition("|")
    if path.startswith("./") or path.startswith("../") \
            or path.startswith(".\\") or path.startswith("..\\"):
        path = os.path.normpath(os.path.join(project_dir, path))
    return path + sep + tail


def source_key(source):
    """Источник для сравнения: путь без регистра и разделителей."""
    path, sep, tail = (source or "").partition("|")
    path = os.path.normcase(os.path.normpath(path)) if path else path
    return path + sep + tail


def collect_ids(state):
    """Все строки сцены, которые могут быть id слоёв."""
    out = set()

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                out.add(k)
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, str):
            out.add(x)
    walk(state)
    return out


def remap(state, mapping):
    """Состояние сцены с заменой id слоёв по `mapping` (старый -> новый).

    Замена идёт по точному совпадению строк и ключей: id слоя - строка
    из имени и uuid, случайно совпасть с настройкой она не может.
    """
    def walk(x):
        if isinstance(x, dict):
            return {mapping.get(k, k): walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        if isinstance(x, str):
            return mapping.get(x, x)
        return x
    return walk(state)


def match_layers(used, src_layers, here, project_dir):
    """Слои чужой сцены в текущем проекте.

    `used` - id слоёв, на которые ссылаются переносимые сцены.
    `src_layers` - слои чужого проекта из `parse_project`.
    `here` - слои текущего проекта {id: {name, source}}.

    Возвращает (mapping {чужой id: id здесь}, missing [чужие id,
    которых здесь нет]). Ищется по источнику, потом по тому же id,
    потом по имени, если имя здесь единственное.
    """
    by_src = {}
    by_name = {}
    for lid, info in here.items():
        by_src.setdefault(source_key(info.get("source")), lid)
        by_name.setdefault(info.get("name"), []).append(lid)
    mapping, missing = {}, []
    for lid in sorted(used):
        info = src_layers.get(lid)
        if info is None:
            continue
        key = source_key(absolute_source(info["source"], project_dir))
        if key and key in by_src:
            mapping[lid] = by_src[key]
        elif lid in here:
            mapping[lid] = lid
        elif len(by_name.get(info["name"], [])) == 1:
            mapping[lid] = by_name[info["name"]][0]
        else:
            missing.append(lid)
    return mapping, missing
