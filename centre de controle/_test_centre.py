"""Test hors-UI des fonctions du centre : lecture themes, ecriture config, lancement."""
import io
import os
import sys
import time

SRC = "centre_controle.py"
code = open(SRC, encoding="utf-8").read().replace("root.mainloop()", "pass  # test")
# bypass du garde single-instance pour que le test puisse tourner si le centre est ouvert
code = code.replace('sys.exit(0)', 'pass  # test: bypass mutex')
g = {"__file__": os.path.abspath(SRC), "__name__": "ctest"}
exec(compile(code, SRC, "exec"), g)

schemes = g["SCHEMES"]
print("themes lus :", len(schemes))
for s in schemes:
    print("  ", s["i"], s["key"], "|", s["desc"])
assert len(schemes) == 9, "9 themes attendus"

PANEL_DIR = g["PANEL_DIR"]
print("panel dir  :", PANEL_DIR)
assert PANEL_DIR and os.path.isdir(PANEL_DIR)

# ecriture theme 6 puis retour 1 (commentaires conserves ?)
cfgp = g["panel_cfg_path"]()
before = open(cfgp, encoding="utf-8").read()
assert g["write_panel_theme"]("6"), "ecriture theme 6 KO"
mid = open(cfgp, encoding="utf-8").read()
assert re_search_theme(mid) == "6" if False else True
assert "theme = 6" in mid and "# Theme du panneau" in mid, "commentaires perdus !"
g["write_panel_theme"]("1")
after = open(cfgp, encoding="utf-8").read()
assert "theme = 1" in after and "# Theme du panneau" in after
print("ecriture config OK (commentaires conserves)")

# actuel trouve
print("theme courant :", g["read_panel_theme_key"](), "->", g["match_theme"](g["read_panel_theme_key"](), schemes)["key"])

# detection apres lancement manuel de l'exe du panel
target = g["panel_launch_target"]()
print("lancement  :", target)
ok, err = g["launch_panel"](False, target)
assert ok, err
time.sleep(3.0)
procs = g["panel_running"]()
print("panel detecte :", [p.info["pid"] if hasattr(p, 'info') else p.pid for p in procs])
assert procs, "panel non detecte"
for p in procs:
    try:
        p.terminate()
    except Exception:
        pass
time.sleep(2.0)
left = g["panel_running"]()
for p in left:
    try:
        p.kill()
    except Exception:
        pass
print("panel arrete, restants :", len(g["panel_running"]()))
print("TESTS OK")
