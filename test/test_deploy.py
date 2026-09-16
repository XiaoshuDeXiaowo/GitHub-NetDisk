# coding: utf-8
import plistlib
import struct

import deploy


def test_localized_app_names_use_all_available_translations():
    assert deploy.getLocalizedAppNames() == {
        'en_us': 'GitHub NetDisk',
        'zh_cn': 'GitHub 网盘',
        'zh_hk': 'GitHub 網盤',
    }


def test_build_command_does_not_depend_on_build_system_language():
    windows_command = deploy.createBuildCommand('win32')
    mac_command = deploy.createBuildCommand('darwin')

    assert '--windows-file-description=GitHub NetDisk' in windows_command
    assert '--macos-app-name=GitHub-NetDisk' in mac_command
    assert '--include-package=keyring' in windows_command
    assert '--include-package=keyring' in mac_command
    assert '--collect-all' in deploy.createBuildCommand('linux')


def test_native_windows_arm_build_uses_matching_msys2_compiler(monkeypatch):
    monkeypatch.setenv('GITHUB_NETDISK_WINDOWS_ARM64', '1')
    command = deploy.createBuildCommand('win32')

    assert '--msvc=latest' not in command
    assert '--plugin-enable=pyqt5' not in command
    assert '--windows-target-version=win7' in command


def test_macos_bundle_contains_target_language_display_names(tmp_path):
    bundle = tmp_path / 'GitHub-NetDisk.app'
    contents = bundle / 'Contents'
    contents.mkdir(parents=True)
    with (contents / 'Info.plist').open('wb') as file:
        plistlib.dump({'CFBundleDisplayName': 'GitHub-NetDisk'}, file)

    deploy.localizeMacBundle(bundle)

    # Localization changes Finder's display name, never the bundle path.
    assert bundle.name == 'GitHub-NetDisk.app'
    assert bundle.is_dir()
    resources = contents / 'Resources'
    assert 'GitHub NetDisk' in (
        resources / 'en.lproj' / 'InfoPlist.strings'
    ).read_text(encoding='utf-8')
    assert 'GitHub 网盘' in (
        resources / 'zh-Hans.lproj' / 'InfoPlist.strings'
    ).read_text(encoding='utf-8')
    assert 'GitHub 網盤' in (
        resources / 'zh-Hant.lproj' / 'InfoPlist.strings'
    ).read_text(encoding='utf-8')
    with (contents / 'Info.plist').open('rb') as file:
        info = plistlib.load(file)
    assert info['LSHasLocalizedDisplayName'] is True
    assert info['CFBundleURLTypes'][0]['CFBundleURLSchemes'] == [
        'github-netdisk']


def test_windows_version_resources_are_language_specific():
    names = deploy.getLocalizedAppNames()
    simplified = deploy.createWindowsVersionInfo(0x0804, names['zh_cn'])
    traditional = deploy.createWindowsVersionInfo(0x0404, names['zh_hk'])
    english = deploy.createWindowsVersionInfo(0x0409, names['en_us'])

    assert struct.unpack_from('<H', simplified)[0] == len(simplified)
    assert 'GitHub 网盘'.encode('utf-16le') in simplified
    assert 'GitHub 網盤'.encode('utf-16le') in traditional
    assert 'GitHub NetDisk'.encode('utf-16le') in english
    assert struct.pack('<HH', 0x0804, 1200) in simplified
