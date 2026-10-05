#!/bin/sh
set -eu

mkdir -p "$BBREW_DATA_DIR"
chown -R bbrew:bbrew "$BBREW_DATA_DIR"
gosu bbrew python manage.py migrate --noinput
exec gosu bbrew "$@"
