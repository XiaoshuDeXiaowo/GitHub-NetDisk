# coding: utf-8
import os

from PyQt5.QtCore import pyqtProperty, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QFileDialog,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from loguru import logger
from pyqt5_concurrent.TaskExecutor import TaskExecutor
from qfluentwidgets import (
    Action,
    SimpleCardWidget,
    IconWidget,
    StrongBodyLabel,
    CaptionLabel,
    IndeterminateProgressRing,
    PrimaryPushButton,
    PrimarySplitPushButton,
    PushButton,
    RoundMenu,
    HorizontalSeparator,
    ToolTipPosition,
)
from qfluentwidgets import themeColor, setThemeColor, FluentThemeColor
from qfluentwidgets import FluentIcon as FIF

from ..common.config import cfg
from ..common.event_logger import logAction, logCancelled, logChanged, logSelected, logSucceeded
from ..service.netdisk_service import MAX_ASSET_SIZE, netdiskService
from ..common.signal_bus import signalBus
from ..common.translator import translate
from ..service.github_service import hasWriteAccess
from ..service.auth_service import authService
from ..common.utils import getFileTypeIcon, getFileTypeName, getFolderTypeIcon, getFolderTypeName
from .tool_tip import DisabledFriendlyAcrylicToolTipFilter


class FileToolBar(QWidget):
    def __init__(self, parent = None):
        super().__init__(parent=parent)
        self.tr = translate
        self._currentFileName = ''
        self.vBoxLayout = QVBoxLayout(self)

        self.downloadBtn = PrimarySplitPushButton(
            FIF.DOWN, self.tr('FileToolBar.Download'), self)
        self.downloadBtn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.downloadBtn.button.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.downloadBtn.hBoxLayout.setAlignment(
            self.downloadBtn.button, Qt.Alignment())
        self.downloadBtn.hBoxLayout.setStretch(0, 1)
        self.downloadBtn.hBoxLayout.setStretch(1, 0)
        self.saveAsAction = Action(FIF.SAVE_AS, self.tr('FileToolBar.SaveAs'))
        menu = RoundMenu(parent=self)
        menu.addAction(self.saveAsAction)
        self.downloadBtn.setFlyout(menu)
        self.copyLinkBtn = PushButton(FIF.SEND, self.tr('OpsBar.CopyLink'), self)
        self.copyDirectLinkBtn = PushButton(
            FIF.COPY, self.tr('OpsBar.CopyDirectLink'), self)
        self.copyLinkBtn.setToolTip(self.tr('OpsBar.CopyLink.ToolTip'))
        self.copyDirectLinkBtn.setToolTip(
            self.tr('OpsBar.CopyDirectLink.ToolTip'))
        self.copyLinkBtn.installEventFilter(DisabledFriendlyAcrylicToolTipFilter(
            self.copyLinkBtn, position=ToolTipPosition.TOP))
        self.copyDirectLinkBtn.installEventFilter(DisabledFriendlyAcrylicToolTipFilter(
            self.copyDirectLinkBtn, position=ToolTipPosition.TOP))

        self.separator1 = HorizontalSeparator(self)

        self.deleteBtn = PushButton(FIF.DELETE, self.tr('FileToolBar.Delete'), self)

        self.vBoxLayout.addWidget(self.downloadBtn)
        self.vBoxLayout.addWidget(self.copyLinkBtn)
        self.vBoxLayout.addWidget(self.copyDirectLinkBtn)
        self.vBoxLayout.addWidget(self.separator1)
        self.vBoxLayout.addWidget(self.deleteBtn)
        self.vBoxLayout.setAlignment(Qt.AlignTop)

        self.downloadBtn.clicked.connect(self.onDownloadBtn)
        self.saveAsAction.triggered.connect(self.onSaveAs)
        self.copyLinkBtn.clicked.connect(lambda: signalBus.copyLinkSig.emit(False))
        self.copyDirectLinkBtn.clicked.connect(
            lambda: signalBus.copyLinkSig.emit(True))
        self.deleteBtn.clicked.connect(self.onDeleteBtn)

    def onRepoChanged(self, repo: str):
        logChanged('Log.Action.Repository', repo, level='debug')
        self.deleteBtn.setEnabled(hasWriteAccess(repo, authService.accessToken()))

    def onDownloadBtn(self):
        logAction('Log.Action.FileDownload')
        signalBus.downloadSig.emit()

    def onSaveAs(self):
        logAction('Log.Action.FileDownload', self.tr('FileToolBar.SaveAs'))
        filename = self.currentFileName()
        initial_path = (
            os.path.join(cfg.get(cfg.saveFolder), filename)
            if filename else cfg.get(cfg.saveFolder)
        )
        path, _ = QFileDialog.getSaveFileName(
            self.window(),
            self.tr('FileToolBar.SaveAs'),
            initial_path,
        )
        if path:
            logSelected('Log.Action.SaveFolder', path)
            signalBus.downloadAsSig.emit(path)
        else:
            logCancelled('Log.Action.FileDownload')

    def onDeleteBtn(self):
        logAction('Log.Action.Delete')
        signalBus.deleteSig.emit()

    def setCurrentFileName(self, file_name):
        self._currentFileName = str(file_name or '')

    def currentFileName(self):
        return self._currentFileName


class RepoToolBar(QWidget):
    def __init__(self, parent = None):
        super().__init__(parent=parent)
        self.tr = translate
        self.vBoxLayout = QVBoxLayout(self)

        self.addFileBtn = PrimaryPushButton(FIF.ADD_TO, self.tr('DirToolBar.AddFile'), self)

        self.vBoxLayout.addWidget(self.addFileBtn)
        self.vBoxLayout.setAlignment(Qt.AlignTop)

        self.addFileBtn.clicked.connect(self.onAddFileBtn)

    def onRepoChanged(self, repo: str):
        logChanged('Log.Action.Repository', repo, level='debug')
        self.addFileBtn.setEnabled(hasWriteAccess(repo, authService.accessToken()))

    def onAddFileBtn(self):
        logAction('Log.Action.FileUpload')
        dialog = QFileDialog(self.window(), self.tr('OpsBar.SelectFilesToUpload'))
        dialog.setFileMode(QFileDialog.ExistingFiles)
        if dialog.exec():
            paths = dialog.selectedFiles()
            logSelected('Log.Action.FileSelection', str(len(paths)))
            signalBus.uploadFilesSig.emit(paths)
        else:
            logCancelled('Log.Action.FileSelection')


class DirToolBar(QWidget):
    def __init__(self, parent = None):
        super().__init__(parent=parent)
        self.tr = translate
        self.vBoxLayout = QVBoxLayout(self)

        self.addFileBtn = PrimaryPushButton(FIF.ADD_TO, self.tr('DirToolBar.AddFile'), self)

        self.separator1 = HorizontalSeparator(self)

        self.deleteBtn = PushButton(FIF.DELETE, self.tr('DirToolBar.Delete'), self)

        self.vBoxLayout.addWidget(self.addFileBtn)
        self.vBoxLayout.addWidget(self.separator1)
        self.vBoxLayout.addWidget(self.deleteBtn)
        self.vBoxLayout.setAlignment(Qt.AlignTop)

        self.addFileBtn.clicked.connect(self.onAddFileBtn)
        self.deleteBtn.clicked.connect(self.onDeleteBtn)

    def onRepoChanged(self, repo: str):
        logChanged('Log.Action.Repository', repo, level='debug')
        self.addFileBtn.setEnabled(hasWriteAccess(repo, authService.accessToken()))
        self.deleteBtn.setEnabled(hasWriteAccess(repo, authService.accessToken()))

    def onAddFileBtn(self):
        logAction('Log.Action.FileUpload')
        dialog = QFileDialog(self.window(), self.tr('OpsBar.SelectFilesToUpload'))
        dialog.setFileMode(QFileDialog.ExistingFiles)
        if dialog.exec():
            paths = dialog.selectedFiles()
            logSelected('Log.Action.FileSelection', str(len(paths)))
            signalBus.uploadFilesSig.emit(paths)
        else:
            logCancelled('Log.Action.FileSelection')

    def onDeleteBtn(self):
        logAction('Log.Action.Delete')
        signalBus.deleteSig.emit()


class FileInfoCard(SimpleCardWidget):

    def __init__(self, parent = None):
        super().__init__(parent=parent)
        self.tr = translate
        self._netdisk = netdiskService
        self._path = ''
        self.vBoxLayout = QVBoxLayout(self)

        self.iconWidget = IconWidget(self)
        self.iconWidget.setFixedSize(64, 64)

        self.titleLabel = StrongBodyLabel(self)
        self.titleLabel.setWordWrap(True)
        self.titleLabel.setMinimumWidth(0)
        self.titleLabel.setSizePolicy(
            QSizePolicy.Ignored, QSizePolicy.Preferred)

        self.typeLabel = CaptionLabel(self)
        self.typeLabel.setTextColor('#6d6d6d', '#dedede')
        self.typeLabel.setWordWrap(True)
        self.typeLabel.setMinimumWidth(0)
        self.typeLabel.setSizePolicy(
            QSizePolicy.Ignored, QSizePolicy.Preferred)

        self.ring = IndeterminateProgressRing(self)
        self.ring.hide()

        self.toolBarStackedWidget = QStackedWidget(self)
        self.repoToolBar = RepoToolBar(self)
        self.toolBarStackedWidget.addWidget(self.repoToolBar)  # 0: RepoToolBar
        self.fileToolBar = FileToolBar(self)
        self.toolBarStackedWidget.addWidget(self.fileToolBar)  # 1: FileToolBar
        self.dirToolBar = DirToolBar(self)
        self.toolBarStackedWidget.addWidget(self.dirToolBar)   # 2: DirToolBar
        self.toolBarStackedWidget.addWidget(QWidget(self))     # 3: Empty QWidget
        self.toolBarStackedWidget.setCurrentIndex(3)

        self.vBoxLayout.addWidget(self.iconWidget)
        self.vBoxLayout.addWidget(self.titleLabel)
        self.vBoxLayout.addWidget(self.typeLabel)
        self.vBoxLayout.addWidget(self.toolBarStackedWidget)
        self.vBoxLayout.setAlignment(Qt.AlignTop)
        self.vBoxLayout.setContentsMargins(20, 20, 20, 20)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, 'ring'):
            x = self.width() // 2 - self.ring.width() // 2
            y = self.height() // 2 - self.ring.height() // 2
            self.ring.move(x, y)

        # Fullscreen changes the splitter geometry temporarily.  Persisting
        # that transient width makes the card take up most of the splitter on
        # the next launch, even though the user never resized it normally.
        window = self.window()
        is_fullscreen = bool(
            window is not None
            and callable(getattr(window, 'isFullScreen', None))
            and window.isFullScreen()
        )
        if is_fullscreen:
            return
        cfg.set(cfg.fileCardWidth, self.width())

    def currentFileName(self):
        return self.titleLabel.text() if self._path else ''

    @property
    def path(self):
        return self._path

    @path.setter
    def path(self, path):
        assert self.repo, 'Please set a repo first.'

        self._path = path
        if self._netdisk.isFile(path):
            fileName = path.strip('/').split('/')[-1]
            self.iconWidget.setIcon(getFileTypeIcon(fileName))
            self.titleLabel.setText(fileName)
            self.typeLabel.setText(getFileTypeName(fileName))
            self.fileToolBar.setCurrentFileName(fileName)
            self.toolBarStackedWidget.setCurrentIndex(1)
            metadata = self._netdisk.getContent(path)
            assets = metadata.get(':assets') or [fileName]
            self.fileToolBar.copyDirectLinkBtn.setEnabled(
                int(metadata.get(':size', 0) or 0) < MAX_ASSET_SIZE
                and len(assets) == 1)
        else:
            self.iconWidget.setIcon(getFolderTypeIcon())
            self.titleLabel.setText(path.strip('/').split('/')[-1])
            self.typeLabel.setText(getFolderTypeName())
            self.fileToolBar.copyDirectLinkBtn.setEnabled(False)
            self.toolBarStackedWidget.setCurrentIndex(2)

    def _onLoadFinished(self, f):
        self.ring.hide()
        logSucceeded('Log.Action.Repository', self.getRepo(), level='debug')

    def setRepo(self, repo: str) -> None:
        """ set the model's repo

        Parameters
        ----------
        repo: str
            repo
        """
        self.iconWidget.setIcon(getFolderTypeIcon())
        self.titleLabel.setText(self.tr('FileInfoCard.Repo', (repo,)))

        if hasattr(self.toolBarStackedWidget.currentWidget(), 'onRepoChanged'):
            self.toolBarStackedWidget.currentWidget().onRepoChanged(repo)

    def getRepo(self) -> str:
        """ returns the model's repo """
        return self._netdisk.getRepo()

    repo = pyqtProperty(str, getRepo, setRepo)

    def setBranch(self, branch: str) -> None:
        """ set the model's branch

        Parameters
        ----------
        branch: str
            branch
        """
        self.iconWidget.setIcon(getFolderTypeIcon())
        self.titleLabel.setText(self.tr('FileInfoCard.Repo', (self.repo,)))
        self.typeLabel.setText(self.tr('FileInfoCard.Branch', (branch,)))
        self.toolBarStackedWidget.setCurrentIndex(0)

    def getBranch(self) -> str:
        """ returns the model's branch """
        return self._netdisk.getBranch()

    branch = pyqtProperty(str, getBranch, setBranch)

    def showRepository(self, repo: str, branch: str):
        """Update the summary after the tree model has loaded the repository."""
        self._path = ''
        self.iconWidget.setIcon(getFolderTypeIcon())
        self.titleLabel.setText(self.tr('FileInfoCard.Repo', (repo,)))
        self.typeLabel.setText(self.tr('FileInfoCard.Branch', (branch,)))
        self.toolBarStackedWidget.setCurrentIndex(0)
        # The file toolbar may still hold enabled state from the previous
        # selection even though it is now hidden.  Reset the direct-link
        # action so a subsequent refresh cannot expose stale file controls.
        self.fileToolBar.copyDirectLinkBtn.setEnabled(False)
        self.repoToolBar.onRepoChanged(repo)
        self.fileToolBar.onRepoChanged(repo)
        self.dirToolBar.onRepoChanged(repo)

    def clearRepository(self):
        """Show a neutral empty state after an initial repository load fails."""
        self._path = ''
        self.iconWidget.setIcon(QIcon())
        self.titleLabel.clear()
        self.typeLabel.clear()
        self.toolBarStackedWidget.setCurrentIndex(3)
        self.fileToolBar.copyDirectLinkBtn.setEnabled(False)
