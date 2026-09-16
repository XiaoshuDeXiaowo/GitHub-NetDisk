# coding:utf-8
from loguru import logger
from qfluentwidgets import (SwitchSettingCard, FolderListSettingCard,
                            OptionsSettingCard, PushSettingCard,
                            HyperlinkCard, PrimaryPushSettingCard, ScrollArea,
                            ComboBoxSettingCard, ExpandGroupSettingCard,
                            ExpandLayout, Theme, CustomColorSettingCard,
                            PushButton, SwitchButton, setTheme, setThemeColor,
                            isDarkTheme, setFont, TitleLabel)
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import SettingCardGroup as CardGroup
from qfluentwidgets import InfoBar
from PyQt5.QtCore import Qt, pyqtSignal, QUrl
from PyQt5.QtGui import QDesktopServices, QFont
from PyQt5.QtWidgets import QWidget, QLabel, QFileDialog, QApplication

from ..common.config import cfg, isWin11
from ..service.aria2_download_service import aria2DownloadService
from ..common.event_logger import logAction, logChanged, logInitialized
from ..common.icon import Icon
from ..common.setting import (AUTHOR, AUTHOR_URL, DEVELOPMENT_STAGE,
                              FEEDBACK_URL, LICENSE_URL, REPO_URL, VERSION,
                              YEAR,
                              localizedWebsiteUrl)
from ..common.signal_bus import signalBus
from ..common.style_sheet import StyleSheet
from ..common.translator import translate, getTranslateNamesList


class SettingCardGroup(CardGroup):

   def __init__(self, title: str, parent=None):
       super().__init__(title, parent)
       setFont(self.titleLabel, 14, QFont.Weight.DemiBold)



class SettingInterface(ScrollArea):
    """ Setting interface """

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.tr = translate
        self.scrollWidget = QWidget()
        self.expandLayout = ExpandLayout(self.scrollWidget)

        # setting label
        self.titleLabel = TitleLabel(self.tr("SettingInterface.Settings"), self)

        # personalization
        self.personalGroup = SettingCardGroup(
            self.tr('SettingInterface.Personalization'), self.scrollWidget)
        self.micaCard = SwitchSettingCard(
            FIF.TRANSPARENT,
            self.tr('SettingInterface.MicaEffect.title'),
            self.tr('SettingInterface.MicaEffect.text'),
            cfg.micaEnabled,
            self.personalGroup
        )
        self.trayIconCard = ExpandGroupSettingCard(
            FIF.APPLICATION,
            self.tr('SettingInterface.DisableTrayIcon.title'),
            self.tr('SettingInterface.DisableTrayIcon.text'),
            self.personalGroup,
        )
        self.disableTrayIconSwitch = SwitchButton(self.trayIconCard)
        self.disableTrayIconSwitch.setChecked(
            cfg.get(cfg.disableTrayIcon))
        self.trayIconCard.addWidget(self.disableTrayIconSwitch)
        self.exitOnCloseSwitch = SwitchButton(self.trayIconCard)
        self.exitOnCloseSwitch.setChecked(cfg.get(cfg.exitOnClose))
        self.exitOnCloseGroup = self.trayIconCard.addGroup(
            FIF.POWER_BUTTON,
            self.tr('SettingInterface.ExitOnClose.title'),
            self.tr('SettingInterface.ExitOnClose.text'),
            self.exitOnCloseSwitch,
        )
        self.themeCard = ComboBoxSettingCard(
            cfg.themeMode,
            FIF.BRUSH,
            self.tr('SettingInterface.ApplicationTheme.title'),
            self.tr("SettingInterface.ApplicationTheme.text"),
            texts=[
                self.tr('SettingInterface.ApplicationTheme.Light'), self.tr('SettingInterface.ApplicationTheme.Dark'),
                self.tr('SettingInterface.UseSystemSetting')
            ],
            parent=self.personalGroup
        )
        self.zoomCard = ComboBoxSettingCard(
            cfg.dpiScale,
            FIF.ZOOM,
            self.tr("SettingInterface.InterfaceZoom.title"),
            self.tr("SettingInterface.InterfaceZoom.text"),
            texts=[
                "100%", "125%", "150%", "175%", "200%",
                self.tr("SettingInterface.UseSystemSetting")
            ],
            parent=self.personalGroup
        )
        self.languageCard = ComboBoxSettingCard(
            cfg.language,
            FIF.LANGUAGE,
            self.tr('SettingInterface.Language.title'),
            self.tr('SettingInterface.Language.text'),
            texts=[*getTranslateNamesList(':/app/lang'), self.tr('SettingInterface.UseSystemSetting')],
            parent=self.personalGroup
        )

        # download
        self.downloadGroup = SettingCardGroup(
            self.tr('SettingInterface.Download'), self.scrollWidget)
        self.saveFolderCard = PushSettingCard(
            self.tr('SettingInterface.DefaultSaveFolder.Button.text'),
            FIF.SAVE,
            self.tr('SettingInterface.DefaultSaveFolder.title'),
            cfg.get(cfg.saveFolder),
            self.downloadGroup,
        )
        self.aria2Card = ExpandGroupSettingCard(
            FIF.DOWN,
            self.tr('SettingInterface.Aria2.title'),
            self.tr('SettingInterface.Aria2.text'),
            self.downloadGroup,
        )
        self.aria2Switch = SwitchButton(self.aria2Card)
        self.aria2Switch.setChecked(cfg.get(cfg.aria2Enabled))
        self.aria2Card.addWidget(self.aria2Switch)
        self.aria2PathButton = PushButton(
            self.tr('SettingInterface.Aria2Path.Button.text'),
            self.aria2Card,
        )
        self.aria2PathGroup = self.aria2Card.addGroup(
            FIF.COMMAND_PROMPT,
            self.tr('SettingInterface.Aria2Path.title'),
            self._aria2PathContent(),
            self.aria2PathButton,
        )

        # net disk
        self.netdiskGroup = SettingCardGroup(
            self.tr('SettingInterface.NetDisk'), self.scrollWidget)
        self.dirAheadCard = SwitchSettingCard(
            FIF.FOLDER,
            self.tr('SettingInterface.DirAhead.title'),
            self.tr('SettingInterface.DirAhead.text'),
            configItem=cfg.dirAhead,
            parent=self.netdiskGroup
        )

        # github
        self.githubGroup = SettingCardGroup(
            self.tr('SettingInterface.GithubMirror'), self.scrollWidget)
        self.githubMirrorCard = SwitchSettingCard(
            FIF.GITHUB,
            self.tr('SettingInterface.GithubMirror.title'),
            self.tr("SettingInterface.GithubMirror.text"),
            configItem=cfg.githubMirrorEnabled,
            parent=self.githubGroup
        )
        # self.apiMirrorCard = SwitchSettingCard(
        #     FIF.CODE,
        #     self.tr('SettingInterface.APIMirror.title'),
        #     self.tr("SettingInterface.APIMirror.text"),
        #     configItem=cfg.apiMirrorEnabled,
        #     parent=self.githubGroup
        # )

        # update software
        self.updateSoftwareGroup = SettingCardGroup(
            self.tr("SettingInterface.SoftwareUpdate"), self.scrollWidget)
        self.updateOnStartUpCard = SwitchSettingCard(
            FIF.UPDATE,
            self.tr('SettingInterface.SoftwareUpdate.title'),
            self.tr('SettingInterface.SoftwareUpdate.text'),
            configItem=cfg.checkUpdateAtStartUp,
            parent=self.updateSoftwareGroup
        )

        # application
        self.aboutGroup = SettingCardGroup(self.tr('SettingInterface.About'), self.scrollWidget)
        self.aboutCard = PrimaryPushSettingCard(
            self.tr('SettingInterface.About.Button.text'),
            ':/app/images/logo.png',
            self.tr('SettingInterface.About.title'),
            (f'{self.tr("SettingInterface.About.text")} · '
             f'{self.tr("SettingInterface.About.Version")} {DEVELOPMENT_STAGE} '
             f'{VERSION} · '
             f'© {self.tr("SettingInterface.About.Copyright")} {YEAR}, {AUTHOR}'),
            self.aboutGroup
        )
        self.projectCard = HyperlinkCard(
            REPO_URL,
            self.tr('SettingInterface.Project.Button.text'),
            Icon.REPO,
            self.tr('SettingInterface.Project.title'),
            self.tr('SettingInterface.Project.text'),
            self.aboutGroup
        )
        self.authorCard = HyperlinkCard(
            AUTHOR_URL,
            self.tr('SettingInterface.Author.Button.text'),
            Icon.CONTACT,
            self.tr('SettingInterface.Author.title'),
            self.tr('SettingInterface.Author.text', AUTHOR),
            self.aboutGroup
        )
        self.licenseCard = HyperlinkCard(
            LICENSE_URL,
            self.tr('SettingInterface.License.Button.text'),
            FIF.CERTIFICATE,
            self.tr('SettingInterface.License.title'),
            self.tr('SettingInterface.License.text'),
            self.aboutGroup
        )
        self.helpCard = HyperlinkCard(
            localizedWebsiteUrl(cfg.get(cfg.language).name()),
            self.tr('SettingInterface.Help.Button.text'),
            FIF.HELP,
            self.tr('SettingInterface.Help.title'),
            self.tr('SettingInterface.Help.text'),
            self.aboutGroup
        )
        self.feedbackCard = PrimaryPushSettingCard(
            self.tr('SettingInterface.ProvideFeedback.Button.text'),
            FIF.FEEDBACK,
            self.tr('SettingInterface.ProvideFeedback.title'),
            self.tr('SettingInterface.ProvideFeedback.text'),
            self.aboutGroup
        )
        self.__initWidget()

    def __initWidget(self):
        self.resize(1000, 800)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setViewportMargins(0, 100, 0, 20)
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)
        self.setObjectName('settingInterface')

        # initialize style sheet
        self.scrollWidget.setObjectName('scrollWidget')
        StyleSheet.FLUENT_INTERFACE.apply(self)

        self.micaCard.setEnabled(isWin11())
        self._syncTraySettingDependency(
            cfg.get(cfg.disableTrayIcon), persist=True)

        # initialize layout
        self.__initLayout()
        self._connectSignalToSlot()
        logger.info(self.tr('Log.Interface.Initialize.Success', self.tr('SettingInterface.Settings')))
        logInitialized('Log.Action.Settings')

    def __initLayout(self):
        self.titleLabel.move(36, 50)

        self.personalGroup.addSettingCard(self.micaCard)
        self.personalGroup.addSettingCard(self.trayIconCard)
        self.personalGroup.addSettingCard(self.themeCard)
        self.personalGroup.addSettingCard(self.zoomCard)
        self.personalGroup.addSettingCard(self.languageCard)

        self.downloadGroup.addSettingCard(self.saveFolderCard)
        self.downloadGroup.addSettingCard(self.aria2Card)

        self.netdiskGroup.addSettingCard(self.dirAheadCard)

        self.githubGroup.addSettingCard(self.githubMirrorCard)
        # self.githubGroup.addSettingCard(self.apiMirrorCard)

        self.updateSoftwareGroup.addSettingCard(self.updateOnStartUpCard)

        self.aboutGroup.addSettingCard(self.aboutCard)
        self.aboutGroup.addSettingCard(self.projectCard)
        self.aboutGroup.addSettingCard(self.authorCard)
        self.aboutGroup.addSettingCard(self.licenseCard)
        self.aboutGroup.addSettingCard(self.helpCard)
        self.aboutGroup.addSettingCard(self.feedbackCard)

        # add setting card group to layout
        self.expandLayout.setSpacing(28)
        self.expandLayout.setContentsMargins(36, 10, 36, 0)
        self.expandLayout.addWidget(self.personalGroup)
        self.expandLayout.addWidget(self.downloadGroup)
        self.expandLayout.addWidget(self.netdiskGroup)
        self.expandLayout.addWidget(self.githubGroup)
        self.expandLayout.addWidget(self.updateSoftwareGroup)
        self.expandLayout.addWidget(self.aboutGroup)

    def _showRestartTooltip(self):
        """ show restart tooltip """
        logChanged('Log.Action.Settings', self.tr('SettingInterface.RestartToolTip.text'))
        InfoBar.success(
            self.tr('SettingInterface.RestartToolTip.title'),
            self.tr('SettingInterface.RestartToolTip.text'),
            duration=1500,
            parent=self
        )

    def _connectSignalToSlot(self):
        """ connect signal to slot """
        cfg.appRestartSig.connect(self._showRestartTooltip)

        # personalization
        cfg.themeChanged.connect(self.onThemeChanged)
        self.micaCard.checkedChanged.connect(self.onMicaChanged)
        self.disableTrayIconSwitch.checkedChanged.connect(
            self.onTrayIconDisabledChanged)
        self.exitOnCloseSwitch.checkedChanged.connect(
            self.onExitOnCloseChanged)
        self.dirAheadCard.checkedChanged.connect(self.onDirAheadChanged)
        self.githubMirrorCard.checkedChanged.connect(
            lambda checked: logChanged('Log.Action.GitHubMirror', checked))
        self.updateOnStartUpCard.checkedChanged.connect(
            lambda checked: logChanged('Log.Action.UpdateCheck', checked))
        self.saveFolderCard.clicked.connect(self.onChooseSaveFolder)
        self.aria2Switch.checkedChanged.connect(self.onAria2EnabledChanged)
        self.aria2PathButton.clicked.connect(self.onChooseAria2Path)

        # check update
        self.aboutCard.clicked.connect(self.onCheckUpdate)

        # about
        self.helpCard.linkButton.clicked.connect(
            lambda: logAction('Log.Action.Settings', self.tr('SettingInterface.Help.title')))
        self.projectCard.linkButton.clicked.connect(
            lambda: logAction('Log.Action.Settings', self.tr('SettingInterface.Project.title')))
        self.authorCard.linkButton.clicked.connect(
            lambda: logAction('Log.Action.Settings', self.tr('SettingInterface.Author.title')))
        self.licenseCard.linkButton.clicked.connect(
            lambda: logAction('Log.Action.Settings', self.tr('SettingInterface.License.title')))
        self.feedbackCard.clicked.connect(self.onFeedback)

    def scrollToTop(self):
        """Scroll to the beginning of the settings interface."""
        logAction('Log.Action.SettingsSection', self.tr('SettingInterface.Settings'))
        self.verticalScrollBar().setValue(0)

    def scrollToAbout(self):
        """Scroll until the About group is visible."""
        logAction('Log.Action.SettingsSection', self.tr('SettingInterface.About'))
        self.ensureWidgetVisible(self.aboutGroup, 0, 20)

    def onThemeChanged(self, theme):
        logChanged('Log.Action.Theme', theme)
        setTheme(theme)

    def onChooseSaveFolder(self):
        logAction('Log.Action.SaveFolder', cfg.get(cfg.saveFolder))
        folder = QFileDialog.getExistingDirectory(
            self,
            self.tr('SettingInterface.DefaultSaveFolder.Dialog.title'),
            cfg.get(cfg.saveFolder),
        )
        if not folder:
            logChanged('Log.Action.SaveFolder', cfg.get(cfg.saveFolder), level='debug')
            return
        cfg.set(cfg.saveFolder, folder)
        self.saveFolderCard.setContent(folder)
        logChanged('Log.Action.SaveFolder', folder)

    def _aria2PathContent(self):
        return (
            cfg.get(cfg.aria2Path)
            or self.tr('SettingInterface.Aria2Path.AutoDetect')
        )

    def onAria2EnabledChanged(self, checked):
        cfg.set(cfg.aria2Enabled, checked)
        aria2DownloadService.reset()
        logChanged('Log.Action.Aria2Download', checked)

    def onChooseAria2Path(self):
        current = cfg.get(cfg.aria2Path)
        logAction('Log.Action.Aria2Path', current)
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr('SettingInterface.Aria2Path.Dialog.title'),
            current,
        )
        if not path:
            logChanged('Log.Action.Aria2Path', current, level='debug')
            return
        cfg.set(cfg.aria2Path, path)
        self.aria2PathGroup.setContent(path)
        aria2DownloadService.reset()
        logChanged('Log.Action.Aria2Path', path)

    def onMicaChanged(self, checked):
        logChanged('Log.Action.Mica', checked)
        signalBus.micaEnableChanged.emit(checked)

    def _syncTraySettingDependency(self, tray_disabled, persist=False):
        """Apply the requested master/dependent switch relationship."""
        force_exit = bool(tray_disabled)
        self.exitOnCloseSwitch.blockSignals(True)
        if force_exit:
            self.exitOnCloseSwitch.setChecked(True)
            if persist:
                cfg.set(cfg.exitOnClose, True)
        self.exitOnCloseSwitch.setEnabled(not tray_disabled)
        self.exitOnCloseSwitch.blockSignals(False)

    def onTrayIconDisabledChanged(self, checked):
        cfg.set(cfg.disableTrayIcon, checked)
        self._syncTraySettingDependency(checked, persist=True)
        signalBus.trayIconDisabledChanged.emit(checked)
        logChanged('Log.Action.SystemTray', not checked)

    def onExitOnCloseChanged(self, checked):
        if cfg.get(cfg.disableTrayIcon):
            self._syncTraySettingDependency(True, persist=True)
            return
        cfg.set(cfg.exitOnClose, checked)
        logChanged('Log.Action.Quit', checked)

    def onDirAheadChanged(self, checked):
        logChanged('Log.Action.FolderSorting', checked)
        signalBus.dirAheadChanged.emit()

    def onCheckUpdate(self):
        logAction('Log.Action.UpdateCheck')
        signalBus.checkUpdateSig.emit()

    def onFeedback(self):
        logAction('Log.Action.Feedback', FEEDBACK_URL)
        QDesktopServices.openUrl(QUrl(FEEDBACK_URL))
