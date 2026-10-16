"""Genere 4 propositions d'UI 480x320 dans mockups/. Donnees simulees realistes."""
import math
import os
import random

from PIL import Image, ImageDraw, ImageFont

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "mockups")
os.makedirs(OUT, exist_ok=True)
FOND = Image.open(os.path.join(BASE, "assets", "Fond.png")).convert("RGB")

DIGI = os.path.join(os.environ["LOCALAPPDATA"], r"Microsoft\Windows\Fonts\dash_digital-7.ttf")
ARIAL = r"C:\Windows\Fonts\arial.ttf"
ARIALB = r"C:\Windows\Fonts\arialbd.ttf"


def font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


random.seed(7)
cpu_hist = [min(100, max(4, 20 + 12 * math.sin(i / 6) + random.uniform(-6, 9))) for i in range(60)]
gpu_hist = [min(100, max(2, 30 + 25 * math.sin(i / 9 + 2) + random.uniform(-8, 12))) for i in range(60)]

GREEN, BRIGHT, DIM, BLACK = "#1FE01F", "#7CFF6B", "#0A4D0A", "#000000"


def curve(d, hist, x0, y0, w, h, color=GREEN, width=2):
    pts = [(x0 + i * w / (len(hist) - 1), y0 + h - v / 100 * h) for i, v in enumerate(hist)]
    d.line(pts, fill=color, width=width, joint="curve")
    return pts


def grid(d, x0, y0, w, h, color="#005E00"):
    for i in range(1, 4):
        d.line([x0, y0 + i * h / 4, x0 + w, y0 + i * h / 4], fill=color)
    for i in range(1, 6):
        d.line([x0 + i * w / 6, y0, x0 + i * w / 6, y0 + h], fill=color)


# ---------- A : actuel affute (fond integral, courbe epaisse, titres + %) ----------
img = FOND.copy()
d = ImageDraw.Draw(img)
f_n, f_v, f_s = font(ARIALB, 16), font(DIGI, 30), font(ARIAL, 14)
d.text((10, 6), "AMD Ryzen 5 7600X", font=f_n, fill=GREEN)
d.text((478, 0), "48.5 °C", font=f_v, fill=GREEN, anchor="ra")
d.text((10, 38), "Utilisation CPU  —  20 %", font=f_s, fill=BRIGHT)
curve(d, cpu_hist, 0, 60, 480, 88, width=3)
d.text((10, 160), "NVIDIA GeForce RTX 5080", font=f_n, fill=GREEN)
d.text((478, 156), "42.0 °C", font=f_v, fill=GREEN, anchor="ra")
d.text((10, 194), "Utilisation GPU  —  34 %", font=f_s, fill=BRIGHT)
curve(d, gpu_hist, 0, 216, 480, 88, width=3)
img.save(f"{OUT}/A-actuel-affute.png")

# ---------- B : tuiles (2 cartes, gros chiffres, sparkline) ----------
img = Image.new("RGB", (480, 320), BLACK)
d = ImageDraw.Draw(img)
f_big, f_mid, f_s = font(DIGI, 52), font(DIGI, 22), font(ARIALB, 14)
for top, name, t, u, hist in [(8, "RYZEN 5 7600X", "48.5", "34", cpu_hist),
                              (164, "RTX 5080", "42.0", "34", gpu_hist)]:
    d.rounded_rectangle([6, top, 474, top + 148], radius=10, outline=DIM, width=2)
    d.text((20, top + 6), name, font=f_s, fill=BRIGHT)
    d.text((20, top + 26), f"{t}", font=f_big, fill=GREEN)
    d.text((194, top + 64), "°C", font=f_mid, fill=GREEN)
    d.text((290, top + 26), f"{u}", font=f_big, fill=GREEN)
    d.text((394, top + 64), "%", font=f_mid, fill=GREEN)
    curve(d, hist, 20, top + 104, 440, 32, width=2)
img.save(f"{OUT}/B-tuiles.png")

# ---------- C : cadrans (jauges arc + centre digital) ----------
img = FOND.copy().point(lambda v: int(v * 0.55))
d = ImageDraw.Draw(img)
f_big, f_mid, f_s = font(DIGI, 44), font(DIGI, 22), font(ARIAL, 15)


def gauge(cx, cy, r, frac, label, val):
    d.arc([cx - r, cy - r, cx + r, cy + r], 150, 390, fill=DIM, width=10)
    d.arc([cx - r, cy - r, cx + r, cy + r], 150, 150 + 240 * frac, fill=GREEN, width=10)
    d.text((cx, cy - 26), val, font=f_big, fill=GREEN, anchor="ma")
    d.text((cx, cy + 8), label, font=f_s, fill=BRIGHT, anchor="ma")


d.text((10, 8), "AMD Ryzen 5 7600X  —  48.5 °C", font=f_s, fill=BRIGHT)
gauge(120, 105, 52, 0.20, "CPU %", "20")
gauge(360, 105, 52, 0.34, "GPU %", "34")
curve(d, cpu_hist, 20, 175, 200, 50, width=2)
curve(d, gpu_hist, 260, 175, 200, 50, width=2)
d.text((20, 232), "TEMP CPU 48.5 °C   FAN 1250 rpm", font=f_s, fill=BRIGHT)
d.text((20, 258), "TEMP GPU 42.0 °C   HOTSPOT 55 °C", font=f_s, fill=BRIGHT)
d.text((20, 284), "RAM 12.4 / 32 Go   VRAM 6.1 Go", font=f_s, fill=BRIGHT)
img.save(f"{OUT}/C-cadrans.png")

# ---------- D : contraste max (bandes noires, zero texture, texte blanc-vert) ----------
img = Image.new("RGB", (480, 320), BLACK)
d = ImageDraw.Draw(img)
f_t, f_v, f_s = font(ARIALB, 20), font(DIGI, 40), font(ARIALB, 17)
WHT = "#E8FFE8"
d.rectangle([0, 0, 480, 44], fill="#061206")
d.text((12, 8), "AMD Ryzen 5 7600X", font=f_t, fill=WHT)
d.text((468, 2), "48.5°C", font=f_v, fill=GREEN, anchor="ra")
d.text((12, 50), "CPU  20 %", font=f_s, fill=BRIGHT)
curve(d, cpu_hist, 0, 76, 480, 76, color=BRIGHT, width=3)
d.rectangle([0, 160, 480, 204], fill="#061206")
d.text((12, 168), "NVIDIA RTX 5080", font=f_t, fill=WHT)
d.text((468, 162), "42.0°C", font=f_v, fill=GREEN, anchor="ra")
d.text((12, 210), "GPU  34 %", font=f_s, fill=BRIGHT)
curve(d, gpu_hist, 0, 236, 480, 76, color=BRIGHT, width=3)
img.save(f"{OUT}/D-contraste-max.png")

print("OK:", sorted(os.listdir(OUT)))
