# coding: utf-8
from types import SimpleNamespace

from app.service import github_service
from app.common.config import cfg
from app.common.setting import GITHUB_MIRRORS


def test_get_user_name_uses_profile_name_not_login(monkeypatch):
    github_service.getUserName.cache_clear()
    user = SimpleNamespace(
        url='https://api.github.com/user',
        login='account-login',
        name='Profile Name',
    )
    monkeypatch.setattr(github_service, 'getUserByToken', lambda token: user)

    assert github_service.getUserName('token-with-name') == 'Profile Name'


def test_get_user_name_falls_back_to_login(monkeypatch):
    github_service.getUserName.cache_clear()
    user = SimpleNamespace(
        url='https://api.github.com/user',
        login='account-login',
        name=None,
    )
    monkeypatch.setattr(github_service, 'getUserByToken', lambda token: user)

    assert github_service.getUserName('token-without-name') == 'account-login'


def test_ghproxy_next_nodes_are_stored_as_static_unique_domains():
    assert len(GITHUB_MIRRORS) >= 74
    assert len(set(GITHUB_MIRRORS)) == len(GITHUB_MIRRORS)
    assert any(node.startswith('gh.dpik.top/') for node in GITHUB_MIRRORS)
    assert any(node.startswith('gh.ruan.dpdns.org/') for node in GITHUB_MIRRORS)


def test_proxy_url_uses_mirror_path_for_source_url():
    source = 'https://github.com/owner/repo/releases/download/v1/file.zip'
    assert github_service.githubProxyUrl(source, 'mirror.example') == (
        'http://mirror.example//owner/repo/releases/download/v1/file.zip'
    )


def test_each_selection_uses_the_current_fastest_node(monkeypatch):
    monkeypatch.setattr(cfg, 'get', lambda item: True)
    monkeypatch.setattr(
        github_service,
        'GITHUB_MIRRORS',
        ('slow.example', 'fast.example', 'down.example'),
    )
    speeds = {
        'slow.example': 100,
        'fast.example': 900,
        'down.example': None,
    }
    calls = []

    def measure(mirror, target_url):
        calls.append((mirror, target_url))
        speed = speeds[mirror]
        return None if speed is None else (mirror, speed)

    monkeypatch.setattr(github_service, '_measureGithubMirrorSpeed', measure)
    target = 'https://github.com/owner/repo/releases/download/v1/file.zip'

    assert github_service.getFastestGithubMirror(target) == 'fast.example'
    assert {mirror for mirror, _ in calls} == set(speeds)


def test_mirror_selection_is_skipped_when_disabled(monkeypatch):
    monkeypatch.setattr(cfg, 'get', lambda item: False)
    monkeypatch.setattr(
        github_service,
        '_measureGithubMirrorSpeed',
        lambda *args: (_ for _ in ()).throw(
            AssertionError('disabled mirror must not be measured')),
    )

    assert github_service.getFastestGithubMirror(
        'https://github.com/owner/repo/releases/download/v1/file.zip'
    ) is None
