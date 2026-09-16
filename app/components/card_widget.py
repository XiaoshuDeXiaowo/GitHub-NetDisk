# coding: utf-8
from PyQt5.QtCore import Qt, pyqtProperty
from PyQt5.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    IconWidget,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
    SubtitleLabel,
    ToolTipPosition,
)
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets.components.material import AcrylicToolTipFilter
from qfluentwidgets.common.overload import singledispatchmethod

from ..common.config import cfg
from ..common.event_logger import logAction, logCancelled, logChanged
from ..common.signal_bus import signalBus
from ..common.translator import translate


class LinkCard(CardWidget):
    """Compact dialog choice card with a trailing arrow."""

    @singledispatchmethod
    def __init__(self, parent: QWidget = None):
        super().__init__(parent=parent)
        self.hBoxLayout = QHBoxLayout(self)
        self.bodyLabel = BodyLabel(self)
        self.iconWidget = IconWidget(FIF.RIGHT_ARROW, self)
        self.iconWidget.setFixedSize(20, 20)
        self.hBoxLayout.addWidget(self.bodyLabel, 1, Qt.AlignVCenter)
        self.hBoxLayout.addWidget(self.iconWidget, 0, Qt.AlignVCenter)

    @__init__.register
    def _initWithText(self, text: str, parent: QWidget = None):
        self.__init__(parent=parent)
        self.setText(text)

    def setText(self, text: str):
        self.bodyLabel.setText(text)

    def setEnabled(self, enabled: bool):
        """Keep disabled choice cards visibly disabled as well as inert."""
        super().setEnabled(enabled)
        effect = self.graphicsEffect()
        if enabled:
            self.clearDisabledVisual()
            return
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(self)
            self.setGraphicsEffect(effect)
        # Keep the card readable while still making it clearly unavailable.
        effect.setOpacity(0.62)

    def clearDisabledVisual(self):
        """Detach the opacity effect before a dialog/widget is destroyed."""
        if isinstance(self.graphicsEffect(), QGraphicsOpacityEffect):
            self.setGraphicsEffect(None)

    def getText(self):
        return self.bodyLabel.text()

    text = pyqtProperty(str, getText, setText)


class HomeActionCard(CardWidget):
    """Large, responsive action used in the home interface quick-action row."""

    def __init__(self, icon, title, description, parent=None):
        super().__init__(parent=parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(108)
        self.setMinimumWidth(260)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(title)

        self.hBoxLayout = QHBoxLayout(self)
        self.textLayout = QVBoxLayout()
        self.iconWidget = IconWidget(icon, self)
        self.iconWidget.setFixedSize(32, 32)
        self.titleLabel = StrongBodyLabel(title, self)
        self.descriptionLabel = CaptionLabel(description, self)
        self.descriptionLabel.setWordWrap(True)
        self.arrowIcon = IconWidget(FIF.CHEVRON_RIGHT, self)
        self.arrowIcon.setFixedSize(16, 16)

        self.hBoxLayout.setContentsMargins(20, 16, 18, 16)
        self.hBoxLayout.setSpacing(14)
        self.hBoxLayout.addWidget(self.iconWidget, 0, Qt.AlignVCenter)
        self.hBoxLayout.addLayout(self.textLayout, 1)
        self.hBoxLayout.addWidget(self.arrowIcon, 0, Qt.AlignVCenter)
        self.textLayout.setSpacing(5)
        self.textLayout.addWidget(self.titleLabel)
        self.textLayout.addWidget(self.descriptionLabel)


class EmptyRepoCard(CardWidget):
    """Home-interface empty state; intentionally non-clickable."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(116)
        self.hBoxLayout = QHBoxLayout(self)
        self.textLayout = QVBoxLayout()
        self.iconWidget = IconWidget(FIF.INFO, self)
        self.iconWidget.setFixedSize(28, 28)
        self.titleLabel = StrongBodyLabel(translate('HomeInterface.EmptyReposTitle'), self)
        self.descriptionLabel = CaptionLabel(translate('HomeInterface.ReposTip.NoRepo'), self)
        self.descriptionLabel.setWordWrap(True)
        self.hBoxLayout.setContentsMargins(20, 18, 20, 18)
        self.hBoxLayout.setSpacing(14)
        self.hBoxLayout.addWidget(self.iconWidget, 0, Qt.AlignVCenter)
        self.hBoxLayout.addLayout(self.textLayout, 1)
        self.textLayout.addWidget(self.titleLabel)
        self.textLayout.addWidget(self.descriptionLabel)


class RepoCard(CardWidget):
    """Responsive recent-repository card with explicit browse/remove actions."""

    def __init__(self, title='', text='', parent=None):
        super().__init__(parent=parent)
        self.tr = translate
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumWidth(320)
        self.setFixedHeight(142)
        self.vBoxLayout = QVBoxLayout(self)
        self.headerLayout = QHBoxLayout()
        self.buttonLayout = QHBoxLayout()
        self.repoIcon = IconWidget(FIF.GITHUB, self)
        self.repoIcon.setFixedSize(26, 26)
        self.titleLabel = SubtitleLabel(title, self)
        self.titleLabel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.titleLabel.setToolTip(title)
        self.titleLabel.installEventFilter(
            AcrylicToolTipFilter(self.titleLabel, position=ToolTipPosition.TOP))
        self.textLabel = CaptionLabel(text, self)
        self.textLabel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.textLabel.setToolTip(text)
        self.textLabel.installEventFilter(
            AcrylicToolTipFilter(self.textLabel, position=ToolTipPosition.TOP))
        self.browseBtn = PrimaryPushButton(FIF.VIEW, self.tr('RepoCard.BrowseBtn'), self)
        self.removeBtn = PushButton(FIF.DELETE, self.tr('RepoCard.EditBtn'), self)
        self.browseBtn.setMinimumWidth(104)
        self.removeBtn.setMinimumWidth(96)
        self.browseBtn.setFixedHeight(34)
        self.removeBtn.setFixedHeight(34)

        self.vBoxLayout.setContentsMargins(18, 16, 18, 16)
        self.vBoxLayout.setSpacing(8)
        self.headerLayout.setSpacing(10)
        self.headerLayout.addWidget(self.repoIcon)
        self.headerLayout.addWidget(self.titleLabel, 1)
        self.buttonLayout.setContentsMargins(0, 4, 0, 0)
        self.buttonLayout.setSpacing(18)
        self.buttonLayout.addStretch(1)
        self.buttonLayout.addWidget(self.browseBtn)
        self.buttonLayout.addWidget(self.removeBtn)
        self.vBoxLayout.addLayout(self.headerLayout)
        self.vBoxLayout.addWidget(self.textLabel)
        self.vBoxLayout.addLayout(self.buttonLayout)
        self.setAccessibleName(text or title)

        self.browseBtn.clicked.connect(self.onBrowseClick)
        self.removeBtn.clicked.connect(self.onRemoveClick)

    def onBrowseClick(self):
        logAction('Log.Action.BrowseRepository', self.text)
        signalBus.browseRepo.emit(self.text)

    def onRemoveClick(self):
        logAction('Log.Action.Delete', self.text)
        repositories = list(cfg.get(cfg.quickAccessList))
        if self.text in repositories:
            repositories.remove(self.text)
            cfg.set(cfg.quickAccessList, repositories)
            signalBus.quickAccessChanged.emit()
            logChanged('Log.Action.QuickAccess', self.text)
        else:
            logCancelled('Log.Action.Delete', self.text)

    def setTitle(self, title: str):
        self.titleLabel.setText(title)
        self.titleLabel.setToolTip(title)

    def getTitle(self):
        return self.titleLabel.text()

    title = pyqtProperty(str, getTitle, setTitle)

    def setText(self, text: str):
        self.textLabel.setText(text)
        self.textLabel.setToolTip(text)

    def getText(self):
        return self.textLabel.text()

    text = pyqtProperty(str, getText, setText)
