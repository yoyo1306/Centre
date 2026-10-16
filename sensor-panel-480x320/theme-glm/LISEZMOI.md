# Thèmes GLM — SensorPanel 480×320

Un dossier par thème, galerie de comparaison à la racine :

```
theme-glm/
├── index.html            ← galerie (double-clic, tout est autonome)
├── 01-aida-classique/    ← réplique du thème actuel (référence)
├── 02-modern-dark/
├── 03-terminal-ambre/
├── 04-minimal-mono/
└── 05-cyber-neon/
```

Chaque dossier contient un `index.html` à la taille exacte 480×320, animé en 1 Hz
(données simulées, même rythme que le panel réel). Double-clic + F11 sur le petit
moniteur = aperçu 1:1 plein écran.

| Dossier | Nom | Ambiance |
|---|---|---|
| `01-aida-classique` | AIDA Classic | Vert, Dash Digital-7, Fond.png (émbarqué inline) — état actuel |
| `02-modern-dark` | Modern Dark | Cartes sombres, chiffres fins, sparklines dégradées cyan/violet |
| `03-terminal-ambre` | Terminal Ambre | CRT rétro : scanlines, lueur, barres segmentées |
| `04-minimal-mono` | Minimal Mono | B/N épuré, température géante fine, sparkline blanche |
| `05-cyber-neon` | Cyber Néon | Néons cyan/magenta, grille perspective, chiffres italiques |

## Notes pour l'implémentation tkinter (thème à la volée)

Le rendu tkinter ne peut pas faire la translucidité/lueur réelle de P2/P5 —
traduction réaliste proposée par thème :

### Palette (config.ini `[colors]`)
- **aida** : inchangé (label `#1FE01F`, value `#4EC221`, graph `#56DC23`, grid `#008000`, bg `#000000`).
- **modern** : label `#8B98A9`, value `#38BDF8` / `#A78BFA`, graph `#38BDF8`, fond `#0B0F14`,
  seuils temp : < 65 °C accent normal, 65–75 °C `#FBBF24`, ≥ 75 °C `#FB7185`.
- **ambre** : label `#FFA726`, value `#FFB000`, graph `#FFB000`, fond `#0A0600`.
  Traînée = tracer la même courbe 3 fois (`#3D2E00`, `#7A5800`, puis `#FFB000`).
- **minimal** : label `#8F8F8F`, value `#F2F2F2`, graph `#E8E8E8`, fond `#050505`,
  seuil ≥ 80 °C → `#FF5C5C`.
- **neon** : label `#7FF3FF` (CPU) / `#FFA8EA` (GPU), value `#00E5FF` / `#FF3EC8`, fond `#0A0022`.

### Polices
- `aida` : `Dash Digital-7` (déjà le cas).
- `ambre` : `Consolas` ou `Cascadia Mono`.
- `modern` / `minimal` / `neon` : Inter/Orbitron non installées → fallback
  `Segoe UI Light` / `Segoe UI` (garder les graisses fines poids 200-300).

### Éléments traduisibles en Canvas
- **Barres segmentées** (ambre/neon) : rectangles 17×9 px allumés/éteints, gap 3 px.
- **Chip d'état** (modern) : texte `STABLE`/`CHAUD` coloré à droite du titre.
- **Scanlines** (ambre) : lignes horizontales noires 1 px toutes les 3 px, dessinées
  une fois sous le texte.
- **Grille perspective** (neon) : 2-3 bandes horizontales dégradées au bas du Canvas.
- **Cartes** (modern) : rectangles arrondis via `create_polygon` + `smooth=True`.
- **Ombre texte** : déjà en place (`shadow_text`).
- **Sparkline "aire"** (modern) : polyline + polygone fermé en couleur assombrie.

### Piste pour le sélecteur à la volée
1. Ajouter `theme = aida|modern|ambre|minimal|neon` dans `[panel]` (config.ini).
2. Factoriser en un dict `THEMES = {...}` : couleurs, polices, positions
   (lignes 10/170, tops graphes 40/200, hauteur 120, pas 10 px).
3. Menu clic droit : sous-menu « Thème ▸ » qui écrit `theme=` dans config.ini puis
   reboucle `os.execv` (même mécanique que le verrouillage actuel).

## Servir en HTTP (aperçu navigateur)
```
python -m http.server 9901
# → http://localhost:9901/theme-glm/index.html
```
