# coding: utf-8
from app.common.application import hasForceGuideWindowArgument


def test_force_guide_window_argument_is_case_insensitive():
    assert hasForceGuideWindowArgument([
        'GitHub-NetDisk.py', '--FoRcE-EnTeR-GuIdEwInDoW'])


def test_force_guide_window_argument_requires_an_exact_switch():
    assert not hasForceGuideWindowArgument([
        'GitHub-NetDisk.py', '--force-enter-guidewindow=true'])
    assert not hasForceGuideWindowArgument(['GitHub-NetDisk.py'])
