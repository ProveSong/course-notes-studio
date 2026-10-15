from __future__ import annotations
import os
import subprocess
import threading
from pathlib import Path


class Cancelled(Exception):
    pass


def check_cancel(cancel: threading.Event):
    if cancel.is_set():
        raise Cancelled('任务已取消；已完成的证据与片段保留，可继续。')


def run_command(command, log_path: Path, cancel: threading.Event, cwd=None):
    """Use file-backed output to avoid pipe deadlocks and unbounded memory."""
    check_cancel(cancel)
    with log_path.open('w', encoding='utf-8') as out:
        env={**os.environ,'PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8:backslashreplace'}
        proc = subprocess.Popen([str(x) for x in command], cwd=cwd, stdout=out,env=env,
                                stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            while proc.poll() is None:
                if cancel.wait(0.3):
                    if os.name == 'nt':
                        subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                                       capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                    else:
                        proc.terminate()
                    proc.wait(timeout=15)
                    raise Cancelled('任务已取消。')
            if proc.returncode:
                raise RuntimeError(f'外部程序失败（返回码 {proc.returncode}），详情：{log_path}')
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
