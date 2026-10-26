#!/bin/bash
set -e

MEDIA_DIR="/var/app/data/media"
APP_MEDIA="/var/app/staging/media"

mkdir -p "$MEDIA_DIR"
chown webapp:webapp "$MEDIA_DIR"
chmod 755 "$MEDIA_DIR"

if [ -L "$APP_MEDIA" ]; then
    rm "$APP_MEDIA"
elif [ -e "$APP_MEDIA" ]; then
    echo "Existing media directory found. Refusing to overwrite it."
    exit 1
fi

ln -s "$MEDIA_DIR" "$APP_MEDIA"