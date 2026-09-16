# encoding: utf-8
import logging
import posixpath
import re
import traceback
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from getpass import getuser
from ..common.utils import lru_cache_noexcept as lru_cache
from time import monotonic
from urllib.parse import urlsplit, urlunsplit
from loguru import logger
from github import Auth, Github
from PyQt5.QtGui import QPixmap, QImage

from ..common.exception_handler import exceptionHandler
from ..common.event_logger import (
    exceptionDetail,
    logChanged,
    logFailed,
    logStarted,
    logSucceeded,
)
from ..common.translator import translate
from ..common.setting import GITHUB_MIRRORS


MIRROR_SPEED_SAMPLE_SIZE = 32 * 1024
MIRROR_SPEED_MAX_WORKERS = 32
MIRROR_SPEED_TIMEOUT = (1.0, 2.0)
_CHINESE_RE = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]')
_rateLimitLogHandler = None


def releaseAssetName(name, default_stem='default'):
    """Return an asset name suitable for direct Release download URLs."""
    value = str(name or '').replace('\\', '/')
    value = posixpath.basename(value)
    stem, suffix = posixpath.splitext(value)
    stem = _CHINESE_RE.sub('', stem).strip()
    suffix = _CHINESE_RE.sub('', suffix).strip()
    if not stem:
        stem = default_stem
    return f'{stem}{suffix}'


def isGithubRateLimitLogMessage(message):
    """Return whether a PyGithub log line describes API rate limiting."""
    value = str(message or '').lower()
    return (
        'rate limit exceeded' in value
        or 'retry-able primary rate limit error' in value
        or 'retry-able secondary rate limit error' in value
        or 'setting next backoff' in value
        or 'retrying after' in value
    )


class GithubRateLimitLogHandler(logging.Handler):
    """Emit a Qt signal when PyGithub announces API rate limiting."""

    def emit(self, record):
        try:
            message = record.getMessage()
            if isGithubRateLimitLogMessage(message):
                from ..common.signal_bus import signalBus
                signalBus.githubRateLimitSig.emit(message)
        except Exception:
            self.handleError(record)


def installGithubRateLimitMonitor():
    """Install the PyGithub rate-limit log monitor once."""
    global _rateLimitLogHandler
    if _rateLimitLogHandler is not None:
        return _rateLimitLogHandler
    retry_logger = logging.getLogger('github.GithubRetry')
    _rateLimitLogHandler = GithubRateLimitLogHandler()
    _rateLimitLogHandler.setLevel(logging.INFO)
    retry_logger.addHandler(_rateLimitLogHandler)
    return _rateLimitLogHandler


@lru_cache()
def getUserByToken(token: str):
    """ get a GitHub user object by GitHub token

    Parameters
    ----------
    token: str
        GitHub token

    Returns
    -------
    user: AuthenticatedUser | None
        the GitHub user object
    """
    assert isinstance(token, str), type(token)
    if not token.strip():
        raise ValueError('GitHub token cannot be empty.')
    logStarted('Log.Action.GitHubAPI')
    github = Github(base_url=apiUrl(), auth=Auth.Token(token))
    user = github.get_user()
    logSucceeded('Log.Action.GitHubAPI')
    return user

@lru_cache()
def getUserName(token: str):
    """ get a GitHub user's name

    Parameters
    ----------
    token: str
        GitHub token

    Returns
    -------
    name: str
        the GitHub user's name
    """
    assert isinstance(token, str), type(token)
    try:
        if not token:
            return getuser()
        u = getUserByToken(token)
        logger.info(translate('Log.Utils.GetUserName.Success', (u.url, u.login, u.name)))
        return u.name or u.login
    except:
        logger.error(translate('Log.Utils.GetUserName.Failed.Exception', (apiUrl(), traceback.format_exc())))
        return ''

@lru_cache()
def getUserLogin(token: str):
    """ get a GitHub user's login name

    Parameters
    ----------
    token: str
        GitHub token

    Returns
    -------
    name: str
        the GitHub user's name
    """
    assert isinstance(token, str), type(token)
    try:
        if not token:
            return getuser()
        u = getUserByToken(token)
        logger.info(translate('Log.Utils.GetUserLogin.Success', (u.url, u.login)))
        return u.login
    except:
        logger.error(translate('Log.Utils.GetUserLogin.Failed.Exception', (apiUrl(), traceback.format_exc())))
        return ''

@lru_cache()
def getUserAvatar(username: str) -> QPixmap:
    """ get a GitHub user's avatar

    Parameters
    ----------
    username: str
        the GitHub user's name

    Returns
    -------
    avatar: QPixmap
        the avatar of the GitHub user
    """
    try:
        g = Github(base_url=apiUrl())
        avatar_url = g.get_user(username).avatar_url
        response = requests.get(avatar_url, timeout=15)
        response.raise_for_status()
        data = response.content
        logger.info(translate('Log.Utils.GetUserAvatar.Success', (avatar_url, username)))
        return QPixmap.fromImage(QImage.fromData(data))
    except:
        if 'avatar_url' in locals():
            url = avatar_url
        else:
            url = apiUrl()
        logger.error(translate('Log.Utils.GetUserAvatar.Failed.Exception', (url, username, traceback.format_exc())))
        return QPixmap()

@lru_cache()
@exceptionHandler(None)
def getRepo(repo: str, token: str = None, write_log_on_err = True):
    """ get a GitHub repo object

    Parameters
    ----------
    repo: str
        the GitHub repo's name

    token: str = None
        the GitHub token

    write_log_on_err: bool = True
        whether to output to the log when an error occurs

    Returns
    -------
    repo: Repository
        the GitHub repo object
    """
    g = Github(base_url=apiUrl(), auth=Auth.Token(token) if token else None)
    logStarted('Log.Action.Repository', repo, level='debug')
    if not write_log_on_err:
        try:
            result = g.get_repo(repo)
            logSucceeded('Log.Action.Repository', repo, level='debug')
            return result
        except Exception as error:
            logFailed(
                'Log.Action.Repository',
                exceptionDetail(error, repo),
                level='debug',
            )
            return None
    else:
        result = g.get_repo(repo)
        logSucceeded('Log.Action.Repository', repo, level='debug')
        return result

@lru_cache()
@exceptionHandler([])
def getRepoBranches(repo: str, token: str = None):
    """ get a GitHub repo's branches

    Parameters
    ----------
    repo: str
        the GitHub repo's name

    token: str = None
        the GitHub token
    """
    repo_name = repo
    logStarted('Log.Action.Branch', repo_name, level='debug')
    repo = getRepo(repo_name, token)
    if not repo:
        logFailed('Log.Action.Branch', repo_name, level='debug')
        return []
    branches = list(repo.get_branches())
    res = []
    for i in branches:
        res.append(i.name)
    logSucceeded('Log.Action.Branch', f'{repo_name}: {len(res)}', level='debug')
    return res

@lru_cache()
@exceptionHandler(False)
def hasWriteAccess(repo: str, token: str = None):
    """ check if the user has write access to the repo

    Parameters
    ----------
    repo: str
        the GitHub repo's name

    token: str = None
        the GitHub token
    """
    if not token:
        logChanged('Log.Action.Repository', f'{repo}: {False}', level='debug')
        return False
    repo = getRepo(repo, token)
    if not repo:
        return False
    permissions = repo.permissions
    if isinstance(permissions, dict):
        writable = bool(permissions.get('push') or permissions.get('admin'))
    else:
        writable = bool(getattr(permissions, 'push', False) or getattr(permissions, 'admin', False))
    logChanged('Log.Action.Repository', f'{repo}: {writable}', level='debug')
    return writable

# @exceptionHandler('https://api.github.com')
def apiUrl():
    """ get the GitHub api url """
    # 这个镜像站有些问题
    # if cfg.get(cfg.apiMirrorEnabled) and requests.get('https://api.kkgithub.com').ok:
    #     return 'https://api.kkgithub.com'
    # else:
    return 'https://api.github.com'


def githubProxyUrl(target_url: str, mirror: str) -> str:
    """Build a ghproxy URL while preserving the complete source URL."""
    url_path = urlunsplit(urlsplit(target_url)._replace(scheme='', netloc=''))
    return f'http://{mirror}/{url_path}' if mirror else target_url


def _measureGithubMirrorSpeed(mirror: str, target_url: str):
    """Return sampled bytes per second for one mirror, or ``None``."""
    proxy_url = githubProxyUrl(target_url, mirror)
    started_at = monotonic()
    try:
        with requests.get(
            proxy_url,
            headers={
                'Range': f'bytes=0-{MIRROR_SPEED_SAMPLE_SIZE - 1}',
                'Accept-Encoding': 'identity',
            },
            stream=True,
            allow_redirects=True,
            timeout=MIRROR_SPEED_TIMEOUT,
        ) as response:
            response.raise_for_status()
            if response.status_code not in (200, 206):
                return None

            sample = bytearray()
            for chunk in response.iter_content(8192):
                if not chunk:
                    continue
                remaining = MIRROR_SPEED_SAMPLE_SIZE - len(sample)
                sample.extend(chunk[:remaining])
                if len(sample) >= MIRROR_SPEED_SAMPLE_SIZE:
                    break
            if not sample:
                return None

            suffix = urlsplit(target_url).path.lower()
            prefix = bytes(sample[:64]).lstrip().lower()
            if (
                suffix.rsplit('.', 1)[-1] not in ('htm', 'html')
                and (prefix.startswith(b'<!doctype html')
                     or prefix.startswith(b'<html'))
            ):
                return None

            elapsed = max(monotonic() - started_at, 0.001)
            return mirror, len(sample) / elapsed
    except requests.RequestException:
        return None


def getFastestGithubMirror(target_url: str):
    """Measure every configured node for this URL and return the fastest."""
    from ..common.config import cfg
    if not cfg.get(cfg.githubMirrorEnabled):
        logChanged(
            'Log.Action.GitHubMirror',
            'https://github.com',
            level='debug',
        )
        return None
    if urlsplit(target_url).hostname != 'github.com':
        logChanged('Log.Action.GitHubMirror', target_url, level='debug')
        return None

    mirrors = tuple(dict.fromkeys(GITHUB_MIRRORS))
    if not mirrors:
        logFailed(
            'Log.Action.GitHubMirror',
            '0/0 -> https://github.com',
            level='warning',
        )
        return None
    logStarted(
        'Log.Action.GitHubMirror',
        f'{urlsplit(target_url).path}: {len(mirrors)}',
        level='debug',
    )
    results = []
    with ThreadPoolExecutor(
        max_workers=min(MIRROR_SPEED_MAX_WORKERS, len(mirrors)),
        thread_name_prefix='github-mirror-speed',
    ) as executor:
        futures = {
            executor.submit(_measureGithubMirrorSpeed, mirror, target_url): mirror
            for mirror in mirrors
        }
        for future in as_completed(futures):
            try:
                result = future.result()
                if result is not None:
                    results.append(result)
            except Exception as error:
                logFailed(
                    'Log.Action.GitHubMirror',
                    exceptionDetail(error, futures[future]),
                    level='debug',
                )

    if not results:
        logFailed(
            'Log.Action.GitHubMirror',
            f'0/{len(mirrors)} -> https://github.com',
            level='warning',
        )
        return None

    mirror, speed = max(results, key=lambda item: item[1])
    logChanged(
        'Log.Action.GitHubMirror',
        f'{mirror}: {speed / 1024:.1f} KiB/s',
    )
    return mirror
