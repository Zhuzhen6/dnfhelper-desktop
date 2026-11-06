"""桌面版配置持久化；Windows 凭证使用当前用户的 DPAPI 加密。"""
import ctypes
import json
import os
import tempfile
from pathlib import Path
from ctypes import wintypes


def account_directory():
    return Path(os.environ.get("DNFHELPER_ACCOUNT_DIR", Path(__file__).parent))


def data_directory():
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
    return base / "DNFHelperDesktop"


def atomic_write(path, content):
    """同目录原子替换，避免中断造成配置损坏。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def protect(content, decrypt=False):
    """凭证绑定 Windows 当前用户，无需保存额外密钥。"""
    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("content", ctypes.POINTER(ctypes.c_byte))]

    buffer = ctypes.create_string_buffer(content)
    source = Blob(len(content), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    result = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    operation = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    operation.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                          ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                          ctypes.POINTER(Blob)]
    operation.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not operation(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(result.content, result.size)
    finally:
        kernel.LocalFree(result.content)


def read_json(path):
    content = Path(path).read_bytes()
    if content.startswith(b"DPAPI\n"):
        if os.name != "nt":
            raise ValueError("该凭证只能在原 Windows 用户下读取，请重新扫码")
        content = protect(content[6:], decrypt=True)
    return json.loads(content.decode("utf-8"))


def write_json(path, value, secret=False):
    content = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
    if secret and os.name == "nt":
        content = b"DPAPI\n" + protect(content)
    atomic_write(path, content)
