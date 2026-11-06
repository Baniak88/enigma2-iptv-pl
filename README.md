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
- **Telewizja + OK**: bezpośrednio otwiera bukiety tematyczne TV i kanały w dwóch kolumnach.
- **Filmy / Seriale**: pozycje pogrupowane według metadanych M3U.
- **Moja lista**: ulubione dodawane i usuwane żółtym przyciskiem.
- **Bukiety**: pełny widok grup playlisty i kanałów z przewijaniem stronami.
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
5. Poczekaj na **Pobrano i sprawdzono … pozycji** albo komunikat błędu. Telefon i telewizor pokazują postęp pobierania.
6. Po udanym pobraniu naciśnij **zielony** na pilocie, aby zapisać źródło i otworzyć listę.

Cały URL jest przekazywany bez zmiany parametrów, kodowania procentowego ani znaków `&` i `+`.
Nie musi kończyć się na `.m3u` — obsługiwane są adresy typu `https://dostawca.pl/get.php?username=...&password=...&type=m3u_plus`.
Limit adresu wynosi 16384 znaków. Lista jest pobierana i sprawdzana od razu po wysłaniu URL, ale aktywne źródło zmienia się dopiero po zatwierdzeniu pilotem.
Sprawdzona lista jest przechowywana w pamięci do 120 sekund i używana przy zatwierdzeniu bez drugiego żądania.
Nie pokazujemy go w komunikacie potwierdzenia, ponieważ może zawierać hasło.
Potwierdzenie i błędy są widoczne nad formularzem telefonu. Odrębne komunikaty obejmują HTTP 401/403,
404, 429 i inne błędy serwera, przekroczenie czasu, DNS, HTTPS, stronę HTML zamiast M3U,
brak kanałów oraz przekroczenie limitu 512 MiB. Podczas pobierania działa odczyt statusu przez przeglądarkę.

Ekran importu musi pozostać otwarty. EXIT kończy odbieranie plików.
Serwer działa tylko podczas otwartego ekranu; kod zmienia się przy każdym otwarciu.
Po 10 błędnych kodach zamknij i otwórz ekran ponownie.
Plik jest sprawdzany przed zapisaniem, limit wynosi 512 MiB.
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

## Przyciski w ustawieniach i imporcie

Ustawienia mają osobne przyciski **Zapisz** (zielony), **Playlisty** (żółty)
i **Anuluj** (czerwony / EXIT), z jasnymi etykietami oraz oznaczeniami pilota.
Podpowiedź pod listą ustawień opisuje aktualnie wybrane pole.

Ekrany wyboru playlist i plików mają przyciski **Wybierz**, **Folder list**
(niebieski w przeglądarce plików) i **Wróć**.
Na ekranie przesyłania przycisk zmienia etykietę w zależności od stanu:
**Oczekiwanie na listę**, **Pobieranie…**, **Otwórz playlistę** lub **Popraw źródło**.
Gotową listę można otworzyć zielonym przyciskiem albo OK.
Czerwony lub EXIT zamyka ekran przesyłania bez zmiany źródła.

## Pełna klawiatura ekranowa

Wtyczka ma własną klawiaturę QWERTY, niezależną od klawiatury numerycznej obrazu Enigma2.
Otwiera się przy **OK** na polu **Lista M3U** w ustawieniach, dodawaniu URL
w menu **Playlisty** i wyszukiwaniu. Zawiera wszystkie drukowalne znaki ASCII,
polskie litery, cyfry, małe/wielkie litery i znaki potrzebne do pełnych adresów URL.

- **Strzałki + OK**: wybór i wpisanie znaku.
- **Niebieski / ABC / #+=**: przełączenie wielkich liter i symboli.
- **Żółty / Usuń znak**: usunięcie znaku przed kursorem.
- **Kursor < / Kursor >**: przesunięcie kursora wewnątrz tekstu.
- **Spacja**: wpisanie spacji, np. w wyszukiwaniu (URL nie może zawierać surowych odstępów).
- **Zielony / Gotowe**: zatwierdzenie tekstu; w ustawieniach nadal trzeba zapisać zmiany.
- **Czerwony / EXIT**: anulowanie bez zmiany poprzedniej wartości.
- **0–9 na pilocie**: natychmiastowe wpisanie cyfry, bez wielokrotnego naciskania klawisza.

Długie adresy są zachowywane w całości (do 16384 znaków); pole tekstowe pokazuje
fragment wokół kursora i jego pozycję. W obsługujących to obrazach można także wpisywać
znaki z klawiatury USB; tryb klawiatury dekodera jest przywracany po zamknięciu ekranu.

## Duże playlisty

Limit pobrania, przesłania pliku i importu wynosi **512 MiB**, a katalogu **2000000 pozycji**.
Dane są odczytywane fragmentami do 64 KiB. Pojedynczy wiersz może mieć do 1 MiB;
przekroczenia są zgłaszane błędem, bez cichego obcinania listy.

Małe listy pozostają w pamięci. Po przekroczeniu 5000 pozycji lub budżetu roboczego
około 4 MiB parser przenosi katalog do pliku SQLite. Pobieranie, indeksowanie,
wyszukiwanie i wybór grup odbywają się w tle. Interfejs pobiera małe strony z bazy,
a wspólna pamięć podręczna przechowuje maksymalnie 64 rekordy kanałów.
Nie jest tworzona lista słowników dla całego dużego katalogu.

Katalog jest zapisywany w `.iptvpl-cache` na zamontowanym `/media/hdd` albo `/media/usb`;
w przeciwnym razie w `/etc/enigma2/iptvpl/catalogue-cache`.
Sprawdzane jest wolne miejsce. Po zamknięciu aplikacji i zmianie źródła zwalniane są uchwyty katalogu.
Poprawnie zapisany katalog pozostaje na nośniku jako pamięć podręczna. Niewykorzystane potwierdzenie z telefonu wygasa po 120 sekundach.
Pliki importowane przez użytkownika pozostają w folderze zapisanych playlist.
Duży katalog może zajmować więcej miejsca na dysku niż surowa lista M3U.

Wymagany jest moduł `sqlite3`; instalator sprawdza go i w razie braku próbuje
zainstalować `python3-sqlite3` przez `opkg`.
Jeżeli repozytoria obrazu nie udostępniają pakietu, instalator zgłosi błąd.
Przy braku miejsca podłącz nośnik albo zwolnij pamięć — limit 512 MiB nie gwarantuje,
że każda lista zmieści się na każdym odbiorniku.


## Nawigacja podczas oglądania i bukiety

Odtwarzacz IPTV rozszerza systemowy MoviePlayer, zachowując jego obsługę dźwięku,
napisów i przywracania poprzedniej usługi po zamknięciu.

- **CH+ / CH−**: następny/poprzedni kanał w aktualnej liście lub bukiecie.
  Szybkie naciśnięcia są łączone; uruchamiany jest ostatni wskazany kanał.
- **OK / góra / dół**: otwarcie listy kanałów przy działającym odtwarzaniu.
- **MENU / niebieski**: otwarcie bukietów.
- **INFO**: panel z nazwą, bieżącym bukietem, numerem pozycji i przyciskami; znika po 5 sekundach.
- **EXIT / czerwony**: zakończenie odtwarzania i powrót do aplikacji na ostatnio wybraną pozycję.
- **AUDIO / SUBTITLE**: wybór ścieżek przez mechanizmy obrazu Enigma2.
- Lewo/prawo przełącza pozycje telewizji; przy filmach/serialach pozostaje obsługa przewijania obrazu.

Zakładka **Bukiety** w górnym menu otwiera dwie kolumny:
wszystkie grupy z licznikami po lewej, pozycje danego bukietu po prawej.
Ze **Start** są dostępne wszystkie grupy playlisty; w pozostałych kategoriach
obowiązuje ich filtr i wyszukiwanie. Bukiety są grupami z metadanych M3U,
nie są automatycznie zapisywane do systemowych bukietów tunera.

W tym widoku **lewo/prawo** zmienia kolumnę, **góra/dół** wybiera pozycję,
**CH+/−** przewija stronami po 12, **OK** na bukiecie przechodzi do kanałów,
a **OK / zielony** na kanale uruchamia go. **EXIT** wraca bez zmiany kanału.
Wskazany kanał i zakres strony są widoczne; przeglądanie nie uruchamia kanałów automatycznie.
Przy katalogach SQLite nie jest tworzona pełna lista kanałów w RAM.

Mapowania obejmują standardowe akcje Enigma2 i nazwy przycisków OpenATV.
Różnice w mapie klawiszy konkretnego obrazu mogą wymagać dopasowania;
pełna weryfikacja odtwarzania nadal wymaga odbiornika.

## Szybsze kolejne uruchomienia

Duże katalogi SQLite są zapisywane i używane ponownie, bez ponownego pobierania
ani indeksowania. Kopia listy z URL jest ważna przez **24 godziny**.
Dla pliku lokalnego porównywane są rozmiar i czas modyfikacji.
Uszkodzona, niezgodna wersją lub nieaktualna kopia powoduje ponowny import.
Metadane cache nie zapisują adresu źródła ani hasła; nazwa klucza jest skrótem SHA-256.
Same adresy kanałów w bazie mogą zawierać dane konta, więc katalog należy chronić jak playlistę.

**Zielony na ekranie głównym** wymusza pełne pobranie/odświeżenie.
Samo otwarcie aplikacji oraz wejście do kategorii korzysta z gotowego katalogu.
Również przesłanie tego samego URL z telefonu może użyć ważnego zapisanego katalogu —
komunikat wyraźnie wskazuje wtedy, że użyto zapisanej kopii.
Nowy kompletny katalog zastępuje poprzedni; aktualnie używany plik jest zwalniany
dopiero po zakończeniu korzystania z niego. Mała lista po wymuszonym odświeżeniu
unieważnia poprzedni duży katalog.

Podczas pierwszego importu widać ilość odebranych danych i etap budowania indeksów.
Jeżeli dostawca obsługuje HTTP gzip, wtyczka prosi o skompresowaną odpowiedź
i rozpakowuje ją strumieniowo. Limit 512 MiB dotyczy danych po rozpakowaniu.
Liczniki grup i kategorii są zapisywane w bazie; wejście w nie nie wymaga ponownego
przeliczania wszystkich kanałów. Zwiększono również partie zapisu przy imporcie.

Pierwsze pobranie lub ręczne odświeżenie bardzo dużej listy nadal może trwać długo —
zależy to od serwera, łącza i szybkości nośnika. Nie deklarujemy konkretnego czasu
startu na odbiorniku. Wersja sprzed tej optymalizacji nie zachowywała gotowego katalogu;
po aktualizacji potrzebny jest jeden pełny import, aby utworzyć nową kopię.

### Telewizja otwiera bukiety

Wybierz zakładkę **Telewizja** i naciśnij **OK**. Od razu otworzy się widok
bukietów telewizyjnych z licznikami po lewej i kanałami po prawej.
Nie trzeba wchodzić najpierw w panel wskazanego kanału ani w osobną zakładkę Bukiety.
Grupy pochodzą z metadanych aktywnej playlisty, zgodnie z filtrem kategorii TV.

Jeśli trwa pobieranie lub przygotowywanie katalogu, ekran pokazuje etap oczekiwania,
a bukiety otwierają się po zakończeniu. Przejście do innej zakładki lub ustawień
anuluje automatyczne otwarcie, aby nie przerywać nowej czynności.
Brak konfiguracji albo błąd źródła nie tworzy przykładowych bukietów.
EXIT z widoku bukietów wraca do zakładki Telewizja.

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

Listy powinny mieć kodowanie UTF-8. Limit pobieranego pliku wynosi 512 MiB,
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











