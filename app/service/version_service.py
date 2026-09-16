# coding: utf-8
"""Application update checks based on GitHub Releases."""
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

import requests
from PyQt5.QtCore import QVersionNumber

from ..common.exception_handler import exceptionHandler
from ..common.setting import CONFIG_FOLDER, RELEASE_URL, VERSION


LATEST_RELEASE_API = (
    'https://api.github.com/repos/XiaoshuDeXiaowo/GitHub-NetDisk/releases/latest'
)


def _normalizedArchitecture(machine=None):
    value = str(machine or platform.machine()).lower()
    if value in ('amd64', 'x64', 'x86_64'):
        return 'x86_64'
    if value in ('arm64', 'aarch64'):
        return 'arm64'
    return value


class VersionService:
    """ Version service """

    def __init__(self):
        self.currentVersion = VERSION
        self.lastestVersion = VERSION
        self.latestReleaseTitle = VERSION
        self.releaseUrl = RELEASE_URL
        self.installAsset = None
        self.usingFallbackInstaller = False
        self.versionPattern = re.compile(r'v?(\d+)\.(\d+)\.(\d+)')

    @exceptionHandler(VERSION)
    def getLatestVersion(self):
        """ get latest version """
        release = self._latestRelease()
        self.releaseUrl = str(release.get('html_url') or RELEASE_URL)
        self.installAsset = None
        self.usingFallbackInstaller = False
        version = str(release.get('tag_name') or '')
        match = self.versionPattern.search(version)
        if not match:
            return VERSION
        self.lastestVersion = version.lstrip('v')
        self.latestReleaseTitle = str(
            release.get('name') or self.lastestVersion)
        assets = release.get('assets') or []
        self.installAsset = self.selectInstallerAsset(assets)
        if self.installAsset is None and sys.platform == 'win32':
            # Windows on ARM can run the x64 build through its compatibility
            # layer. Prefer that release over reporting no installer at all.
            if _normalizedArchitecture() == 'arm64':
                self.installAsset = self.selectInstallerAsset(
                    assets, system='win32', machine='x86_64')
                self.usingFallbackInstaller = self.installAsset is not None
        return self.lastestVersion

    def hasNewVersion(self):
        """ check whether there is a new version """
        version, _ = QVersionNumber.fromString(self.getLatestVersion())
        currentVersion, _ = QVersionNumber.fromString(self.currentVersion)
        return version > currentVersion

    def _latestRelease(self):
        response = requests.get(
            LATEST_RELEASE_API,
            headers={'User-Agent': 'GitHub-NetDisk'},
            timeout=5,
            allow_redirects=True,
        )
        response.raise_for_status()
        return response.json()

    def selectInstallerAsset(self, assets, system=None, machine=None):
        """Choose the installer asset for the current operating system."""
        system = system or sys.platform
        arch = _normalizedArchitecture(machine)
        candidates = []
        if system == 'win32':
            candidates = [(f'Windows-{arch}-Setup', '.exe')]
        elif system == 'darwin':
            candidates = [(f'macOS-{arch}', '.dmg')]
        elif system.startswith('linux'):
            candidates = [(f'Linux-{arch}', '.deb')]
        else:
            return None

        for marker, suffix in candidates:
            for asset in assets:
                name = str(asset.get('name') or '')
                if marker in name and name.endswith(suffix):
                    return asset
        return None

    def downloadInstaller(self):
        """Download the selected installer asset and return its local path."""
        if not self.installAsset:
            self.getLatestVersion()
        if not self.installAsset:
            raise RuntimeError('No installer asset matches this system.')

        name = str(self.installAsset.get('name') or '').strip()
        url = str(self.installAsset.get('browser_download_url') or '').strip()
        if not name or not url:
            raise RuntimeError('Installer asset is missing download information.')

        update_folder = CONFIG_FOLDER / 'updates'
        update_folder.mkdir(parents=True, exist_ok=True)
        target = update_folder / name
        expected_size = int(self.installAsset.get('size') or 0)
        if target.is_file() and (not expected_size or target.stat().st_size == expected_size):
            return str(target)

        temp_path = target.with_suffix(target.suffix + '.download')
        with requests.get(url, stream=True, timeout=(10, 120)) as response:
            response.raise_for_status()
            with temp_path.open('wb') as file:
                for chunk in response.iter_content(1024 * 1024):
                    if chunk:
                        file.write(chunk)
        temp_path.replace(target)
        return str(target)

    def startInstaller(self, path):
        """Start the downloaded installer using the current platform behavior."""
        path = str(Path(path).absolute())
        if sys.platform == 'win32':
            os.startfile(path)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', path])
        else:
            subprocess.Popen(['xdg-open', path])
        return True


versionService = VersionService()
