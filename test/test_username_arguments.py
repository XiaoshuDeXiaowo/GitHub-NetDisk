# coding: utf-8
from app.common.application import getForcedUsernameArgument


def test_force_username_argument_is_case_insensitive_and_preserves_value():
    assert getForcedUsernameArgument([
        'GitHub-NetDisk.py', '--FORCE-USERNAME=示例用户']) == '示例用户'


def test_force_username_argument_requires_a_non_empty_value():
    assert getForcedUsernameArgument([
        'GitHub-NetDisk.py', '--force-username=']) is None
    assert getForcedUsernameArgument([
        'GitHub-NetDisk.py', '--force-username']) is None
