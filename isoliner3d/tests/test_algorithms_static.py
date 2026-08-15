# -*- coding: utf-8 -*-
#
# Isoliner3D - 3D-просмотр поверхностей (QGIS).
# © 2026 ООО «Информ++» (www.informpp.ru).
# SPDX-License-Identifier: GPL-2.0-or-later
#
"""Проверки группы «Пласт и блочная модель» без запуска QGIS.

`algorithms.py` импортирует qgis.core на верхнем уровне, поэтому выполнить
его headless нельзя. Разбираем файл статически, через AST: этого хватает,
чтобы поймать типовые поломки при переносе и правках - пропавший класс,
дубль идентификатора, инструмент не в той группе, забытую запись в
ALGORITHMS.

Запуск:  python isoliner3d/tests/test_algorithms_static.py
"""
import ast
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)

EXPECTED = {
    "BedAssembleAlgorithm": ("assemble_bed_grid", "1.01"),
    "BedCalculatorAlgorithm": ("bed_calculator", "1.02"),
    "BedToBlockModelAlgorithm": ("bed_to_block_model", "1.03"),
    "SectionSurfacesToMeshAlgorithm": ("surfaces_to_mesh3d", "1.04"),
    "DomainsToGridAlgorithm": ("domains_to_grid", "1.05"),
    "ReserveDeltaAlgorithm": ("reserve_delta", "1.06"),
    "PolyhedralDemoAlgorithm": ("polyhedral_demo", "1.07"),
}


def _tree(name):
    with open(os.path.join(PKG, name), encoding="utf-8") as fh:
        return ast.parse(fh.read())


def _classes(tree):
    return {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}


def _returned_const(cls, method):
    """Константа, возвращаемая одностроч(н)ым методом класса."""
    for node in cls.body:
        if not isinstance(node, ast.FunctionDef) or node.name != method:
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Return):
                val = sub.value
                if isinstance(val, ast.Constant):
                    return val.value
                if (isinstance(val, ast.Call) and val.args
                        and isinstance(val.args[0], ast.Constant)):
                    return val.args[0].value
    return None


def test_all_algorithms_present():
    cls = _classes(_tree("algorithms.py"))
    missing = sorted(set(EXPECTED) - set(cls))
    assert not missing, "нет классов: %s" % ", ".join(missing)


def test_ids_and_numbers():
    cls = _classes(_tree("algorithms.py"))
    for name, (alg_id, number) in sorted(EXPECTED.items()):
        got = _returned_const(cls[name], "name")
        assert got == alg_id, "%s: id %r вместо %r" % (name, got, alg_id)
        disp = _returned_const(cls[name], "displayName") or ""
        assert disp.startswith(number), (
            "%s: имя %r не начинается с %s" % (name, disp, number))


def test_ids_unique():
    cls = _classes(_tree("algorithms.py"))
    ids = [_returned_const(cls[n], "name") for n in EXPECTED]
    assert len(set(ids)) == len(ids), "дубли идентификаторов: %s" % ids


def test_group_is_bed_block_model():
    cls = _classes(_tree("algorithms.py"))
    for name in sorted(EXPECTED):
        gid = _returned_const(cls[name], "groupId")
        assert gid == "GROUP4_ID" or gid is None or gid == "bed_block_model", (
            "%s: groupId %r" % (name, gid))


def test_algorithms_list_matches():
    tree = _tree("algorithms.py")
    listed = None
    for node in tree.body:
        if (isinstance(node, ast.Assign)
                and getattr(node.targets[0], "id", "") == "ALGORITHMS"):
            listed = [e.id for e in node.value.elts]
    assert listed is not None, "ALGORITHMS не найден"
    assert set(listed) == set(EXPECTED), (
        "ALGORITHMS расходится с ожидаемым: %s"
        % sorted(set(listed) ^ set(EXPECTED)))


def test_provider_id_not_isoliner():
    """Провайдер обязан отличаться от основного плагина, иначе конфликт."""
    cls = _classes(_tree("provider.py"))
    prov = cls["Isoliner3DProvider"]
    assert _returned_const(prov, "id") == "isoliner3d"


def test_no_kriging_dependency():
    """Группа не должна тянуть kb2d и isolines: их в модуле нет."""
    tree = _tree("algorithms.py")
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level:
            mods.add(node.module or "")
        elif isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name)
    bad = mods & {"kb2d", "isolines", "hydro", "fractal", "topo_flow"}
    assert not bad, "лишние зависимости: %s" % ", ".join(sorted(bad))


if __name__ == "__main__":
    ok = 0
    for nm, fn in sorted(globals().items()):
        if nm.startswith("test_") and callable(fn):
            fn()
            print("OK", nm)
            ok += 1
    print("all algorithms tests passed (%d)" % ok)
