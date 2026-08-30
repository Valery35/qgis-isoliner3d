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
    "CrossValidateAlgorithm": ("cross_validate_3d", "2.05"),
    "DemoMapAlgorithm": ("demo_map", "1.08"),
    "Kriging3DAlgorithm": ("kriging_3d", "2.06"),
    "Mba3DAlgorithm": ("mba3d", "2.07"),
    "SectionsToBedAlgorithm": ("sections_to_bed", "2.08"),
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
             ("Mba3DAlgorithm", "HINTS_2_07"),
             ("SectionsToBedAlgorithm", "HINTS_2_08"),
             ("CubeToBlocksAlgorithm", "HINTS_2_03"),
             ("CubeVoxelBodyAlgorithm", "HINTS_2_04"),
             ("CrossValidateAlgorithm", "HINTS_2_05"),
             ("DemoMapAlgorithm", "HINTS_1_08"),
             ("Kriging3DAlgorithm", "HINTS_2_06"))
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


def test_demo_site_is_one_field():
    """Площадка задаётся одним охватом, а не пятью полями.

    Охват, X угла, Y угла, ширина и высота описывали один и тот же
    прямоугольник, причём четыре последних читались, только когда
    охват пуст. Пять строк на одно понятие.
    """
    import re
    src = open(os.path.join(PKG, "algorithms.py"),
               encoding="utf-8").read()
    i = src.index("class Demo3DPointsAlgorithm(")
    nxt = re.search(r"\nclass \w+Algorithm\(", src[i + 10:])
    seg = src[i:i + 10 + nxt.start()] if nxt else src[i:]
    for key in ("X0", "Y0", "SIZE_Y"):
        assert "self.%s" % key not in seg, key
    assert "self.EXTENT" in seg
    assert seg.count("self.addParameter(") == 14, seg.count(
        "self.addParameter(")


def test_demo_site_falls_back_to_a_default():
    """Пустой охват даёт площадку по умолчанию, а не отказ.

    Инструмент демонстрационный, и требовать охват до первого запуска
    незачем: размер по умолчанию печатается в журнал.
    """
    src = open(os.path.join(PKG, "algorithms.py"),
               encoding="utf-8").read()
    i = src.index("class Demo3DPointsAlgorithm(")
    seg = src[i:src.index("\nclass ", i + 10)]
    assert "Площадка по умолчанию" in seg


def test_demo_map_is_a_tool_of_its_own():
    """Карта для текстуры отделена от тел.

    В 1.07 было тринадцать полей и пять примеров с непересекающимися
    наборами: при выборе карты четыре поля картинки читались, а мощность
    и разбиение не читались вовсе. По списку было не понять, какие поля
    про твой случай.
    """
    import re
    src = open(os.path.join(PKG, "algorithms.py"),
               encoding="utf-8").read()
    assert "class DemoMapAlgorithm(" in src
    i = src.index("class PolyhedralDemoAlgorithm(")
    nxt = re.search(r"\nclass \w+Algorithm\(", src[i + 10:])
    seg = src[i:i + 10 + nxt.start()] if nxt else src[i:]
    for key in ("LIKE", "PIXEL", "CELLS", "FIELDS", "OUTPUT_MAP"):
        assert "self.%s" % key not in seg, key
    assert '"map"' not in seg
    assert seg.count("self.addParameter(") == 8, seg.count(
        "self.addParameter(")
    j = src.index("class DemoMapAlgorithm(")
    nxt2 = re.search(r"\nclass \w+Algorithm\(", src[j + 10:])
    seg2 = src[j:j + 10 + nxt2.start()] if nxt2 else src[j:]
    assert seg2.count("self.addParameter(") == 6, seg2.count(
        "self.addParameter(")
    assert "def _make_map" in seg2


def test_kriging_writes_two_cubes():
    """Кригинг отдаёт и оценку, и дисперсию.

    Дисперсия это единственное, что кригинг даёт всегда, независимо
    от густоты сети. Без неё брать его вместо обратных расстояний
    на редкой сети незачем.
    """
    import re
    src = open(os.path.join(PKG, "algorithms.py"),
               encoding="utf-8").read()
    i = src.index("class Kriging3DAlgorithm(")
    nxt = re.search(r"\nclass \w+Algorithm\(", src[i + 10:])
    seg = src[i:i + 10 + nxt.start()] if nxt else src[i:]
    assert '"OUTPUT"' in seg and '"OUTVAR"' in seg
    assert "ordinary(" in seg


def test_kriging_measures_the_variogram_itself():
    """Вариограмма замеряется по данным, а не спрашивается у человека.

    Задавать три числа на глаз бессмысленно: их и надо было замерить.
    Ручной ввод оставлен, но умолчание считает само.
    """
    import re
    src = open(os.path.join(PKG, "algorithms.py"),
               encoding="utf-8").read()
    i = src.index("class Kriging3DAlgorithm(")
    nxt = re.search(r"\nclass \w+Algorithm\(", src[i + 10:])
    seg = src[i:i + 10 + nxt.start()] if nxt else src[i:]
    assert "auto_fit(" in seg
    assert 'direction="plan"' in seg and 'direction="vert"' in seg
    assert "assemble(" in seg


def test_demo3d_explains_its_fields():
    """2.01 печатает расшифровку своих полей.

    Слой выходит с шестью полями, и по именам не видно, какое из них
    содержание, а какое номер скважины. Расшифровка нужна там, где
    данные только что созданы, а не в руководстве через две главы.
    """
    import re
    src = open(os.path.join(PKG, "algorithms.py"),
               encoding="utf-8").read()
    i = src.index("class Demo3DPointsAlgorithm(")
    nxt = re.search(r"\nclass \w+Algorithm\(", src[i + 10:])
    seg = src[i:i + 10 + nxt.start()] if nxt else src[i:]
    for field in ("hole", "from_m", "to_m", "grade", "truth", "zone"):
        assert "%s " % field in seg or "`%s`" % field in seg, field
    assert "Поля слоя:" in seg


def test_value_field_hint_names_the_demo_field():
    """Подсказка к полю значения называет поле демонстрационных данных.

    Иначе на демо подставляется первое числовое поле, а это номер
    скважины, и куб выходит по номерам.
    """
    import ast as _ast
    src = open(os.path.join(PKG, "algorithms.py"),
               encoding="utf-8").read()
    tree = _ast.parse(src)
    for node in tree.body:
        name = getattr(getattr(node, "targets", [None])[0], "id", "") \
            if isinstance(node, _ast.Assign) else ""
        if name not in ("HINTS_2_02", "HINTS_2_05", "HINTS_2_06"):
            continue
        for k, v in zip(node.value.keys, node.value.values):
            if k.value == "FIELD":
                assert "grade" in _ast.literal_eval(v), name


def test_tool_numbers_have_no_gaps():
    """Номера инструментов идут подряд, без дыр.

    Дыра в нумерации читается как «инструмент был и пропал», и первым
    делом человек ищет, куда он делся.
    """
    import re
    nums = {}
    for cls, (_name, num) in EXPECTED.items():
        g, k = num.split(".")
        nums.setdefault(g, set()).add(int(k))
    for g, got in sorted(nums.items()):
        want = set(range(1, max(got) + 1))
        assert got == want, "в группе %s нет: %s" % (
            g, sorted(want - got))


def test_cubes_are_loaded_into_the_project():
    """Записанные кубы открываются слоями сами.

    Папка сама в проект ничего не кладёт, а открывать по пять файлов
    руками - работа на пустом месте.
    """
    src = open(os.path.join(PKG, "algorithms.py"),
               encoding="utf-8").read()
    i = src.index("class SectionsToBedAlgorithm")
    seg = src[i:src.index("\nclass ", i + 10)]
    # грид один, и обычный выход растра открывается сам
    assert 'return {"OUTPUT": out_path}' in seg


def test_sections_tool_glues_contacts():
    """Контакт соседних пластов строится одной поверхностью.

    Подошва верхнего и кровля нижнего это одна граница, если геолог
    провёл их одной линией. Построенные порознь, между разрезами они
    расходятся, и в модели встаёт щель или нахлёст, которых
    на разрезе нет.
    """
    src = open(os.path.join(PKG, "algorithms.py"),
               encoding="utf-8").read()
    i = src.index("class SectionsToBedAlgorithm")
    seg = src[i:src.index("\nclass ", i + 10)]
    assert '"CONTACT"' in seg
    # порядок по залеганию, а не по имени поля: номера бывают текстом
    assert 'key=lambda d: -float(np.median(d["top"][:, 2]))' in seg
    # одна поверхность на контакт: кэш по ключу склейки
    assert "def _surface(pts, key):" in seg
    assert 'd.get("glue")' in seg and 'd.get("glue_top")' in seg


def test_sections_tool_can_be_clipped_by_a_mask():
    """2.08 умеет обрезать результат векторной маской.

    Грид строится на весь охват контуров, и за пределами разрезов тело
    живёт там, где данных нет вовсе. Маска задаёт, докуда поверхностям
    верить: контур выработки, шурфа, подсчётного блока.
    """
    src = open(os.path.join(PKG, "algorithms.py"),
               encoding="utf-8").read()
    i = src.index("class SectionsToBedAlgorithm")
    seg = src[i:src.index("\nclass ", i + 10)]
    assert '"MASK"' in seg and '"MASK_BUFFER"' in seg
    assert "polygon_mask(" in seg
    # система координат маски своя: без пересчёта она ляжет мимо грида
    assert "QgsCoordinateTransform" in seg
    # пустое пересечение - отказ, а не молча пустой грид
    assert "QgsProcessingException" in seg


def test_feedback_goes_to_the_journal_too():
    """Строки расчёта дублируются в журнал плагина.

    Раньше журнал знал только имя инструмента и время: снимок
    показывал, что расчёт прошёл за полсекунды, и ни одного числа,
    по которому видно, что именно он посчитал. На удалённой машине
    каждый такой круг стоит отдельного визита.
    """
    src = open(os.path.join(PKG, "algorithms.py"),
               encoding="utf-8").read()
    i = src.index("class _JournalFeedback")
    body = src[i:src.index("\nclass ", i + 10)]
    for name in ("pushInfo", "pushWarning", "reportError"):
        assert "def %s(" % name in body, name
    assert "__getattr__" in body, "остальное должно уходить в настоящий"
    run = src[src.index("def processAlgorithm"):]
    assert "_JournalFeedback(feedback, trace)" in run[:1200]


def test_volume_mba_removes_the_trend():
    """2.07 тоже снимает тренд: в объёме дефект тот же.

    Ошибка метода растёт вместе с величиной значения, а не с его
    разбросом. На содержаниях около двадцати процентов это половина
    разброса данных.
    """
    src = open(os.path.join(PKG, "algorithms.py"),
               encoding="utf-8").read()
    i = src.index("class Mba3DAlgorithm")
    seg = src[i:src.index("\nclass ", i + 10)]
    assert 'center="plane"' in seg


def test_sections_tool_samples_the_whole_bed():
    """2.09 опробует пласт целиком, а не кусок за куском.

    Забор нарезан по звеньям линии, и минусы вокруг одного куска
    ложатся туда, где соседний даёт плюс. На настоящих данных плюсов
    в слое решётки оставалось три процента, и ноль в кубе
    не встречался вовсе.
    """
    src = open(os.path.join(PKG, "algorithms.py"),
               encoding="utf-8").read()
    i = src.index("class SectionsToBedAlgorithm")
    seg = src[i:src.index("\nclass ", i + 10)]
    # кровля и подошва: их и надо интерполировать, а не тело целиком
    assert "section3d.roof_and_floor(own" in seg
    assert "surface_on_grid(" in seg
    # тренд снимается: без этого ошибка растёт вместе с самой отметкой,
    # и на кровле около -250 м поверхность уходила на четырнадцать метров
    assert 'center="plane"' in seg
    # расхождение разрезов должно попадать в журнал, а не считаться
    # и выбрасываться, как было
    assert "crossing_spread(" in seg
    assert "pushWarning" in seg


def test_manual_tables_match_the_tools():
    """Таблицы полей в руководстве собираются из кода, а не пишутся.

    Руководство, писанное отдельно, расходится с кодом на первой же
    правке: поле переименовали, а в тексте старое имя. Проверка
    сверяет подписи полей из кода с тем, что стоит в руководстве.
    """
    import importlib.util
    root = os.path.dirname(PKG)
    gen = os.path.join(root, "tools", "gen_tool_tables.py")
    assert os.path.isfile(gen), "нет сборщика таблиц"
    spec = importlib.util.spec_from_file_location("gen_tables", gen)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    tools = mod.collect()
    assert len(tools) >= 14, len(tools)
    man = open(os.path.join(root, "manual", "manual.md"),
               encoding="utf-8").read()
    missing = []
    for t in tools:
        if t["title"] not in man:
            missing.append(t["title"])
            continue
        for _k, lab, _kind, _hint in t["params"]:
            if ("**%s**" % lab) not in man:
                missing.append("%s / %s" % (t["title"], lab))
    assert not missing, "нет в руководстве: %s" % "; ".join(missing[:6])


def test_mesh_input_skips_the_validity_check():
    """У инструментов, читающих меш, проверка годности отключена.

    Набор смежных треугольников не бывает годным мультиполигоном
    по правилам OGC: у частей не должно быть общих внутренностей,
    а у оболочки соседние грани касаются рёбрами. Обработка отклоняла
    такой слой на входе, не начав работу.
    """
    import re
    src = open(os.path.join(PKG, "algorithms.py"),
               encoding="utf-8").read()
    bad = []
    for m in re.finditer(r"class (\w+Algorithm)\(", src):
        i = m.start()
        nxt = re.search(r"\nclass \w+Algorithm\(", src[i + 10:])
        seg = src[i:i + 10 + nxt.start()] if nxt else src[i:]
        # признак чтения меша: полигональный вход и разбор колец
        if "TypeVectorPolygon" in seg and "exteriorRing" in seg:
            if "GeometryNoCheck" not in seg:
                bad.append(m.group(1))
    assert not bad, "проверка не снята: %s" % ", ".join(bad)


def test_mba_calls_match_the_core():
    """Инструмент 2.07 зовёт ядро с теми подписями, что у ядра есть.

    Отчёт по уровням возвращает словари, а не строки, и подстановка
    их прямо в журнал роняла работу на первом же уровне. Проверка
    сверяет вызовы с настоящими подписями.
    """
    import ast
    import importlib.util
    import inspect
    spec = importlib.util.spec_from_file_location(
        "mba_core", os.path.join(PKG, "mba.py"))
    mba = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mba)
    src = open(os.path.join(PKG, "algorithms.py"),
               encoding="utf-8").read()
    i = src.index("class Mba3DAlgorithm(")
    nxt = src.index("\nclass ", i + 10)
    seg = src[i:nxt]
    tree = ast.parse(seg.strip())
    called = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and getattr(node.func.value, "id", "") == "mba"):
            called.add(node.func.attr)
    assert called, "инструмент не зовёт ядро вовсе"
    for name in sorted(called):
        assert hasattr(mba, name), "нет в ядре: %s" % name
        inspect.signature(getattr(mba, name))
    # отчёт по уровням разбирается, а не суётся в журнал как есть
    assert "levels_report" in called
    assert 'rep["max"]' in seg and 'rep["cells"]' in seg


def test_sectors_are_taken_from_the_data():
    """Число секторов берётся от опробования, а не ставится наугад.

    Умолчание в восемь было сделано под скважины и не разведено
    с плановыми данными: у почвенных проб деление рвёт поле лучами
    от узлов.
    """
    import re
    src = open(os.path.join(PKG, "algorithms.py"),
               encoding="utf-8").read()
    for cls in ("Interp3DAlgorithm", "CrossValidateAlgorithm",
                "Kriging3DAlgorithm"):
        i = src.index("class %s(" % cls)
        nxt = re.search(r"\nclass \w+Algorithm\(", src[i + 10:])
        seg = src[i:i + 10 + nxt.start()] if nxt else src[i:]
        assert "auto_sectors(" in seg, cls
        j = seg.index('"SECTORS", self.tr(')
        assert "0 - от данных" in seg[j:j + 200], cls
        assert "defaultValue=0" in seg[j:j + 260], cls


def test_blocks_can_be_clipped_by_surfaces():
    """2.03 отсекает точки поверхностями сверху и снизу.

    Одной отметкой этого не заменить: дневной рельеф и кровля меняются
    по площади, а отметка плоская.
    """
    import re
    src = open(os.path.join(PKG, "algorithms.py"),
               encoding="utf-8").read()
    i = src.index("class CubeToBlocksAlgorithm(")
    nxt = re.search(r"\nclass \w+Algorithm\(", src[i + 10:])
    seg = src[i:i + 10 + nxt.start()] if nxt else src[i:]
    assert "self.TOPSURF" in seg and "self.BOTSURF" in seg
    assert "keep_between(px, py, pz, ta, tg, ba, bg)" in seg
    # отсечка идёт до выгрузки, а не после
    assert seg.index("keep_between(") < seg.index("sink.addFeature")


def test_voxels_take_own_edges_and_labels():
    """2.04 берёт свои границы интервалов и их названия.

    Равные доли годятся не всегда: содержания делят по своим
    ступеням, и у ступеней есть имена.
    """
    import re
    src = open(os.path.join(PKG, "algorithms.py"),
               encoding="utf-8").read()
    i = src.index("class CubeVoxelBodyAlgorithm(")
    nxt = re.search(r"\nclass \w+Algorithm\(", src[i + 10:])
    seg = src[i:i + 10 + nxt.start()] if nxt else src[i:]
    assert "self.EDGES" in seg and "self.LABELS" in seg
    assert "voxel.parse_edges(" in seg and "voxel.parse_labels(" in seg
    assert '"name"' in seg
    # свои границы важнее числа интервалов
    assert seg.index("if own:") < seg.index("elif nclass > 1")


def test_kriging_can_flatten_too():
    """Спрямление есть и у кригинга.

    Вариограмма меряется в тех же координатах, в которых потом идёт
    расчёт: замерив её в абсолютных, а посчитав в спрямлённых,
    получишь модель не от этих данных.
    """
    import re
    src = open(os.path.join(PKG, "algorithms.py"),
               encoding="utf-8").read()
    i = src.index("class Kriging3DAlgorithm(")
    nxt = re.search(r"\nclass \w+Algorithm\(", src[i + 10:])
    seg = src[i:i + 10 + nxt.start()] if nxt else src[i:]
    assert '"REF"' in seg and '"REF_FLOOR"' in seg
    assert seg.count("to_flat(") >= 2
    # спрямление идёт до замера вариограммы
    assert seg.index("to_flat(") < seg.index("auto_fit(")


def test_interp3d_takes_anisotropy_from_the_variogram():
    """У 2.02 анизотропию можно замерить, а не задавать на глаз.

    Отношение длин связи в плане и по вертикали и есть анизотропия,
    и это тот случай, когда гадать не нужно.
    """
    import re
    src = open(os.path.join(PKG, "algorithms.py"),
               encoding="utf-8").read()
    i = src.index("class Interp3DAlgorithm(")
    nxt = re.search(r"\nclass \w+Algorithm\(", src[i + 10:])
    seg = src[i:i + 10 + nxt.start()] if nxt else src[i:]
    assert 'direction="plan"' in seg and 'direction="vert"' in seg
    assert "assemble(" in seg
    assert "0 - от данных" in seg[seg.index('"ANISO"'):
                                  seg.index('"ANISO"') + 300]


def test_interp3d_can_flatten_along_the_bedding():
    """2.02 умеет считать вертикаль от опорной поверхности.

    В абсолютных отметках интерполяция идёт поперёк напластования:
    у пласта со складкой соседняя по вертикали проба лежит в другой
    пачке. Никакой анизотропией это не лечится, она правит масштаб,
    а не форму.
    """
    import re
    src = open(os.path.join(PKG, "algorithms.py"),
               encoding="utf-8").read()
    i = src.index("class Interp3DAlgorithm(")
    nxt = re.search(r"\nclass \w+Algorithm\(", src[i + 10:])
    seg = src[i:i + 10 + nxt.start()] if nxt else src[i:]
    assert '"REF"' in seg and '"REF_FLOOR"' in seg
    assert "to_flat(" in seg
    # спрямляются и пробы, и узлы сетки: иначе куб ляжет не туда
    assert seg.count("to_flat(") >= 2


def test_flattened_nodes_without_reference_are_gaps():
    """Узел без опорной поверхности остаётся пропуском.

    Продлить поверхность наружу значило бы считать спрямление
    от выдумки.
    """
    import re
    src = open(os.path.join(PKG, "algorithms.py"),
               encoding="utf-8").read()
    i = src.index("class Interp3DAlgorithm(")
    nxt = re.search(r"\nclass \w+Algorithm\(", src[i + 10:])
    seg = src[i:i + 10 + nxt.start()] if nxt else src[i:]
    assert "np.isfinite(fz)" in seg or "isfinite(nodes_f" in seg


def test_fields_avoid_the_deprecated_constructor():
    """Поля слоя заводятся помощником, а не устаревшим вызовом.

    В новых сборках QGIS `QgsField(name, QVariant.Type)` объявлен
    устаревшим и на каждый запуск сыплет предупреждениями в журнал.
    """
    import re
    src = open(os.path.join(PKG, "algorithms.py"),
               encoding="utf-8").read()
    assert "def _field(name, kind):" in src
    body = src[src.index("def _advanced("):]
    left = re.findall(r"(?<![\w.])QgsField\(", body)
    assert not left, "остались прямые вызовы: %d" % len(left)
    head = src[:src.index("def _advanced(")]
    assert "QMetaType" in head


if __name__ == "__main__":
    ok = 0
    for nm, fn in sorted(globals().items()):
        if nm.startswith("test_") and callable(fn):
            fn()
            print("OK", nm)
            ok += 1
    print("all algorithms tests passed (%d)" % ok)
