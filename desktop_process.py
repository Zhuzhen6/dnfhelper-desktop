"""后台准备并启动独立任务进程，不接触 Tk 控件。Created by 朱圳。"""
import os
import subprocess
import sys
from pathlib import Path

from desktop_storage import atomic_write


def launch_worker(directory, action):
    directory.mkdir(parents=True, exist_ok=True)
    atomic_write(directory / "current.log", b"")
    (directory / "qr_login.png").unlink(missing_ok=True)
    arguments = [sys.executable]
    if not getattr(sys, "frozen", False):
        arguments.append(str(Path(__file__).with_name("desktop.py")))
    arguments += ["--worker", str(directory), action]
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    return subprocess.Popen(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, **options)
