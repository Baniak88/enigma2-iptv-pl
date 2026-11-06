# -*- coding: utf-8 -*-
from enigma import eServiceReference, ePicLoad
from Plugins.Plugin import PluginDescriptor
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Screens.InfoBar import MoviePlayer
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Pixmap import Pixmap
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Components.MenuList import MenuList
from Components.ConfigList import ConfigListScreen
from Components.config import (config, configfile, ConfigSubsection, ConfigText,
                               ConfigSelection, ConfigYesNo, getConfigListEntry)
from twisted.internet.threads import deferToThread
from .playlist import load_playlist, load_artwork
from .sources import PlaylistUpload, saved_playlists, import_local_playlist

config.plugins.iptvpl = ConfigSubsection()
settings = config.plugins.iptvpl
settings.source = ConfigText(default='/etc/enigma2/iptv.m3u', fixed_size=False)
settings.player = ConfigSelection(default='4097', choices=[('4097', 'GStreamer (4097)'),
                                  ('5001', 'ServiceApp / exteplayer3 (5001)'),
                                  ('5002', 'ServiceApp / gstplayer (5002)')])

settings.slowinternet = ConfigYesNo(default=False)
settings.favourites = ConfigText(default='[]', fixed_size=False)


def fit_skin(skin, fullscreen=False):
    """Scale the design to the receiver's GUI resolution."""
    import xml.etree.ElementTree as ET
    from enigma import getDesktop
    root = ET.fromstring(skin)
    original_w, original_h = map(int, root.get('size').split(','))
    desktop = getDesktop(0).size()
    available = 1.0 if fullscreen else 0.94
    scale = min(desktop.width() * available / original_w,
                desktop.height() * available / original_h)
    for node in root.iter():
        for attribute in ('size', 'position'):
            value = node.get(attribute)
            if value and all(part.strip().isdigit() for part in value.split(',')):
                node.set(attribute, ','.join(str(max(0, int(int(part) * scale))) for part in value.split(',')))
        font = node.get('font')
        if font:
            family, size = font.rsplit(';', 1)
            node.set('font', '%s;%d' % (family, max(14, int(int(size) * scale))))
        if node.get('itemHeight'):
            node.set('itemHeight', str(max(20, int(int(node.get('itemHeight')) * scale))))
    return ET.tostring(root, encoding='unicode')


def streaming_skin():
    # Fixed widget count keeps even very large playlists cheap to render.
    elements = ['''<screen name="IPTVHome" position="center,center" size="1280,720" flags="wfNoBorder" backgroundColor="#00101010" title="IPTV PL">
      <eLabel position="44,22" size="180,42" text="/ IPTV PL" font="Regular;30" foregroundColor="#00E50914" backgroundColor="#00101010" />
      <widget name="eyebrow" position="44,103" size="690,28" font="Regular;19" foregroundColor="#00D0D0D0" backgroundColor="#00101010" />
      <widget name="hero" position="44,141" size="760,85" font="Regular;41" foregroundColor="#00FFFFFF" backgroundColor="#00101010" />
      <widget name="summary" position="44,233" size="760,56" font="Regular;23" foregroundColor="#00BFBFBF" backgroundColor="#00101010" />
      <widget name="art" position="855,103" size="370,186" alphatest="blend" />
      <widget name="actionfocus0" position="40,300" size="250,56" backgroundColor="#00E50914" />
      <widget name="action0" position="44,304" size="242,48" font="Regular;24" halign="center" valign="center" foregroundColor="#00101010" backgroundColor="#00FFFFFF" />
      <widget name="actionfocus1" position="302,300" size="322,56" backgroundColor="#00FFFFFF" />
      <widget name="action1" position="306,304" size="314,48" font="Regular;23" halign="center" valign="center" foregroundColor="#00FFFFFF" backgroundColor="#00303030" />
      <widget name="status" position="650,309" size="575,40" font="Regular;19" foregroundColor="#00BFBFBF" backgroundColor="#00101010" />
      <widget name="help" position="44,681" size="1180,30" font="Regular;18" foregroundColor="#00BFBFBF" backgroundColor="#00101010" />''']
    nav = [('Start', 238, 80), ('Telewizja', 326, 125), ('Filmy', 459, 80),
           ('Seriale', 547, 95), ('Moja lista', 650, 125), ('Szukaj', 943, 105), ('Playlisty', 1060, 165)]
    for index, (title, x, width) in enumerate(nav):
        elements.append('<eLabel position="%d,28" size="%d,34" text="%s" font="Regular;23" halign="center" foregroundColor="#00FFFFFF" backgroundColor="#00101010" />' % (x, width, title))
        elements.append('<widget name="nav%d" position="%d,67" size="%d,4" backgroundColor="#00E50914" />' % (index, x, width))
    for row, y in enumerate((382, 528)):
        elements.append('<widget name="row%d" position="44,%d" size="1180,29" font="Regular;24" foregroundColor="#00FFFFFF" backgroundColor="#00101010" />' % (row, y))
        for column in range(5):
            x = 44 + column * 238
            name = '%d_%d' % (row, column)
            elements.append('<widget name="frame%s" position="%d,%d" size="230,102" backgroundColor="#00FFFFFF" />' % (name, x - 4, y + 33))
            elements.append('<widget name="card%s" position="%d,%d" size="222,94" font="Regular;23" halign="center" valign="center" foregroundColor="#00FFFFFF" backgroundColor="#00262626" />' % (name, x, y + 37))
    elements.append('</screen>')
    return ''.join(elements)


def channel_key(channel):
    import hashlib
    return hashlib.sha256(channel['url'].encode('utf-8')).hexdigest()


class IPTVHome(Screen):
    skin = streaming_skin()

    def __init__(self, session):
        self.skin = fit_skin(type(self).skin, fullscreen=True)
        Screen.__init__(self, session)
        self.channels = []
        self.rows = []
        self.category = 'start'
        self.query = ''
        self.nav = 0
        self.area = 'nav'
        self.row = 0
        self.column = 0
        self.first_row = 0
        self.action = 0
        self.featured = None
        self.loading = False
        self.player_open = False
        self.disposed = False
        self.request_id = 0
        self.image_request = 0
        self.logo_url = None
        self.logo_pending = None
        self.logo_busy = False
        self.logo_failed = set()
        self.status_text = 'Dodaj własną listę M3U w ustawieniach.'
        self.favourites = self.read_favourites()
        for name in ('eyebrow', 'hero', 'summary', 'action0', 'action1', 'status', 'help'):
            self[name] = Label('')
        self['art'] = Pixmap()
        for i in range(7):
            self['nav%d' % i] = Label('')
        for i in range(2):
            self['actionfocus%d' % i] = Label('')
            self['row%d' % i] = Label('')
            for col in range(5):
                self['frame%d_%d' % (i, col)] = Label('')
                self['card%d_%d' % (i, col)] = Label('')
        self.picload = None
        try:
            loader = ePicLoad()
            loader.PictureData.get().append(self.art_decoded)
            self.picload = loader
        except (AttributeError, TypeError):
            pass  # Optional artwork must never prevent the TV interface from opening.
        self['actions'] = ActionMap(['OkCancelActions', 'DirectionActions', 'MenuActions', 'ColorActions', 'InfoActions'],
                                   {'ok': self.activate, 'cancel': self.back,
                                    'left': lambda: self.move('left'),
                                    'right': lambda: self.move('right'),
                                    'up': lambda: self.move('up'),
                                    'down': lambda: self.move('down'),
                                    'menu': self.setup, 'blue': self.setup,
                                    'green': self.reload, 'yellow': self.toggle_favourite,
                                    'info': self.info}, -1)
        self.onLayoutFinish.append(self.render)
        self.onFirstExecBegin.append(self.start)
        self.onClose.append(self.cleanup)

    def read_favourites(self):
        import json
        try:
            value = json.loads(settings.favourites.value)
            return set(k for k in value if isinstance(k, str) and len(k) == 64) if isinstance(value, list) else set()
        except (ValueError, TypeError):
            return set()

    def start(self):
        import os
        source = settings.source.value.strip()
        if source.startswith(('http://', 'https://')) or (source.startswith('/') and os.path.isfile(source)):
            self.reload()
        else:
            self.render()

    def cleanup(self):
        self.disposed = True
        self.request_id += 1
        self.image_request += 1
        self.logo_pending = None
        # Temporary image is local and never contains playlist URLs in its name.
        self.remove_art_file()

    def remove_art_file(self):
        import os
        path = getattr(self, 'art_path', None)
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass
            self.art_path = None

    def reload(self):
        if self.loading or self.disposed:
            return
        source = settings.source.value.strip()
        if not source:
            self.status_text = 'Niebieski: dodaj źródło M3U.'
            self.render()
            return
        self.loading = True
        self.request_id += 1
        request = self.request_id
        self.status_text = 'Odświeżanie listy w tle…'
        self.render()
        timeout = 60 if settings.slowinternet.value else 20
        deferToThread(load_playlist, source, timeout=timeout).addCallbacks(
            lambda channels: self.loaded(channels, request),
            lambda failure: self.failed(failure, request))

    def loaded(self, channels, request):
        if self.disposed or request != self.request_id:
            return
        self.loading = False
        self.channels = channels
        self.logo_failed.clear()
        self.status_text = '%d pozycji na liście' % len(channels)
        self.rebuild_rows()

    def failed(self, failure, request):
        if self.disposed or request != self.request_id:
            return
        self.loading = False
        self.status_text = 'Błąd źródła. Niebieski: ustawienia • Zielony: ponów'
        self.render()

    def rebuild_rows(self):
        channels = self.channels
        if self.query:
            text = self.query.casefold()
            channels = [c for c in channels if text in c['name'].casefold() or text in c['group'].casefold()]
        if self.category == 'favourites':
            channels = [c for c in channels if channel_key(c) in self.favourites]
        elif self.category in ('live', 'movies', 'series'):
            channels = [c for c in channels if channel_category(c) == self.category]
        rows = []
        if self.category == 'start' and not self.query:
            for key, title in [('live', 'Telewizja na żywo'), ('movies', 'Filmy'), ('series', 'Seriale')]:
                subset = [c for c in channels if channel_category(c) == key]
                if subset:
                    rows.append((title, subset))
        else:
            # Preserve provider ordering; each group becomes a horizontally scrollable shelf.
            groups = {}
            for channel in channels:
                groups.setdefault(channel['group'], []).append(channel)
            rows = list(groups.items())
        self.rows = rows
        if not rows and self.area == 'shelf':
            self.area = 'hero'
        self.row = self.column = self.first_row = 0
        self.featured = rows[0][1][0] if rows else None
        self.render()

    def current(self):
        if self.rows and self.area == 'shelf':
            return self.rows[self.row][1][self.column]
        return self.featured

    def move(self, direction):
        if self.area == 'shelf' and not self.rows:
            self.area = 'hero'
        if self.area == 'nav':
            if direction in ('left', 'right'):
                self.nav = max(0, min(6, self.nav + (-1 if direction == 'left' else 1)))
            elif direction == 'down':
                self.area = 'hero'
        elif self.area == 'hero':
            if direction == 'up':
                self.area = 'nav'
            elif direction == 'down' and self.rows:
                self.area = 'shelf'
            elif direction in ('left', 'right'):
                self.action = 0 if direction == 'left' else 1
        else:
            if direction in ('left', 'right'):
                self.column = max(0, min(len(self.rows[self.row][1]) - 1,
                                        self.column + (-1 if direction == 'left' else 1)))
            elif direction == 'up':
                if self.row == 0:
                    self.area = 'hero'
                else:
                    self.row -= 1
                    self.column = min(self.column, len(self.rows[self.row][1]) - 1)
            elif direction == 'down' and self.row + 1 < len(self.rows):
                self.row += 1
                self.column = min(self.column, len(self.rows[self.row][1]) - 1)
            if self.area == 'shelf':
                self.featured = self.current()
                self.first_row = min(self.first_row, self.row)
                if self.row >= self.first_row + 2:
                    self.first_row = self.row - 1
        self.render()

    def render(self):
        if self.disposed:
            return
        for i in range(7):
            self['nav%d' % i].show() if self.nav == i else self['nav%d' % i].hide()
        for i in range(2):
            self['actionfocus%d' % i].show() if self.area == 'hero' and self.action == i else self['actionfocus%d' % i].hide()
        selected = self.current()
        if selected:
            self.featured = selected
            self['eyebrow'].setText('TELEWIZJA NA ŻYWO' if channel_category(selected) == 'live' else 'Z TWOJEJ LISTY M3U')
            self['hero'].setText(selected['name'])
            saved = ' • W mojej liście' if channel_key(selected) in self.favourites else ''
            self['summary'].setText('%s%s' % (selected['group'], saved))
            self['action0'].setText('Odtwórz')
            self['action1'].setText('Więcej informacji')
        else:
            self['eyebrow'].setText('TWOJA TELEWIZJA. TWÓJ WYBÓR.')
            self['hero'].setText('Co oglądamy?')
            self['summary'].setText('Brak wyników wyszukiwania.' if self.query else 'Brak pozycji. Wybierz inną kategorię lub dodaj źródło M3U.')
            self['action0'].setText('Zmień źródło')
            self['action1'].setText('Ustawienia')
        self['status'].setText(self.status_text)
        self['help'].setText('Strzałki: wybierz  OK: otwórz  Zielony: odśwież  Żółty: moja lista  Niebieski: ustawienia  EXIT: wróć')
        for slot in range(2):
            row_index = self.first_row + slot
            row = self.rows[row_index] if row_index < len(self.rows) else None
            self['row%d' % slot].setText(row[0] if row else '')
            offset = (self.column // 5) * 5 if row_index == self.row else 0
            if row:
                self['row%d' % slot].setText('%s   %d–%d / %d' % (row[0], offset + 1, min(offset + 5, len(row[1])), len(row[1])))
            for col in range(5):
                widget = self['card%d_%d' % (slot, col)]
                frame = self['frame%d_%d' % (slot, col)]
                index = offset + col
                if row and index < len(row[1]):
                    channel = row[1][index]
                    widget.setText(channel['name'])
                    widget.show()
                    if self.area == 'shelf' and row_index == self.row and index == self.column:
                        frame.show()
                    else:
                        frame.hide()
                else:
                    widget.hide()
                    frame.hide()
        self.update_art(selected)

    def activate(self):
        if self.area == 'nav':
            if self.nav == 5:
                self.session.openWithCallback(self.searched, VirtualKeyBoard, title='Szukaj na swojej liście', text=self.query)
            elif self.nav == 6:
                self.playlists()
            else:
                self.category = ('start', 'live', 'movies', 'series', 'favourites')[self.nav]
                self.query = ''
                self.rebuild_rows()
                self.area = 'hero'
                self.render()
        elif self.area == 'hero' and self.action == 1:
            self.info() if self.current() else self.setup()
        else:
            self.play() if self.current() else self.setup()

    def searched(self, text):
        if text is not None:
            self.query = text.strip()
            self.category = 'start'
            self.rebuild_rows()
            self.area = 'shelf' if self.rows else 'hero'
            self.render()

    def info(self):
        channel = self.current()
        if channel:
            text = '%s\n\nGrupa: %s\n\nBrak dodatkowego opisu.' % (channel['name'], channel['group'])
            self.session.open(MessageBox, text, MessageBox.TYPE_INFO)

    def toggle_favourite(self):
        import json
        channel = self.current()
        if not channel:
            return
        key = channel_key(channel)
        if key in self.favourites:
            self.favourites.remove(key)
        elif len(self.favourites) < 2000:
            self.favourites.add(key)
        else:
            self.status_text = 'Moja lista: osiągnięto limit 2000 pozycji.'
            self.render()
            return
        settings.favourites.value = json.dumps(sorted(self.favourites))
        settings.favourites.save()
        configfile.save()
        if self.category == 'favourites':
            self.rebuild_rows()
            if not self.rows:
                self.area = 'hero'
        self.render()

    def back(self):
        if self.area != 'nav':
            self.area = 'nav'
            self.render()
        elif self.category != 'start' or self.query:
            self.nav = 0
            self.category = 'start'
            self.query = ''
            self.rebuild_rows()
        else:
            self.close()

    def playlists(self):
        self.session.openWithCallback(self.playlist_selected, IPTVPlaylistSources)

    def playlist_selected(self, source):
        if source and not self.disposed:
            settings.source.value = source
            settings.source.save()
            configfile.save()
            self.nav = 0
            self.category = 'start'
            self.query = ''
            self.settings_closed(True)

    def setup(self):
        self.session.openWithCallback(self.settings_closed, IPTVSettings)

    def settings_closed(self, saved):
        if saved:
            # Ignore callbacks from a previous source after a configuration change.
            self.request_id += 1
            self.loading = False
            self.channels = []
            self.rows = []
            self.area = 'hero'
            self.featured = None
            self.logo_failed.clear()
            self.reload()
        else:
            self.render()

    def play(self):
        channel = self.current()
        if self.player_open or self.disposed or not channel:
            return
        service_type = 4097 if settings.slowinternet.value else int(settings.player.value)
        reference = eServiceReference(service_type, 0, channel['url'])
        if settings.slowinternet.value:
            reference.setData(7, 1)
        reference.setName(channel['name'])
        self.player_open = True
        try:
            self.session.openWithCallback(self.player_closed, MoviePlayer, reference)
        except Exception:
            self.player_open = False
            self.status_text = 'Nie udało się uruchomić odtwarzacza. Niebieski: ustawienia'
            self.render()

    def player_closed(self, *args):
        self.player_open = False
        self.render()

    def update_art(self, selected):
        url = selected.get('logo', '') if selected and self.picload is not None and not settings.slowinternet.value else ''
        if url == self.logo_url:
            return
        self.logo_url = url
        self.image_request += 1
        self['art'].hide()
        self.logo_pending = (url, self.image_request) if url and url not in self.logo_failed else None
        self.fetch_next_art()

    def fetch_next_art(self):
        if self.logo_busy or self.disposed or not self.logo_pending:
            return
        url, request = self.logo_pending
        self.logo_pending = None
        self.logo_busy = True
        deferToThread(load_artwork, url).addCallbacks(
            lambda path: self.art_downloaded(path, url, request),
            lambda failure: self.art_failed(failure, url))

    def art_downloaded(self, path, url, request):
        import os
        if self.disposed or request != self.image_request:
            try:
                os.unlink(path)
            except OSError:
                pass
            self.logo_busy = False
            self.fetch_next_art()
            return
        self.remove_art_file()
        self.art_path = path
        self.decoding_request = request
        try:
            size = self['art'].instance.size()
            self.picload.setPara((size.width(), size.height(), 1, 1, False, 1, '#00101010'))
            result = self.picload.startDecode(path)
            if result:
                self.art_failed(None, url)
        except Exception:
            self.art_failed(None, url)

    def art_decoded(self, *args):
        try:
            if not self.disposed and self.decoding_request == self.image_request:
                data = self.picload.getData()
                if data:
                    pixmap = data.__deref__() if hasattr(data, '__deref__') else data
                    self['art'].instance.setPixmap(pixmap)
                    self['art'].show()
        except Exception:
            if not self.disposed:
                self['art'].hide()
        finally:
            self.remove_art_file()
            self.logo_busy = False
            self.fetch_next_art()

    def art_failed(self, failure, url):
        self.logo_failed.add(url)
        self.remove_art_file()
        self.logo_busy = False
        self.fetch_next_art()


def channel_category(channel):
    """Use explicit playlist group names; no provider API or guessed accounts."""
    group = channel.get('group', '').casefold()
    if any(word in group for word in ('serial', 'series', 'sezon', 'season')):
        return 'series'
    if any(word in group for word in ('film', 'movie', 'vod', 'kino')):
        return 'movies'
    return 'live'


class IPTVPlaylistSources(Screen):
    skin = '''<screen name="IPTVPlaylistSources" position="center,center" size="1100,620" flags="wfNoBorder" backgroundColor="#00101010" title="Playlisty">
      <eLabel position="35,25" size="1030,55" text="Twoje playlisty" font="Regular;38" foregroundColor="#00FFFFFF" backgroundColor="#00101010" />
      <widget name="sources" position="35,110" size="1030,340" font="Regular;25" itemHeight="55" foregroundColor="#00FFFFFF" backgroundColor="#00262626" foregroundColorSelected="#00FFFFFF" backgroundColorSelected="#00E50914" scrollbarMode="showOnDemand" />
      <widget name="status" position="35,470" size="1030,75" font="Regular;23" foregroundColor="#00BBBBBB" backgroundColor="#00101010" />
      <eLabel position="35,565" size="1030,35" text="OK: wybierz    EXIT: wróć" font="Regular;23" foregroundColor="#00FFFFFF" backgroundColor="#00101010" />
    </screen>'''

    def __init__(self, session):
        self.skin = fit_skin(type(self).skin)
        Screen.__init__(self, session)
        self.busy = False
        self.disposed = False
        choices = [('Prześlij M3U z telefonu', 'upload', None),
                   ('Wybierz plik z dekodera / USB', 'file', None),
                   ('Dodaj adres URL playlisty', 'url', None)]
        choices += [(name, 'saved', path) for name, path in saved_playlists()]
        self['sources'] = MenuList(choices)
        self['status'] = Label('Wybierz sposób dodania lub jedną z zapisanych playlist.')
        self['actions'] = ActionMap(['OkCancelActions'], {'ok': self.choose, 'cancel': self.close}, -1)
        self.onClose.append(self.cleanup)

    def cleanup(self):
        self.disposed = True

    def choose(self):
        if self.busy:
            return
        selected = self['sources'].getCurrent()
        if not selected:
            return
        if selected[1] == 'upload':
            self.session.openWithCallback(self.selected, IPTVPlaylistUpload)
        elif selected[1] == 'file':
            self.session.openWithCallback(self.file_selected, IPTVPlaylistFile)
        elif selected[1] == 'url':
            self.session.openWithCallback(self.url_selected, VirtualKeyBoard,
                                          title='Adres URL playlisty M3U', text='https://')
        else:
            self.close(selected[2])

    def selected(self, path):
        if path and not self.disposed:
            self.close(path)

    def url_selected(self, value):
        from urllib.parse import urlsplit
        if value is None:
            return
        value = value.strip()
        try:
            valid = urlsplit(value).scheme.lower() in ('http', 'https') and bool(urlsplit(value).netloc)
        except ValueError:
            valid = False
        if valid:
            self.close(value)
        else:
            self['status'].setText('Wpisz pełny adres HTTP lub HTTPS playlisty M3U.')

    def file_selected(self, path):
        if not path or self.disposed:
            return
        self.busy = True
        self['status'].setText('Sprawdzanie i zapisywanie playlisty…')
        deferToThread(import_local_playlist, path).addCallbacks(self.imported, self.import_failed)

    def imported(self, result):
        self.busy = False
        if not self.disposed:
            self.close(result[0])

    def import_failed(self, failure):
        self.busy = False
        if not self.disposed:
            self['status'].setText('Nie udało się dodać pliku. Wybierz listę M3U do 8 MiB zawierającą adresy kanałów.')


class IPTVPlaylistFile(Screen):
    skin = '''<screen name="IPTVPlaylistFile" position="center,center" size="1100,620" flags="wfNoBorder" backgroundColor="#00101010" title="Wybierz plik M3U">
      <eLabel position="35,25" size="1030,55" text="Wybierz plik M3U" font="Regular;38" foregroundColor="#00FFFFFF" backgroundColor="#00101010" />
      <widget name="files" position="35,110" size="1030,390" font="Regular;25" itemHeight="50" foregroundColor="#00FFFFFF" backgroundColor="#00262626" foregroundColorSelected="#00FFFFFF" backgroundColorSelected="#00E50914" scrollbarMode="showOnDemand" />
      <eLabel position="35,530" size="1030,65" text="OK: otwórz katalog / wybierz plik    Niebieski: /etc/enigma2/    EXIT: wróć" font="Regular;23" foregroundColor="#00BBBBBB" backgroundColor="#00101010" />
    </screen>'''

    def __init__(self, session):
        from Components.FileList import FileList
        self.skin = fit_skin(type(self).skin)
        Screen.__init__(self, session)
        self['files'] = FileList('/media/', matchingPattern=r'(?i)^.*\.(m3u|m3u8)$', useServiceRef=False)
        self['actions'] = ActionMap(['OkCancelActions', 'ColorActions'],
                                   {'ok': self.choose, 'cancel': self.close,
                                    'blue': lambda: self['files'].changeDir('/etc/enigma2/')}, -1)

    def choose(self):
        import os
        files = self['files']
        if files.canDescent():
            files.descent()
        else:
            name = files.getFilename()
            if name and name.lower().endswith(('.m3u', '.m3u8')):
                self.close(os.path.join(files.getCurrentDirectory() or '/', name))


class IPTVPlaylistUpload(Screen):
    skin = '''<screen name="IPTVPlaylistUpload" position="center,center" size="1100,620" flags="wfNoBorder" backgroundColor="#00101010" title="Prześlij playlistę">
      <eLabel position="35,25" size="1030,55" text="Prześlij playlistę z telefonu" font="Regular;36" foregroundColor="#00FFFFFF" backgroundColor="#00101010" />
      <eLabel position="35,110" size="1030,65" text="1. Połącz telefon z tą samą siecią Wi-Fi.\n2. Otwórz poniższy adres w przeglądarce telefonu:" font="Regular;25" foregroundColor="#00BBBBBB" backgroundColor="#00101010" />
      <widget name="address" position="35,200" size="1030,60" font="Regular;38" foregroundColor="#00FFFFFF" backgroundColor="#00101010" />
      <widget name="code" position="35,285" size="1030,55" font="Regular;36" foregroundColor="#00E50914" backgroundColor="#00101010" />
      <eLabel position="35,370" size="1030,75" text="3. Wpisz kod i wybierz plik M3U / M3U8 (do 8 MiB).\n4. Po przesłaniu naciśnij zielony przycisk pilota." font="Regular;25" foregroundColor="#00BBBBBB" backgroundColor="#00101010" />
      <widget name="status" position="35,470" size="1030,70" font="Regular;23" foregroundColor="#00FFFFFF" backgroundColor="#00101010" />
      <eLabel position="35,565" size="1030,35" text="Zielony: użyj przesłanej playlisty    EXIT: zakończ przesyłanie" font="Regular;23" foregroundColor="#00BBBBBB" backgroundColor="#00101010" />
    </screen>'''

    def __init__(self, session):
        from enigma import eTimer
        self.skin = fit_skin(type(self).skin)
        Screen.__init__(self, session)
        self.receiver = PlaylistUpload()
        self.path = None
        self.disposed = False
        self['address'] = Label('Uruchamianie…')
        self['code'] = Label('Kod: %s' % self.receiver.code)
        self['status'] = Label('Przesyłanie działa tylko przy otwartym ekranie.')
        self['actions'] = ActionMap(['OkCancelActions', 'ColorActions'],
                                   {'cancel': self.close, 'green': self.use_file}, -1)
        self.timer = eTimer()
        self.timer.callback.append(self.poll)
        self.onFirstExecBegin.append(self.start)
        self.onClose.append(self.cleanup)

    def start(self):
        try:
            self.receiver.start()
            from Components.Network import iNetwork
            addresses = []
            for adapter in iNetwork.getConfiguredAdapters():
                ip = iNetwork.getAdapterAttribute(adapter, 'ip')
                if ip and len(ip) == 4 and ip[0] not in (0, 127):
                    addresses.append('.'.join(str(part) for part in ip))
            self['address'].setText('http://%s:%d' % (addresses[0], self.receiver.port)
                                    if addresses else 'http://ADRES_IP_DEKODERA:%d' % self.receiver.port)
            self.timer.start(500, False)
        except Exception:
            self.receiver.stop()
            self['address'].setText('Nie można uruchomić przesyłania.')
            self['status'].setText('Port 8099 może być zajęty. Wróć i wybierz plik z dekodera / USB.')

    def poll(self):
        from queue import Empty
        while not self.disposed:
            try:
                path, count = self.receiver.events.get_nowait()
            except Empty:
                break
            self.path = path
            self['status'].setText('Gotowe: %d pozycji. Zielony: użyj tej playlisty.' % count)

    def use_file(self):
        self.poll()
        if self.path:
            self.close(self.path)
        else:
            self['status'].setText('Najpierw prześlij plik z telefonu.')

    def cleanup(self):
        self.disposed = True
        self.timer.stop()
        self.receiver.stop()


class IPTVSettings(Screen, ConfigListScreen):
    skin = '''<screen name="IPTVSettings" position="center,center" size="1100,620" flags="wfNoBorder" backgroundColor="#00101010" title="Ustawienia">
      <eLabel position="35,25" size="1030,55" text="Ustawienia" font="Regular;40" foregroundColor="#00FFFFFF" backgroundColor="#00101010" />
      <eLabel position="35,95" size="1030,40" text="TWOJA TELEWIZJA" font="Regular;21" foregroundColor="#00BBBBBB" backgroundColor="#00101010" />
      <widget name="config" position="35,145" size="1030,210" itemHeight="65" font="Regular;26" foregroundColor="#00FFFFFF" backgroundColor="#00262626" foregroundColorSelected="#00FFFFFF" backgroundColorSelected="#00E50914" scrollbarMode="showOnDemand" />
      <eLabel position="35,360" size="1030,105" text="Wpisz adres listy M3U lub ścieżkę pliku.
Wolny internet: buforowanie GStreamer i dłuższe oczekiwanie na listę." font="Regular;24" foregroundColor="#00BBBBBB" backgroundColor="#00101010" />
      <widget name="help" position="35,515" size="1030,75" font="Regular;23" foregroundColor="#00E50914" backgroundColor="#00101010" />
    </screen>'''

    def __init__(self, session):
        self.skin = fit_skin(type(self).skin)
        Screen.__init__(self, session)
        ConfigListScreen.__init__(self, [getConfigListEntry('Lista kanałów', settings.source),
                                      getConfigListEntry('Odtwarzanie', settings.player),
                                      getConfigListEntry('Wolny internet (GStreamer)', settings.slowinternet)], session=session)
        self['help'] = Label('Żółty: dodaj / wybierz playlistę\nZielony: zapisz   Czerwony: anuluj')
        self['actions'] = ActionMap(['SetupActions', 'ColorActions'],
                                   {'save': self.save, 'green': self.save,
                                    'cancel': self.cancel, 'red': self.cancel, 'yellow': self.playlists}, -2)

    def playlists(self):
        self.session.openWithCallback(self.playlist_selected, IPTVPlaylistSources)

    def playlist_selected(self, source):
        if source:
            settings.source.value = source
            self['config'].invalidateCurrent()

    def save(self):
        settings.save()
        configfile.save()
        self.close(True)

    def cancel(self):
        settings.cancel()
        self.close(False)


class IPTVGroups(Screen):
    skin = '''<screen name="IPTVGroups" position="center,center" size="760,580" flags="wfNoBorder" backgroundColor="#00101010" title="Grupy">
      <eLabel position="30,25" size="700,60" text="Grupy kanałów" font="Regular;38" foregroundColor="#00FFFFFF" backgroundColor="#00101010" />
      <widget name="groups" font="Regular;27" itemHeight="60" position="30,110" size="700,360" foregroundColor="#00FFFFFF" backgroundColor="#00262626" foregroundColorSelected="#00FFFFFF" backgroundColorSelected="#00E50914" scrollbarMode="showOnDemand" />
      <eLabel position="30,505" size="700,45" text="OK  Wybierz     EXIT  Wróć" font="Regular;24" foregroundColor="#00E50914" backgroundColor="#00101010" />
    </screen>'''

    def __init__(self, session, choices):
        self.skin = fit_skin(type(self).skin)
        Screen.__init__(self, session)
        self['groups'] = MenuList(choices)
        self['actions'] = ActionMap(['OkCancelActions'],
                                   {'ok': self.choose, 'cancel': self.close}, -1)

    def choose(self):
        self.close(self['groups'].getCurrent())


class IPTVBrowser(Screen):
    skin = '''<screen name="IPTVBrowser" position="center,center" size="1100,620" flags="wfNoBorder" backgroundColor="#00101010" title="IPTV PL">
      <eLabel position="35,25" size="700,55" text="Telewizja" font="Regular;42" foregroundColor="#00FFFFFF" backgroundColor="#00101010" />
      <eLabel position="840,35" size="225,40" text="IPTV PL" halign="right" font="Regular;24" foregroundColor="#00E50914" backgroundColor="#00101010" />
      <widget name="status" position="35,90" size="1030,40" font="Regular;23" foregroundColor="#00BBBBBB" backgroundColor="#00101010" />
      <widget name="channels" font="Regular;27" itemHeight="60" position="35,145" size="650,360" foregroundColor="#00FFFFFF" backgroundColor="#00262626" foregroundColorSelected="#00FFFFFF" backgroundColorSelected="#00E50914" scrollbarMode="showOnDemand" />
      <eLabel position="715,145" size="350,360" backgroundColor="#00262626" />
      <eLabel position="740,170" size="300,35" text="WYBRANY KANAŁ" font="Regular;19" foregroundColor="#00BBBBBB" backgroundColor="#00262626" />
      <widget name="selection" position="740,225" size="300,140" font="Regular;29" foregroundColor="#00FFFFFF" backgroundColor="#00262626" />
      <widget name="detail" position="740,380" size="300,100" font="Regular;23" foregroundColor="#00E50914" backgroundColor="#00262626" />
      <widget name="help" position="35,535" size="1030,65" font="Regular;22" foregroundColor="#00BBBBBB" backgroundColor="#00101010" />
    </screen>'''

    def __init__(self, session, category='all'):
        self.skin = fit_skin(type(self).skin)
        Screen.__init__(self, session)
        self.category = category
        self.channels = []
        self.group = None
        self.loading = False
        self.player_open = False
        self.disposed = False
        self['status'] = Label('')
        self['channels'] = MenuList([])
        self['selection'] = Label('Twoje kanały')
        self['detail'] = Label('Dodaj listę w ustawieniach')
        self['channels'].onSelectionChanged.append(self.selection_changed)
        self['help'] = Label('OK: odtwórz   Zielony: odśwież   Żółty: grupy\nNiebieski/Menu: ustawienia   EXIT: wyjdź')
        self['actions'] = ActionMap(['OkCancelActions', 'ColorActions', 'MenuActions'],
                                   {'ok': self.play, 'cancel': self.close, 'red': self.close,
                                    'green': self.reload, 'yellow': self.groups,
                                    'blue': self.setup, 'menu': self.setup}, -1)
        self.onClose.append(self.cleanup)
        self.onFirstExecBegin.append(self.reload)

    def cleanup(self):
        self.disposed = True

    def reload(self):
        if self.loading:
            return
        self.loading = True
        self['status'].setText('Odświeżanie kanałów…')
        self['detail'].setText('Pobieranie listy…')
        timeout = 60 if settings.slowinternet.value else 20
        deferToThread(load_playlist, settings.source.value, timeout=timeout).addCallbacks(self.loaded, self.failed)

    def loaded(self, channels):
        self.loading = False
        if self.disposed:
            return
        self.channels = [c for c in channels if self.category == 'all' or channel_category(c) == self.category]
        self.group = None
        self.render()

    def failed(self, failure):
        self.loading = False
        if self.disposed:
            return
        self.render()
        self['status'].setText('Nie udało się odświeżyć • Zielony: spróbuj ponownie')
        # Do not expose playlist URLs, which may contain passwords, in errors.
        self['selection'].setText('Sprawdź źródło')
        self['detail'].setText('Niebieski: ustaw listę M3U\nZielony: spróbuj ponownie')

    def render(self):
        visible = [c for c in self.channels if self.group is None or c['group'] == self.group]
        self['channels'].setList([(c['name'], c) for c in visible])
        self['status'].setText('%s • %d kanałów' % (self.group or {'all': 'Wszystkie kanały', 'live': 'Telewizja na żywo', 'movies': 'Filmy', 'series': 'Seriale'}.get(self.category, 'Kanały'), len(visible)))
        self.selection_changed()

    def selection_changed(self):
        current = self['channels'].getCurrent()
        if current:
            self['selection'].setText(current[1]['name'])
            self['detail'].setText('%s\nOK  Oglądaj teraz' % current[1]['group'])
        else:
            self['selection'].setText('Brak kanałów')
            self['detail'].setText('Brak pozycji w tej kategorii.\nNiebieski: ustawienia źródła' if not self.channels else 'Żółty: wybierz inną grupę')

    def groups(self):
        choices = [('Wszystkie', None)] + [(g, g) for g in sorted(set(c['group'] for c in self.channels))]
        self.session.openWithCallback(self.selected_group, IPTVGroups, choices)

    def selected_group(self, choice):
        if choice:
            self.group = choice[1]
            self.render()

    def setup(self):
        if not self.loading:
            self.session.openWithCallback(self.settings_closed, IPTVSettings)

    def settings_closed(self, saved):
        if saved:
            self.reload()

    def play(self):
        if self.player_open or self.disposed:
            return
        current = self['channels'].getCurrent()
        if current:
            channel = current[1]
            # Slow mode uses native GStreamer buffering, independent of ServiceApp.
            service_type = 4097 if settings.slowinternet.value else int(settings.player.value)
            reference = eServiceReference(service_type, 0, channel['url'])
            if settings.slowinternet.value:
                # eServiceMP3 BUFFERING_ENABLED; no progressive disk download.
                reference.setData(7, 1)
            reference.setName(channel['name'])
            self.player_open = True
            try:
                self.session.openWithCallback(self.player_closed, MoviePlayer, reference)
            except Exception:
                self.player_open = False
                self.session.open(MessageBox, 'Nie udało się otworzyć odtwarzacza. Sprawdź wybrany odtwarzacz w ustawieniach.', MessageBox.TYPE_ERROR)

    def player_closed(self, *args):
        self.player_open = False
        if not self.disposed:
            self.selection_changed()


def main(session, **kwargs):
    session.open(IPTVHome)


def Plugins(**kwargs):
    return [PluginDescriptor(name='IPTV PL', description='Odtwarzacz list IPTV M3U',
                             where=PluginDescriptor.WHERE_PLUGINMENU, fnc=main)]


