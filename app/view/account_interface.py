# coding: utf-8
"""GitHub App and compatibility-token account management."""
from threading import Event

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout, QWidget
from pyqt5_concurrent.TaskExecutor import TaskExecutor
from qfluentwidgets import (
    BodyLabel,
    ExpandGroupSettingCard,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    PasswordLineEdit,
    PrimaryPushButton,
    PushButton,
    ScrollArea,
    SimpleCardWidget,
    StrongBodyLabel,
    TitleLabel,
)

from ..components.label import ThemedRichBodyLabel
from ..common.event_logger import (
    logAction,
    logCancelled,
    logChanged,
    logFailed,
    logInitialized,
    logStarted,
    logSucceeded,
)
from ..common.signal_bus import signalBus
from ..common.style_sheet import StyleSheet
from ..common.translator import translate
from ..common.utils import openUrl, unwrapFutureError
from ..service.auth_service import (
    AUTH_GITHUB_APP,
    AUTH_PAT,
    DeviceFlowCancelled,
    authService,
)
from ..service.github_service import getUserByToken, getUserLogin, getUserName


class AccountInterface(ScrollArea):
    """Prefer GitHub App sign-in while retaining PAT as an advanced option."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.tr = translate
        self._deviceSession = None
        self._cancelEvent = Event()
        self.scrollWidget = QWidget(self)
        self.vBoxLayout = QVBoxLayout(self.scrollWidget)

        self.titleLabel = TitleLabel(
            self.tr('AccountInterface.Account'), self.scrollWidget)
        self._initSessionCard()
        self._initGithubAppCard()
        self._initPatCard()

        self.vBoxLayout.setContentsMargins(36, 42, 36, 36)
        self.vBoxLayout.setSpacing(0)
        self.vBoxLayout.addWidget(self.titleLabel)
        self.vBoxLayout.addSpacing(24)
        self.vBoxLayout.addWidget(self.sessionCard)
        self.vBoxLayout.addSpacing(20)
        self.vBoxLayout.addWidget(self.appCard)
        self.vBoxLayout.addSpacing(28)
        self.vBoxLayout.addWidget(self.patCard)
        self.vBoxLayout.addSpacing(24)
        self.vBoxLayout.addStretch(1)
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setObjectName('accountInterface')
        self.scrollWidget.setObjectName('scrollWidget')
        StyleSheet.FLUENT_INTERFACE.apply(self)

        self.refreshStatus()
        logInitialized('Log.Action.Account')

    def _initSessionCard(self):
        """Create a provider-neutral card for the active login session."""
        self.sessionCard = SimpleCardWidget(self.scrollWidget)
        layout = QHBoxLayout(self.sessionCard)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(16)
        textLayout = QVBoxLayout()
        textLayout.setSpacing(4)
        self.sessionTitleLabel = StrongBodyLabel(
            self.tr('AccountInterface.Session.Title'), self.sessionCard)
        self.sessionStatusLabel = BodyLabel(self.sessionCard)
        self.sessionStatusLabel.setWordWrap(True)
        textLayout.addWidget(self.sessionTitleLabel)
        textLayout.addWidget(self.sessionStatusLabel)
        self.logoutButton = PushButton(
            self.tr('AccountInterface.Logout'), self.sessionCard)
        self.logoutButton.setEnabled(False)
        layout.addLayout(textLayout, 1)
        layout.addWidget(self.logoutButton, 0, Qt.AlignVCenter)
        self.logoutButton.clicked.connect(self.logout)

    def _initGithubAppCard(self):
        self.appCard = SimpleCardWidget(self.scrollWidget)
        self.appCardLayout = QVBoxLayout(self.appCard)
        self.appCardLayout.setContentsMargins(24, 24, 24, 24)
        self.appCardLayout.setSpacing(0)
        self.appTitleLabel = StrongBodyLabel(
            self.tr('AccountInterface.GitHubApp.Title'), self.appCard)
        self.statusLabel = StrongBodyLabel(self.appCard)
        self.appDescriptionLabel = BodyLabel(
            self.tr('AccountInterface.GitHubApp.Description'), self.appCard)
        self.appDescriptionLabel.setWordWrap(True)
        self.deviceCodeLabel = StrongBodyLabel(
            self.tr('AccountInterface.GitHubApp.NoCode'), self.appCard)
        self.deviceCodeLabel.hide()
        self.appButtonLayout = QHBoxLayout()
        self.appButtonLayout.setSpacing(12)
        self.connectButton = PrimaryPushButton(
            self.tr('AccountInterface.GitHubApp.Connect'), self.appCard)
        self.copyCodeButton = PushButton(
            self.tr('AccountInterface.GitHubApp.CopyCode'), self.appCard)
        self.manageButton = PushButton(
            self.tr('AccountInterface.GitHubApp.Manage'), self.appCard)
        self.copyCodeButton.setEnabled(False)
        for button in (
                self.connectButton, self.copyCodeButton,
                self.manageButton):
            self.appButtonLayout.addWidget(button)
        self.appButtonLayout.addStretch(1)
        self.appCardLayout.addWidget(self.appTitleLabel)
        self.appCardLayout.addSpacing(8)
        self.appCardLayout.addWidget(self.statusLabel)
        self.appCardLayout.addSpacing(12)
        self.appCardLayout.addWidget(self.appDescriptionLabel)
        self.appCardLayout.addSpacing(12)
        self.appCardLayout.addWidget(self.deviceCodeLabel)
        self.appCardLayout.addSpacing(16)
        self.appCardLayout.addLayout(self.appButtonLayout)

        self.connectButton.clicked.connect(self.connectGithubApp)
        self.copyCodeButton.clicked.connect(self.copyDeviceCode)
        self.manageButton.clicked.connect(self.openManageAccess)
        self.logoutButton.clicked.connect(self.logout)

    def _initPatCard(self):
        self.patCard = ExpandGroupSettingCard(
            FluentIcon.DEVELOPER_TOOLS,
            self.tr('AccountInterface.Advanced'),
            self.tr('AccountInterface.PAT.Title'),
            self.scrollWidget,
        )
        self.advancedCard = self.patCard
        self.patContentWidget = QWidget(self.patCard)
        self.patCardLayout = QVBoxLayout(self.patContentWidget)
        self.patCardLayout.setContentsMargins(24, 16, 24, 20)
        self.patCardLayout.setSpacing(0)
        self.patDescriptionLabel = ThemedRichBodyLabel(self.patContentWidget)
        self.patDescriptionLabel.setText(
            self.tr('AccountInterface.PAT.Description'))
        self.patDescriptionLabel.setWordWrap(True)
        self.patDescriptionLabel.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.patDescriptionLabel.setOpenExternalLinks(False)
        self.tokenEdit = PasswordLineEdit(self.patContentWidget)
        self.tokenEdit.setPlaceholderText(
            self.tr('AccountInterface.TokenPlaceholder'))
        self.tokenEdit.setClearButtonEnabled(True)
        self.saveButton = PushButton(
            self.tr('AccountInterface.PAT.Login'), self.patContentWidget)
        self.patButtonLayout = QHBoxLayout()
        self.patButtonLayout.setSpacing(12)
        self.patButtonLayout.addWidget(self.saveButton)
        self.patButtonLayout.addStretch(1)
        self.patCardLayout.addWidget(self.patDescriptionLabel)
        self.patCardLayout.addSpacing(16)
        self.patCardLayout.addWidget(self.tokenEdit)
        self.patCardLayout.addSpacing(16)
        self.patCardLayout.addLayout(self.patButtonLayout)
        self.patCard.addGroupWidget(self.patContentWidget)
        self._syncPatCardHeight()

        self.saveButton.clicked.connect(self.login)
        self.patDescriptionLabel.linkActivated.connect(self.openTokenCreationPage)
        self.patCard.expandAni.finished.connect(self._syncPatCardHeight)

    def _syncPatCardHeight(self):
        content_height = self.patContentWidget.height()
        self.patCard.spaceWidget.setFixedHeight(content_height)
        if not self.patCard.isExpand:
            self.patCard.verticalScrollBar().setValue(
                self.patCard.verticalScrollBar().maximum())
            self.patCard.setFixedHeight(self.patCard.card.height())
        else:
            self.patCard.setFixedHeight(
                self.patCard.card.height() + content_height)

    def openTokenCreationPage(self, url):
        logAction('Log.Action.OpenLink', url)
        openUrl(url)

    def openManageAccess(self):
        url = authService.installationUrl()
        logAction('Log.Action.OpenLink', url)
        openUrl(url)

    def refreshStatus(self):
        authenticated = authService.isAuthenticated()
        login = self._currentLogin()
        mode = authService.mode()
        app_connected = authenticated and mode == AUTH_GITHUB_APP
        if app_connected:
            app_text = self.tr('AccountInterface.LoggedInGitHubApp', (login,))
        else:
            app_text = self.tr('AccountInterface.GitHubApp.NotConnected')
        self.statusLabel.setText(app_text)
        if authenticated:
            session_text = self.tr(
                'AccountInterface.LoggedInGitHubApp'
                if mode == AUTH_GITHUB_APP else 'AccountInterface.LoggedInPAT',
                (login,),
            )
        else:
            session_text = self.tr('AccountInterface.NotLoggedIn')
        self.sessionStatusLabel.setText(session_text)
        self.logoutButton.setEnabled(authenticated)
        logChanged('Log.Action.Account', login if authenticated else '-', level='debug')

    @staticmethod
    def _currentLogin():
        from ..common.config import cfg
        return str(cfg.get(cfg.userLoginCache) or '')

    def connectGithubApp(self):
        logAction('Log.Action.Login', 'GitHub App')
        if not authService.isGithubAppConfigured():
            InfoBar.error(
                self.tr('GitHubApp.ConfigMissing.title'),
                self.tr('GitHubApp.ConfigMissing.text'),
                duration=5000,
                position=InfoBarPosition.TOP_RIGHT,
                parent=self,
            )
            return
        self.cancelDeviceFlow(reset=False)
        self._cancelEvent = Event()
        self.connectButton.setEnabled(False)
        self.saveButton.setEnabled(False)
        self.statusLabel.setText(
            self.tr('AccountInterface.GitHubApp.Requesting'))
        self.sessionStatusLabel.setText(
            self.tr('AccountInterface.GitHubApp.Requesting'))
        future = TaskExecutor.run(authService.requestDeviceCode)
        future.result.connect(self._deviceCodeReady)
        future.failed.connect(self._deviceLoginFailed)

    def _deviceCodeReady(self, session):
        if self._cancelEvent.is_set():
            return
        self._deviceSession = session
        self.deviceCodeLabel.setText(
            self.tr('AccountInterface.GitHubApp.Code', (session.user_code,)))
        self.deviceCodeLabel.show()
        self.copyCodeButton.setEnabled(True)
        self.statusLabel.setText(
            self.tr('AccountInterface.GitHubApp.Waiting'))
        self.sessionStatusLabel.setText(
            self.tr('AccountInterface.GitHubApp.Waiting'))
        self.copyDeviceCode()
        logAction('Log.Action.OpenLink', session.verification_uri)
        openUrl(session.verification_uri)
        future = TaskExecutor.run(
            authService.waitForDeviceAuthorization, session, self._cancelEvent)
        future.result.connect(self._githubLoginSucceeded)
        future.failed.connect(self._deviceLoginFailed)

    def copyDeviceCode(self):
        if self._deviceSession:
            QApplication.clipboard().setText(self._deviceSession.user_code)

    def _githubLoginSucceeded(self, authorization):
        if self._cancelEvent.is_set():
            return
        try:
            identity = authService.completeDeviceAuthorization(authorization)
        except Exception as error:
            self._deviceLoginFailed(error)
            return
        # Device Flow only authenticates the user.  The GitHub App still has
        # to be installed and granted access to the target repositories, so
        # take the user directly to the installation page after authorization.
        installation_url = authService.installationUrl()
        logAction('Log.Action.OpenLink', installation_url)
        openUrl(installation_url)
        self.connectButton.setEnabled(True)
        self.saveButton.setEnabled(True)
        self.copyCodeButton.setEnabled(False)
        self.deviceCodeLabel.hide()
        signalBus.userNameChanged.emit(identity.name)
        self.refreshStatus()
        InfoBar.success(
            self.tr('AccountInterface.LoginSuccess'),
            self.tr('AccountInterface.LoggedInGitHubApp', (identity.login,)),
            duration=2500,
            parent=self.window(),
        )
        logSucceeded('Log.Action.Login', identity.login)

    def login(self):
        """Sign in with a PAT from the advanced compatibility card."""
        logAction('Log.Action.Login', 'PAT')
        token = self.tokenEdit.text().strip()
        if not token:
            logCancelled('Log.Action.Login')
            return
        self.cancelDeviceFlow()
        logStarted('Log.Action.TokenValidation')
        self.saveButton.setEnabled(False)
        self.connectButton.setEnabled(False)
        future = TaskExecutor.run(self._validateToken, token)
        future.result.connect(
            lambda identity: self._patLoginSucceeded(token, identity))
        future.failed.connect(self._patLoginFailed)

    @staticmethod
    def _validateToken(token: str):
        user = getUserByToken(token)
        return user.login, (user.name or user.login)

    def _patLoginSucceeded(self, token: str, identity):
        login, user_name = identity
        logSucceeded('Log.Action.TokenValidation', login)
        try:
            result = authService.storeToken(token, AUTH_PAT, identity)
        except Exception as error:
            self._patLoginFailed(error)
            return
        signalBus.userNameChanged.emit(result.name)
        self.tokenEdit.clear()
        self.saveButton.setEnabled(True)
        self.connectButton.setEnabled(True)
        self.refreshStatus()
        InfoBar.success(
            self.tr('AccountInterface.LoginSuccess'),
            self.tr('AccountInterface.LoggedInPAT', (login,)),
            duration=2500,
            parent=self.window(),
        )
        logSucceeded('Log.Action.Login', login)

    def _deviceLoginFailed(self, error):
        error = unwrapFutureError(error)
        if isinstance(error, DeviceFlowCancelled) or self._cancelEvent.is_set():
            return
        logFailed('Log.Action.Login', error)
        self.connectButton.setEnabled(True)
        self.saveButton.setEnabled(True)
        InfoBar.error(
            self.tr('AccountInterface.LoginFailed'),
            str(error),
            duration=4500,
            parent=self.window(),
        )

    def _patLoginFailed(self, error):
        error = unwrapFutureError(error)
        logFailed('Log.Action.TokenValidation', error)
        logFailed('Log.Action.Login', error)
        self.saveButton.setEnabled(True)
        self.connectButton.setEnabled(True)
        InfoBar.error(
            self.tr('AccountInterface.LoginFailed'),
            str(error),
            duration=4500,
            parent=self.window(),
        )

    def cancelDeviceFlow(self, reset=True):
        self._cancelEvent.set()
        self._deviceSession = None
        if reset:
            self.deviceCodeLabel.hide()
            self.copyCodeButton.setEnabled(False)
            self.connectButton.setEnabled(True)
            self.saveButton.setEnabled(True)

    def logout(self):
        logAction('Log.Action.Logout')
        self.cancelDeviceFlow()
        authService.disconnect()
        signalBus.userNameChanged.emit('')
        getUserByToken.cache_clear()
        getUserLogin.cache_clear()
        getUserName.cache_clear()
        self.refreshStatus()
        InfoBar.success(
            self.tr('AccountInterface.LogoutSuccess'),
            '',
            duration=2000,
            parent=self.window(),
        )
        logSucceeded('Log.Action.Logout')
