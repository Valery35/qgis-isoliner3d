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
    "Demo3DPointsAlgorithm": ("demo_points_3d", "2.01"),
    "Interp3DAlgorithm": ("interpolate_3d", "2.02"),
    "CubeToBlocksAlgorithm": ("cube_to_block_model", "2.03"),
    "CubeVoxelBodyAlgorithm": ("cube_voxel_body", "2.04"),
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


def _enum_options(cls, key_name):
    """Число вариантов в QgsProcessingParameterEnum по имени ключа."""
    for node in ast.walk(cls):
        if not isinstance(node, ast.Call):
            continue
        fn = getattr(node.func, "attr", None) or getattr(node.func, "id", "")
        if "ParameterEnum" not in str(fn):
            continue
        arg = node.args[0] if node.args else None
        if getattr(arg, "attr", None) != key_name:
            continue
        for kw in node.keywords:
            if kw.arg == "options":
                return len(kw.value.elts)
    return None


def _tuple_len(cls, name):
    """Длина кортежа-константы класса."""
    for node in cls.body:
        if (isinstance(node, ast.Assign)
                and getattr(node.targets[0], "id", "") == name):
            return len(node.value.elts)
    return None


def test_demo_variants_match_options():
    """Каждый вариант в _KINDS обязан быть виден в списке диалога.

    Ловит потерю правки: в 0.5.2 вариант «Карта» жил в _KINDS и имел свой
    метод рисования, но в список параметра не попал, и выбрать его было
    нельзя вовсе.
    """
    cls = _classes(_tree("algorithms.py"))["PolyhedralDemoAlgorithm"]
    kinds = _tuple_len(cls, "_KINDS")
    options = _enum_options(cls, "EXAMPLE")
    assert kinds is not None and options is not None, (kinds, options)
    assert kinds == options, (
        "вариантов в _KINDS %d, а в списке диалога %d: часть недостижима"
        % (kinds, options))


def test_declared_parameter_keys_are_registered():
    """Ключ параметра, объявленный в классе, должен быть добавлен.

    Иначе parameterAs* обращается к незарегистрированному ключу
    и инструмент падает при запуске.
    """
    src = open(os.path.join(PKG, "algorithms.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    bad = []
    for cls in _classes(tree).values():
        declared = set()
        for node in cls.body:
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Tuple):
                    names = [getattr(e, "id", "") for e in target.elts]
                else:
                    names = [getattr(target, "id", "")]
                for nm in names:
                    if nm.isupper() and nm not in ("OUTPUT",):
                        declared.add(nm)
        if not declared:
            continue
        body = ast.get_source_segment(src, cls) or ""
        if "addParameter" not in body:
            continue
        for name in sorted(declared):
            used = "self.%s" % name
            if body.count(used) and "self.%s," % name not in body:
                continue
            registered = ("addParameter" in body
                          and body.count("self.%s" % name) > 0)
            if not registered:
                bad.append("%s.%s" % (cls.name, name))
    assert not bad, "ключи без регистрации: %s" % ", ".join(bad)


def test_base_class_provides_tr():
    """Инструменты берут перевод у своего базового класса.

    В QGIS 4 базовый класс Processing метод tr больше не даёт, и все
    инструменты падали при открытии окна параметров.
    """
    src = open(os.path.join(PKG, "algorithms.py"),
               encoding="utf-8").read()
    start = src.index("class IsolinerAlgorithm")
    end = src.index("class BedAssembleAlgorithm", start)
    body = src[start:end]
    assert "def tr(self, text" in body
    assert "return _tr(text)" in body


def test_groups_are_numbered():
    """Группы пронумерованы: иначе порядок в панели случайный.

    Номер инструмента должен совпадать с номером его группы, иначе
    в разговоре «второй ноль первый» указывает не туда.
    """
    src = open(os.path.join(PKG, "algorithms.py"),
               encoding="utf-8").read()
    assert 'GROUP4 = _tr("1. Пласт и блочная модель")' in src
    assert 'GROUP5 = _tr("2. 3D-интерполяция")' in src
    assert '"3.01' not in src and '"3.02' not in src


def test_enums_are_scoped():
    """Перечисления пишутся с областью, как требует QGIS 4.

    Плоская запись вроде `QgsWkbTypes.PointZ` в новых сборках даёт
    ошибку, и проверка модуля перед выкладкой в каталог её ловит.
    Дешевле поймать здесь.
    """
    import re
    src = open(os.path.join(PKG, "algorithms.py"),
               encoding="utf-8").read()
    rules = (
        (r"QgsWkbTypes\.(?!Type\.)[A-Z]", "QgsWkbTypes: нужен Type"),
        (r"QgsProcessingParameterNumber\.(?!Type\.)(Integer|Double)\b",
         "QgsProcessingParameterNumber: нужен Type"),
        (r"QgsProcessing\.(?!SourceType\.)Type[A-Z]",
         "QgsProcessing: нужен SourceType"),
        (r"QgsProcessingParameterField\.(?!DataType\.)"
         r"(Numeric|String|DateTime|Any)\b",
         "QgsProcessingParameterField: нужен DataType"),
    )
    bad = []
    for pat, why in rules:
        for m in re.finditer(pat, src):
            line = src[:m.start()].count("\n") + 1
            bad.append("%s, строка %d" % (why, line))
    assert not bad, "плоские перечисления: %s" % "; ".join(bad[:8])


def test_interp3d_data_params_come_first():
    """В основном списке 2.02 только про исходные данные.

    Настройка метода к данным отношения не имеет и в основном списке
    только мешает выбирать: пятнадцать строк подряд читаются хуже,
    чем семь.
    """
    src = open(os.path.join(PKG, "algorithms.py"),
               encoding="utf-8").read()
    seg = src[src.index("class Interp3DAlgorithm"):]
    seg = seg[:seg.index("class CubeToBlocks")]
    init = seg[seg.index("def initAlgorithm"):seg.index("def _process")]
    import re
    adv = set(re.findall(
        r'_advanced\(QgsProcessingParameter\w+\(\s*"([A-Z_]+)"', init))
    for key in ("ANISO", "RADIUS", "POWER", "MINPTS", "SECTORS"):
        assert key in adv, key
    for key in ("INPUT", "FIELD", "ZSRC", "METHOD", "CELL", "OUTPUT"):
        assert key not in adv, key


def test_interp3d_zero_means_from_the_data():
    """Ноль в шаге и числе точек означает «взять от данных»."""
    src = open(os.path.join(PKG, "algorithms.py"),
               encoding="utf-8").read()
    seg = src[src.index("class Interp3DAlgorithm"):]
    seg = seg[:seg.index("class CubeToBlocks")]
    for key in ("CELL", "CELLZ", "MAXPTS"):
        i = seg.index('"%s", self.tr(' % key)
        block = seg[i:i + 260]
        assert "0 - от данных" in block, key
        assert "defaultValue=0" in block, key
    assert "auto = auto_grid(*net) if net else None" in seg
    for line in ("Шаг по горизонтали от данных", "Шаг по вертикали "
                 "от данных", "Наибольшее число точек "):
        assert line in seg, line


def test_every_tool_has_field_hints():
    """У каждого поля каждого инструмента есть своя подсказка.

    Общая справка лежит сбоку и читается один раз, а решать «что сюда
    писать» приходится у каждого поля.
    """
    import re
    src = open(os.path.join(PKG, "algorithms.py"),
               encoding="utf-8").read()
    pairs = (("BedAssembleAlgorithm", "HINTS_1_01"),
             ("BedCalculatorAlgorithm", "HINTS_1_02"),
             ("BedToBlockModelAlgorithm", "HINTS_1_03"),
             ("SectionSurfacesToMeshAlgorithm", "HINTS_1_04"),
             ("DomainsToGridAlgorithm", "HINTS_1_05"),
             ("ReserveDeltaAlgorithm", "HINTS_1_06"),
             ("PolyhedralDemoAlgorithm", "HINTS_1_07"),
             ("Demo3DPointsAlgorithm", "HINTS_2_01"),
             ("Interp3DAlgorithm", "HINTS_2_02"),
             ("CubeToBlocksAlgorithm", "HINTS_2_03"),
             ("CubeVoxelBodyAlgorithm", "HINTS_2_04"))
    tree = ast.parse(src)
    dicts = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and \
                getattr(node.targets[0], "id", "").startswith("HINTS_"):
            dicts[node.targets[0].id] = {
                k.value for k in node.value.keys}
    for cls, name in pairs:
        assert name in dicts, name
        i = src.index("class %s(" % cls)
        nxt = re.search(r"\nclass \w+Algorithm\(", src[i + 10:])
        seg = src[i:i + 10 + nxt.start()] if nxt else src[i:]
        assert "_hints(self, %s)" % name in seg, cls
        keys = set(re.findall(r'"([A-Z_0-9]+)",\s*self\.tr\(', seg))
        keys |= set(re.findall(r'self\.addParameter\((?:_advanced\()?'
                               r'QgsProcessingParameter\w+\(\s*\n?\s*'
                               r'self\.([A-Z_0-9]+)\b', seg))
        missing = sorted(k for k in keys if k not in dicts[name])
        assert not missing, "%s: без подсказки %s" % (cls, missing)


def test_field_hints_say_what_the_other_choice_costs():
    """Подсказка не пересказывает имя поля, а объясняет выбор.

    «Шаг по горизонтали» в подсказке «шаг по горизонтали» бесполезен.
    Полезна цена другого выбора.
    """
    src = open(os.path.join(PKG, "algorithms.py"),
               encoding="utf-8").read()
    tree = ast.parse(src)
    for node in tree.body:
        if not (isinstance(node, ast.Assign)
                and getattr(node.targets[0], "id", "").startswith("HINTS_")):
            continue
        for key, val in zip(node.value.keys, node.value.values):
            text = ast.literal_eval(val)
            assert len(text) > 40, (key.value, text)
            assert text[0].isupper(), (key.value, text)
            assert text.rstrip().endswith("."), (key.value, text)


if __name__ == "__main__":
    ok = 0
    for nm, fn in sorted(globals().items()):
        if nm.startswith("test_") and callable(fn):
            fn()
            print("OK", nm)
            ok += 1
    print("all algorithms tests passed (%d)" % ok)
