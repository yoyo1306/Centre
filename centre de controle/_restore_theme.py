# -*- coding: utf-8 -*-
"""_restore_theme.py — remise d'état propre : theme = 01-aida (config + affichage à chaud).

Usage : python _restore_theme.py

Fait :
  1. arrête toute instance du centre en cours de test (pythonw + exe) ;
  2. réécrit `theme = 01-aida` dans config.ini du panel (regex, commentaires conservés) ;
  3. dépose theme_cmd.txt = 01-aida → si le panel tourne, apply_theme à chaud (≤1 s,
     PID inchangé) ; sinon le fichier est consommé/redondant au prochain démarrage.
"""
import os, re, time, psutil

BASE = r"C:\Users\Kevin AJOURY\Documents\Projet IA\sensor-panel-480x320"

for p in list(psutil.process_iter(['name', 'cmdline'])):
    n = (p.info['name'] or '')
    cl = ' '.join(p.info['cmdline'] or [])
    if n == 'CentreControle.exe'.lower() or (
            n.lower().startswith('python') and 'centre_controle.py' in cl):
        try:
            p.kill()
        except Exception:
            pass
time.sleep(0.8)

cfg = os.path.join(BASE, 'config.ini')
txt = open(cfg, encoding='utf-8').read()
new, ndone = re.subn(r'(?m)^(\s*theme\s*=\s*).*$', lambda m: m.group(1) + '01-aida', txt, count=1)
open(cfg, 'w', encoding='utf-8').write(new)
open(os.path.join(BASE, 'theme_cmd.txt'), 'w', encoding='utf-8').write('01-aida')
time.sleep(1.8)
print('config restauree :', [l.strip() for l in open(cfg, encoding='utf-8') if l.strip().startswith('theme')][0])
print('cmd consomme     :', not os.path.exists(os.path.join(BASE, 'theme_cmd.txt')))
print('pids panel       :', sorted(p.pid for p in psutil.process_iter(['name']) if 'sensor_panel' in (p.info['name'] or '').lower()))
