# Changelog

Toutes les modifications notables du **Centre de contrôle** et du **Moniteur 480×320** sont documentées dans ce fichier.

## [1.2.0] - 2026-11-21

### Ajouté
- Son en deux temps sur le bouton **Appliquer** : `assets\click_down.wav` à l’appui et `assets\click_up.wav` au relâchement.
- Contrôles du moniteur 480×320 directement dans le panneau **Options** : recentrage sur le petit écran, verrouillage/déverrouillage et maintien au premier plan (`topmost`).
- Commandes live via `panel_cmd.txt` (`pos`, `lock`, `topmost`, `quit`) scrutées toutes les 250 ms par `sensor_panel.py`.

### Modifié
- Déclenchement des sélections et clics au relâchement du bouton sur le même élément (`on_press` / `on_release`).
- Refonte du thème `01-aida` selon la maquette AIDA64 (`assets\Fond.png`, températures entières, courbes vertes) et harmonisation des thèmes `02-hud` à `09-split` avec mise à jour de leurs vignettes `preview.png`.
- Passage à `VERSION = "1.2.0"` dans `centre_controle.py` et ajout du repli `py -3.12` dans `build.bat`.

### Supprimé
- Thème `07-double` (`themes\07-double\`) : le logiciel passe de 21 à 20 thèmes.
- Menu contextuel clic droit, remplacé par le panneau **Options**.

### Corrigé
- `resolve_theme()` dans `sensor_panel.py` pour éviter le décalage d’index sur les thèmes `08-frise` à `21-focus` après la suppression de `07-double`.
- Recentrage du moniteur ciblant désormais `Moniteur.exe` sur le petit écran 480×320 plutôt que la fenêtre du centre.
- Vérification asynchrone de l’état du panneau (`panel_running()`), garde `--noconsole` (`_Quiet`), signatures 64 bits Win32 (`ShellExecuteW`, `FindWindowW`, PDH/HWND), repli `Perflib\00C`, exécution silencieuse de `nvidia-smi` et garde `_spark_pts`.

## [1.1.0] - 2026-10-17

### Ajouté
- Six boutons de luminosité (`0` à `5`, de 0 % à 100 %) réservés à l’écran 480×320, synchronisés avec le bouton physique de l’écran.
- Capture `apercu.png` ajoutée au README.

### Modifié
- Icône renommée en `ico.ico` et regroupement du centre et du panneau dans `centre de controle\`.

## [1.0.0] - 2026-10-16

### Ajouté
- Version initiale du Centre de contrôle (`CentreControle.exe`) et du panneau capteurs 480×320 (`Moniteur.exe`), avec `themes\`, `libs\`, `assets\` et `config.ini`.
