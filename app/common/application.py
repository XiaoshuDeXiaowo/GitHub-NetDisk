# coding:utf-8
import ctypes
import os
import sys
from typing import List
from loguru import logger

from PyQt5.QtCore import QEvent, QIODevice, QSharedMemory, pyqtSignal
from PyQt5.QtNetwork import QLocalServer, QLocalSocket
from PyQt5.QtWidgets import QApplication

from .config import cfg

from .signal_bus import signalBus
from .translator import JsonTranslator, JsonTranslatorManager, translate

FORCE_GUIDE_WINDOW_ARGUMENT = '--force-enter-guidewindow'
FORCE_USERNAME_ARGUMENT = '--force-username='


def hasForceGuideWindowArgument(argv: List[str]) -> bool:
    """Return whether argv requests the setup guide regardless of first-use state.

    Command-line switches are intentionally matched case-insensitively while
    still requiring an exact argument, so unrelated values are not consumed.
    """
    return any(
        str(argument).casefold() == FORCE_GUIDE_WINDOW_ARGUMENT.casefold()
        for argument in argv[1:]
    )


def getForcedUsernameArgument(argv: List[str]):
    """Return the username supplied by ``--force-username=<name>``."""
    prefix = FORCE_USERNAME_ARGUMENT.casefold()
    for argument in argv[1:]:
        value = str(argument)
        key, separator, username = value.partition('=')
        if separator and f'{key}='.casefold() == prefix:
            username = username.strip()
            return username or None
    return None


def nativeDialogLanguageIdentifiers(locale_name: str):
    """Return Apple language identifiers for the application's locale."""
    locale = str(locale_name or '').lower().replace('-', '_')
    if locale.startswith(('zh_cn', 'zh_sg')):
        return ['zh-Hans', 'en']
    if locale.startswith(('zh_hk', 'zh_tw', 'zh_mo')):
        return ['zh-Hant', 'en']
    return ['en']


def nativeDialogLocale(locale_name: str):
    """Return platform locale names for native dialog APIs."""
    locale = str(locale_name or '').lower().replace('-', '_')
    if locale.startswith(('zh_cn', 'zh_sg')):
        return 'zh-CN', 'zh_CN'
    if locale.startswith(('zh_hk', 'zh_tw', 'zh_mo')):
        return 'zh-HK', 'zh_HK'
    return 'en-US', 'en_US'


def configureApplicationLanguageDialogs(locale_name=''):
    """Keep native file dialogs and request the application's UI language.

    QFileDialog remains native.  On macOS, NSOpenPanel/NSSavePanel read the
    process AppleLanguages preference when they are created.  A volatile
    argument domain changes only this process and does not modify the user's
    global system language preference.
    """
    if sys.platform != 'darwin':
        if sys.platform == 'win32':
            try:
                windows_locale, _ = nativeDialogLocale(locale_name)
                kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
                set_preferred = kernel32.SetThreadPreferredUILanguages
                set_preferred.argtypes = [
                    ctypes.c_uint32, ctypes.c_wchar_p,
                    ctypes.POINTER(ctypes.c_uint32),
                ]
                set_preferred.restype = ctypes.c_int
                # MUI_LANGUAGE_NAME: use names such as zh-CN/en-US.
                set_preferred(0x8, windows_locale, None)
            except Exception as error:
                logger.debug('Unable to set Windows native dialog language: {}', error)
        else:
            # GTK/portal-backed native dialogs use gettext's LANGUAGE and
            # LC_MESSAGES variables.  Set only the message language; numeric
            # and date formatting remain controlled by the system locale.
            _, posix_locale = nativeDialogLocale(locale_name)
            os.environ['LANGUAGE'] = f'{posix_locale}:en_US:en'
            os.environ['LC_MESSAGES'] = posix_locale
        return
    try:
        from Foundation import NSUserDefaults
        defaults = NSUserDefaults.standardUserDefaults()
        defaults.setVolatileDomain_forName_(
            {'AppleLanguages': nativeDialogLanguageIdentifiers(locale_name)},
            'NSArgumentDomain',
        )
    except Exception as error:
        logger.debug('Unable to set native dialog language: {}', error)


class SingletonApplication(QApplication):
    """ Singleton application """

    messageSig = pyqtSignal(object)

    @staticmethod
    def hasRunningInstance(key: str) -> bool:
        memory = QSharedMemory(key)
        try:
            return memory.attach()
        finally:
            if memory.isAttached():
                memory.detach()

    def __init__(self, argv: List[str], key: str):
        super().__init__(argv)

        # initialize json translator
        locale = cfg.get(cfg.language)
        jsonTranslator = JsonTranslator(locale, ':/app/lang')
        JsonTranslatorManager(jsonTranslator)

        self.key = key
        self.timeout = 1000
        self.server = QLocalServer(self)

        # cleanup (only needed for unix)
        QSharedMemory(key).attach()
        self.memory = QSharedMemory(self)
        self.memory.setKey(key)

        if self.memory.attach():
            self.isRunning = True
            logger.info(translate('Log.App.AppInstance.Detected'))

            msg = " ".join(argv[1:]) if len(argv) > 1 else 'show'
            if self.sendMessage(msg):
                logger.info(translate('Log.App.AppMessage.Sent', msg))
                sys.exit()

            logger.warning(translate(
                'Log.Event.Failed',
                (translate('Log.Action.Application'), 'stale singleton lock'),
            ))
            self.memory.detach()
            self.isRunning = False

        self.isRunning = False
        if not self.memory.create(1):
            logger.error(translate(
                'Log.Event.Failed',
                (translate('Log.Action.Application'), self.memory.errorString()),
            ))
            raise RuntimeError(self.memory.errorString())

        self.server.newConnection.connect(self.__onNewConnection)
        QLocalServer.removeServer(key)
        self.server.listen(key)

    def __onNewConnection(self):
        socket = self.server.nextPendingConnection()
        if socket.waitForReadyRead(self.timeout):
            message = socket.readAll().data().decode('utf-8')
            logger.debug(translate(
                'Log.Event.Received',
                (translate('Log.Action.Application'), message),
            ))
            signalBus.appMessageSig.emit(message)
            socket.disconnectFromServer()

    def sendMessage(self, message: str):
        """ send message to another application """
        if not self.isRunning:
            return

        # connect to another application
        socket = QLocalSocket(self)
        socket.connectToServer(self.key, QIODevice.WriteOnly)
        if not socket.waitForConnected(self.timeout):
            logger.error(translate(
                'Log.Event.Failed',
                (translate('Log.Action.Application'), socket.errorString()),
            ))
            return False

        # send message
        socket.write(message.encode("utf-8"))
        if not socket.waitForBytesWritten(self.timeout):
            logger.error(translate(
                'Log.Event.Failed',
                (translate('Log.Action.Application'), socket.errorString()),
            ))
            return False

        socket.disconnectFromServer()
        return True

    def event(self, event):
        """Forward macOS URL/file-open events to the active main window."""
        if event.type() == QEvent.FileOpen:
            value = event.url().toString() if not event.url().isEmpty() else event.file()
            if value:
                signalBus.appMessageSig.emit(value)
                return True
        return super().event(event)
