# Changelog

Toutes les modifications notables du **Centre de contrôle** et du **Moniteur 480×320** sont documentées dans ce fichier.

## [2.0.0] - 2026-11-21

### Ajouté
- **Réécriture complète en C# (.NET 10) — zéro dépendance Python** :
  - **Centre de contrôle (`CentreControle.App`) en WinUI 3** : DA Windows 11 native (Mica, barre de titre personnalisée, coins arrondis, thème Clair/Sombre, filtres de thèmes Tous/Verts/Couleurs, son en deux temps sur Appliquer, tiroir Options style Paramètres Windows 11 avec état PawnIO).
  - **Moniteur 480×320 (`CentreControle.Monitor`) natif C#** : les 20 thèmes portés en rendu GDI+ double-buffered anti-aliasé, appel direct à `LibreHardwareMonitorLib` 0.9.6 (sans `pythonnet`), NVML natif (`nvml.dll`) + repli `nvidia-smi`, police `assets\dash-digital.ttf` embarquée, et communication live instantanée par Named Pipe (`CentreControlePanelPipe`) avec repli fichiers.
  - **Installateur Windows 11 (`installer\CentreControle.iss` via Inno Setup 6)** : `CentreControle-Setup-2.0.0.exe` self-contained (aucun prérequis Python/.NET/Windows App SDK sur un PC vierge), installation dans `Program Files`, raccourcis, désinstallation propre, police `Dash Digital-7`, et installation silencieuse automatique de `PawnIO_setup.exe` si absent.
- Gestion automatique du dossier de données (`AppPaths.ResolveDataDir`) : mode portable si le dossier est inscriptible, ou `%ProgramData%\CentreControle\` partagé lorsqu’installé dans `Program Files`.
- Script de build automatisé [build.ps1](build.ps1) et solution [src/CentreControle.slnx](src/CentreControle.slnx).

### Modifié
- Anciens scripts Python (`centre_controle.py`, `sensor_panel.py`, `build.bat`, `requirements.txt`) archivés dans `legacy\`.

## [1.2.1] - 2026-11-21

### Ajouté
- Intégration de `libs\PawnIO_setup.exe` (v2.2.0, signé) dans le dépôt et l’archive de release pour fonctionner sur un PC vierge dès le premier lancement.
- Détection (`_pawnio_present()`) et installation silencieuse automatique (`_ensure_pawnio()` via `-install -silent`) au démarrage de `Moniteur.exe` si le pilote `PawnIO` est absent avant le chargement de `LibreHardwareMonitorLib.dll`.

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
