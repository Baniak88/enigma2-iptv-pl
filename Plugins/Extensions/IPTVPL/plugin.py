# -*- coding: utf-8 -*-
from enigma import eServiceReference
from Plugins.Plugin import PluginDescriptor
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Screens.InfoBar import MoviePlayer
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.ConfigList import ConfigListScreen
from Components.config import (config, configfile, ConfigSubsection, ConfigText,
                               ConfigSelection, ConfigYesNo, getConfigListEntry)
from twisted.internet.threads import deferToThread
from .playlist import load_playlist

config.plugins.iptvpl = ConfigSubsection()
settings = config.plugins.iptvpl
settings.source = ConfigText(default='/etc/enigma2/iptv.m3u', fixed_size=False)
settings.player = ConfigSelection(default='4097', choices=[('4097', 'GStreamer (4097)'),
                                  ('5001', 'ServiceApp / exteplayer3 (5001)'),
                                  ('5002', 'ServiceApp / gstplayer (5002)')])

settings.slowinternet = ConfigYesNo(default=False)


class IPTVSettings(Screen, ConfigListScreen):
    skin = '''<screen name="IPTVSettings" position="center,center" size="1100,620" flags="wfNoBorder" backgroundColor="#00F2F2F7" title="Ustawienia">
      <eLabel position="35,25" size="1030,55" text="Ustawienia" font="Regular;40" foregroundColor="#001C1C1E" backgroundColor="#00F2F2F7" />
      <eLabel position="35,95" size="1030,40" text="TWOJA TELEWIZJA" font="Regular;21" foregroundColor="#00636366" backgroundColor="#00F2F2F7" />
      <widget name="config" position="35,145" size="1030,210" itemHeight="65" font="Regular;26" foregroundColor="#001C1C1E" backgroundColor="#00FFFFFF" foregroundColorSelected="#00FFFFFF" backgroundColorSelected="#00007AFF" scrollbarMode="showOnDemand" />
      <eLabel position="35,360" size="1030,105" text="Wpisz adres listy M3U lub ścieżkę pliku.
Wolny internet: buforowanie GStreamer i dłuższe oczekiwanie na listę." font="Regular;24" foregroundColor="#00636366" backgroundColor="#00F2F2F7" />
      <widget name="help" position="35,515" size="1030,75" font="Regular;23" foregroundColor="#00007AFF" backgroundColor="#00F2F2F7" />
    </screen>'''

    def __init__(self, session):
        Screen.__init__(self, session)
        ConfigListScreen.__init__(self, [getConfigListEntry('Lista kanałów', settings.source),
                                      getConfigListEntry('Odtwarzanie', settings.player),
                                      getConfigListEntry('Wolny internet (GStreamer)', settings.slowinternet)], session=session)
        self['help'] = Label('OK: edycja / klawiatura ekranowa   Zielony: zapisz   Czerwony: anuluj')
        self['actions'] = ActionMap(['SetupActions', 'ColorActions'],
                                   {'save': self.save, 'green': self.save,
                                    'cancel': self.cancel, 'red': self.cancel}, -2)

    def save(self):
        settings.save()
        configfile.save()
        self.close(True)

    def cancel(self):
        settings.cancel()
        self.close(False)


class IPTVGroups(Screen):
    skin = '''<screen name="IPTVGroups" position="center,center" size="760,580" flags="wfNoBorder" backgroundColor="#00F2F2F7" title="Grupy">
      <eLabel position="30,25" size="700,60" text="Grupy kanałów" font="Regular;38" foregroundColor="#001C1C1E" backgroundColor="#00F2F2F7" />
      <widget name="groups" font="Regular;27" itemHeight="60" position="30,110" size="700,360" foregroundColor="#001C1C1E" backgroundColor="#00FFFFFF" foregroundColorSelected="#00FFFFFF" backgroundColorSelected="#00007AFF" scrollbarMode="showOnDemand" />
      <eLabel position="30,505" size="700,45" text="OK  Wybierz     EXIT  Wróć" font="Regular;24" foregroundColor="#00007AFF" backgroundColor="#00F2F2F7" />
    </screen>'''

    def __init__(self, session, choices):
        Screen.__init__(self, session)
        self['groups'] = MenuList(choices)
        self['actions'] = ActionMap(['OkCancelActions'],
                                   {'ok': self.choose, 'cancel': self.close}, -1)

    def choose(self):
        self.close(self['groups'].getCurrent())


class IPTVBrowser(Screen):
    skin = '''<screen name="IPTVBrowser" position="center,center" size="1100,620" flags="wfNoBorder" backgroundColor="#00F2F2F7" title="IPTV PL">
      <eLabel position="35,25" size="700,55" text="Telewizja" font="Regular;42" foregroundColor="#001C1C1E" backgroundColor="#00F2F2F7" />
      <eLabel position="840,35" size="225,40" text="IPTV PL" halign="right" font="Regular;24" foregroundColor="#00007AFF" backgroundColor="#00F2F2F7" />
      <widget name="status" position="35,90" size="1030,40" font="Regular;23" foregroundColor="#00636366" backgroundColor="#00F2F2F7" />
      <widget name="channels" font="Regular;27" itemHeight="60" position="35,145" size="650,360" foregroundColor="#001C1C1E" backgroundColor="#00FFFFFF" foregroundColorSelected="#00FFFFFF" backgroundColorSelected="#00007AFF" scrollbarMode="showOnDemand" />
      <eLabel position="715,145" size="350,360" backgroundColor="#00FFFFFF" />
      <eLabel position="740,170" size="300,35" text="WYBRANY KANAŁ" font="Regular;19" foregroundColor="#00636366" backgroundColor="#00FFFFFF" />
      <widget name="selection" position="740,225" size="300,140" font="Regular;29" foregroundColor="#001C1C1E" backgroundColor="#00FFFFFF" />
      <widget name="detail" position="740,380" size="300,100" font="Regular;23" foregroundColor="#00007AFF" backgroundColor="#00FFFFFF" />
      <widget name="help" position="35,535" size="1030,65" font="Regular;22" foregroundColor="#00636366" backgroundColor="#00F2F2F7" />
    </screen>'''

    def __init__(self, session):
        Screen.__init__(self, session)
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
        self.channels = channels
        self.group = None
        self.render()

    def failed(self, failure):
        self.loading = False
        if self.disposed:
            return
        self.render()
        self['status'].setText('Nie udało się odświeżyć • Zielony: spróbuj ponownie')
        # Do not expose playlist URLs, which may contain passwords, in errors.
        self.session.open(MessageBox, 'Nie udało się wczytać listy. Sprawdź adres lub plik, połączenie i format M3U (maks. 8 MiB).', MessageBox.TYPE_ERROR)

    def render(self):
        visible = [c for c in self.channels if self.group is None or c['group'] == self.group]
        self['channels'].setList([(c['name'], c) for c in visible])
        self['status'].setText('%s • %d kanałów' % (self.group or 'Wszystkie kanały', len(visible)))
        self.selection_changed()

    def selection_changed(self):
        current = self['channels'].getCurrent()
        if current:
            self['selection'].setText(current[1]['name'])
            self['detail'].setText('%s\nOK  Oglądaj teraz' % current[1]['group'])
        else:
            self['selection'].setText('Brak kanałów')
            self['detail'].setText('Niebieski: dodaj listę' if not self.channels else 'Żółty: wybierz inną grupę')

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
    session.open(IPTVBrowser)


def Plugins(**kwargs):
    return [PluginDescriptor(name='IPTV PL', description='Odtwarzacz list IPTV M3U',
                             where=PluginDescriptor.WHERE_PLUGINMENU, fnc=main)]
