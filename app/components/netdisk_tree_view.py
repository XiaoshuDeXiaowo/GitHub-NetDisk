# coding: utf-8
import os
from typing import Union, Optional
from PyQt5.QtCore import pyqtProperty, pyqtSignal, Qt, QModelIndex
from PyQt5.QtGui import QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import QAbstractItemView, QWidget
from qfluentwidgets import TreeView, IndeterminateProgressRing
from qfluentwidgets.common.overload import singledispatchmethod
from pyqt5_concurrent.TaskExecutor import TaskExecutor

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
from ..service.github_service import getRepo, hasWriteAccess
from ..service.auth_service import authService
from ..common.signal_bus import signalBus
from ..common.translator import translate
from ..service.netdisk_service import netdiskService
from ..common.utils import (
    adjustFileName,
    getFileTypeIcon,
    getFileTypeName,
    getFolderTypeIcon,
    getFolderTypeName,
    unwrapFutureError,
)


class NetdiskTreeModel(QStandardItemModel):
    """ tree model for github-netdisk

    Constructors
    ------------
    * NetdiskTreeModel(`parent`: QWidget | None = None)
    * NetdiskTreeModel(`repo`: str, `parent`: QWidget | None = None)
    * NetdiskTreeModel(`repo`: str, `branch`: str, `parent`: QWidget | None = None)
    """

    @singledispatchmethod
    def __init__(self, parent: QWidget = None):
        super().__init__(parent=parent)
        self.tr = translate
        self._netdisk = netdiskService
        self.setHorizontalHeaderLabels([self.tr('NetdiskTreeModel.header.Name'), self.tr('NetdiskTreeModel.header.Type'),
            self.tr('NetdiskTreeModel.header.Size')])
        self.setSortRole(Qt.UserRole if cfg.get(cfg.dirAhead) else Qt.DisplayRole)

        signalBus.dirAheadChanged.connect(lambda: self.setSortRole(Qt.UserRole if cfg.get(cfg.dirAhead) else Qt.DisplayRole))
        logInitialized('Log.Action.RepositoryList', level='debug')

    @__init__.register
    def _(self, repo: str, parent: QWidget = None):
        self.__init__(parent=parent)
        self.setRepo(repo)

    @__init__.register
    def _(self, repo: str, branch: str, parent: QWidget = None):
        self.__init__(parent=parent)
        self.setRepo(repo)
        self.setBranch(branch)

    def forceLoad(self) -> None:
        """ force load the net disk """
        logStarted('Log.Action.Refresh', self._netdisk.getRepo(), level='debug')
        self.clear()
        self.setHorizontalHeaderLabels([self.tr('NetdiskTreeModel.header.Name'), self.tr('NetdiskTreeModel.header.Type'),
            self.tr('NetdiskTreeModel.header.Size')])
        root = self.invisibleRootItem()
        folder_items = {'/': root}
        for i in self._netdisk.walk('/'):
            walking = i[0]
            root = folder_items.get(walking, self.invisibleRootItem())
            for dir in i[1]:
                name = QStandardItem(getFolderTypeIcon(), dir)
                full_path = self._netdisk.join(walking, dir)
                name.setData(f'dir:{full_path}', Qt.UserRole)
                root.appendRow([name, QStandardItem(getFolderTypeName()), QStandardItem('')])
                folder_items[full_path] = name
            for nondir in i[2]:
                name = QStandardItem(getFileTypeIcon(nondir), nondir)
                name.setData(f'nondir:{self._netdisk.join(walking, nondir)}', Qt.UserRole)
                size = self._netdisk.getSize(self._netdisk.join(i[0], nondir))
                root.appendRow([name, QStandardItem(getFileTypeName(nondir)), QStandardItem(size)])
        logSucceeded('Log.Action.Refresh', str(self.rowCount()), level='debug')

    def reload(self) -> None:
        """Fetch the current remote index before rebuilding the tree."""
        self._netdisk.forceReload(create_if_missing=False)
        self.forceLoad()

    def flags(self, index):
        flags = super().flags(index)
        if not index.isValid() or index.column() != 0:
            return flags & ~Qt.ItemIsEditable
        repo = self._netdisk.getRepo()
        if not repo or not hasWriteAccess(repo, authService.accessToken()):
            return flags & ~Qt.ItemIsEditable
        return flags

    def setRepo(self, repo: str) -> None:
        """ set the model's repo

        Parameters
        ----------
        repo: str
            repo
        """
        self._netdisk.setRepo(repo)
        self.setBranch(self._netdisk.getBranch())

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
        self._netdisk.setBranch(branch)
        self.forceLoad()

    def getBranch(self) -> str:
        """ returns the model's branch """
        return self._netdisk.getBranch()

    branch = pyqtProperty(str, getBranch, setBranch)

class NetdiskTreeView(TreeView):
    """ a tree view for GitHub-NetDisk """
    repoLoaded = pyqtSignal(str)
    branchLoaded = pyqtSignal(str)
    reloadFinished = pyqtSignal()
    loadError = pyqtSignal(object)
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent=parent)
        self.tr = translate
        self.ring = IndeterminateProgressRing(self)
        self.ring.hide()
        self._model = NetdiskTreeModel(self)
        self.setModel(self._model)
        self.header().setStretchLastSection(True)
        self.setColumnWidth(0, 320)
        self.setColumnWidth(1, 160)
        self.setSortingEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setDropIndicatorShown(True)
        self._model.dataChanged.connect(self.onDataChanged)
        logInitialized('Log.Action.RepositoryList')

    @staticmethod
    def localDropFiles(mime_data):
        if not mime_data or not mime_data.hasUrls():
            return []
        return [
            os.path.normpath(url.toLocalFile())
            for url in mime_data.urls()
            if url.isLocalFile() and os.path.isfile(url.toLocalFile())
        ]

    def canUploadDroppedFiles(self, paths):
        repo = self._model.getRepo()
        return bool(
            paths
            and repo
            and hasWriteAccess(repo, authService.accessToken())
        )

    def dragEnterEvent(self, event):
        paths = self.localDropFiles(event.mimeData())
        if self.canUploadDroppedFiles(paths):
            event.setDropAction(Qt.CopyAction)
            event.accept()
            return
        event.ignore()

    def dragMoveEvent(self, event):
        paths = self.localDropFiles(event.mimeData())
        if self.canUploadDroppedFiles(paths):
            event.setDropAction(Qt.CopyAction)
            event.accept()
            return
        event.ignore()

    def dropEvent(self, event):
        paths = self.localDropFiles(event.mimeData())
        if not self.canUploadDroppedFiles(paths):
            logCancelled('Log.Action.FileDropUpload')
            event.ignore()
            return

        index = self.indexAt(event.pos())
        if index.isValid():
            self.setCurrentIndex(index.sibling(index.row(), 0))
        logAction('Log.Action.FileDropUpload', str(len(paths)))
        signalBus.uploadFilesSig.emit(paths)
        event.setDropAction(Qt.CopyAction)
        event.accept()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, 'ring'):
            x = self.width()//2 - self.ring.width()//2
            y = self.height()//2 - self.ring.height()//2
            self.ring.move(x, y)
        cfg.set(cfg.treeWidth, self.width())

    def reload(self):
        logAction('Log.Action.Refresh')
        w1 = self.columnWidth(0)
        w2 = self.columnWidth(1)
        self.ring.show()
        future = TaskExecutor.run(self._model.reload)
        future.result.connect(lambda f: self._onLoadFinished(f, w1, w2))
        future.failed.connect(lambda e: self._onLoadFailed(e, w1, w2))

    def onDataChanged(self, topLeft: QModelIndex, bottomRight: QModelIndex, roles):
        """ handle data changed signal to rename files/folders """
        if Qt.DisplayRole in roles or not roles:
            newValue = adjustFileName(topLeft.data(Qt.DisplayRole))
            oldValue = topLeft.data(Qt.UserRole).split(':')[-1].strip('/').split('/')[-1]
            if not newValue or newValue == oldValue:
                logCancelled('Log.Action.Rename', oldValue, level='debug')
                return
            oldData = self._model.data(topLeft, Qt.UserRole).split(':')
            prefix = oldData[0]
            oldPath = oldData[-1]
            newPath = oldPath.split('/')[:-1] + [newValue]
            newPath = self._model._netdisk.join(*newPath)
            try:
                logStarted('Log.Action.Rename', f'{oldPath} -> {newPath}')
                self._model._netdisk.rename(oldPath, newPath)
                self._model.blockSignals(True)
                self._model.setData(topLeft, newValue, Qt.DisplayRole)
                self._model.setData(topLeft, f'{prefix}:{newPath}', Qt.UserRole)
                logSucceeded('Log.Action.Rename', f'{oldPath} -> {newPath}')
            except Exception as error:
                logFailed(
                    'Log.Action.Rename',
                    exceptionDetail(error, oldPath),
                )
                self._model.blockSignals(True)
                self._model.setData(topLeft, oldValue, Qt.DisplayRole)
                self.loadError.emit(error)
            finally:
                self._model.blockSignals(False)
          

    def onCreateNewFolder(self):
        """ Create a new folder. If a file is selected, create at the same level;
        if a folder is selected, create inside it. Then start rename mode. """
        index = self.currentIndex()

        # Determine parent item and parent path
        if not index.isValid():
            # No selection: create at root level
            parentItem = self._model.invisibleRootItem()
            parentPath = '/'
        else:
            data = self._model.data(index, Qt.UserRole)
            if not data:
                logCancelled('Log.Action.CreateFolder')
                return
            prefix, path = data.split(':', 1)
            if prefix == 'nondir':
                # File selected: create sibling folder (same level)
                parentIndex = self._model.parent(index)
                if parentIndex.isValid():
                    parentData = self._model.data(parentIndex, Qt.UserRole)
                    parentPath = parentData.split(':', 1)[1] if parentData else '/'
                    parentItem = self._model.itemFromIndex(parentIndex)
                else:
                    parentPath = '/'
                    parentItem = self._model.invisibleRootItem()
            else:  # dir
                # Folder selected: create child folder inside it
                parentPath = path
                parentItem = self._model.itemFromIndex(index)

        # Generate unique folder name (handle conflicts like "新建文件夹 (1)")
        baseName = self.tr('NetdiskTreeView.NewFolder')
        folderName = baseName
        counter = 1
        existingNames = {parentItem.child(row).text() for row in range(parentItem.rowCount()) if parentItem.child(row)}
        while folderName in existingNames:
            folderName = f'{baseName} ({counter})'
            counter += 1

        newPath = self._model._netdisk.join(parentPath, folderName)
        logStarted('Log.Action.CreateFolder', newPath)

        future = TaskExecutor.run(self._model._netdisk.mkdir, newPath)
        future.finished.connect(
            lambda _: self._addNewFolderRow(parentItem, folderName, newPath))
        future.failed.connect(lambda error: self._onCreateFolderFailed(error, newPath))

    def _addNewFolderRow(self, parentItem, folderName: str, newPath: str):
        """Insert a newly-created remote folder into the model on the UI thread."""
        nameItem = QStandardItem(getFolderTypeIcon(), folderName)
        nameItem.setData(f'dir:{newPath}', Qt.UserRole)
        typeItem = QStandardItem(getFolderTypeName())
        sizeItem = QStandardItem('')
        parentItem.appendRow([nameItem, typeItem, sizeItem])

        # Expand parent to make the new item visible
        if parentItem != self._model.invisibleRootItem():
            parentIdx = self._model.indexFromItem(parentItem)
            if parentIdx.isValid():
                self.expand(parentIdx)

        # Scroll to the new item and start rename mode
        newIndex = self._model.indexFromItem(nameItem)
        self.scrollTo(newIndex)
        self.edit(newIndex)
        logSucceeded('Log.Action.CreateFolder', newPath)

    def _onCreateFolderFailed(self, error, path):
        error = unwrapFutureError(error)
        logFailed(
            'Log.Action.CreateFolder',
            exceptionDetail(error, path),
        )
        self.loadError.emit(error)

    def _restoreLoadUi(self, w1, w2):
        self.ring.hide()
        self.setColumnWidth(0, w1)
        self.setColumnWidth(1, w2)

    def _onLoadFinished(self, f, w1, w2):
        self._restoreLoadUi(w1, w2)
        logSucceeded('Log.Action.Refresh', level='debug')
        self.reloadFinished.emit()

    def _onLoadFailed(self, e, w1, w2, action_key='Log.Action.Refresh',
                      log_error=True):
        error = unwrapFutureError(e)
        self._restoreLoadUi(w1, w2)
        signalBus.loadFailedSig.emit()
        if log_error:
            logFailed(action_key, error)
        self.loadError.emit(error)

    def _onRepoLoadFinished(self, f, w1, w2):
        self._restoreLoadUi(w1, w2)
        self.repoLoaded.emit(self.getRepo())

    def setRepo(self, repo: str):
        w1 = self.columnWidth(0)
        w2 = self.columnWidth(1)
        self.ring.show()
        future = TaskExecutor.run(self._model.setRepo, repo)
        # ``finished`` is emitted for both success and failure by
        # pyqt5-concurrent. Only publish a loaded repository on real success.
        future.result.connect(lambda f: self._onRepoLoadFinished(f, w1, w2))
        future.failed.connect(
            lambda e: self._onLoadFailed(e, w1, w2, log_error=False))

    def getRepo(self) -> str:
        return self._model.getRepo()

    repo = pyqtProperty(str, getRepo, setRepo)

    def setBranch(self, branch: str):
        w1 = self.columnWidth(0)
        w2 = self.columnWidth(1)
        self.ring.show()
        logStarted('Log.Action.Branch', branch)
        future = TaskExecutor.run(self._model.setBranch, branch)
        future.result.connect(
            lambda f: self._onBranchLoadFinished(f, w1, w2))
        future.failed.connect(lambda e: self._onLoadFailed(
            e, w1, w2, action_key='Log.Action.Branch'))

    def _onBranchLoadFinished(self, f, w1, w2):
        self._restoreLoadUi(w1, w2)
        logSucceeded('Log.Action.Branch', self.getBranch())
        self.branchLoaded.emit(self.getBranch())

    def getBranch(self) -> str:
        return self._model.getBranch()

    branch = pyqtProperty(str, getBranch, setBranch)
