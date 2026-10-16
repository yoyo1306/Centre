# -*- coding: utf-8 -*-
"""_test_click.py — test d'intégration : clic RÉEL sur une ligne de thème du centre.

Usage : python _test_click.py        (depuis ce dossier ; centre + panel auto-démarrés)

Ce que ça fait :
  1. démarre CentreControle.exe et sensor_panel.exe s'ils ne tournent pas ;
  2. localise la fenêtre du centre par titre exact (« Centre de controle ») ;
  3. clic ligne 2 (03-anneaux) : surligne seulement, config.ini inchangé ;
  4. clic sur Appliquer : config.ini mis à jour, theme_cmd.txt consommé,
      PID du panel inchangé (hot-swap, pas de relance).

À savoir / pièges :
  - vignettes : grille 3×3, case 160×106, origine (8, 42). Le clic vise le centre
    de la case. Appliquer est centré vers x=256, y=422 logiques.
  - fenêtre minimisée = GetWindowRect à (-32000,-32000) → ShowWindow(hwnd, 9) d'abord.
  - pour voir les messages du centre (flash) : lancer à la place le centre en source
    avec CTRACE=1 (stdout fichier) — l'exe compilé est muet (no console).
"""
import os, time, ctypes, psutil, subprocess
from ctypes import WINFUNCTYPE, windll, c_void_p, c_ulong, c_int, byref
import ctypes.wintypes as wt

BASE  = r"C:\Users\Kevin AJOURY\Documents\Projet IA\sensor-panel-480x320"
CCDIR = r"C:\Users\Kevin AJOURY\Documents\Projet IA\centre de controle"

PAD, GAP, COLS = 8, 8, 3
THUMB_W, THUMB_H, GRID_Y0 = 160, 107, 42
FOOT_Y = 387


def cell_center(i):
    c, r = i % COLS, i // COLS
    x = PAD + c * (THUMB_W + GAP) + THUMB_W / 2
    y = GRID_Y0 + r * (THUMB_H + GAP) + THUMB_H / 2
    return x, y
GA_ROOT = 2


def procs_by_name(sub):
    out = set()
    for pp in psutil.process_iter(['name']):
        n = (pp.info['name'] or '').lower()
        if sub in n:
            out.add(pp.pid)
    return out


def cfg_theme():
    with open(os.path.join(BASE, "config.ini"), encoding="utf-8") as f:
        for l in f:
            if l.strip().startswith("theme"):
                return l.strip()
    return "?"


# 1) lancer centre + panel si absents
if not procs_by_name('centrecontrole'):
    subprocess.Popen([os.path.join(CCDIR, "CentreControle.exe")], cwd=CCDIR)
    time.sleep(2.5)
if not procs_by_name('sensor_panel'):
    subprocess.Popen([os.path.join(BASE, "sensor_panel.exe")], cwd=BASE,
                     creationflags=0x08000000)
    time.sleep(2.5)
panel_before = procs_by_name('sensor_panel')
print("processus panel avant :", sorted(panel_before))
print("config avant          :", cfg_theme())

# 2) fenêtre du centre (titre exact, non minimisée, taille attendue au scale 2)
ccpid = next(iter(procs_by_name('centrecontrole')), None)
assert ccpid, "centre introuvable !"
EW = WINFUNCTYPE(c_int, c_void_p, c_void_p)
found = []

def cb(h, l):
    if not windll.user32.IsWindowVisible(h):
        return 1
    buf = ctypes.create_unicode_buffer(256)
    windll.user32.GetWindowTextW(h, buf, 256)
    if buf.value != "Centre de controle":
        return 1
    pid = c_ulong(0)
    windll.user32.GetWindowThreadProcessId(h, byref(pid))
    r = wt.RECT()
    windll.user32.GetWindowRect(h, byref(r))
    w, hh = r.right - r.left, r.bottom - r.top
    print("fenetre trouve : pid=%d rect=(%d,%d)-(%d,%d) %dx%d" %
          (pid.value, r.left, r.top, r.right, r.bottom, w, hh))
    if w > 400 and hh > 300:
        found.append((h, r, max(1, int(round(w / 512.0)))))
    return 1

windll.user32.EnumWindows(EW(cb), 0)
assert found, "fenetre centre non trouvee"
hwnd, rect, SCALE = found[0]
pt = wt.POINT(0, 0)
windll.user32.ClientToScreen(hwnd, byref(pt))
client_x, client_y = pt.x, pt.y
print("client origin :", client_x, client_y)

def guarded_click(i):
    """clic souris VÉRIFIÉ sur la vignette i : abandon si le point n'est pas dans le centre."""
    cx, cy = cell_center(i)
    x = int(client_x + cx * SCALE)
    y = int(client_y + cy * SCALE)
    probe = wt.POINT(x, y)
    under = windll.user32.WindowFromPoint(probe)
    rootw = windll.user32.GetAncestor(under, GA_ROOT)
    same = (rootw == hwnd)
    print("clic ligne %d cible %d,%d : sous le curseur=%d racine=%d attendue=%d -> %s" %
          (i, x, y, under, rootw, hwnd, "SAFE" if same else "ABANDON"))
    if not same:
        cls = ctypes.create_unicode_buffer(128)
        windll.user32.GetClassNameW(under, cls, 128)
        print("   element sous le curseur :", cls.value)
        return False
    windll.user32.SetCursorPos(x, y)
    time.sleep(0.15)
    windll.user32.mouse_event(0x0002, 0, 0, 0, 0)   # LEFTDOWN
    time.sleep(0.06)
    windll.user32.mouse_event(0x0004, 0, 0, 0, 0)   # LEFTUP
    return True

# 3) clic ligne 2 = prévisualisation seule, puis Appliquer = thème écrit
if guarded_click(2):
    time.sleep(0.6)
    print("config apres surlignage :", cfg_theme(), "(doit être inchangé)")
    ax = int(client_x + 256 * SCALE)
    ay = int(client_y + 425 * SCALE)
    probe = wt.POINT(ax, ay)
    under = windll.user32.WindowFromPoint(probe)
    rootw = windll.user32.GetAncestor(under, GA_ROOT)
    print("clic Appliquer %d,%d -> %s" % (ax, ay, "SAFE" if rootw == hwnd else "ABANDON"))
    if rootw == hwnd:
        windll.user32.SetCursorPos(ax, ay)
        time.sleep(0.15)
        windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(0.06)
        windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
        time.sleep(2.3)
        panel_after = procs_by_name('sensor_panel')
        print("config apres Appliquer :", cfg_theme())
        print("meme pid panel         :", panel_before == panel_after, sorted(panel_after))
        print("cmd fichier consomme   :", not os.path.exists(os.path.join(BASE, "theme_cmd.txt")))
