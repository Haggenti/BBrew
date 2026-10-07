# Journal des évolutions — BBS

La version du programme est le hash complet (`40` caractères) du commit Git
courant. Dans un clone Git, la page « À propos » le lit directement depuis
`HEAD`. Lors de la construction Docker, une étape dédiée lit le hash du dépôt
et le transmet à l'image finale sans y inclure `.git`.

Le hash ne peut pas être inscrit dans le contenu du commit qui le crée : il
est calculé à partir de ce contenu. L'entrée ci-dessous indique donc le dernier
commit présent au moment de la création de ce journal. À chaque évolution
livrée, ajouter une entrée décrivant le changement et le hash du commit
précédent ; après le commit, la version de l'application affichera
automatiquement le nouveau hash.

## Historique Git

### 2026-10-07

- `4d50b20` — Détection automatique de la version Git pendant la construction
  de l'image Docker.

### 2026-10-06

- `5805ed9` — Ajout du journal des événements et aperçu du coût unitaire dans
  la liste de courses.
- `243e5d6` — Amélioration de la fenêtre de réglage de la carbonatation et de
  la mise en page de la fiche recette.
- `ee3b620` — Réinitialisation de la numérotation des brassins à leur création
  et suppression.
- `3c895f2` — Gestion des sessions et invalidation des sessions au démarrage.
- `c144aed` — Documentation du bilan de revue de sécurité.
- `8d4f99d` — Ajout de la carte de couleur de bière et ajustement de la fiche
  recette.

### 2026-10-05

- `2df6e87` — Création de la page « À propos » avec version et lien du dépôt.
- `a000a09` — Réorganisation du code pour faciliter sa maintenance.
- `73df1fb` — Ajout de logos SVG pour BBS.
- `aaa0890` — Ajustements de mise en page de la fiche recette.
- `13f3e7c` — Ajout du profil de dégustation à la recette.
- `42d5f8a` — Amélioration de la fiche brassin, du calendrier et des coûts.
- `217982a` — Amélioration du déploiement Docker et de la gestion des données.
- `943e8a9` — Suppression de ressources graphiques inutilisées.
- `78b0402` — Simplification de la configuration Docker et suppression du
  fichier d'exemple d'environnement.
- `5e84fc7` — Ajout du déploiement Docker et de son script d'entrée.
- `14432a2` — Amélioration des indicateurs de style et des événements
  d'ébullition de la recette.
- `4ab4307` — Réorganisation du formulaire de courses et ajout de champs à la
  recette.

### 2026-10-04

- `91a16f0` — Validation de la consommation du stock et améliorations de la
  gestion des recettes.
- `ca37ccf` — Réorganisation du code pour faciliter sa maintenance.
- `c9b7913` — Ajout du tableau de bord.
- `494ccc6` — Amélioration de la gestion des articles de courses et de la
  documentation.
- `b98d59b` — Mise à jour du profil d'empâtage et de la fiche recette.
- `2beddfe` — Amélioration du catalogue de recettes et de la liste de courses.
- `803c4e8` — Amélioration de la gestion et de la validation des ingrédients.

### 2026-10-03

- `c90e3ca` — Ajout d'icônes SVG et des pages de gestion des brassins.

### 2026-10-02

- `d5b831e` — Ajout des catégories et styles BJCP.
- `763300c` — Ajout de l'import et de l'export BeerXML.
- `781e6d0` — Ajout du catalogue d'ingrédients et amélioration de leur gestion.
- `bb334b5` — Création de l'application Django et des premières fonctions de
  gestion des recettes.

## Version lors de la création de ce journal

`5805ed95bc48a8eac05f5a18a3b35c8fad81b969`
