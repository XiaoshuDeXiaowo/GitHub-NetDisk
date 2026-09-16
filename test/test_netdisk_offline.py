# coding: utf-8
"""Deterministic tests for the virtual file-system layer."""
from types import SimpleNamespace
from pathlib import Path

import pytest
from github import UnknownObjectException

import app.service.netdisk_service as netdisk_module
from app.service.netdisk_service import (
    NetdiskService,
    NetdiskItemType,
    _TransferCancelled,
    sanitizedDownloadError,
)
from app.service.github_service import releaseAssetName


@pytest.fixture
def disk(monkeypatch):
    value = object.__new__(NetdiskService)
    value._repo = SimpleNamespace(full_name='owner/repo')
    value._branch = 'main'
    value._cwd = '/'
    value._content = {
        'version': 1,
        'files': {
            'docs': {
                'readme.txt': {
                    ':file': 'release-1',
                    ':assets': ['readme.txt'],
                    ':hash': '',
                    ':size': 12,
                }
            }
        },
    }
    value.push_count = 0
    value.pushContent = lambda: setattr(value, 'push_count', value.push_count + 1)
    monkeypatch.setattr(netdisk_module, 'hasWriteAccess', lambda repo, token: True)
    return value


def test_abspath_does_not_mutate_cwd(disk):
    disk.chdir('/docs')
    assert disk.abspath('../other') == '/other'
    assert disk.getcwd() == '/docs'
    assert disk.abspath('/docs/readme.txt') == '/docs/readme.txt'


def test_set_repo_restores_previous_state_when_index_load_fails(
        disk, monkeypatch):
    previous_repo = disk._repo
    previous_branch = disk._branch
    previous_content = disk._content
    target = SimpleNamespace(full_name='owner/new', default_branch='main')
    monkeypatch.setattr(netdisk_module, 'getRepo', lambda *_args: target)
    monkeypatch.setattr(
        disk,
        'forceReload',
        lambda **_kwargs: (_ for _ in ()).throw(
            ValueError('netdisk.json is missing')),
    )

    with pytest.raises(ValueError, match='netdisk.json is missing'):
        disk.setRepo('owner/new')

    assert disk._repo is previous_repo
    assert disk._branch == previous_branch
    assert disk._content is previous_content


def test_folder_and_file_types(disk):
    assert disk.getItemType('/') == NetdiskItemType.FOLDER
    assert disk.isDir('/docs')
    assert disk.isFile('/docs/readme.txt')
    assert disk.listdir('/docs') == ['readme.txt']


def test_mkdir_creates_all_parents_once(disk):
    disk.mkdir('/photos/2026/july')
    assert disk.exists('/photos/2026/july')
    assert disk.push_count == 1


def test_copy_rename_and_remove(disk):
    disk.mkdir('/archive')
    disk.copy('/docs/readme.txt', '/archive/copy.txt')
    assert disk.isFile('/archive/copy.txt')
    disk.rename('/archive/copy.txt', '/archive/renamed.txt')
    assert not disk.exists('/archive/copy.txt')
    assert disk.exists('/archive/renamed.txt')
    disk.remove('/archive/renamed.txt', delete_release=False)
    assert not disk.exists('/archive/renamed.txt')


def test_remove_deletes_release_and_git_tag(disk):
    deleted = []
    disk._repo.get_release = lambda tag: SimpleNamespace(
        delete_release=lambda: deleted.append(('release', tag)))
    disk._repo.get_git_ref = lambda ref: SimpleNamespace(
        delete=lambda: deleted.append(('tag', ref)))

    disk.remove('/docs/readme.txt')

    assert deleted == [
        ('release', 'release-1'),
        ('tag', 'tags/release-1'),
    ]
    assert not disk.exists('/docs/readme.txt')


def test_remove_keeps_release_until_last_copied_reference_is_deleted(disk):
    deleted = []
    disk.mkdir('/archive')
    disk.copy('/docs/readme.txt', '/archive/copy.txt')
    disk._repo.get_release = lambda tag: SimpleNamespace(
        delete_release=lambda: deleted.append(('release', tag)))
    disk._repo.get_git_ref = lambda ref: SimpleNamespace(
        delete=lambda: deleted.append(('tag', ref)))

    disk.remove('/docs/readme.txt')
    assert deleted == []

    disk.remove('/archive/copy.txt')
    assert deleted == [
        ('release', 'release-1'),
        ('tag', 'tags/release-1'),
    ]


def test_rejects_invalid_operations(disk):
    with pytest.raises(ValueError):
        disk.rename('/docs/readme.txt', '/readme.txt')
    with pytest.raises(ValueError):
        disk.remove('/')
    with pytest.raises(ValueError):
        disk.abspath('/:reserved')


def test_upload_splits_assets_and_records_checksum(disk, monkeypatch, tmp_path):
    class Release:
        def __init__(self):
            self.assets = []

        def upload_asset(self, path, name=None):
            self.assets.append((name, Path(path).read_bytes()))

        def delete_release(self):
            raise AssertionError('successful upload must not delete its release')

    release = Release()

    def missing_release(tag):
        raise UnknownObjectException(404, {'message': 'not found'}, {})

    disk._repo.get_release = missing_release
    disk._repo.create_git_release = lambda *args, **kwargs: release
    monkeypatch.setattr(netdisk_module, 'MAX_ASSET_SIZE', 4)
    source = tmp_path / 'sample.bin'
    source.write_bytes(b'abcdefghij')

    progress = []
    statuses = []
    disk.uploadFile(
        str(source),
        '/uploads/sample.bin',
        tag='release-upload',
        progress=lambda current, total: progress.append((current, total)),
        status=lambda key, args: statuses.append((key, args)),
    )

    assert dict(release.assets) == {
        'sample.bin.part0001': b'abcd',
        'sample.bin.part0002': b'efgh',
        'sample.bin.part0003': b'ij',
    }
    metadata = disk.getContent('/uploads/sample.bin')
    assert metadata[':file'] == 'release-upload'
    assert metadata[':assets'] == [
        'sample.bin.part0001',
        'sample.bin.part0002',
        'sample.bin.part0003',
    ]
    assert metadata[':size'] == 10
    assert len(metadata[':hash']) == 64
    assert progress[0] == (0, 10)
    assert progress[-1] == (10, 10)
    assert [current for current, _total in progress] == sorted(
        current for current, _total in progress)
    assert statuses[0][0] == 'TaskInterface.PreparingUpload'
    assert ('TaskInterface.UploadingParts', (3, 3)) in statuses
    assert statuses[-2][0] == 'TaskInterface.VerifyingUpload'
    assert statuses[-1][0] == 'TaskInterface.UpdatingNetdiskIndex'


def test_native_release_upload_reports_streaming_progress(
        disk, monkeypatch, tmp_path):
    source = tmp_path / 'stream.bin'
    source.write_bytes(b'abcdefgh')
    calls = []
    progress = []

    class Response:
        def raise_for_status(self):
            pass

    def post(url, params, headers, data, timeout):
        chunks = []
        while chunk := data.read(2):
            chunks.append(chunk)
        calls.append((url, params, headers, b''.join(chunks), timeout))
        return Response()

    monkeypatch.setattr(netdisk_module.requests, 'post', post)
    monkeypatch.setattr(
        netdisk_module.authService, 'accessToken', lambda: 'secret-token')
    release = SimpleNamespace(
        upload_url='https://uploads.github.com/releases/1/assets{?name,label}')

    disk._uploadAsset(
        release, str(source), 'stream.bin', 0, 8,
        lambda current: progress.append(current))

    assert calls[0][0] == 'https://uploads.github.com/releases/1/assets'
    assert calls[0][1] == {'name': 'stream.bin'}
    assert calls[0][2]['Authorization'] == 'Bearer secret-token'
    assert calls[0][2]['Content-Length'] == '8'
    assert calls[0][3] == b'abcdefgh'
    assert progress[-1] == 8


def test_upload_plan_preserves_direct_link_eligible_files(monkeypatch):
    monkeypatch.setattr(netdisk_module, 'MAX_ASSET_SIZE', 10)

    assert NetdiskService._uploadPlan('archive.zip', 10) == [
        ('archive.zip', 0, 10),
    ]
    assert NetdiskService._uploadPlan('archive.zip', 11) == [
        ('archive.zip.part0001', 0, 10),
        ('archive.zip.part0002', 10, 1),
    ]


def test_release_asset_name_strips_chinese_and_uses_default_stem():
    assert releaseAssetName('  头像.jpg  ') == 'default.jpg'
    assert releaseAssetName('截图 final.png') == 'final.png'
    assert NetdiskService._uploadPlan('头像.jpg', 10) == [
        ('default.jpg', 0, 10),
    ]


def test_resumable_upload_skips_completed_assets(disk, monkeypatch, tmp_path):
    class Asset:
        def __init__(self, name, content):
            self.name = name
            self.content = content
            self.size = len(content)
            self.deleted = False

        def delete_asset(self):
            self.deleted = True

    class Release:
        def __init__(self):
            self.assets = [Asset('sample.bin.part0001', b'abcd')]
            self.uploaded_names = []

        def get_assets(self):
            return [asset for asset in self.assets if not asset.deleted]

        def upload_asset(self, path, name=None):
            content = Path(path).read_bytes()
            self.assets.append(Asset(name, content))
            self.uploaded_names.append(name)

        def delete_release(self):
            raise AssertionError('resumable upload must preserve its release')

    release = Release()
    disk._repo.get_release = lambda _tag: release
    monkeypatch.setattr(netdisk_module, 'MAX_ASSET_SIZE', 4)
    source = tmp_path / 'sample.bin'
    source.write_bytes(b'abcdefghij')
    resume_data = netdisk_module.createUploadResumeData(
        str(source), 'release-resume')
    progress = []

    disk.uploadFile(
        str(source), '/uploads/sample.bin',
        progress=lambda current, total: progress.append((current, total)),
        resumeData=resume_data,
    )

    assert set(release.uploaded_names) == {
        'sample.bin.part0002', 'sample.bin.part0003'}
    assert progress[0] == (4, 10)
    assert progress[-1] == (10, 10)
    assert disk.getContent('/uploads/sample.bin')[':assets'] == [
        'sample.bin.part0001',
        'sample.bin.part0002',
        'sample.bin.part0003',
    ]


def test_private_download_link_uses_github_asset_api(disk, monkeypatch):
    asset = SimpleNamespace(
        id=123456,
        name='readme.txt',
        browser_download_url=(
            'https://github.com/owner/repo/releases/download/release-1/readme.txt'
        ),
    )
    disk._repo.private = True
    disk._repo.get_release = lambda tag: SimpleNamespace(get_assets=lambda: [asset])
    assert disk.getDownloadLink('/docs/readme.txt') == (
        'https://api.github.com/repos/owner/repo/releases/assets/123456'
    )


def test_public_download_link_uses_fastest_proxy_node(disk, monkeypatch):
    asset = SimpleNamespace(
        id=123456,
        name='readme.txt',
        browser_download_url=(
            'https://github.com/owner/repo/releases/download/release-1/readme.txt'
        ),
    )
    disk._repo.private = False
    disk._repo.get_release = lambda tag: SimpleNamespace(
        get_assets=lambda: [asset])
    monkeypatch.setattr(
        netdisk_module,
        'getFastestGithubMirror',
        lambda url: 'fast.example',
    )

    statuses = []
    assert disk.getDownloadLink(
        '/docs/readme.txt',
        status=lambda key, args: statuses.append((key, args)),
    ) == (
        'http://fast.example//owner/repo/releases/download/release-1/readme.txt'
    )
    assert statuses == [
        ('TaskInterface.ResolvingDownloadLink', ()),
        ('TaskInterface.TestingDownloadMirror', ()),
    ]


def test_private_asset_api_download_uses_required_headers(
        disk, monkeypatch, tmp_path):
    destination = tmp_path / 'readme.txt'
    calls = []
    monkeypatch.setattr(
        disk,
        'getDownloadLink',
        lambda path, status=None: (
            'https://api.github.com/repos/owner/repo/releases/assets/123456'),
    )

    def get_config(item):
        return item is netdisk_module.cfg.aria2Enabled

    monkeypatch.setattr(netdisk_module.cfg, 'get', get_config)
    monkeypatch.setattr(
        netdisk_module.authService, 'accessToken', lambda: 'secret')

    def download(links, output, total=0, progress=None, headers=None,
                 status=None, cancel_event=None):
        calls.append((links, headers))
        Path(output).write_bytes(b'hello world!')

    monkeypatch.setattr(netdisk_module.aria2DownloadService, 'download', download)

    assert disk.downloadFile('/docs/readme.txt', str(destination)) == str(destination)
    assert calls == [([(
        'https://api.github.com/repos/owner/repo/releases/assets/123456'
    )], {
        'Accept': 'application/octet-stream',
        'X-GitHub-Api-Version': '2022-11-28',
        'Authorization': 'Bearer secret',
    })]


def test_download_file_prefers_aria2(disk, monkeypatch, tmp_path):
    destination = tmp_path / 'readme.txt'
    calls = []
    monkeypatch.setattr(
        disk, 'getDownloadLink',
        lambda path, status=None: 'https://example.com/file')
    monkeypatch.setattr(
        netdisk_module.cfg,
        'get',
        lambda item: item is netdisk_module.cfg.aria2Enabled,
    )

    def download(links, output, total=0, progress=None, headers=None,
                 status=None, cancel_event=None):
        calls.append((links, total, headers))
        Path(output).write_bytes(b'hello world!')
        if progress:
            progress(12, 12)

    monkeypatch.setattr(netdisk_module.aria2DownloadService, 'download', download)
    monkeypatch.setattr(
        netdisk_module.requests,
        'get',
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError('requests fallback should not be used')),
    )

    statuses = []
    assert disk.downloadFile(
        '/docs/readme.txt', str(destination),
        status=lambda key, args: statuses.append((key, args)),
    ) == str(destination)
    assert destination.read_bytes() == b'hello world!'
    assert calls == [(['https://example.com/file'], 12, {})]
    assert [key for key, _args in statuses] == [
        'TaskInterface.StartingAria2',
        'TaskInterface.DownloadingFile',
        'TaskInterface.VerifyingDownload',
    ]


def test_download_file_falls_back_when_aria2_is_unavailable(disk, monkeypatch, tmp_path):
    destination = tmp_path / 'readme.txt'
    request_headers = []
    monkeypatch.setattr(
        disk,
        'getDownloadLink',
        lambda path, status=None: 'https://user:secret@mirror.example/file',
    )
    monkeypatch.setattr(
        netdisk_module.cfg,
        'get',
        lambda item: item is netdisk_module.cfg.aria2Enabled,
    )
    monkeypatch.setattr(
        netdisk_module.authService, 'accessToken', lambda: 'secret')
    monkeypatch.setattr(
        netdisk_module.aria2DownloadService,
        'download',
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError('aria2 unavailable')),
    )

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def raise_for_status(self):
            pass

        def iter_content(self, size):
            yield b'hello world!'

    def get(url, headers=None, **kwargs):
        request_headers.append(headers)
        return Response()

    monkeypatch.setattr(netdisk_module.requests, 'get', get)

    assert disk.downloadFile('/docs/readme.txt', str(destination)) == str(destination)
    assert destination.read_bytes() == b'hello world!'
    assert request_headers == [{}]


def test_download_file_does_not_fallback_after_aria2_cancel(
        disk, monkeypatch, tmp_path):
    destination = tmp_path / 'readme.txt'
    cancel_event = SimpleNamespace(is_set=lambda: True)
    monkeypatch.setattr(
        disk,
        'getDownloadLink',
        lambda path, status=None: 'https://example.com/file',
    )
    monkeypatch.setattr(
        netdisk_module.cfg,
        'get',
        lambda item: item is netdisk_module.cfg.aria2Enabled,
    )
    monkeypatch.setattr(
        netdisk_module.aria2DownloadService,
        'download',
        lambda *args, **kwargs: (_ for _ in ()).throw(
            IOError('download cancelled')),
    )
    monkeypatch.setattr(
        netdisk_module.requests,
        'get',
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError('requests fallback should not be used')),
    )

    with pytest.raises(_TransferCancelled):
        disk.downloadFile(
            '/docs/readme.txt',
            str(destination),
            cancel_event=cancel_event,
        )


def test_download_file_skips_aria2_when_disabled(disk, monkeypatch, tmp_path):
    destination = tmp_path / 'readme.txt'
    monkeypatch.setattr(
        disk,
        'getDownloadLink',
        lambda path, status=None: 'https://example.com/file',
    )
    monkeypatch.setattr(
        netdisk_module.cfg,
        'get',
        lambda item: False if item is netdisk_module.cfg.aria2Enabled else '',
    )
    monkeypatch.setattr(
        netdisk_module.aria2DownloadService,
        'download',
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError('aria2 should be disabled')),
    )

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def raise_for_status(self):
            pass

        def iter_content(self, size):
            yield b'hello world!'

    monkeypatch.setattr(
        netdisk_module.requests,
        'get',
        lambda *args, **kwargs: Response(),
    )

    assert disk.downloadFile('/docs/readme.txt', str(destination)) == str(destination)
    assert destination.read_bytes() == b'hello world!'


def test_authenticated_download_errors_are_redacted():
    error = 'failed: https://user:top-secret@mirror.example/file'
    redacted = sanitizedDownloadError(error)

    assert 'top-secret' not in redacted
    assert 'https://***:***@mirror.example/file' in redacted
