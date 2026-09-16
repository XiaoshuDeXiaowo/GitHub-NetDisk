# coding: utf-8
import json
import re
from pathlib import Path

from PyQt5.QtCore import QFile, QIODevice, QTextStream

from app.common import resource  # noqa: F401


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LANG_DIR = PROJECT_ROOT / 'app' / 'resource' / 'lang'
LOG_KEY_PATTERN = re.compile(r'Log\.[A-Za-z0-9_.]+')


def _read_resource_json(path):
    file = QFile(path)
    assert file.open(QIODevice.ReadOnly | QIODevice.Text)
    stream = QTextStream(file)
    stream.setCodec('UTF-8')
    try:
        return json.loads(stream.readAll())
    finally:
        file.close()


def test_compiled_resources_include_current_translation_keys():
    data = _read_resource_json(':/app/lang/zh_cn.json')

    assert data['Log.Task.InitialTaskLogOverflow'] % (2,) == (
        '还有 2 个传输任务……'
    )
    assert data['GitHub.RateLimit.title'] == 'GitHub API 速率限制'
    assert data['TaskInterface.PauseTask'] == '暂停'
    assert data['TaskInterface.Paused'] == '已暂停'
    assert data['UpdateCheck.NewVersion.title'] == '发现新版本'
    assert data['UpdateCheck.InstallerStarted.title'] == '安装程序已启动'
    assert data['GuideWindow.githubAppCardWidget.title'] == '连接 GitHub App（推荐）'
    assert '请遵守 GitHub 服务条款' in data['GuideWindow.Disclaimer']
    assert data['AccountInterface.PAT.Title'] == 'Personal Access Token'


def _read_lang_json(name):
    return json.loads((LANG_DIR / name).read_text(encoding='utf-8'))


def _python_log_keys():
    keys = set()
    for path in (PROJECT_ROOT / 'app').rglob('*.py'):
        if path.name == 'resource.py':
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        keys.update(LOG_KEY_PATTERN.findall(text))
    return keys


def test_log_translation_keys_cover_application_operations():
    languages = {
        name: _read_lang_json(name)
        for name in ('zh_cn.json', 'en_us.json', 'zh_hk.json')
    }
    used_keys = _python_log_keys()

    for name, data in languages.items():
        missing = sorted(key for key in used_keys if key not in data)
        assert missing == [], f'{name} missing log keys: {missing}'

    zh_log_keys = {
        key for key in languages['zh_cn.json']
        if key.startswith('Log.')
    }
    for name, data in languages.items():
        log_keys = {key for key in data if key.startswith('Log.')}
        assert sorted(zh_log_keys - log_keys) == []
        assert sorted(log_keys - zh_log_keys) == []
