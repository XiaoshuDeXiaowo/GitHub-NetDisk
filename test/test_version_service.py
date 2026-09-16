# coding: utf-8
from pathlib import Path
from types import SimpleNamespace

from app.service.version_service import VersionService
from app.view.main_window import MainWindow


def test_version_service_reads_latest_release(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                'tag_name': 'v1.2.0',
                'name': 'Alpha Release 1.2.0',
                'html_url': 'https://example.test/releases/v1.2.0',
                'assets': [{
                    'name': 'GitHub-NetDisk-v1.2.0-Windows-x86_64-Setup.exe',
                    'browser_download_url': 'https://example.test/setup.exe',
                }],
            }

    calls = []
    monkeypatch.setattr(
        'app.service.version_service.requests.get',
        lambda *args, **kwargs: calls.append((args, kwargs)) or Response(),
    )
    monkeypatch.setattr('app.service.version_service.sys.platform', 'win32')
    monkeypatch.setattr(
        'app.service.version_service.platform.machine',
        lambda: 'AMD64',
    )

    service = VersionService()
    service.currentVersion = '1.0.0'

    assert service.hasNewVersion()
    assert service.lastestVersion == '1.2.0'
    assert service.latestReleaseTitle == 'Alpha Release 1.2.0'
    assert service.installAsset['browser_download_url'].endswith('setup.exe')
    assert calls[0][1]['timeout'] == 5


def test_version_service_selects_platform_installer():
    service = VersionService()
    assets = [
        {'name': 'GitHub-NetDisk-v1.2.0-Windows-x86_64-Setup.exe'},
        {'name': 'GitHub-NetDisk-v1.2.0-macOS-arm64.dmg'},
        {'name': 'GitHub-NetDisk-v1.2.0-Linux-arm64.deb'},
    ]

    assert service.selectInstallerAsset(
        assets, system='win32', machine='AMD64')['name'].endswith('Setup.exe')
    assert service.selectInstallerAsset(
        assets, system='darwin', machine='arm64')['name'].endswith('.dmg')
    assert service.selectInstallerAsset(
        assets, system='linux', machine='aarch64')['name'].endswith('.deb')


def test_windows_arm_uses_x64_installer_as_fallback(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                'tag_name': 'v1.2.0',
                'name': 'Alpha Release 1.2.0',
                'assets': [{
                    'name': 'GitHub-NetDisk-v1.2.0-Windows-x86_64-Setup.exe',
                }],
            }

    monkeypatch.setattr(
        'app.service.version_service.requests.get',
        lambda *args, **kwargs: Response(),
    )
    monkeypatch.setattr('app.service.version_service.sys.platform', 'win32')
    monkeypatch.setattr(
        'app.service.version_service.platform.machine',
        lambda: 'ARM64',
    )

    service = VersionService()
    service.currentVersion = '1.0.0'

    assert service.hasNewVersion()
    assert service.usingFallbackInstaller is True
    assert 'x86_64' in service.installAsset['name']


def test_update_prompt_uses_release_title_and_development_stage(monkeypatch):
    messages = []
    window = SimpleNamespace(
        _checkingUpdate=True,
        tr=lambda key, args=(): {
            'UpdateCheck.DownloadInstaller.text':
            'current=%s latest=%s',
            'UpdateCheck.NewVersion.title': 'new',
        }.get(key, key) % args if args else key,
        showMessage=lambda *args, **kwargs: messages.append((args, kwargs)) or False,
    )
    service = SimpleNamespace(
        currentVersion='1.0.0',
        lastestVersion='1.2.0',
        latestReleaseTitle='Alpha Release 1.2.0',
        installAsset={'name': 'installer'},
        usingFallbackInstaller=False,
    )
    monkeypatch.setattr('app.view.main_window.versionService', service)
    monkeypatch.setattr(
        'app.view.main_window.logChanged', lambda *args, **kwargs: None)

    MainWindow.onVersionInfoFetched(window, True)

    assert messages[0][0][1] == 'current=1.0.0 (Alpha) latest=Alpha Release 1.2.0'


def test_update_prompt_explains_when_no_binary_is_available(monkeypatch):
    messages = []
    window = SimpleNamespace(
        _checkingUpdate=True,
        tr=lambda key, args=(): key,
        showMessage=lambda *args, **kwargs: messages.append((args, kwargs)),
    )
    service = SimpleNamespace(
        currentVersion='1.0.0',
        lastestVersion='1.2.0',
        latestReleaseTitle='Alpha Release 1.2.0',
        installAsset=None,
        usingFallbackInstaller=False,
    )
    monkeypatch.setattr('app.view.main_window.versionService', service)
    monkeypatch.setattr(
        'app.view.main_window.logChanged', lambda *args, **kwargs: None)

    MainWindow.onVersionInfoFetched(window, True)

    assert messages[0][0][:2] == (
        'UpdateCheck.Unsupported.title',
        'UpdateCheck.Unsupported.text',
    )
    assert messages[0][1]['showCancelButton'] is False


def test_download_installer_uses_update_folder(monkeypatch, tmp_path):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def raise_for_status(self):
            pass

        def iter_content(self, _size):
            yield b'installer'

    monkeypatch.setattr(
        'app.service.version_service.CONFIG_FOLDER',
        tmp_path,
    )
    monkeypatch.setattr(
        'app.service.version_service.requests.get',
        lambda *args, **kwargs: Response(),
    )
    service = VersionService()
    service.installAsset = {
        'name': 'GitHub-NetDisk-v1.2.0-Windows-x86_64-Setup.exe',
        'browser_download_url': 'https://example.test/setup.exe',
        'size': len(b'installer'),
    }

    path = Path(service.downloadInstaller())

    assert path == tmp_path / 'updates' / service.installAsset['name']
    assert path.read_bytes() == b'installer'


def test_update_check_no_update_shows_message(monkeypatch):
    messages = []
    window = SimpleNamespace(
        _checkingUpdate=True,
        tr=lambda key, args=(): key,
        showMessage=lambda *args, **kwargs: messages.append((args, kwargs)),
    )
    monkeypatch.setattr(
        'app.view.main_window.logChanged',
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        'app.view.main_window.versionService.currentVersion',
        '1.0.0',
    )
    monkeypatch.setattr(
        'app.view.main_window.versionService.lastestVersion',
        '1.0.0',
    )

    MainWindow.onVersionInfoFetched(window, False, False)

    assert window._checkingUpdate is False
    assert messages[0][0][:2] == (
        'UpdateCheck.NoUpdate.title',
        'UpdateCheck.NoUpdate.text',
    )
    assert messages[0][1]['showYesButton'] is True
    assert messages[0][1]['showCancelButton'] is False


def test_update_download_infobar_is_not_closable(monkeypatch):
    info_bars = []
    window = SimpleNamespace(
        tr=lambda key, args=(): key,
        window=lambda: None,
        _updateDownloadInfoBar=None,
        _closeUpdateDownloadInfoBar=lambda: None,
        _onUpdateInstallerDownloaded=lambda *_args: None,
        _onUpdateDownloadFailed=lambda *_args: None,
    )
    monkeypatch.setattr(
        'app.view.main_window.logStarted',
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        'app.view.main_window.TaskExecutor.run',
        lambda *_args, **_kwargs: SimpleNamespace(
            result=SimpleNamespace(connect=lambda *_args: None),
            failed=SimpleNamespace(connect=lambda *_args: None),
        ),
    )
    monkeypatch.setattr(
        'app.view.main_window.InfoBar.info',
        lambda *args, **kwargs: info_bars.append((args, kwargs)) or 'bar',
    )

    MainWindow.downloadAndInstallUpdate(window)

    assert window._updateDownloadInfoBar == 'bar'
    assert info_bars[0][1]['isClosable'] is False
    assert info_bars[0][1]['duration'] == -1


def test_downloaded_installer_starts_and_prompts_user(monkeypatch):
    started = []
    messages = []
    closed = []
    quit_called = []
    window = SimpleNamespace(
        tr=lambda key, args=(): key,
        window=lambda: None,
        _updateDownloadInfoBar=SimpleNamespace(close=lambda: closed.append(True)),
        _closeUpdateDownloadInfoBar=lambda: MainWindow._closeUpdateDownloadInfoBar(window),
        showMessage=lambda *args, **kwargs: messages.append((args, kwargs)) or True,
        quitApplication=lambda: quit_called.append(True),
    )
    monkeypatch.setattr(
        'app.view.main_window.logChanged',
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        'app.view.main_window.InfoBar.success',
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        'app.view.main_window.versionService.startInstaller',
        lambda path: started.append(path),
    )

    MainWindow._onUpdateInstallerDownloaded(window, 'C:/temp/setup.exe')

    assert closed == [True]
    assert window._updateDownloadInfoBar is None
    assert started == ['C:/temp/setup.exe']
    assert messages[0][0][:2] == (
        'UpdateCheck.InstallerStarted.title',
        'UpdateCheck.InstallerStarted.text',
    )
    assert messages[0][1]['showCancelButton'] is False
    assert quit_called == [True]
