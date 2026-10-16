"""Centre de controle SensorPanel — fenetre sur l'ECRAN PRINCIPAL.
Liste les themes de sensor_panel.py (lus dans le fichier, jamais desynchronise).
Ecrit `theme = N` dans config.ini du panel (commentaires conserves), lance /
relance / arrete le panel. Le panel demarre toujours en admin (temp CPU Ryzen).

Apparence : theme sombre ou clair (centre.ini > appearance), bascule dans la
barre de titre. Echelle x1/x2. Position persistee (x/y) ; sinon centre de
l'ecran principal. Clic droit : menu.
"""
import configparser
import ctypes
from ctypes import wintypes
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import tkinter as tk
from concurrent import futures

try:
    import psutil
    HAVE_PSUTIL = True
except Exception:
    HAVE_PSUTIL = False

FROZEN = getattr(sys, "frozen", False)
APPDIR = os.path.dirname(os.path.abspath(sys.executable if FROZEN else __file__))
CFG_PATH = os.path.join(APPDIR, "centre.ini")
# Grille 3×3 : aperçus 480×320 réduits d'un facteur 3 (160×106).
PAD, GAP, COLS = 8, 8, 3
THUMB_W, THUMB_H = 160, 107
GRID_Y0 = 70               # sous la rangée de luminosité
ROWS = 3
W = PAD + COLS * THUMB_W + (COLS - 1) * GAP + PAD
FOOT_Y = GRID_Y0 + ROWS * THUMB_H + (ROWS - 1) * GAP + 8
H = FOOT_Y + 62


def fit_grid(n):
    """Agrandit la fenêtre pour autant de rangées que de thèmes."""
    global ROWS, FOOT_Y, H
    ROWS = max(1, (max(n, 1) + COLS - 1) // COLS)
    FOOT_Y = GRID_Y0 + ROWS * THUMB_H + max(0, ROWS - 1) * GAP + 8
    H = FOOT_Y + 62
VERSION = "1.1.0"
PANEL_EXE = "sensor_panel.exe"
PANEL_PY = "sensor_panel.py"
PANEL_CFG_NAME = "config.ini"
APPLY_WAV = r"C:\Users\Kevin AJOURY\Documents\Projet IA\dofus-grab\Dofus-Grab.v32i.yolo26\staplebops-01.wav"

# Couleurs resolues par use_palette(). Cles stables pour le dessin.
PALETTES = {
    "dark": dict(
        bg="#0E1318", header="#151C24", footer="#151C24",
        card="#0E1318", card_sel="#173026", card_hover="#243140",
        line="#2A3642", accent="#3DDC84", accent_soft="#17382A",
        on_accent="#062215", txt="#E8EEF4", mut="#8B98A6", warn="#FF6B81",
        dot_off="#3A4652", btn="#1C262F", btn_hover="#27333E", btn_line="#33414E",
        menu_bg="#1C262F",
    ),
    "light": dict(
        bg="#F3F5F8", header="#FFFFFF", footer="#FFFFFF",
        card="#F3F5F8", card_sel="#E4F6EB", card_hover="#D5E0EA",
        line="#D3DBE3", accent="#0E8A46", accent_soft="#D9F3E4",
        on_accent="#FFFFFF", txt="#1B2430", mut="#5C6B7A", warn="#D23B4C",
        dot_off="#C5CED6", btn="#FFFFFF", btn_hover="#EEF2F6", btn_line="#D0D7DF",
        menu_bg="#FFFFFF",
    ),
}
C = {}
TITLE_H = 34               # logique

_exec = futures.ThreadPoolExecutor(max_workers=2)

# ---------- dpi exact (pixels reels) ----------
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# ---------- un seul exemplaire du centre ----------
# Double-clic supplementaire sur l'exe : remet la fenetre existante au premier
# plan et ferme la 2e instance au lieu d'en ouvrir 10.
_hmutex = ctypes.windll.kernel32.CreateMutexW(None, False, "CentreControleSingleInstance")
if ctypes.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
    hwnd = ctypes.windll.user32.FindWindowW(None, "Centre de controle")
    try:
        ctypes.windll.user32.ShowWindow(hwnd, 9)      # SW_RESTORE
        ctypes.windll.user32.SetForegroundWindow(hwnd)
    except Exception:
        pass
    sys.exit(0)


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


# ---------- config du centre ----------
def load_cfg():
    c = configparser.ConfigParser()
    try:
        c.read(CFG_PATH, encoding="utf-8")
    except Exception:
        pass
    for sec in ("centre", "panel"):
        if not c.has_section(sec):
            c.add_section(sec)
    return c


cfg = load_cfg()
locked = cfg.getboolean("centre", "locked", fallback=True)
topmost = cfg.getboolean("centre", "topmost", fallback=False)
admin_on = cfg.getboolean("centre", "admin", fallback=False)
mini = cfg.getboolean("centre", "mini", fallback=False)
SCALE = cfg.getint("centre", "scale", fallback=2)          # 1 = 480x320, 2 = 960x640
if SCALE not in (1, 2, 3):
    SCALE = 2
appearance = cfg.get("centre", "appearance", fallback="dark").strip().lower()
if appearance not in PALETTES:
    appearance = "dark"


def use_palette(name=None):
    """Remplit C. Configure la fenetre si elle existe deja."""
    global appearance
    if name:
        appearance = name
    C.clear()
    C.update(PALETTES[appearance])
    try:
        root.configure(bg=C["bg"])
        cv.configure(bg=C["bg"])
    except Exception:
        pass


use_palette()


def save_cfg(set_locked=None, new_admin=None, new_mini=None, new_scale=None,
             new_appearance=None):
    global locked, admin_on, mini, SCALE, appearance
    if set_locked is not None:
        locked = set_locked
    if new_admin is not None:
        admin_on = new_admin
    if new_mini is not None:
        mini = new_mini
    if new_scale is not None:
        SCALE = new_scale
    if new_appearance is not None:
        appearance = new_appearance
    try:
        cfg.set("centre", "locked", str(locked).lower())
        cfg.set("centre", "topmost", str(topmost).lower())
        cfg.set("centre", "admin", str(admin_on).lower())
        cfg.set("centre", "mini", str(mini).lower())
        cfg.set("centre", "scale", str(SCALE))
        cfg.set("centre", "appearance", appearance)
        cfg.set("centre", "x", str(root.winfo_x()))
        cfg.set("centre", "y", str(root.winfo_y()))
        if PANEL_DIR:
            cfg.set("panel", "path", PANEL_DIR)
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            cfg.write(f)
    except Exception:
        pass


# ---------- cible : le panel ----------
def resolve_panel_dir():
    p = cfg.get("panel", "path", fallback="").strip()
    if p:
        c = os.path.abspath(p)
        if os.path.isfile(os.path.join(c, PANEL_PY)) or \
                os.path.isfile(os.path.join(c, PANEL_EXE)):
            return c
    for cand in (APPDIR,
                 os.path.join(APPDIR, "sensor-panel-480x320")):
        c = os.path.abspath(cand)
        if os.path.isfile(os.path.join(c, PANEL_PY)) or \
                os.path.isfile(os.path.join(c, PANEL_EXE)):
            return c
    return None


PANEL_DIR = resolve_panel_dir()


def panel_cfg_path():
    return os.path.join(PANEL_DIR, PANEL_CFG_NAME) if PANEL_DIR else None


def read_panel_schemes():
    """[{i,key,desc}] : les themes, lus dans sensor_panel.py (name= / desc=)."""
    out = []
    src = os.path.join(PANEL_DIR or "", PANEL_PY)
    try:
        txt = open(src, encoding="utf-8").read()
    except Exception:
        return out
    for m in re.finditer(r'name = "([^"]+)"\n    desc = "([^"]+)"', txt):
        g = re.match(r"(\d+)", m.group(1))
        if g:
            out.append(dict(i=int(g.group(1)), key=m.group(1), desc=m.group(2)))
    return out


def read_panel_theme_key():
    try:
        m = re.search(r"(?m)^\s*theme\s*=\s*(\S+)",
                      open(panel_cfg_path(), encoding="utf-8").read())
        if m:
            return m.group(1)
    except Exception:
        pass
    return "1"


def match_theme(want, schemes):
    """'3', '03-anneaux', 'anneaux' -> ligne (premiere par defaut)."""
    if not schemes:
        return None
    w = re.sub(r"\s+", "", str(want)).lower()
    num = re.match(r"(\d+)", w)
    if num:
        for s in schemes:
            if s["i"] == int(num.group(1)):
                return s
    for s in schemes:
        if w and (w in s["key"].lower() or w in s["desc"].lower()):
            return s
    return schemes[0]


def write_panel_theme(key):
    """theme=key dans config.ini du panel, commentaires preserves."""
    pt = panel_cfg_path()
    try:
        txt = open(pt, encoding="utf-8").read() if os.path.isfile(pt) else ""
        new, n = re.subn(r"(?m)^(\s*theme\s*=\s*).*$",
                         lambda m: m.group(1) + str(key), txt, count=1)
        if not n:
            if "[panel]" in txt:
                new = txt.replace("[panel]", "[panel]\ntheme = " + str(key), 1)
            else:
                new = (txt + ("\n" if txt and not txt.endswith("\n") else "") +
                       "[panel]\ntheme = " + str(key) + "\n")
        with open(pt, "w", encoding="utf-8") as f:
            f.write(new)
        return True
    except Exception:
        return False


def panel_problem():
    try:
        if not PANEL_DIR:
            return "dossier panel introuvable (centre.ini > [panel] path)"
        if not (os.path.isfile(os.path.join(PANEL_DIR, PANEL_EXE)) or
                os.path.isfile(os.path.join(PANEL_DIR, PANEL_PY))):
            return "sensor_panel.exe/.py absent dans " + PANEL_DIR
    except Exception as e:
        return str(e)
    return None


def panel_launch_target():
    """(file, params) : exe du panel, sinon python/pythonw + script quote."""
    if not PANEL_DIR:
        return None
    exe = os.path.join(PANEL_DIR, PANEL_EXE)
    if os.path.isfile(exe):
        return exe, ""
    script = os.path.join(PANEL_DIR, PANEL_PY)
    if not os.path.isfile(script):
        return None
    py = shutil.which("pythonw") or shutil.which("python")
    if py:
        return py, '"' + script + '"'
    return None


def panel_running():
    """Processus du panel (psutil requis ; [] sinon)."""
    if not HAVE_PSUTIL:
        return []
    out = []
    try:
        for p in psutil.process_iter(["pid", "name", "cmdline"]):
            info = p.info or {}
            nl = (info.get("name") or "").lower()
            if "sensor_panel" in nl:
                out.append(p)
                continue
            cl = " ".join(info.get("cmdline") or []).lower() \
                if info.get("cmdline") else ""
            if "sensor_panel.py" in cl and "centre_controle" not in cl:
                out.append(p)
    except Exception:
        pass
    return out


def stop_panel_async(done=None):
    """terminate() immediat ; kill verifie apres 2 s dans un worker."""
    procs = panel_running()
    for p in procs:
        try:
            p.terminate()
        except Exception:
            pass

    def work():
        time.sleep(2.0)
        for p in panel_running():
            try:
                p.kill()
            except Exception:
                pass
        if done:
            try:
                root.after(0, done)
            except Exception:
                pass
    if procs:
        _exec.submit(work)
    return len(procs)


STARTUP_TASK = "SensorPanel"


def _schtasks_exe():
    return os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                        "System32", "schtasks.exe")


def panel_startup_enabled():
    """Vrai si le panneau est planifié à l'ouverture de session, en admin."""
    try:
        r = subprocess.run(
            [_schtasks_exe(), "/Query", "/TN", STARTUP_TASK],
            capture_output=True, creationflags=0x08000000)
        return r.returncode == 0
    except Exception:
        return False


def apply_panel_startup(enabled):
    """Crée ou retire la tâche de démarrage. La création demande l'élévation."""
    exe = os.path.join(PANEL_DIR or "", PANEL_EXE)
    if enabled and not os.path.isfile(exe):
        return False, "sensor_panel.exe introuvable"
    if (not enabled) and (not panel_startup_enabled()):
        return True, None
    tmp = os.environ.get("TEMP") or APPDIR
    log = os.path.join(tmp, "sensorpanel_startup.txt")
    script = os.path.join(tmp, "sensorpanel_startup.cmd")
    if enabled:
        body = (
            "schtasks /Create /F /TN %s /SC ONLOGON /RL HIGHEST /IT "
            "/TR \"\\\"%s\\\"\" > \"%s\" 2>&1\r\n" % (STARTUP_TASK, exe, log)
        )
    else:
        body = "schtasks /Delete /F /TN %s > \"%s\" 2>&1\r\n" % (STARTUP_TASK, log)
    try:
        if os.path.isfile(log):
            os.remove(log)
        with open(script, "w", encoding="ascii", errors="replace") as f:
            f.write(body)
    except Exception as e:
        return False, str(e)
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", script, None, tmp, 0)
    if rc <= 32:
        return False, "action refusée"
    for _ in range(40):
        time.sleep(0.25)
        if panel_startup_enabled() == bool(enabled):
            return True, None
    return False, "échec"


def launch_panel(admin, target):
    file, params = target
    try:
        if admin:
            r = ctypes.windll.shell32.ShellExecuteW(None, "runas", file,
                                                    params, PANEL_DIR, 1)
            if r <= 32:
                return False, "lancement admin refuse (UAC annule ?)"
        else:
            lst = [file] + ([params.strip('"')] if params else [])
            subprocess.Popen(lst, cwd=PANEL_DIR, creationflags=0x08000000)
        return True, None
    except Exception as e:
        return False, str(e)


# ---------- ecran principal + echelle ----------
def primary_size():
    """(l,h) de l'ecran PRINCIPAL en pixels reels (processus DPI aware)."""
    try:
        return (ctypes.windll.user32.GetSystemMetrics(0),
                ctypes.windll.user32.GetSystemMetrics(1))
    except Exception:
        return (1920, 1080)


def default_pos():
    """Centre de l'ecran principal pour la fenetre a l'echelle SCALE."""
    pw, ph = primary_size()
    return max(0, (pw - W * SCALE) // 2), max(0, (ph - H * SCALE) // 2)


def saved_pos():
    cx = cfg.get("centre", "x", fallback="").strip()
    cy = cfg.get("centre", "y", fallback="").strip()
    if cx and cy and cx != "None" and cy != "None":
        try:
            return int(cx), int(cy)
        except ValueError:
            pass
    return None


def center_on_primary():
    POS[0], POS[1] = default_pos()


# ---------- UI ----------
SCHEMES = []
SELECTION = None
preview_key = None          # thème affiché sur le panel, pas encore enregistré
flash = None
last_launch = 0.0
drag = {"moving": False, "dx": 0, "dy": 0}   # deplacement via la barre de titre

root = tk.Tk()
root.title("Centre de controle")
_icon = os.path.join(APPDIR, "ico.ico")
if os.path.isfile(_icon):
    try:
        root.iconbitmap(_icon)
    except Exception:
        pass
root.resizable(False, False)
root.configure(bg=C["bg"])

cv = tk.Canvas(root, width=W * SCALE, height=H * SCALE, bg=C["bg"],
               bd=0, highlightthickness=0)
cv.pack(fill="both", expand=True)

BTN = {}          # actions du pied : stop / run / quit
HDR = {}          # puces de la barre : theme_light / theme_dark
BRIGHT = {}       # niveaux 0..5 de l'écran 480×320
BRIGHT_LEVELS = (0, 20, 40, 60, 80, 100)
bright_sel = None
bright_hold = 0.0
POS = list(default_pos())
st = {"dot": None, "text": None, "run": None}
HOVER = {"row": None, "btn": None}


def X(v):
    """coord logique -> pixels reels."""
    return int(round(v * SCALE))


def fnt(size, bold=False):
    if bold:
        return ("Segoe UI", size * SCALE, "bold")
    return ("Segoe UI", size * SCALE)


def round_rect(x1, y1, x2, y2, r=5, **kw):
    """Rectangle a coins reels (pas le lissage blobby de smooth=True)."""
    x1, y1, x2, y2 = X(x1), X(y1), X(x2), X(y2)
    r = int(min(X(r), max(0, (x2 - x1) // 2), max(0, (y2 - y1) // 2)))
    if r < 2:
        return cv.create_rectangle(x1, y1, x2, y2, **kw)
    pts = []

    def arc(cx, cy, a0, a1, n=7):
        for i in range(n + 1):
            a = math.radians(a0 + (a1 - a0) * i / n)
            pts.extend((cx + r * math.cos(a), cy + r * math.sin(a)))

    arc(x2 - r, y1 + r, -90, 0)
    arc(x2 - r, y2 - r, 0, 90)
    arc(x1 + r, y2 - r, 90, 180)
    arc(x1 + r, y1 + r, 180, 270)
    return cv.create_polygon(pts, **kw)


def chip(store, key, x1, y1, x2, y2, label, kind="ghost", fg=None, size=8):
    """Puce cliquable. kind: ghost | solid | soft. fg force la couleur du texte."""
    store[key] = (x1, y1, x2, y2)
    hot = HOVER["btn"] == key
    if kind == "solid":
        fill, col, ol = C["accent"], C["on_accent"], C["accent"]
    elif kind == "soft":
        fill, col, ol = C["accent_soft"], C["accent"], C["accent"]
    elif hot:
        fill, col, ol = C["btn_hover"], C["txt"], C["btn_line"]
    else:
        fill, col, ol = C["btn"], C["txt"], C["btn_line"]
    round_rect(x1, y1, x2, y2, 6, fill=fill, outline=ol, width=1)
    return cv.create_text(X((x1 + x2) / 2), X((y1 + y2) / 2), text=label,
                          fill=fg or col, font=fnt(size, True))


def _small_monitor(fn):
    """Appelle fn(dxva2, handle) sur l'écran 480×320. None si absent."""
    user32 = ctypes.windll.user32
    dxva2 = ctypes.windll.dxva2

    class RECT(ctypes.Structure):
        _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                    ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

    class PHYSICAL_MONITOR(ctypes.Structure):
        _fields_ = [("hPhysicalMonitor", wintypes.HANDLE),
                    ("szPhysicalMonitorDescription", wintypes.WCHAR * 128)]

    found = []

    def cb(hmon, hdc, rect, data):
        r = rect.contents
        found.append((hmon, r.right - r.left, r.bottom - r.top))
        return True

    cb_t = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
        ctypes.POINTER(RECT), wintypes.LPARAM)
    user32.EnumDisplayMonitors(None, None, cb_t(cb), 0)
    dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [
        wintypes.HMONITOR, ctypes.POINTER(wintypes.DWORD)]
    dxva2.GetPhysicalMonitorsFromHMONITOR.argtypes = [
        wintypes.HMONITOR, wintypes.DWORD, ctypes.POINTER(PHYSICAL_MONITOR)]
    dxva2.DestroyPhysicalMonitors.argtypes = [
        wintypes.DWORD, ctypes.POINTER(PHYSICAL_MONITOR)]
    dxva2.GetVCPFeatureAndVCPFeatureReply.argtypes = [
        wintypes.HANDLE, wintypes.BYTE,
        ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD)]
    dxva2.GetVCPFeatureAndVCPFeatureReply.restype = wintypes.BOOL
    dxva2.SetMonitorBrightness.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    dxva2.SetMonitorBrightness.restype = wintypes.BOOL
    dxva2.SetVCPFeature.argtypes = [
        wintypes.HANDLE, wintypes.BYTE, wintypes.DWORD]
    dxva2.SetVCPFeature.restype = wintypes.BOOL
    for hmon, w, h in found:
        if (w, h) != (480, 320):
            continue
        n = wintypes.DWORD()
        if not dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(hmon, ctypes.byref(n)) or not n.value:
            return None
        arr = (PHYSICAL_MONITOR * n.value)()
        if not dxva2.GetPhysicalMonitorsFromHMONITOR(hmon, n.value, arr):
            return None
        try:
            return fn(dxva2, arr[0].hPhysicalMonitor)
        finally:
            dxva2.DestroyPhysicalMonitors(n.value, arr)
    return None


def read_small_brightness():
    def fn(dxva2, handle):
        vct = wintypes.DWORD()
        cur = wintypes.DWORD()
        mx = wintypes.DWORD()
        ok = dxva2.GetVCPFeatureAndVCPFeatureReply(
            handle, 0x10, ctypes.byref(vct), ctypes.byref(cur), ctypes.byref(mx))
        return cur.value if ok else None
    return _small_monitor(fn)


def apply_small_brightness(percent):
    def fn(dxva2, handle):
        if dxva2.SetMonitorBrightness(handle, int(percent)):
            return True
        return bool(dxva2.SetVCPFeature(handle, 0x10, int(percent)))
    return bool(_small_monitor(fn))


def bright_geom(i):
    bw = (W - 2 * PAD - 5 * GAP) // 6
    x1 = PAD + i * (bw + GAP)
    return (x1, 40, x1 + bw, 62)


def draw_bright():
    BRIGHT.clear()
    for i, _pct in enumerate(BRIGHT_LEVELS):
        x1, y1, x2, y2 = bright_geom(i)
        on = bright_sel == i
        chip(BRIGHT, "b%d" % i, x1, y1, x2, y2, str(i),
             "solid" if on else "ghost",
             fg=None if on else C["mut"], size=8)


def set_bright(i):
    global bright_sel, bright_hold
    if not (0 <= i < len(BRIGHT_LEVELS)):
        return
    bright_sel = i
    bright_hold = time.time() + 1.5
    paint()
    percent = BRIGHT_LEVELS[i]

    def work():
        try:
            ok = apply_small_brightness(percent)
        except Exception:
            traceback.print_exc()
            ok = False

        def done():
            if not ok:
                show_flash("luminosité refusée", "warn")
        try:
            root.after(0, done)
        except Exception:
            pass
    _exec.submit(work)


def follow_bright():
    """Relit l'écran 480×320 et aligne le bouton sur le niveau physique."""
    try:
        if time.time() < bright_hold:
            pct = None
        else:
            pct = read_small_brightness()
    except Exception:
        traceback.print_exc()
        pct = None

    def done():
        global bright_sel
        if time.time() >= bright_hold and pct is not None:
            for i, v in enumerate(BRIGHT_LEVELS):
                if v == pct and bright_sel != i:
                    bright_sel = i
                    paint()
                    break
        try:
            root.after(1500, lambda: _exec.submit(follow_bright))
        except Exception:
            pass
    try:
        root.after(0, done)
    except Exception:
        pass


def draw_title():
    cv.create_rectangle(0, 0, X(W), X(TITLE_H), fill=C["header"], outline="")
    cv.create_rectangle(0, X(TITLE_H) - 1, X(W), X(TITLE_H), fill=C["line"], outline="")
    if mini:
        cv.create_rectangle(X(12), X(11), X(15), X(23), fill=C["accent"], outline="")
        cv.create_text(X(22), X(TITLE_H / 2), text="Centre de contrôle",
                       anchor="w", fill=C["txt"], font=fnt(10, True))
        cv.create_text(X(W - 12), X(TITLE_H / 2), anchor="e",
                       text="Cliquer pour rouvrir", fill=C["mut"], font=fnt(8))
        return
    chip(HDR, "options", 8, 6, 104, 28, "Options")
    # paire Clair / Sombre : la pastille pleine est le theme actif
    chip(HDR, "theme_light", W - 156, 6, W - 84, 28, "Clair",
         "solid" if appearance == "light" else "ghost",
         fg=None if appearance == "light" else C["mut"])
    chip(HDR, "theme_dark", W - 80, 6, W - 8, 28, "Sombre",
         "solid" if appearance == "dark" else "ghost",
         fg=None if appearance == "dark" else C["mut"])


THUMBS = []
_THUMB_KEEP = []


def load_thumbs():
    """Vignettes 480×320 : themes/<clé>/preview.png, à côté du panneau."""
    THUMBS.clear()
    _THUMB_KEEP.clear()
    folder = os.path.join(PANEL_DIR, "themes") if PANEL_DIR else ""
    for s in SCHEMES:
        img = None
        path = os.path.join(folder, s["key"], "preview.png")
        if os.path.isfile(path):
            try:
                src = tk.PhotoImage(file=path)
                _THUMB_KEEP.append(src)
                if SCALE > 1:
                    src = src.zoom(SCALE, SCALE)
                    _THUMB_KEEP.append(src)
                img = src.subsample(3, 3)
                _THUMB_KEEP.append(img)
            except Exception:
                img = None
        THUMBS.append(img)


def cell_geom(i):
    c, r = i % COLS, i // COLS
    x1 = PAD + c * (THUMB_W + GAP)
    y1 = GRID_Y0 + r * (THUMB_H + GAP)
    return (x1, y1, x1 + THUMB_W, y1 + THUMB_H)


def cell_at(lx, ly):
    for i in range(len(SCHEMES)):
        if hit(lx, ly, cell_geom(i)):
            return i
    return None


def draw_rows():
    if not SCHEMES:
        cv.create_text(X(W // 2), X(GRID_Y0 + 80),
                       text="Aucun thème lu : sensor_panel.py introuvable\n"
                            "Règle [panel] path dans centre.ini",
                       fill=C["warn"], font=fnt(9), justify="center")
        return
    for idx, s in enumerate(SCHEMES):
        x1, y1, x2, y2 = cell_geom(idx)
        sel = (idx == SELECTION)
        hot = (not sel) and HOVER["row"] == idx
        img = THUMBS[idx] if idx < len(THUMBS) else None
        if img is not None:
            cv.create_image(X((x1 + x2) / 2), X((y1 + y2) / 2), image=img)
        else:
            cv.create_rectangle(X(x1), X(y1), X(x2), X(y2), fill=C["card"], outline="")
            cv.create_text(X((x1 + x2) / 2), X((y1 + y2) / 2), text=s["key"],
                           fill=C["txt"], font=fnt(8, True))
        if sel:
            ol, wd = C["accent"], 3
        elif hot:
            ol, wd = C["txt"], 2
        else:
            ol, wd = C["line"], 1
        cv.create_rectangle(X(x1) + 1, X(y1) + 1, X(x2) - 1, X(y2) - 1,
                            outline=ol, width=wd)


def draw_footer():
    cv.create_rectangle(0, X(FOOT_Y), X(W), X(H), fill=C["footer"], outline="")
    cv.create_rectangle(0, X(FOOT_Y), X(W), X(FOOT_Y) + 1, fill=C["line"], outline="")
    sy = FOOT_Y + 12
    st["dot"] = cv.create_oval(X(14), X(sy - 4), X(22), X(sy + 4),
                               fill=C["dot_off"], outline="")
    st["text"] = cv.create_text(X(28), X(sy), anchor="w", text="·",
                                fill=C["mut"], font=fnt(8))
    by1, by2 = FOOT_Y + 22, FOOT_Y + 54
    chip(BTN, "stop", 8, by1, 150, by2, "Arrêter", size=9)
    chip(BTN, "run", 156, by1, W - 156, by2, "Appliquer", "solid", size=9)
    chip(BTN, "quit", W - 150, by1, W - 8, by2, "Quitter", fg=C["warn"], size=9)
    cv.create_text(X(W - 12), X(sy), anchor="e", text="v" + VERSION,
                   fill=C["mut"], font=fnt(8))
    update_status()


def update_status():
    try:
        if not st.get("text"):
            return
        tkey = read_panel_theme_key() if PANEL_DIR else "?"
        cur = match_theme(tkey, SCHEMES)
        running = bool(panel_running())
        if flash:
            txt, role = flash
            col = C["accent"] if role == "ok" else C["warn"]
            cv.itemconfig(st["text"], text=txt, fill=col)
            cv.itemconfig(st["dot"], fill=col)
        else:
            applied = cur["key"] if cur else "?"
            if preview_key and preview_key != applied:
                cv.itemconfig(st["text"],
                              text="Prévisualisation · " + preview_key,
                              fill=C["accent"])
                cv.itemconfig(st["dot"], fill=C["accent"])
            else:
                base = ("Panel actif" if running else
                        ("Panel arrêté" if HAVE_PSUTIL else "psutil absent"))
                cv.itemconfig(st["text"],
                              text=base + "   ·   " + applied,
                              fill=C["mut"])
                cv.itemconfig(st["dot"], fill=C["accent"] if running else C["dot_off"])
    except Exception:
        pass


def play_apply_sound():
    """Retour sonore quand Appliquer a enregistré le thème."""
    try:
        # SND_ASYNC | SND_NODEFAULT | SND_FILENAME
        ctypes.windll.winmm.PlaySoundW(APPLY_WAV, None, 0x00020003)
    except Exception:
        pass


def show_flash(txt, color="warn", delay=3200):
    """color : 'ok' ou 'warn' (resolu dans la palette au moment du dessin)."""
    global flash
    role = "ok" if color == "ok" else "warn"
    if os.environ.get("CTRACE"):
        print("[flash]", txt, flush=True)
    flash = (txt, role)
    update_status()

    def clear(entry=flash):
        time.sleep(delay / 1000.0)
        if globals()["flash"] == entry:
            globals()["flash"] = None
            try:
                root.after(0, update_status)
            except Exception:
                pass
    threading.Thread(target=clear, daemon=True).start()


def paint():
    """Redessine sans bouger la fenetre (survol)."""
    cv.delete("all")
    BTN.clear()
    HDR.clear()
    BRIGHT.clear()
    st["dot"] = st["text"] = st["run"] = None
    hpx = (TITLE_H if mini else H) * SCALE
    cv.configure(bg=C["bg"])
    if mini:
        draw_title()
    else:
        draw_title()
        draw_bright()
        draw_rows()
        draw_footer()
    cv.create_rectangle(1, 1, X(W) - 1, hpx - 1, outline=C["line"], width=1)
    draw_options()


def render():
    hpx = (TITLE_H if mini else H) * SCALE
    cv.configure(width=X(W), height=hpx, bg=C["bg"])
    root.configure(bg=C["bg"])
    root.geometry("%dx%d+%d+%d" % (X(W), hpx, POS[0], POS[1]))
    paint()


# ---------- actions ----------
def act(key, autohide=True):
    global last_launch, preview_key
    if key == "quit":
        on_close()
        return
    if key == "stop":
        n = stop_panel_async(lambda: show_flash("panel arrêté", "ok"))
        show_flash(("arrêt du panel (%d proc.)" % n) if n
                   else "aucun panel actif", "warn")
        return
    if key == "run":
        if not SCHEMES:
            show_flash("⚠ " + (panel_problem() or "aucun theme"), "warn")
            return
        idx = int(SELECTION) if SELECTION is not None else 0
        if not (0 <= idx < len(SCHEMES)):
            idx = 0
        sel = SCHEMES[idx]
        prob = panel_problem()
        if prob:
            show_flash("⚠ " + prob, "warn")
            return
        wr = write_panel_theme(sel["key"])
        if not wr:
            show_flash("⚠ écriture config.ini refusée", "warn")
            return
        # chemin rapide : le panel ecoute theme_cmd.txt (apply_theme a chaud)
        cmdp = os.path.join(PANEL_DIR, "theme_cmd.txt")
        hot = False
        try:
            with open(cmdp, "w", encoding="utf-8") as f:
                f.write(sel["key"])
            hot = True
        except Exception:
            try:
                os.remove(cmdp)
            except Exception:
                pass
        running = panel_running()
        if running and hot:
            preview_key = None
            play_apply_sound()
            show_flash("thème appliqué · " + sel["key"], "ok")
            return
        if hot:
            # panel arrete : le fichier serait appliqué a son lancement (redondant)
            try:
                os.remove(cmdp)
            except Exception:
                pass
        # chemin lent : lancement/relance du panel (avec anti-double-clic)
        if time.time() - last_launch < 2.0:
            show_flash("sélection · " + sel["key"], "ok")
            return
        last_launch = time.time()
        target = panel_launch_target() or (None, None)
        running = panel_running()
        if running:
            for p in running:
                try:
                    p.terminate()
                except Exception:
                    pass
            show_flash("relance · thème " + sel["key"] + " ...", "ok")

            def delayed(target=target, sel=sel):
                time.sleep(1.2)
                for p in panel_running():
                    try:
                        p.kill()
                    except Exception:
                        pass
                root.after(0, lambda: _start(target, sel, autohide))
            _exec.submit(delayed)
        else:
            _start(target, sel, autohide)


def _start(target, sel, autohide=True):
    global preview_key
    ok, err = launch_panel(True, target)
    if ok:
        preview_key = None
        play_apply_sound()
        show_flash("thème appliqué · " + sel["key"], "ok")
    else:
        show_flash("⚠ lancement impossible : " + (err or ""), "warn")


def preview_theme(sel):
    """Affiche le thème sur le panel. config.ini n'est pas modifié."""
    global preview_key, last_launch
    preview_key = sel["key"]
    prob = panel_problem()
    if prob:
        show_flash("⚠ " + prob, "warn")
        return
    cmdp = os.path.join(PANEL_DIR, "theme_cmd.txt")
    try:
        with open(cmdp, "w", encoding="utf-8") as f:
            f.write(sel["key"])
    except Exception:
        show_flash("⚠ prévisualisation impossible", "warn")
        return
    if panel_running():
        show_flash("prévisualisation · " + sel["key"], "ok")
        return
    if time.time() - last_launch < 2.0:
        show_flash("prévisualisation · " + sel["key"], "ok")
        return
    last_launch = time.time()
    target = panel_launch_target()
    if not target:
        show_flash("⚠ lancement impossible", "warn")
        return
    ok, err = launch_panel(True, target)
    if ok:
        show_flash("prévisualisation · " + sel["key"], "ok")
    else:
        show_flash("⚠ " + (err or "lancement impossible"), "warn")


def revert_preview():
    """Ferme le centre : le panel revient au thème enregistré dans config.ini."""
    if not preview_key or not PANEL_DIR:
        return
    applied = match_theme(read_panel_theme_key(), SCHEMES)
    key = applied["key"] if applied else None
    if not key or key == preview_key:
        return
    try:
        with open(os.path.join(PANEL_DIR, "theme_cmd.txt"), "w", encoding="utf-8") as f:
            f.write(key)
    except Exception:
        pass


def on_close():
    revert_preview()
    save_cfg()
    root.destroy()


# ---------- events ----------
def hit(x, y, r):
    return r[0] <= x <= r[2] and r[1] <= y <= r[3]


def on_press(e):
    """Coord logiques : tout le traitement est fait en espace 480x320."""
    lx, ly = e.x / SCALE, e.y / SCALE
    if opt_open and hit(lx, ly, opt_box):
        for key, rect in opt_rects.items():
            if not hit(lx, ly, rect):
                continue
            if key == "toggle":
                toggle_startup()
            elif key == "close":
                close_options()
            return
        return
    on_options = (not mini) and ly <= TITLE_H and "options" in HDR and hit(lx, ly, HDR["options"])
    if opt_open and not on_options:
        close_options()
    if ly <= TITLE_H:
        if mini:
            toggle_mini()                      # clic titre en mode mini = rouvrir
            return
        for k, rect in HDR.items():
            if hit(lx, ly, rect):
                if k == "options":
                    show_options(e)
                elif k == "theme_light":
                    set_appearance("light")
                elif k == "theme_dark":
                    set_appearance("dark")
                return
        if locked and lx < W - 156:
            drag["moving"] = True              # sans barre Windows, le titre déplace
            drag["dx"], drag["dy"] = e.x, e.y
        return
    if mini:
        return
    for k, rect in BRIGHT.items():
        if hit(lx, ly, rect):
            set_bright(int(k[1:]))
            return
    i = cell_at(lx, ly)
    if i is not None:
        globals()["SELECTION"] = i
        render()
        preview_theme(SCHEMES[i])
        return
    for k, rect in BTN.items():
        if hit(lx, ly, rect):
            act(k)
            return


def on_motion(e):
    if drag["moving"] or mini:
        if mini:
            cv.configure(cursor="hand2")
        return
    lx, ly = e.x / SCALE, e.y / SCALE
    if opt_open and hit(lx, ly, opt_box):
        key = None
        for k, rect in opt_rects.items():
            if hit(lx, ly, rect):
                key = k
                break
        if key != opt_hover or HOVER["row"] is not None or HOVER["btn"]:
            globals()["opt_hover"] = key
            HOVER["row"], HOVER["btn"] = None, None
            paint()
        cv.configure(cursor="hand2" if key else "")
        return
    if opt_hover is not None:
        globals()["opt_hover"] = None
    row, btn = None, None
    if ly <= TITLE_H:
        for k, rect in HDR.items():
            if hit(lx, ly, rect):
                btn = k
                break
    else:
        for k, rect in BRIGHT.items():
            if hit(lx, ly, rect):
                btn = k
                break
        if btn is None:
            i = cell_at(lx, ly)
            if i is not None:
                row = i
            else:
                for k, rect in BTN.items():
                    if hit(lx, ly, rect):
                        btn = k
                        break
    if row != HOVER["row"] or btn != HOVER["btn"]:
        HOVER["row"], HOVER["btn"] = row, btn
        paint()
    if btn or row is not None:
        cv.configure(cursor="hand2")
    elif locked and ly <= TITLE_H and lx < W - 156:
        cv.configure(cursor="fleur")
    else:
        cv.configure(cursor="")


def on_leave(e):
    if drag["moving"]:
        return
    if HOVER["row"] is not None or HOVER["btn"] or opt_hover is not None:
        HOVER["row"], HOVER["btn"] = None, None
        globals()["opt_hover"] = None
        paint()
    cv.configure(cursor="")


def set_appearance(name):
    if name not in PALETTES or name == appearance:
        return
    save_cfg(new_appearance=name)
    use_palette(appearance)
    close_options()
    build_menu()
    render()


def on_key(e):
    if e.keysym == "Escape" and opt_open:
        close_options()
        return
    if SCHEMES and e.keysym in ("Up", "Down"):
        cur = SELECTION if SELECTION is not None else -1
        globals()["SELECTION"] = int(max(0, min(len(SCHEMES) - 1,
                                            cur + (1 if e.keysym == "Down" else -1))))
        render()
    elif e.keysym in ("Return", "KP_Enter"):
        act("run")


def on_move(e):
    """Drag de la barre de titre : redeplace la fenetre (n'importe quel ecran)."""
    if drag["moving"]:
        root.geometry("+%d+%d" % (e.x_root - drag["dx"], e.y_root - drag["dy"]))
        POS[:] = [root.winfo_x(), root.winfo_y()]


def on_release(e):
    if drag["moving"]:
        drag["moving"] = False
        save_cfg()                            # memorise la nouvelle position


def toggle_mini():
    save_cfg(new_mini=not mini)
    render()


def toggle_lock():
    save_cfg(set_locked=not locked)
    root.destroy()
    if FROZEN:
        os.execv(sys.executable, [sys.executable])
    else:
        os.execv(sys.executable, [sys.executable, os.path.abspath(sys.argv[0])])


def poll():
    if not flash:
        update_status()
    root.after(2500, poll)


def recenter_primary():
    center_on_primary()
    save_cfg()
    render()


menu = tk.Menu(root, tearoff=0)
opt_open = False
opt_box = (0, 0, 0, 0)
opt_rects = {}
opt_hover = None
opt_state = {"on": False, "busy": False}


def close_options():
    global opt_open, opt_hover
    if not opt_open:
        return
    opt_open = False
    opt_hover = None
    paint()


def show_options(e):
    """Panneau Options dessiné dans la fenêtre, donc il suit le déplacement."""
    global opt_open
    if opt_open:
        close_options()
        return
    opt_state["on"] = panel_startup_enabled()
    opt_open = True
    paint()


def toggle_startup():
    if opt_state["busy"]:
        return
    want = not opt_state["on"]
    opt_state["busy"] = True
    paint()

    def work():
        ok, err = apply_panel_startup(want)

        def done():
            opt_state["busy"] = False
            if ok:
                opt_state["on"] = want
                show_flash("démarrage Windows activé" if want
                           else "démarrage Windows retiré", "ok")
            else:
                show_flash(err or "échec", "warn")
            paint()
        try:
            root.after(0, done)
        except Exception:
            pass
    _exec.submit(work)


def draw_options():
    """Colle le panneau sous le bouton Options, dans le canvas du centre."""
    global opt_box
    if not opt_open or mini:
        return
    rect = HDR.get("options")
    ox = rect[0] if rect else 8
    oy = (rect[3] + 6) if rect else TITLE_H
    ow, oh = 236, 80
    opt_box = (ox, oy, ox + ow, oy + oh)
    opt_rects.clear()
    cv.create_rectangle(X(ox), X(oy), X(ox + ow), X(oy + oh),
                        fill=C["header"], outline="")
    cv.create_text(X(ox + 12), X(oy + 16), anchor="w",
                   text="Lancer le panneau au démarrage",
                   fill=C["txt"], font=fnt(8))
    cv.create_text(X(ox + 12), X(oy + 32), anchor="w",
                   text="Activé" if opt_state["on"] else "Désactivé",
                   fill=C["accent"] if opt_state["on"] else C["mut"],
                   font=fnt(8))
    by1, by2 = oy + 46, oy + 68
    bits = (
        ("toggle", ox + 24, ox + 136,
         "Désactiver" if opt_state["on"] else "Activer", "solid"),
        ("close", ox + 144, ox + 224, "Fermer", "ghost"),
    )
    for key, x1, x2, label, kind in bits:
        opt_rects[key] = (x1, by1, x2, by2)
        hot = opt_hover == key and not opt_state["busy"]
        if kind == "solid":
            fill, col, ol = C["accent"], C["on_accent"], C["accent"]
        elif hot:
            fill, col, ol = C["btn_hover"], C["txt"], C["btn_line"]
        else:
            fill, col, ol = C["btn"], C["txt"], C["btn_line"]
        round_rect(x1, by1, x2, by2, 6, fill=fill, outline=ol, width=1)
        cv.create_text(X((x1 + x2) / 2), X((by1 + by2) / 2), text=label,
                       fill=col, font=fnt(8, True))
    cv.create_rectangle(X(ox) + 1, X(oy) + 1, X(ox + ow) - 1, X(oy + oh) - 1,
                        outline=C["line"], width=1)


def build_menu():
    menu.delete(0, "end")
    menu.configure(bg=C["menu_bg"], fg=C["txt"],
                   activebackground=C["accent"], activeforeground=C["on_accent"],
                   activeborderwidth=0, bd=0, relief="flat",
                   font=("Segoe UI", 10))
    menu.add_command(label="Thème clair", command=lambda: set_appearance("light"))
    menu.add_command(label="Thème sombre", command=lambda: set_appearance("dark"))
    menu.add_separator()
    menu.add_command(label="Verrouiller" if not locked else "Déverrouiller",
                     command=toggle_lock)
    menu.add_command(label="Recentrer sur l'écran principal", command=recenter_primary)
    menu.add_separator()
    menu.add_command(label="Quitter", command=on_close)


def show_menu(e):
    menu.post(e.x_root, e.y_root)


# ---------- demarrage ----------
SCHEMES = read_panel_schemes()
fit_grid(len(SCHEMES))
load_thumbs()
cur = match_theme(read_panel_theme_key() if PANEL_DIR else "1", SCHEMES)
SELECTION = SCHEMES.index(cur) if cur else None
sp = saved_pos()
pw0, ph0 = primary_size()
if sp and 0 <= sp[0] < pw0 and 0 <= sp[1] < ph0:
    POS[:] = list(sp)          # position sauvegardee sur l'ecran principal
else:
    center_on_primary()        # vieille position (petit ecran) -> ignorer
if POS[1] + H * SCALE > ph0 - 8:
    POS[1] = max(0, ph0 - 8 - H * SCALE)
if POS[0] + W * SCALE > pw0 - 8:
    POS[0] = max(0, pw0 - 8 - W * SCALE)
root.geometry("%dx%d+%d+%d" % (W * SCALE, H * SCALE, POS[0], POS[1]))
if topmost:
    root.attributes("-topmost", True)
if locked:
    root.overrideredirect(True)

cv.bind("<Button-1>", on_press)
cv.bind("<B1-Motion>", on_move)
cv.bind("<ButtonRelease-1>", on_release)
cv.bind("<Motion>", on_motion)
cv.bind("<Leave>", on_leave)
cv.bind("<Button-3>", show_menu)
root.bind("<Button-3>", show_menu)
root.bind("<Alt-F4>", lambda e: on_close())
root.bind("<Up>", on_key)
root.bind("<Down>", on_key)
root.bind("<Return>", on_key)
root.bind("<Escape>", on_key)
root.protocol("WM_DELETE_WINDOW", on_close)

build_menu()
render()
poll()
_exec.submit(follow_bright)
root.mainloop()
