"""Genere un README.md par dossier de theme (docstring de la classe + bascule)."""
import ast
import os

BASE = os.path.dirname(os.path.abspath(__file__))
tree = ast.parse(open(os.path.join(BASE, "sensor_panel.py"), encoding="utf-8").read())
infos = {}
for n in ast.walk(tree):
    if isinstance(n, ast.ClassDef) and n.name.startswith("T0"):
        for s in n.body:
            if isinstance(s, ast.Assign) and getattr(s.targets[0], "id", "") == "name":
                infos[s.value.value] = (n.name, ast.get_docstring(n) or "")

for key in sorted(infos):
    cls, doc = infos[key]
    d = os.path.join(BASE, "theme muse spark", key)
    lines = [
        "# Theme " + key,
        "",
        "Classe : `" + cls + "` (dans sensor_panel.py)",
        "",
        doc,
        "",
        "## Apercu",
        "",
        "![preview](preview.png)",
        "",
        "## Basculer",
        "",
        "Clic droit sur le panel > Theme > " + key,
        "",
        "    python sensor_panel.py --theme=" + key,
        "",
    ]
    with open(os.path.join(d, "README.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(key, "fiche OK")
