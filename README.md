# Centre de contrôle

Fenêtre qui pilote le panneau capteurs 480×320 (`sensor-panel-480x320`).
Le centre s’affiche sur l’écran principal. Le panneau reste sur le petit moniteur.

Le dépôt contient les sources des deux programmes, pour pouvoir les modifier et les recompiler.
La release GitHub joint un zip qui ne contient que le nécessaire pour lancer le logiciel.

## Lancer le zip

Dézipper en gardant les dossiers côte à côte :

```
CentreControle.exe
_internal\
oscilloscope-16.png
oscilloscope-24.png
oscilloscope-32.png
oscilloscope-48.png
oscilloscope.png
sensor-panel-480x320\
    sensor_panel.exe
    sensor_panel.py
    _internal\
    config.ini
    assets\Fond.png
    libs\
    theme muse spark\<thème>\preview.png
    theme-glm\<thème>\preview.png
```

`CentreControle.exe` et son dossier `_internal` doivent rester ensemble. Pareil pour `sensor_panel.exe`.
Sans `centre.ini`, le centre cherche le panneau dans `sensor-panel-480x320` à côté de l’exe.
Un second lancement ramène la fenêtre déjà ouverte au premier plan.

Le panneau est lancé en administrateur (température CPU Ryzen via LibreHardwareMonitor).
Avec l’UAC sur « Ne jamais m’avertir », il n’y a pas de fenêtre de confirmation.

## Utilisation

| Action | Effet |
|---|---|
| Clic sur une vignette | Prévisualise le thème sur le panneau. `config.ini` n’est pas modifié. |
| Appliquer | Enregistre le thème prévisualisé et joue un son. |
| Fermer le centre | Remet le dernier thème enregistré si une prévisualisation était en cours. |
| Arrêter | Arrête le panneau. |
| Quitter | Ferme le centre. |
| Clair / Sombre | Change l’apparence du centre. |
| Flèches | Déplacent la sélection, sans l’appliquer. |
| Entrée | Appliquer. |
| Glisser la barre de titre | Déplace la fenêtre. La position est mémorisée dans `centre.ini`. |
| Clic droit | Verrouiller, recentrer sur l’écran principal, quitter. |

Le changement à chaud écrit la clé dans `theme_cmd.txt`. Le panneau l’applique au tick suivant (au plus une seconde) et supprime le fichier. Appliquer écrit aussi `theme =` dans `config.ini`.

## Thèmes

Treize thèmes. Les neuf premiers sont les thèmes verts d’origine. Les quatre suivants viennent des maquettes en couleurs :

| Clé | Nom |
|---|---|
| 01-aida | Heritage AIDA+ |
| 02-hud | HUD grands chiffres |
| 03-anneaux | Anneaux (jauges) |
| 04-tuiles | Tuiles 2x2 |
| 05-colonnes | Colonnes segmentees |
| 06-oscillo | Oscilloscope |
| 07-double | Double peak |
| 08-frise | Frise thermique |
| 09-split | Compact splitscreen |
| 10-modern | Modern Dark |
| 11-ambre | Terminal Ambre |
| 12-minimal | Minimal Mono |
| 13-neon | Cyber Neon |

Le centre lit les thèmes dans `sensor-panel-480x320/sensor_panel.py`, avec exactement :

```
name = "10-modern"
    desc = "Modern Dark"
```

Quatre espaces avant `desc`. Une clé ne doit pas commencer par le numéro d’un thème déjà présent (`02-…` serait lu comme le thème 2).

Les vignettes sont des PNG 480×320 :

- `theme muse spark\<clé>\preview.png` pour 01 à 09
- `theme-glm\<clé>\preview.png` pour 10 à 13

## Sources

```
centre de controle\
    centre_controle.py      interface du centre
    CentreControle.exe      exe compilé, à côté de _internal
    oscilloscope.ico        icône de l’exe
    oscilloscope*.png       icône de la fenêtre
    centre.ini              réglages locaux
    build.bat               recompile les deux exe
sensor-panel-480x320\
    sensor_panel.py         panneau et thèmes
    sensor_panel.exe        exe compilé, à côté de _internal
    config.ini              position, thème enregistré
    assets\Fond.png         fond des thèmes verts
    libs\                   LibreHardwareMonitor (température CPU)
```

`_internal`, `build` et `dist` sont produits par PyInstaller. Ils ne sont pas dans le dépôt. Ils sont dans le zip de la release.

## Réglages (`centre.ini`)

```ini
[centre]
locked = false
topmost = true
admin = true
mini = false
x = 800
y = 400
scale = 1
appearance = light

[panel]
path = C:\chemin\vers\sensor-panel-480x320
```

`appearance` vaut `light` ou `dark`. `scale` reste à 1 : il n’y a plus de bouton pour agrandir la fenêtre.

## Recompiler

Prérequis : Python 3.12, puis `pip install pyinstaller` et, pour le panneau, les paquets de `sensor-panel-480x320/requirements.txt` (`psutil`, `pynvml`, `pythonnet`).

```
centre de controle\build.bat
```

Le script arrête les deux programmes, recompile le panneau puis le centre, et replace chaque exe à côté de son `_internal`. L’icône du centre est `oscilloscope.ico`.

Les coordonnées souris du centre sont des flottants. Tout index de liste calculé depuis un clic doit passer par `int(...)`. Dans l’exe sans console, une exception Tk n’affiche rien : le clic a l’air de ne rien faire.
