"""Centre de controle SensorPanel — fenetre sur l'ECRAN PRINCIPAL.
Liste les themes de sensor_panel.py (lus dans le fichier, jamais desynchronise).
Ecrit `theme = N` dans config.ini du panel (commentaires conserves), lance /
relance / arrete le panel. Le panel demarre toujours en admin (temp CPU Ryzen).

Apparence : theme sombre ou clair (centre.ini > appearance), bascule dans la
barre de titre. Echelle x1/x2. Position persistee (x/y) ; sinon centre de
l'ecran principal. Menu Options : demarrage, vitesse, moniteur et centre.
"""
import configparser
import ctypes
from ctypes import wintypes
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass
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
if FROZEN and (sys.stdout is None or sys.stderr is None):
    class _Quiet(object):
        def write(self, *_a):
            pass

        def flush(self):
            pass
    if sys.stdout is None:
        sys.stdout = _Quiet()
    if sys.stderr is None:
        sys.stderr = _Quiet()

APPDIR = os.path.dirname(os.path.abspath(sys.executable if FROZEN else __file__))
CFG_PATH = os.path.join(APPDIR, "centre.ini")
# Grille 3×4 : aperçus 480×320 réduits d'un facteur 3 (160×107). Le reste est paginé.
PAD, GAP, COLS, ROWS = 8, 8, 3, 4
THUMB_W, THUMB_H = 160, 107
PANEL_W, PANEL_H = 480, 320
GRID_Y0 = 70               # sous la rangée de luminosité
PAGE = COLS * ROWS
PAGER_Y = GRID_Y0 + ROWS * THUMB_H + (ROWS - 1) * GAP + 8
PAGER_H = 32
W = PAD + COLS * THUMB_W + (COLS - 1) * GAP + PAD
FOOT_Y = PAGER_Y + PAGER_H + 8
H = FOOT_Y + 62


def fit_grid(n=None):
    """La grille reste 3×4. n est ignoré : les thèmes au-delà passent à la page suivante."""
    global FOOT_Y, H
    FOOT_Y = PAGER_Y + PAGER_H + 8
    H = FOOT_Y + 62
VERSION = "1.1.0"
SPEEDS = (
    ("high", "Élevé", 500),
    ("normal", "Normal", 1000),
    ("low", "Faible", 4000),
    ("paused", "En pause", 0),
)
PANEL_EXE = "Moniteur.exe"
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

_exec = futures.ThreadPoolExecutor(max_workers=4)

# ---------- ctypes Windows (64-bit safe) ----------
_user32 = ctypes.windll.user32
_shell32 = ctypes.windll.shell32
_kernel32 = ctypes.windll.kernel32
_user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
_user32.FindWindowW.restype = wintypes.HWND
_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.ShowWindow.restype = wintypes.BOOL
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.SetForegroundWindow.restype = wintypes.BOOL
_shell32.ShellExecuteW.argtypes = [
    wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR,
    wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_int]
_shell32.ShellExecuteW.restype = ctypes.c_void_p

# ---------- un seul exemplaire du centre ----------
# Double-clic supplementaire sur l'exe : remet la fenetre existante au premier
# plan et ferme la 2e instance au lieu d'en ouvrir 10.
_hmutex = _kernel32.CreateMutexW(None, False, "CentreControleSingleInstance")
if ctypes.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
    hwnd = _user32.FindWindowW(None, "Centre de controle")
    try:
        if hwnd:
            _user32.ShowWindow(hwnd, 9)      # SW_RESTORE
            _user32.SetForegroundWindow(hwnd)
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


def save_cfg(set_locked=None, new_topmost=None, new_admin=None, new_mini=None,
             new_scale=None, new_appearance=None):
    global locked, topmost, admin_on, mini, SCALE, appearance
    if set_locked is not None:
        locked = set_locked
    if new_topmost is not None:
        topmost = new_topmost
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
        try:
            if root.winfo_ismapped() and root.state() == "normal":
                rx, ry = root.winfo_x(), root.winfo_y()
                if rx > -10000 and ry > -10000:
                    cfg.set("centre", "x", str(rx))
                    cfg.set("centre", "y", str(ry))
        except Exception:
            pass
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
_panel_running_cache = False


def panel_cfg_path():
    return os.path.join(PANEL_DIR, PANEL_CFG_NAME) if PANEL_DIR else None


def read_panel_schemes():
    """[{i,key,desc}] : les themes, lus dans sensor_panel.py (name= / desc=)."""
    out = []
    src = os.path.join(PANEL_DIR or "", PANEL_PY)
    try:
        with open(src, encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return out
    for m in re.finditer(r'name\s*=\s*"([^"]+)"\s*\r?\n\s*desc\s*=\s*"([^"]+)"', txt):
        g = re.match(r"(\d+)", m.group(1))
        if g:
            out.append(dict(i=int(g.group(1)), key=m.group(1), desc=m.group(2)))
    return out


def read_panel_theme_key():
    pt = panel_cfg_path()
    if not pt:
        return "1"
    try:
        with open(pt, encoding="utf-8") as f:
            txt = f.read()
        m = re.search(r"(?m)^\s*theme\s*=\s*([^\s#;]+)", txt)
        if m:
            return m.group(1)
    except Exception:
        pass
    return "1"


def read_panel_bool(name, default=True):
    pt = panel_cfg_path()
    if not pt:
        return default
    try:
        c = configparser.ConfigParser()
        c.read(pt, encoding="utf-8")
        return c.getboolean("panel", name, fallback=default)
    except Exception:
        return default


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


def _set_ini_line(txt, name, value):
    new, n = re.subn(r"(?m)^(\s*" + re.escape(name) + r"\s*=\s*).*$",
                     lambda m: m.group(1) + value, txt, count=1)
    if n:
        return new
    m = re.search(r"(?m)^\[panel\]\s*$", txt)
    if m:
        pos = m.end()
        return txt[:pos] + "\n" + name + " = " + value + txt[pos:]
    sep = "\n" if txt and not txt.endswith("\n") else ""
    return txt + sep + "[panel]\n" + name + " = " + value + "\n"


def write_panel_ini(pairs):
    """Met a jour une ou plusieurs cles [panel] dans config.ini (commentaires preserves)."""
    pt = panel_cfg_path()
    if not pt:
        return False
    try:
        txt = ""
        if os.path.isfile(pt):
            with open(pt, encoding="utf-8") as f:
                txt = f.read()
        for k, v in pairs.items():
            txt = _set_ini_line(txt, k, str(v))
        with open(pt, "w", encoding="utf-8") as f:
            f.write(txt)
        return True
    except Exception:
        return False


def write_panel_theme(key):
    """theme=key dans config.ini du panel, commentaires preserves."""
    return write_panel_ini({"theme": key})


def read_update_speed():
    """high, normal, low ou paused. Défaut : normal."""
    pt = panel_cfg_path()
    if not pt:
        return "normal"
    try:
        with open(pt, encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return "normal"
    m = re.search(r"(?m)^\s*update_speed\s*=\s*([^\s#;]+)", txt)
    if m and m.group(1).strip().lower() in dict((k, 1) for k, _l, _v in SPEEDS):
        return m.group(1).strip().lower()
    m = re.search(r"(?m)^\s*interval_ms\s*=\s*(\d+)", txt)
    if m:
        ms = int(m.group(1))
        for key, _label, val in SPEEDS:
            if val and val == ms:
                return key
    return "normal"


def write_update_speed(key):
    """Écrit update_speed. interval_ms suit, sauf en pause."""
    ms = dict((k, v) for k, _l, v in SPEEDS).get(key)
    if ms is None:
        return False
    pairs = {"update_speed": key}
    if key != "paused":
        pairs["interval_ms"] = str(ms)
    return write_panel_ini(pairs)


def send_panel_cmd(*lines):
    """Envoie une ou plusieurs commandes live a sensor_panel.py via panel_cmd.txt."""
    if not PANEL_DIR:
        return False
    p = os.path.join(PANEL_DIR, "panel_cmd.txt")
    try:
        with open(p, "a", encoding="utf-8") as f:
            for ln in lines:
                f.write(str(ln).strip() + "\n")
        return True
    except Exception:
        return False


def panel_problem():
    try:
        if not PANEL_DIR:
            return "dossier panel introuvable (centre.ini > [panel] path)"
        if not (os.path.isfile(os.path.join(PANEL_DIR, PANEL_EXE)) or
                os.path.isfile(os.path.join(PANEL_DIR, PANEL_PY))):
            return "Moniteur.exe absent dans " + PANEL_DIR
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
    global _panel_running_cache
    if not HAVE_PSUTIL:
        _panel_running_cache = False
        return []
    out = []
    try:
        for p in psutil.process_iter(["pid", "name"]):
            info = p.info or {}
            nl = (info.get("name") or "").lower()
            if nl in ("moniteur.exe", "sensor_panel.exe"):
                out.append(p)
                continue
            if nl.startswith("python"):
                try:
                    cl = " ".join(p.cmdline() or []).lower()
                except Exception:
                    cl = ""
                if "sensor_panel.py" in cl and "centre_controle" not in cl:
                    out.append(p)
    except Exception:
        pass
    _panel_running_cache = bool(out)
    return out


def stop_panel_async(done=None):
    """Demande un arret propre via panel_cmd.txt + terminate/kill en secours."""
    procs = panel_running()
    if procs:
        send_panel_cmd("quit")
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass

    def work():
        for _ in range(8):
            time.sleep(0.25)
            if not panel_running():
                break
        rem = panel_running()
        for p in rem:
            try:
                p.kill()
            except Exception:
                pass
        if rem:
            time.sleep(0.2)
        still = bool(panel_running())
        if done:
            try:
                root.after(0, lambda ok=(not still): done(ok))
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
        return False, "Moniteur.exe introuvable"
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
    rc = _shell32.ShellExecuteW(None, "runas", script, None, tmp, 0)
    if int(rc or 0) <= 32:
        return False, "action refusée"
    ok = False
    for _ in range(40):
        time.sleep(0.25)
        if panel_startup_enabled() == bool(enabled):
            ok = True
            break
    for p in (script, log):
        try:
            if os.path.isfile(p):
                os.remove(p)
        except Exception:
            pass
    return (True, None) if ok else (False, "échec")


def launch_panel(admin, target):
    file, params = target
    try:
        if admin:
            r = _shell32.ShellExecuteW(None, "runas", file, params, PANEL_DIR, 1)
            if int(r or 0) <= 32:
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
page = 0
preview_key = None          # thème affiché sur le panel, pas encore enregistré
flash = None
last_launch = 0.0
drag = {"moving": False, "dx": 0, "dy": 0}   # deplacement via la barre de titre

root = tk.Tk()
root.withdraw()
root.title("Centre de controle")
_icon = os.path.join(APPDIR, "ico.ico")
if os.path.isfile(_icon):
    try:
        root.iconbitmap(_icon)
    except Exception:
        pass
root.resizable(False, False)
root.configure(bg=C["bg"])
fit_grid(len(read_panel_schemes()))

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


_AA = {}


def _hex(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def _in_round(px, py, w, h, r):
    if w <= 0 or h <= 0:
        return False
    rr = min(r, w / 2.0, h / 2.0)
    dx = abs(px - w / 2.0) - (w / 2.0 - rr)
    dy = abs(py - h / 2.0) - (h / 2.0 - rr)
    if dx > 0 and dy > 0:
        return dx * dx + dy * dy <= rr * rr
    return dx <= rr and dy <= rr


def _aa_chip(w, h, r, fill, outline, stroke, backdrop):
    """Puce antialiasée, composée sur la couleur du fond."""
    key = (w, h, r, fill, outline, stroke, backdrop)
    img = _AA.get(key)
    if img is not None:
        return img
    ss = 4
    n = ss * ss
    fc, oc, bc = _hex(fill), _hex(outline), _hex(backdrop)
    iw, ih, ir = w - 2 * stroke, h - 2 * stroke, max(0, r - stroke)
    rows = []
    for y in range(h):
        cells = []
        for x in range(w):
            nf = no = 0
            for sy in range(ss):
                for sx in range(ss):
                    px = x + (sx + 0.5) / ss
                    py = y + (sy + 0.5) / ss
                    if not _in_round(px, py, w, h, r):
                        continue
                    if stroke and _in_round(px - stroke, py - stroke, iw, ih, ir):
                        nf += 1
                    else:
                        no += 1
            nb = n - nf - no
            cells.append("#%02x%02x%02x" % tuple(
                (fc[i] * nf + oc[i] * no + bc[i] * nb + n // 2) // n
                for i in range(3)))
        rows.append("{" + " ".join(cells) + "}")
    img = tk.PhotoImage(width=w, height=h)
    img.put(" ".join(rows))
    _AA[key] = img
    return img


def round_rect(x1, y1, x2, y2, r=5, **kw):
    """Rectangle à coins lissés, composé sur le fond réel du bouton."""
    x1, y1, x2, y2 = X(x1), X(y1), X(x2), X(y2)
    w, h = x2 - x1, y2 - y1
    rad = int(min(X(r), max(0, w // 2), max(0, h // 2)))
    fill = kw.get("fill") or C["bg"]
    outline = kw.get("outline") or fill
    stroke = int(kw.get("width") or 0)
    backdrop = kw.get("backdrop") or C["bg"]
    if w < 2 or h < 2 or rad < 2:
        return cv.create_rectangle(x1, y1, x2, y2, fill=fill, outline=outline, width=stroke)
    img = _aa_chip(w, h, rad, fill, outline, stroke, backdrop)
    return cv.create_image(x1, y1, image=img, anchor="nw")


def chip(store, key, x1, y1, x2, y2, label, kind="ghost", fg=None, size=8, backdrop=None):
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
    round_rect(x1, y1, x2, y2, 6, fill=fill, outline=ol, width=1, backdrop=backdrop or C["bg"])
    return cv.create_text(X((x1 + x2) / 2), X((y1 + y2) / 2), text=label,
                          fill=fg or col, font=fnt(size, True))


class _MON_RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


class _PHYSICAL_MONITOR(ctypes.Structure):
    _fields_ = [("hPhysicalMonitor", wintypes.HANDLE),
                ("szPhysicalMonitorDescription", wintypes.WCHAR * 128)]


_MON_CB_T = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
    ctypes.POINTER(_MON_RECT), wintypes.LPARAM)

_dxva2 = ctypes.windll.dxva2
_dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [
    wintypes.HMONITOR, ctypes.POINTER(wintypes.DWORD)]
_dxva2.GetPhysicalMonitorsFromHMONITOR.argtypes = [
    wintypes.HMONITOR, wintypes.DWORD, ctypes.POINTER(_PHYSICAL_MONITOR)]
_dxva2.DestroyPhysicalMonitors.argtypes = [
    wintypes.DWORD, ctypes.POINTER(_PHYSICAL_MONITOR)]
_dxva2.GetVCPFeatureAndVCPFeatureReply.argtypes = [
    wintypes.HANDLE, wintypes.BYTE,
    ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(wintypes.DWORD)]
_dxva2.GetVCPFeatureAndVCPFeatureReply.restype = wintypes.BOOL
_dxva2.SetMonitorBrightness.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_dxva2.SetMonitorBrightness.restype = wintypes.BOOL
_dxva2.SetVCPFeature.argtypes = [
    wintypes.HANDLE, wintypes.BYTE, wintypes.DWORD]
_dxva2.SetVCPFeature.restype = wintypes.BOOL


def all_monitors():
    """Retourne [(hmon, x, y, w, h)] pour chaque moniteur."""
    found = []

    def cb(hmon, hdc, rect, data):
        r = rect.contents
        found.append((hmon, r.left, r.top, r.right - r.left, r.bottom - r.top))
        return True

    cb_ref = _MON_CB_T(cb)
    _user32.EnumDisplayMonitors(None, None, cb_ref, 0)
    return found


def _small_monitor(fn):
    """Appelle fn(dxva2, handle) sur l'écran 480×320. None si absent."""
    for hmon, _x, _y, w, h in all_monitors():
        if (w, h) != (PANEL_W, PANEL_H):
            continue
        n = wintypes.DWORD()
        if not _dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(hmon, ctypes.byref(n)) or not n.value:
            return None
        arr = (_PHYSICAL_MONITOR * n.value)()
        if not _dxva2.GetPhysicalMonitorsFromHMONITOR(hmon, n.value, arr):
            return None
        try:
            return fn(_dxva2, arr[0].hPhysicalMonitor)
        finally:
            _dxva2.DestroyPhysicalMonitors(n.value, arr)
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
            match_i = None
            for i, v in enumerate(BRIGHT_LEVELS):
                if v == pct:
                    match_i = i
                    break
            if match_i is None:
                best_i = min(range(len(BRIGHT_LEVELS)),
                             key=lambda i: abs(BRIGHT_LEVELS[i] - pct))
                if abs(BRIGHT_LEVELS[best_i] - pct) <= 2:
                    match_i = best_i
            if match_i is not None and bright_sel != match_i:
                bright_sel = match_i
                if not mini:
                    paint()
        try:
            root.after(400, lambda: _exec.submit(follow_bright))
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
    chip(HDR, "options", 8, 6, 104, 28, "Options", backdrop=C["header"])
    # paire Clair / Sombre : la pastille pleine est le theme actif
    chip(HDR, "theme_light", W - 156, 6, W - 84, 28, "Clair",
         "solid" if appearance == "light" else "ghost",
         fg=None if appearance == "light" else C["mut"], backdrop=C["header"])
    chip(HDR, "theme_dark", W - 80, 6, W - 8, 28, "Sombre",
         "solid" if appearance == "dark" else "ghost",
         fg=None if appearance == "dark" else C["mut"], backdrop=C["header"])


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


def page_count():
    return max(1, (len(SCHEMES) + PAGE - 1) // PAGE)


def cell_geom(slot):
    """slot : position dans la page, 0..11."""
    c, r = slot % COLS, slot // COLS
    x1 = PAD + c * (THUMB_W + GAP)
    y1 = GRID_Y0 + r * (THUMB_H + GAP)
    return (x1, y1, x1 + THUMB_W, y1 + THUMB_H)


def cell_at(lx, ly):
    start = page * PAGE
    for slot in range(PAGE):
        idx = start + slot
        if idx >= len(SCHEMES):
            break
        if hit(lx, ly, cell_geom(slot)):
            return idx
    return None


def draw_rows():
    if not SCHEMES:
        cv.create_text(X(W // 2), X(GRID_Y0 + 80),
                       text="Aucun thème lu : sensor_panel.py introuvable\n"
                            "Règle [panel] path dans centre.ini",
                       fill=C["warn"], font=fnt(9), justify="center")
        return
    start = page * PAGE
    for slot, s in enumerate(SCHEMES[start:start + PAGE]):
        idx = start + slot
        x1, y1, x2, y2 = cell_geom(slot)
        sel = (idx == SELECTION)
        hot = (not sel) and HOVER["row"] == idx
        img = THUMBS[idx] if idx < len(THUMBS) else None
        if img is not None:
            cv.create_image(X((x1 + x2) / 2), X((y1 + y2) / 2), image=img)
        else:
            cv.create_rectangle(X(x1), X(y1), X(x2), X(y2), fill=C["card"], outline="")
            cv.create_text(X((x1 + x2) / 2), X((y1 + y2) / 2), text=s["key"],
                           fill=C["txt"], font=fnt(9, True))
        if sel:
            ol, wd = C["accent"], 3
        elif hot:
            ol, wd = C["txt"], 2
        else:
            ol, wd = C["line"], 1
        cv.create_rectangle(X(x1) + 1, X(y1) + 1, X(x2) - 1, X(y2) - 1,
                            outline=ol, width=wd)


def draw_pager():
    y1, y2 = PAGER_Y, PAGER_Y + PAGER_H
    n = page_count()
    for key, x1, x2, label, enabled in (
            ("page_prev", 8, 168, "Précédent", page > 0),
            ("page_next", W - 168, W - 8, "Suivant", page < n - 1)):
        if enabled:
            chip(BTN, key, x1, y1, x2, y2, label, size=9, backdrop=C["bg"])
        else:
            round_rect(x1, y1, x2, y2, 6, fill=C["btn"], outline=C["line"],
                       width=1, backdrop=C["bg"])
            cv.create_text(X((x1 + x2) / 2), X((y1 + y2) / 2), text=label,
                           fill=C["mut"], font=fnt(9, True))
    cv.create_text(X(W // 2), X((y1 + y2) / 2), text="%d / %d" % (page + 1, n),
                   fill=C["txt"], font=fnt(9, True))


def draw_footer():
    cv.create_rectangle(0, X(FOOT_Y), X(W), X(H), fill=C["footer"], outline="")
    cv.create_rectangle(0, X(FOOT_Y), X(W), X(FOOT_Y) + 1, fill=C["line"], outline="")
    sy = FOOT_Y + 12
    st["dot"] = cv.create_oval(X(14), X(sy - 4), X(22), X(sy + 4),
                               fill=C["dot_off"], outline="")
    st["text"] = cv.create_text(X(28), X(sy), anchor="w", text="·",
                                fill=C["mut"], font=fnt(8))
    by1, by2 = FOOT_Y + 22, FOOT_Y + 54
    chip(BTN, "stop", 8, by1, 150, by2, "Arrêter", size=9, backdrop=C["footer"])
    chip(BTN, "run", 156, by1, W - 156, by2, "Appliquer", "solid", size=9, backdrop=C["footer"])
    chip(BTN, "quit", W - 150, by1, W - 8, by2, "Quitter", fg=C["warn"], size=9, backdrop=C["footer"])
    cv.create_text(X(W - 12), X(sy), anchor="e", text="v" + VERSION,
                   fill=C["mut"], font=fnt(8))
    update_status()


def update_status():
    try:
        if not st.get("text"):
            return
        tkey = read_panel_theme_key() if PANEL_DIR else "?"
        cur = match_theme(tkey, SCHEMES)
        running = bool(_panel_running_cache)
        if flash:
            txt, role = flash
            col = C["accent"] if role == "ok" else C["warn"]
            cv.itemconfig(st["text"], text=txt, fill=col)
            cv.itemconfig(st["dot"], fill=col)
        else:
            applied = cur["key"] if cur else "?"
            if running and preview_key and preview_key != applied:
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


def _load_wav(name):
    for base in (APPDIR, PANEL_DIR):
        if not base:
            continue
        p = os.path.join(base, "assets", name)
        if os.path.isfile(p):
            try:
                with open(p, "rb") as f:
                    return f.read()
            except Exception:
                pass
    return None


_WAV_DOWN = None
_WAV_UP = None
_winmm = ctypes.windll.winmm
_winmm.PlaySoundA.argtypes = [ctypes.c_char_p, wintypes.HMODULE, wintypes.DWORD]
_winmm.PlaySoundA.restype = wintypes.BOOL


def _init_sounds():
    global _WAV_DOWN, _WAV_UP
    _WAV_DOWN = _load_wav("click_down.wav")
    _WAV_UP = _load_wav("click_up.wav")


def play_click_down():
    """Premier son au clic (enfoncement) sur Appliquer."""
    try:
        if _WAV_DOWN:
            # SND_ASYNC | SND_NODEFAULT | SND_MEMORY = 0x0007
            _winmm.PlaySoundA(_WAV_DOWN, None, 0x0007)
    except Exception:
        pass


def play_apply_sound():
    """Second son au relachement quand Appliquer a enregistré le thème."""
    try:
        if _WAV_UP:
            _winmm.PlaySoundA(_WAV_UP, None, 0x0007)
        elif os.path.isfile(APPLY_WAV):
            # SND_ASYNC | SND_NODEFAULT | SND_FILENAME
            _winmm.PlaySoundW(APPLY_WAV, None, 0x00020003)
    except Exception:
        pass


_flash_seq = 0


def show_flash(txt, color="warn", delay=3200):
    """color : 'ok' ou 'warn' (resolu dans la palette au moment du dessin)."""
    global flash, _flash_seq
    role = "ok" if color == "ok" else "warn"
    if os.environ.get("CTRACE"):
        print("[flash]", txt, flush=True)
    flash = (txt, role)
    _flash_seq += 1
    seq = _flash_seq
    update_status()

    def clear():
        if _flash_seq == seq:
            globals()["flash"] = None
            update_status()
    try:
        root.after(delay, clear)
    except Exception:
        pass


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
        draw_pager()
        draw_footer()
    cv.create_rectangle(1, 1, X(W) - 1, hpx - 1, outline=C["line"], width=1)
    draw_options()


def render():
    hpx = (TITLE_H if mini else H) * SCALE
    cv.configure(width=X(W), height=hpx, bg=C["bg"])
    root.configure(bg=C["bg"])
    if root.winfo_width() != X(W) or root.winfo_height() != hpx:
        root.geometry("%dx%d" % (X(W), hpx))
    paint()


# ---------- actions ----------
def act(key, autohide=True):
    global last_launch, preview_key, _panel_running_cache
    if key == "quit":
        on_close()
        return
    if key in ("page_prev", "page_next"):
        turn_page(-1 if key == "page_prev" else 1)
        return
    if key == "stop":
        preview_key = None

        def _stopped(ok):
            show_flash("panel arrêté" if ok else "arrêt refusé (droits admin)",
                       "ok" if ok else "warn")

        n = stop_panel_async(_stopped)
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
            _panel_running_cache = True
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
            preview_key = None
            show_flash("sélection · " + sel["key"], "ok")
            return
        last_launch = time.time()
        target = panel_launch_target() or (None, None)
        running = panel_running()
        if running:
            send_panel_cmd("quit")
            for p in running:
                try:
                    p.terminate()
                except Exception:
                    pass
            show_flash("relance · thème " + sel["key"] + " ...", "ok")

            def delayed(target=target, sel=sel):
                for _ in range(6):
                    time.sleep(0.25)
                    if not panel_running():
                        break
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
    global preview_key, _panel_running_cache
    ok, err = launch_panel(True, target)
    if ok:
        preview_key = None
        _panel_running_cache = True
        play_apply_sound()
        show_flash("thème appliqué · " + sel["key"], "ok")
    else:
        show_flash("⚠ lancement impossible : " + (err or ""), "warn")


def preview_theme(sel):
    """Affiche le thème sur le panel. config.ini n'est pas modifié."""
    global preview_key, last_launch, _panel_running_cache
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
        try:
            os.remove(cmdp)
        except Exception:
            pass
        show_flash("⚠ lancement impossible", "warn")
        return
    ok, err = launch_panel(True, target)
    if ok:
        _panel_running_cache = True
        show_flash("prévisualisation · " + sel["key"], "ok")
    else:
        try:
            os.remove(cmdp)
        except Exception:
            pass
        show_flash("⚠ " + (err or "lancement impossible"), "warn")


def revert_preview():
    """Ferme le centre : le panel revient au thème enregistré dans config.ini."""
    if not preview_key or not PANEL_DIR:
        return
    cmdp = os.path.join(PANEL_DIR, "theme_cmd.txt")
    if not panel_running():
        try:
            if os.path.isfile(cmdp):
                os.remove(cmdp)
        except Exception:
            pass
        return
    applied = match_theme(read_panel_theme_key(), SCHEMES)
    key = applied["key"] if applied else None
    if not key or key == preview_key:
        return
    try:
        with open(cmdp, "w", encoding="utf-8") as f:
            f.write(key)
    except Exception:
        pass


def on_close():
    revert_preview()
    save_cfg()
    try:
        _exec.shutdown(wait=False, cancel_futures=True)
    except Exception:
        pass
    try:
        if _hmutex:
            _kernel32.CloseHandle(_hmutex)
    except Exception:
        pass
    try:
        root.destroy()
    except Exception:
        pass
    os._exit(0)


# ---------- events ----------
def hit(x, y, r):
    return r[0] <= x <= r[2] and r[1] <= y <= r[3]


_pressed = None


def _hit_target(lx, ly):
    """Retourne le tuple cible sous (lx, ly) ou None."""
    if opt_open and not mini and hit(lx, ly, opt_box):
        for key, rect in opt_rects.items():
            if hit(lx, ly, rect):
                return ("opt", key)
        return ("opt_bg", None)
    if ly <= TITLE_H:
        if mini:
            return ("mini", None)
        for k, rect in HDR.items():
            if hit(lx, ly, rect):
                return ("hdr", k)
        return None
    if mini:
        return None
    for k, rect in BRIGHT.items():
        if hit(lx, ly, rect):
            return ("bright", int(k[1:]))
    i = cell_at(lx, ly)
    if i is not None:
        return ("cell", i)
    for k, rect in BTN.items():
        if hit(lx, ly, rect):
            return ("btn", k)
    return None


def on_press(e):
    """Coord logiques : memorise la cible pressee (action executee au relachement)."""
    global _pressed
    lx, ly = e.x / SCALE, e.y / SCALE
    tgt = _hit_target(lx, ly)
    on_opt_area = tgt is not None and tgt[0] in ("opt", "opt_bg")
    on_opt_btn = tgt == ("hdr", "options")
    if opt_open and not on_opt_area and not on_opt_btn:
        close_options()
        _pressed = tgt if (tgt is not None and tgt[0] == "hdr") else None
        return
    if tgt is None and not mini and ly <= TITLE_H and locked and lx < W - 156:
        drag["moving"] = True              # sans barre Windows, le titre déplace
        drag["dx"], drag["dy"] = e.x, e.y
        _pressed = None
        return
    _pressed = tgt
    if tgt == ("btn", "run"):
        play_click_down()


def on_motion(e):
    if drag["moving"] or mini:
        if mini:
            cv.configure(cursor="hand2")
        return
    lx, ly = e.x / SCALE, e.y / SCALE
    if opt_open and not mini and hit(lx, ly, opt_box):
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
    render()


def turn_page(delta):
    global page
    nxt = max(0, min(page_count() - 1, page + delta))
    if nxt == page:
        return
    page = nxt
    render()


def on_key(e):
    if e.keysym == "Escape" and opt_open:
        close_options()
        return
    if SCHEMES and e.keysym in ("Left", "Right", "Up", "Down"):
        cur = SELECTION if SELECTION is not None else 0
        delta = {"Left": -1, "Right": 1, "Up": -COLS, "Down": COLS}[e.keysym]
        idx = int(max(0, min(len(SCHEMES) - 1, cur + delta)))
        globals()["SELECTION"] = idx
        globals()["page"] = idx // PAGE
        render()
    elif e.keysym in ("Return", "KP_Enter"):
        act("run")


def on_move(e):
    """Drag de la barre de titre : redeplace la fenetre (n'importe quel ecran)."""
    if drag["moving"]:
        root.geometry("+%d+%d" % (e.x_root - drag["dx"], e.y_root - drag["dy"]))
        POS[:] = [root.winfo_x(), root.winfo_y()]


def on_release(e):
    global _pressed
    if drag["moving"]:
        drag["moving"] = False
        _pressed = None
        save_cfg()                            # memorise la nouvelle position
        return
    pressed = _pressed
    _pressed = None
    if not pressed:
        return
    lx, ly = e.x / SCALE, e.y / SCALE
    if _hit_target(lx, ly) != pressed:
        return
    kind, val = pressed
    if kind == "opt":
        if val == "toggle":
            toggle_startup()
        elif val == "close":
            close_options()
        elif val.startswith("speed_"):
            set_update_speed(val[6:])
        elif val == "mon_center_small":
            recenter_monitor()
        elif val == "mon_lock":
            toggle_panel_lock()
        elif val == "mon_topmost":
            toggle_panel_topmost()
    elif kind == "mini":
        toggle_mini()
    elif kind == "hdr":
        if val == "options":
            show_options(e)
        elif val == "theme_light":
            set_appearance("light")
        elif val == "theme_dark":
            set_appearance("dark")
    elif kind == "bright":
        set_bright(val)
    elif kind == "cell":
        globals()["SELECTION"] = val
        render()
        preview_theme(SCHEMES[val])
    elif kind == "btn":
        act(val)


def toggle_mini():
    close_options()
    save_cfg(new_mini=not mini)
    render()


def poll():
    def work():
        panel_running()

        def done():
            if not flash:
                update_status()
            try:
                root.after(2500, poll)
            except Exception:
                pass
        try:
            root.after(0, done)
        except Exception:
            pass
    _exec.submit(work)


def recenter_monitor():
    """Recentre la fenetre du Moniteur sur le petit ecran (config.ini + commande live)."""
    if not PANEL_DIR:
        show_flash("⚠ dossier panel introuvable", "warn")
        return
    mons = all_monitors()
    exact = [m for m in mons if (m[3], m[4]) == (PANEL_W, PANEL_H)]
    if exact:
        _hmon, mx, my, mw, mh = exact[0]
        msg = "moniteur recentré (petit écran)"
    elif mons:
        _hmon, mx, my, mw, mh = min(mons, key=lambda m: m[3] * m[4])
        msg = ("moniteur recentré (plus petit écran)"
               if len(mons) > 1 else "moniteur recentré (écran principal)")
    else:
        pw, ph = primary_size()
        mx, my, mw, mh = 0, 0, pw, ph
        msg = "moniteur recentré (écran principal)"
    tx = mx + (mw - PANEL_W) // 2
    ty = my + (mh - PANEL_H) // 2
    if not write_panel_ini({"x": str(tx), "y": str(ty)}):
        show_flash("⚠ écriture config.ini refusée", "warn")
        return
    send_panel_cmd("pos %d %d" % (tx, ty))
    show_flash(msg, "ok")
    paint()


def toggle_panel_lock():
    if not PANEL_DIR:
        show_flash("⚠ dossier panel introuvable", "warn")
        return
    want = not opt_state.get("panel_locked", True)
    if not write_panel_ini({"locked": str(want).lower()}):
        show_flash("⚠ écriture config.ini refusée", "warn")
        return
    opt_state["panel_locked"] = want
    send_panel_cmd("lock " + ("1" if want else "0"))
    show_flash("moniteur verrouillé" if want else "moniteur déverrouillé", "ok")
    paint()


def toggle_panel_topmost():
    if not PANEL_DIR:
        show_flash("⚠ dossier panel introuvable", "warn")
        return
    want = not opt_state.get("panel_topmost", True)
    if not write_panel_ini({"topmost": str(want).lower()}):
        show_flash("⚠ écriture config.ini refusée", "warn")
        return
    opt_state["panel_topmost"] = want
    send_panel_cmd("topmost " + ("1" if want else "0"))
    show_flash("moniteur au premier plan" if want else "moniteur normal", "ok")
    paint()


opt_open = False
opt_box = (0, 0, 0, 0)
opt_rects = {}
opt_hover = None
opt_state = {
    "on": False,
    "busy": False,
    "speed": "normal",
    "panel_locked": True,
    "panel_topmost": True,
}


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
    opt_state["speed"] = read_update_speed()
    opt_state["panel_locked"] = read_panel_bool("locked", True)
    opt_state["panel_topmost"] = read_panel_bool("topmost", True)
    opt_open = True
    paint()

    def refresh_startup():
        on = panel_startup_enabled()

        def done():
            if opt_open and opt_state["on"] != on:
                opt_state["on"] = on
                paint()
            else:
                opt_state["on"] = on
        try:
            root.after(0, done)
        except Exception:
            pass
    _exec.submit(refresh_startup)


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


def set_update_speed(key):
    if key == opt_state.get("speed"):
        return
    if not write_update_speed(key):
        show_flash("écriture config.ini refusée", "warn")
        return
    opt_state["speed"] = key
    names = {"high": "élevé", "normal": "normal", "low": "faible", "paused": "en pause"}
    show_flash("mise à jour · " + names.get(key, key), "ok")
    paint()


def _opt_chip(key, x1, y1, x2, y2, label, kind="ghost", fg=None, size=8, disabled=False):
    opt_rects[key] = (x1, y1, x2, y2)
    hot = (opt_hover == key) and not disabled
    if kind == "solid":
        fill, col, ol = C["accent"], C["on_accent"], C["accent"]
    elif hot:
        fill, col, ol = C["btn_hover"], C["txt"], C["btn_line"]
    else:
        fill, col, ol = C["btn"], C["txt"], C["btn_line"]
    round_rect(x1, y1, x2, y2, 6, fill=fill, outline=ol, width=1,
               backdrop=C["header"])
    cv.create_text(X((x1 + x2) / 2), X((y1 + y2) / 2), text=label,
                   fill=fg or col, font=fnt(size, True))


def draw_options():
    """Colle le panneau sous le bouton Options, dans le canvas du centre."""
    global opt_box
    if not opt_open or mini:
        return
    ox, oy = 8, 36
    ow, oh = W - 16, 218
    ix, rx = ox + 12, ox + ow - 12
    opt_box = (ox, oy, ox + ow, oy + oh)
    opt_rects.clear()
    cv.create_rectangle(X(ox), X(oy), X(ox + ow), X(oy + oh),
                        fill=C["header"], outline="")

    # Entête
    cv.create_text(X(ix), X(oy + 21), anchor="w", text="Options",
                   fill=C["txt"], font=fnt(10, True))
    _opt_chip("close", rx - 74, oy + 9, rx, oy + 33, "Fermer", "ghost", size=8)
    cv.create_line(X(ox + 1), X(oy + 40), X(ox + ow - 1), X(oy + 40), fill=C["line"])

    # Section 1 : Démarrage Windows
    cv.create_text(X(ix), X(oy + 56), anchor="w",
                   text="Lancer le moniteur au démarrage",
                   fill=C["txt"], font=fnt(8, True))
    cv.create_text(X(ix), X(oy + 72), anchor="w",
                   text="Activé" if opt_state["on"] else "Désactivé",
                   fill=C["accent"] if opt_state["on"] else C["mut"],
                   font=fnt(8))
    _opt_chip("toggle", rx - 104, oy + 50, rx, oy + 76,
              "Désactiver" if opt_state["on"] else "Activer",
              "solid" if opt_state["on"] else "ghost",
              size=8, disabled=opt_state["busy"])
    cv.create_line(X(ix), X(oy + 86), X(rx), X(oy + 86), fill=C["line"])

    # Section 2 : Vitesse de mise à jour
    cv.create_text(X(ix), X(oy + 102), anchor="w",
                   text="Vitesse de mise à jour",
                   fill=C["txt"], font=fnt(9, True))
    bw, gap = 112, 8
    x = ix
    sy1, sy2 = oy + 116, oy + 142
    current = opt_state.get("speed") or "normal"
    for key, label, _ms in SPEEDS:
        x2 = x + bw
        _opt_chip("speed_" + key, x, sy1, x2, sy2, label,
                  "solid" if current == key else "ghost", size=8)
        x = x2 + gap
    cv.create_line(X(ix), X(oy + 150), X(rx), X(oy + 150), fill=C["line"])

    # Section 3 : Moniteur (480x320)
    cv.create_text(X(ix), X(oy + 166), anchor="w",
                   text="Moniteur (480×320)",
                   fill=C["txt"], font=fnt(9, True))
    my1, my2 = oy + 180, oy + 206
    p_lock = opt_state.get("panel_locked", True)
    p_top = opt_state.get("panel_topmost", True)
    _opt_chip("mon_center_small", ix, my1, ix + 180, my2,
              "Recentrer (petit écran)", "ghost", size=8)
    _opt_chip("mon_lock", ix + 188, my1, ix + 324, my2,
              "Verrouillé" if p_lock else "Déverrouillé",
              "solid" if p_lock else "ghost", size=8)
    _opt_chip("mon_topmost", ix + 332, my1, rx, my2,
              "Toujours au-dessus",
              "solid" if p_top else "ghost", size=8)

    cv.create_rectangle(X(ox) + 1, X(oy) + 1, X(ox + ow) - 1, X(oy + oh) - 1,
                        outline=C["line"], width=1)


# ---------- demarrage ----------
SCHEMES = read_panel_schemes()
fit_grid(len(SCHEMES))
load_thumbs()
cur = match_theme(read_panel_theme_key() if PANEL_DIR else "1", SCHEMES)
SELECTION = SCHEMES.index(cur) if cur else None
if SELECTION is not None:
    page = SELECTION // PAGE
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
root.bind("<Alt-F4>", lambda e: on_close())
root.bind("<Left>", on_key)
root.bind("<Right>", on_key)
root.bind("<Up>", on_key)
root.bind("<Down>", on_key)
root.bind("<Return>", on_key)
root.bind("<KP_Enter>", on_key)
root.bind("<Escape>", on_key)
root.protocol("WM_DELETE_WINDOW", on_close)

_init_sounds()
panel_running()
render()
root.deiconify()
poll()
_exec.submit(follow_bright)
root.mainloop()
