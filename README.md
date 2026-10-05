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
