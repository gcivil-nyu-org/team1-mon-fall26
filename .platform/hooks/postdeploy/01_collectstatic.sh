#!/bin/bash
set -e
cd /var/app/current
/var/app/venv/*/bin/python manage.py collectstatic --noinput
