# BBrew

Application de conception de recettes de bière basée sur Django, SQLite,
Django Templates, HTMX et Bootstrap.

BBrew permet de gérer les recettes et leurs versions, les paliers
de brassage, les brassins, le stock d'ingrédients et de consommables, ainsi
que la liste de courses. Les recettes peuvent être importées et exportées au
format BeerXML.

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
  ses phases de fermentation et ses versions. Les ingrédients d'une recette
  sont sélectionnés parmi les fiches du stock ; l'import crée automatiquement
  les fiches manquantes.
- **Stock** : gérer les malts, houblons, levures, ingrédients divers et
  consommables comme les capsules.
- **Brassins** : sélectionner la version d'une recette, saisir les mesures
  réelles et suivre la consommation du stock.
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
   fonctionne. Clonez ou copiez le projet dans un dossier de travail.
2. Choisissez un dossier de données sur un disque local persistant (évitez un partage
   réseau pour SQLite), puis créez-le et attribuez-le à l'utilisateur du conteneur :

   ```sh
   sudo mkdir -p /mnt/dietpi_userdata/bbrew-data
   sudo chown -R 10001:10001 /mnt/dietpi_userdata/bbrew-data
   ```

3. Si vous avez déjà utilisé BBrew, arrêtez l'ancienne instance et copiez son
   `db.sqlite3` dans ce dossier avant le premier démarrage. Gardez également une
   copie de sauvegarde. Une base existante sera migrée automatiquement au lancement.
4. Créez le fichier `.env` à partir de `.env.example`. Définissez une longue clé
   aléatoire avec Python, par exemple :

   ```sh
   python3 -c 'import secrets; print(secrets.token_urlsafe(50))'
   ```

   Remplacez `DJANGO_SECRET_KEY`, le nom/IP réel du NAS dans `DJANGO_ALLOWED_HOSTS`
   et `DJANGO_CSRF_TRUSTED_ORIGINS`, ainsi que `BBREW_HOST_DATA_DIR`. Gardez `.env`
   privé : il contient le secret de l'application.
5. Construisez et démarrez BBrew :

   ```sh
   docker compose up -d --build
   docker compose logs -f bbrew
   ```

   L'application est disponible sur `http://<adresse-du-nas>:8000/`. Connectez-vous
   avec `brewer` / `brewer` uniquement sur un réseau de confiance, puis changez
   immédiatement le mot de passe depuis le menu **Mot de passe**.

### Accès et opérations courantes

- Ne transférez pas le port 8000 directement depuis Internet. Pour un accès extérieur,
  privilégiez un VPN. Si vous utilisez un reverse proxy HTTPS, activez
  `DJANGO_SECURE_COOKIES=1` et `DJANGO_SECURE_PROXY_SSL_HEADER=1`, indiquez l'origine
  `https://...` dans `DJANGO_CSRF_TRUSTED_ORIGINS` et empêchez les accès directs qui
  contourneraient le proxy.
- Gardez une seule instance BBrew active : SQLite ne convient pas à plusieurs
  réplicas applicatifs concurrents.
- Sauvegardez le dossier de données (en particulier `db.sqlite3`) vers un autre
  emplacement. Arrêtez le service ou faites une sauvegarde cohérente avant de
  copier directement le fichier SQLite.
- Pour mettre à jour : sauvegardez les données, mettez le code à jour, puis lancez
  `docker compose up -d --build`. Les migrations sont exécutées au démarrage.
- Pour arrêter : `docker compose down`. Ne supprimez pas le dossier de données lors
  de la suppression ou de la reconstruction du conteneur.

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
