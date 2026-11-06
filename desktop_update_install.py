"""在原程序退出后替换 exe，失败时恢复旧文件。Created by 朱圳。"""
import ctypes
import os
from pathlib import Path
import subprocess
import time


def apply_update(parent_pid, target, downloaded):
    if os.name != "nt":
        return 2
    target, downloaded = Path(target).resolve(), Path(downloaded).resolve()
    backup = target.with_suffix(".exe.previous")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x100000, False, int(parent_pid))
    if handle:
        try:
            if kernel.WaitForSingleObject(handle, 60000) != 0:
                return 2
        finally:
            kernel.CloseHandle(handle)
    moved = False
    try:
        for attempt in range(30):
            try:
                os.replace(target, backup)
                moved = True
                break
            except PermissionError:
                if attempt == 29:
                    raise
                time.sleep(1)
        # 跨磁盘时复制到目标同目录后再原子替换。
        import shutil
        staged = target.with_suffix(".exe.installing")
        shutil.copyfile(downloaded, staged)
        os.replace(staged, target)
        subprocess.Popen([str(target)], cwd=target.parent, env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"})
        return 0
    except OSError:
        if moved:
            os.replace(backup, target)
        ctypes.windll.user32.MessageBoxW(None, "更新安装失败，已保留旧版本。请从 Releases 手动下载，或将程序放到可写目录后重试。", "更新失败", 0x10)
        subprocess.Popen([str(target)], cwd=target.parent, env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"})
        return 2
