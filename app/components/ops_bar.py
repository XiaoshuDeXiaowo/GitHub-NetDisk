# coding: utf-8
from typing import Union, Callable
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QFileDialog
from loguru import logger
from qfluentwidgets import (CommandBar, Action, FluentIconBase, TransparentDropDownPushButton,
                            RoundMenu, ToolTipPosition, setFont)
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets.components.widgets.command_bar import CommandToolTipFilter

from ..common.icon import Icon
from ..common.event_logger import logAction, logCancelled, logSelected
from ..service.netdisk_service import netdiskService
from ..common.signal_bus import signalBus
from ..common.translator import translate
from ..common.utils import getFolderTypeIcon
from .tool_tip import DisabledFriendlyAcrylicToolTipFilter

class OpsBar(CommandBar):
    def __init__(self, parent = None):
        super().__init__(parent=parent)
        self.tr = translate

        self.addObjBtn = TransparentDropDownPushButton(FIF.ADD_TO, self.tr('OpsBar.Add'), self)
        self.addObjBtn.setFixedHeight(34)
        setFont(self.addObjBtn, 12)

        self.uploadAction = Action(FIF.UP, self.tr('OpsBar.UploadFiles'))
        self.newFolderAction = Action(getFolderTypeIcon(), self.tr('OpsBar.NewFolder'))

        menu = RoundMenu(parent=self)
        menu.addActions([self.uploadAction, self.newFolderAction])
        self.addObjBtn.setMenu(menu)
        self.addWidget(self.addObjBtn)
        
        self.downloadAction = self.addButton(FIF.DOWN, self.tr('OpsBar.Download'), signalBus.downloadSig)
        self.copyLinkAction = self.addButton(
            FIF.SEND, self.tr('OpsBar.CopyLink'),
            lambda: signalBus.copyLinkSig.emit(False),
            self.tr('OpsBar.CopyLink.ToolTip'))
        self.copyDirectLinkAction = self.addButton(
            FIF.COPY, self.tr('OpsBar.CopyDirectLink'),
            lambda: signalBus.copyLinkSig.emit(True),
            self.tr('OpsBar.CopyDirectLink.ToolTip'))
        self.copyLinkAction.setEnabled(False)
        self.copyDirectLinkAction.setEnabled(False)

        self.addSeparator()
        self.renameAction = self.addButton(Icon.RENAME, self.tr('OpsBar.Rename'), signalBus.renameSig)
        self.deleteAction = self.addButton(FIF.DELETE, self.tr('OpsBar.Delete'), signalBus.deleteSig)
        
        self.downloadAction.setEnabled(False)
        self.renameAction.setEnabled(False)
        self.deleteAction.setEnabled(False)
        self.addSeparator()
        self.refreshAction = self.addButton(FIF.SYNC, self.tr('OpsBar.Refresh'), signalBus.refreshSig)

        self._connectSignalToSlot()

    def addButton(self, icon: Union[FluentIconBase, QIcon, str], text: str,
                  triggered: Callable = None, tool_tip: str = ''):
        action = Action(icon, text)
        if triggered:
            action.triggered.connect(triggered)
        button = self.addAction(action)
        if tool_tip:
            action.setToolTip(tool_tip)
            button.setToolTip(tool_tip)
            # CommandButton installs its own tooltip filter in setAction().
            # Remove it before adding the Acrylic variant, otherwise both
            # filters create a tooltip for the same hover event.
            for filter_ in button.findChildren(CommandToolTipFilter):
                button.removeEventFilter(filter_)
                filter_.deleteLater()
            button.installEventFilter(DisabledFriendlyAcrylicToolTipFilter(
                button, position=ToolTipPosition.TOP))
        return action

    def _connectSignalToSlot(self):
        self.uploadAction.triggered.connect(self.onUpload)
        self.newFolderAction.triggered.connect(self.onCreateFolder)

    def onUpload(self):
        logAction('Log.Action.FileUpload')
        dialog = QFileDialog(self.window(), self.tr('OpsBar.SelectFilesToUpload'))
        dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        if dialog.exec():
            filePaths = dialog.selectedFiles()
            logSelected('Log.Action.FileSelection', str(len(filePaths)))
            signalBus.uploadFilesSig.emit(filePaths)
        else:
            logCancelled('Log.Action.FileSelection')

    def onCreateFolder(self):
        logAction('Log.Action.CreateFolder')
        signalBus.createNewFolderSig.emit()

