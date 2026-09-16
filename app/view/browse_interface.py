# coding: utf-8
"""Repository browser and file-operation coordinator."""
import os
import posixpath
from urllib.parse import urlsplit

import requests

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QSplitter, QVBoxLayout, QWidget
from pyqt5_concurrent.TaskExecutor import TaskExecutor
from qfluentwidgets import ComboBox, InfoBar, LineEdit, PrimaryPushButton, TitleLabel

from ..common.config import cfg
from ..common.event_logger import (
    logAction,
    logCancelled,
    logChanged,
    logFailed,
    logInitialized,
    logReceived,
    logSelected,
    logStarted,
    logSucceeded,
)
from ..service.github_service import (getFastestGithubMirror, getRepoBranches,
                                   githubProxyUrl, hasWriteAccess)
from ..service.auth_service import authService
from ..common.icon import Icon
from ..service.netdisk_service import (
    MAX_ASSET_SIZE,
    NetdiskService,
    _TransferCancelled,
    createUploadResumeData,
    netdiskService,
    sourceMatchesResumeData,
)
from ..common.signal_bus import signalBus
from ..service.transfer_task_service import (
    TransferDirection,
    transferTaskService,
)
from ..common.translator import translate
from ..common.transfer_utils import isTransferCancelledError
from ..common.utils import getUniqueFilePath, unwrapFutureError
from ..common.url_scheme import (redirect_link, release_download_link,
                                 split_netdisk_uri)
from ..components.file_info_card import FileInfoCard
from ..components.netdisk_tree_view import NetdiskTreeView
from ..components.ops_bar import OpsBar


class BrowseInterface(QWidget):
    """Browse one GitHub-NetDisk repository at a time."""

    MAX_SPLITTER_WIDTH = 1200

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.tr = translate
        self.setObjectName('browseInterface')
        self._busy = False
        self._requestedBranch = ''
        self._queuedBrowse = None
        self._pendingTaskRequest = None
        self._openingRepository = ''

        self.vBoxLayout = QVBoxLayout(self)
        self.repoLayout = QHBoxLayout()
        self.titleLabel = TitleLabel(self.tr('BrowseInterface.Browse'), self)
        self.repoEdit = LineEdit(self)
        self.repoEdit.setClearButtonEnabled(True)
        self.repoEdit.setPlaceholderText(self.tr('BrowseInterface.RepoEdit.placeholder'))
        self.goButton = PrimaryPushButton(self.tr('BrowseInterface.Go'), self)
        self.branchSelector = ComboBox(self)
        self.branchSelector.setIcon(Icon.BRANCH.qicon())
        self.branchSelector.setPlaceholderText(self.tr('BrowseInterface.BranchSelector.placeholder'))
        self.opsBar = OpsBar(self)
        self.opsBar.setEnabled(False)
        self.vBoxLayout.setContentsMargins(36, 42, 36, 30)
        self.vBoxLayout.setSpacing(12)

        self.treeView = NetdiskTreeView(self)
        self.fileInfoCard = FileInfoCard(self)
        self.splitter = QSplitter(Qt.Horizontal, self)
        self.splitter.addWidget(self.treeView)
        self.splitter.addWidget(self.fileInfoCard)
        self.splitter.setMaximumWidth(self.MAX_SPLITTER_WIDTH)
        self.splitter.setSizes(self._restoredSplitterSizes())
        self.splitter.setChildrenCollapsible(False)

        self.repoLayout.addWidget(self.repoEdit, 1)
        self.repoLayout.addWidget(self.goButton)
        self.repoLayout.addWidget(self.branchSelector)
        self.vBoxLayout.addWidget(self.titleLabel)
        self.vBoxLayout.addLayout(self.repoLayout)
        self.vBoxLayout.addWidget(self.opsBar)
        self.vBoxLayout.addWidget(self.splitter, 1)

        self.goButton.clicked.connect(self.openRepository)
        self.repoEdit.returnPressed.connect(self.openRepository)
        self.branchSelector.currentTextChanged.connect(self.onBranchChanged)
        self.treeView.repoLoaded.connect(self.onRepoLoaded)
        self.treeView.branchLoaded.connect(self.onBranchLoaded)
        self.treeView.reloadFinished.connect(self._onTreeReloaded)
        self.treeView.loadError.connect(self.onLoadError)
        self.treeView.selectionModel().currentChanged.connect(self.onSelectionChanged)
        signalBus.browseRepo.connect(self.browse)
        signalBus.createNewFolderSig.connect(self.treeView.onCreateNewFolder)
        signalBus.uploadFilesSig.connect(self.uploadFiles)
        signalBus.downloadSig.connect(self.downloadSelected)
        signalBus.downloadAsSig.connect(self.downloadSelectedAs)
        signalBus.renameSig.connect(self.renameSelected)
        signalBus.deleteSig.connect(self.deleteSelected)
        signalBus.refreshSig.connect(self.treeView.reload)
        signalBus.newTaskRequestedSig.connect(self.addTaskRequest)
        signalBus.resumeTaskSig.connect(self._resumeTransfer)
        signalBus.pauseTaskSig.connect(self._pauseTransfer)
        signalBus.cancelTaskSig.connect(self._cancelTransfer)
        signalBus.copyLinkSig.connect(self.copySelectedLink)
        logInitialized('Log.Action.BrowseRepository')

    def _restoredSplitterSizes(self):
        """Return saved splitter sizes without restoring a stale fullscreen width."""
        tree_width = max(1, int(cfg.get(cfg.treeWidth)))
        file_card_width = max(1, int(cfg.get(cfg.fileCardWidth)))

        # Older versions saved FileInfoCard's fullscreen width.  Limit only
        # the initial restore to a proportion of the normal window so that a
        # stale value cannot make the card dominate the browser.  A normal
        # user-selected width is left untouched when it is within that range.
        parent = self.parentWidget()
        normal_width = parent.width() if parent is not None else 0
        if normal_width > 0:
            margins = self.vBoxLayout.contentsMargins()
            splitter_width = max(0, normal_width - margins.left() - margins.right())
            max_card_width = max(400, int(splitter_width * 0.70))
            file_card_width = min(file_card_width, max_card_width)

        return [tree_width, file_card_width]

    def browse(self, repo: str, branch: str = ''):
        logReceived('Log.Action.BrowseRepository', repo or '/')
        if self._busy:
            self._queuedBrowse = (repo, branch)
            return
        self.repoEdit.setText(repo)
        self._requestedBranch = branch
        self.openRepository()

    def openRepository(self):
        repo = self.repoEdit.text().strip()
        if not repo:
            logCancelled('Log.Action.Repository', '/')
            return
        if self._busy:
            logCancelled('Log.Action.Repository', repo)
            return
        logStarted('Log.Action.Repository', repo)
        self._openingRepository = repo
        self._busy = True
        self.goButton.setEnabled(False)
        self.opsBar.setEnabled(False)
        self.treeView.repo = repo

    def onRepoLoaded(self, repo: str):
        self._openingRepository = ''
        logSucceeded('Log.Action.Repository', repo)
        self._busy = False
        self.goButton.setEnabled(True)
        self.opsBar.setEnabled(True)
        self.repoEdit.setText(repo)
        cfg.set(cfg.repoCache, repo)

        branches = getRepoBranches(repo, authService.accessToken())
        self.branchSelector.blockSignals(True)
        self.branchSelector.clear()
        self.branchSelector.addItems(branches)
        current = netdiskService.getBranch()
        switching_branch = False
        if self._requestedBranch and self._requestedBranch in branches:
            current = self._requestedBranch
            if current != netdiskService.getBranch():
                self.treeView.branch = current
                switching_branch = True
            self._requestedBranch = ''
        if current in branches:
            self.branchSelector.setCurrentText(current)
        self.branchSelector.blockSignals(False)
        self.fileInfoCard.showRepository(repo, current)
        writable = hasWriteAccess(repo, authService.accessToken())
        self.opsBar.addObjBtn.setEnabled(writable)
        self._resetSelectionUi()
        if switching_branch:
            return
        self._continueQueuedOrPending()

    def onBranchLoaded(self, branch):
        self._requestedBranch = ''
        self.branchSelector.blockSignals(True)
        self.branchSelector.setCurrentText(branch)
        self.branchSelector.blockSignals(False)
        self.fileInfoCard.showRepository(netdiskService.getRepo(), branch)
        self._resetSelectionUi()
        self._continueQueuedOrPending()

    def _continueQueuedOrPending(self):
        if self._queuedBrowse:
            queued = self._queuedBrowse
            self._queuedBrowse = None
            QTimer.singleShot(0, lambda: self.browse(*queued))
            return
        self._startPendingTask()

    def _startPendingTask(self):
        if self._pendingTaskRequest:
            request = self._pendingTaskRequest
            self._pendingTaskRequest = None
            QTimer.singleShot(0, lambda: self._startRepoTask(request))

    def addTaskRequest(self, request):
        """Start a task created by the dialog or a custom-protocol URL."""
        if request.target_type == 'url':
            self._startUrlTask(request)
            return
        try:
            repo, branch, _ = split_netdisk_uri(request.uri)
        except ValueError as error:
            self.showError(str(error))
            return
        if repo != netdiskService.getRepo() or branch != netdiskService.getBranch():
            self._pendingTaskRequest = request
            self.browse(repo, branch)
        else:
            self._startRepoTask(request)

    def _startRepoTask(self, request):
        try:
            repo, branch, remote_path = split_netdisk_uri(request.uri)
            if repo != netdiskService.getRepo() or branch != netdiskService.getBranch():
                raise ValueError('The requested repository or branch could not be opened.')
            if request.direction == 'upload':
                source = os.path.abspath(os.path.expanduser(request.filename))
                if not os.path.isfile(source):
                    raise FileNotFoundError(source)
                resume_data = createUploadResumeData(source)
                task = transferTaskService.create(
                    TransferDirection.UPLOAD, os.path.basename(source), source,
                    remote_path, os.path.getsize(source), repo, branch,
                    resume_data)

                def operation():
                    transferTaskService.start(task)
                    transferTaskService.updateStage(
                        task, 'TaskInterface.ConnectingRepository')
                    try:
                        task_disk = NetdiskService(repo, branch)
                        task_disk.uploadFile(
                            source, remote_path,
                            resumeData=task.resume_data,
                            status=lambda key, args:
                                transferTaskService.updateStage(task, key, args),
                            progress=lambda current, total:
                                transferTaskService.updateProgress(task, current, total))
                        transferTaskService.finish(task)
                    except Exception as error:
                        transferTaskService.fail(task, error)
                        raise
                action = 'Log.Action.FileUpload'
                text = self.tr('BrowseInterface.UploadFinished')
            else:
                download_name = posixpath.basename(
                    request.filename.replace('\\', '/')) or posixpath.basename(remote_path)
                destination = getUniqueFilePath(os.path.join(
                    cfg.get(cfg.saveFolder),
                    download_name))
                metadata = netdiskService.getContent(remote_path)
                task = transferTaskService.create(
                    TransferDirection.DOWNLOAD, os.path.basename(destination),
                    remote_path, destination, metadata.get(':size', 0), repo, branch)

                def operation():
                    transferTaskService.start(task)
                    transferTaskService.updateStage(
                        task, 'TaskInterface.ConnectingRepository')
                    try:
                        task_disk = NetdiskService(repo, branch)
                        result = task_disk.downloadFile(
                            remote_path, destination,
                            status=lambda key, args:
                                transferTaskService.updateStage(task, key, args),
                            progress=lambda current, total:
                                transferTaskService.updateProgress(task, current, total),
                            cancel_event=task._cancel_event)
                        transferTaskService.finish(task, result)
                    except Exception as error:
                        transferTaskService.fail(task, error)
                        raise
                action = 'Log.Action.FileDownload'
                text = self.tr('BrowseInterface.DownloadFinished')
            self._runTransfer(
                operation, text, action,
                (repo, branch) if request.direction == 'upload' else None)
        except Exception as error:
            self.showError(str(error))

    def _startUrlTask(self, request):
        url = request.uri
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https'):
            self.showError('URL tasks require an HTTP or HTTPS URL.')
            return
        direction = (TransferDirection.UPLOAD if request.direction == 'upload'
                     else TransferDirection.DOWNLOAD)
        source = os.path.abspath(os.path.expanduser(request.filename))
        if direction == TransferDirection.UPLOAD:
            if not os.path.isfile(source):
                self.showError(str(FileNotFoundError(source)))
                return
            destination, total = url, os.path.getsize(source)
            display_name = os.path.basename(source)
        else:
            download_name = posixpath.basename(
                request.filename.replace('\\', '/'))
            destination = getUniqueFilePath(os.path.join(
                cfg.get(cfg.saveFolder), download_name))
            source, total = url, 0
            display_name = os.path.basename(destination)
        context = parsed.netloc
        task = transferTaskService.create(
            direction, display_name, source, destination, total, context, '')
        temp_path = destination + '.part' if direction == TransferDirection.DOWNLOAD else ''

        def operation():
            transferTaskService.start(task)
            try:
                if direction == TransferDirection.UPLOAD:
                    with open(source, 'rb') as file:
                        response = requests.put(url, data=file, timeout=120)
                        response.raise_for_status()
                    transferTaskService.updateProgress(task, total, total)
                    transferTaskService.finish(task)
                else:
                    transferTaskService.updateStage(
                        task, 'TaskInterface.WaitingForDownloadData')
                    if task.is_cancelled:
                        raise _TransferCancelled()
                    with requests.get(url, stream=True, timeout=30) as response:
                        response.raise_for_status()
                        length = int(response.headers.get('content-length', 0) or 0)
                        with open(temp_path, 'wb') as file:
                            current = 0
                            for chunk in response.iter_content(1024 * 256):
                                if task.is_cancelled:
                                    raise _TransferCancelled()
                                if chunk:
                                    file.write(chunk)
                                    current += len(chunk)
                                    transferTaskService.updateStage(
                                        task, 'TaskInterface.DownloadingFile')
                                    transferTaskService.updateProgress(task, current, length)
                    os.replace(temp_path, destination)
                    transferTaskService.finish(task, destination)
            except Exception as error:
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)
                transferTaskService.fail(task, error)
                raise
        action = ('Log.Action.FileUpload' if direction == TransferDirection.UPLOAD
                  else 'Log.Action.FileDownload')
        text = self.tr('BrowseInterface.UploadFinished' if direction == TransferDirection.UPLOAD
                       else 'BrowseInterface.DownloadFinished')
        self._runTransfer(operation, text, action)

    def onBranchChanged(self, branch: str):
        if branch and branch != netdiskService.getBranch() and not self._busy:
            logChanged('Log.Action.Branch', branch)
            self.treeView.branch = branch
            self.fileInfoCard.showRepository(netdiskService.getRepo(), branch)

    def selectedPath(self):
        index = self.treeView.currentIndex()
        if not index.isValid():
            return ''
        index = index.sibling(index.row(), 0)
        data = index.data(Qt.UserRole)
        return data.split(':', 1)[1] if data else ''

    def selectedFolder(self):
        path = self.selectedPath()
        if not path:
            return '/'
        return path if netdiskService.isDir(path) else posixpath.dirname(path) or '/'

    def onSelectionChanged(self, current, previous):
        path = self.selectedPath()
        if not path:
            self._resetSelectionUi()
            return
        logSelected('Log.Action.FileSelection', path)
        self.fileInfoCard.path = path
        has_repo = bool(netdiskService.getRepo())
        self.opsBar.setEnabled(has_repo and not self._busy)
        if not has_repo:
            return
        writable = hasWriteAccess(netdiskService.getRepo(), authService.accessToken())
        self.opsBar.downloadAction.setEnabled(bool(path))
        is_file = bool(path) and netdiskService.isFile(path)
        self.opsBar.copyLinkAction.setEnabled(is_file)
        if is_file:
            metadata = netdiskService.getContent(path)
            assets = metadata.get(':assets') or [posixpath.basename(path)]
            direct_link_available = (
                int(metadata.get(':size', 0) or 0) < MAX_ASSET_SIZE
                and len(assets) == 1
            )
        else:
            direct_link_available = False
        self.opsBar.copyDirectLinkAction.setEnabled(direct_link_available)
        self.opsBar.renameAction.setEnabled(bool(path) and writable)
        self.opsBar.deleteAction.setEnabled(bool(path) and writable)

    def _resetSelectionUi(self):
        """Clear selection-dependent state after a model/repository refresh.

        A model reset can invalidate the current index without emitting
        ``currentChanged``.  Keeping the old ``FileInfoCard`` and enabled
        actions in that case makes buttons appear usable while their handlers
        have no selected path.  Always restore the repository summary and
        disable every file-only operation when no path is selected.
        """
        repository = netdiskService.getRepo()
        if repository:
            self.fileInfoCard.showRepository(repository, netdiskService.getBranch())
        else:
            self.fileInfoCard.clearRepository()
        self.opsBar.downloadAction.setEnabled(False)
        self.opsBar.copyLinkAction.setEnabled(False)
        self.opsBar.copyDirectLinkAction.setEnabled(False)
        self.opsBar.renameAction.setEnabled(False)
        self.opsBar.deleteAction.setEnabled(False)
        self.opsBar.setEnabled(bool(repository) and not self._busy)

    def _onTreeReloaded(self):
        # Do not retain a stale selection across a refresh.  Clearing both the
        # selection and current index also makes the behavior deterministic on
        # Qt versions that preserve the old current index during modelReset.
        selection_model = self.treeView.selectionModel()
        selection_model.clearSelection()
        selection_model.clearCurrentIndex()
        self._resetSelectionUi()

    def _run(self, function, success_text: str, action_key: str):
        logStarted(action_key)
        self._busy = True
        self.opsBar.setEnabled(False)
        future = TaskExecutor.run(function)
        future.result.connect(lambda _: self._finishOperation(success_text, action_key))
        future.failed.connect(lambda error: self._failOperation(error, action_key))

    def _runTransfer(self, function, success_text: str, action_key: str,
                     refresh_context=None):
        """Run a transfer without locking the repository browser."""
        logStarted(action_key)
        future = TaskExecutor.run(function)
        future.result.connect(
            lambda _: self._finishTransfer(
                success_text, action_key, refresh_context))
        future.failed.connect(
            lambda error: self._failTransfer(
                error, action_key, refresh_context))

    def _refreshTransferRepository(self, context):
        if (context and context ==
                (netdiskService.getRepo(), netdiskService.getBranch())):
            self.treeView.reload()

    def _finishTransfer(self, text, action_key, refresh_context=None):
        logSucceeded(action_key)
        self._refreshTransferRepository(refresh_context)
        InfoBar.success(
            self.tr('Common.Success'), text,
            duration=2500, parent=self.window())

    def _failTransfer(self, error, action_key, refresh_context=None):
        error = unwrapFutureError(error)
        if isTransferCancelledError(error):
            logCancelled(action_key)
            self._refreshTransferRepository(refresh_context)
            return
        logFailed(action_key, error)
        self._refreshTransferRepository(refresh_context)
        InfoBar.error(
            self.tr('BrowseInterface.ErrorFlyout.title'), str(error),
            duration=5000, parent=self.window())

    def _finishOperation(self, text: str, action_key: str):
        logSucceeded(action_key)
        self._busy = False
        self._resetSelectionUi()
        self.treeView.reload()
        InfoBar.success(self.tr('Common.Success'), text, duration=2500, parent=self.window())

    def _failOperation(self, error, action_key='Log.Action.Repository'):
        error = unwrapFutureError(error)
        logFailed(action_key, error)
        self._busy = False
        self.opsBar.setEnabled(bool(netdiskService.getRepo()))
        self.treeView.reload()
        self.showError(error)

    def uploadFiles(self, paths: list):
        if not paths or not netdiskService.getRepo():
            logCancelled('Log.Action.FileUpload')
            return
        logSelected('Log.Action.FileSelection', str(len(paths)))
        folder = self.selectedFolder()
        repository = netdiskService.getRepo()
        branch = netdiskService.getBranch()
        entries = []
        for path in paths:
            destination = netdiskService.join(folder, os.path.basename(path))
            resume_data = createUploadResumeData(path)
            task = transferTaskService.create(
                TransferDirection.UPLOAD,
                os.path.basename(path),
                path,
                destination,
                os.path.getsize(path),
                repository,
                branch,
                resume_data,
            )
            entries.append((path, destination, task))

        def upload():
            errors = []
            for _, _, task in entries:
                transferTaskService.updateStage(
                    task, 'TaskInterface.ConnectingRepository')
            try:
                task_disk = NetdiskService(repository, branch)
            except Exception as error:
                for _, _, task in entries:
                    transferTaskService.fail(task, error)
                raise
            for source, destination, task in entries:
                transferTaskService.start(task)
                try:
                    task_disk.uploadFile(
                        source,
                        destination,
                        resumeData=task.resume_data,
                        status=lambda key, args, current_task=task:
                            transferTaskService.updateStage(
                                current_task, key, args),
                        progress=lambda current, total, current_task=task:
                            transferTaskService.updateProgress(current_task, current, total),
                    )
                    transferTaskService.finish(task)
                except Exception as error:
                    transferTaskService.fail(task, error)
                    errors.append(f'{task.file_name}: {error}')
            if errors:
                raise RuntimeError('\n'.join(errors))

        self._runTransfer(
            upload,
            self.tr('BrowseInterface.UploadFinished'),
            'Log.Action.FileUpload',
            (repository, branch),
        )

    def _resumeTransfer(self, task):
        """Dispatch resume to the correct handler based on direction."""
        if task.direction == TransferDirection.UPLOAD:
            self.resumeUpload(task)
        else:
            self.resumeDownload(task)

    def _cancelTransfer(self, task):
        """Request cancellation of an active transfer."""
        transferTaskService.cancelTask(task)

    def _pauseTransfer(self, task):
        """Request pausing of an active transfer."""
        transferTaskService.pauseTask(task)

    def resumeDownload(self, task):
        """Continue an interrupted download, keeping already transferred bytes."""
        if not task.can_resume:
            return
        if not transferTaskService.restart(task):
            return
        transferTaskService.updateStage(
            task, 'TaskInterface.ConnectingRepository')

        def download():
            try:
                task_disk = NetdiskService(task.repository, task.branch)
                result = task_disk.downloadFile(
                    task.source,
                    task.destination,
                    status=lambda key, args:
                        transferTaskService.updateStage(task, key, args),
                    progress=lambda current, total:
                        transferTaskService.updateProgress(task, current, total),
                    resume_bytes=task.transferred,
                    cancel_event=task._cancel_event,
                )
                transferTaskService.finish(task, result)
            except Exception as error:
                transferTaskService.fail(task, error)
                raise

        self._runTransfer(
            download,
            self.tr('BrowseInterface.DownloadFinished'),
            'Log.Action.FileDownload',
        )

    def resumeUpload(self, task):
        """Continue an interrupted upload using the assets in its Release."""
        if not task.can_resume:
            return
        if not sourceMatchesResumeData(task.source, task.resume_data):
            self.showError(self.tr('TaskInterface.ResumeSourceChanged'))
            return
        if not transferTaskService.restart(task):
            return
        transferTaskService.updateStage(
            task, 'TaskInterface.ConnectingRepository')

        def upload():
            try:
                task_disk = NetdiskService(task.repository, task.branch)
                task_disk.uploadFile(
                    task.source,
                    task.destination,
                    resumeData=task.resume_data,
                    status=lambda key, args:
                        transferTaskService.updateStage(task, key, args),
                    progress=lambda current, total:
                        transferTaskService.updateProgress(task, current, total),
                )
                transferTaskService.finish(task)
            except Exception as error:
                transferTaskService.fail(task, error)
                raise

        self._runTransfer(
            upload,
            self.tr('BrowseInterface.UploadFinished'),
            'Log.Action.FileUpload',
            (task.repository, task.branch),
        )

    def downloadSelected(self):
        self._downloadSelected()

    def downloadSelectedAs(self, destination):
        self._downloadSelected(destination)

    def _downloadSelected(self, destination_override=None):
        path = self.selectedPath()
        if not path:
            logCancelled('Log.Action.FileDownload')
            return
        if netdiskService.isFile(path):
            repository = netdiskService.getRepo()
            branch = netdiskService.getBranch()
            if destination_override:
                requested_destination = os.path.abspath(destination_override)
                destination = requested_destination
            else:
                requested_destination = os.path.join(
                    cfg.get(cfg.saveFolder), os.path.basename(path))
                destination = getUniqueFilePath(
                    requested_destination,
                    self._activeDownloadDestinations(),
                )
            if destination != requested_destination:
                logChanged(
                    'Log.Action.FileDownload',
                    f'{requested_destination} -> {destination}',
                )
            logSelected('Log.Action.SaveFolder', destination)
            task = transferTaskService.create(
                TransferDirection.DOWNLOAD,
                os.path.basename(destination),
                path,
                destination,
                netdiskService.getContent(path).get(':size', 0),
                repository,
                branch,
            )

            def download_file():
                transferTaskService.start(task)
                transferTaskService.updateStage(
                    task, 'TaskInterface.ConnectingRepository')
                try:
                    task_disk = NetdiskService(repository, branch)
                    result = task_disk.downloadFile(
                        path,
                        destination,
                        status=lambda key, args:
                            transferTaskService.updateStage(task, key, args),
                        progress=lambda current, total:
                            transferTaskService.updateProgress(task, current, total),
                        cancel_event=task._cancel_event,
                    )
                    transferTaskService.finish(task, result)
                except Exception as error:
                    transferTaskService.fail(task, error)
                    raise

            self._runTransfer(
                download_file,
                self.tr('BrowseInterface.DownloadFinished'),
                'Log.Action.FileDownload',
            )
            return

        destination = cfg.get(cfg.saveFolder)
        repository = netdiskService.getRepo()
        branch = netdiskService.getBranch()
        logSelected('Log.Action.SaveFolder', destination)

        base = posixpath.dirname(path.rstrip('/'))
        reserved_destinations = self._activeDownloadDestinations()
        entries = []
        for root, _, files in netdiskService.walk(path):
            relative = posixpath.relpath(root, base)
            local_folder = os.path.join(destination, *relative.split('/'))
            for name in files:
                remote_path = netdiskService.join(root, name)
                requested_path = os.path.join(local_folder, name)
                local_path = getUniqueFilePath(
                    requested_path,
                    reserved_destinations,
                )
                reserved_destinations.add(local_path)
                if local_path != requested_path:
                    logChanged(
                        'Log.Action.FileDownload',
                        f'{requested_path} -> {local_path}',
                    )
                task = transferTaskService.create(
                    TransferDirection.DOWNLOAD,
                    os.path.basename(local_path),
                    remote_path,
                    local_path,
                    netdiskService.getContent(remote_path).get(':size', 0),
                    repository,
                    branch,
                )
                entries.append((remote_path, local_path, task))

        def download_folder():
            errors = []
            cancelled = False
            for _, _, task in entries:
                transferTaskService.updateStage(
                    task, 'TaskInterface.ConnectingRepository')
            try:
                task_disk = NetdiskService(repository, branch)
            except Exception as error:
                for _, _, task in entries:
                    transferTaskService.fail(task, error)
                raise
            for remote_path, local_path, task in entries:
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                transferTaskService.start(task)
                try:
                    result = task_disk.downloadFile(
                        remote_path,
                        local_path,
                        status=lambda key, args, current_task=task:
                            transferTaskService.updateStage(
                                current_task, key, args),
                        progress=lambda current, total, current_task=task:
                            transferTaskService.updateProgress(current_task, current, total),
                        cancel_event=task._cancel_event,
                    )
                    transferTaskService.finish(task, result)
                except Exception as error:
                    transferTaskService.fail(task, error)
                    if isTransferCancelledError(error):
                        cancelled = True
                    else:
                        errors.append(f'{task.file_name}: {error}')
            if errors:
                raise RuntimeError('\n'.join(errors))
            if cancelled:
                raise _TransferCancelled()

        self._runTransfer(
            download_folder,
            self.tr('BrowseInterface.DownloadFinished'),
            'Log.Action.FolderDownload',
        )

    @staticmethod
    def _activeDownloadDestinations():
        return {
            task.destination
            for task in transferTaskService.tasks()
            if task.direction == TransferDirection.DOWNLOAD and task.is_active
        }

    def copySelectedLink(self, direct=False):
        logAction(
            'Log.Action.Copy',
            self.tr(
                'OpsBar.CopyDirectLink' if direct else 'OpsBar.CopyLink'
            ),
        )
        path = self.selectedPath()
        if not path or not netdiskService.isFile(path):
            logCancelled('Log.Action.Copy')
            return
        metadata = netdiskService.getContent(path)
        assets = metadata.get(':assets') or [posixpath.basename(path)]
        if not assets:
            self.showError('The selected file has no Release asset.')
            return
        size = int(metadata.get(':size', 0) or 0)
        if direct:
            if size >= MAX_ASSET_SIZE or len(assets) != 1:
                self.showError(self.tr('BrowseInterface.DirectLinkUnavailable'))
                return
            link = release_download_link(
                netdiskService.getRepo(), metadata.get(':file', ''), assets[0])
            if cfg.get(cfg.githubMirrorEnabled):
                future = TaskExecutor.run(getFastestGithubMirror, link)
                future.result.connect(
                    lambda mirror, target=link: self._finishCopyLink(
                        githubProxyUrl(target, mirror) if mirror else target))
                future.failed.connect(
                    lambda _error, target=link: self._finishCopyLink(target))
                return
        else:
            link = redirect_link(
                netdiskService.getRepo(), netdiskService.getBranch(), path,
                posixpath.basename(path), metadata.get(':file', ''), assets[0],
                size, cfg.get(cfg.language).name())
        self._finishCopyLink(link)

    def _finishCopyLink(self, link):
        QApplication.clipboard().setText(link)
        logSucceeded('Log.Action.Copy', link)
        InfoBar.success(
            self.tr('Common.Success'), self.tr('BrowseInterface.LinkCopied'),
            duration=2000, parent=self.window())

    def renameSelected(self):
        index = self.treeView.currentIndex()
        if index.isValid():
            logAction('Log.Action.Rename', self.selectedPath())
            self.treeView.edit(index.sibling(index.row(), 0))
        else:
            logCancelled('Log.Action.Rename')

    def deleteSelected(self):
        path = self.selectedPath()
        if not path:
            logCancelled('Log.Action.Delete')
            return
        name = posixpath.basename(path)
        if not self.window().showMessage(
            self.tr('FileToolBar.Delete.title', name),
            self.tr('FileToolBar.Delete.text', name),
        ):
            logCancelled('Log.Action.Delete', path)
            return
        logAction('Log.Action.Delete', path)
        self._run(
            lambda: netdiskService.remove(path),
            self.tr('BrowseInterface.DeleteFinished'),
            'Log.Action.Delete',
        )

    def onLoadError(self, error):
        """Restore a coherent browser state after an asynchronous load error."""
        repository = self._openingRepository
        self._openingRepository = ''
        if repository:
            current_repo = netdiskService.getRepo()
            self.branchSelector.blockSignals(True)
            if current_repo:
                self.repoEdit.setText(current_repo)
                self.branchSelector.setCurrentText(netdiskService.getBranch())
                self.fileInfoCard.showRepository(
                    current_repo, netdiskService.getBranch())
            else:
                self.branchSelector.clear()
                self.fileInfoCard.clearRepository()
            self.branchSelector.blockSignals(False)
            logFailed(
                'Log.Action.Repository',
                self._repositoryErrorText(error, repository),
            )
        # Refresh/branch failures do not carry an opening repository marker,
        # but they can still leave an invalid current index.  Reset in both
        # cases so action buttons and the information card stay coherent.
        self._resetSelectionUi()
        self.showError(error, repository)

    def _repositoryErrorText(self, error, repository):
        error = unwrapFutureError(error)
        message = str(error) or self.tr('BrowseInterface.UnknownError')
        if message == 'Failed to open repository.':
            return self.tr(
                'BrowseInterface.RepositoryUnavailable', (repository,))
        if 'netdisk.json is missing' in message:
            return self.tr(
                'BrowseInterface.RepositoryNotNetdisk', (repository,))
        return message

    def showError(self, error, repository=''):
        error = unwrapFutureError(error)
        message = str(error) or self.tr('BrowseInterface.UnknownError')
        title = self.tr('BrowseInterface.ErrorFlyout.title')
        if repository:
            title = self.tr('BrowseInterface.RepositoryOpenFailed.title')
            message = self._repositoryErrorText(error, repository)
        logAction('Log.Action.InfoBar', message, level='debug')
        self._busy = False
        self.goButton.setEnabled(True)
        self.opsBar.setEnabled(bool(netdiskService.getRepo()))
        InfoBar.error(title, message, duration=6000, parent=self.window())
