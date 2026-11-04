# -*- coding: utf-8 -*-
from enigma import eServiceReference
from Plugins.Plugin import PluginDescriptor
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Screens.ChoiceBox import ChoiceBox
from Screens.InfoBar import MoviePlayer
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.ConfigList import ConfigListScreen
from Components.config import (config, configfile, ConfigSubsection, ConfigText,
                               ConfigSelection, getConfigListEntry)
from twisted.internet.threads import deferToThread
from .playlist import load_playlist

config.plugins.iptvpl = ConfigSubsection()
settings = config.plugins.iptvpl
settings.source = ConfigText(default='/etc/enigma2/iptv.m3u', fixed_size=False)
settings.player = ConfigSelection(default='4097', choices=[('4097', 'GStreamer (4097)'),
                                  ('5001', 'ServiceApp / exteplayer3 (5001)'),
                                  ('5002', 'ServiceApp / gstplayer (5002)')])


class IPTVSettings(Screen, ConfigListScreen):
    skin = '''<screen name="IPTVSettings" position="center,center" size="1100,450" title="IPTV PL — ustawienia">
      <widget name="config" position="20,20" size="1060,310" />
      <widget name="help" position="20,350" size="1060,80" font="Regular;23" />
    </screen>'''

    def __init__(self, session):
        Screen.__init__(self, session)
        ConfigListScreen.__init__(self, [getConfigListEntry('Plik M3U lub URL', settings.source),
                                      getConfigListEntry('Odtwarzacz', settings.player)], session=session)
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


class IPTVBrowser(Screen):
    skin = '''<screen name="IPTVBrowser" position="center,center" size="1100,620" title="IPTV PL">
      <widget name="status" position="20,15" size="1060,45" font="Regular;25" />
      <widget name="channels" position="20,70" size="1060,460" scrollbarMode="showOnDemand" />
      <widget name="help" position="20,545" size="1060,60" font="Regular;22" />
    </screen>'''

    def __init__(self, session):
        Screen.__init__(self, session)
        self.channels = []
        self.group = None
        self.loading = False
        self.disposed = False
        self['status'] = Label('')
        self['channels'] = MenuList([])
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
        self['status'].setText('Wczytywanie listy…')
        deferToThread(load_playlist, settings.source.value).addCallbacks(self.loaded, self.failed)

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
        # Do not expose playlist URLs, which may contain passwords, in errors.
        self.session.open(MessageBox, 'Nie udało się wczytać listy. Sprawdź adres lub plik, połączenie i format M3U (maks. 8 MiB).', MessageBox.TYPE_ERROR)

    def render(self):
        visible = [c for c in self.channels if self.group is None or c['group'] == self.group]
        self['channels'].setList([(c['name'], c) for c in visible])
        self['status'].setText('%s — %d kanałów' % (self.group or 'Wszystkie', len(visible)))

    def groups(self):
        choices = [('Wszystkie', None)] + [(g, g) for g in sorted(set(c['group'] for c in self.channels))]
        self.session.openWithCallback(self.selected_group, ChoiceBox, title='Wybierz grupę', list=choices)

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
        current = self['channels'].getCurrent()
        if current:
            channel = current[1]
            reference = eServiceReference(int(settings.player.value), 0, channel['url'])
            reference.setName(channel['name'])
            self.session.open(MoviePlayer, reference)


def main(session, **kwargs):
    session.open(IPTVBrowser)


def Plugins(**kwargs):
    return [PluginDescriptor(name='IPTV PL', description='Odtwarzacz list IPTV M3U',
                             where=PluginDescriptor.WHERE_PLUGINMENU, fnc=main)]
