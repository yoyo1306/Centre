# SensorPanel 480x320 — remplaçant léger d'AIDA64

Clone ton thème AIDA (`2026-05-21.sp2`, 480x320) :
- Ligne 1 : nom CPU + température CPU
- Graph 1 : utilisation CPU (vert `#56DC23`, grille `#008000`)
- Ligne 2 : nom GPU + température GPU
- Graph 2 : utilisation GPU
- Fond : ton `Fond.png` d'origine, police `Dash Digital-7` si installée

Fenêtre **480x320 verrouillée** (sans bordure, non déplaçable, always-on-top) pour petit moniteur.
Clic droit : verrouiller/déverrouiller, quitter. `Alt+F4` = quitter.

## Sources de données (100% local, 1 poll/sec)
| Mesure | Source | Note |
|---|---|---|
| Usage CPU | `psutil` | sans admin |
| Temp CPU | `LibreHardwareMonitorLib.dll` (`libs/`) | **admin requis** sur Ryzen AM5, sinon `--.- °C` |
| Temp + usage GPU | NVML (`pynvml`) | sans admin, ~1ms/tick |
| Fallback GPU | `nvidia-smi` 1x/10s max | si NVML indispo |

Testé sur : Ryzen 5 7600X + RTX 5080.

## Install
```
pip install -r requirements.txt
```

## Lancer
```
run.bat
```
ou `python sensor_panel.py`.
Pour la temp CPU : clic droit sur `run.bat` > **Exécuter en tant qu'administrateur**.

## Placer sur le petit moniteur
1. `python sensor_panel.py --setup` → fenêtre déplaçable, glisse-la sur le 480x320.
2. Clic droit > Verrouiller (la position est sauvée dans `config.ini`).
3. Relance normale : `run.bat`.

Si aucun x/y n'est renseigné, la fenêtre se centre automatiquement sur le plus
petit moniteur (ton 480x320 → plein écran pile, ton 800x600 → centré avec marges).
Sinon règle `x` / `y` dans `config.ini`.

## Thèmes (9)
Toutes les maquettes (`ui_proposals.html`) sont implémentées en Canvas pur, sélectionnables :

| # | Nom | Description |
|---|---|---|
| 1 | `01-aida` | Héritage AIDA+ : layout d'origine + grille, aire et point live |
| 2 | `02-hud` | HUD : température énorme, barre de charge, sparkline |
| 3 | `03-anneaux` | Jauges circulaires 240° + sparklines |
| 4 | `04-tuiles` | Tuiles 2×2 (temp + charge CPU/GPU) |
| 5 | `05-colonnes` | Gros chiffres + colonnes segmentées 14 crans |
| 6 | `06-oscillo` | Oscilloscope : 48 s d'historique CPU plein + GPU tirets |
| 7 | `07-double` | Double peak : 2 courbes empilées + barres dans les entêtes |
| 8 | `08-frise` | Frise thermique : 1 barre = 1 s, hauteur + densité = temp |
| 9 | `09-split` | Compact splitscreen CPU / GPU |

Choisir le thème :
```
# dans config.ini :  theme = 6   (numéro OU clé complète, ex : theme = 02-hud)
python sensor_panel.py --theme=6        # surcharge ponctuelle
python sensor_panel.py --list-themes    # liste
```
Changement **à chaud** (activé) : `check_theme_cmd()` est appelé en tête de `tick()` ;
il lit `theme_cmd.txt` (à la racine du dossier panel), appelle `apply_theme(k)`
en mémoire (canvas reconstruit, capteurs juste re-greffés — aucune relance) puis
supprime le fichier. Le centre de contrôle (`../centre de controle /`) écrit ce
fichier à chaque clic de thème → changement visible en < 1 s, PID inchangé.
- encodage : **UTF-8 sans BOM recommandé** ; `utf-8-sig` donc BOM toléré
  (PowerShell 5.1 écrit UTF8+BOM — c'est pour ça).
- contenu accepté : numéro (`"6"`) ou clé (`"06-oscillo"`) — résolu par `resolve_theme()`.
  Si la valeur ne matche rien, le thème 1 (01-aida) est appliqué en repli.
- ce fichier ne fait rien si le panel est éteint (consommé/redondant au boot) ;
  le centre le supprime alors lui-même.
Test rapide d'un thème : `python sensor_panel.py --theme=6 --selftest=5000`.

## Config.ini (clés)
```
[panel]
theme =      ; numéro (1..9) ou clé (--list-themes) ; --theme=N surcharge ce fichier
x, y =       ; position ; vide -> auto-centré sur le plus petit moniteur detecté
locked =     ; true : blocage de déplacement
topmost =    ; true : toujours au-dessus (small monitor, tip topmost au-dessus du fond)
[... couleurs du thème courant (commentaires conservées par le centre)]

## Fichiers
- `sensor_panel.py` — tout le tool (tkinter seul, pas de matplotlib/numpy)
- `config.ini` — position, verrouillage, couleurs du thème, intervalle
- `theme_cmd.txt` — fichier transitoire du hot-swap (écrit par le centre, consommé+supprimé par le panel)
- `sensor_panel.exe` + `_internal\` — build onedir (NE JAMAIS séparer les deux)
- `assets/Fond.png` — ton fond d'origine
- `libs/` — LibreHardwareMonitor (sondes CPU)
- `run.bat` — lancement rapide

## Compiler en exe standalone (optionnel)
Lancer `..\centre de controle\build.bat` (fait les deux apps dans le bon ordre).
Manuellement :
```
pip install pyinstaller
pyinstaller --noconsole --clean --name sensor_panel sensor_panel.py
move /y "dist\sensor_panel\sensor_panel.exe" "sensor_panel.exe"
move /y "dist\sensor_panel\_internal" "_internal"
rmdir /s /q dist build
del sensor_panel.spec
```
Mode **onedir** (exe + `_internal`) — PAS `--onefile` : onefile extrait tout dans
`%TEMP%\_MEI…` à chaque lancement (~1 s de plus) et un kill laisse le dossier
orphelin ; la réutilisation de PID par Windows corrompt alors le prochain
lancement (erreurs « Failed to start embedded python interpreter » /
« Failed to remove temporary directory »). Onedir n'a aucun de ces problèmes.

## État au moment de la passation (16/10/2026 ~22:45)
- `sensor_panel.exe` (onedir) inclut `check_theme_cmd()` + tolérance BOM (`utf-8-sig`)
  et démarre en ~0,5 s.
- Panel en cours sur le petit moniteur (1300,1440), topmost 480×320, thème `01-aida`.
- `config.ini` : `theme = 01-aida`, x/y = 1300/1440, commentaires intacts.
- Le centre de contrôle (../centre de controle) fait clic = application à chaud ;
  ses propres règles et bugs corrigés sont documentés dans SON README.
