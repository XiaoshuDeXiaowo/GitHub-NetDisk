# coding: utf-8
from types import SimpleNamespace

import pytest

from app.service import auth_service as auth_module
from app.service.auth_service import (
    AUTH_GITHUB_APP,
    AUTH_PAT,
    AuthConfigurationError,
    AuthError,
    AuthService,
    DeviceFlowCancelled,
    DeviceFlowSession,
)


class FakeStore:
    def __init__(self, token=''):
        self.token = token
        self.deleted = False

    def get(self):
        return self.token

    def set(self, token):
        self.token = token

    def delete(self):
        self.token = ''
        self.deleted = True


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self.data


class FakeHttp:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(self.responses.pop(0))


class FakeConfig:
    loginType = object()
    authExpiresAt = object()
    userLoginCache = object()
    usernameCache = object()

    def __init__(self):
        self.values = {
            self.loginType: 'Anonymous',
            self.authExpiresAt: 0,
            self.userLoginCache: '',
            self.usernameCache: '',
        }

    def get(self, item):
        return self.values[item]

    def set(self, item, value):
        self.values[item] = value


class NoWaitEvent:
    def __init__(self, cancelled=False):
        self.cancelled = cancelled
        self.waits = []

    def wait(self, timeout):
        self.waits.append(timeout)
        return self.cancelled


def test_device_flow_requires_a_configured_client_id():
    service = AuthService(client_id='', store=FakeStore(), http=FakeHttp())

    with pytest.raises(AuthConfigurationError):
        service.requestDeviceCode()


def test_request_device_code_uses_public_client_id_with_repo_scope():
    http = FakeHttp({
        'device_code': 'device-secret',
        'user_code': 'ABCD-EFGH',
        'verification_uri': 'https://github.com/login/device',
        'expires_in': 900,
        'interval': 5,
    })
    service = AuthService(client_id='Iv1.public', store=FakeStore(), http=http)

    session = service.requestDeviceCode()

    assert session.user_code == 'ABCD-EFGH'
    assert http.calls == [(
            auth_module.DEVICE_CODE_URL,
            {
                'data': {
                    'client_id': 'Iv1.public',
                    'scope': 'repo',
                },
            'headers': {'Accept': 'application/json'},
            'timeout': 15,
        },
    )]


def test_device_flow_handles_pending_and_slow_down(monkeypatch):
    http = FakeHttp(
        {'error': 'authorization_pending'},
        {'error': 'slow_down'},
        {'access_token': 'ghu_secret', 'expires_in': 3600},
    )
    store = FakeStore()
    service = AuthService(client_id='Iv1.public', store=store, http=http)
    session = DeviceFlowSession(
        'device-secret', 'ABCD-EFGH',
        'https://github.com/login/device', 900, 0)
    event = NoWaitEvent()
    user = SimpleNamespace(login='octocat', name='The Octocat')
    monkeypatch.setattr(
        auth_module, 'Github',
        lambda auth=None: SimpleNamespace(get_user=lambda: user),
    )

    authorization = service.waitForDeviceAuthorization(session, event)

    assert authorization.access_token == 'ghu_secret'
    assert authorization.login == 'octocat'
    assert store.token == ''  # committed later on the Qt/UI thread
    assert event.waits == [0, 0, 5]


def test_completing_device_flow_persists_mode_and_identity(monkeypatch):
    fake_cfg = FakeConfig()
    store = FakeStore()
    service = AuthService(client_id='Iv1.public', store=store, http=FakeHttp())
    monkeypatch.setattr(auth_module, 'cfg', fake_cfg)
    authorization = auth_module.DeviceAuthorization(
        'ghu_secret', 'octocat', 'The Octocat', 3600)

    identity = service.completeDeviceAuthorization(authorization)

    assert identity.mode == AUTH_GITHUB_APP
    assert store.token == 'ghu_secret'
    assert fake_cfg.get(fake_cfg.loginType) == 'GitHubApp'
    assert fake_cfg.get(fake_cfg.userLoginCache) == 'octocat'
    assert fake_cfg.get(fake_cfg.usernameCache) == 'The Octocat'
    assert fake_cfg.get(fake_cfg.authExpiresAt) > 0


def test_pat_storage_does_not_fall_back_to_plaintext(monkeypatch):
    class RejectingStore(FakeStore):
        def set(self, token):
            raise AuthError('credential store unavailable')

    fake_cfg = FakeConfig()
    service = AuthService(store=RejectingStore(), http=FakeHttp())
    monkeypatch.setattr(auth_module, 'cfg', fake_cfg)

    with pytest.raises(AuthError):
        service.storeToken('github_pat_secret', AUTH_PAT, ('octocat', 'Octocat'))

    assert fake_cfg.get(fake_cfg.loginType) == 'Anonymous'


def test_disconnect_clears_keyring_and_sets_login_type(monkeypatch):
    fake_cfg = FakeConfig()
    store = FakeStore('ghu_secret')
    service = AuthService(store=store, http=FakeHttp())
    monkeypatch.setattr(auth_module, 'cfg', fake_cfg)

    service.disconnect()

    assert store.deleted
    assert fake_cfg.get(fake_cfg.loginType) == 'Anonymous'
    assert fake_cfg.get(fake_cfg.userLoginCache) == ''


def test_device_flow_can_be_cancelled_without_polling():
    http = FakeHttp()
    service = AuthService(client_id='Iv1.public', store=FakeStore(), http=http)
    session = DeviceFlowSession(
        'device-secret', 'ABCD-EFGH',
        'https://github.com/login/device', 900, 5)

    with pytest.raises(DeviceFlowCancelled):
        service.waitForDeviceAuthorization(
            session, NoWaitEvent(cancelled=True))

    assert http.calls == []
