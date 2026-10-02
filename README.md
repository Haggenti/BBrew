# BBrew

Application de conception de recettes de bière basée sur Django, SQLite,
Django Templates, HTMX et Bootstrap.

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

Pour quitter l'environnement virtuel :

```fish
deactivate
```

## Tests

```fish
source .venv/bin/activate.fish
python manage.py test
```
