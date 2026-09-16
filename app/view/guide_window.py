# coding: utf-8
import sys
from threading import Event

from loguru import logger
from PyQt5.QtCore import QEvent, QSize, Qt, QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (QApplication, QWidget, QHBoxLayout, QVBoxLayout,
                             QStackedWidget, QSizePolicy)
from pyqt5_concurrent.TaskExecutor import TaskExecutor
from qfluentwidgets import (FluentWidget, SplashScreen, TitleLabel, BodyLabel,
                            CaptionLabel,
                            PasswordLineEdit, CardWidget, OpacityAniStackedWidget, IconWidget,
                            FluentIcon, SubtitleLabel, TransparentToolButton, HyperlinkButton,
                            PushButton, PrimaryPushButton, ToolTipPosition, MessageBox, InfoBar,
                            InfoBarPosition)
from qfluentwidgets.components.material import AcrylicToolTipFilter

from ..components.menu_bar import GuideMenuBar
from ..components.native_menu import MacNativeMenuController
from ..common.signal_bus import signalBus
from ..common.event_logger import (
    logAction,
    logCancelled,
    logFailed,
    logStarted,
    logSucceeded,
)
from ..common.translator import translate
from ..common.config import cfg
from ..service.github_service import getUserLogin, getUserName
from ..service.auth_service import (
    AUTH_PAT,
    DeviceFlowCancelled,
    authService,
)
from ..common.setting import FEEDBACK_URL, localizedWebsiteUrl
from ..common.theme_listener import SystemThemeListener, stopSystemThemeListener
from ..common.utils import openUrl, unwrapFutureError
from .main_window import MainWindow

class WelcomeInterface(QWidget):
    def __init__(self, parent = None):
        super().__init__(parent=parent)
        self.tr = translate
        self.__initWidgets()

    def __initWidgets(self):
        self.expandLayout = QVBoxLayout(self)
        self.expandLayout.setContentsMargins(24, 20, 24, 20)
        self.expandLayout.setSpacing(0)

        self.guideLabel = TitleLabel(self.tr('GuideWindow.Welcome'), self)
        self.bodyLabel = BodyLabel(self.tr('GuideWindow.text'), self)
        self.bodyLabel.setWordWrap(True)
        self.disclaimerLabel = CaptionLabel(
            self.tr('GuideWindow.Disclaimer'), self)
        self.disclaimerLabel.setWordWrap(True)

        self.githubAppCardWidget = CardWidget(self)
        self.githubAppCardWidget.setMinimumHeight(96)
        self.githubAppCardWidget.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.githubAppCardWidget.hBoxLayout = QHBoxLayout(self.githubAppCardWidget)
        self.githubAppCardWidget.hBoxLayout.setContentsMargins(20, 16, 20, 16)
        self.githubAppCardWidget.hBoxLayout.setSpacing(16)
        self.githubAppCardWidget.vBoxLayout = QVBoxLayout()
        self.githubAppCardWidget.vBoxLayout.setSpacing(6)
        self.githubAppCardWidget.titleLabel = SubtitleLabel(
            self.tr('GuideWindow.githubAppCardWidget.title'), self.githubAppCardWidget)
        self.githubAppCardWidget.label = BodyLabel(
            self.tr('GuideWindow.githubAppCardWidget.text'), self.githubAppCardWidget)
        self.githubAppCardWidget.label.setWordWrap(True)
        self.githubAppCardWidget.icon = IconWidget(
            FluentIcon.RIGHT_ARROW, self.githubAppCardWidget)
        self.githubAppCardWidget.icon.setFixedSize(20, 20)
        self.githubAppCardWidget.vBoxLayout.addWidget(
            self.githubAppCardWidget.titleLabel)
        self.githubAppCardWidget.vBoxLayout.addWidget(
            self.githubAppCardWidget.label)
        self.githubAppCardWidget.hBoxLayout.addLayout(
            self.githubAppCardWidget.vBoxLayout, 1)
        self.githubAppCardWidget.hBoxLayout.addWidget(
            self.githubAppCardWidget.icon, 0, Qt.AlignRight | Qt.AlignTop)

        self.tokenCardWidget = CardWidget(self)
        self.tokenCardWidget.setMinimumHeight(96)
        self.tokenCardWidget.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.tokenCardWidget.hBoxLayout = QHBoxLayout(self.tokenCardWidget)
        self.tokenCardWidget.hBoxLayout.setContentsMargins(20, 16, 20, 16)
        self.tokenCardWidget.hBoxLayout.setSpacing(16)
        self.tokenCardWidget.vBoxLayout = QVBoxLayout()
        self.tokenCardWidget.vBoxLayout.setSpacing(6)
        self.tokenCardWidget.titleLabel = SubtitleLabel(self.tr('GuideWindow.tokenCardWidget.title'), self.tokenCardWidget)
        self.tokenCardWidget.label = BodyLabel(self.tr('GuideWindow.tokenCardWidget.text'), self.tokenCardWidget)
        self.tokenCardWidget.label.setWordWrap(True)
        self.tokenCardWidget.icon = IconWidget(FluentIcon.RIGHT_ARROW, self.tokenCardWidget)
        self.tokenCardWidget.icon.setFixedSize(20, 20)

        self.tokenCardWidget.vBoxLayout.addWidget(self.tokenCardWidget.titleLabel)
        self.tokenCardWidget.vBoxLayout.addWidget(self.tokenCardWidget.label)
        self.tokenCardWidget.hBoxLayout.addLayout(
            self.tokenCardWidget.vBoxLayout, 1)
        self.tokenCardWidget.hBoxLayout.addWidget(self.tokenCardWidget.icon, 0, Qt.AlignRight | Qt.AlignTop)

        self.notLoginButton = HyperlinkButton('', self.tr('GuideWindow.notLoginButton.text'), self)
        self.expandLayout.addWidget(self.guideLabel)
        self.expandLayout.addSpacing(12)
        self.expandLayout.addWidget(self.bodyLabel)
        self.expandLayout.addSpacing(24)
        self.expandLayout.addWidget(self.githubAppCardWidget)
        self.expandLayout.addSpacing(12)
        self.expandLayout.addWidget(self.tokenCardWidget)
        self.expandLayout.addStretch(1)
        self.expandLayout.addSpacing(16)
        self.expandLayout.addWidget(self.disclaimerLabel)
        self.expandLayout.addSpacing(8)
        self.expandLayout.addWidget(self.notLoginButton, 0, Qt.AlignLeft)

class GitHubAppLoginInterface(QWidget):
    """Guide page for GitHub App Device Flow authentication."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.tr = translate
        self._cancelEvent = Event()
        self._session = None
        self.expandLayout = QVBoxLayout(self)
        self.expandLayout.setContentsMargins(24, 16, 24, 20)
        self.expandLayout.setSpacing(0)

        self.returnBtn = TransparentToolButton(self)
        self.returnBtn.setIcon(FluentIcon.RETURN)
        self.returnBtn.setToolTip(self.tr('GuideWindow.returnBtn.tooltip'))
        self.returnBtn.setIconSize(QSize(20, 20))
        self.returnBtn.setFixedSize(32, 32)
        self.titleLabel = TitleLabel(
            self.tr('GuideWindow.githubAppLoginInterface.title'), self)
        self.bodyLabel = BodyLabel(
            self.tr('GuideWindow.githubAppLoginInterface.text'), self)
        self.bodyLabel.setWordWrap(True)
        self.codeLabel = SubtitleLabel(
            self.tr('GuideWindow.githubAppLoginInterface.noCode'), self)
        self.statusLabel = BodyLabel(
            self.tr('GuideWindow.githubAppLoginInterface.ready'), self)

        self.buttonsWidget = QWidget(self)
        self.buttonsLayout = QHBoxLayout(self.buttonsWidget)
        self.buttonsLayout.setContentsMargins(0, 0, 0, 0)
        self.buttonsLayout.setSpacing(12)
        self.startButton = PrimaryPushButton(
            self.tr('GuideWindow.githubAppLoginInterface.start'), self.buttonsWidget)
        self.copyButton = PushButton(
            self.tr('GuideWindow.githubAppLoginInterface.copy'), self.buttonsWidget)
        self.browserButton = PushButton(
            self.tr('GuideWindow.githubAppLoginInterface.browser'), self.buttonsWidget)
        self.copyButton.setEnabled(False)
        self.browserButton.setEnabled(False)
        self.buttonsLayout.addWidget(self.startButton)
        self.buttonsLayout.addWidget(self.copyButton)
        self.buttonsLayout.addWidget(self.browserButton)
        self.buttonsLayout.addStretch(1)
        self.expandLayout.addWidget(self.returnBtn)
        self.expandLayout.addSpacing(12)
        self.expandLayout.addWidget(self.titleLabel)
        self.expandLayout.addSpacing(12)
        self.expandLayout.addWidget(self.bodyLabel)
        self.expandLayout.addSpacing(24)
        self.expandLayout.addWidget(self.codeLabel)
        self.expandLayout.addSpacing(8)
        self.expandLayout.addWidget(self.statusLabel)
        self.expandLayout.addSpacing(20)
        self.expandLayout.addWidget(self.buttonsWidget)
        self.expandLayout.addStretch(1)

        self.startButton.clicked.connect(self.startLogin)
        self.copyButton.clicked.connect(self.copyCode)
        self.browserButton.clicked.connect(self.openBrowser)

    def startLogin(self):
        if not authService.isGithubAppConfigured():
            InfoBar.error(
                self.tr('GitHubApp.ConfigMissing.title'),
                self.tr('GitHubApp.ConfigMissing.text'),
                duration=5000,
                position=InfoBarPosition.TOP_RIGHT,
                parent=self,
            )
            return
        self.cancelLogin(reset=False)
        self._cancelEvent = Event()
        self.startButton.setEnabled(False)
        self.statusLabel.setText(
            self.tr('GuideWindow.githubAppLoginInterface.requesting'))
        future = TaskExecutor.run(authService.requestDeviceCode)
        future.result.connect(self._deviceCodeReady)
        future.failed.connect(self._loginFailed)

    def _deviceCodeReady(self, session):
        if self._cancelEvent.is_set():
            return
        self._session = session
        self.codeLabel.setText(session.user_code)
        self.copyButton.setEnabled(True)
        self.browserButton.setEnabled(True)
        self.statusLabel.setText(
            self.tr('GuideWindow.githubAppLoginInterface.waiting'))
        self.copyCode()
        self.openBrowser()
        future = TaskExecutor.run(
            authService.waitForDeviceAuthorization, session, self._cancelEvent)
        future.result.connect(self._loginSucceeded)
        future.failed.connect(self._loginFailed)

    def copyCode(self):
        if self._session:
            QApplication.clipboard().setText(self._session.user_code)

    def openBrowser(self):
        if self._session:
            logAction('Log.Action.OpenLink', self._session.verification_uri)
            openUrl(self._session.verification_uri)

    def _loginSucceeded(self, authorization):
        if self._cancelEvent.is_set():
            return
        try:
            identity = authService.completeDeviceAuthorization(authorization)
        except Exception as error:
            self._loginFailed(error)
            return
        logSucceeded('Log.Action.Login', identity.login)
        installation_url = authService.installationUrl()
        logAction('Log.Action.OpenLink', installation_url)
        openUrl(installation_url)
        InfoBar.success(
            self.tr('GuideWindow.tokenLoginInterface.loginSucceed.title'),
            self.tr('GuideWindow.githubAppLoginInterface.succeeded',
                    (identity.login,)),
            duration=5000,
            parent=self.window(),
        )
        self.window().onAuthenticated(identity)

    def _loginFailed(self, error):
        error = unwrapFutureError(error)
        if isinstance(error, DeviceFlowCancelled) or self._cancelEvent.is_set():
            return
        logFailed('Log.Action.Login', error)
        self.startButton.setEnabled(True)
        self.statusLabel.setText(
            self.tr('GuideWindow.githubAppLoginInterface.ready'))
        InfoBar.error(
            self.tr('AccountInterface.LoginFailed'),
            str(error),
            duration=5000,
            parent=self.window(),
        )

    def cancelLogin(self, reset=True):
        self._cancelEvent.set()
        self._session = None
        if reset:
            self.codeLabel.setText(
                self.tr('GuideWindow.githubAppLoginInterface.noCode'))
            self.statusLabel.setText(
                self.tr('GuideWindow.githubAppLoginInterface.ready'))
            self.startButton.setEnabled(True)
            self.copyButton.setEnabled(False)
            self.browserButton.setEnabled(False)


class TokenLoginInterface(QWidget):
    def __init__(self, parent = None):
        super().__init__(parent=parent)
        self.tr = translate
        self.__initWidgets()

    def __initWidgets(self):
        self.expandLayout = QVBoxLayout(self)
        self.expandLayout.setContentsMargins(24, 16, 24, 20)
        self.expandLayout.setSpacing(0)

        self.returnBtn = TransparentToolButton(self)
        self.returnBtn.setIcon(FluentIcon.RETURN)
        self.returnBtn.setToolTip(self.tr('GuideWindow.returnBtn.tooltip'))
        self.returnBtn.setIconSize(QSize(20, 20))
        self.returnBtn.setFixedSize(32, 32)
        self.returnBtn.installEventFilter(AcrylicToolTipFilter(self.returnBtn, position=ToolTipPosition.BOTTOM_LEFT))

        self.titleLabel = TitleLabel(self.tr('GuideWindow.tokenLoginInterface.title'), self)
        self.titleLabel.adjustSize()

        self.bodyLabel = BodyLabel(self.tr('TokenLogin.Help'), self)
        self.bodyLabel.setWordWrap(True)
        self.bodyLabel.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.bodyLabel.setOpenExternalLinks(False)

        self.tokenInput = PasswordLineEdit(self)
        self.tokenInput.setPlaceholderText(self.tr('GuideWindow.tokenLoginInterface.tokenInput.text'))

        self.buttonsWidget = QWidget(self)
        self.buttonsLayout = QHBoxLayout(self.buttonsWidget)
        self.buttonsLayout.setContentsMargins(0, 0, 0, 0)
        self.buttonsLayout.setSpacing(12)

        self.testBtn = PushButton(self.tr('GuideWindow.tokenLoginInterface.testBtn.text'), self.buttonsWidget)
        self.testBtn.adjustSize()
        self.buttonsLayout.addWidget(self.testBtn)

        self.loginBtn = PrimaryPushButton(self.tr('GuideWindow.tokenLoginInterface.loginBtn.text'), self.buttonsWidget)
        self.loginBtn.adjustSize()
        self.buttonsLayout.addWidget(self.loginBtn)
        self.buttonsLayout.addStretch(1)

        self.expandLayout.addWidget(self.returnBtn)
        self.expandLayout.addSpacing(12)
        self.expandLayout.addWidget(self.titleLabel)
        self.expandLayout.addSpacing(12)
        self.expandLayout.addWidget(self.bodyLabel)
        self.expandLayout.addSpacing(20)
        self.expandLayout.addWidget(self.tokenInput)
        self.expandLayout.addSpacing(16)
        self.expandLayout.addWidget(self.buttonsWidget)
        self.expandLayout.addStretch(1)

        self.testBtn.clicked.connect(self.onTestBtnClicked)
        self.loginBtn.clicked.connect(self.onLoginBtnClicked)
        self.tokenInput.textChanged.connect(lambda: self.tokenInput.setError(False))
        self.bodyLabel.linkActivated.connect(self.openTokenCreationPage)

    def openTokenCreationPage(self, url):
        logAction('Log.Action.OpenLink', url)
        openUrl(url)

    def onTestBtnClicked(self):
        logger.info(self.tr('Log.GuideWindow.TokenLoginInterface.TestBtn.clicked'))
        if not self.tokenInput.text():
            logCancelled('Log.Action.TokenValidation')
            return

        # test github token
        logStarted('Log.Action.TokenValidation')
        username = getUserLogin(self.tokenInput.text())
        if not username:
            logFailed('Log.Action.TokenValidation')
            self.window().showMessage(self.tr('GuideWindow.tokenLoginInterface.testFailedMsgBox.title'),
                                      self.tr('GuideWindow.tokenLoginInterface.testFailedMsgBox.text'),
                                      showCancelButton=False)
            self.tokenInput.setError(True)
            return
        logSucceeded('Log.Action.TokenValidation', username)
        self.window().showMessage(self.tr('GuideWindow.tokenLoginInterface.testSucceedMsgBox.title'),
                                  self.tr('GuideWindow.tokenLoginInterface.testSucceedMsgBox.text',
                                          (username, )),
                                  showCancelButton=False)

    def onLoginBtnClicked(self):
        logger.info(self.tr('Log.GuideWindow.TokenLoginInterface.LoginBtn.clicked'))
        if not self.tokenInput.text():
            logCancelled('Log.Action.Login')
            return

        # test github token
        logStarted('Log.Action.Login')
        username = getUserLogin(self.tokenInput.text())
        if not username:
            logFailed('Log.Action.Login')
            InfoBar.error(
                title=self.tr('GuideWindow.tokenLoginInterface.loginFailed.title'),
                content=self.tr('GuideWindow.tokenLoginInterface.loginFailed.text'),
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self.window()
            )
            self.tokenInput.setError(True)
            return
        try:
            identity = authService.storeToken(
                self.tokenInput.text(),
                AUTH_PAT,
                (username, getUserName(self.tokenInput.text()) or username),
            )
        except Exception as error:
            logFailed('Log.Action.Login', error)
            InfoBar.error(
                title=self.tr('GuideWindow.tokenLoginInterface.loginFailed.title'),
                content=str(error),
                duration=5000,
                parent=self.window(),
            )
            return
        logSucceeded('Log.Action.Login', username)
        InfoBar.success(
            title=self.tr('GuideWindow.tokenLoginInterface.loginSucceed.title'),
            content=self.tr('GuideWindow.tokenLoginInterface.loginSucceed.text', (username,)),
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=2000,
            parent=self.window()
        )
        self.tokenInput.clear()
        QTimer.singleShot(1000, lambda: self.window().onAuthenticated(identity))

class GuideWindow(FluentWidget):

    def __init__(self, parent=None, forced_username=None):
        super().__init__(parent=parent)
        self.tr = translate
        self._forcedUsername = str(forced_username or '').strip()
        logger.info(self.tr('Log.GuideWindow.Initialize.Start'))

        # create system theme listener
        self.themeListener = SystemThemeListener(self)

        self.initWidgets()
        self.initWindow()
        self.initMenuBar()
        self.connectSignalToSlot()

        self.splashScreen.finish()
        self.themeListener.start()

        logger.info(self.tr('Log.GuideWindow.Initialize.Success'))

    def connectSignalToSlot(self):
        self.welcomeInterface.githubAppCardWidget.clicked.connect(
            lambda: logAction('Log.Action.Login', 'GitHub App'))
        self.welcomeInterface.githubAppCardWidget.clicked.connect(
            lambda: self.stackedWidget.setCurrentWidget(self.githubAppLoginInterface))
        self.welcomeInterface.tokenCardWidget.clicked.connect(lambda: logger.info(self.tr('Log.GuideWindow.TokenCardWidget.clicked')))
        self.welcomeInterface.tokenCardWidget.clicked.connect(lambda: self.stackedWidget.setCurrentWidget(self.tokenLoginInterface))
        self.welcomeInterface.notLoginButton.clicked.connect(lambda: logger.info(self.tr('Log.GuideWindow.NotLoginButton.clicked')))
        self.welcomeInterface.notLoginButton.clicked.connect(self.onNotLogin)
        self.tokenLoginInterface.returnBtn.clicked.connect(lambda: logger.info(self.tr('Log.GuideWindow.TokenLoginInterface.ReturnBtn.clicked')))
        self.tokenLoginInterface.returnBtn.clicked.connect(self.goBack)
        self.githubAppLoginInterface.returnBtn.clicked.connect(self.goBack)
        self.stackedWidget.currentChanged.connect(self.updateBackAction)
        signalBus.micaEnableChanged.connect(self.setMicaEffectEnabled)

    def initMenuBar(self):
        self.menuBar = GuideMenuBar(self)
        self.menuBar.closeWindowAct.triggered.connect(self.close)
        self.menuBar.helpAct.triggered.connect(
            lambda: self.openMenuUrl(
                'MenuBar.OpenHelp',
                localizedWebsiteUrl(cfg.get(cfg.language).name())))
        self.menuBar.feedbackAct.triggered.connect(
            lambda: self.openMenuUrl('MenuBar.Feedback', FEEDBACK_URL))
        self.menuBar.aboutQtAct.triggered.connect(self.showAboutQtFromMenu)
        self.menuBar.backAct.triggered.connect(self.goBack)
        self.menuBar.fullScreenAct.triggered.connect(
            self.toggleFullScreenFromShortcut)
        self.updateBackAction()
        if sys.platform == 'darwin':
            self.addAction(self.menuBar.fullScreenAct)
            self.nativeMenuController = MacNativeMenuController(
                self, self.menuBar, show_back=True)
            QTimer.singleShot(0, self.nativeMenuController.install)
        else:
            self.menuBar.hide()
            for action in self.menuBar.shortcutActions():
                self.addAction(action)

    def canGoBack(self):
        return self.stackedWidget.currentWidget() is not self.welcomeInterface

    def updateBackAction(self, _index=None):
        self.menuBar.backAct.setEnabled(self.canGoBack())

    def goBack(self):
        if not self.canGoBack():
            return
        logAction('Log.Action.MenuBar', self.tr('MenuBar.Back'))
        if self.stackedWidget.currentWidget() is self.githubAppLoginInterface:
            self.githubAppLoginInterface.cancelLogin()
        self.stackedWidget.setCurrentWidget(self.welcomeInterface)

    def showAboutQtFromMenu(self):
        logAction(
            'Log.Action.MenuBar', self.tr('MacApplicationMenu.AboutQt'))
        QApplication.aboutQt()

    def toggleFullScreenFromShortcut(self):
        action_key = (
            'MenuBar.ExitFullScreen'
            if self.isFullScreen()
            else 'MenuBar.EnterFullScreen'
        )
        logAction('Log.Action.MenuBar', self.tr(action_key))

        # Keep the welcome window on the same AppKit fullscreen path as the
        # main window.  Qt's showFullScreen()/showNormal() path can leave
        # Cocoa cursor tracking stale after the transition on macOS.
        if sys.platform == 'darwin':
            native_window = MainWindow._nativeMacWindow()
            if native_window is not None:
                native_window.toggleFullScreen_(None)
                self._scheduleCursorRefresh()
                return

        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def initWidgets(self):
        self.stackedWidget = QStackedWidget(self)

        self.welcomeInterface = WelcomeInterface()
        self.stackedWidget.addWidget(self.welcomeInterface)

        self.githubAppLoginInterface = GitHubAppLoginInterface()
        self.stackedWidget.addWidget(self.githubAppLoginInterface)

        self.tokenLoginInterface = TokenLoginInterface()
        self.stackedWidget.addWidget(self.tokenLoginInterface)

    def initWindow(self):
        self.resize(840, 530)
        self.setMinimumSize(820, 510)
        self.setWindowIcon(QIcon(':/app/images/logo.png'))
        self.setWindowTitle(self.tr("GuideWindow.title"))

        # create splash screen
        self.splashScreen = SplashScreen(self.windowIcon(), self)
        self.splashScreen.setIconSize(QSize(106, 106))
        self.splashScreen.raise_()

        desktop = QApplication.primaryScreen().availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)
        self.show()
        QApplication.processEvents()

    def onNotLogin(self):
        logAction('Log.Action.Login', self.tr('GuideWindow.notLoginButton.text'))
        ok = self.showMessage(self.tr('GuideWindow.notLoginMessageBox.title'), self.tr('GuideWindow.notLoginMessageBox.text'))
        if ok:
            logSucceeded('Log.Action.Login', self.tr('GuideWindow.notLoginButton.text'))
            authService.disconnect()
            self.mainWindow = MainWindow(
                forced_username=self._forcedUsername)
            QApplication.instance().aboutToQuit.connect(self.mainWindow.onExit)
            self.mainWindow.show()
            stopSystemThemeListener(self.themeListener)
            self.hide()
            cfg.set(cfg.firstUse, False)
        else:
            logCancelled('Log.Action.Login', self.tr('GuideWindow.notLoginButton.text'))

    def onAuthenticated(self, identity):
        cfg.set(cfg.firstUse, False)
        signalBus.userNameChanged.emit(identity.name)
        self.mainWindow = MainWindow(
            forced_username=self._forcedUsername)
        QApplication.instance().aboutToQuit.connect(self.mainWindow.onExit)
        self.mainWindow.show()
        stopSystemThemeListener(self.themeListener)
        self.hide()

    def minimizeWindow(self):
        logAction('Log.Action.MenuBar', self.tr('MenuBar.Minimize'))
        self.showMinimized()

    def toggleWindowZoom(self):
        logAction('Log.Action.MenuBar', self.tr('MenuBar.Zoom'))
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def bringAllToFront(self):
        logAction('Log.Action.MenuBar', self.tr('MenuBar.BringAllToFront'))
        self.show()
        self.raise_()
        self.activateWindow()

    def openMenuUrl(self, action_key, url):
        logAction('Log.Action.MenuBar', self.tr(action_key))
        openUrl(url)

    def showMessage(self, title: str, content: str, showYesButton: bool = True, showCancelButton: bool = True):
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

        if hasattr(self, 'stackedWidget'):
            self.stackedWidget.move(0, self.titleBar.height())
            self.stackedWidget.resize(
                self.width(), max(0, self.height() - self.titleBar.height()))

    def changeEvent(self, event):
        super().changeEvent(event)
        if sys.platform == 'darwin' and event.type() == QEvent.WindowStateChange:
            self._scheduleCursorRefresh()

    def _scheduleCursorRefresh(self):
        for delay in (0, 350, 800):
            QTimer.singleShot(delay, self._refreshWidgetCursors)

    def _refreshWidgetCursors(self):
        for widget in (self, *self.findChildren(QWidget)):
            if not widget.testAttribute(Qt.WA_SetCursor):
                continue
            cursor = widget.cursor()
            widget.unsetCursor()
            widget.setCursor(cursor)

    def closeEvent(self, e):
        if hasattr(self, 'githubAppLoginInterface'):
            self.githubAppLoginInterface.cancelLogin(reset=False)
        stopSystemThemeListener(self.themeListener)
        self.themeListener.deleteLater()
        super().closeEvent(e)
        logger.info(self.tr('Log.App.Close.Success'))
