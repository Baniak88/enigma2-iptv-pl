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

## Wolny internet

W ustawieniach (niebieski przycisk) włącz **Wolny internet (GStreamer)** i zapisz zielonym.
Tryb wybiera dla odtwarzania typ 4097 oraz natywną flagę buforowania Enigma2
(`reference.setData(7, 1)`). Nie zmienia globalnych ustawień dekodera ani nie zapisuje strumienia na dysku.
W tym trybie wybór ServiceApp 5001/5002 jest pomijany; po wyłączeniu trybu znowu obowiązuje.
Start kanału może potrwać dłużej. Odtwarzacz nie otwiera się wielokrotnie przy kolejnych naciśnięciach OK.

Limit pojedynczego odczytu sieciowego listy wzrasta z 20 do 60 sekund; lista nadal jest wczytywana w tle.
To nie jest limit ani gwarancja czasu uruchomienia kanału.
Obsługa buforowania zależy od obrazu Enigma2 i protokołu; dla HLS i strumieni live
odtwarzacz może stosować własne zasady. Tryb nie obniża automatycznie jakości kanału.
Jeśli łącze jest stale za wolne, wybierz wersję SD/niższej jakości dostępną na swojej liście.
Fizyczny odbiornik wymaga osobnego sprawdzenia.

## Ekran startowy

Pełnoekranowy, ciemny interfejs ma górne menu, duży panel wskazanej pozycji
i poziome rzędy z prawdziwej listy M3U. Dwie półki i maksymalnie dziesięć kart
są rysowane jednocześnie, niezależnie od wielkości listy.

- **Start**: półki telewizji, filmów i seriali.
- **Telewizja / Filmy / Seriale**: pozycje pogrupowane według metadanych M3U.
- **Moja lista**: ulubione dodawane i usuwane żółtym przyciskiem.
- **Szukaj**: klawiatura ekranowa; wyszukiwanie nazw i grup w całej wczytanej liście.
- **Playlisty**: przesyłanie z telefonu, import pliku z dekodera/USB, adres URL i wybór zapisanych plików.
- **MENU / niebieski**: zmiana źródła, odtwarzacza i trybu wolnego internetu.

Strzałki poruszają zaznaczenie w górnym menu, przyciskach panelu i rzędach.
OK na pozycji odtwarza ją, na górnej zakładce otwiera kategorię.
W rzędach przewijanie w prawo pokazuje kolejne pozycje; w dół — kolejne grupy.
EXIT wraca do menu, potem do Start, a następnie zamyka wtyczkę.
Biała ramka oznacza wskazaną kartę, czerwony akcent wybraną zakładkę.

Przy skonfigurowanym źródle lista wczytuje się w tle po otwarciu ekranu.
Bez istniejącego pliku lub adresu źródła pokazuje się ekran konfiguracji początkowej,
bez okna błędu. Nieudane odświeżenie zachowuje już wczytaną listę.
Po zapisaniu zmienionego źródła poprzednia lista jest usuwana z ekranu.

**Grafiki i opisy:** ekran korzysta z nazw, grup oraz opcjonalnego `tvg-logo`.
Grafika wskazanej pozycji jest pobierana pojedynczo w tle (PNG/JPEG, do 512 KiB,
limit odczytu 5 sekund), a plik tymczasowy jest usuwany po dekodowaniu.
Wolny internet wyłącza pobieranie grafik. Brak grafiki oznacza kartę z nazwą.
Nie ma fikcyjnych plakatów, roczników, ocen ani opisów filmów z wizualizacji.
Nie dodaje to dostępu do katalogu Netflix ani Xtream API.

Kategorie: nazwy grup zawierające serial/series/sezon/season trafiają do seriali,
film/movie/vod/kino do filmów, pozostałe do telewizji.
Moja lista zapisuje skróty adresów pozycji w ustawieniach — bez dodatkowych kopii URL.
Zmiana adresu strumienia w źródle może wymagać ponownego dodania go do ulubionych.

Układ skaluje się do rozdzielczości GUI Enigma2. Rzeczywisty wygląd zależy
od czcionek i możliwości obrazu dekodera; nie jest identyczny z wizualizacją.

## Dodawanie playlist M3U

W górnym menu wybierz **Playlisty**. Możesz też wejść w ustawienia
(niebieski / MENU) i nacisnąć **żółty**.

### Z telefonu: wklejenie URL lub przesłanie pliku

1. Wybierz **Wklej URL / prześlij plik z telefonu**.
2. Połącz telefon z tą samą siecią co dekoder.
3. Otwórz adres pokazany na telewizorze, np. `http://192.168.4.128:8099`.
4. Wpisz sześciocyfrowy kod z telewizora. W polu **Wklej cały adres URL M3U** przytrzymaj palcem i wybierz **Wklej**, potem **Wyślij adres do dekodera**.
   Alternatywnie w sekcji **Lub prześlij plik** wybierz plik M3U i naciśnij **Wyślij plik playlisty**.
5. Po potwierdzeniu naciśnij **zielony** na pilocie, aby zapisać wybrany URL lub plik jako źródło i wczytać listę.

Cały URL jest przekazywany bez zmiany parametrów, kodowania procentowego ani znaków `&` i `+`.
Nie musi kończyć się na `.m3u` — obsługiwane są adresy typu `https://dostawca.pl/get.php?username=...&password=...&type=m3u_plus`.
Limit adresu wynosi 16384 znaków. Adres nie jest pobierany ani aktywowany przed zatwierdzeniem pilotem.
Nie pokazujemy go w komunikacie potwierdzenia, ponieważ może zawierać hasło.

Ekran importu musi pozostać otwarty. EXIT kończy odbieranie plików.
Serwer działa tylko podczas otwartego ekranu; kod zmienia się przy każdym otwarciu.
Po 10 błędnych kodach zamknij i otwórz ekran ponownie.
Plik jest sprawdzany przed zapisaniem, limit wynosi 8 MiB.
To przesyłanie w lokalnej sieci HTTP — port 8099 nie wymaga przekierowania na routerze.
Nie trzeba wysyłać playlisty do zewnętrznego serwisu.

### Z dekodera lub USB

Wybierz **Wybierz plik z dekodera / USB**.
Przeglądarka otwiera `/media/`; OK otwiera folder lub wybiera plik,
a niebieski przechodzi do `/etc/enigma2/`.
Obsługiwane rozszerzenia: `.m3u`, `.m3u8` zawierające listę adresów kanałów.
Plik jest kopiowany do pamięci dekodera, więc po imporcie można odłączyć USB.

### Przez adres URL

Wybierz **Dodaj adres URL playlisty**, wpisz pełny URL HTTP/HTTPS
na klawiaturze ekranowej i zatwierdź.
Adres może zawierać parametry dostawcy; nie publikuj go, jeśli zawiera dane konta.

### Zapisane playlisty

Zaimportowane pliki znajdują się w `/etc/enigma2/iptvpl/playlists/`
i są widoczne w menu **Playlisty**. Możesz przełączać je bez ponownego przesyłania.
Powtórny import tworzy osobny plik i nie nadpisuje poprzedniego.
Po wybraniu listy z głównego menu źródło jest zapisywane i wczytywane w tle.
Wybór z ekranu ustawień wymaga dodatkowo zapisu zielonym przyciskiem;
anulowanie ustawień nie przełącza aktywnego źródła.
Zaimportowane, lecz niewybrane pliki pozostają w menu zapisanych playlist.
Rozszerzenie M3U8 dotyczy list kanałów; pojedynczy manifest HLS z względnymi
segmentami nie jest playlistą kanałów.
Wymagany jest osobny test interfejsu na odbiorniku.

## Pilot

- **Strzałki**: wybór zakładki, przycisku, pozycji lub grupy.
- **OK**: otwarcie zakładki albo odtworzenie pozycji.
- **EXIT**: powrót; w odtwarzaczu powrót do interfejsu obsługuje MoviePlayer obrazu.
- **Zielony**: ponowne wczytanie listy.
- **Żółty**: dodanie/usunięcie wskazanej pozycji z Mojej listy.
- **Niebieski / MENU**: ustawienia źródła i odtwarzania.
- **INFO**: nazwa i grupa wskazanej pozycji.

Przykład listy (adres demonstracyjny, zastąp go działającym strumieniem):

```m3u
#EXTM3U
#EXTINF:-1 group-title="Polskie",Mój kanał
https://example.com/live/index.m3u8
```

Listy powinny mieć kodowanie UTF-8. Limit pobieranego pliku wynosi 8 MiB,
a limit odczytu listy 20 sekund (60 w trybie wolnego internetu). Wtyczka nie dostarcza kanałów ani kont.
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



