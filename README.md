# BBS — Brewing Brain System

Application de conception de recettes de bière basée sur Django, SQLite,
Django Templates, HTMX et Bootstrap.

BBS est le **Brewing Brain System**, le BBS des brasseurs : recettes, brassins
et stock connectés sans modem 56k. Il permet de gérer les recettes et leurs
versions, les paliers de brassage, le stock d'ingrédients et de consommables,
ainsi que la liste de courses. Les recettes peuvent être importées et exportées
au format BeerXML.

## Installation et lancement en local

### Avec Fish

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

### Avec un terminal standard (Bash, Zsh ou sh)

Depuis la racine du projet :

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

L'application est ensuite disponible à l'adresse
<http://127.0.0.1:8000/>.

À la première installation, connectez-vous avec `brewer` / `brewer`, puis
utilisez le lien **Mot de passe** du menu pour remplacer le mot de passe
initial. Pour quitter l'environnement virtuel, exécutez `deactivate`.

## Utilisation

- **Recettes** : créer une recette, gérer ses ingrédients, ses paliers,
  ses phases de fermentation, ses versions et son profil de dégustation
  interactif avec une note globale par demi-étoile. Les ingrédients d'une recette
  sont sélectionnés parmi les fiches du stock ; l'import crée automatiquement
  les fiches manquantes.
- **Stock** : gérer les malts, houblons, levures, ingrédients divers et
  consommables comme les capsules.
- **Coûts** : renseigner le coût unitaire sur les fiches de stock. La fiche
  recette estime ensuite le coût de chaque ingrédient selon sa quantité et
  affiche les totaux par catégorie ainsi que le total estimé.
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

## Déploiement Docker

L'image utilise Python 3.13 sur Debian Bookworm (image officielle multi-architecture,
dont ARM64), Gunicorn et WhiteNoise. SQLite reste dans un dossier persistant sur
l'hôte Docker ; le conteneur effectue les migrations au démarrage et sert les
fichiers statiques collectés dans l'image.

### Première installation

1. Sur la machine qui hébergera l'application, installez Docker Engine et vérifiez
   que `docker compose version` fonctionne, puis clonez le dépôt :

   ```sh
   git clone https://github.com/Haggenti/BBrew.git
   cd BBrew
   ```

2. Générez une clé secrète et modifiez les valeurs de personnalisation directement
   dans `docker-compose.yml`. Vous pouvez générer la clé sur l'hôte Docker ou sur un
   autre ordinateur :

   ```sh
   openssl rand -hex 50
   ```

   Remplacez `DJANGO_SECRET_KEY`, puis renseignez le nom de domaine ou l'adresse
   utilisée pour accéder à l'application dans `DJANGO_ALLOWED_HOSTS` et
   `DJANGO_CSRF_TRUSTED_ORIGINS`. La base est écrite dans le répertoire `./data`
   à côté du fichier Compose, sur l'hôte et hors du conteneur. Docker le crée
   automatiquement et le conteneur règle ses permissions au démarrage.
   Le port publié par défaut est `8086` (`8086:8000`) ; vous pouvez le modifier.
3. Depuis le dossier `BBrew`, construisez et démarrez l'application :

   ```sh
   docker compose up
   ```

   Compose construit l'image, crée le stockage persistant et lance les migrations.
   L'application est disponible sur
   `http://<adresse-de-la-machine>:8086/`. Connectez-vous avec `brewer` / `brewer`
   uniquement sur un réseau de confiance, puis changez immédiatement le mot de
   passe depuis le menu **Mot de passe**.

   Les connexions sont conservées dans un cookie de session de navigateur, supprimé
   à la fermeture du navigateur. Toutes les sessions enregistrées sont également
   invalidées au démarrage du serveur ; il faut donc se reconnecter après un arrêt
   ou un redémarrage de BBS.

### Accès et opérations courantes

- Ne transférez pas le port 8086 directement depuis Internet. Pour un accès extérieur,
  privilégiez un VPN. Si vous utilisez un reverse proxy HTTPS, réglez
  `DJANGO_SECURE_COOKIES` et `DJANGO_SECURE_PROXY_SSL_HEADER` à `1`, indiquez l'origine
  `https://...` dans `DJANGO_CSRF_TRUSTED_ORIGINS` et empêchez les accès directs qui
  contourneraient le proxy.
- Gardez une seule instance BBS active : SQLite ne convient pas à plusieurs
  réplicas applicatifs concurrents.
- Le répertoire `data/` contient la base SQLite sur l'hôte, hors du conteneur.
  Il est exclu de Git ; sauvegardez-le régulièrement, ainsi que les
  sauvegardes générées dans BBS, vers un autre emplacement.
- Pour mettre à jour : sauvegardez les données, lancez `git pull`
  puis `docker compose up --build`. Les migrations sont exécutées au
  démarrage et le hash du commit courant est détecté automatiquement pendant la
  construction de l'image.
- Pour arrêter : `docker compose down`. Ce répertoire reste en place lors de la
  suppression ou de la reconstruction du conteneur ; sauvegardez-le avant toute
  opération de nettoyage manuelle.

## Configuration

Dans Fish, les paramètres suivants peuvent être définis dans le terminal :

```fish
set -x DJANGO_SECRET_KEY "une-cle-secrete"
set -x DJANGO_DEBUG 0
set -x DJANGO_ALLOWED_HOSTS "localhost,127.0.0.1"
```

Dans un terminal standard (Bash, Zsh ou sh), utilisez `export` :

```sh
export DJANGO_SECRET_KEY="une-cle-secrete"
export DJANGO_DEBUG=0
export DJANGO_ALLOWED_HOSTS="localhost,127.0.0.1"
```

En développement, les valeurs par défaut permettent de lancer l'application
sans configuration supplémentaire. Pour une mise en production, définissez
au minimum une clé secrète personnalisée, désactivez `DEBUG` et renseignez
les hôtes autorisés. La version affichée dans « À propos » est le hash court
(7 caractères) du commit Git courant. Il est détecté automatiquement dans un
clone Git et lors de la construction de l'image Docker.

Consultez [changelog.md](./changelog.md) pour l'historique des évolutions ;
ajoutez-y une entrée à chaque évolution livrée.

## Tests

```fish
source .venv/bin/activate.fish
python manage.py test
```

Dans un terminal standard :

```sh
. .venv/bin/activate
python manage.py test
```
