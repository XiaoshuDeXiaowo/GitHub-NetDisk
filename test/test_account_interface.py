# coding: utf-8
from types import SimpleNamespace

from app.view.account_interface import AccountInterface


def test_github_app_authorization_opens_installation_page(monkeypatch):
    opened = []
    identity = SimpleNamespace(login='octocat', name='The Octocat')
    account = SimpleNamespace(
        _cancelEvent=SimpleNamespace(is_set=lambda: False),
        connectButton=SimpleNamespace(setEnabled=lambda value: None),
        saveButton=SimpleNamespace(setEnabled=lambda value: None),
        copyCodeButton=SimpleNamespace(setEnabled=lambda value: None),
        deviceCodeLabel=SimpleNamespace(hide=lambda: None),
        refreshStatus=lambda: None,
        window=lambda: None,
        tr=lambda key, args=(): key,
    )

    monkeypatch.setattr(
        'app.view.account_interface.authService.completeDeviceAuthorization',
        lambda authorization: identity,
    )
    monkeypatch.setattr(
        'app.view.account_interface.authService.installationUrl',
        lambda: 'https://github.com/apps/gh-netdisk/installations/new',
    )
    monkeypatch.setattr(
        'app.view.account_interface.openUrl',
        lambda url: opened.append(url),
    )
    monkeypatch.setattr(
        'app.view.account_interface.InfoBar.success',
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        'app.view.account_interface.logSucceeded',
        lambda *args, **kwargs: None,
    )

    AccountInterface._githubLoginSucceeded(account, object())

    assert opened == [
        'https://github.com/apps/gh-netdisk/installations/new']
