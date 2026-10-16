"""SensorPanel 480x320 — remplacant leger d'AIDA64 SensorPanel.
9 themes d'affichage (maquettes dans ui_proposals.html), fenetre 480x320 verrouillee
pour petit moniteur. Donnees : CPU usage via psutil, temp CPU via LibreHardwareMonitor
(admin requis sur Ryzen), GPU via NVML (pynvml) avec fallback nvidia-smi puis LHM.
Choix du theme : config.ini `theme = 1..9` ou `--theme=6` en ligne de commande.
Changement a chaud : apply_theme("6") — pret a etre branche sur un menu (a la volee).
Test rapide : `python sensor_panel.py --theme=6 --selftest=4000` (auto-quit).
"""
import configparser
import ctypes
import math
import os
import re
import subprocess
import sys
import time
import tkinter as tk
import tkinter.font as tkfont
from collections import deque

try:
    import psutil as _psutil_mod
except Exception:
    _psutil_mod = None

BASE = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
CFG_PATH = os.path.join(BASE, "config.ini")
LIBS = os.path.join(BASE, "libs")
FOND = os.path.join(BASE, "assets", "Fond.png")

# PyInstaller --noconsole : sys.stdout/stderr = None => tout print() planterait
if getattr(sys, "frozen", False) and (sys.stdout is None or sys.stderr is None):
    class _Quiet(object):
        def write(self, *_a):
            pass

        def flush(self):
            pass
    if sys.stdout is None:
        sys.stdout = _Quiet()
    if sys.stderr is None:
        sys.stderr = _Quiet()

W, H = 480, 320
FONT_DIGI = "Dash Digital-7"

# ---------- etat global rempli par main() ----------
cfg = configparser.ConfigParser()
COL = {"label": "#1FE01F", "value": "#4EC221", "graph": "#56DC23",
       "graph2": "#4EC221", "grid": "#008000", "frame": "#005E00", "bg": "#000000"}
HN = 48                  # points d'historique (48 s @ 1 Hz)
locked = True
topmost = True
interval = 1000
want_cpu_temp = True

CPU_NAME = "CPU"
GPU_NAME = "GPU"
ADMIN = False
HAVE_PSUTIL = False
HAVE_NVML = False
_gpu = None
_lhm_cpu = None

root = None
cv = None
theme = None
bg_img = None
state = {}
warned_admin = False
smi_cooldown = 0


# ================= providers =================
def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def init_providers(want_temp):
    """psutil + NVML + LibreHardwareMonitor. Remplit les globals."""
    global HAVE_PSUTIL, HAVE_NVML, _gpu, GPU_NAME, _lhm_cpu, CPU_NAME
    try:
        import psutil
        psutil.cpu_percent(interval=None)  # amorce (1er appel = 0)
        HAVE_PSUTIL = True
    except Exception:
        HAVE_PSUTIL = False
    try:
        from pynvml import (nvmlDeviceGetHandleByIndex, nvmlDeviceGetName,
                            nvmlDeviceGetTemperature, nvmlDeviceGetUtilizationRates,
                            nvmlInit, NVML_TEMPERATURE_GPU)  # noqa: F401
        nvmlInit()
        _gpu = nvmlDeviceGetHandleByIndex(0)
        n = nvmlDeviceGetName(_gpu)
        GPU_NAME = n.decode() if isinstance(n, bytes) else str(n)
        HAVE_NVML = True
    except Exception:
        HAVE_NVML = False
    try:
        if want_temp and os.path.isfile(os.path.join(LIBS, "LibreHardwareMonitorLib.dll")):
            import clr
            clr.AddReference(os.path.join(LIBS, "LibreHardwareMonitorLib.dll"))
            from LibreHardwareMonitor.Hardware import Computer
            comp = Computer()
            comp.IsCpuEnabled = True
            comp.IsGpuEnabled = False
            comp.IsMemoryEnabled = False
            comp.IsMotherboardEnabled = False
            comp.IsStorageEnabled = False
            comp.IsNetworkEnabled = False
            comp.IsBatteryEnabled = False
            comp.Open()
            for hw in comp.Hardware:
                if str(hw.HardwareType) == "Cpu":
                    _lhm_cpu = hw
                    CPU_NAME = str(hw.Name)
                    break
    except Exception as e:
        print("LHM indisponible:", e)
        _lhm_cpu = None
    if CPU_NAME == "CPU":
        try:
            import platform
            CPU_NAME = platform.processor() or "CPU"
        except Exception:
            pass


def gpu_nvml():
    """Retourne (temp_c, util_%) ou (None, None)."""
    if not HAVE_NVML:
        return None, None
    try:
        from pynvml import nvmlDeviceGetTemperature, nvmlDeviceGetUtilizationRates, NVML_TEMPERATURE_GPU
        t = float(nvmlDeviceGetTemperature(_gpu, NVML_TEMPERATURE_GPU))
        u = float(nvmlDeviceGetUtilizationRates(_gpu).gpu)
        return t, u
    except Exception:
        return None, None


def gpu_smi_fallback():
    """Fallback sans pynvml : 1 appel nvidia-smi (~40ms). Utilise rarement."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,temperature.gpu,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5)
        parts = out.stdout.strip().split(",")
        return float(parts[1]), float(parts[2])
    except Exception:
        return None, None


def cpu_temp_lhm():
    """Retourne temp package ou None (0.0 = pas d'acces, generalement pas admin)."""
    if _lhm_cpu is None:
        return None
    try:
        _lhm_cpu.Update()
        best = None
        for s in _lhm_cpu.Sensors:
            if str(s.SensorType) == "Temperature" and s.Value is not None:
                v = float(s.Value)
                if v > 0.5:  # ignore les sondes a 0 = pas de droits
                    name = str(s.Name)
                    if "Tctl" in name or "Package" in name or "Core" in name:
                        return v
                    if best is None:
                        best = v
        return best
    except Exception:
        return None


def cpu_usage():
    if HAVE_PSUTIL:
        try:
            import psutil
            return float(psutil.cpu_percent(interval=None))
        except Exception:
            return 0.0
    return 0.0


# ================= position : auto-detecte le moniteur 480x320 =================
def monitors_all():
    """Retourne [(x, y, w, h)] pour chaque moniteur (coords physiques)."""
    found = []
    try:
        from ctypes import WINFUNCTYPE, c_int, c_void_p, c_double, POINTER, windll
        from ctypes.wintypes import RECT
        user32 = windll.user32
        CB = WINFUNCTYPE(c_int, c_void_p, c_void_p, POINTER(RECT), c_double)

        def cb(hmon, hdc, r, data):
            found.append((r.contents.left, r.contents.top,
                          r.contents.right - r.contents.left,
                          r.contents.bottom - r.contents.top))
            return 1
        cb_ref = CB(cb)
        user32.EnumDisplayMonitors(None, None, cb_ref, 0)
    except Exception:
        pass
    return found


def panel_xy():
    cx = cfg.get("panel", "x", fallback="").strip()
    cy = cfg.get("panel", "y", fallback="").strip()
    if cx not in ("", "None") and cy not in ("", "None"):
        try:
            return int(cx), int(cy)
        except ValueError:
            pass
    mons = monitors_all()
    if mons:
        # centre pile sur le plus petit moniteur (le 480x320 ou le 800x600).
        mx, my, mw, mh = min(mons, key=lambda m: m[2] * m[3])
        return mx + (mw - W) // 2, my + (mh - H) // 2
    return 0, 0  # defaut (mets x,y dans config.ini)


# ================= helpers canvas =================
def stext(cv_, x, y, text, font, fill, anchor="nw"):
    """Texte + ombre portee noire (+1,+1) : net sur fond texture. Retourne (ombre, texte)."""
    a = cv_.create_text(x + 1, y + 1, text=text, anchor=anchor, font=font, fill="#000000")
    b = cv_.create_text(x, y, text=text, anchor=anchor, font=font, fill=fill)
    return (a, b)


def stext_set(cv_, ids, text):
    cv_.itemconfig(ids[0], text=text)
    cv_.itemconfig(ids[1], text=text)


def temp_str(t):
    return "--.- °C" if t is None else f"{t:.1f} °C"


def pts_line(hist, x, y, w, h, vmax=100.0):
    """Historique 0..vmax -> coords canvas etirees sur toute la largeur (bord droit = valeur recente)."""
    n = len(hist)
    if n < 2:
        hist = list(hist) * 2 if hist else [0.0, 0.0]
        n = 2
    step = w / (n - 1)
    out = []
    for i, v in enumerate(hist):
        vv = min(max(v, 0.0), vmax) / vmax
        out.extend((x + i * step, y + h - vv * h))
    return out


def pts_area(hist, x, y, w, h, vmax=100.0):
    return pts_line(hist, x, y, w, h, vmax) + [x + w, y + h, x, y + h]


def pos_last(hist, x, y, w, h, vmax=100.0):
    v = hist[-1] if hist else 0.0
    vv = min(max(v, 0.0), vmax) / vmax
    return x + w, y + h - vv * h


def compass(cx, cy, r, deg):
    """Point sur un cercle : deg 0 = haut, sens horaire (ecran)."""
    rad = math.radians(deg)
    return cx + r * math.sin(rad), cy - r * math.cos(rad)


def stipple_for_op(op):
    """Approxime une opacite (0..1) par un stipple tkinter. None = invisible."""
    if op <= 0.08:
        return None
    if op >= 0.90:
        return ""
    if op >= 0.65:
        return "gray75"
    if op >= 0.40:
        return "gray50"
    return "gray25"


def seg_set(cv_, rid, color, op):
    st = stipple_for_op(op)
    if st is None:
        cv_.itemconfig(rid, fill="", stipple="")
    else:
        cv_.itemconfig(rid, fill=color, stipple=st)


# ================= themes =================
class ThemeBase:
    """Un theme construit ses items une fois (build) puis les rafraichit (update, 1 Hz)."""
    name = ""
    desc = ""

    def __init__(self, cv_, col, font_family, meta):
        self.cv = cv_
        self.C = col
        self.F = font_family
        self.cpu_name, self.gpu_name = meta
        self.build()

    def f(self, px):
        """Taille en pixels physiques (taille negative tkinter = pixels, independant du DPI)."""
        return (self.F, -max(6, int(px)))

    def _measure(self, txt, px):
        try:
            return tkfont.Font(family=self.F, size=-int(px)).measure(txt)
        except Exception:
            return 0

    def _fit_px(self, txt, px, budget):
        """Reduit la taille px jusqu'a ce que txt tienne dans budget pixels."""
        while px > 7 and self._measure(txt, px) > budget:
            px -= 1
        return px

    def T(self, x, y, txt, px, fill, anchor="nw", budget=None):
        """Texte + ombre, avec suivi d'id pour maj. budget = largeur max en px (auto-fit)."""
        if budget is not None:
            px = self._fit_px(txt, px, budget)
        return stext(self.cv, x, y, txt, self.f(px), fill, anchor)

    def short_suffix(self, name, px, budget):
        """Nom compact : garde les derniers mots qui tiennent dans budget px."""
        words = name.upper().split()
        if not words:
            return name.upper()
        out = words[-1]
        i = len(words) - 2
        while i >= 0:
            cand = words[i] + " " + out
            if self._measure(cand, px) > budget:
                break
            out = cand
            i -= 1
        return out

    def build(self):
        raise NotImplementedError

    def update(self, s):
        pass


class T01AidaPlus(ThemeBase):
    """01 · Heritage AIDA+ : layout AIDA, + grille, aire, point live, echelle."""
    name = "01-aida"
    desc = "Heritage AIDA+"

    def build(self):
        cv_, C = self.cv, self.C
        gx, gw, gh = 6, 450, 108
        self.g1, self.g2 = (gx, 44, gw, gh), (gx, 208, gw, gh)
        for (x, y, w, h) in (self.g1, self.g2):
            for i in (1, 2, 3):
                cv_.create_line(x, y + h * i / 4, x + w, y + h * i / 4, fill=C["grid"])
            cv_.create_line(x, y + h, x + w, y + h, fill=C["frame"])
        cv_.create_line(6, 168, 474, 168, fill=C["frame"])
        for yy, t in ((46, "100"), (96, "50"), (144, "0"),
                      (210, "100"), (260, "50"), (308, "0")):
            cv_.create_text(458, yy, text=t, anchor="nw", font=self.f(9), fill=C["grid"])
        self.t_name_c = self.T(10, 10, self.cpu_name.upper(), 14, C["label"], budget=300)
        self.t_temp_c = self.T(470, 6, "--.- °C", 26, C["value"], anchor="ne", budget=190)
        self.t_title_c = self.T(6, 30, "UTILISATION CPU — -- %", 11, C["grid"])
        self.t_name_g = self.T(10, 174, self.gpu_name.upper(), 14, C["label"], budget=300)
        self.t_temp_g = self.T(470, 170, "--.- °C", 26, C["value"], anchor="ne", budget=190)
        self.t_title_g = self.T(6, 194, "UTILISATION GPU — -- %", 11, C["grid"])
        self.sparks = []
        for (x, y, w, h), key, col in ((self.g1, "cpu", C["graph"]), (self.g2, "gpu", C["graph2"])):
            area = cv_.create_polygon(0, 0, 0, 0, 0, 0, fill=col, stipple="gray25", outline="")
            line = cv_.create_line(0, 0, 0, 0, fill=col, width=3)
            dot = cv_.create_oval(0, 0, 0, 0, fill=col, outline="")
            self.sparks.append((x, y, w, h, key, area, line, dot))

    def update(self, s):
        cv_ = self.cv
        for x, y, w, h, key, area, line, dot in self.sparks:
            hist = s["hc"] if key == "cpu" else s["hg"]
            cv_.coords(area, *pts_area(hist, x, y, w, h))
            cv_.coords(line, *pts_line(hist, x, y, w, h))
            px, py = pos_last(hist, x, y, w, h)
            cv_.coords(dot, px - 3.2, py - 3.2, px + 3.2, py + 3.2)
        stext_set(cv_, self.t_temp_c, temp_str(s["ct"]))
        stext_set(cv_, self.t_temp_g, temp_str(s["gt"]))
        stext_set(cv_, self.t_title_c, f"UTILISATION CPU — {s['cu']:.0f} %")
        stext_set(cv_, self.t_title_g, f"UTILISATION GPU — {s['gu']:.0f} %")


class T02Hud(ThemeBase):
    """02 · HUD : deux moities, temp enorme, barre de charge, sparkline."""
    name = "02-hud"
    desc = "HUD grands chiffres"

    def build(self):
        cv_, C = self.cv, self.C
        cv_.create_line(240, 8, 240, 312, fill=C["frame"])
        self.halves = []
        for ox, key in ((0, "cpu"), (240, "gpu")):
            col = C["graph"] if key == "cpu" else C["graph2"]
            cx = ox + 120
            name = (self.cpu_name if key == "cpu" else self.gpu_name).upper()
            t_name = self.T(cx, 12, name, 13, C["label"], anchor="n", budget=226)
            t_temp = self.T(cx, 38, "--.- °C", 42, C["value"], anchor="n", budget=206)
            cv_.create_text(ox + 24, 118, text="CHARGE", anchor="nw", font=self.f(10), fill=C["grid"])
            t_pct = self.T(ox + 216, 112, "-- %", 22, C["label"], anchor="ne")
            bx, bw, by = ox + 24, 192, 152
            cv_.create_rectangle(bx, by, bx + bw, by + 9, outline=C["frame"], fill="")
            bar = cv_.create_rectangle(bx + 1, by + 1, bx + 1, by + 8, outline="", fill=col)
            sx, sw, sy, sh = ox + 24, 192, 188, 96
            for i in (1, 2):
                cv_.create_line(sx, sy + sh * i / 3, sx + sw, sy + sh * i / 3, fill=C["grid"])
            area = cv_.create_polygon(0, 0, 0, 0, 0, 0, fill=col, stipple="gray25", outline="")
            line = cv_.create_line(0, 0, 0, 0, fill=col, width=2)
            dot = cv_.create_oval(0, 0, 0, 0, fill=col, outline="")
            cv_.create_text(ox + 24, 296, text="HISTORIQUE 48 S", anchor="nw", font=self.f(9), fill=C["grid"])
            self.halves.append(dict(key=key, color=col, t_temp=t_temp, t_pct=t_pct,
                                    bar=bar, bx=bx, bw=bw, by=by,
                                    sx=sx, sy=sy, sw=sw, sh=sh, area=area, line=line, dot=dot))

    def update(self, s):
        cv_ = self.cv
        for h in self.halves:
            key = h["key"]
            use = s["cu"] if key == "cpu" else s["gu"]
            hist = s["hc"] if key == "cpu" else s["hg"]
            stext_set(cv_, h["t_temp"], temp_str(s["ct"] if key == "cpu" else s["gt"]))
            stext_set(cv_, h["t_pct"], f"{use:.0f} %")
            cv_.coords(h["bar"], h["bx"] + 1, h["by"] + 1,
                       h["bx"] + 1 + (h["bw"] - 2) * use / 100.0, h["by"] + 8)
            x, y, w, sh = h["sx"], h["sy"], h["sw"], h["sh"]
            cv_.coords(h["area"], *pts_area(hist, x, y, w, sh))
            cv_.coords(h["line"], *pts_line(hist, x, y, w, sh))
            px, py = pos_last(hist, x, y, w, sh)
            cv_.coords(h["dot"], px - 2.8, py - 2.8, px + 2.8, py + 2.8)


class T03Anneaux(ThemeBase):
    """03 · Anneaux : jauges circulaires 240°, temp au centre, sparklines en bas."""
    name = "03-anneaux"
    desc = "Anneaux (jauges)"

    def build(self):
        cv_, C = self.cv, self.C
        self.gs = []
        for cx, key in ((120, "cpu"), (360, "gpu")):
            col = C["graph"] if key == "cpu" else C["graph2"]
            r, cy = 72, 102
            cv_.create_arc(cx - r, cy - r, cx + r, cy + r, start=210, extent=-240,
                           style=tk.ARC, outline=C["frame"], width=9)
            val = cv_.create_arc(cx - r, cy - r, cx + r, cy + r, start=210, extent=-240,
                                 style=tk.ARC, outline=col, width=9)
            for cdeg in (-120, -60, 0, 60, 120):
                x0, y0 = compass(cx, cy, r + 8, cdeg)
                x1, y1 = compass(cx, cy, r + 13, cdeg)
                cv_.create_line(x0, y0, x1, y1, fill=C["grid"], width=2)
            name = (self.cpu_name if key == "cpu" else self.gpu_name).upper()
            t_name = self.T(cx, 10, name, 12, C["label"], anchor="n", budget=230)
            t_temp = self.T(cx, 74, "--.- °C", 26, C["value"], anchor="n", budget=150)
            t_use = self.T(cx, 116, f"{key.upper()} · -- %", 14, C["label"], anchor="n")
            self.gs.append(dict(key=key, val=val, t_temp=t_temp, t_use=t_use))
        self.sparks = []
        for sx, key in ((16, "cpu"), (256, "gpu")):
            col = C["graph"] if key == "cpu" else C["graph2"]
            sy, sw, sh = 238, 208, 62
            for i in (1, 2):
                cv_.create_line(sx, sy + sh * i / 3, sx + sw, sy + sh * i / 3, fill=C["grid"])
            area = cv_.create_polygon(0, 0, 0, 0, 0, 0, fill=col, stipple="gray25", outline="")
            line = cv_.create_line(0, 0, 0, 0, fill=col, width=2)
            cv_.create_text(sx, 226, text=f"HISTORIQUE {key.upper()} — 48 S", anchor="nw",
                            font=self.f(9), fill=C["grid"])
            self.sparks.append(dict(key=key, sx=sx, sy=sy, sw=sw, sh=sh, area=area, line=line))

    def update(self, s):
        cv_ = self.cv
        for g in self.gs:
            key = g["key"]
            use = s["cu"] if key == "cpu" else s["gu"]
            cv_.itemconfig(g["val"], extent=-240.0 * use / 100.0)
            stext_set(cv_, g["t_temp"], temp_str(s["ct"] if key == "cpu" else s["gt"]))
            stext_set(cv_, g["t_use"], f"{key.upper()} · {use:.0f} %")
        for sp in self.sparks:
            hist = s["hc"] if sp["key"] == "cpu" else s["hg"]
            x, y, w, sh = sp["sx"], sp["sy"], sp["sw"], sp["sh"]
            cv_.coords(sp["area"], *pts_area(hist, x, y, w, sh))
            cv_.coords(sp["line"], *pts_line(hist, x, y, w, sh))


class T04Tuiles(ThemeBase):
    """04 · Tuiles 2x2 : temp/charge CPU a gauche, temp/charge GPU a droite."""
    name = "04-tuiles"
    desc = "Tuiles 2x2"

    def build(self):
        cv_, C = self.cv, self.C
        # (x, y, w, h, label, hist_key, unite)
        tiles = [
            (4, 4, 232, 152, "CPU · TEMPÉRATURE", "htc", "°C"),
            (244, 4, 232, 152, "CPU · CHARGE", "hc", "%"),
            (4, 164, 232, 152, "GPU · TEMPÉRATURE", "htg", "°C"),
            (244, 164, 232, 152, "GPU · CHARGE", "hg", "%"),
        ]
        self.tiles = []
        for (x, y, w, h, label, hkey, unit) in tiles:
            col = C["graph"] if "CPU" in label else C["graph2"]
            cv_.create_rectangle(x, y, x + w, y + h, outline=C["frame"],
                                 fill=C["bg"], stipple="gray12")
            cv_.create_line(x + 14, y + h - 52, x + w - 14, y + h - 52, fill=C["grid"])
            sx, sy, sw, sh = x + 14, y + h - 46, w - 28, 36
            area = cv_.create_polygon(0, 0, 0, 0, 0, 0, fill=col, stipple="gray25", outline="")
            line = cv_.create_line(0, 0, 0, 0, fill=col, width=2)
            self.T(x + 14, y + 12, label, 11, C["grid"])
            t_val = self.T(x + 14, y + 36, "--", 38, C["value"], budget=200)
            sub = "48 S D HISTORIQUE" if unit == "%" else ("PACKAGE · LIVE" if "CPU" in label else "CORE · LIVE")
            self.T(x + 14, y + 94, sub, 10, C["label"])
            self.tiles.append(dict(col=col, hkey=hkey, unit=unit, t_val=t_val,
                                   sx=sx, sy=sy, sw=sw, sh=sh, area=area, line=line))

    def update(self, s):
        cv_ = self.cv
        for t in self.tiles:
            if t["unit"] == "°C":
                val = temp_str(s["ct"] if t["hkey"] == "htc" else s["gt"])
            else:
                val = f"{(s['cu'] if t['hkey'] == 'hc' else s['gu']):.0f} %"
            stext_set(cv_, t["t_val"], val)
            hist = s[t["hkey"]]
            cv_.coords(t["area"], *pts_area(hist, t["sx"], t["sy"], t["sw"], t["sh"]))
            cv_.coords(t["line"], *pts_line(hist, t["sx"], t["sy"], t["sw"], t["sh"]))


class T05Colonnes(ThemeBase):
    """05 · Colonnes segmentees : gros chiffres + VU-metre vertical (14 segments)."""
    name = "05-colonnes"
    desc = "Colonnes segmentees"

    SEGS = 14
    SEG_H = 15
    SEG_GAP = 3
    SEG_TOP = 38

    def build(self):
        cv_, C = self.cv, self.C
        cv_.create_line(240, 10, 240, 310, fill=C["frame"])
        self.cols = []
        for ox, key in ((0, "cpu"), (240, "gpu")):
            col = C["graph"] if key == "cpu" else C["graph2"]
            cx = ox + 192
            rects = []
            for i in range(self.SEGS):
                yy = self.SEG_TOP + (self.SEGS - 1 - i) * (self.SEG_H + self.SEG_GAP)
                rid = cv_.create_rectangle(cx, yy, cx + 30, yy + self.SEG_H,
                                           outline=C["frame"], fill="")
                rects.append(rid)
            sx, sy, sw, sh = ox + 14, 170, 158, 108
            for i in (1, 2):
                cv_.create_line(sx, sy + sh * i / 3, sx + sw, sy + sh * i / 3, fill=C["grid"])
            area = cv_.create_polygon(0, 0, 0, 0, 0, 0, fill=col, stipple="gray25", outline="")
            line = cv_.create_line(0, 0, 0, 0, fill=col, width=2)
            name = (self.cpu_name if key == "cpu" else self.gpu_name).upper()
            self.T(ox + 14, 12, name, 12, C["label"], budget=200)
            t_temp = self.T(ox + 14, 34, "--.- °C", 28, C["value"])
            t_use = self.T(ox + 14, 78, "-- %", 34, col)
            self.T(ox + 14, 122, "UTILISATION", 9, C["grid"])
            self.T(ox + 14, 288, "HISTORIQUE 48 S", 9, C["grid"])
            self.cols.append(dict(key=key, color=col, rects=rects, t_temp=t_temp, t_use=t_use,
                                  sx=sx, sy=sy, sw=sw, sh=sh, area=area, line=line))

    def update(self, s):
        cv_ = self.cv
        for c in self.cols:
            key = c["key"]
            use = s["cu"] if key == "cpu" else s["gu"]
            level = self.SEGS * use / 100.0
            for i, rid in enumerate(c["rects"]):
                seg_set(cv_, rid, c["color"], max(0.0, min(1.0, level - i)))
            stext_set(cv_, c["t_temp"], temp_str(s["ct"] if key == "cpu" else s["gt"]))
            stext_set(cv_, c["t_use"], f"{use:.0f} %")
            hist = s["hc"] if key == "cpu" else s["hg"]
            cv_.coords(c["area"], *pts_area(hist, c["sx"], c["sy"], c["sw"], c["sh"]))
            cv_.coords(c["line"], *pts_line(hist, c["sx"], c["sy"], c["sw"], c["sh"]))


class T06Oscillo(ThemeBase):
    """06 · Oscilloscope : une grande courbe, CPU plein + GPU en tirets, bandeau de lecture."""
    name = "06-oscillo"
    desc = "Oscilloscope"

    def build(self):
        cv_, C = self.cv, self.C
        gx, gy, gw, gh = 38, 12, 434, 168
        self.g = (gx, gy, gw, gh)
        for i in (1, 2, 3):
            cv_.create_line(gx, gy + gh * i / 4, gx + gw, gy + gh * i / 4, fill=C["grid"])
        for k in (1, 2, 3, 4, 5):
            vx = gx + gw * k / 6
            cv_.create_line(vx, gy, vx, gy + gh, fill=C["grid"])
        self.area_c = cv_.create_polygon(0, 0, 0, 0, 0, 0, fill=C["graph"], stipple="gray25", outline="")
        self.line_c = cv_.create_line(0, 0, 0, 0, fill=C["graph"], width=3)
        self.line_g = cv_.create_line(0, 0, 0, 0, fill=C["graph2"], width=2, dash=(5, 4))
        self.dot_c = cv_.create_oval(0, 0, 0, 0, fill=C["graph"], outline="")
        self.dot_g = cv_.create_oval(0, 0, 0, 0, fill=C["graph2"], outline="")
        cv_.create_line(12, 192, 468, 192, fill=C["frame"])
        # legende (petits traits + labels)
        cv_.create_line(376, 10, 392, 10, fill=C["graph"], width=3)
        cv_.create_text(396, 6, text="CPU", anchor="nw", font=self.f(10), fill=C["grid"])
        cv_.create_line(432, 10, 448, 10, fill=C["graph2"], width=2, dash=(4, 3))
        cv_.create_text(452, 6, text="GPU", anchor="nw", font=self.f(10), fill=C["grid"])
        for yy, t in ((6, "100"), (91, "50"), (174, "0")):
            cv_.create_text(8 if t == "100" else (12 if t == "50" else 16), yy,
                            text=t, anchor="nw", font=self.f(9), fill=C["grid"])
        # barres de lecture
        for bx, col in ((16, C["graph"]), (264, C["graph2"])):
            cv_.create_rectangle(bx, 284, bx + 200, 291, outline=C["frame"], fill="")
        self.bar_c = cv_.create_rectangle(17, 285, 17, 290, outline="", fill=C["graph"])
        self.bar_g = cv_.create_rectangle(265, 285, 265, 290, outline="", fill=C["graph2"])
        self.t_temp_c = self.T(16, 204, "--.- °C", 32, C["value"], budget=230)
        self.t_temp_g = self.T(264, 204, "--.- °C", 32, C["value"], budget=230)
        self.t_use_c = self.T(16, 250, "CPU · CHARGE -- %", 12, C["label"])
        self.t_use_g = self.T(264, 250, "GPU · CHARGE -- %", 12, C["label"])
        cv_.create_text(16, 296, text=self.cpu_name.upper(), anchor="nw", font=self.f(9), fill=C["grid"])
        cv_.create_text(264, 296, text=self.gpu_name.upper(), anchor="nw", font=self.f(9), fill=C["grid"])
        cv_.create_text(468, 266, text="MAJ 1 S", anchor="ne", font=self.f(9), fill=C["grid"])

    def update(self, s):
        cv_ = self.cv
        x, y, w, h = self.g
        cv_.coords(self.area_c, *pts_area(s["hc"], x, y, w, h))
        cv_.coords(self.line_c, *pts_line(s["hc"], x, y, w, h))
        cv_.coords(self.line_g, *pts_line(s["hg"], x, y, w, h))
        px, py = pos_last(s["hc"], x, y, w, h)
        cv_.coords(self.dot_c, px - 3.2, py - 3.2, px + 3.2, py + 3.2)
        px, py = pos_last(s["hg"], x, y, w, h)
        cv_.coords(self.dot_g, px - 3.2, py - 3.2, px + 3.2, py + 3.2)
        cv_.coords(self.bar_c, 17, 285, 17 + 198 * s["cu"] / 100.0, 290)
        cv_.coords(self.bar_g, 265, 285, 265 + 198 * s["gu"] / 100.0, 290)
        stext_set(cv_, self.t_temp_c, temp_str(s["ct"]))
        stext_set(cv_, self.t_temp_g, temp_str(s["gt"]))
        stext_set(cv_, self.t_use_c, f"CPU · CHARGE {s['cu']:.0f} %")
        stext_set(cv_, self.t_use_g, f"GPU · CHARGE {s['gu']:.0f} %")


class T07DoublePeak(ThemeBase):
    """07 · Double peak : 2 courbes empilees + barres de charge dans les entetes."""
    name = "07-double"
    desc = "Double peak"

    def build(self):
        cv_, C = self.cv, self.C
        gx, gw, gh = 6, 466, 104
        self.g1, self.g2 = (gx, 52, gw, gh), (gx, 212, gw, gh)
        for (x, y, w, h) in (self.g1, self.g2):
            for i in (1, 2, 3):
                cv_.create_line(x, y + h * i / 4, x + w, y + h * i / 4, fill=C["grid"])
        self.sparks = []
        for (x, y, w, h), key, col in ((self.g1, "cpu", C["graph"]), (self.g2, "gpu", C["graph2"])):
            area = cv_.create_polygon(0, 0, 0, 0, 0, 0, fill=col, stipple="gray25", outline="")
            line = cv_.create_line(0, 0, 0, 0, fill=col, width=3)
            self.sparks.append((x, y, w, h, key, area, line))
        # barres de charge dans les entetes
        cv_.create_rectangle(286, 12, 406, 19, outline=C["frame"], fill="")
        cv_.create_rectangle(286, 172, 406, 179, outline=C["frame"], fill="")
        self.bar_c = cv_.create_rectangle(287, 13, 287, 18, outline="", fill=C["graph"])
        self.bar_g = cv_.create_rectangle(287, 173, 287, 178, outline="", fill=C["graph2"])
        cv_.create_line(6, 164, 474, 164, fill=C["frame"])
        cv_.create_oval(237, 161, 243, 167, fill=C["graph"], outline="")
        cv_.create_oval(241, 161, 247, 167, fill=C["graph2"], outline="")
        self.t_name_c = self.T(10, 10, self.cpu_name.upper(), 14, C["label"], budget=270)
        self.t_use_c = self.T(10, 34, "UTILISATION -- %", 10, C["grid"])
        self.t_temp_c = self.T(470, 4, "--.- °C", 24, C["value"], anchor="ne")
        self.t_name_g = self.T(10, 170, self.gpu_name.upper(), 14, C["label"], budget=270)
        self.t_use_g = self.T(10, 194, "UTILISATION -- %", 10, C["grid"])
        self.t_temp_g = self.T(470, 164, "--.- °C", 24, C["value"], anchor="ne")

    def update(self, s):
        cv_ = self.cv
        for x, y, w, h, key, area, line in self.sparks:
            hist = s["hc"] if key == "cpu" else s["hg"]
            cv_.coords(area, *pts_area(hist, x, y, w, h))
            cv_.coords(line, *pts_line(hist, x, y, w, h))
        cv_.coords(self.bar_c, 287, 13, 287 + 118 * s["cu"] / 100.0, 18)
        cv_.coords(self.bar_g, 287, 173, 287 + 118 * s["gu"] / 100.0, 178)
        stext_set(cv_, self.t_temp_c, temp_str(s["ct"]))
        stext_set(cv_, self.t_temp_g, temp_str(s["gt"]))
        stext_set(cv_, self.t_use_c, f"UTILISATION {s['cu']:.0f} %")
        stext_set(cv_, self.t_use_g, f"UTILISATION {s['gu']:.0f} %")


class T08Frise(ThemeBase):
    """08 · Frise thermique : barres verticales (1 s = 1 barre), hauteur + densite = temp."""
    name = "08-frise"
    desc = "Frise thermique"

    def build(self):
        cv_, C = self.cv, self.C
        self.tracks = []
        n = max(1, HN)
        bw = 316.0 / n
        for oy, key in ((6, "cpu"), (160, "gpu")):
            col = C["graph"] if key == "cpu" else C["graph2"]
            x0, w, y, h = 160, 306, oy + 30, 64
            rects = []
            for i in range(n):
                rid = cv_.create_rectangle(x0 + i * bw + 1, y + h - 4,
                                           x0 + i * bw + bw - 1, y + h,
                                           fill=col, stipple="gray50", outline="")
                rects.append(rid)
            cv_.create_line(x0, y + h, x0 + w, y + h, fill=C["frame"])
            for i in (1, 2):
                cv_.create_line(x0, y + h * i / 3, x0 + w, y + h * i / 3, fill=C["grid"])
            name = (self.cpu_name if key == "cpu" else self.gpu_name).upper()
            short = self.short_suffix(name, 11, 130)
            self.T(12, oy + 26, short, 11, C["label"], budget=140)
            t_temp = self.T(12, oy + 48, "--.- °C", 28, C["value"], budget=140)
            t_use = self.T(12, oy + 84, "-- % CHARGE", 11, col, budget=140)
            cv_.create_text(160, oy + 100, text="−48 S", anchor="nw", font=self.f(9), fill=C["grid"])
            cv_.create_text(466, oy + 100, text="NOW", anchor="ne", font=self.f(9), fill=C["grid"])
            self.tracks.append(dict(key=key, color=col, x0=x0, w=w, y=y, h=h, bw=bw,
                                    rects=rects, t_temp=t_temp, t_use=t_use))

    @staticmethod
    def _bar_levels(v):
        """(hauteur_css, densite 0..1) calculates depuis la temperature."""
        vv = 50.0 if v is None else v
        vv = min(max(vv, 35.0), 90.0)
        bh = max(4.0, (vv - 40.0) / 45.0 * 64.0)
        op = 0.35 + 0.65 * min(1.0, max(0.0, (vv - 45.0) / 35.0))
        return min(bh, 64.0), op

    def update(self, s):
        cv_ = self.cv
        for t in self.tracks:
            key = t["key"]
            hist = s["htc"] if key == "cpu" else s["htg"]
            y, h, bw, x0 = t["y"], t["h"], t["bw"], t["x0"]
            for i, rid in enumerate(t["rects"]):
                v = hist[i] if i < len(hist) else (hist[-1] if hist else None)
                bh, op = self._bar_levels(v)
                cv_.coords(rid, x0 + i * bw + 1, y + h - bh, x0 + i * bw + bw - 1, y + h)
                st = stipple_for_op(op) or ""
                cv_.itemconfig(rid, fill=t["color"], stipple=st)
            stext_set(cv_, t["t_temp"], temp_str(s["ct"] if key == "cpu" else s["gt"]))
            stext_set(cv_, t["t_use"], f"{(s['cu'] if key == 'cpu' else s['gu']):.0f} % CHARGE")


class T09Split(ThemeBase):
    """09 · Compact splitscreen : CPU a gauche, GPU a droite, courbes independantes."""
    name = "09-split"
    desc = "Compact splitscreen"

    def build(self):
        cv_, C = self.cv, self.C
        cv_.create_line(240, 8, 240, 312, fill=C["frame"])
        self.halves = []
        for ox, key in ((0, "cpu"), (240, "gpu")):
            col = C["graph"] if key == "cpu" else C["graph2"]
            sx, sy, sw, sh = ox + 12, 150, 212, 150
            for i in (1, 2, 3):
                cv_.create_line(sx, sy + sh * i / 4, sx + sw, sy + sh * i / 4, fill=C["grid"])
            area = cv_.create_polygon(0, 0, 0, 0, 0, 0, fill=col, stipple="gray25", outline="")
            line = cv_.create_line(0, 0, 0, 0, fill=col, width=3)
            dot = cv_.create_oval(0, 0, 0, 0, fill=col, outline="")
            name = (self.cpu_name if key == "cpu" else self.gpu_name).upper()
            self.T(ox + 12, 10, name, 12, C["label"], budget=220)
            t_temp = self.T(ox + 12, 34, "--.- °C", 30, C["value"])
            t_use = self.T(ox + 12, 92, "-- %", 24, col)
            t_lab = self.T(ox + 12, 132, "UTILISATION · 48 S", 9, C["grid"])
            self.halves.append(dict(key=key, color=col, t_temp=t_temp, t_use=t_use,
                                    sx=sx, sy=sy, sw=sw, sh=sh, area=area, line=line, dot=dot))

    def update(self, s):
        cv_ = self.cv
        for h in self.halves:
            key = h["key"]
            use = s["cu"] if key == "cpu" else s["gu"]
            hist = s["hc"] if key == "cpu" else s["hg"]
            stext_set(cv_, h["t_temp"], temp_str(s["ct"] if key == "cpu" else s["gt"]))
            stext_set(cv_, h["t_use"], f"{use:.0f} %")
            x, y, w, sh = h["sx"], h["sy"], h["sw"], h["sh"]
            cv_.coords(h["area"], *pts_area(hist, x, y, w, sh))
            cv_.coords(h["line"], *pts_line(hist, x, y, w, sh))
            px, py = pos_last(hist, x, y, w, sh)
            cv_.coords(h["dot"], px - 3.0, py - 3.0, px + 3.0, py + 3.0)


def _temp_color(t, normal, warm=65, hot=75):
    if t is None:
        return normal
    if t >= hot:
        return "#FB7185"
    if t >= warm:
        return "#FBBF24"
    return normal


class T10Modern(ThemeBase):
    """10 · Cartes sombres, chiffres fins, courbes cyan / violet."""
    name = "10-modern"
    desc = "Modern Dark"

    def build(self):
        self.F = "Segoe UI"
        cv_ = self.cv
        cv_.create_rectangle(0, 0, 480, 320, fill="#0B0F14", outline="")
        self.cards = []
        for top, key, accent, name in (
                (8, "cpu", "#38BDF8", self.cpu_name),
                (166, "gpu", "#A78BFA", self.gpu_name)):
            cv_.create_rectangle(10, top, 470, top + 146, fill="#121820", outline="#2A3544")
            t_name = self.T(26, top + 12, name.upper(), 11, "#8B98A9", budget=300)
            chip_bg = cv_.create_rectangle(380, top + 10, 452, top + 28, fill="#12352C", outline="#1F6B52")
            t_chip = self.T(416, top + 12, "STABLE", 9, "#34D399", anchor="n")
            t_temp = self.T(26, top + 36, "-- °C", 36, accent, budget=240)
            self.T(26, top + 78, "TEMPÉRATURE", 9, "#566372")
            t_use = self.T(452, top + 40, "-- %", 28, "#E6EDF3", anchor="ne", budget=140)
            self.T(452, top + 78, "UTILISATION", 9, "#566372", anchor="ne")
            sx, sy, sw, sh = 26, top + 96, 424, 28
            area = cv_.create_polygon(0, 0, 0, 0, 0, 0, fill=accent, stipple="gray25", outline="")
            line = cv_.create_line(0, 0, 0, 0, fill=accent, width=2, smooth=True)
            cv_.create_rectangle(sx, top + 130, sx + sw, top + 134, fill="#1C2630", outline="")
            bar = cv_.create_rectangle(sx, top + 130, sx, top + 134, fill=accent, outline="")
            self.cards.append(dict(key=key, accent=accent, t_name=t_name, chip_bg=chip_bg,
                                    t_chip=t_chip, t_temp=t_temp, t_use=t_use,
                                    sx=sx, sy=sy, sw=sw, sh=sh, area=area, line=line, bar=bar))

    def update(self, s):
        cv_ = self.cv
        for c in self.cards:
            cpu = c["key"] == "cpu"
            temp = s["ct"] if cpu else s["gt"]
            use = s["cu"] if cpu else s["gu"]
            hist = s["hc"] if cpu else s["hg"]
            col = _temp_color(temp, c["accent"])
            hot = temp is not None and temp >= 65
            stext_set(cv_, c["t_temp"], "-- °C" if temp is None else f"{temp:.0f} °C")
            cv_.itemconfig(c["t_temp"][1], fill=col)
            stext_set(cv_, c["t_use"], f"{use:.0f} %")
            stext_set(cv_, c["t_chip"], "CHAUD" if hot else "STABLE")
            cv_.itemconfig(c["t_chip"][1], fill="#FBBF24" if hot else "#34D399")
            cv_.itemconfig(c["chip_bg"], fill="#3A3014" if hot else "#12352C",
                           outline="#8A6A20" if hot else "#1F6B52")
            cv_.coords(c["area"], *pts_area(hist, c["sx"], c["sy"], c["sw"], c["sh"]))
            cv_.coords(c["line"], *pts_line(hist, c["sx"], c["sy"], c["sw"], c["sh"]))
            cv_.itemconfig(c["line"], fill=col)
            frac = max(0.0, min(1.0, use / 100.0))
            cv_.coords(c["bar"], c["sx"], c["sy"] + 34, c["sx"] + c["sw"] * frac, c["sy"] + 38)
            cv_.itemconfig(c["bar"], fill=col)


class T11Ambre(ThemeBase):
    """11 · Terminal ambre, barres segmentées, courbe à traînée."""
    name = "11-ambre"
    desc = "Terminal Ambre"

    def build(self):
        self.F = "Consolas"
        cv_ = self.cv
        cv_.create_rectangle(0, 0, 480, 320, fill="#0A0600", outline="")
        for y in range(0, 320, 3):
            cv_.create_line(0, y, 480, y, fill="#140C00")
        cv_.create_text(12, 10, text="SENSORPANEL // SYS.01", anchor="nw",
                        font=("Consolas", -12, "bold"), fill="#FFB000")
        self.t_clock = self.T(468, 10, "--:--:--", 12, "#FF8F00", anchor="ne")
        cv_.create_line(12, 30, 468, 30, fill="#FFB000", dash=(3, 3))
        self.blocks = []
        for top, key, name in ((40, "cpu", self.cpu_name), (168, "gpu", self.gpu_name)):
            self.T(12, top, "> " + name.upper(), 11, "#FFA726", budget=450)
            t_temp = self.T(12, top + 18, "-- °C", 28, "#FFB000", budget=220)
            t_use = self.T(468, top + 18, "-- %", 28, "#FFC46B", anchor="ne", budget=160)
            segs = []
            for i in range(24):
                x = 12 + i * 19
                segs.append(cv_.create_rectangle(x, top + 54, x + 16, top + 63,
                                                 fill="#3A2A08", outline=""))
            sy = top + 70
            glow = cv_.create_line(0, 0, 0, 0, fill="#7A5800", width=4)
            line = cv_.create_line(0, 0, 0, 0, fill="#FFB000", width=2)
            self.blocks.append(dict(key=key, t_temp=t_temp, t_use=t_use, segs=segs,
                                     sx=12, sy=sy, sw=444, sh=36, glow=glow, line=line))
        cv_.create_line(12, 292, 468, 292, fill="#FFB000", dash=(3, 3))
        cv_.create_text(12, 300, text="● POLL 1.0s", anchor="nw",
                        font=("Consolas", -10), fill="#B36B00")
        cv_.create_text(468, 300, text="NVML · LHM", anchor="ne",
                        font=("Consolas", -10), fill="#B36B00")

    def update(self, s):
        cv_ = self.cv
        stext_set(cv_, self.t_clock, time.strftime("%H:%M:%S"))
        for b in self.blocks:
            cpu = b["key"] == "cpu"
            temp = s["ct"] if cpu else s["gt"]
            use = s["cu"] if cpu else s["gu"]
            hist = s["hc"] if cpu else s["hg"]
            stext_set(cv_, b["t_temp"], "-- °C" if temp is None else f"{temp:.0f} °C")
            stext_set(cv_, b["t_use"], f"{use:.0f} %")
            n_on = int(round(max(0.0, min(100.0, use)) / 100.0 * len(b["segs"])))
            for i, rid in enumerate(b["segs"]):
                cv_.itemconfig(rid, fill="#FFB000" if i < n_on else "#3A2A08")
            cv_.coords(b["glow"], *pts_line(hist, b["sx"], b["sy"], b["sw"], b["sh"]))
            cv_.coords(b["line"], *pts_line(hist, b["sx"], b["sy"], b["sw"], b["sh"]))


class T12Minimal(ThemeBase):
    """12 · Noir et blanc, température géante, courbe fine."""
    name = "12-minimal"
    desc = "Minimal Mono"

    def build(self):
        self.F = "Segoe UI"
        cv_ = self.cv
        cv_.create_rectangle(0, 0, 480, 320, fill="#050505", outline="")
        cv_.create_line(24, 160, 456, 160, fill="#262626")
        self.halves = []
        for top, key, name in ((0, "cpu", self.cpu_name), (162, "gpu", self.gpu_name)):
            dot = cv_.create_oval(24, top + 18, 30, top + 24, fill="#3A3A3A", outline="")
            t_temp = self.T(24, top + 28, "--", 52, "#F2F2F2", budget=210)
            self.T(24, top + 96, name, 11, "#8F8F8F", budget=200)
            t_use = self.T(24, top + 116, "USAGE -- %", 11, "#C9C9C9", budget=200)
            sx, sy, sw, sh = 230, top + 22, 226, 96
            cv_.create_line(sx, sy + sh - 8, sx + sw, sy + sh - 8, fill="#1D1D1D")
            line = cv_.create_line(0, 0, 0, 0, fill="#E8E8E8", width=2, smooth=True)
            dotg = cv_.create_oval(0, 0, 0, 0, fill="#FFFFFF", outline="")
            self.halves.append(dict(key=key, dot=dot, t_temp=t_temp, t_use=t_use,
                                     sx=sx, sy=sy, sw=sw, sh=sh, line=line, dotg=dotg))

    def update(self, s):
        cv_ = self.cv
        for h in self.halves:
            cpu = h["key"] == "cpu"
            temp = s["ct"] if cpu else s["gt"]
            use = s["cu"] if cpu else s["gu"]
            hist = s["hc"] if cpu else s["hg"]
            hot = temp is not None and temp >= 80
            col = "#FF5C5C" if hot else "#F2F2F2"
            stext_set(cv_, h["t_temp"], "--" if temp is None else f"{temp:.0f}°")
            cv_.itemconfig(h["t_temp"][1], fill=col)
            stext_set(cv_, h["t_use"], f"USAGE {use:.0f} %")
            cv_.itemconfig(h["dot"], fill="#FF5C5C" if hot else "#3A3A3A")
            cv_.coords(h["line"], *pts_line(hist, h["sx"], h["sy"], h["sw"], h["sh"]))
            px, py = pos_last(hist, h["sx"], h["sy"], h["sw"], h["sh"])
            cv_.coords(h["dotg"], px - 3, py - 3, px + 3, py + 3)


class T13Neon(ThemeBase):
    """13 · Néon cyan / magenta, barres segmentées."""
    name = "13-neon"
    desc = "Cyber Néon"

    def build(self):
        self.F = "Segoe UI"
        cv_ = self.cv
        cv_.create_rectangle(0, 0, 480, 320, fill="#0A0022", outline="")
        cv_.create_rectangle(0, 220, 480, 320, fill="#14042E", outline="")
        for y in range(230, 320, 14):
            cv_.create_line(0, y, 480, y, fill="#3A1460")
        for x in range(0, 480, 26):
            cv_.create_line(x, 240, x, 320, fill="#401030")
        self.T(14, 10, "⌁ SENSOR PANEL", 12, "#00E5FF")
        self.t_clock = self.T(466, 10, "--:--", 12, "#FF3EC8", anchor="ne")
        self.panels = []
        for top, key, accent, edge, name in (
                (38, "cpu", "#00E5FF", "#7FF3FF", "CPU · " + self.cpu_name),
                (174, "gpu", "#FF3EC8", "#FFA8EA", "GPU · " + self.gpu_name)):
            cv_.create_rectangle(12, top, 468, top + 126, fill="#12082E", outline=accent, width=2)
            self.T(26, top + 10, name.upper(), 10, edge, budget=420)
            t_temp = stext(cv_, 26, top + 32, "--°C", ("Segoe UI", -36, "bold italic"), accent, "nw")
            t_use = stext(cv_, 454, top + 36, "--%", ("Segoe UI", -30, "bold italic"), "#E8ECFF", "ne")
            self.T(26, top + 74, "TEMPÉRATURE", 8, "#7780B8")
            self.T(454, top + 74, "UTILISATION", 8, "#7780B8", anchor="ne")
            segs = []
            for i in range(22):
                x = 26 + i * 20
                segs.append(cv_.create_rectangle(x, top + 100, x + 16, top + 110,
                                                 fill="#2A2048", outline=""))
            self.panels.append(dict(key=key, accent=accent, t_temp=t_temp, t_use=t_use, segs=segs))

    def update(self, s):
        cv_ = self.cv
        stext_set(cv_, self.t_clock, time.strftime("%H:%M"))
        for p in self.panels:
            cpu = p["key"] == "cpu"
            temp = s["ct"] if cpu else s["gt"]
            use = s["cu"] if cpu else s["gu"]
            stext_set(cv_, p["t_temp"], "--°C" if temp is None else f"{temp:.0f}°C")
            stext_set(cv_, p["t_use"], f"{use:.0f}%")
            n_on = int(round(max(0.0, min(100.0, use)) / 100.0 * len(p["segs"])))
            for i, rid in enumerate(p["segs"]):
                cv_.itemconfig(rid, fill=p["accent"] if i < n_on else "#2A2048")


THEMES = [T01AidaPlus, T02Hud, T03Anneaux, T04Tuiles, T05Colonnes,
          T06Oscillo, T07DoublePeak, T08Frise, T09Split,
          T10Modern, T11Ambre, T12Minimal, T13Neon]


def resolve_theme(key):
    """'6', '06-oscillo', 'oscillo'... -> classe de theme (defaut : 01)."""
    k = str(key).strip().lower()
    m = re.match(r"(\d+)", k)
    if m:
        i = int(m.group(1))
        if 1 <= i <= len(THEMES):
            return THEMES[i - 1]
    for t in THEMES:
        if k and (k == t.name or k in t.name or k in t.desc.lower()):
            return t
    return THEMES[0]


# ================= UI / boucle =================
def parse_args(argv):
    setup = "--setup" in argv
    theme_arg = None
    selftest_ms = 0
    for a in argv:
        if a.startswith("--theme="):
            theme_arg = a.split("=", 1)[1].strip()
        elif a.startswith("--selftest"):
            selftest_ms = 3000
            if "=" in a:
                try:
                    selftest_ms = int(a.split("=", 1)[1])
                except ValueError:
                    pass
    return setup, theme_arg, selftest_ms


def paint_background():
    """(Re)dessine Fond.png sur le canvas. A rappeler apres un cv.delete('all')."""
    if bg_img is not None:
        cv.create_image(0, 0, image=bg_img, anchor="nw")


def make_theme(key):
    return resolve_theme(key)(cv, COL, FONT_DIGI, (CPU_NAME, GPU_NAME))


def apply_theme(key):
    """Change le theme a chaud (efface et reconstruit tout le canvas).
    Pret pour une option 'a la volee' : ex. depuis le menu, apply_theme('6')."""
    global theme
    cv.delete("all")
    paint_background()
    theme = make_theme(key)
    theme.update(state)


def set_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def toggle_lock():
    # bascule : sauvegarde la position puis inverse le mode
    cfg.set("panel", "x", str(root.winfo_x()))
    cfg.set("panel", "y", str(root.winfo_y()))
    cfg.set("panel", "locked", str(not locked).lower())
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        cfg.write(f)
    root.destroy()
    if getattr(sys, "frozen", False):
        os.execv(sys.executable, [sys.executable])
    else:
        os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)])


def show_menu(e):
    menu.post(e.x_root, e.y_root)


def check_theme_cmd():
    """Theme a la volée demandé par le Centre de controle : BASE/theme_cmd.txt.
    Le fichier contient la clé du theme ; on l'applique et on supprime le fichier."""
    p = os.path.join(BASE, "theme_cmd.txt")
    try:
        k = open(p, encoding="utf-8-sig").read().strip()   # utf-8-sig : BOM tolere
        os.remove(p)
    except Exception:
        return
    if k:
        try:
            apply_theme(k)
        except Exception:
            pass


def tick():
    global warned_admin, smi_cooldown
    check_theme_cmd()
    # --- CPU : usage psutil + temp LHM ---
    u_cpu = cpu_usage()
    t_cpu = cpu_temp_lhm() if want_cpu_temp else None
    state["cu"] = u_cpu
    state["ct"] = t_cpu
    state["hc"].append(u_cpu)
    state["htc"].append(t_cpu if t_cpu is not None else state["htc"][-1])
    if t_cpu is None and not ADMIN and not warned_admin:
        warned_admin = True
        print("ASTUCE : relance en admin pour la temp CPU Ryzen (clic droit > admin).")

    # --- GPU : NVML, fallback nvidia-smi 1x/10s max, sinon dernier ---
    t_gpu, u_gpu = gpu_nvml()
    if t_gpu is None and smi_cooldown <= 0:
        try:
            ft, fu = gpu_smi_fallback()
        except Exception:
            ft, fu = None, None
        if ft is not None:
            t_gpu = ft
        if fu is not None:
            u_gpu = fu
        smi_cooldown = 10
    smi_cooldown = max(0, smi_cooldown - 1)
    if u_gpu is None:
        u_gpu = state["hg"][-1] if state["hg"] else 0.0
    state["gu"] = u_gpu
    state["gt"] = t_gpu
    state["hg"].append(u_gpu)
    state["htg"].append(t_gpu if t_gpu is not None else state["htg"][-1])

    theme.update(state)
    root.after(interval, tick)


def main(argv=None):
    global cfg, locked, topmost, interval, HN, want_cpu_temp, COL, ADMIN
    global root, cv, theme, bg_img, state

    argv = list(sys.argv if argv is None else argv)
    setup, theme_arg, selftest_ms = parse_args(argv)

    if "--list-themes" in argv:
        for i, t in enumerate(THEMES, 1):
            print(f"{i}) {t.name} — {t.desc}")
        return 0

    ADMIN = is_admin()

    cfg = configparser.ConfigParser()
    cfg.read(CFG_PATH, encoding="utf-8")
    locked = cfg.getboolean("panel", "locked", fallback=True)
    topmost = cfg.getboolean("panel", "topmost", fallback=True)
    interval = cfg.getint("panel", "interval_ms", fallback=1000)
    HN = cfg.getint("panel", "history", fallback=48)
    want_cpu_temp = cfg.getboolean("panel", "cpu_temp_lhm", fallback=True)
    COL = {
        "label": cfg.get("colors", "label", fallback="#1FE01F"),
        "value": cfg.get("colors", "value", fallback="#4EC221"),
        "graph": cfg.get("colors", "graph", fallback="#56DC23"),
        "graph2": cfg.get("colors", "graph2", fallback="#4EC221"),
        "grid": cfg.get("colors", "grid", fallback="#008000"),
        "frame": cfg.get("colors", "frame", fallback="#005E00"),
        "bg": cfg.get("colors", "bg", fallback="#000000"),
    }
    theme_key = theme_arg or cfg.get("panel", "theme", fallback="1")
    if setup:
        locked = False  # fenetre deplacable pour placement, quitte puis relance normal

    init_providers(want_cpu_temp)
    set_dpi_awareness()

    # historiques : usages + temperatures (pour les sparklines temp)
    state = {
        "cu": 0.0, "ct": None, "gu": 0.0, "gt": None,
        "hc": deque([0.0] * HN, maxlen=HN),
        "hg": deque([0.0] * HN, maxlen=HN),
        "htc": deque([40.0] * HN, maxlen=HN),
        "htg": deque([40.0] * HN, maxlen=HN),
    }

    px, py = panel_xy()
    if selftest_ms:
        px, py = 60, 60   # position fixe pour capture propre
        locked = True

    root = tk.Tk()
    root.title("SensorPanel 480x320")
    root.geometry(f"{W}x{H}+{px}+{py}")
    root.resizable(False, False)
    root.configure(bg=COL["bg"])
    if topmost or selftest_ms:
        root.attributes("-topmost", True)
    if locked:
        root.overrideredirect(True)  # sans bordure => non deplacable, non redimensionnable

    cv = tk.Canvas(root, width=W, height=H, bg=COL["bg"], bd=0, highlightthickness=0)
    cv.place(x=0, y=0, width=W, height=H)
    if os.path.isfile(FOND):
        try:
            bg_img = tk.PhotoImage(file=FOND)
        except Exception:
            bg_img = None
    paint_background()

    theme = make_theme(theme_key)
    theme.update(state)

    # ---------- menu clic droit / quit ----------
    global menu
    menu = tk.Menu(root, tearoff=0)
    menu.add_command(label="Verrouiller" if not locked else "Deverrouiller (setup)",
                     command=lambda: toggle_lock())
    menu.add_command(label="Quitter", command=root.destroy)
    # NB : option "theme a la volee" a brancher ici si voulu, ex. :
    #   for t in THEMES: menu.add_command(label=t.desc, command=lambda k=t.name: apply_theme(k))
    cv.bind("<Button-3>", show_menu)
    root.bind("<Button-3>", show_menu)
    root.bind("<Alt-F4>", lambda e: root.destroy())

    if selftest_ms:
        print(f"selftest: theme {theme.name} ({theme.desc}) {selftest_ms}ms")
        root.after(selftest_ms, root.destroy)

    root.after(interval, tick)
    root.mainloop()
    return 0


menu = None

if __name__ == "__main__":
    sys.exit(main())
