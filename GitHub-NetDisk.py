#!/usr/bin/env python3
# coding:utf-8
import os
import sys

toolsPath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tools')
pathEntries = [entry for entry in os.environ.get('PATH', '').split(os.pathsep)
               if entry]
if toolsPath not in pathEntries:
    os.environ['PATH'] = os.pathsep.join([*pathEntries, toolsPath])

from app.common.console_logger import configureLogger, installConsoleLogCapture
from app.common.setting import APP_ID, APP_NAME, LOG_FILE

from PyQt5.QtCore import QSharedMemory


def hasRunningInstance(key: str) -> bool:
    memory = QSharedMemory(key)
    try:
        return memory.attach()
    finally:
        if memory.isAttached():
            memory.detach()


consoleLogCapture = (
    None
    if hasRunningInstance(APP_ID)
    else installConsoleLogCapture(LOG_FILE)
)
logger = configureLogger(consoleLogCapture, LOG_FILE)

from PyQt5.QtCore import QLibraryInfo, QLocale, Qt, QTimer, QTranslator
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication
from qfluentwidgets import FluentTranslator, setThemeColor
from qframelesswindow.utils import getSystemAccentColor
if sys.platform == 'win32':
    from qframelesswindow.utils.win32_utils import isWin7

from app.common import resource, exception_hook
from app.common.application import (
    SingletonApplication,
    configureApplicationLanguageDialogs,
    getForcedUsernameArgument,
    hasForceGuideWindowArgument,
)
from app.common.config import cfg
from app.common.translator import JsonTranslator, translate
from app.components.native_menu import (
    MacApplicationMenuTranslator,
    prepareMacApplicationName,
    setMacDockIcon,
)
from app.view.main_window import MainWindow
from app.view.guide_window import GuideWindow

# enable dpi scale
if cfg.get(cfg.dpiScale) != "Auto":
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
    os.environ["QT_SCALE_FACTOR"] = str(cfg.get(cfg.dpiScale))
else:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)

# create application
startup_translator = JsonTranslator(cfg.get(cfg.language), ':/app/lang')
startup_app_name = startup_translator.tr('App.Name') or APP_NAME
prepareMacApplicationName(startup_app_name)
QApplication.setApplicationName(startup_app_name)
QApplication.setApplicationDisplayName(startup_app_name)
configureApplicationLanguageDialogs(cfg.get(cfg.language).name())
try:
    app = SingletonApplication(sys.argv, APP_ID)
    app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)
    localized_app_name = translate('App.Name')
    prepareMacApplicationName(localized_app_name)
    app.setApplicationName(localized_app_name)
    app.setApplicationDisplayName(localized_app_name)

    if sys.platform == 'darwin':
        from AppKit import NSApplication
        NSApplication.sharedApplication()
        setMacDockIcon()

    # set theme color
    if sys.platform == 'win32' and isWin7():
        setThemeColor('#0078D7')
    else:
        setThemeColor(getSystemAccentColor() if getSystemAccentColor().isValid() else '#0078D7')

    # internationalization
    locale = cfg.get(cfg.language)
    qt_locale = (
        QLocale('zh_TW')
        if locale.name().lower() in ('zh_hk', 'zh_mo')
        else locale
    )
    qt_base_translator = QTranslator(app)
    qt_base_translator.load(
        qt_locale,
        'qtbase',
        '_',
        QLibraryInfo.location(QLibraryInfo.TranslationsPath),
    )
    app.installTranslator(qt_base_translator)
    translator = FluentTranslator(locale)
    app.installTranslator(translator)

    if sys.platform == 'darwin':
        mac_menu_translator = MacApplicationMenuTranslator(app)
        app.installTranslator(mac_menu_translator)

    # create main window
    startup_message = ' '.join(sys.argv[1:]) if len(sys.argv) > 1 else ''
    has_app_link = 'github-netdisk://' in startup_message.lower()
    force_enter_guidewindow = hasForceGuideWindowArgument(sys.argv)
    forced_username = getForcedUsernameArgument(sys.argv)
    if force_enter_guidewindow or (cfg.get(cfg.firstUse) and not has_app_link):
        w = GuideWindow(forced_username=forced_username)
    else:
        w = MainWindow(forced_username=forced_username)
        app.aboutToQuit.connect(w.onExit)
    w.show()
    if isinstance(w, MainWindow) and startup_message:
        QTimer.singleShot(0, lambda: w.onAppMessage(startup_message))

    app.exec()
finally:
    logger.remove()
    if consoleLogCapture:
        consoleLogCapture.close()
