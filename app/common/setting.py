# coding: utf-8
import sys
from datetime import datetime
from pathlib import Path
from PyQt5.QtCore import QStandardPaths

# change DEBUG to False if you want to compile the code to exe
DEBUG = "__compiled__" not in globals()

YEAR = 2026
AUTHOR = "XiaoshuDeXiaowo"
VERSION = "0.0.2"
# Human-readable maturity marker shown in the About and update UI.
DEVELOPMENT_STAGE = "Alpha"
APP_NAME = "GitHub NetDisk"
APP_ID = "GitHub-NetDisk"
# Fill these values after the GitHub App has been registered.  Only the
# OAuth client id and public app slug belong in a desktop build.  Never ship
# the GitHub App client secret or a private key with the application.
GITHUB_APP_ID = "4420492"
GITHUB_APP_CLIENT_ID = "Iv23liBKEF8tukx5CajW"
GITHUB_APP_SLUG = "gh-netdisk"
HELP_URL = "https://github-netdisk.top/"
REPO_URL = "https://github.com/XiaoshuDeXiaowo/GitHub-NetDisk"
RELEASE_URL = f"{REPO_URL}/releases"
AUTHOR_URL = "https://github.com/XiaoshuDeXiaowo"
LICENSE_URL = f"{REPO_URL}/blob/main/LICENSE"
FEEDBACK_URL = "https://github.com/XiaoshuDeXiaowo/GitHub-NetDisk/issues"
DOC_URL = "https://github-netdisk.top/"


def localizedWebsiteUrl(locale_name=''):
    """Return the documentation root matching the current UI language."""
    locale = str(locale_name or '').lower().replace('-', '_')
    if locale.startswith(('zh_cn', 'zh_sg')):
        return 'https://github-netdisk.top/zh/'
    if locale.startswith(('zh_hk', 'zh_tw', 'zh_mo')):
        return 'https://github-netdisk.top/zh-hk/'
    return 'https://github-netdisk.top/'

APP_FOLDER = Path('config').parent.absolute()

if sys.platform == "win32" and not DEBUG:
    APP_FOLDER = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)) / APP_ID

CONFIG_FOLDER = APP_FOLDER / "config"
CONFIG_FOLDER.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = CONFIG_FOLDER / "config.json"
TRANSFER_TASK_FILE = CONFIG_FOLDER / "transfer_tasks.json"

LOG_FOLDER = APP_FOLDER / "logs"
LOG_FOLDER.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_FOLDER / f"Log_{datetime.now():%Y%m%d_%H%M%S}.log"

if sys.platform == "win32":
    EXE_SUFFIX = ".exe"
else:
    EXE_SUFFIX = ""

# Static snapshot of ghproxy-next's public node list:
# https://github.com/hubporg/ghproxy-next/raw/refs/heads/main/components/nodes.ts
GITHUB_MIRRORS = [
    "gh.dpik.top/https://github.com",
    "github.tbap.top/https://github.com",
    "ghfile.geekertao.top/https://github.com",
    "ghproxy.net/https://github.com",
    "gh-proxy.com/https://github.com",
    "gh-proxy.net/https://github.com",
    "cdn.gh-proxy.com/https://github.com",
    "github.dpik.top/https://github.com",
    "j.1lin.dpdns.org/https://github.com",
    "github.starrlzy.cn/https://github.com",
    "github-proxy.memory-echoes.cn/https://github.com",
    "git.yylx.win/https://github.com",
    "ghm.078465.xyz/https://github.com",
    "gh.927223.xyz/https://github.com",
    "ghf.无名氏.top/https://github.com",
    "gh.felicity.ac.cn/https://github.com",
    "gh.bugdey.us.kg/https://github.com",
    "cdn.akaere.online/https://github.com",
    "jiashu.1win.eu.org/https://github.com",
    "tvv.tw/https://github.com",
    "j.1win.ggff.net/https://github.com",
    "gitproxy.127731.xyz/https://github.com",
    "gh.inkchills.cn/https://github.com",
    "gh.catmak.name/https://github.com",
    "gh.b52m.cn/https://github.com",
    "down.mxw.xx.kg/https://github.com",
    "down.mxw.qzz.io/https://github.com",
    "github.mxw.qzz.io/https://github.com",
    "gh.acmsz.top/https://github.com",
    "gh.jjj.gv.uy/https://github.com",
    "slink.ltd/https://github.com",
    "github.tmby.shop/https://github.com",
    "ghpr.cc/https://github.com",
    "gh.tryxd.cn/https://github.com",
    "gitproxy.click/https://github.com",
    "github.chenc.dev/https://github.com",
    "gh.ddlc.top/https://github.com",
    "gitproxy.mrhjx.cn/https://github.com",
    "gh.sixyin.com/https://github.com",
    "gh.monlor.com/https://github.com",
    "ghpxy.hwinzniej.top/https://github.com",
    "git.669966.xyz/https://github.com",
    "ghfast.top/https://github.com",
    "gh.jasonzeng.dev/https://github.com",
    "github.geekery.cn/https://github.com",
    "gp.zkitefly.eu.org/https://github.com",
    "fastgit.cc/https://github.com",
    "ghproxy.1888866.xyz/https://github.com",
    "ghp.arslantu.xyz/https://github.com",
    "github.ednovas.xyz/https://github.com",
    "ghproxy.imciel.com/https://github.com",
    "ghproxy.cxkpro.top/https://github.com",
    "github.xxlab.tech/https://github.com",
    "gh.idayer.com/https://github.com",
    "free.cn.eu.org/https://github.com",
    "gh.chjina.com/https://github.com",
    "ghp.keleyaa.com/https://github.com",
    "proxy.yaoyaoling.net/https://github.com",
    "ghproxy.monkeyray.net/https://github.com",
    "gh.noki.icu/https://github.com",
    "g.blfrp.cn/https://github.com",
    "githubdog.com/https://github.com",
    "gh.meali.top/https://github.com",
    "777.z321.cc.cd/https://github.com",
    "gg.z321.cc.cd/https://github.com",
    "g.z321.cc.cd/https://github.com",
    "js.jiangss.shop/https://github.com",
    "gap.andyjin.website/https://github.com",
    "gh.my-website.ccwu.cc/https://github.com",
    "github.ikgy.top/https://github.com",
    "gh.07150721.xyz/https://github.com",
    "cfgh.ikgy.top/https://github.com",
    "xsadwsd.kdns.fr/https://github.com",
    "gh.ruan.dpdns.org/https://github.com",
    # 2026.8.4 update from https://github.com/XIU2/Userscript/blob/master/GithubEnhanced-High-Speed-Download.user.js
    "gh.h233.eu.org/https://github.com",
    "gh-proxy.org/https://github.com",
    "cdn.gh-proxy.org/https://github.com",
    "edgeone.gh-proxy.org/https://github.com",
    "cors.isteed.cc/https://github.com",
    "ghproxy.it/https://github.com",
    "github.boki.moe/https://github.com",
    "cdn.crashmc.com/https://github.com",
    "gh.xxooo.cf/https://github.com",
    "down.npee.cn/?https://github.com",
    "raw.ihtw.moe/https://github.com",
    "xget.xi-xu.me/gh",
    "gh.zwy.one/https://github.com",
    "wget.la/https://github.com"
]
