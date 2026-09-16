# coding: utf-8
from app.common.application import (
    nativeDialogLanguageIdentifiers,
    nativeDialogLocale,
)


def test_native_dialog_language_uses_simplified_chinese():
    assert nativeDialogLanguageIdentifiers('zh_CN') == ['zh-Hans', 'en']


def test_native_dialog_language_uses_traditional_chinese():
    assert nativeDialogLanguageIdentifiers('zh_HK') == ['zh-Hant', 'en']


def test_native_dialog_language_falls_back_to_english():
    assert nativeDialogLanguageIdentifiers('en_US') == ['en']


def test_native_dialog_locale_maps_platform_names():
    assert nativeDialogLocale('zh_CN') == ('zh-CN', 'zh_CN')
    assert nativeDialogLocale('zh_HK') == ('zh-HK', 'zh_HK')
    assert nativeDialogLocale('en_US') == ('en-US', 'en_US')
