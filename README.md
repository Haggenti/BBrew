# BBS — Brewing Brain System

Application de conception de recettes de bière basée sur Django, SQLite,
Django Templates, HTMX et Bootstrap.

BBS est le **Brewing Brain System**, le BBS des brasseurs : recettes, brassins
et stock connectés sans modem 56k. Il permet de gérer les recettes et leurs
versions, les paliers de brassage, le stock d'ingrédients et de consommables,
ainsi que la liste de courses. Les recettes peuvent être importées et exportées
au format BeerXML.

## Installation et lancement avec Fish

Depuis la racine du projet :

```fish
python3 -m venv .venv
source .venv/bin/activate.fish
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

L'application est ensuite disponible à l'adresse
<http://127.0.0.1:8000/>.

À la première installation, connectez-vous avec `brewer` / `brewer`, puis
utilisez le lien **Mot de passe** du menu pour remplacer le mot de passe
initial.

Pour quitter l'environnement virtuel :

```fish
deactivate
```

## Utilisation

- **Recettes** : créer une recette, gérer ses ingrédients, ses paliers,
  ses phases de fermentation, ses versions et son profil de dégustation
  interactif avec une note globale par demi-étoile. Les ingrédients d'une recette
  sont sélectionnés parmi les fiches du stock ; l'import crée automatiquement
  les fiches manquantes.
- **Stock** : gérer les malts, houblons, levures, ingrédients divers et
  consommables comme les capsules.
- **Coûts** : activer la gestion dans les paramètres puis renseigner le coût
  estimé de la quantité utilisée pour chaque ingrédient d’une recette. Les coûts
  inconnus restent vides et sont exclus du total, indiqué comme partiel.
- **Brassins** : chaque brassin reçoit une référence auto-incrémentée.
  Le calendrier indique les brassages et les embouteillages, avec un accès
  à la fiche correspondante.
- **Courses** : ajouter les articles manquants, les marquer comme commandés,
  puis les intégrer au stock avec la quantité réellement reçue.
- **BeerXML** : utiliser les actions d'import et d'export depuis les fiches
  recettes.

## Sauvegarde et restauration

La page **Paramètres** permet de télécharger une sauvegarde JSON complète et
de restaurer une sauvegarde existante. Une restauration remplace les données
actuelles : téléchargez une sauvegarde avant toute opération de ce type.

## Déploiement Docker sur Odroid HC4 (DietPi)

L'image utilise Python 3.13 sur Debian Bookworm (image officielle multi-architecture,
dont ARM64), Gunicorn et WhiteNoise. SQLite reste dans un dossier persistant du NAS ;
le conteneur effectue les migrations au démarrage et sert les fichiers statiques
collectés dans l'image.

### Première installation

1. Sur le NAS, vérifiez que Docker Engine est installé et que `docker compose version`
   fonctionne, puis clonez le dépôt :

   ```sh
   git clone https://github.com/Haggenti/BBrew.git
   cd BBrew
   ```

2. Générez une clé secrète et modifiez les valeurs de personnalisation directement
   dans `docker-compose.yml`. Vous pouvez générer la clé sur le NAS ou sur un autre
   ordinateur :

   ```sh
   openssl rand -hex 50
   ```

   Remplacez `DJANGO_SECRET_KEY`, puis renseignez le nom/IP du NAS dans
   `DJANGO_ALLOWED_HOSTS` et `DJANGO_CSRF_TRUSTED_ORIGINS`. La base est écrite dans
   le répertoire `./data` à côté du fichier Compose, hors du conteneur. Docker le
   crée automatiquement et le conteneur règle ses permissions au démarrage.
   Vous pouvez également modifier le port publié (`8000:8000`).
3. Depuis le dossier `BBrew`, construisez et démarrez l'application :

   ```sh
   docker compose up
   ```

   Compose construit l'image, crée le stockage persistant et lance les migrations.
   L'application est disponible sur `http://<adresse-du-nas>:8000/`. Connectez-vous
   avec `brewer` / `brewer` uniquement sur un réseau de confiance, puis changez
   immédiatement le mot de passe depuis le menu **Mot de passe**.

### Accès et opérations courantes

- Ne transférez pas le port 8000 directement depuis Internet. Pour un accès extérieur,
  privilégiez un VPN. Si vous utilisez un reverse proxy HTTPS, réglez
  `DJANGO_SECURE_COOKIES` et `DJANGO_SECURE_PROXY_SSL_HEADER` à `1`, indiquez l'origine
  `https://...` dans `DJANGO_CSRF_TRUSTED_ORIGINS` et empêchez les accès directs qui
  contourneraient le proxy.
- Gardez une seule instance BBS active : SQLite ne convient pas à plusieurs
  réplicas applicatifs concurrents.
- Le répertoire `data/` contient la base SQLite directement sur le NAS, hors du
  conteneur. Il est exclu de Git ; sauvegardez-le régulièrement, ainsi que les
  sauvegardes générées dans BBS, vers un autre emplacement.
- Pour mettre à jour : sauvegardez les données, mettez le code à jour, puis lancez
  `git pull` puis `docker compose up --build`. Les migrations sont exécutées au
  démarrage.
- Pour arrêter : `docker compose down`. Ce répertoire reste en place lors de la
  suppression ou de la reconstruction du conteneur ; sauvegardez-le avant toute
  opération de nettoyage manuelle.

## Configuration

Les paramètres suivants peuvent être définis avec des variables
d'environnement :

```fish
set -x DJANGO_SECRET_KEY "une-cle-secrete"
set -x DJANGO_DEBUG 0
set -x DJANGO_ALLOWED_HOSTS "localhost,127.0.0.1"
```

En développement, les valeurs par défaut permettent de lancer l'application
sans configuration supplémentaire. Pour une mise en production, définissez
au minimum une clé secrète personnalisée, désactivez `DEBUG` et renseignez
les hôtes autorisés.

## Tests

```fish
source .venv/bin/activate.fish
python manage.py test
```
