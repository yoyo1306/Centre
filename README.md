# Centre de contrôle

Fenêtre qui pilote le panneau capteurs 480×320, dans le même dossier.
Le centre s’affiche sur l’écran principal. Le panneau reste sur le petit moniteur.

Le dépôt contient les sources des deux programmes, pour pouvoir les modifier et les recompiler.
La release GitHub joint un zip qui ne contient que le nécessaire pour lancer le logiciel.

## Lancer le zip

Dézipper en gardant les dossiers côte à côte :

```
CentreControle.exe
_internal\
ico.ico
sensor_panel.exe
panel_internal\
sensor_panel.py
config.ini
assets\Fond.png
libs\
themes\<thème>\preview.png
```

`CentreControle.exe` reste avec `_internal`. `sensor_panel.exe` reste avec `panel_internal`. Les deux dossiers n’ont pas le même nom, sinon un exe écrase l’autre.
Sans `centre.ini`, le centre cherche `sensor_panel.exe` dans son propre dossier.
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
| 0 à 5 | Règle la luminosité de l’écran 480×320. |
| Options | Ouvre le panneau collé à la fenêtre. Un second clic le ferme. |
| Flèches | Déplacent la sélection, sans l’appliquer. |
| Entrée | Appliquer. |
| Glisser la barre de titre | Déplace la fenêtre. La position est mémorisée dans `centre.ini`. |
| Clic droit | Verrouiller, recentrer sur l’écran principal, quitter. |

Le changement à chaud écrit la clé dans `theme_cmd.txt`. Le panneau l’applique au tick suivant (au plus une seconde) et supprime le fichier. Appliquer écrit aussi `theme =` dans `config.ini`.

## Luminosité

Les boutons 0 à 5, sous la barre du haut, règlent seulement l’écran 480×320.

| Bouton | Luminosité |
|---|---|
| 0 | 0 % |
| 1 | 20 % |
| 2 | 40 % |
| 3 | 60 % |
| 4 | 80 % |
| 5 | 100 % |

Le bouton vert est le niveau en cours. Un réglage avec le bouton physique de cet écran met à jour le bouton vert en moins de deux secondes. L’écran principal n’est pas modifié.

Options permet de lancer le panneau à l’ouverture de session Windows. La tâche planifiée s’appelle `SensorPanel`.

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

Le centre lit les thèmes dans `sensor_panel.py`, avec exactement :

```
name = "10-modern"
    desc = "Modern Dark"
```

Quatre espaces avant `desc`. Une clé ne doit pas commencer par le numéro d’un thème déjà présent (`02-…` serait lu comme le thème 2).

Les vignettes sont des PNG 480×320 :

- `themes\<clé>\preview.png` pour les treize thèmes

## Sources

```
centre de controle\
    centre_controle.py      interface du centre
    CentreControle.exe      exe compilé, à côté de _internal
    ico.ico                 icône de l’exe et de la fenêtre
    centre.ini              réglages locaux
    build.bat               recompile les deux exe
    sensor_panel.py         panneau et thèmes
    sensor_panel.exe        exe du panneau, à côté de panel_internal
    config.ini              position, thème enregistré
    assets\Fond.png         fond des thèmes verts
    libs\                   LibreHardwareMonitor (température CPU)
    themes\                 vignettes du centre
```

`_internal`, `panel_internal`, `build` et `dist` sont produits par PyInstaller. Ils ne sont pas dans le dépôt. Ils sont dans le zip de la release.

## Réglages (`centre.ini`)

```ini
[centre]
locked = false
topmost = false
admin = true
mini = false
x = 800
y = 400
scale = 1
appearance = light

[panel]
path = C:\chemin\vers\centre de controle
```

`appearance` vaut `light` ou `dark`. `scale` reste à 1 : il n’y a plus de bouton pour agrandir la fenêtre.

## Recompiler

Prérequis : Python 3.12, puis `pip install pyinstaller` et, pour le panneau, `psutil`, `pynvml` et `pythonnet` (`requirements.txt`).

```
centre de controle\build.bat
```

Le script arrête les deux programmes, recompile le panneau puis le centre, et replace chaque exe à côté de son dossier d’exécution. L’icône du centre est `ico.ico`.

Les coordonnées souris du centre sont des flottants. Tout index de liste calculé depuis un clic doit passer par `int(...)`. Dans l’exe sans console, une exception Tk n’affiche rien : le clic a l’air de ne rien faire.
