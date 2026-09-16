# coding: utf-8
"""aria2 download integration via direct CLI invocation (no RPC daemon)."""
import atexit
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from threading import RLock
from urllib.parse import urlsplit

from ..common.event_logger import (
    logCancelled,
    logChanged,
    logFailed,
    logStarted,
    logSucceeded,
)
from ..common.config import cfg
from ..common.transfer_utils import isTransferCancelledError


class Aria2Unavailable(RuntimeError):
    """Raised when aria2c is not available."""


# Matches aria2c progress lines, e.g.:
# [#2504b5 0B/512KiB(0%) CN:1 DL:887B ETA:9m51s]
_PROGRESS_RE = re.compile(
    r'\[(?P<gid>[^\s]+)\s+'
    r'(?P<done>[\d.]+[KMGT]?i?B)/(?P<total>[\d.]+[KMGT]?i?B)'
    r'\((?P<pct>\d+)%\)'
)


def _parse_size(text):
    """Parse an aria2c size string like '3.2MiB' into bytes."""
    text = str(text).strip()
    if not text:
        return 0
    text = text.lower()
    multipliers = {
        'k': 1024, 'm': 1024 ** 2, 'g': 1024 ** 3, 't': 1024 ** 4,
    }
    for suffix in ('ib', 'b'):
        if text.endswith(suffix):
            text = text[:-len(suffix)]
            break
    unit = text[-1] if text else ''
    value = float(text[:-1]) if unit in multipliers else float(text or 0)
    if unit in multipliers:
        return int(value * multipliers[unit])
    return int(value)


class Aria2DownloadService:
    """Invoke aria2c directly via the CLI for each download."""

    def __init__(self):
        self._processes = []
        self._lock = RLock()
        self._unavailable_reason = ''
        atexit.register(self.close)

    def _ensure_executable(self):
        configured_path = str(cfg.get(cfg.aria2Path) or '').strip()
        executable = configured_path or shutil.which('aria2c')
        if configured_path and not (
                os.path.isfile(configured_path)
                and os.access(configured_path, os.X_OK)):
            raise Aria2Unavailable('configured aria2c path is not executable')
        if not executable:
            raise Aria2Unavailable('aria2c was not found')
        return executable

    def _build_args(self, executable, link, directory, output_name, headers):
        args = [
            executable,
            link,
            '--dir', directory,
            '--out', output_name,
            '--allow-overwrite=true',
            '--auto-file-renaming=false',
            '--continue=true',
            '--file-allocation=none',
            '--max-connection-per-server=4',
            '--split=4',
            '--min-split-size=1M',
            '--timeout=15',
            '--connect-timeout=10',
            '--async-dns=false',
            '--summary-interval=1',
            '--console-log-level=warn',
        ]
        if headers and not urlsplit(link).username:
            for name, value in headers.items():
                args.extend(['--header', f'{name}: {value}'])
        return args

    @staticmethod
    def _popen_kwargs():
        """Return process options that keep aria2c out of the user's UI.

        ``aria2c`` is a console executable.  When it is launched from a
        packaged GUI application on Windows, inheriting the parent's console
        (or creating a new one) causes a visible black window for every
        asset.  ``CREATE_NO_WINDOW`` handles modern Windows versions while
        the hidden ``STARTUPINFO`` flags cover older systems such as Windows
        7.  Keep the options platform-specific so tests and Unix builds do
        not depend on Windows-only subprocess attributes.
        """
        options = {}
        if sys.platform == 'win32':
            options['creationflags'] = getattr(
                subprocess, 'CREATE_NO_WINDOW', 0)
            startup_info_factory = getattr(subprocess, 'STARTUPINFO', None)
            if startup_info_factory is not None:
                startup_info = startup_info_factory()
                startup_info.dwFlags |= getattr(
                    subprocess, 'STARTF_USESHOWWINDOW', 0)
                startup_info.wShowWindow = getattr(
                    subprocess, 'SW_HIDE', 0)
                options['startupinfo'] = startup_info
        return options

    def download(self, links, destination, total=0, progress=None,
                 headers=None, status=None, cancel_event=None):
        """Download assets concurrently via separate aria2c processes."""
        executable = self._ensure_executable()
        destination = os.path.abspath(destination)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        directory = tempfile.mkdtemp(prefix='github-netdisk-aria2-')
        logStarted('Log.Action.Aria2Download', str(len(links)))
        try:
            part_paths = []
            processes = []
            # Launch all downloads in parallel.
            for index, link in enumerate(links):
                output_name = f'part-{index:04d}'
                part_path = os.path.join(directory, output_name)
                part_paths.append(part_path)
                args = self._build_args(
                    executable, link, directory, output_name, headers or {})
                proc = subprocess.Popen(
                    args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    **self._popen_kwargs(),
                )
                processes.append(proc)
                with self._lock:
                    self._processes.append(proc)

            if progress:
                progress(0, total)

            # Poll until all complete, parsing progress from stderr.
            remaining = list(enumerate(processes))
            part_done = {i: 0 for i in range(len(links))}
            while remaining:
                if cancel_event and cancel_event.is_set():
                    for _, proc in remaining:
                        proc.terminate()
                    raise IOError('transfer cancelled')

                for idx, proc in list(remaining):
                    line = proc.stdout.readline()
                    if not line and proc.poll() is not None:
                        if proc.returncode != 0:
                            raise IOError(
                                f'aria2c part {idx} exited with code '
                                f'{proc.returncode}')
                        remaining.remove((idx, proc))
                        continue
                    match = _PROGRESS_RE.search(line)
                    if match:
                        part_done[idx] = _parse_size(match.group('done'))
                    # Report aggregate progress.
                    current = sum(part_done.values())
                    if progress and current > 0:
                        progress(current, total)

            # Reassemble parts.
            if len(part_paths) == 1:
                os.replace(part_paths[0], destination)
            else:
                if status:
                    status('TaskInterface.ReassemblingDownload', ())
                with open(destination, 'wb') as output:
                    for part_path in part_paths:
                        with open(part_path, 'rb') as part:
                            shutil.copyfileobj(part, output, 8 * 1024 * 1024)
            if progress:
                size = total or os.path.getsize(destination)
                progress(size, size)
            logSucceeded('Log.Action.Aria2Download', str(len(links)))
            return destination
        except Exception as error:
            if isTransferCancelledError(error):
                logCancelled('Log.Action.Aria2Download')
            else:
                logFailed('Log.Action.Aria2Download', error)
            raise
        finally:
            with self._lock:
                self._processes = [
                    p for p in self._processes
                    if p not in processes
                ]
            for proc in processes:
                try:
                    if proc.poll() is None:
                        proc.terminate()
                except Exception:
                    pass
            shutil.rmtree(directory, ignore_errors=True)

    def close(self):
        with self._lock:
            for proc in self._processes:
                try:
                    if proc.poll() is None:
                        proc.terminate()
                except Exception:
                    pass
            self._processes.clear()

    def reset(self):
        """Forget connection failures and restart with current settings."""
        self.close()
        self._unavailable_reason = ''


aria2DownloadService = Aria2DownloadService()

