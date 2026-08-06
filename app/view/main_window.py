# coding: utf-8
import sys
from getpass import getuser
from time import monotonic

from loguru import logger
from PyQt5.QtCore import QSize, Qt, QTimer
from PyQt5.QtGui import QIcon, QColor
from PyQt5.QtWidgets import QApplication
from pyqt5_concurrent.TaskExecutor import TaskExecutor
from qfluentwidgets import (NavigationItemPosition, FluentWindow, SplashScreen,
                            InfoBar, InfoBarPosition, MessageBox)
from qfluentwidgets import FluentIcon as FIF

from .home_interface import HomeInterface
from .browse_interface import BrowseInterface
from .task_interface import TaskInterface
from .account_interface import AccountInterface
from .setting_interface import SettingInterface
from ..components.menu_bar import MenuBar
from ..components.dialog import AddTaskDialog
from ..components.native_menu import MacNativeMenuController
from ..components.system_tray_icon import SystemTrayIcon
from ..service.aria2_download_service import aria2DownloadService
from ..common import resource
from ..common.config import cfg
from ..common.event_logger import (logAction, logChanged, logInitialized,
                                   logReceived, logStarted, logFailed)
from ..service.github_service import getUserName, installGithubRateLimitMonitor
from ..service.auth_service import authService
from ..common.icon import Icon
from ..common.signal_bus import signalBus
from ..common.setting import FEEDBACK_URL, localizedWebsiteUrl
from ..service.transfer_task_service import transferTaskService
from ..service.version_service import versionService
from ..common.translator import translate
from ..common.theme_listener import SystemThemeListener, stopSystemThemeListener
from ..common.utils import openUrl
from ..common.url_scheme import BrowseRepoRequest, NewTaskRequest, parse_app_url


class MainWindow(FluentWindow):

    def __init__(self):
        super().__init__()
        self.tr = translate
        self._isQuitting = False
        self._cleanupDone = False
        self._lastGithubRateLimitInfoAt = 0.0
        self._checkingUpdate = False
        self._updateDownloadInfoBar = None
        self.initWindow()
        logger.info(self.tr('Log.App.Initialize.Start'))

        # create system theme listener
        self.themeListener = SystemThemeListener(self)

        # create sub interface
        self.homeInterface = HomeInterface(self)
        self.browseInterface = BrowseInterface(self)
        self.taskInterface = TaskInterface(self)
        self.accountInterface = AccountInterface(self)
        self.settingInterface = SettingInterface(self)
        self.systemTrayIcon = SystemTrayIcon(self)
        QApplication.instance().systemTrayIcon = self.systemTrayIcon
        logger.info(self.tr('Log.App.SubInterfaces.Create.Success'))

        self.connectSignalToSlot()
        self.refreshGitHubUserName()

        # add items to navigation interface
        self.initMenuBar()
        self.initNavigation()

        # start system theme listener
        self.themeListener.start()
        if not cfg.get(cfg.disableTrayIcon):
            self.systemTrayIcon.show()

        logger.info(self.tr('Log.App.Initialize.Success'))
        logInitialized('Log.Action.Application')
        if cfg.get(cfg.checkUpdateAtStartUp):
            QTimer.singleShot(1200, lambda: self.checkUpdate(True))

    def connectSignalToSlot(self):
        signalBus.appMessageSig.connect(self.onAppMessage)
        signalBus.micaEnableChanged.connect(self.setMicaEffectEnabled)
        signalBus.trayIconDisabledChanged.connect(
            self.setTrayIconDisabled)
        signalBus.browseRepo.connect(self.onBrowseRequested)
        signalBus.showAddTaskDialogSig.connect(self.showAddTaskDialog)
        signalBus.githubRateLimitSig.connect(self.showGithubRateLimitInfo)
        signalBus.checkUpdateSig.connect(lambda: self.checkUpdate(False))
        transferTaskService.taskAdded.connect(self.showTaskInterfaceForNewTask)
        installGithubRateLimitMonitor()
        self.systemTrayIcon.showWindowRequested.connect(self.showWindow)
        self.systemTrayIcon.toggleWindowRequested.connect(self.toggleWindow)
        self.systemTrayIcon.settingsRequested.connect(self.showSettingsFromTray)
        self.systemTrayIcon.quitRequested.connect(self.quitApplication)

        self.stackedWidget.currentChanged.connect(self.onCurrentChanged)

    def initMenuBar(self):
        self.menuBar = MenuBar(self)
        self.menuBar.addTaskAct.triggered.connect(
            lambda: self.showAddTaskDialog(None))
        self.menuBar.homeAct.triggered.connect(
            lambda: self.showInterface(self.homeInterface, 'MenuBar.Home'))
        self.menuBar.browseAct.triggered.connect(
            lambda: self.showInterface(self.browseInterface, 'MenuBar.Browse'))
        self.menuBar.tasksAct.triggered.connect(
            lambda: self.showInterface(self.taskInterface, 'MenuBar.Tasks'))
        self.menuBar.accountAct.triggered.connect(
            lambda: self.showInterface(
                self.accountInterface, 'MainWindow.Account'))
        self.menuBar.settingsAct.triggered.connect(self.showSettingsFromMenu)
        self.menuBar.closeWindowAct.triggered.connect(self.close)
        self.menuBar.quitAct.triggered.connect(self.quitApplication)
        self.menuBar.helpAct.triggered.connect(
            lambda: self.openMenuUrl(
                'MenuBar.OpenHelp',
                localizedWebsiteUrl(cfg.get(cfg.language).name())))
        self.menuBar.feedbackAct.triggered.connect(
            lambda: self.openMenuUrl('MenuBar.Feedback', FEEDBACK_URL))
        self.menuBar.aboutQtAct.triggered.connect(self.showAboutQtFromMenu)
        self.menuBar.aboutAct.triggered.connect(self.showAboutFromMenu)
        self.menuBar.backAct.triggered.connect(self.goBack)
        self.menuBar.fullScreenAct.triggered.connect(
            self.toggleFullScreenFromShortcut)
        if sys.platform == 'darwin':
            # Native AppKit displays Globe-F; keep Qt's standard binding too
            # because macOS native apps continue to accept Control-Command-F.
            self.addAction(self.menuBar.fullScreenAct)
            self.nativeMenuController = MacNativeMenuController(
                self, self.menuBar, show_back=True)
            QTimer.singleShot(0, self.nativeMenuController.install)
        else:
            self.menuBar.hide()
            for action in self.menuBar.shortcutActions():
                self.addAction(action)

    def onBrowseRequested(self, repo):
        logReceived('Log.Action.BrowseRepository', repo or '/')
        self.switchTo(self.browseInterface)

    def showAddTaskDialog(self, request=None):
        self.showWindow()
        dialog = AddTaskDialog(request=request, parent=self)
        if dialog.exec():
            task_request = dialog.request
            logAction('Log.Action.Task', task_request.uri)
            signalBus.newTaskRequestedSig.emit(task_request)

    def showTaskInterfaceForNewTask(self, task=None):
        self.showWindow()
        if self.stackedWidget.currentWidget() is self.taskInterface:
            self.taskInterface.selectPreferredCategory()
        else:
            self.switchTo(self.taskInterface)

    def showGithubRateLimitInfo(self, detail=''):
        now = monotonic()
        if now - self._lastGithubRateLimitInfoAt < 30:
            return
        self._lastGithubRateLimitInfoAt = now
        logAction('Log.Action.InfoBar', detail, level='debug')
        InfoBar.warning(
            self.tr('GitHub.RateLimit.title'),
            self.tr('GitHub.RateLimit.text'),
            duration=8000,
            position=InfoBarPosition.TOP_RIGHT,
            parent=self.window(),
        )

    def checkUpdate(self, silent=True):
        if self._checkingUpdate:
            if not silent:
                InfoBar.info(
                    self.tr('UpdateCheck.Checking.title'),
                    self.tr('UpdateCheck.Checking.text'),
                    duration=2000,
                    position=InfoBarPosition.TOP_RIGHT,
                    parent=self.window(),
                )
            return
        self._checkingUpdate = True
        logStarted('Log.Action.UpdateCheck')
        future = TaskExecutor.run(versionService.hasNewVersion)
        future.result.connect(
            lambda has_update, silent=silent:
            self.onVersionInfoFetched(has_update, silent))
        future.failed.connect(
            lambda error, silent=silent: self._onUpdateCheckFailed(error, silent))

    def onVersionInfoFetched(self, has_update, silent=True):
        self._checkingUpdate = False
        logChanged('Log.Action.UpdateCheck', versionService.lastestVersion)
        if has_update:
            if self.showMessage(
                    self.tr('UpdateCheck.NewVersion.title'),
                    self.tr(
                        'UpdateCheck.DownloadInstaller.text',
                        (versionService.currentVersion,
                         versionService.lastestVersion),
                    )):
                self.downloadAndInstallUpdate()
            return
        if not silent:
            self.showMessage(
                self.tr('UpdateCheck.NoUpdate.title'),
                self.tr('UpdateCheck.NoUpdate.text',
                        (versionService.currentVersion,)),
                showYesButton=False,
            )

    def downloadAndInstallUpdate(self):
        logStarted('Log.Action.UpdateCheck', versionService.lastestVersion)
        self._closeUpdateDownloadInfoBar()
        self._updateDownloadInfoBar = InfoBar.info(
            self.tr('UpdateCheck.Downloading.title'),
            self.tr('UpdateCheck.Downloading.text'),
            isClosable=False,
            duration=-1,
            position=InfoBarPosition.TOP_RIGHT,
            parent=self.window(),
        )
        future = TaskExecutor.run(versionService.downloadInstaller)
        future.result.connect(self._onUpdateInstallerDownloaded)
        future.failed.connect(lambda error: self._onUpdateDownloadFailed(error))

    def _onUpdateInstallerDownloaded(self, installer_path):
        self._closeUpdateDownloadInfoBar()
        logChanged('Log.Action.UpdateCheck', installer_path)
        InfoBar.success(
            self.tr('UpdateCheck.Downloaded.title'),
            self.tr('UpdateCheck.Downloaded.text'),
            duration=3000,
            position=InfoBarPosition.TOP_RIGHT,
            parent=self.window(),
        )
        try:
            versionService.startInstaller(installer_path)
            self.showMessage(
                self.tr('UpdateCheck.InstallerStarted.title'),
                self.tr('UpdateCheck.InstallerStarted.text'),
                showCancelButton=False,
            )
            self.quitApplication()
        except Exception as error:
            self._onUpdateDownloadFailed(error)

    def _onUpdateDownloadFailed(self, error):
        self._closeUpdateDownloadInfoBar()
        logChanged('Log.Action.UpdateCheck', str(error), level='warning')
        InfoBar.error(
            self.tr('UpdateCheck.DownloadFailed.title'),
            self.tr('UpdateCheck.DownloadFailed.text'),
            duration=5000,
            position=InfoBarPosition.TOP_RIGHT,
            parent=self.window(),
        )

    def _closeUpdateDownloadInfoBar(self):
        info_bar = self._updateDownloadInfoBar
        self._updateDownloadInfoBar = None
        if info_bar is not None:
            info_bar.close()

    def _onUpdateChecked(self, result, silent=True):
        """Backward-compatible wrapper for older tests and pending callbacks."""
        self._checkingUpdate = False
        logChanged('Log.Action.UpdateCheck', result.latest_version)
        if result.has_new_version:
            if self.showMessage(
                    self.tr('UpdateCheck.NewVersion.title'),
                    self.tr(
                        'UpdateCheck.DownloadInstaller.text',
                        (result.current_version, result.latest_version),
                    )):
                self.downloadAndInstallUpdate()
            return
        if not silent:
            self.showMessage(
                self.tr('UpdateCheck.NoUpdate.title'),
                self.tr(
                    'UpdateCheck.NoUpdate.text',
                    (result.current_version,),
                ),
                showYesButton=False,
            )

    def _onUpdateCheckFailed(self, error, silent=True):
        self._checkingUpdate = False
        logChanged('Log.Action.UpdateCheck', str(error), level='warning')
        if silent:
            return
        InfoBar.error(
            self.tr('UpdateCheck.Failed.title'),
            self.tr('UpdateCheck.Failed.text'),
            duration=5000,
            position=InfoBarPosition.TOP_RIGHT,
            parent=self.window(),
        )

    def showInterface(self, interface, action_key, source_key='Log.Action.MenuBar'):
        logAction(source_key, self.tr(action_key))
        self.showWindow()
        self.switchTo(interface)

    def showSettingsFromMenu(self):
        self._showSettingsSection(
            'MenuBar.Preferences',
            'Log.Action.MenuBar',
            self.settingInterface.scrollToTop,
        )

    def showAboutFromMenu(self):
        self._showSettingsSection(
            'MenuBar.About',
            'Log.Action.MenuBar',
            self.settingInterface.scrollToAbout,
        )

    def showAboutQtFromMenu(self):
        logAction(
            'Log.Action.MenuBar', self.tr('MacApplicationMenu.AboutQt'))
        QApplication.aboutQt()

    def showSettingsFromTray(self):
        self._showSettingsSection(
            'SystemTray.Settings',
            'Log.Action.SystemTray',
            self.settingInterface.scrollToTop,
        )

    def _showSettingsSection(self, action_key, source_key, scroll_callback):
        self.showInterface(self.settingInterface, action_key, source_key)
        QTimer.singleShot(0, scroll_callback)

    def goBack(self):
        button = self.navigationInterface.panel.returnButton
        if button.isEnabled():
            logAction('Log.Action.MenuBar', self.tr('MenuBar.Back'))
            button.click()

    def toggleFullScreenFromShortcut(self):
        action_key = (
            'MenuBar.ExitFullScreen'
            if self.isFullScreen()
            else 'MenuBar.EnterFullScreen'
        )
        logAction('Log.Action.MenuBar', self.tr(action_key))
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def minimizeWindow(self):
        logAction('Log.Action.MenuBar', self.tr('MenuBar.Minimize'))
        window = self._nativeMacWindow()
        if window is not None:
            window.performMiniaturize_(None)
        else:
            self.showMinimized()

    def toggleWindowZoom(self):
        logAction('Log.Action.MenuBar', self.tr('MenuBar.Zoom'))
        window = self._nativeMacWindow()
        if window is not None:
            window.performZoom_(None)
        elif self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def bringAllToFront(self):
        logAction('Log.Action.MenuBar', self.tr('MenuBar.BringAllToFront'))
        if sys.platform == 'darwin':
            from AppKit import NSApplication
            application = NSApplication.sharedApplication()
            application.activateIgnoringOtherApps_(True)
            for window in application.windows():
                if window.isVisible():
                    window.orderFrontRegardless()
        self.showWindow()

    @staticmethod
    def _nativeMacWindow():
        if sys.platform != 'darwin':
            return None
        from AppKit import NSApplication
        application = NSApplication.sharedApplication()
        return application.keyWindow() or application.mainWindow()

    def openMenuUrl(self, action_key, url):
        logAction('Log.Action.MenuBar', self.tr(action_key))
        openUrl(url)

    def showWindow(self):
        logAction('Log.Action.WindowVisibility', self.tr('SystemTray.ShowWindow'))
        if self.windowState() & Qt.WindowMinimized:
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    def toggleWindow(self):
        logAction('Log.Action.SystemTray')
        if self.isVisible() and not self.isMinimized():
            self.hide()
            logChanged(
                'Log.Action.WindowVisibility',
                self.tr('SystemTray.HideWindow'),
            )
        else:
            self.showWindow()

    def setTrayIconDisabled(self, disabled):
        """Apply the tray setting immediately without restarting the app."""
        if disabled:
            self.systemTrayIcon.hide()
        else:
            self.systemTrayIcon.show()

    def quitApplication(self):
        if self._isQuitting:
            return
        self._isQuitting = True
        logAction('Log.Action.Quit')
        self.systemTrayIcon.hide()
        QApplication.instance().quit()

    def refreshGitHubUserName(self):
        token = authService.accessToken()
        if not token:
            return
        logStarted('Log.Action.UserName')
        future = TaskExecutor.run(getUserName, token)
        future.result.connect(
            lambda user_name, expected_token=token:
            self._onGitHubUserNameLoaded(expected_token, user_name)
        )

    def _onGitHubUserNameLoaded(self, token: str, user_name: str):
        if token != authService.accessToken():
            return
        user_name = user_name or ''
        cfg.set(cfg.usernameCache, user_name)
        signalBus.userNameChanged.emit(user_name)
        logChanged('Log.Action.UserName', user_name or getuser())

    def initNavigation(self):
        self.navigationInterface.setAcrylicEnabled(True)

        # add navigation items
        self.addSubInterface(
            self.homeInterface, FIF.HOME, self.tr('MainWindow.Home'))
        self.addSubInterface(
            self.browseInterface, Icon.REPO, self.tr('MainWindow.Browse'))
        self.addSubInterface(
            self.taskInterface, FIF.SCROLL, self.tr('MainWindow.Task'))
        
        # add custom widget to bottom
        self.addSubInterface(
            self.accountInterface, Icon.CONTACT, self.tr('MainWindow.Account'), NavigationItemPosition.BOTTOM)
        self.addSubInterface(
            self.settingInterface, Icon.SETTINGS, self.tr('MainWindow.Settings'), NavigationItemPosition.BOTTOM)

        if sys.platform == 'darwin':
            current = self.stackedWidget.currentWidget()
            if current:
                self.menuBar.setCurrentInterface(current.objectName())

        logger.info(self.tr('Log.App.SubInterfaces.Add.Success'))

        self.splashScreen.finish()

    def initWindow(self):
        self.resize(960, 780)
        self.setMinimumSize(520, 350)
        self.setWindowIcon(QIcon(':/app/images/logo.png'))
        self.setWindowTitle(self.tr('App.Name'))
        QApplication.setQuitOnLastWindowClosed(False)

        self.setCustomBackgroundColor(QColor(240, 244, 249), QColor(32, 32, 32))
        self.setMicaEffectEnabled(cfg.get(cfg.micaEnabled))

        # create splash screen
        self.splashScreen = SplashScreen(self.windowIcon(), self)
        self.splashScreen.setIconSize(QSize(106, 106))
        self.splashScreen.raise_()

        desktop = QApplication.primaryScreen().availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w//2 - self.width()//2, h//2 - self.height()//2)
        self.show()
        QApplication.processEvents()

    def onAppMessage(self, message: str):
        logReceived('Log.Action.Application', message)
        logger.info(self.tr('Log.App.AppMessage.Received', message))
        self.showWindow()
        if message == "show":
            return
        value = message.strip().strip('"\'')
        start = value.find('github-netdisk://')
        if start >= 0:
            value = value[start:].split()[0]
        try:
            request = parse_app_url(value)
        except ValueError as error:
            logFailed('Log.Action.Application', error)
            self.showMessage(
                self.tr('BrowseInterface.ErrorFlyout.title'), str(error),
                showYesButton=False,
            )
            return
        if isinstance(request, NewTaskRequest):
            self.showAddTaskDialog(request)
        elif isinstance(request, BrowseRepoRequest):
            self.switchTo(self.browseInterface)
            self.browseInterface.browse(request.repo, request.branch)
        else:
            self.switchTo(self.homeInterface)

    def showMessage(self, title: str, content: str, showYesButton: bool = True, showCancelButton: bool = True):
        logAction('Log.Action.MessageBox', title)
        logger.info(self.tr('Log.App.ShowMessage', (title, content)))
        w = MessageBox(title=title, content=content, parent=self.window())
        if not showYesButton:
            w.hideYesButton()
        if not showCancelButton:
            w.hideCancelButton()
        ret = w.exec()
        logger.info(self.tr('Log.App.ShowMessage.btnClicked', ('OK' if ret else 'Cancel')))
        return ret

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, 'splashScreen'):
            self.splashScreen.resize(self.size())

    def closeEvent(self, event):
        if self._isQuitting:
            event.accept()
            return
        if cfg.get(cfg.exitOnClose):
            event.accept()
            self.quitApplication()
            return
        event.ignore()
        self.hide()
        logChanged(
            'Log.Action.WindowVisibility',
            self.tr('SystemTray.HideWindow'),
        )

    def onCurrentChanged(self, index=None):
        current = self.stackedWidget.currentWidget()
        if current:
            logChanged('Log.Action.WindowNavigation', current.objectName())
            if (sys.platform == 'darwin'
                    and isinstance(getattr(self, 'menuBar', None), MenuBar)):
                self.menuBar.setCurrentInterface(current.objectName())
                controller = getattr(self, 'nativeMenuController', None)
                if controller is not None:
                    QTimer.singleShot(0, controller.updateViewMenu)
        if self.stackedWidget.currentWidget() is self.homeInterface:
            self.homeInterface.refreshCards()
        elif self.stackedWidget.currentWidget() is self.taskInterface:
            self.taskInterface.selectPreferredCategory()
        elif self.stackedWidget.currentWidget() is self.accountInterface:
            self.accountInterface.refreshStatus()

    def onExit(self):
        if self._cleanupDone:
            return
        self._cleanupDone = True
        self.systemTrayIcon.hide()
        transferTaskService.save()
        aria2DownloadService.close()
        stopSystemThemeListener(self.themeListener)
        self.themeListener.deleteLater()
        logger.info(self.tr('Log.App.Close.Success'))
