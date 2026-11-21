"""SensorPanel 480x320 — remplacant leger d'AIDA64 SensorPanel.
Themes d'affichage, fenetre 480x320 verrouillee
pour petit moniteur. Donnees : CPU usage via psutil, temp CPU via LibreHardwareMonitor
(admin requis sur Ryzen), GPU via NVML (pynvml) avec fallback nvidia-smi.
Choix du theme : config.ini `theme = 13-neon` ou `--theme=6` en ligne de commande.
Changement a chaud : apply_theme("6") — pret a etre branche sur un menu (a la volee).
Test rapide : `python sensor_panel.py --theme=6 --selftest=4000` (auto-quit).
"""
import configparser
import ctypes
from ctypes import wintypes
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
HN = 300                 # points d'historique (5 min a 1 Hz)
locked = True
topmost = True
interval = 1000
paused = False
_cfg_mtime = None
HIST_WINDOW_MS = 300000
SPEED_MS = {"high": 500, "normal": 1000, "low": 4000, "paused": 0}
want_cpu_temp = True

CPU_NAME = "CPU"
GPU_NAME = "GPU"
ADMIN = False
HAVE_PSUTIL = False
HAVE_NVML = False
_gpu = None
_lhm_comp = None
_lhm_cpu = None
_net_prev = None
_smi_missing = False
_last_pos = None
_cfg_save_job = None

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
    global HAVE_PSUTIL, HAVE_NVML, _gpu, GPU_NAME, _lhm_comp, _lhm_cpu, CPU_NAME
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
            _lhm_comp = comp
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


def cleanup_providers():
    """Ferme proprement LHM, NVML et les compteurs PDH a la sortie."""
    global _lhm_comp, _lhm_cpu
    try:
        _task_meters.close()
    except Exception:
        pass
    if _lhm_comp is not None:
        try:
            _lhm_comp.Close()
        except Exception:
            pass
        _lhm_comp = None
        _lhm_cpu = None
    if HAVE_NVML:
        try:
            from pynvml import nvmlShutdown
            nvmlShutdown()
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
    global _smi_missing
    if _smi_missing:
        return None, None
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,temperature.gpu,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2,
            creationflags=0x08000000)
        if out.returncode != 0:
            return None, None
        parts = out.stdout.strip().split(",")
        return float(parts[1]), float(parts[2])
    except FileNotFoundError:
        _smi_missing = True
        return None, None
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


def _blank_extra():
    return {
        "ru": 0.0, "rg": 0.0, "rt": 0.0,
        "du": 0.0, "nd": 0.0, "nu": 0.0,
        "cf": 0.0, "vm": None, "vg": 0.0, "vt": 0.0,
        "pw": None, "up": 0.0,
    }


def extra_stats():
    """RAM, disque, reseau, frequence, VRAM, puissance, uptime. Jamais d'exception."""
    global _net_prev
    out = _blank_extra()
    ps = _psutil_mod
    if ps is not None:
        try:
            mem = ps.virtual_memory()
            out["ru"] = float(mem.percent)
            out["rg"] = mem.used / (1024 ** 3)
            out["rt"] = mem.total / (1024 ** 3)
        except Exception:
            pass
        try:
            out["du"] = float(ps.disk_usage("C:\\").percent)
        except Exception:
            pass
        try:
            freq = ps.cpu_freq()
            if freq is not None and freq.current:
                out["cf"] = float(freq.current)
        except Exception:
            pass
        try:
            out["up"] = max(0.0, time.time() - float(ps.boot_time()))
        except Exception:
            pass
        try:
            io = ps.net_io_counters()
            now = time.time()
            if _net_prev is not None:
                dt = now - _net_prev[0]
                if dt > 0.2:
                    out["nu"] = max(0.0, (io.bytes_sent - _net_prev[1]) / dt / 1e6)
                    out["nd"] = max(0.0, (io.bytes_recv - _net_prev[2]) / dt / 1e6)
            _net_prev = (now, io.bytes_sent, io.bytes_recv)
        except Exception:
            pass
    if HAVE_NVML and _gpu is not None:
        try:
            from pynvml import nvmlDeviceGetMemoryInfo
            mem = nvmlDeviceGetMemoryInfo(_gpu)
            if mem.total:
                out["vt"] = mem.total / (1024 ** 3)
                out["vg"] = mem.used / (1024 ** 3)
                out["vm"] = 100.0 * mem.used / mem.total
        except Exception:
            pass
        try:
            from pynvml import nvmlDeviceGetPowerUsage
            out["pw"] = nvmlDeviceGetPowerUsage(_gpu) / 1000.0
        except Exception:
            pass
    return out


class _PdhFmt(ctypes.Structure):
    _fields_ = [("status", wintypes.DWORD), ("value", ctypes.c_double),
                ("a", wintypes.LONG), ("b", ctypes.c_longlong)]


class _TaskMeters:
    """Compte les mêmes grandeurs que le Gestionnaire des tâches."""

    _ENGINES = ("3D", "Copy", "VideoDecode", "VideoEncode", "Compute")
    _pdh_ready = False

    def __init__(self):
        self.query = None
        self.primed = False
        self.sig = None
        self.base_mhz = 0.0
        self.cpu = None
        self.perf = None
        self.disks = []
        self.nics = []
        self.engines = []
        self.vrams = []
        self._names = None

    @classmethod
    def _init_pdh(cls):
        if cls._pdh_ready:
            return
        pdh = ctypes.windll.pdh
        pdh.PdhExpandWildCardPathW.argtypes = [
            wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
        pdh.PdhExpandWildCardPathW.restype = wintypes.LONG
        pdh.PdhOpenQueryW.argtypes = [
            wintypes.LPCWSTR, ctypes.c_size_t, ctypes.POINTER(wintypes.HANDLE)]
        pdh.PdhOpenQueryW.restype = wintypes.LONG
        pdh.PdhCloseQuery.argtypes = [wintypes.HANDLE]
        pdh.PdhCloseQuery.restype = wintypes.LONG
        pdh.PdhAddEnglishCounterW.argtypes = [
            wintypes.HANDLE, wintypes.LPCWSTR, ctypes.c_size_t,
            ctypes.POINTER(wintypes.HANDLE)]
        pdh.PdhAddEnglishCounterW.restype = wintypes.LONG
        pdh.PdhCollectQueryData.argtypes = [wintypes.HANDLE]
        pdh.PdhCollectQueryData.restype = wintypes.LONG
        pdh.PdhGetFormattedCounterValue.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(_PdhFmt)]
        pdh.PdhGetFormattedCounterValue.restype = wintypes.LONG
        cls._pdh_ready = True

    def close(self):
        if self.query:
            try:
                self._init_pdh()
                ctypes.windll.pdh.PdhCloseQuery(self.query)
            except Exception:
                pass
            self.query = None

    def _loc(self, english):
        if self._names is None:
            import winreg

            def load(lang):
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Perflib\\" + lang
                ) as key:
                    data, _ = winreg.QueryValueEx(key, "Counter")
                idx, names = {}, {}
                it = iter(data)
                for a, b in zip(it, it):
                    idx[int(a)] = b
                    names[b.lower()] = int(a)
                return idx, names
            en_idx, en_name = load("009")
            try:
                fr_idx, _fr = load("00C")
            except OSError:
                fr_idx = en_idx
            self._names = (en_name, fr_idx)
        en_name, fr_idx = self._names
        i = en_name.get(english.lower())
        if i is None:
            return None
        return fr_idx.get(i)

    def _expand(self, path):
        self._init_pdh()
        pdh = ctypes.windll.pdh
        need = wintypes.DWORD(0)
        pdh.PdhExpandWildCardPathW(None, path, None, ctypes.byref(need), 0)
        if need.value <= 0:
            return []
        buf = ctypes.create_unicode_buffer(need.value + 2)
        if pdh.PdhExpandWildCardPathW(None, path, buf, ctypes.byref(need), 0) != 0:
            return []
        data = "".join(buf[i] for i in range(need.value))
        return [p for p in data.split("\x00") if p]

    @staticmethod
    def _inst(path):
        a = path.find("(")
        b = path.rfind(")\\")
        if a < 0 or b <= a:
            return None
        return path[a + 1:b]

    def _base(self):
        import winreg
        vals = []
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor"
        ) as key:
            for i in range(winreg.QueryInfoKey(key)[0]):
                with winreg.OpenKey(key, winreg.EnumKey(key, i)) as sub:
                    mhz, _typ = winreg.QueryValueEx(sub, "~MHz")
                    vals.append(float(mhz))
        return sum(vals) / len(vals) if vals else 0.0

    def _ensure(self):
        self._init_pdh()
        disks, nics, engines, vrams = [], [], [], []
        disk_obj = self._loc("PhysicalDisk")
        idle = self._loc("% Idle Time")
        if disk_obj and idle:
            for path in self._expand("\\" + disk_obj + "(*)\\" + idle):
                inst = self._inst(path)
                if inst and inst != "_Total":
                    disks.append(r"\PhysicalDisk(" + inst + r")\% Idle Time")
        if not disks:
            disks.append(r"\PhysicalDisk(_Total)\% Idle Time")
        nic = self._loc("Network Interface")
        rx = self._loc("Bytes Received/sec")
        if nic and rx:
            for path in self._expand("\\" + nic + "(*)\\" + rx):
                inst = self._inst(path)
                if inst:
                    nics.append(inst)
        engines = self._expand(r"\GPU Engine(*)\Utilization Percentage")
        vrams = self._expand(r"\GPU Adapter Memory(*)\Dedicated Usage")
        sig = (tuple(disks), tuple(nics), tuple(engines), tuple(vrams))
        if sig == self.sig and self.query:
            return
        pdh = ctypes.windll.pdh
        if self.query:
            pdh.PdhCloseQuery(self.query)
            self.query = None
        query = wintypes.HANDLE()
        if pdh.PdhOpenQueryW(None, 0, ctypes.byref(query)) != 0:
            return

        def add(path):
            handle = wintypes.HANDLE()
            if pdh.PdhAddEnglishCounterW(query, path, 0, ctypes.byref(handle)) != 0:
                return None
            return handle
        self.query = query
        self.primed = False
        self.sig = sig
        self.base_mhz = self.base_mhz or self._base()
        self.cpu = add(r"\Processor Information(_Total)\% Processor Time")
        self.perf = add(r"\Processor Information(_Total)\% Processor Performance")
        self.disks = [h for h in (add(p) for p in disks) if h]
        self.nics = []
        for inst in nics:
            rh = add(r"\Network Interface(" + inst + r")\Bytes Received/sec")
            sh = add(r"\Network Interface(" + inst + r")\Bytes Sent/sec")
            if rh or sh:
                self.nics.append((rh, sh))
        self.engines = []
        for path in engines:
            kind = ""
            mark = path.find("engtype_")
            if mark >= 0:
                kind = path[mark + 8:].split(")")[0]
            if any(kind == name or kind.startswith(name) for name in self._ENGINES):
                handle = add(path)
                if handle:
                    self.engines.append((kind.split("_")[0], handle))
        self.vrams = [h for h in (add(p) for p in vrams) if h]

    def _read(self, handle):
        if not handle:
            return None
        fmt = _PdhFmt()
        st = ctypes.windll.pdh.PdhGetFormattedCounterValue(
            handle, 0x00000200, None, ctypes.byref(fmt))
        if st != 0 or fmt.status not in (0, 1):
            return None
        return float(fmt.value)

    def sample(self):
        try:
            self._ensure()
            if not self.query:
                return {}
            ctypes.windll.pdh.PdhCollectQueryData(self.query)
            if not self.primed:
                self.primed = True
                return {}
            out = {}
            cpu = self._read(self.cpu)
            if cpu is not None:
                out["cpu"] = max(0.0, min(100.0, cpu))
            perf = self._read(self.perf)
            if perf is not None and self.base_mhz > 0:
                out["freq"] = self.base_mhz * perf / 100.0
            active = []
            for handle in self.disks:
                idle = self._read(handle)
                if idle is not None:
                    active.append(max(0.0, min(100.0, 100.0 - idle)))
            if active:
                out["disk"] = max(active)
            best = -1.0
            for rh, sh in self.nics:
                rx = self._read(rh) or 0.0
                tx = self._read(sh) or 0.0
                if rx + tx >= best:
                    best = rx + tx
                    out["down"] = max(0.0, rx) * 8.0 / 1e6
                    out["up"] = max(0.0, tx) * 8.0 / 1e6
            sums = {}
            for kind, handle in self.engines:
                val = self._read(handle)
                if val is not None and val > 0:
                    sums[kind] = sums.get(kind, 0.0) + val
            if self.engines:
                out["gpu"] = min(100.0, max(sums.values()) if sums else 0.0)
            used = [self._read(h) for h in self.vrams]
            used = [v for v in used if v is not None]
            if used:
                out["vram"] = max(used)
            return out
        except Exception:
            return {}


_task_meters = _TaskMeters()


# ================= position : auto-detecte le moniteur 480x320 =================
def monitors_all():
    """Retourne [(x, y, w, h)] pour chaque moniteur (coords physiques)."""
    found = []
    try:
        from ctypes import WINFUNCTYPE, POINTER, windll
        from ctypes.wintypes import BOOL, HMONITOR, HDC, RECT, LPARAM
        user32 = windll.user32
        CB = WINFUNCTYPE(BOOL, HMONITOR, HDC, POINTER(RECT), LPARAM)

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


def temp_int(t):
    return "--°C" if t is None else f"{t:.0f}°C"


def hist_span():
    """Duree couverte par les courbes, d'apres l'intervalle et le nombre de points."""
    sec = max(1, int(round(HN * max(interval, 1) / 1000.0)))
    if sec >= 60 and sec % 60 == 0:
        return "%d MIN" % (sec // 60)
    return "%d S" % sec


def frise_bar(x0, i, bw, top, bottom):
    """Barre de la frise. L'espace entre barres disparait quand elles sont trop fines."""
    pad = 1.0 if bw >= 3.0 else 0.0
    x1 = x0 + i * bw + pad
    x2 = x0 + (i + 1) * bw - pad
    if x2 <= x1:
        x2 = x1 + 1
    return x1, top, x2, bottom


def uptime_str(sec):
    sec = int(max(0, sec))
    days, rem = divmod(sec, 86400)
    hours, rem = divmod(rem, 3600)
    mins = rem // 60
    if days:
        return f"{days}j {hours}h"
    return f"{hours}h {mins:02d}"


def go_str(n):
    return f"{n:.0f}" if n >= 10 else f"{n:.1f}"


def rate_str(mbits):
    if mbits >= 10:
        return f"{mbits:.0f}"
    if mbits >= 1:
        return f"{mbits:.1f}"
    return f"{mbits:.2f}"


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

    def T(self, x, y, txt, px, fill, anchor="nw", budget=None, sample=None):
        """Texte + ombre, avec suivi d'id pour maj. budget = largeur max en px (auto-fit)."""
        if budget is not None:
            px = self._fit_px(sample or txt, px, budget)
        return stext(self.cv, x, y, txt, self.f(px), fill, anchor)

    def _ascent(self, px):
        try:
            return tkfont.Font(family=self.F, size=-max(6, int(px))).metrics("ascent")
        except Exception:
            return int(px * 0.8)

    def temp_group(self, x, y, px, fill, unit_px=13, unit_fill=None, budget=None):
        """Valeur + unite °C plus petite, alignee sur la ligne de base."""
        ids = self.T(x, y, "100.0", px, fill, budget=budget)
        uy = y + self._ascent(px) - self._ascent(unit_px)
        unit = self.T(x, uy, " °C", unit_px, unit_fill or fill)
        return dict(ids=ids, unit=unit, x=x, y=y, uy=uy, px=px, upx=unit_px)

    def temp_group_set(self, grp, txt):
        stext_set(self.cv, grp["ids"], txt)
        ux = grp["x"] + self._measure(txt, grp["px"]) + 2
        self.cv.coords(grp["unit"][0], ux + 1, grp["uy"] + 1)
        self.cv.coords(grp["unit"][1], ux, grp["uy"])

    def temp_group_c(self, cx, y, px, fill, unit_px=13, unit_fill=None):
        """Comme temp_group, mais recentre valeur + unite sur cx a chaque maj."""
        ids = self.T(cx, y, "100.0", px, fill)
        uy = y + self._ascent(px) - self._ascent(unit_px)
        unit = self.T(cx, uy, " °C", unit_px, unit_fill or fill)
        return dict(ids=ids, unit=unit, cx=cx, y=y, uy=uy, px=px, upx=unit_px)

    def temp_group_c_set(self, grp, txt):
        stext_set(self.cv, grp["ids"], txt)
        nw = self._measure(txt, grp["px"])
        total = nw + 2 + self._measure(" °C", grp["upx"])
        left = grp["cx"] - total / 2.0
        self.cv.coords(grp["ids"][0], left + 1, grp["y"] + 1)
        self.cv.coords(grp["ids"][1], left, grp["y"])
        self.cv.coords(grp["unit"][0], left + nw + 3, grp["uy"] + 1)
        self.cv.coords(grp["unit"][1], left + nw + 2, grp["uy"])

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
    """01 · Heritage AIDA+ : fidele au layout AIDA64 (Fond.png + noms/temps + 2 graphes)."""
    name = "01-aida"
    desc = "Heritage AIDA+"

    def build(self):
        cv_, C = self.cv, self.C
        self.g1, self.g2 = (0, 40, 479, 119), (0, 200, 479, 119)
        for (x, y, w, h) in (self.g1, self.g2):
            cv_.create_rectangle(x, y, x + w, y + h, outline=C["grid"], fill="")
        self.t_name_c = self.T(10, 10, self.cpu_name, 16, C["label"], budget=355)
        self.t_temp_c = self.T(474, 10, "--°C", 16, C["label"], anchor="ne",
                               budget=95, sample="100°C")
        self.t_name_g = self.T(10, 170, self.gpu_name, 16, C["label"], budget=355)
        self.t_temp_g = self.T(474, 170, "--°C", 16, C["label"], anchor="ne",
                               budget=95, sample="100°C")
        self.sparks = []
        for (x, y, w, h), key, col in ((self.g1, "cpu", C["graph"]), (self.g2, "gpu", C["graph2"])):
            line = cv_.create_line(0, 0, 0, 0, fill=col, width=2)
            self.sparks.append((x + 1, y + 1, w - 2, h - 2, key, line))

    def update(self, s):
        cv_ = self.cv
        for x, y, w, h, key, line in self.sparks:
            hist = s["hc"] if key == "cpu" else s["hg"]
            cv_.coords(line, *pts_line(hist, x, y, w, h))
        ct, gt = s["ct"], s["gt"]
        stext_set(cv_, self.t_temp_c, temp_int(ct))
        stext_set(cv_, self.t_temp_g, temp_int(gt))


class T02Hud(ThemeBase):
    """02 · HUD : deux moities, temp enorme, barre de charge, graphe encadre."""
    name = "02-hud"
    desc = "HUD grands chiffres"

    def build(self):
        cv_, C = self.cv, self.C
        cv_.create_line(240, 8, 240, 312, fill=C["frame"])
        self.halves = []
        for ox, key in ((0, "cpu"), (240, "gpu")):
            col = C["graph"] if key == "cpu" else C["graph2"]
            cx = ox + 120
            name = self.cpu_name if key == "cpu" else self.gpu_name
            self.T(cx, 10, name, 13, C["label"], anchor="n", budget=216)
            t_temp = self.T(cx, 42, "--°C", 34, C["value"], anchor="n",
                            budget=208, sample="100°C")
            cv_.create_text(ox + 16, 112, text="CHARGE", anchor="nw",
                            font=self.f(10), fill=C["grid"])
            t_pct = self.T(ox + 224, 106, "-- %", 18, C["label"], anchor="ne",
                           budget=110, sample="100 %")
            bx, bw, by = ox + 16, 208, 138
            cv_.create_rectangle(bx, by, bx + bw, by + 9, outline=C["grid"], fill="")
            bar = cv_.create_rectangle(bx + 1, by + 1, bx + 1, by + 8, outline="", fill=col)
            sx, sw, sy, sh = ox + 16, 208, 166, 138
            cv_.create_rectangle(sx, sy, sx + sw, sy + sh, outline=C["grid"], fill="")
            line = cv_.create_line(0, 0, 0, 0, fill=col, width=2)
            self.halves.append(dict(key=key, color=col, t_temp=t_temp, t_pct=t_pct,
                                    bar=bar, bx=bx, bw=bw, by=by,
                                    sx=sx + 1, sy=sy + 1, sw=sw - 2, sh=sh - 2, line=line))

    def update(self, s):
        cv_ = self.cv
        for h in self.halves:
            key = h["key"]
            use = s["cu"] if key == "cpu" else s["gu"]
            hist = s["hc"] if key == "cpu" else s["hg"]
            stext_set(cv_, h["t_temp"], temp_int(s["ct"] if key == "cpu" else s["gt"]))
            stext_set(cv_, h["t_pct"], f"{use:.0f} %")
            cv_.coords(h["bar"], h["bx"] + 1, h["by"] + 1,
                       h["bx"] + 1 + (h["bw"] - 2) * use / 100.0, h["by"] + 8)
            cv_.coords(h["line"], *pts_line(hist, h["sx"], h["sy"], h["sw"], h["sh"]))


class T03Anneaux(ThemeBase):
    """03 · Anneaux : jauges circulaires 240°, temp au centre, graphes encadres."""
    name = "03-anneaux"
    desc = "Anneaux (jauges)"

    def build(self):
        cv_, C = self.cv, self.C
        self.gs = []
        for cx, key in ((120, "cpu"), (360, "gpu")):
            col = C["graph"] if key == "cpu" else C["graph2"]
            r, cy = 68, 108
            cv_.create_arc(cx - r, cy - r, cx + r, cy + r, start=210, extent=-240,
                           style=tk.ARC, outline=C["frame"], width=8)
            val = cv_.create_arc(cx - r, cy - r, cx + r, cy + r, start=210, extent=-240,
                                 style=tk.ARC, outline=col, width=8)
            for cdeg in (-120, -60, 0, 60, 120):
                x0, y0 = compass(cx, cy, r + 8, cdeg)
                x1, y1 = compass(cx, cy, r + 13, cdeg)
                cv_.create_line(x0, y0, x1, y1, fill=C["grid"], width=2)
            name = self.cpu_name if key == "cpu" else self.gpu_name
            self.T(cx, 10, name, 12, C["label"], anchor="n", budget=216)
            t_temp = self.T(cx, 82, "--°C", 24, C["value"], anchor="n",
                            budget=114, sample="100°C")
            t_use = self.T(cx, 118, f"{key.upper()} · -- %", 13, C["label"], anchor="n",
                           budget=106, sample=f"{key.upper()} · 100 %")
            self.gs.append(dict(key=key, val=val, t_temp=t_temp, t_use=t_use))
        self.sparks = []
        for sx, key in ((12, "cpu"), (252, "gpu")):
            col = C["graph"] if key == "cpu" else C["graph2"]
            sy, sw, sh = 204, 216, 104
            cv_.create_text(sx + 2, 188, text=key.upper(), anchor="nw",
                            font=self.f(9), fill=C["grid"])
            cv_.create_rectangle(sx, sy, sx + sw, sy + sh, outline=C["grid"], fill="")
            line = cv_.create_line(0, 0, 0, 0, fill=col, width=2)
            self.sparks.append(dict(key=key, sx=sx + 1, sy=sy + 1,
                                    sw=sw - 2, sh=sh - 2, line=line))

    def update(self, s):
        cv_ = self.cv
        for g in self.gs:
            key = g["key"]
            use = s["cu"] if key == "cpu" else s["gu"]
            cv_.itemconfig(g["val"], extent=-240.0 * use / 100.0)
            stext_set(cv_, g["t_temp"], temp_int(s["ct"] if key == "cpu" else s["gt"]))
            stext_set(cv_, g["t_use"], f"{key.upper()} · {use:.0f} %")
        for sp in self.sparks:
            hist = s["hc"] if sp["key"] == "cpu" else s["hg"]
            cv_.coords(sp["line"], *pts_line(hist, sp["sx"], sp["sy"], sp["sw"], sp["sh"]))


class T04Tuiles(ThemeBase):
    """04 · Tuiles 2x2 : temp/charge CPU a gauche, temp/charge GPU a droite."""
    name = "04-tuiles"
    desc = "Tuiles 2x2"

    def build(self):
        cv_, C = self.cv, self.C
        tiles = [
            (6, 6, 228, 148, "CPU · TEMPÉRATURE", "htc", "°C"),
            (246, 6, 228, 148, "CPU · CHARGE", "hc", "%"),
            (6, 166, 228, 148, "GPU · TEMPÉRATURE", "htg", "°C"),
            (246, 166, 228, 148, "GPU · CHARGE", "hg", "%"),
        ]
        self.tiles = []
        for (x, y, w, h, label, hkey, unit) in tiles:
            col = C["graph"] if "CPU" in label else C["graph2"]
            cv_.create_rectangle(x, y, x + w, y + h, outline=C["grid"], fill="")
            sx, sy, sw, sh = x + 12, y + 88, w - 24, 50
            cv_.create_rectangle(sx, sy, sx + sw, sy + sh, outline=C["frame"], fill="")
            line = cv_.create_line(0, 0, 0, 0, fill=col, width=2)
            self.T(x + 12, y + 10, label, 10, C["grid"])
            sample = "100°C" if unit == "°C" else "100 %"
            t_val = self.T(x + 12, y + 32, "--", 32, C["value"],
                           budget=w - 24, sample=sample)
            self.tiles.append(dict(col=col, hkey=hkey, unit=unit, t_val=t_val,
                                   sx=sx + 1, sy=sy + 1, sw=sw - 2, sh=sh - 2, line=line))

    def update(self, s):
        cv_ = self.cv
        for t in self.tiles:
            if t["unit"] == "°C":
                val = temp_int(s["ct"] if t["hkey"] == "htc" else s["gt"])
            else:
                val = f"{(s['cu'] if t['hkey'] == 'hc' else s['gu']):.0f} %"
            stext_set(cv_, t["t_val"], val)
            hist = s[t["hkey"]]
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
        cv_.create_line(240, 8, 240, 312, fill=C["frame"])
        self.cols = []
        for ox, key in ((0, "cpu"), (240, "gpu")):
            col = C["graph"] if key == "cpu" else C["graph2"]
            cx = ox + 196
            rects = []
            for i in range(self.SEGS):
                yy = self.SEG_TOP + (self.SEGS - 1 - i) * (self.SEG_H + self.SEG_GAP)
                rid = cv_.create_rectangle(cx, yy, cx + 28, yy + self.SEG_H,
                                           outline=C["grid"], fill="")
                rects.append(rid)
            sx, sy, sw, sh = ox + 14, 142, 170, 162
            cv_.create_rectangle(sx, sy, sx + sw, sy + sh, outline=C["grid"], fill="")
            line = cv_.create_line(0, 0, 0, 0, fill=col, width=2)
            name = self.cpu_name if key == "cpu" else self.gpu_name
            self.T(ox + 14, 10, name, 12, C["label"], budget=212)
            t_temp = self.T(ox + 14, 38, "--°C", 26, C["value"],
                            budget=172, sample="100°C")
            t_use = self.T(ox + 14, 78, "-- %", 26, col,
                           budget=172, sample="100 %")
            self.T(ox + 14, 118, "CHARGE", 9, C["grid"])
            self.cols.append(dict(key=key, color=col, rects=rects, t_temp=t_temp, t_use=t_use,
                                  sx=sx + 1, sy=sy + 1, sw=sw - 2, sh=sh - 2, line=line))

    def update(self, s):
        cv_ = self.cv
        for c in self.cols:
            key = c["key"]
            use = s["cu"] if key == "cpu" else s["gu"]
            level = self.SEGS * use / 100.0
            for i, rid in enumerate(c["rects"]):
                seg_set(cv_, rid, c["color"], max(0.0, min(1.0, level - i)))
            stext_set(cv_, c["t_temp"], temp_int(s["ct"] if key == "cpu" else s["gt"]))
            stext_set(cv_, c["t_use"], f"{use:.0f} %")
            hist = s["hc"] if key == "cpu" else s["hg"]
            cv_.coords(c["line"], *pts_line(hist, c["sx"], c["sy"], c["sw"], c["sh"]))


class T06Oscillo(ThemeBase):
    """06 · Oscilloscope : une grande courbe, CPU plein + GPU en tirets."""
    name = "06-oscillo"
    desc = "Oscilloscope"

    def build(self):
        cv_, C = self.cv, self.C
        gx, gy, gw, gh = 10, 24, 460, 164
        self.g = (gx + 1, gy + 1, gw - 2, gh - 2)
        cv_.create_rectangle(gx, gy, gx + gw, gy + gh, outline=C["grid"], fill="")
        cv_.create_line(gx, gy + gh / 2.0, gx + gw, gy + gh / 2.0, fill=C["frame"])
        self.line_c = cv_.create_line(0, 0, 0, 0, fill=C["graph"], width=2)
        self.line_g = cv_.create_line(0, 0, 0, 0, fill=C["graph2"], width=2, dash=(5, 4))
        maj = "EN PAUSE" if paused else f"MAJ {interval / 1000.0:g} S"
        cv_.create_text(gx, 6, text=maj, anchor="nw", font=self.f(9), fill=C["grid"])
        cv_.create_line(366, 12, 384, 12, fill=C["graph"], width=2)
        cv_.create_text(388, 6, text="CPU", anchor="nw", font=self.f(9), fill=C["grid"])
        cv_.create_line(426, 12, 444, 12, fill=C["graph2"], width=2, dash=(4, 3))
        cv_.create_text(448, 6, text="GPU", anchor="nw", font=self.f(9), fill=C["grid"])
        for bx in (10, 250):
            cv_.create_rectangle(bx, 272, bx + 220, 281, outline=C["grid"], fill="")
        self.bar_c = cv_.create_rectangle(11, 273, 11, 280, outline="", fill=C["graph"])
        self.bar_g = cv_.create_rectangle(251, 273, 251, 280, outline="", fill=C["graph2"])
        self.t_temp_c = self.T(10, 200, "--°C", 28, C["value"],
                               budget=220, sample="100°C")
        self.t_temp_g = self.T(250, 200, "--°C", 28, C["value"],
                               budget=220, sample="100°C")
        self.t_use_c = self.T(10, 248, "CPU · -- %", 12, C["label"],
                              budget=220, sample="CPU · 100 %")
        self.t_use_g = self.T(250, 248, "GPU · -- %", 12, C["label"],
                              budget=220, sample="GPU · 100 %")
        self.T(10, 290, self.cpu_name, 11, C["grid"], budget=220)
        self.T(250, 290, self.gpu_name, 11, C["grid"], budget=220)

    def update(self, s):
        cv_ = self.cv
        x, y, w, h = self.g
        cv_.coords(self.line_c, *pts_line(s["hc"], x, y, w, h))
        cv_.coords(self.line_g, *pts_line(s["hg"], x, y, w, h))
        cv_.coords(self.bar_c, 11, 273, 11 + 218 * s["cu"] / 100.0, 280)
        cv_.coords(self.bar_g, 251, 273, 251 + 218 * s["gu"] / 100.0, 280)
        stext_set(cv_, self.t_temp_c, temp_int(s["ct"]))
        stext_set(cv_, self.t_temp_g, temp_int(s["gt"]))
        stext_set(cv_, self.t_use_c, f"CPU · {s['cu']:.0f} %")
        stext_set(cv_, self.t_use_g, f"GPU · {s['gu']:.0f} %")


class T08Frise(ThemeBase):
    """08 · Frise thermique : barres verticales (1 s = 1 barre), hauteur + densite = temp."""
    name = "08-frise"
    desc = "Frise thermique"

    def build(self):
        cv_, C = self.cv, self.C
        self.tracks = []
        n = max(1, HN)
        bw = 310.0 / n
        for oy, key in ((10, "cpu"), (170, "gpu")):
            col = C["graph"] if key == "cpu" else C["graph2"]
            x0, y, w, h = 158, oy + 4, 312, 114
            cv_.create_rectangle(x0, y, x0 + w, y + h, outline=C["grid"], fill="")
            rects = []
            for i in range(n):
                rid = cv_.create_rectangle(*frise_bar(x0 + 1, i, bw, y + h - 6, y + h - 1),
                                           fill=col, stipple="gray50", outline="")
                rects.append(rid)
            name = self.cpu_name if key == "cpu" else self.gpu_name
            short = self.short_suffix(name, 10, 138)
            self.T(10, oy + 2, short, 10, C["label"], budget=138)
            t_temp = self.T(10, oy + 36, "--°C", 28, C["value"],
                            budget=138, sample="100°C")
            t_use = self.T(10, oy + 90, "-- %", 14, col,
                           budget=138, sample="100 %")
            cv_.create_text(x0, oy + 122, text="−" + hist_span(), anchor="nw",
                            font=self.f(8), fill=C["grid"])
            cv_.create_text(x0 + w, oy + 122, text="NOW", anchor="ne",
                            font=self.f(8), fill=C["grid"])
            self.tracks.append(dict(key=key, color=col, x0=x0 + 1, w=w - 2,
                                    y=y + 1, h=h - 2, bw=bw,
                                    rects=rects, t_temp=t_temp, t_use=t_use))

    @staticmethod
    def _bar_levels(v, h=112.0):
        """(hauteur_px, densite 0..1) calculees depuis la temperature."""
        vv = 50.0 if v is None else v
        vv = min(max(vv, 30.0), 90.0)
        bh = max(6.0, (vv - 30.0) / 60.0 * h)
        op = 0.45 + 0.55 * min(1.0, max(0.0, (vv - 40.0) / 40.0))
        return min(bh, h), op

    def update(self, s):
        cv_ = self.cv
        for t in self.tracks:
            key = t["key"]
            hist = s["htc"] if key == "cpu" else s["htg"]
            y, h, bw, x0 = t["y"], t["h"], t["bw"], t["x0"]
            for i, rid in enumerate(t["rects"]):
                v = hist[i] if i < len(hist) else (hist[-1] if hist else None)
                bh, op = self._bar_levels(v, h)
                cv_.coords(rid, *frise_bar(x0, i, bw, y + h - bh, y + h))
                st = stipple_for_op(op) or ""
                cv_.itemconfig(rid, fill=t["color"], stipple=st)
            stext_set(cv_, t["t_temp"], temp_int(s["ct"] if key == "cpu" else s["gt"]))
            stext_set(cv_, t["t_use"], f"{(s['cu'] if key == 'cpu' else s['gu']):.0f} %")


class T09Split(ThemeBase):
    """09 · Compact splitscreen : CPU a gauche, GPU a droite, graphes encadres."""
    name = "09-split"
    desc = "Compact splitscreen"

    def build(self):
        cv_, C = self.cv, self.C
        cv_.create_line(240, 8, 240, 312, fill=C["frame"])
        self.halves = []
        for ox, key in ((0, "cpu"), (240, "gpu")):
            col = C["graph"] if key == "cpu" else C["graph2"]
            sx, sy, sw, sh = ox + 14, 92, 212, 214
            cv_.create_rectangle(sx, sy, sx + sw, sy + sh, outline=C["grid"], fill="")
            line = cv_.create_line(0, 0, 0, 0, fill=col, width=2)
            name = self.cpu_name if key == "cpu" else self.gpu_name
            self.T(ox + 14, 10, name, 13, C["label"], budget=212)
            t_temp = self.T(ox + 14, 42, "--°C", 28, C["value"],
                            budget=115, sample="100°C")
            t_use = self.T(ox + 226, 46, "-- %", 22, col, anchor="ne",
                           budget=90, sample="100 %")
            self.halves.append(dict(key=key, color=col, t_temp=t_temp, t_use=t_use,
                                    sx=sx + 1, sy=sy + 1, sw=sw - 2, sh=sh - 2, line=line))

    def update(self, s):
        cv_ = self.cv
        for h in self.halves:
            key = h["key"]
            use = s["cu"] if key == "cpu" else s["gu"]
            hist = s["hc"] if key == "cpu" else s["hg"]
            stext_set(cv_, h["t_temp"], temp_int(s["ct"] if key == "cpu" else s["gt"]))
            stext_set(cv_, h["t_use"], f"{use:.0f} %")
            cv_.coords(h["line"], *pts_line(hist, h["sx"], h["sy"], h["sw"], h["sh"]))


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


class T14Flux(ThemeBase):
    """14 · Tableau dense : CPU/GPU, mémoire, disque, réseau, fréquence, puissance."""
    name = "14-flux"
    desc = "Flux système"

    def build(self):
        self.F = "Segoe UI"
        cv_ = self.cv
        cv_.create_rectangle(0, 0, 480, 320, fill="#08120E", outline="")
        for x in range(0, 480, 24):
            cv_.create_line(x, 0, x, 320, fill="#0E1C16")
        for r in (48, 96, 150):
            cv_.create_oval(400 - r, -30 - r, 400 + r, -30 + r, outline="#163228")
        self.T(14, 8, "FLUX", 13, "#D7F5E4")
        self.t_up = self.T(240, 10, "0h 00", 11, "#8FB8A4", anchor="n")
        self.t_clock = self.T(466, 8, "--:--", 13, "#F0C14A", anchor="ne")
        self.cards = []
        for left, key, accent, title, name in (
                (10, "cpu", "#5EE0A0", "CPU", self.cpu_name),
                (246, "gpu", "#F0C14A", "GPU", self.gpu_name)):
            cv_.create_rectangle(left, 34, left + 224, 186, fill="#0E1C16", outline="#1C3A2E")
            self.T(left + 12, 42, title, 10, accent)
            self.T(left + 12, 58, self.short_suffix(name, 9, 198), 9, "#8AA399", budget=198)
            t_temp = self.T(left + 12, 76, "--°", 34, "#F4F7F2", budget=130)
            t_use = self.T(left + 210, 86, "--%", 16, accent, anchor="ne", budget=70)
            cv_.create_rectangle(left + 12, 124, left + 210, 132, fill="#13241C", outline="")
            bar = cv_.create_rectangle(left + 12, 124, left + 12, 132, fill=accent, outline="")
            line = cv_.create_line(0, 0, 0, 0, fill=accent, width=2, smooth=True)
            self.cards.append(dict(
                key=key, accent=accent, t_temp=t_temp, t_use=t_use, bar=bar,
                bx=left + 12, bw=198, by=124, sx=left + 12, sy=140, sw=198, sh=34, line=line))
        self.rows = []
        for y, key, label, color in (
                (198, "ram", "MÉMOIRE", "#7EC8E3"),
                (222, "vram", "VRAM", "#C9B6E4"),
                (246, "disk", "DISQUE", "#E07A5F")):
            self.T(14, y, label, 10, color, budget=78)
            t_pct = self.T(98, y, "--%", 12, "#F4F7F2", budget=52)
            cv_.create_rectangle(156, y + 4, 332, y + 13, fill="#13241C", outline="")
            bar = cv_.create_rectangle(156, y + 4, 156, y + 13, fill=color, outline="")
            t_det = self.T(340, y, "", 10, "#A8BDB2", budget=126)
            self.rows.append(dict(key=key, color=color, t_pct=t_pct, t_det=t_det,
                                   bar=bar, bx=156, bw=176, by=y + 4))
        cv_.create_line(14, 270, 466, 270, fill="#1C3A2E")
        self.bits = []
        for x, key, label in (
                (14, "cf", "FRÉQUENCE"),
                (132, "pw", "PUISSANCE"),
                (250, "nd", "↓ Mbit/s"),
                (366, "nu", "↑ Mbit/s")):
            self.T(x, 276, label, 8, "#7E9488")
            t_val = self.T(x, 290, "--", 14, "#F4F7F2", budget=108)
            self.bits.append((key, t_val))

    def _fill(self, bar, bx, by, bw, frac, color):
        frac = max(0.0, min(1.0, frac))
        self.cv.coords(bar, bx, by, bx + bw * frac, by + 8)
        self.cv.itemconfig(bar, fill=color)

    def update(self, s):
        cv_ = self.cv
        stext_set(cv_, self.t_clock, time.strftime("%H:%M"))
        stext_set(cv_, self.t_up, uptime_str(s.get("up", 0)))
        for c in self.cards:
            cpu = c["key"] == "cpu"
            temp = s["ct"] if cpu else s["gt"]
            use = s["cu"] if cpu else s["gu"]
            hist = s["hc"] if cpu else s["hg"]
            stext_set(cv_, c["t_temp"], "--°" if temp is None else f"{temp:.0f}°")
            stext_set(cv_, c["t_use"], f"{use:.0f}%")
            self._fill(c["bar"], c["bx"], c["by"], c["bw"], use / 100.0, c["accent"])
            cv_.coords(c["line"], *pts_line(hist, c["sx"], c["sy"], c["sw"], c["sh"]))
        ram = s.get("ru", 0.0)
        vram = s.get("vm")
        disk = s.get("du", 0.0)
        details = {
            "ram": (ram, f"{go_str(s.get('rg', 0))} / {go_str(s.get('rt', 0))} Go"),
            "vram": (0.0 if vram is None else vram,
                     "--" if vram is None else f"{go_str(s.get('vg', 0))} / {go_str(s.get('vt', 0))} Go"),
            "disk": (disk, ""),
        }
        for row in self.rows:
            pct, det = details[row["key"]]
            stext_set(cv_, row["t_pct"], "--%" if row["key"] == "vram" and vram is None else f"{pct:.0f}%")
            stext_set(cv_, row["t_det"], det)
            self._fill(row["bar"], row["bx"], row["by"], row["bw"], pct / 100.0, row["color"])
        freq = s.get("cf") or 0.0
        power = s.get("pw")
        bits = {
            "cf": "--" if freq <= 0 else f"{freq / 1000.0:.1f} GHz",
            "pw": "--" if power is None else f"{power:.0f} W",
            "nd": rate_str(s.get("nd", 0.0)),
            "nu": rate_str(s.get("nu", 0.0)),
        }
        for key, tid in self.bits:
            stext_set(cv_, tid, bits[key])


class T15Atelier(ThemeBase):
    """15 · Mosaïque chaude : six mesures, puis mémoire, disque et réseau."""
    name = "15-atelier"
    desc = "Atelier"

    def build(self):
        self.F = "Segoe UI"
        cv_ = self.cv
        cv_.create_rectangle(0, 0, 480, 320, fill="#211612", outline="")
        cv_.create_oval(-90, 170, 230, 490, outline="#3A2822", width=2)
        cv_.create_oval(280, -80, 560, 200, outline="#3A2822", width=2)
        cv_.create_oval(150, 70, 360, 280, outline="#2E201C")
        for x in range(-40, 480, 14):
            cv_.create_line(x, 0, x + 28, 46, fill="#3A2A24")
        self.t_clock = self.T(14, 6, "--:--", 22, "#F8EFE6")
        self.T(148, 14, "ATELIER", 11, "#E7A07A")
        self.t_up = self.T(466, 14, "0h 00", 11, "#C4A090", anchor="ne")
        specs = (
            ("ct", "TEMPÉRATURE CPU", "#E8896A"),
            ("cu", "CHARGE CPU", "#E6C27A"),
            ("cf", "FRÉQUENCE", "#D7C4A1"),
            ("gt", "TEMPÉRATURE GPU", "#8FB8C4"),
            ("gu", "CHARGE GPU", "#CDB4E0"),
            ("pw", "PUISSANCE GPU", "#F0A48A"),
        )
        self.tiles = []
        for i, (key, label, accent) in enumerate(specs):
            col, row = i % 3, i // 3
            x, y = 10 + col * 156, 50 + row * 104
            cv_.create_rectangle(x, y, x + 148, y + 96, fill="#2C211C", outline=accent)
            self.T(x + 10, y + 8, label, 8, "#C4A090", budget=128)
            t_val = self.T(x + 10, y + 28, "100%", 22, accent, budget=128)
            cv_.create_rectangle(x + 10, y + 74, x + 138, y + 82, fill="#3A2C26", outline="")
            bar = cv_.create_rectangle(x + 10, y + 74, x + 10, y + 82, fill=accent, outline="")
            self.tiles.append(dict(key=key, accent=accent, t_val=t_val, bar=bar,
                                    bx=x + 10, by=y + 74, bw=128))
        cv_.create_rectangle(10, 262, 470, 310, fill="#2A1C18", outline="#3A2822")
        self.foot = []
        for i, (key, label, color) in enumerate((
                ("ram", "MÉMOIRE", "#E6C27A"),
                ("vram", "VRAM", "#CDB4E0"),
                ("disk", "DISQUE", "#E8896A"),
                ("net", "Mbit/s", "#8FB8C4"))):
            x = 20 + i * 116
            self.T(x, 268, label, 8, color, budget=100)
            t_val = self.T(x, 282, "--", 12, "#F8EFE6", budget=108)
            bar = None
            if key != "net":
                cv_.create_rectangle(x, 300, x + 96, 306, fill="#3A2C26", outline="")
                bar = cv_.create_rectangle(x, 300, x, 306, fill=color, outline="")
            self.foot.append(dict(key=key, color=color, t_val=t_val, bar=bar, bx=x, bw=96))

    def _fill(self, bar, bx, by, bw, bh, frac, color):
        if bar is None:
            return
        frac = max(0.0, min(1.0, frac))
        self.cv.coords(bar, bx, by, bx + bw * frac, by + bh)
        self.cv.itemconfig(bar, fill=color)

    def update(self, s):
        cv_ = self.cv
        stext_set(cv_, self.t_clock, time.strftime("%H:%M"))
        stext_set(cv_, self.t_up, uptime_str(s.get("up", 0)))
        freq = s.get("cf") or 0.0
        power = s.get("pw")
        vram = s.get("vm")
        shown = {
            "ct": ("--°" if s["ct"] is None else f"{s['ct']:.0f}°",
                   0.0 if s["ct"] is None else s["ct"] / 100.0),
            "cu": (f"{s['cu']:.0f}%", s["cu"] / 100.0),
            "cf": ("--" if freq <= 0 else f"{freq / 1000.0:.1f} GHz",
                   0.0 if freq <= 0 else min(freq / 1000.0, 6.0) / 6.0),
            "gt": ("--°" if s["gt"] is None else f"{s['gt']:.0f}°",
                   0.0 if s["gt"] is None else s["gt"] / 100.0),
            "gu": (f"{s['gu']:.0f}%", s["gu"] / 100.0),
            "pw": ("--" if power is None else f"{power:.0f} W",
                   0.0 if power is None else min(power, 400.0) / 400.0),
        }
        for tile in self.tiles:
            text, frac = shown[tile["key"]]
            stext_set(cv_, tile["t_val"], text)
            self._fill(tile["bar"], tile["bx"], tile["by"], tile["bw"], 8, frac, tile["accent"])
        foot = {
            "ram": (f"{s.get('ru', 0):.0f}%  {go_str(s.get('rg', 0))} Go", s.get("ru", 0) / 100.0),
            "vram": ("--" if vram is None else f"{vram:.0f}%  {go_str(s.get('vg', 0))} Go",
                     0.0 if vram is None else vram / 100.0),
            "disk": (f"{s.get('du', 0):.0f}%", s.get("du", 0) / 100.0),
            "net": (f"↓{rate_str(s.get('nd', 0))}  ↑{rate_str(s.get('nu', 0))}", 0.0),
        }
        for item in self.foot:
            text, frac = foot[item["key"]]
            stext_set(cv_, item["t_val"], text)
            self._fill(item["bar"], item["bx"], 300, item["bw"], 6, frac, item["color"])


_HEAT_STOPS = [
    (30, (11, 42, 51)), (38, (14, 79, 82)), (46, (15, 118, 110)),
    (54, (21, 128, 61)), (62, (101, 163, 13)), (68, (202, 138, 4)),
    (74, (234, 88, 12)), (80, (220, 38, 38)), (100, (127, 29, 29)),
]


def _heat_color(t):
    """Temperature 30..100 -> couleur de cellule (interpolation lineaire)."""
    if t is None:
        return "#14110F"
    t = max(30.0, min(100.0, float(t)))
    for i in range(len(_HEAT_STOPS) - 1):
        t0, c0 = _HEAT_STOPS[i]
        t1, c1 = _HEAT_STOPS[i + 1]
        if t <= t1:
            f = (t - t0) / float(t1 - t0)
            return "#%02X%02X%02X" % tuple(int(c0[j] + (c1[j] - c0[j]) * f) for j in range(3))
    return "#7F1D1D"


def _last_n(hist, n):
    """Derniers n points, completes a gauche par None (cellules vides)."""
    vals = list(hist)[-n:]
    return [None] * (n - len(vals)) + vals


class T16Thermo(ThemeBase):
    """16 — Thermometres a mercure, seuils 65/80 C."""
    name = "16-thermo"
    desc = "Thermo"

    def build(self):
        self.F = "Segoe UI"
        cv_ = self.cv
        cv_.create_rectangle(0, 0, 480, 320, fill="#0B1115", outline="")
        cv_.create_line(0, 32, 480, 32, fill="#0E181E")
        self.T(16, 9, "THERMO", 10, "#93A4B1")
        self.T(240, 9, "MERCURE · 20–100 °C", 8, "#5F7180", anchor="n")
        self.t_clock = self.T(464, 9, "--:--", 8, "#5F7180", anchor="ne")
        cv_.create_line(12, 28, 468, 28, fill="#1B2A33")
        self.thermos = [
            self._one(10, "cpu", self.cpu_name, "#34D399"),
            self._one(246, "gpu", self.gpu_name, "#38BDF8"),
        ]

    def _one(self, px, key, name, accent):
        cv_ = self.cv
        cx = px + 14
        tube = px + 158
        inner = tube + 10
        bulb = tube + 14
        cv_.create_rectangle(px, 38, px + 224, 310, fill="#0F181E", outline="#1E2E38")
        cv_.create_rectangle(px, 38, px + 224, 41, fill=accent, outline="")
        self.T(cx, 51, "CPU" if key == "cpu" else "GPU", 9, accent)
        self.T(cx, 65, name, 8, "#7C8B99", budget=134)
        t_temp = self.temp_group(cx, 80, 40, "#E6EDF3", 13, "#7C8B99")
        self.T(cx, 132, "CHARGE", 7, "#5F7180")
        t_use = self.T(cx, 142, "-- %", 18, accent)
        bx, by, bw = cx, 166, 108
        cv_.create_rectangle(bx, by, bx + bw, by + 5, fill="#1A2730", outline="")
        bar = cv_.create_rectangle(bx, by, bx, by + 5, fill=accent, outline="")
        self.T(cx, 184, "PLAGE", 7, "#5F7180")
        self.T(cx, 194, "20–100 °C", 8, "#A7B7C4")
        t_min = self.T(cx, 212, "MIN --", 7.5, "#5F7180")
        t_max = self.T(cx, 224, "MAX --", 7.5, "#5F7180")
        self.T(cx, 248, "SONDE PACKAGE · MAJ 1 S", 6.5, "#3F505C")
        # tube capsule : contour, fond, puis mercure
        cv_.create_line(tube + 14, 72, tube + 14, 250, width=30,
                        fill="#24333D", capstyle=tk.ROUND)
        cv_.create_line(tube + 14, 72, tube + 14, 250, width=26,
                        fill="#0A0F13", capstyle=tk.ROUND)
        cv_.create_line(inner + 1, 72, inner + 1, 250, width=1, fill="#132029")
        seg_norm = cv_.create_rectangle(0, 0, 0, 0, fill=accent, outline="")
        seg_warm = cv_.create_rectangle(0, 0, 0, 0, fill="#FBBF24", outline="")
        seg_hot = cv_.create_rectangle(0, 0, 0, 0, fill="#FB7185", outline="")
        cv_.create_oval(bulb - 23, 250, bulb + 23, 296, fill="#0A0F13",
                        outline="#24333D", width=1)
        bulb_in = cv_.create_oval(bulb - 20, 253, bulb + 20, 293,
                                  fill=accent, outline="")
        meniscus = cv_.create_line(inner - 1, 250, inner + 9, 250,
                                   fill="#E6EDF3", width=1)
        for v in range(20, 101, 10):
            yy = 250 - (v - 20) / 80.0 * 182
            major = (v % 20 == 0)
            x0 = tube - (11 if major else 5)
            cv_.create_line(x0, yy, tube - 2, yy,
                            fill="#2A3B45" if major else "#1C2A33")
            if major:
                self.T(tube - 14, yy, str(v), 7, "#5F7180", anchor="e")
        return dict(key=key, accent=accent, t_temp=t_temp, t_use=t_use,
                    t_min=t_min, t_max=t_max, bar=bar, bx=bx, by=by, bw=bw,
                    inner=inner, foot=256, seg_norm=seg_norm, seg_warm=seg_warm,
                    seg_hot=seg_hot, bulb=bulb_in, meniscus=meniscus,
                    y65=250 - 45 / 80.0 * 182, y80=250 - 60 / 80.0 * 182)

    def _seg(self, rid, x0, y0, x1, y1):
        if y1 > y0 + 0.2:
            self.cv.coords(rid, x0, y0, x1, y1)
        else:
            self.cv.coords(rid, 0, 0, 0, 0)

    def update(self, s):
        cv_ = self.cv
        stext_set(cv_, self.t_clock, time.strftime("%H:%M"))
        for h in self.thermos:
            cpu = h["key"] == "cpu"
            t = s["ct"] if cpu else s["gt"]
            use = s["cu"] if cpu else s["gu"]
            hist = [v for v in (s["htc"] if cpu else s["htg"]) if v is not None]
            self.temp_group_set(h["t_temp"], "--.-" if t is None else f"{t:.1f}")
            stext_set(cv_, h["t_use"], f"{use:.0f} %")
            stext_set(cv_, h["t_min"], "MIN --" if not hist else f"MIN {min(hist):.1f}°")
            stext_set(cv_, h["t_max"], "MAX --" if not hist else f"MAX {max(hist):.1f}°")
            val = 20.0 if t is None else max(20.0, min(100.0, t))
            ly = 250 - (val - 20) / 80.0 * 182
            self._seg(h["seg_norm"], h["inner"], max(ly, h["y65"]),
                      h["inner"] + 8, h["foot"])
            if ly < h["y65"]:
                self._seg(h["seg_warm"], h["inner"], max(ly, h["y80"]),
                          h["inner"] + 8, h["y65"])
            else:
                self._seg(h["seg_warm"], 0, 0, 0, 0)
            if ly < h["y80"]:
                self._seg(h["seg_hot"], h["inner"], ly, h["inner"] + 8, h["y80"])
            else:
                self._seg(h["seg_hot"], 0, 0, 0, 0)
            cv_.coords(h["meniscus"], h["inner"] - 1, ly, h["inner"] + 9, ly)
            cv_.itemconfig(h["bulb"], fill=_temp_color(t, h["accent"], 65, 80))
            frac = max(0.0, min(1.0, use / 100.0))
            cv_.coords(h["bar"], h["bx"], h["by"],
                       h["bx"] + h["bw"] * frac, h["by"] + 5)


def _spark_pts(vals, x, y, w, h, lo, hi):
    """Sparkline : coordonnees canvas, marge de 3 px, valeurs hors plage bornees."""
    vals = list(vals)
    if not vals:
        return []
    if len(vals) == 1:
        vals = [vals[0], vals[0]]
    n = len(vals)
    span = max(1e-6, float(hi - lo))
    out = []
    for i, v in enumerate(vals):
        p = max(0.0, min(1.0, (v - lo) / span))
        px = x + 3.0 + i * (w - 6.0) / (n - 1.0)
        py = y + 3.0 + (h - 6.0) * (1.0 - p)
        out.extend((px, py))
    return out


class T17Heatmap(ThemeBase):
    """17 · 48 cellules de temperature par sonde (1 cellule = 1 s)."""
    name = "17-heatmap"
    desc = "Heatmap"

    def build(self):
        self.F = "Segoe UI"
        cv_ = self.cv
        cv_.create_rectangle(0, 0, 480, 320, fill="#0A0908", outline="")
        cv_.create_line(0, 32, 480, 32, fill="#14110F")
        self.T(16, 9, "HEATMAP", 10, "#FAFAF9")
        self.T(240, 9, "TEMPÉRATURE · 48 SECONDES", 7.5, "#78716C", anchor="n")
        self.t_clock = self.T(464, 9, "--:--", 8, "#78716C", anchor="ne")
        cv_.create_line(16, 30, 464, 30, fill="#221D18")
        cv_.create_line(240, 42, 240, 130, fill="#221D18")
        self.cards = []
        for px, key, label, accent in ((16, "cpu", "CPU", "#FB923C"),
                                       (248, "gpu", "GPU", "#60A5FA")):
            name = self.cpu_name if key == "cpu" else self.gpu_name
            self.T(px, 40, label, 8, accent)
            self.T(px, 52, name, 7, "#78716C", budget=214)
            t_temp = self.temp_group(px, 62, 40, "#FAFAF9", 13, "#78716C", budget=222)
            self.T(px, 114, "PACKAGE · ACTUEL" if key == "cpu" else "CORE · ACTUEL",
                   6.5, "#57534E")
            t_row = self.T(px, 170 if key == "cpu" else 212, "--.-°", 7, "#A8A29E")
            self.cards.append(dict(key=key, t_temp=t_temp, t_row=t_row))
        self.T(58, 142, "-48 S", 6.5, "#57534E")
        self.T(261, 142, "-24 S", 6.5, "#57534E", anchor="n")
        self.T(464, 142, "MAINT.", 6.5, "#57534E", anchor="ne")
        self.T(16, 158, "CPU", 7.5, "#FB923C")
        self.T(16, 200, "GPU", 7.5, "#60A5FA")
        self.cells = {"cpu": [], "gpu": []}
        step = (464.0 - 58.0) / 48.0
        for key, y0 in (("cpu", 156), ("gpu", 198)):
            ids = []
            for i in range(48):
                xa = 58.0 + i * step + 0.5
                xb = 58.0 + (i + 1) * step - 0.5
                ids.append(cv_.create_rectangle(xa, y0, xb, y0 + 34.0,
                                                fill="#14110F", outline=""))
            cv_.itemconfig(ids[-1], outline="#FAFAF9")
            self.cells[key] = ids
        self.T(16, 246, "TEMPÉRATURE", 6.5, "#57534E")
        for i in range(12):
            gx = 16.0 + i * 19.5
            cv_.create_rectangle(gx, 258, gx + 19.5, 266,
                                 fill=_heat_color(30 + i * 70.0 / 11.0), outline="")
        self.T(16, 270, "30", 6.5, "#78716C")
        self.T(100, 270, "55", 6.5, "#78716C", anchor="n")
        self.T(183, 270, "80", 6.5, "#78716C", anchor="n")
        self.T(250, 270, "100", 6.5, "#78716C", anchor="ne")
        self.T(464, 246, "CELLULE = 1 S", 6.5, "#57534E", anchor="ne")
        self.T(464, 258, "SEUILS 65° / 80°", 6.5, "#A8A29E", anchor="ne")
        self.T(464, 270, "48 POINTS", 6.5, "#57534E", anchor="ne")
        cv_.create_line(16, 292, 464, 292, fill="#221D18")
        self.T(16, 300, "RAFRAÎCHISSEMENT 1 HZ · HISTORIQUE 48 S", 6.5, "#57534E")
        self.T(464, 300, "SOURCE LHM / NVML", 6.5, "#57534E", anchor="ne")

    def update(self, s):
        cv_ = self.cv
        stext_set(cv_, self.t_clock, time.strftime("%H:%M"))
        for card in self.cards:
            cpu = card["key"] == "cpu"
            t = s["ct"] if cpu else s["gt"]
            hist = s["htc"] if cpu else s["htg"]
            self.temp_group_set(card["t_temp"], "--.-" if t is None else f"{t:.1f}")
            stext_set(cv_, card["t_row"], "--.-°" if t is None else f"{t:.1f}°")
            for rid, v in zip(self.cells[card["key"]], _last_n(hist, 48)):
                cv_.itemconfig(rid, fill=_heat_color(v))


class T18Spectrum(ThemeBase):
    """18 · VU-metre : hauteur = charge, couleur = temperature."""
    name = "18-spectrum"
    desc = "Spectre"

    def build(self):
        self.F = "Segoe UI"
        cv_ = self.cv
        cv_.create_rectangle(0, 0, 480, 320, fill="#060A14", outline="")
        cv_.create_line(16, 30, 464, 30, fill="#101A2E")
        self.T(16, 9, "SPECTRE", 10, "#22D3EE")
        self.T(240, 9, "48 S · HAUTEUR = CHARGE · COULEUR = TEMP.", 7, "#52627A",
               anchor="n")
        self.t_clock = self.T(464, 9, "--:--", 8, "#52627A", anchor="ne")
        cv_.create_line(151, 38, 151, 304, fill="#0E1830")
        self.T(16, 44, "CPU", 9, "#22D3EE")
        self.T(16, 56, self.cpu_name, 7, "#52627A", budget=128)
        self.t_cpu_temp = self.temp_group(16, 68, 32, "#34D399", 13, "#52627A",
                                          budget=132)
        self.T(16, 110, "CHARGE", 6.5, "#3F5068")
        self.t_cpu_use = self.T(16, 120, "-- %", 18, "#22D3EE")
        cv_.create_rectangle(16, 148, 144, 153, fill="#0F1B2D", outline="")
        self.cpu_bar = cv_.create_rectangle(16, 148, 16, 153, fill="#22D3EE", outline="")
        self.t_cpu_det = self.T(16, 158, "PACKAGE · --", 6.5, "#3F5068", budget=132)
        cv_.create_line(16, 180, 144, 180, fill="#0F1B2D")
        self.T(16, 190, "GPU", 9, "#818CF8")
        self.T(16, 202, self.gpu_name, 7, "#52627A", budget=128)
        self.t_gpu_temp = self.temp_group(16, 214, 32, "#818CF8", 13, "#52627A",
                                          budget=132)
        self.T(16, 258, "CHARGE", 6.5, "#3F5068")
        self.t_gpu_use = self.T(16, 268, "-- %", 18, "#818CF8")
        cv_.create_rectangle(16, 294, 144, 299, fill="#0F1B2D", outline="")
        self.gpu_bar = cv_.create_rectangle(16, 294, 16, 299, fill="#818CF8", outline="")
        self.t_gpu_det = self.T(16, 304, "CORE · --", 6.5, "#3F5068", budget=132)
        for yy, col in ((52, "#0C1626"), (108, "#0C1626"), (136, "#0A1220"),
                        (204, "#0A1220"), (244, "#0C1626")):
            cv_.create_line(160, yy, 464, yy, fill=col)
        cv_.create_line(160, 164, 464, 164, fill="#1E293B")
        self.step = 304.0 / 48.0
        self.colw = self.step - 1.1
        self.bars = {"cpu": [], "gpu": []}
        for i in range(48):
            x = 160.0 + i * self.step
            cpu_r = cv_.create_rectangle(x, 164, x + self.colw, 164,
                                         fill="#22D3EE", outline="")
            cpu_h = cv_.create_rectangle(x, 163, x + self.colw, 164, fill="#FFFFFF",
                                         outline="", stipple="gray50")
            gpu_r = cv_.create_rectangle(x, 165, x + self.colw, 165,
                                         fill="#818CF8", outline="")
            gpu_h = cv_.create_rectangle(x, 165, x + self.colw, 166, fill="#FFFFFF",
                                         outline="", stipple="gray50")
            self.bars["cpu"].append((cpu_r, cpu_h, x))
            self.bars["gpu"].append((gpu_r, gpu_h, x))
        self.T(464, 42, "CPU ↑", 6.5, "#22D3EE", anchor="ne")
        self.T(464, 278, "GPU ↓", 6.5, "#818CF8", anchor="ne")
        self.T(160, 304, "-48 S", 6.5, "#334155")
        self.T(464, 304, "MAINT.", 6.5, "#334155", anchor="ne")

    def _fill(self, rid, x, y, w, h, pct, color):
        frac = max(0.0, min(100.0, pct)) / 100.0
        self.cv.coords(rid, x, y, x + w * frac, y + h)
        self.cv.itemconfig(rid, fill=color)

    def update(self, s):
        cv_ = self.cv
        stext_set(cv_, self.t_clock, time.strftime("%H:%M"))
        ct, gt = s["ct"], s["gt"]
        cu, gu = s["cu"], s["gu"]
        self.temp_group_set(self.t_cpu_temp, "--.-" if ct is None else f"{ct:.1f}")
        self.temp_group_set(self.t_gpu_temp, "--.-" if gt is None else f"{gt:.1f}")
        cv_.itemconfig(self.t_cpu_temp["ids"][1],
                       fill=_temp_color(ct, "#34D399", 65, 80))
        cv_.itemconfig(self.t_gpu_temp["ids"][1],
                       fill=_temp_color(gt, "#818CF8", 65, 80))
        stext_set(cv_, self.t_cpu_use, f"{cu:.0f} %")
        stext_set(cv_, self.t_gpu_use, f"{gu:.0f} %")
        self._fill(self.cpu_bar, 16, 148, 128, 5, cu, "#22D3EE")
        self._fill(self.gpu_bar, 16, 294, 128, 5, gu, "#818CF8")
        freq = s.get("cf") or 0.0
        power = s.get("pw")
        stext_set(cv_, self.t_cpu_det,
                  "PACKAGE · --" if freq <= 0 else f"PACKAGE · {freq / 1000.0:.1f} GHz")
        stext_set(cv_, self.t_gpu_det,
                  "CORE · --" if power is None else f"CORE · {power:.0f} W")
        for key, hkey, tkey, base, up, color, scale in (
                ("cpu", "hc", "htc", 164.0, True, "#22D3EE", 112.0),
                ("gpu", "hg", "htg", 165.0, False, "#818CF8", 80.0)):
            uses = _last_n(s[hkey], 48)
            temps = _last_n(s[tkey], 48)
            for (rect, hi, x), u, t in zip(self.bars[key], uses, temps):
                if not u:
                    cv_.coords(rect, 0, 0, 0, 0)
                    cv_.coords(hi, 0, 0, 0, 0)
                    continue
                bh = max(1.0, min(100.0, u) / 100.0 * scale)
                if up:
                    y0, y1 = base - bh, base
                    cv_.coords(hi, x, y0 - 1.0, x + self.colw, y0)
                else:
                    y0, y1 = base, base + bh
                    cv_.coords(hi, x, y1, x + self.colw, y1 + 1.0)
                cv_.coords(rect, x, y0, x + self.colw, y1)
                cv_.itemconfig(rect, fill=_temp_color(t, color, 65, 80))


def _ring_arc(cv_, cx, cy, r, a0, a1, color, width=5):
    """Arc en degres boussole : 0 = haut, sens horaire."""
    return cv_.create_arc(cx - r, cy - r, cx + r, cy + r,
                          start=90 - a0, extent=-(a1 - a0),
                          style=tk.ARC, outline=color, width=width)


class T19Aiguilles(ThemeBase):
    """19 · Deux cadrans a aiguille, zones de seuil sur l'arc."""
    name = "19-aiguilles"
    desc = "Aiguilles"

    def build(self):
        self.F = "Segoe UI"
        cv_ = self.cv
        cv_.create_rectangle(0, 0, 480, 320, fill="#100D0A", outline="")
        cv_.create_line(16, 28, 464, 28, fill="#2A211B")
        cv_.create_line(240, 34, 240, 306, fill="#1A1512")
        self.T(16, 9, "AIGUILLES", 10, "#F59E0B")
        self.T(240, 9, "TEMPÉRATURE · 20–100 °C", 7.5, "#8A7A68", anchor="n")
        self.t_clock = self.T(464, 9, "--:--", 8, "#8A7A68", anchor="ne")
        self.gauges = [self._gauge(120, "cpu", "CPU", self.cpu_name),
                       self._gauge(360, "gpu", "GPU", self.gpu_name)]

    def _gauge(self, cx, key, label, name):
        cv_ = self.cv
        cy, r = 160, 84
        _ring_arc(cv_, cx, cy, r, -120, 120, "#2A211B", 5)
        _ring_arc(cv_, cx, cy, r, -120, 15, "#2E8B6B", 5)
        _ring_arc(cv_, cx, cy, r, 15, 60, "#A56A1C", 5)
        _ring_arc(cv_, cx, cy, r, 60, 120, "#A03A3A", 5)
        for v in range(20, 101, 10):
            ang = -120.0 + (v - 20) / 80.0 * 240.0
            x0, y0 = compass(cx, cy, 90, ang)
            x1, y1 = compass(cx, cy, 95, ang)
            cv_.create_line(x0, y0, x1, y1, fill="#5B4A3A")
            if v % 20 == 0:
                tx, ty = compass(cx, cy, 103, ang)
                self.T(tx, ty, str(v), 6.5, "#8A7A68", anchor="center")
        needle = cv_.create_line(cx, cy - 61, cx, cy, fill="#F97316",
                                 width=3, capstyle=tk.ROUND)
        cv_.create_oval(cx - 8, cy - 8, cx + 8, cy + 8, fill="#100D0A",
                        outline="#F97316", width=2)
        cv_.create_oval(cx - 2, cy - 2, cx + 2, cy + 2, fill="#F5F0E8", outline="")
        self.T(cx, 30, label, 9, "#F59E0B", anchor="n")
        self.T(cx, 42, name, 7.5, "#8A7A68", anchor="n", budget=215)
        t_temp = self.temp_group_c(cx, 232, 26, "#F5F0E8", 12, "#8A7A68")
        self.T(cx, 270, "CHARGE", 6.5, "#8A7A68", anchor="n")
        t_use = self.T(cx, 280, "-- %", 14, "#F59E0B", anchor="n")
        cv_.create_rectangle(cx - 60, 300, cx + 60, 304, fill="#2A211B", outline="")
        bar = cv_.create_rectangle(cx - 60, 300, cx - 60, 304, fill="#F59E0B", outline="")
        return dict(key=key, cx=cx, cy=cy, needle=needle,
                    t_temp=t_temp, t_use=t_use, bar=bar)

    def update(self, s):
        cv_ = self.cv
        stext_set(cv_, self.t_clock, time.strftime("%H:%M"))
        for g in self.gauges:
            cpu = g["key"] == "cpu"
            t = s["ct"] if cpu else s["gt"]
            use = s["cu"] if cpu else s["gu"]
            self.temp_group_c_set(g["t_temp"], "--.-" if t is None else f"{t:.1f}")
            stext_set(cv_, g["t_use"], f"{use:.0f} %")
            val = 20.0 if t is None else max(20.0, min(100.0, t))
            ang = -120.0 + (val - 20.0) / 80.0 * 240.0
            x0, y0 = compass(g["cx"], g["cy"], -14, ang)
            x1, y1 = compass(g["cx"], g["cy"], 61, ang)
            cv_.coords(g["needle"], x0, y0, x1, y1)
            frac = max(0.0, min(100.0, use)) / 100.0
            cv_.coords(g["bar"], g["cx"] - 60, 300, g["cx"] - 60 + 120 * frac, 304)


class T20Analytics(ThemeBase):
    """20 · Fiche de synthese : actuel, moyenne, pic, tendance."""
    name = "20-analytics"
    desc = "Analytics"

    def build(self):
        self.F = "Segoe UI"
        cv_ = self.cv
        cv_.create_rectangle(0, 0, 480, 320, fill="#0B0F14", outline="")
        cv_.create_line(16, 30, 464, 30, fill="#1E293B")
        self.T(16, 9, "ANALYTICS", 10, "#38BDF8")
        self.T(240, 9, "FENÊTRE 5 MIN · 300 POINTS", 7.5, "#64748B", anchor="n")
        self.t_clock = self.T(464, 9, "--:--", 8, "#64748B", anchor="ne")
        self.cards = [self._card(36, "cpu", "CPU", self.cpu_name, "#38BDF8"),
                      self._card(174, "gpu", "GPU", self.gpu_name, "#A78BFA")]
        cv_.create_line(16, 306, 464, 306, fill="#1E293B")
        self.T(16, 310, "ÉCHANTILLON 1 S · MOYENNE / PIC CALCULÉES SUR L’HISTORIQUE",
               6.5, "#52627A")
        self.T(464, 310, "SEUILS 65° / 80°", 6.5, "#52627A", anchor="ne")

    def _card(self, y, key, label, name, accent):
        cv_ = self.cv
        cv_.create_rectangle(10, y, 470, y + 130, fill="#111821", outline="#243244")
        cv_.create_rectangle(10, y, 13, y + 130, fill=accent, outline="")
        self.T(18, y + 8, label, 9, accent)
        self.T(46, y + 8, name, 8, "#7C8B99", budget=200)
        self.T(456, y + 8, "5 MIN", 6.5, "#5F7180", anchor="ne")
        t_temp = self.temp_group(18, y + 22, 36, "#E6EDF3", 14, "#7C8B99", budget=225)
        self.T(132, y + 48, "MOYENNE", 6.5, "#5F7180")
        t_avg = self.T(132, y + 58, "--.-°", 14, "#E6EDF3")
        self.T(198, y + 48, "PIC", 6.5, "#5F7180")
        t_pic = self.T(198, y + 58, "--.-°", 14, "#FBBF24")
        t_trend = self.T(18, y + 78, "TENDANCE --", 7.5, "#34D399", budget=226)
        t_det = self.T(18, y + 92, "CHARGE --", 7.5, "#7C8B99", budget=226)
        cv_.create_rectangle(18, y + 112, 456, y + 116, fill="#1C2630", outline="")
        bar = cv_.create_rectangle(18, y + 112, 18, y + 116, fill=accent, outline="")
        cv_.create_rectangle(262, y + 22, 456, y + 84, fill="#0A1119", outline="")
        area = cv_.create_polygon(0, 0, 0, 0, fill=accent, outline="", stipple="gray12")
        avg_line = cv_.create_line(0, 0, 0, 0, fill=accent, dash=(3, 3))
        line = cv_.create_line(0, 0, 0, 0, fill=accent, width=2)
        dot = cv_.create_oval(0, 0, 0, 0, fill=accent, outline="#0B0F14")
        return dict(key=key, accent=accent, y=y, t_temp=t_temp, t_avg=t_avg,
                    t_pic=t_pic, t_trend=t_trend, t_det=t_det, bar=bar,
                    area=area, avg_line=avg_line, line=line, dot=dot)

    def update(self, s):
        cv_ = self.cv
        stext_set(cv_, self.t_clock, time.strftime("%H:%M"))
        for card in self.cards:
            cpu = card["key"] == "cpu"
            hist = list(s["htc"] if cpu else s["htg"])
            vals = [v for v in hist if v is not None]
            use = s["cu"] if cpu else s["gu"]
            accent = card["accent"]
            y = card["y"]
            if vals:
                last = vals[-1]
                mean = sum(vals) / len(vals)
                peak = max(vals)
                self.temp_group_set(card["t_temp"], f"{last:.1f}")
                stext_set(cv_, card["t_avg"], f"{mean:.1f}°")
                stext_set(cv_, card["t_pic"], f"{peak:.1f}°")
                delta = last - mean
                stext_set(cv_, card["t_trend"],
                          f"TENDANCE {'+' if delta >= 0 else ''}{delta:.1f}° VS MOY")
                cv_.itemconfig(card["t_trend"][1],
                               fill="#FBBF24" if delta > 0 else "#34D399")
                lo, hi = min(vals), max(vals)
                if hi - lo < 6.0:
                    mid = (lo + hi) / 2.0
                    lo, hi = mid - 3.0, mid + 3.0
                else:
                    lo -= 1.0
                    hi += 1.0
                pts = _spark_pts(vals, 264, y + 24, 190, 58, lo, hi)
                cv_.coords(card["line"], *pts)
                cv_.coords(card["area"], *(pts + [451.0, y + 82.0, 267.0, y + 82.0]))
                p = max(0.0, min(1.0, (mean - lo) / max(1e-6, hi - lo)))
                ay = y + 27.0 + 52.0 * (1.0 - p)
                cv_.coords(card["avg_line"], 267, ay, 451, ay)
                dx, dy = pts[-2], pts[-1]
                cv_.coords(card["dot"], dx - 2.6, dy - 2.6, dx + 2.6, dy + 2.6)
            else:
                self.temp_group_set(card["t_temp"], "--.-")
                stext_set(cv_, card["t_avg"], "--.-°")
                stext_set(cv_, card["t_pic"], "--.-°")
            frac = max(0.0, min(100.0, use)) / 100.0
            cv_.coords(card["bar"], 18, y + 112, 18 + 438 * frac, y + 116)
            if cpu:
                freq = s.get("cf") or 0.0
                detail = "--" if freq <= 0 else f"{freq / 1000.0:.1f} GHz"
                stext_set(cv_, card["t_det"], f"CHARGE {use:.0f} % · {detail}")
            else:
                pw = s.get("pw")
                stext_set(cv_, card["t_det"],
                          f"CHARGE {use:.0f} % · " + ("--" if pw is None else f"{pw:.0f} W"))


class T21Focus(ThemeBase):
    """21 · Un capteur en vedette, bascule automatique toutes les 10 s."""
    name = "21-focus"
    desc = "Focus"

    def build(self):
        self.F = "Segoe UI"
        self._flip = False
        self._t0 = time.monotonic()
        cv_ = self.cv
        cv_.create_rectangle(0, 0, 480, 320, fill="#07090D", outline="")
        for x in (60, 180, 300, 420):
            cv_.create_line(x, 0, x, 320, fill="#0A0F16")
        for y in (80, 160, 240):
            cv_.create_line(0, y, 480, y, fill="#0A0F16")
        cv_.create_line(16, 28, 464, 28, fill="#16202A")
        self.T(16, 9, "FOCUS", 10, "#4ADE80")
        self.T(240, 9, "BASCULE AUTOMATIQUE · 10 S", 7, "#5B6675", anchor="n")
        self.t_clock = self.T(464, 9, "--:--", 8, "#5B6675", anchor="ne")
        name_px = min(self._fit_px(self.cpu_name, 8, 270),
                      self._fit_px(self.gpu_name, 8, 270))
        self.t_m_label = self.T(16, 40, "CPU", 10, "#4ADE80")
        self.t_m_tag = self.T(52, 41, "PACKAGE", 6.5, "#5B6675")
        self.t_m_name = self.T(16, 54, self.cpu_name, name_px, "#8A94A6")
        self.t_m_temp = self.temp_group(16, 62, 64, "#E6EDF3", 20, "#7C8B99", budget=290)
        self.T(16, 154, "CHARGE", 6.5, "#5B6675")
        self.t_m_use = self.T(16, 164, "-- %", 20, "#4ADE80")
        self.T(100, 154, "FRÉQUENCE", 6.5, "#5B6675")
        self.t_m_freq = self.T(100, 164, "--", 13, "#E6EDF3", budget=78)
        self.T(184, 154, "PUISSANCE", 6.5, "#5B6675")
        self.t_m_pow = self.T(184, 164, "--", 13, "#E6EDF3", budget=68)
        self.T(256, 154, "MOYENNE", 6.5, "#5B6675")
        self.t_m_mean = self.T(256, 164, "--.-°", 13, "#E6EDF3", budget=64)
        cv_.create_rectangle(16, 200, 304, 206, fill="#16202A", outline="")
        self.m_bar = cv_.create_rectangle(16, 200, 16, 206, fill="#4ADE80", outline="")
        self.t_m_last = self.T(16, 214, "DERNIER RELEVÉ --:--:-- · LHM", 6.5, "#3F4B59")
        cv_.create_line(318, 36, 318, 226, fill="#131C26")
        self.T(398, 44, "BASCULE VERS", 6.5, "#5B6675", anchor="n")
        self.t_target = self.T(398, 54, "GPU", 9, "#A78BFA", anchor="n")
        cv_.create_oval(344, 76, 452, 184, outline="#1C2630", width=1)
        self.ring = []
        for i in range(10):
            self.ring.append(cv_.create_arc(
                344, 76, 452, 184, start=90 - (i * 36 + 4), extent=-28,
                style=tk.ARC, outline="#1C2630", width=6))
        self.t_count = self.T(398, 108, "10", 32, "#F5F5F4", anchor="n")
        self.T(398, 150, "SECONDES", 6, "#5B6675", anchor="n")
        self.T(398, 192, "CYCLE 10 S", 6.5, "#5B6675", anchor="n")
        cv_.create_rectangle(16, 236, 464, 304, fill="#0D1219", outline="#1B2634")
        self.b_top = cv_.create_rectangle(16, 236, 464, 238, fill="#A78BFA", outline="")
        self.t_b_label = self.T(28, 246, "GPU", 8, "#A78BFA")
        bname_px = min(self._fit_px(self.cpu_name, 7, 200),
                       self._fit_px(self.gpu_name, 7, 200))
        self.t_b_name = self.T(28, 258, self.gpu_name, bname_px, "#5B6675")
        self.t_b_temp = self.T(28, 270, "--.- °C", 19, "#E6EDF3", budget=80)
        self.T(112, 268, "CHARGE", 6.5, "#5B6675")
        self.t_b_use = self.T(112, 278, "-- %", 15, "#A78BFA", budget=58)
        self.b_area = cv_.create_polygon(0, 0, 0, 0, fill="#A78BFA",
                                         outline="", stipple="gray12")
        self.b_line = cv_.create_line(0, 0, 0, 0, fill="#A78BFA", width=2)
        self.b_dot = cv_.create_oval(0, 0, 0, 0, fill="#A78BFA", outline="#0D1219")
        self.T(448, 292, "-48 S", 6, "#3F4B59", anchor="ne")

    def update(self, s):
        cv_ = self.cv
        stext_set(cv_, self.t_clock, time.strftime("%H:%M"))
        elapsed = time.monotonic() - self._t0
        flips = int(elapsed // 10.0)
        if flips:
            if flips % 2:
                self._flip = not self._flip
            self._t0 += flips * 10.0
            elapsed -= flips * 10.0
        rem = max(1, 10 - int(elapsed))
        gpu_focus = self._flip
        if gpu_focus:
            label, tag, accent = "GPU", "CORE", "#A78BFA"
            t, use, hist = s["gt"], s["gu"], s["htg"]
            freq = "--"
            pw = s.get("pw")
            power = "--" if pw is None else f"{pw:.0f} W"
            source = "NVML"
        else:
            label, tag, accent = "CPU", "PACKAGE", "#4ADE80"
            t, use, hist = s["ct"], s["cu"], s["htc"]
            f = s.get("cf") or 0.0
            freq = "--" if f <= 0 else f"{f / 1000.0:.1f} GHz"
            power = "--"
            source = "LHM"
        name = self.gpu_name if gpu_focus else self.cpu_name
        stext_set(cv_, self.t_m_label, label)
        cv_.itemconfig(self.t_m_label[1], fill=accent)
        stext_set(cv_, self.t_m_tag, tag)
        stext_set(cv_, self.t_m_name, name)
        self.temp_group_set(self.t_m_temp, "--.-" if t is None else f"{t:.1f}")
        stext_set(cv_, self.t_m_use, f"{use:.0f} %")
        stext_set(cv_, self.t_m_freq, freq)
        stext_set(cv_, self.t_m_pow, power)
        vals = [v for v in hist if v is not None]
        mean = sum(vals) / len(vals) if vals else None
        stext_set(cv_, self.t_m_mean, "--.-°" if mean is None else f"{mean:.1f}°")
        stext_set(cv_, self.t_m_last,
                  f"DERNIER RELEVÉ {time.strftime('%H:%M:%S')} · {source}")
        frac = max(0.0, min(100.0, use)) / 100.0
        cv_.coords(self.m_bar, 16, 200, 16 + 288 * frac, 206)
        cv_.itemconfig(self.m_bar, fill=accent)
        if gpu_focus:
            olabel, oaccent = "CPU", "#4ADE80"
            ot, ouse, ohist = s["ct"], s["cu"], s["htc"]
        else:
            olabel, oaccent = "GPU", "#A78BFA"
            ot, ouse, ohist = s["gt"], s["gu"], s["htg"]
        oname = self.cpu_name if gpu_focus else self.gpu_name
        stext_set(cv_, self.t_b_label, olabel)
        cv_.itemconfig(self.t_b_label[1], fill=oaccent)
        stext_set(cv_, self.t_b_name, oname)
        stext_set(cv_, self.t_b_temp, temp_str(ot))
        stext_set(cv_, self.t_b_use, f"{ouse:.0f} %")
        cv_.itemconfig(self.t_b_use[1], fill=oaccent)
        cv_.itemconfig(self.b_top, fill=oaccent)
        bvals = [v for v in ohist if v is not None][-48:]
        if bvals:
            lo, hi = min(bvals), max(bvals)
            if hi - lo < 4.0:
                mid = (lo + hi) / 2.0
                lo, hi = mid - 2.0, mid + 2.0
            else:
                lo -= 1.0
                hi += 1.0
            pts = _spark_pts(bvals, 240, 250, 208, 36, lo, hi)
            cv_.coords(self.b_line, *pts)
            cv_.coords(self.b_area, *(pts + [445.0, 286.0, 243.0, 286.0]))
            dx, dy = pts[-2], pts[-1]
            cv_.coords(self.b_dot, dx - 2.6, dy - 2.6, dx + 2.6, dy + 2.6)
        cv_.itemconfig(self.b_line, fill=oaccent)
        cv_.itemconfig(self.b_dot, fill=oaccent)
        cv_.itemconfig(self.b_area, fill=oaccent)
        stext_set(cv_, self.t_target, "GPU" if not gpu_focus else "CPU")
        cv_.itemconfig(self.t_target[1],
                       fill="#A78BFA" if not gpu_focus else "#4ADE80")
        stext_set(cv_, self.t_count, str(rem))
        for i, rid in enumerate(self.ring):
            cv_.itemconfig(rid, outline="#F59E0B" if i < rem else "#1C2630")


THEMES = [T01AidaPlus, T02Hud, T03Anneaux, T04Tuiles, T05Colonnes,
          T06Oscillo, T08Frise, T09Split,
          T10Modern, T11Ambre, T12Minimal, T13Neon, T14Flux, T15Atelier,
          T16Thermo, T17Heatmap, T18Spectrum, T19Aiguilles, T20Analytics, T21Focus]


def resolve_theme(key):
    """'6', '06-oscillo', 'oscillo'... -> classe de theme (defaut : 01)."""
    k = str(key).strip().lower()
    for t in THEMES:
        if k and k == t.name.lower():
            return t
    m = re.match(r"(\d+)", k)
    if m:
        i = int(m.group(1))
        for t in THEMES:
            tm = re.match(r"(\d+)", t.name)
            if tm and int(tm.group(1)) == i:
                return t
        if 1 <= i <= len(THEMES):
            return THEMES[i - 1]
    for t in THEMES:
        if k and (k in t.name or k in t.desc.lower()):
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


def check_theme_cmd():
    """Theme a la volée demandé par le Centre de controle : BASE/theme_cmd.txt.
    Le fichier contient la clé du theme ; on l'applique et on supprime le fichier."""
    p = os.path.join(BASE, "theme_cmd.txt")
    try:
        with open(p, encoding="utf-8-sig") as f:
            k = f.read().strip()
        os.remove(p)
    except Exception:
        return
    if k:
        try:
            apply_theme(k)
        except Exception:
            pass


def _save_panel_pos(x, y):
    """Enregistre la nouvelle position du moniteur dans config.ini (commentaires preserves)."""
    global _cfg_mtime
    try:
        txt = ""
        if os.path.isfile(CFG_PATH):
            with open(CFG_PATH, encoding="utf-8") as f:
                txt = f.read()
        for key, val in (("x", str(int(x))), ("y", str(int(y)))):
            txt, n = re.subn(r"(?m)^(\s*" + key + r"\s*=\s*).*$",
                             lambda m, v=val: m.group(1) + v, txt, count=1)
            if not n:
                if "[panel]" in txt:
                    txt = txt.replace("[panel]", f"[panel]\n{key} = {val}", 1)
                else:
                    sep = "\n" if txt and not txt.endswith("\n") else ""
                    txt = f"{txt}{sep}[panel]\n{key} = {val}\n"
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            f.write(txt)
        _cfg_mtime = os.path.getmtime(CFG_PATH)
    except Exception:
        pass


def _apply_topmost(val):
    """Applique topmost au HWND racine + place la fenetre au-dessus ou en-dessous."""
    global topmost
    topmost = bool(val)
    if root is None:
        return
    try:
        root.attributes("-topmost", topmost)
        u32 = ctypes.windll.user32
        u32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        u32.GetAncestor.restype = wintypes.HWND
        u32.SetWindowPos.argtypes = [
            wintypes.HWND, wintypes.HWND,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        u32.SetWindowPos.restype = wintypes.BOOL
        hwnd = u32.GetAncestor(root.winfo_id(), 2) or root.winfo_id()
        # SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE = 0x0013
        if topmost:
            u32.SetWindowPos(hwnd, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0013)
            root.lift()
        else:
            u32.SetWindowPos(hwnd, ctypes.c_void_p(-2), 0, 0, 0, 0, 0x0013)
            u32.SetWindowPos(hwnd, ctypes.c_void_p(1), 0, 0, 0, 0, 0x0013)
            root.lower()
    except Exception:
        pass


def check_panel_cmd():
    """Commandes live du Centre de controle : BASE/panel_cmd.txt."""
    global locked, topmost, _last_pos
    p = os.path.join(BASE, "panel_cmd.txt")
    try:
        with open(p, encoding="utf-8-sig") as f:
            lines = [ln.strip() for ln in f.read().splitlines() if ln.strip()]
        os.remove(p)
    except Exception:
        return False
    for line in lines:
        parts = line.split()
        cmd = parts[0].lower()
        if cmd == "quit":
            try:
                root.destroy()
            except Exception:
                pass
            return True
        elif cmd == "pos" and len(parts) >= 3:
            try:
                nx, ny = int(parts[1]), int(parts[2])
                _last_pos = (nx, ny)
                root.geometry(f"{W}x{H}+{nx}+{ny}")
                root.update_idletasks()
            except Exception:
                pass
        elif cmd == "lock" and len(parts) >= 2:
            try:
                new_lock = parts[1] in ("1", "true", "yes", "on")
                if new_lock != locked:
                    locked = new_lock
                    if root.state() == "normal" and root.winfo_x() > -10000:
                        px, py = root.winfo_x(), root.winfo_y()
                    else:
                        px, py = _last_pos or panel_xy()
                    _last_pos = (px, py)
                    root.withdraw()
                    root.overrideredirect(locked)
                    root.geometry(f"{W}x{H}+{px}+{py}")
                    root.deiconify()
                    if topmost:
                        _apply_topmost(True)
            except Exception:
                pass
        elif cmd == "topmost" and len(parts) >= 2:
            _apply_topmost(parts[1] in ("1", "true", "yes", "on"))
    return False


def poll_cmds():
    """Scrutation rapide (250 ms) des commandes du Centre de controle."""
    check_theme_cmd()
    if check_panel_cmd():
        return
    try:
        root.after(250, poll_cmds)
    except Exception:
        pass


def _on_configure(e):
    global _last_pos, _cfg_save_job
    if e.widget is not root or locked:
        return
    try:
        if root.state() != "normal":
            return
        nx, ny = root.winfo_x(), root.winfo_y()
        if nx <= -10000 or ny <= -10000:
            return
        if _last_pos == (nx, ny):
            return
        _last_pos = (nx, ny)
        if _cfg_save_job is not None:
            root.after_cancel(_cfg_save_job)
        _cfg_save_job = root.after(350, lambda x=nx, y=ny: _save_panel_pos(x, y))
    except Exception:
        pass


def _apply_task(live):
    """Remplace les mesures qui ne sont pas celles du Gestionnaire des tâches."""
    if not live:
        return
    if live.get("freq"):
        state["cf"] = live["freq"]
    if live.get("disk") is not None:
        state["du"] = live["disk"]
    if live.get("down") is not None:
        state["nd"] = live["down"]
        state["nu"] = live.get("up") or 0.0
    if live.get("vram") is not None and state.get("vt"):
        state["vg"] = live["vram"] / (1024 ** 3)
        state["vm"] = 100.0 * state["vg"] / state["vt"]


def sync_speed(rebuild=False):
    """Relit update_speed. Élevé 0,5 s, normal 1 s, faible 4 s, pause figée.
    La courbe couvre toujours 5 minutes."""
    global interval, paused, HN, _cfg_mtime
    try:
        mt = os.path.getmtime(CFG_PATH)
    except Exception:
        return
    if mt == _cfg_mtime:
        return
    _cfg_mtime = mt
    try:
        cfg.read(CFG_PATH, encoding="utf-8")
        speed = cfg.get("panel", "update_speed", fallback="").strip().lower()
        new_top = cfg.getboolean("panel", "topmost", fallback=topmost)
    except Exception:
        return
    if new_top != topmost and root is not None:
        _apply_topmost(new_top)
    if speed not in SPEED_MS:
        return
    new_paused = speed == "paused"
    new_interval = interval
    new_hn = HN
    if not new_paused:
        new_interval = SPEED_MS[speed]
        new_hn = max(2, int(round(HIST_WINDOW_MS / new_interval)))
    changed = new_paused != paused or new_interval != interval or new_hn != HN
    paused = new_paused
    interval = new_interval
    if new_hn != HN and state:
        for key in ("hc", "hg", "htc", "htg"):
            prev = list(state[key])
            state[key] = deque(prev[-new_hn:], maxlen=new_hn)
    HN = new_hn
    if rebuild and changed and theme is not None:
        try:
            apply_theme(theme.name)
        except Exception:
            pass


def tick():
    global warned_admin, smi_cooldown
    check_theme_cmd()
    sync_speed(rebuild=True)
    if paused:
        root.after(400, tick)
        return
    live = _task_meters.sample()
    # --- CPU : meme compteur que le Gestionnaire des taches, sinon psutil ---
    u_cpu = live["cpu"] if live.get("cpu") is not None else cpu_usage()
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
    if live.get("gpu") is not None:
        u_gpu = live["gpu"]
    if u_gpu is None:
        u_gpu = state["hg"][-1] if state["hg"] else 0.0
    state["gu"] = u_gpu
    state["gt"] = t_gpu
    state["hg"].append(u_gpu)
    state["htg"].append(t_gpu if t_gpu is not None else state["htg"][-1])
    state.update(extra_stats())
    _apply_task(live)

    theme.update(state)
    root.after(interval, tick)


def main(argv=None):
    global cfg, locked, topmost, interval, paused, HN, want_cpu_temp, COL, ADMIN
    global root, cv, theme, bg_img, state, _last_pos

    argv = list(sys.argv if argv is None else argv)
    setup, theme_arg, selftest_ms = parse_args(argv)

    if "--list-themes" in argv:
        for i, t in enumerate(THEMES, 1):
            print(f"{i}) {t.name} — {t.desc}")
        return 0

    ADMIN = is_admin()
    set_dpi_awareness()

    cfg = configparser.ConfigParser()
    cfg.read(CFG_PATH, encoding="utf-8")
    locked = cfg.getboolean("panel", "locked", fallback=True)
    topmost = cfg.getboolean("panel", "topmost", fallback=True)
    interval = max(100, cfg.getint("panel", "interval_ms", fallback=1000))
    speed = cfg.get("panel", "update_speed", fallback="").strip().lower()
    if speed in SPEED_MS and speed != "paused":
        interval = SPEED_MS[speed]
        HN = max(2, int(round(HIST_WINDOW_MS / interval)))
    elif speed == "paused":
        paused = True
        HN = max(2, cfg.getint("panel", "history", fallback=300))
    else:
        HN = max(2, cfg.getint("panel", "history", fallback=300))
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

    # historiques : usages + temperatures (pour les sparklines temp)
    state = {
        "cu": 0.0, "ct": None, "gu": 0.0, "gt": None,
        "hc": deque([0.0] * HN, maxlen=HN),
        "hg": deque([0.0] * HN, maxlen=HN),
        "htc": deque([40.0] * HN, maxlen=HN),
        "htg": deque([40.0] * HN, maxlen=HN),
    }
    state.update(_blank_extra())

    px, py = panel_xy()
    if selftest_ms:
        px, py = 60, 60   # position fixe pour capture propre
        locked = True
    _last_pos = (px, py)

    # Evite de rejouer une ancienne commande laissee lorsque le moniteur etait ferme
    try:
        os.remove(os.path.join(BASE, "panel_cmd.txt"))
    except Exception:
        pass

    root = tk.Tk()
    root.title("Moniteur")
    _icon = os.path.join(BASE, "ico.ico")
    if os.path.isfile(_icon):
        try:
            root.iconbitmap(_icon)
        except Exception:
            pass
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

    root.bind("<Alt-F4>", lambda e: root.destroy())
    root.bind("<Configure>", _on_configure)

    if selftest_ms:
        print(f"selftest: theme {theme.name} ({theme.desc}) {selftest_ms}ms")
        root.after(selftest_ms, root.destroy)

    root.after(250, poll_cmds)
    root.after(interval, tick)
    try:
        root.mainloop()
    finally:
        cleanup_providers()
    return 0


if __name__ == "__main__":
    sys.exit(main())
