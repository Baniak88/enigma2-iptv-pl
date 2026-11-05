# IPTV PL — wtyczka Enigma2

Polski odtwarzacz IPTV z list M3U/M3U8. Obsługuje pliki lokalne, URL HTTP/HTTPS,
grupy kanałów i odświeżanie listy bez blokowania interfejsu.

## Wymagania

Enigma2 z Pythonem 3 i Twisted (np. aktualne obrazy OpenATV/OpenPLi).
Domyślny odtwarzacz: GStreamer, typ usługi 4097. Typy 5001/5002 wymagają
osobno zainstalowanego ServiceApp oraz odpowiedniego odtwarzacza.
Python 2 nie jest obsługiwany. Faktyczna obsługa kodeków i protokołów zależy od obrazu dekodera.

## Instalacja bezpośrednio z GitHuba

Repozytorium musi być publiczne, aby poniższe pobieranie działało bez logowania.
W terminalu dekodera jako root:

```sh
wget -O /tmp/iptvpl-install.sh https://raw.githubusercontent.com/Baniak88/enigma2-iptv-pl/main/install.sh && sh /tmp/iptvpl-install.sh
```

Instalator sprawdza pobrane pliki i tworzy kopię poprzedniej wersji w /tmp.
Po instalacji uruchom ponownie GUI z menu dekodera.
Repozytorium prywatne wymaga uwierzytelnionego pobierania.

## Instalacja z archiwum

1. Zbuduj archiwum na komputerze: `python3 scripts/build.py`.
2. Prześlij plik `dist/enigma2-plugin-extensions-iptvpl-1.0.0.tar.gz` do `/tmp` dekodera.
3. Przez SSH na dekoderze wykonaj:

   ```sh
   tar -xzf /tmp/enigma2-plugin-extensions-iptvpl-1.0.0.tar.gz -C /
   ```

4. Uruchom ponownie interfejs graficzny Enigma2 z menu dekodera.
5. Otwórz **Wtyczki → IPTV PL → Niebieski (ustawienia)**.
   Wpisz adres własnej listy lub pełną ścieżkę, np. `/etc/enigma2/iptv.m3u`.
   Zapisz zielonym przyciskiem.

Alternatywnie skopiuj katalog `Plugins/Extensions/IPTVPL` do
`/usr/lib/enigma2/python/Plugins/Extensions/` i uruchom ponownie GUI.
Archiwum jest paczką TAR, a nie pakietem IPK do instalacji przez opkg.

## Pilot

- **OK**: odtwarzanie zaznaczonego kanału w systemowym MoviePlayer.
- **EXIT podczas odtwarzania**: powrót do listy; przywracanie poprzedniej usługi obsługuje MoviePlayer obrazu.
- **Zielony**: ponowne wczytanie listy.
- **Żółty**: wybór grupy kanałów.
- **Niebieski / MENU**: ustawienia; OK na polu tekstowym otwiera edycję dostępną w obrazie.
- **EXIT na liście**: zamknięcie wtyczki.

Przykład listy (adres demonstracyjny, zastąp go działającym strumieniem):

```m3u
#EXTM3U
#EXTINF:-1 group-title="Polskie",Mój kanał
https://example.com/live/index.m3u8
```

Listy powinny mieć kodowanie UTF-8. Limit pobieranego pliku wynosi 8 MiB,
a limit czasu operacji sieciowej 20 sekund. Wtyczka nie dostarcza kanałów ani kont.
Adres listy jest zapisany w ustawieniach Enigma2; jeśli zawiera hasło, chroń kopie tych ustawień.
Brak obsługi DRM, Xtream API, EPG i dodatkowych nagłówków z dyrektyw VLC/Kodi.

## Sprawdzenie

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q Plugins scripts
python3 scripts/build.py
```

Testy sprawdzają parser i odczyt list, w tym przekierowania HTTP, limit rozmiaru,
metadane i błędne protokoły. Wymagany jest osobny test na dekoderze: instalacja,
wpisanie URL pilotem, grupy, odtwarzanie, EXIT, ponowne wczytanie i błąd sieci.
Nie deklarujemy przetestowania na fizycznym odbiorniku.

Usuwanie: usuń katalog `/usr/lib/enigma2/python/Plugins/Extensions/IPTVPL`
i uruchom ponownie GUI.
