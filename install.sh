#!/bin/sh
# IPTV PL installer for Enigma2 / Python 3.
set -eu
command -v python3 >/dev/null 2>&1 || { echo "Wymagany Python 3."; exit 1; }
command -v wget >/dev/null 2>&1 || { echo "Wymagany wget z obsluga HTTPS."; exit 1; }
[ "$(id -u)" = 0 ] || { echo "Uruchom jako root na dekoderze."; exit 1; }
base="https://raw.githubusercontent.com/Baniak88/enigma2-iptv-pl/main/Plugins/Extensions/IPTVPL"
dest="/usr/lib/enigma2/python/Plugins/Extensions/IPTVPL"
stage=$(mktemp -d /tmp/iptvpl.XXXXXX)
trap 'rm -rf "$stage"' EXIT HUP INT TERM
for file in __init__.py catalogue.py playlist.py sources.py plugin.py; do
    if ! wget -O "$stage/$file" "$base/$file"; then
        echo "Pobieranie nieudane. Sprawdz siec i czy repozytorium jest publiczne."
        exit 1
    fi
done
python3 -m compileall -q "$stage"
python3 -c 'import twisted' || { echo "Brak Twisted dla Pythona 3 w obrazie dekodera."; exit 1; }
if ! python3 -c 'import sqlite3' >/dev/null 2>&1; then
    command -v opkg >/dev/null 2>&1 || { echo "Wymagany modul sqlite3 dla Pythona 3."; exit 1; }
    opkg install python3-sqlite3 || { echo "Nie udalo sie zainstalowac python3-sqlite3. Sprawdz repozytoria obrazu."; exit 1; }
    python3 -c 'import sqlite3'
fi
if [ -d "$dest" ]; then
    backup=$(mktemp -d /tmp/iptvpl-backup.XXXXXX)
    cp -R "$dest/." "$backup/"
    echo "Kopia poprzedniej wersji: $backup"
fi
mkdir -p "$dest"
for file in __init__.py catalogue.py playlist.py sources.py plugin.py; do
    cp "$stage/$file" "$dest/$file"
    chmod 644 "$dest/$file"
done
echo "Zainstalowano IPTV PL."
echo "Uruchom ponownie GUI z menu dekodera, potem: Wtyczki > IPTV PL."


