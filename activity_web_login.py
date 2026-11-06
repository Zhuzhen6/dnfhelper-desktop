"""通过腾讯官方二维码获取当前账户的网页登录授权。"""
import queue
import re
import threading
import time
import tkinter as tk
from tkinter import ttk
from urllib.parse import urlparse, urlunparse

import requests

from activity_http import ActivityError, parse_cookie, require_cookie_identity
from qq_login import hash33


def secure_login_url(url):
    """腾讯登录偶尔返回 HTTP 地址，先校验域名再改用 HTTPS。"""
    parsed = urlparse(url)
    hosts = {"ptlogin2.qq.com", "ssl.ptlogin2.qq.com", "xui.ptlogin2.qq.com",
             "ptlogin2.game.qq.com", "ptlogin4.game.qq.com", "ssl.ptlogin4.game.qq.com", "dnf.qq.com"}
    try:
        valid_port = parsed.port in (None, 80 if parsed.scheme == "http" else 443)
    except ValueError:
        valid_port = False
    if (parsed.scheme not in {"http", "https"} or parsed.hostname not in hosts
            or not valid_port or parsed.username or parsed.password):
        raise ActivityError(f"登录跳转地址不受支持（{parsed.hostname or '无域名'}），请重试")
    return urlunparse(parsed._replace(scheme="https", netloc=parsed.hostname))


def collect_web_cookie(events, cancelled):
    """仅访问固定登录域名，校验身份后才把授权交给界面。"""
    with requests.Session() as session:
        session.headers["User-Agent"] = "Mozilla/5.0"
        response = session.get("https://xui.ptlogin2.qq.com/cgi-bin/xlogin", params={
            "appid": "21000127", "daid": "8", "s_url": "https://dnf.qq.com/", "style": "40"},
            timeout=20, allow_redirects=False)
        response.raise_for_status()
        response = session.get("https://ssl.ptlogin2.qq.com/ptqrshow", params={
            "appid": "21000127", "e": "2", "l": "M", "s": "3", "d": "72", "v": "4", "daid": "8"},
            timeout=20, allow_redirects=False)
        response.raise_for_status()
        signature = next((cookie.value for cookie in session.cookies if cookie.name == "qrsig"), "")
        if not signature or not response.content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ActivityError("二维码获取失败，请重试")
        events.put(("qr", response.content))
        deadline = time.monotonic() + 180
        while not cancelled.is_set() and time.monotonic() < deadline:
            response = session.get("https://ssl.ptlogin2.qq.com/ptqrlogin", params={
                "u1": "https://dnf.qq.com/", "ptqrtoken": str(hash33(signature)),
                "ptredirect": "0", "h": "1", "t": "1", "g": "1", "from_ui": "1",
                "ptlang": "2052", "action": f"0-0-{int(time.time() * 1000)}", "js_ver": "22080914",
                "js_type": "1", "login_sig": "", "pt_uistyle": "40", "aid": "21000127", "daid": "8"},
                timeout=20, allow_redirects=False)
            response.raise_for_status()
            match = re.fullmatch(r"\s*ptuiCB\((.*)\);?\s*", response.text, re.S)
            fields = re.findall(r"'([^']*)'", match.group(1)) if match else []
            if len(fields) < 3:
                raise ActivityError("扫码接口格式变化，请稍后重试")
            code = fields[0]
            if code == "0":
                url = fields[2]
                # 登录跳转可能携带临时票据，禁止向其他域名跟随跳转。
                for _ in range(5):
                    if cancelled.is_set():
                        return
                    url = secure_login_url(url)
                    response = session.get(url, timeout=20, allow_redirects=False)
                    response.raise_for_status()
                    cookie = "; ".join(f"{entry.name}={entry.value}" for entry in session.cookies
                                       if entry.name in {"uin", "skey"} and entry.domain.lstrip(".") == "qq.com")
                    if "skey=" in cookie:
                        actual_qq = parse_cookie(cookie).get("uin", "").lstrip("o0")
                        if not re.fullmatch(r"\d{5,20}", actual_qq):
                            raise ActivityError("网页登录未返回有效 QQ，请重新扫码")
                        values = require_cookie_identity(cookie, actual_qq)
                        if values.get("skey"):
                            events.put(("success", cookie))
                            return
                    if not response.is_redirect:
                        break
                    url = requests.compat.urljoin(url, response.headers.get("Location", ""))
                raise ActivityError("登录成功但未取得网页授权，请重新扫码")
            if code not in ("66", "67"):
                raise ActivityError("二维码失效或授权取消，请关闭后重试")
            events.put(("status", "已扫码，请在手机 QQ 确认" if code == "67" else "请用手机 QQ 扫码，将自动匹配已添加账户"))
            cancelled.wait(2)
        if not cancelled.is_set():
            raise ActivityError("扫码超时，请关闭后重试")


def show_web_login(parent, on_success):
    window = tk.Toplevel(parent)
    window.title("扫码获取网页登录授权")
    window.geometry("420x400")
    window.transient(parent)
    status = tk.StringVar(value="正在获取二维码…")
    ttk.Label(window, textvariable=status, wraplength=380).pack(padx=20, pady=20)
    preview = ttk.Label(window)
    preview.pack(expand=True)
    events = queue.Queue()
    cancelled = threading.Event()

    def close():
        cancelled.set()
        window.grab_release()
        window.destroy()
        if parent.winfo_exists():
            parent.grab_set()

    def work():
        try:
            collect_web_cookie(events, cancelled)
        except Exception as error:
            events.put(("error", str(error) if isinstance(error, ActivityError) else "获取失败，请检查网络后重试"))

    def poll():
        if not window.winfo_exists():
            cancelled.set()
            return
        while not events.empty():
            kind, value = events.get_nowait()
            if kind == "success":
                try:
                    on_success(value)
                except (ActivityError, ValueError, OSError):
                    status.set("未更新授权：未找到对应账户或配置无法保存，请先添加该 QQ 账户后重试")
                    preview.configure(image="")
                    return
                close()
                return
            if kind == "qr":
                try:
                    preview.image = tk.PhotoImage(master=window, data=value)
                    preview.configure(image=preview.image)
                    status.set("请用手机 QQ 扫码，将自动匹配已添加账户")
                except tk.TclError:
                    status.set("二维码显示失败，请关闭后重试")
                    cancelled.set()
            else:
                status.set(value)
        window.after(100, poll)

    ttk.Button(window, text="取消", command=close).pack(pady=16)
    window.protocol("WM_DELETE_WINDOW", close)
    window.bind("<Escape>", lambda event: close())
    window.grab_set()
    threading.Thread(target=work, daemon=True).start()
    window.after(100, poll)
