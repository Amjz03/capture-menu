# Every text that reaches tr() has a translation in each assets/lang/*.json, with the same {fields}
# and the same " · " breaks (a notice splits its title from its detail there).
import ast, json, re, sys
from pathlib import Path

repo = Path(sys.argv[1])
tree = ast.parse((repo / "capture_menu.py").read_text(encoding="utf-8"))


def const(n):
    return n.value if isinstance(n, ast.Constant) and isinstance(n.value, str) else None


def pairs(node):   # (glyph, label) / (value, text) tuples
    for t in ast.walk(node):
        if isinstance(t, ast.Tuple) and len(t.elts) == 2 and const(t.elts[1]):
            yield const(t.elts[1])


keys = set()
for n in ast.walk(tree):
    if isinstance(n, ast.Call):
        name = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
        a = n.args
        if name == "tr" and a and const(a[0]):
            keys.add(const(a[0]))
        elif name == "set_items" and a:
            keys.update(pairs(a[0]))
        elif name in ("_row", "SettingRow") and len(a) >= 3:
            keys.add(const(a[1]))
            for extra in a[3:] + [k.value for k in n.keywords if k.arg == "describe"]:
                keys.update(pairs(extra))
                keys.update(s for t in ast.walk(extra) if isinstance(t, (ast.Lambda, ast.IfExp))
                            for s in map(const, ast.walk(t)) if s and " " in s)
        elif name in ("button",) and len(a) >= 2 and const(a[1]):
            keys.add(const(a[1]))
        elif name in ("Chip", "SectionTitle", "_show_msg") and a and const(a[0]):
            keys.add(const(a[0]))
        elif name == "LevelRow":
            keys.update(filter(None, map(const, a[:2])))
        elif name == "ActionCard":
            keys.update(filter(None, map(const, a[1:3])))
        elif name == "set_state" and len(a) >= 2 and const(a[1]):
            keys.add(const(a[1]))
    elif isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "TITLES" for t in n.targets):
        keys.update(map(const, n.value.values))
    elif isinstance(n, ast.Tuple) and len(n.elts) == 2 and const(n.elts[1]):
        # a button prompt and its label, wherever the hint list is built: ("k:Esc", "Close"), ("A", "Select")
        glyph = n.elts[0]
        if (const(glyph) and re.fullmatch(r"k:.+|[A-Z][A-Z0-9_]*", const(glyph))) or isinstance(glyph, ast.JoinedStr):
            keys.add(const(n.elts[1]))
keys = {k for k in keys if k and re.search("[a-z]", k) and k not in ("English",)}   # not button ids like DPAD_UD
assert len(keys) > 200, len(keys)

fields = lambda s: sorted(re.findall(r"\{(\w*)\}", s))
for lang_file in sorted((repo / "assets" / "lang").glob("*.json")):
    table = json.loads(lang_file.read_text(encoding="utf-8"))
    missing = sorted(k for k in keys if k not in table)
    assert not missing, f"{lang_file.name} is missing {len(missing)}: {missing[:8]}"
    for en, tx in table.items():
        assert fields(en) == fields(tx), f"{lang_file.name}: fields differ in {en!r}"
        assert en.count(" · ") == tx.count(" · "), f"{lang_file.name}: ' · ' breaks differ in {en!r}"
    print(f"{lang_file.name}: {len(keys)} texts PASS")
print("translations PASS")
