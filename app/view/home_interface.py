# coding: utf-8
"""Responsive GitHub-NetDisk home interface."""
from getpass import getuser

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    AdaptiveFlowLayout,
    CaptionLabel,
    ScrollArea,
    StrongBodyLabel,
    SubtitleLabel,
    TitleLabel,
)
from qfluentwidgets import FluentIcon as FIF

from ..common.config import cfg
from ..common.icon import Icon
from ..common.event_logger import (
    logAction,
    logChanged,
    logInitialized,
    logReceived,
)
from ..common.signal_bus import signalBus
from ..common.style_sheet import StyleSheet
from ..common.translator import translate
from ..components.card_widget import EmptyRepoCard, HomeActionCard, RepoCard
from ..components.dialog import AddRepo
from ..service.auth_service import authService


class HomeInterface(ScrollArea):
    """Welcome, quick actions and a manually managed repository grid."""

    def __init__(self, parent=None, forced_username=None):
        super().__init__(parent=parent)
        self.tr = translate
        self._forcedUsername = str(forced_username or '').strip()
        self.scrollWidget = QWidget(self)
        self.vBoxLayout = QVBoxLayout(self.scrollWidget)
        self.quickWidget = QWidget(self.scrollWidget)
        self.quickLayout = AdaptiveFlowLayout(self.quickWidget, needAni=False)
        self.recentHeaderLayout = QHBoxLayout()
        self.cardsWidget = QWidget(self.scrollWidget)
        self.cardsLayout = AdaptiveFlowLayout(self.cardsWidget, needAni=False)

        self.titleLabel = TitleLabel(self.tr('HomeInterface.Home'), self.scrollWidget)
        user = self._displayUserName()
        self.subtitleLabel = SubtitleLabel(
            self.tr('HomeInterface.Subtitle', (user,)), self.scrollWidget)
        self.quickLabel = StrongBodyLabel(self.tr('HomeInterface.QuickActions'), self.scrollWidget)
        self.reposLabel = StrongBodyLabel(self.tr('HomeInterface.ReposTip'), self.scrollWidget)
        self.repoCountLabel = CaptionLabel(self.scrollWidget)

        self.addRepoCard = HomeActionCard(
            FIF.ADD,
            self.tr('HomeInterface.AddRepository'),
            self.tr('HomeInterface.AddRepositoryDescription'),
            self.quickWidget,
        )
        self.browseCard = HomeActionCard(
            Icon.REPO,
            self.tr('HomeInterface.BrowseRepository'),
            self.tr('HomeInterface.BrowseRepositoryDescription'),
            self.quickWidget,
        )

        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setObjectName('homeInterface')
        self.scrollWidget.setObjectName('scrollWidget')
        StyleSheet.FLUENT_INTERFACE.apply(self)

        self.vBoxLayout.setContentsMargins(36, 42, 36, 36)
        self.vBoxLayout.setSpacing(12)
        self.vBoxLayout.addWidget(self.titleLabel)
        self.vBoxLayout.addWidget(self.subtitleLabel)
        self.vBoxLayout.addSpacing(20)
        self.vBoxLayout.addWidget(self.quickLabel)
        self.vBoxLayout.addWidget(self.quickWidget)
        self.vBoxLayout.addSpacing(18)
        self.vBoxLayout.addLayout(self.recentHeaderLayout)
        self.vBoxLayout.addWidget(self.cardsWidget)
        self.vBoxLayout.addStretch(1)

        self.recentHeaderLayout.addWidget(self.reposLabel)
        self.recentHeaderLayout.addStretch(1)
        self.recentHeaderLayout.addWidget(self.repoCountLabel)
        for layout in (self.quickLayout, self.cardsLayout):
            layout.setContentsMargins(0, 4, 0, 4)
            layout.setHorizontalSpacing(12)
            layout.setVerticalSpacing(12)
            layout.setWidgetMinimumWidth(300)
            layout.setWidgetMaximumWidth(540)
        self.quickLayout.addWidget(self.addRepoCard)
        self.quickLayout.addWidget(self.browseCard)

        self.addRepoCard.clicked.connect(self.openAddRepo)
        self.browseCard.clicked.connect(self.openBrowser)
        signalBus.userNameChanged.connect(self.updateUserName)
        signalBus.addCardToQuickAccess.connect(self.addRepository)
        signalBus.quickAccessChanged.connect(self.refreshCards)
        self.refreshCards()
        logInitialized('Log.Action.HomeInterface')

    def updateUserName(self, user_name: str):
        user_name = self._displayUserName(user_name)
        self.subtitleLabel.setText(
            self.tr('HomeInterface.Subtitle', (user_name,)))
        logChanged('Log.Action.UserName', user_name, level='debug')

    def _displayUserName(self, user_name=''):
        if self._forcedUsername:
            return self._forcedUsername
        if authService.isAuthenticated():
            return str(user_name or '').strip() or cfg.get(cfg.usernameCache) or getuser()
        return getuser()

    def refreshCards(self):
        while self.cardsLayout.count():
            widget = self.cardsLayout.takeAt(0)
            if widget:
                widget.hide()
                widget.deleteLater()
        stored_repositories = list(cfg.get(cfg.quickAccessList))
        repositories = list(dict.fromkeys(
            repo.strip()
            for repo in stored_repositories
            if isinstance(repo, str) and repo.strip()
        ))[:20]
        if repositories != stored_repositories:
            cfg.set(cfg.quickAccessList, repositories)
        logChanged('Log.Action.RepositoryList', str(len(repositories)), level='debug')
        self.repoCountLabel.setText(
            self.tr('HomeInterface.RepoCount', (len(repositories),)))
        if not repositories:
            self.cardsLayout.addWidget(EmptyRepoCard(self.cardsWidget))
            return
        for repo in repositories:
            self.cardsLayout.addWidget(RepoCard(repo.split('/')[-1], repo, self.cardsWidget))

    def openAddRepo(self):
        logAction('Log.Action.AddRepository')
        AddRepo(self.window()).exec()

    def openBrowser(self):
        logAction('Log.Action.BrowseRepository', cfg.get(cfg.repoCache) or '/')
        signalBus.browseRepo.emit(cfg.get(cfg.repoCache) or '')

    def addRepository(self, repo: str):
        logReceived('Log.Action.QuickAccess', repo)
        if not repo:
            return
        repositories = list(cfg.get(cfg.quickAccessList))
        if repo in repositories:
            repositories.remove(repo)
        repositories.insert(0, repo)
        cfg.set(cfg.quickAccessList, repositories[:20])
        self.refreshCards()
        logChanged('Log.Action.QuickAccess', repo)
