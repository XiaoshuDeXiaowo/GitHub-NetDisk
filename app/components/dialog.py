# coding: utf-8
import json
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QFileDialog, QHBoxLayout, QStackedWidget, QWidget
from qfluentwidgets import (MessageBoxBase, SubtitleLabel, LineEdit, IndeterminateProgressRing,
                            BodyLabel, CheckBox, ComboBox, IconWidget, InfoBar, PushButton)
from qfluentwidgets import FluentIcon as FIF
from pyqt5_concurrent.TaskExecutor import TaskExecutor

from ..common.translator import translate
from ..common.config import cfg
from ..common.event_logger import (
    exceptionDetail,
    logAction,
    logCancelled,
    logFailed,
    logInitialized,
    logStarted,
    logSucceeded,
)
from ..common.utils import unwrapFutureError
from ..service.github_service import getRepo, getUserByToken
from ..service.auth_service import authService
from ..common.signal_bus import signalBus
from ..common.url_scheme import NewTaskRequest, default_filename

from ..components.card_widget import LinkCard


class AddTaskDialog(MessageBoxBase):
    """Collect an upload/download request without starting it immediately."""

    def __init__(self, request=None, parent=None):
        super().__init__(parent=parent)
        self.tr = translate
        self.titleLabel = SubtitleLabel(self.tr('AddTask.title'), self)
        self.directionLabel = BodyLabel(self.tr('AddTask.Direction'), self)
        self.directionBox = ComboBox(self)
        self.directionBox.addItems([
            self.tr('TaskInterface.Download'),
            self.tr('TaskInterface.Upload'),
        ])
        self.targetLabel = BodyLabel(self.tr('AddTask.TargetType'), self)
        self.targetBox = ComboBox(self)
        self.targetBox.addItems([
            self.tr('AddTask.Repository'),
            self.tr('AddTask.URL'),
        ])
        self.uriLabel = BodyLabel(self.tr('AddTask.URI'), self)
        self.uriEdit = LineEdit(self)
        self.uriEdit.setClearButtonEnabled(True)
        self.fileLabel = BodyLabel(self.tr('AddTask.Filename'), self)
        self.fileLayout = QHBoxLayout()
        self.filenameEdit = LineEdit(self)
        self.filenameEdit.setClearButtonEnabled(True)
        self.chooseFileButton = PushButton(
            FIF.FOLDER, self.tr('AddTask.ChooseFile'), self)
        self.fileLayout.addWidget(self.filenameEdit, 1)
        self.fileLayout.addWidget(self.chooseFileButton)

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.directionLabel)
        self.viewLayout.addWidget(self.directionBox)
        self.viewLayout.addWidget(self.targetLabel)
        self.viewLayout.addWidget(self.targetBox)
        self.viewLayout.addWidget(self.uriLabel)
        self.viewLayout.addWidget(self.uriEdit)
        self.viewLayout.addWidget(self.fileLabel)
        self.viewLayout.addLayout(self.fileLayout)
        self.yesButton.setText(self.tr('AddTask.Add'))
        self.cancelButton.setText(self.tr('AddTask.Cancel'))
        self.widget.setMinimumWidth(520)

        self.directionBox.currentIndexChanged.connect(self._updateState)
        self.targetBox.currentIndexChanged.connect(self._updateState)
        self.uriEdit.textChanged.connect(self._updateState)
        self.filenameEdit.textChanged.connect(self._updateState)
        self.chooseFileButton.clicked.connect(self._chooseFile)
        self.rejected.connect(lambda: logCancelled('Log.Action.Task'))
        if request:
            self.setRequest(request)
        self._updateState()

    @property
    def request(self):
        return NewTaskRequest(
            'upload' if self.directionBox.currentIndex() == 1 else 'download',
            'url' if self.targetBox.currentIndex() == 1 else 'repo',
            self.uriEdit.text().strip(),
            self.filenameEdit.text().strip(),
        )

    def setRequest(self, request):
        self.directionBox.setCurrentIndex(1 if request.direction == 'upload' else 0)
        self.targetBox.setCurrentIndex(1 if request.target_type == 'url' else 0)
        self.uriEdit.setText(request.uri)
        self.filenameEdit.setText(
            request.filename or default_filename(request.uri, request.direction))

    def _updateState(self):
        upload = self.directionBox.currentIndex() == 1
        url_target = self.targetBox.currentIndex() == 1
        self.uriEdit.setPlaceholderText(self.tr(
            'AddTask.URLPlaceholder' if url_target else 'AddTask.RepoPlaceholder'))
        self.fileLabel.setText(self.tr(
            'AddTask.UploadFile' if upload else 'AddTask.Filename'))
        self.chooseFileButton.setVisible(upload)
        valid = bool(self.uriEdit.text().strip() and self.filenameEdit.text().strip())
        self.yesButton.setEnabled(valid)

    def _chooseFile(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr('AddTask.ChooseFile'), self.filenameEdit.text())
        if path:
            self.filenameEdit.setText(path)


class AddRepo(MessageBoxBase):
    def __init__(self, parent = None):
        super().__init__(parent=parent)
        self.tr = translate
        self.titleLabel = SubtitleLabel(self.tr('AddRepo.title'))

        self.createRepoCard = LinkCard(self.tr('AddRepo.CreateRepo'), self)
        self.addExistRepoCard = LinkCard(self.tr('AddRepo.AddExistRepo'), self)
        canCreate = self.canCreateRepository()
        self.createRepoCard.setEnabled(canCreate)
        self.createRepoCard.setToolTip(
            '' if canCreate else self.tr('CreateRepo.LoginRequired'))

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.createRepoCard)
        self.viewLayout.addWidget(self.addExistRepoCard)

        self.hideYesButton()

        self.cancelButton.setText(self.tr('AddRepo.CancelButton'))
        self.rejected.connect(lambda: logCancelled('Log.Action.AddRepository'))

        self.createRepoCard.clicked.connect(self.onCreateRepo)
        self.addExistRepoCard.clicked.connect(self.onAddExistRepo)

        self.widget.setMinimumWidth(300)
        logInitialized('Log.Action.AddRepository')

    def _clearDisabledCardEffect(self):
        self.createRepoCard.clearDisabledVisual()

    def reject(self):
        # Remove the effect before QDialog starts its close/overlay sequence.
        self._clearDisabledCardEffect()
        super().reject()

    def closeEvent(self, event):
        # Covers window-manager close and programmatic close().
        self._clearDisabledCardEffect()
        super().closeEvent(event)

    @staticmethod
    def canCreateRepository():
        return authService.isAuthenticated()

    def onCreateRepo(self):
        if not self.canCreateRepository():
            logCancelled('Log.Action.CreateRepository')
            return
        logAction('Log.Action.CreateRepository')
        w = CreateRepo(self.parent())
        QTimer.singleShot(50, self.close)
        w.exec()

    def onAddExistRepo(self):
        logAction('Log.Action.AddExistingRepository')
        w = AddExistRepo(self.parent())
        QTimer.singleShot(50, self.close)
        w.exec()

class CreateRepo(MessageBoxBase):
    def __init__(self, parent = None):
        super().__init__(parent=parent)
        self.tr = translate
        self.titleLabel = SubtitleLabel(self.tr('CreateRepo.title'), self)
        self._creating = False
        
        self.nameLineEdit = LineEdit(self)
        self.nameLineEdit.setPlaceholderText(self.tr('CreateRepo.NameLineEdit.placeholder'))
        self.nameLineEdit.setClearButtonEnabled(True)

        self.isPrivateBtn = CheckBox(
            self.tr('CreateRepo.IsPrivateBtn.onText'), self)

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.nameLineEdit)
        self.viewLayout.addWidget(self.isPrivateBtn)

        self.yesButton.setText(self.tr('CreateRepo.YesButton.text'))
        self.cancelButton.setText(self.tr('CreateRepo.CancelButton.text'))

        self.rejected.connect(lambda: logCancelled('Log.Action.CreateRepository'))

        self.widget.setMinimumWidth(350)
        logInitialized('Log.Action.CreateRepository')

    def validate(self):
        self.onAccept()
        return False

    def onAccept(self):
        if self._creating:
            return
        token = authService.accessToken()
        if not token or not self.nameLineEdit.text().strip():
            logCancelled('Log.Action.CreateRepository')
            return
        repo_name_input = self.nameLineEdit.text().strip()
        logStarted('Log.Action.CreateRepository', repo_name_input)
        self._setCreating(True)
        future = TaskExecutor.run(
            self._createRepository,
            token,
            repo_name_input,
            self.isPrivateBtn.isChecked(),
        )
        future.result.connect(self._onCreateSucceeded)
        future.failed.connect(self._onCreateFailed)

    @staticmethod
    def _createRepository(token, repo_name_input, private):
        u = getUserByToken(token)
        u.create_repo(
            name=repo_name_input,
            description='Repo for GitHub-NetDisk (https://github.com/XiaoshuDeXiaowo/GitHub-NetDisk).',
            private=private,
            has_wiki=False,
            has_projects=False,
            auto_init=False
        )
        repo = u.get_repo(repo_name_input)
        repo.create_file(
            path='netdisk.json',
            message='Initial commit (GitHub-NetDisk)',
            content=json.dumps({'version': 1, 'files': {}})
        )
        return repo.full_name

    def _onCreateSucceeded(self, repo_name):
        try:
            quickAccessList = list(cfg.get(cfg.quickAccessList))
            logSucceeded('Log.Action.CreateRepository', repo_name)
            if repo_name in quickAccessList:
                logCancelled('Log.Action.QuickAccess', repo_name)
            else:
                quickAccessList.append(repo_name)
                cfg.set(cfg.quickAccessList, quickAccessList)
                signalBus.addCardToQuickAccess.emit(repo_name)
            self.accept()
        finally:
            self._setCreating(False)

    def _onCreateFailed(self, error):
        error = unwrapFutureError(error)
        repo_name_input = self.nameLineEdit.text().strip()
        logFailed(
            'Log.Action.CreateRepository',
            exceptionDetail(error, repo_name_input),
        )
        self._setCreating(False)
        InfoBar.error(
            self.tr('CreateRepo.Failed'),
            str(error),
            duration=6000,
            parent=self,
        )

    def _setCreating(self, creating):
        self._creating = bool(creating)
        self.yesButton.setEnabled(not creating)
        self.cancelButton.setEnabled(not creating)
        self.nameLineEdit.setEnabled(not creating)
        self.isPrivateBtn.setEnabled(not creating)

class AddExistRepo(MessageBoxBase):
    def __init__(self, parent = None):
        super().__init__(parent=parent)
        self.tr = translate
        self.titleLabel = SubtitleLabel(self.tr('AddExistRepo.title'), self)
        self._checkTimer = QTimer(self)
        self._checkTimer.setSingleShot(True)
        self._checkTimer.setInterval(450)
        self._checkTimer.timeout.connect(self._checkCurrentRepo)

        self.hBoxLayout = QHBoxLayout()
        self.nameLineEdit = LineEdit(self)
        self.nameLineEdit.setPlaceholderText(self.tr('AddExistRepo.NameLineEdit.placeholderText'))
        self.nameLineEdit.setClearButtonEnabled(True)

        self.stackedWidget = QStackedWidget(self)
        self.stackedWidget.addWidget(QWidget())
        ring = IndeterminateProgressRing()
        ring.setFixedSize(32, 32)
        self.stackedWidget.addWidget(ring)
        acceptIcon = IconWidget(
            FIF.ACCEPT.colored(QColor('#0F7B0F'), QColor('#6CCB5F')))
        acceptIcon.setFixedSize(32, 32)
        self.stackedWidget.addWidget(acceptIcon)
        cancelIcon = IconWidget(
            FIF.CLOSE.colored(QColor('#C42B1C'), QColor('#FF99A4')))
        cancelIcon.setFixedSize(32, 32)
        self.stackedWidget.addWidget(cancelIcon)
        self.stackedWidget.setFixedSize(32, 32)
        self.stackedWidget.setCurrentIndex(0)

        self.hBoxLayout.addWidget(self.nameLineEdit)
        self.hBoxLayout.addWidget(self.stackedWidget)
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addLayout(self.hBoxLayout)

        self.yesButton.setEnabled(False)
        self.yesButton.setText(self.tr('AddExistRepo.YesButton'))
        self.cancelButton.setText(self.tr('AddExistRepo.CancelButton'))

        self.nameLineEdit.textChanged.connect(self.onNameChanged)
        self.accepted.connect(self.onAccept)
        self.rejected.connect(lambda: logCancelled('Log.Action.AddExistingRepository'))

        self.widget.setMinimumWidth(400)
        logInitialized('Log.Action.AddExistingRepository')
        
    def onNameChanged(self, text):
        self._checkTimer.stop()
        if not text.strip():
            self.stackedWidget.setCurrentIndex(0)
            self.yesButton.setEnabled(False)
            return
        self.stackedWidget.setCurrentIndex(1)
        self.yesButton.setEnabled(False)
        # Avoid a GitHub API request for every keystroke.  The current value
        # is captured when the timer fires, and the result callback still
        # verifies that the user has not edited the field in the meantime.
        self._checkTimer.start()

    def _checkCurrentRepo(self):
        value = self.nameLineEdit.text().strip()
        if not value:
            self.stackedWidget.setCurrentIndex(0)
            self.yesButton.setEnabled(False)
            return
        logStarted('Log.Action.Repository', value, level='debug')
        future = TaskExecutor.run(self.isRepoExists, value)
        future.result.connect(lambda r, checked=value: self._onRepoChecked(checked, r))
        future.failed.connect(
            lambda error, checked=value: self._onRepoCheckFailed(checked, error))

    def _onRepoCheckFailed(self, value: str, error):
        if value != self.nameLineEdit.text().strip():
            return
        self.stackedWidget.setCurrentIndex(3)
        self.yesButton.setEnabled(False)
        logFailed(
            'Log.Action.Repository',
            exceptionDetail(unwrapFutureError(error), value),
            level='debug',
        )

    def _onRepoChecked(self, value: str, exists: bool):
        if value != self.nameLineEdit.text().strip():
            return
        self.stackedWidget.setCurrentIndex(2 if exists else 3)
        self.yesButton.setEnabled(exists)
        if exists:
            logSucceeded('Log.Action.Repository', value, level='debug')
        else:
            logFailed('Log.Action.Repository', value, level='debug')

    def isRepoExists(self, repo: str):
        if not repo:
            return False
        target = getRepo(repo, authService.accessToken(), False)
        if not target:
            return False
        try:
            target.get_contents('netdisk.json', ref=target.default_branch)
            return True
        except Exception as error:
            logFailed(
                'Log.Action.Repository',
                exceptionDetail(error, repo),
                level='debug',
            )
            return False
    
    def onAccept(self):
        # check if the repo exists
        repo = self.nameLineEdit.text().strip()
        logStarted('Log.Action.AddExistingRepository', repo)
        if not self.isRepoExists(repo):
            logFailed('Log.Action.AddExistingRepository', repo)
            return
        repo_obj = getRepo(repo, authService.accessToken())
        if not repo_obj:
            logFailed('Log.Action.AddExistingRepository', repo)
            return
        repo = repo_obj.full_name
        
        # update config
        quickAccessList = list(cfg.get(cfg.quickAccessList))
        if repo in quickAccessList:
            logCancelled('Log.Action.AddExistingRepository', repo)
            return
        quickAccessList.append(repo)
        cfg.set(cfg.quickAccessList, quickAccessList)

        signalBus.addCardToQuickAccess.emit(repo)
        logSucceeded('Log.Action.AddExistingRepository', repo)
