"""活动网络边界：固定域名、超时、串行限速、统一响应检查。"""
import json
import re
import time
from http.cookies import SimpleCookie
from urllib.parse import urlparse

import requests


ALLOWED_HOSTS = {"comm.ams.game.qq.com", "dzhu.qq.com"}


class ActivityError(Exception):
    """可以直接向用户展示的业务错误。"""


class AssistantAuthError(ActivityError):
    """助手登录已失效，需要重新扫码。"""


def parse_json(text):
    text = text.strip()
    try:
        value = json.loads(text)
    except ValueError:
        match = re.fullmatch(r"[\w.$]+\s*\((.*)\)\s*;?", text, re.S)
        if not match:
            raise ActivityError("接口未返回 JSON，请检查登录态或活动版本")
        value = json.loads(match.group(1))
    if not isinstance(value, dict):
        raise ActivityError("接口响应格式已变化")
    return value


def parse_cookie(value):
    if not isinstance(value, str) or len(value) > 32768 or any(ch in value for ch in "\r\n"):
        raise ValueError("Cookie 格式无效")
    cookie = SimpleCookie()
    try:
        cookie.load(value)
    except Exception as error:
        raise ValueError("Cookie 格式无效") from error
    return {key: item.value for key, item in cookie.items()}


def require_cookie_identity(cookie, expected_qq):
    values = parse_cookie(cookie)
    candidates = [values[key].lstrip("o0") for key in ("uin", "p_uin", "ptui_loginuin") if values.get(key)]
    if not candidates or any(value != str(expected_qq).lstrip("o0") for value in candidates):
        raise ActivityError("Cookie 的 QQ 与该账户不一致或缺少 uin，请重新配置")
    return values


def ensure_success(response):
    for field in ("ret", "iRet", "returnCode", "code", "result"):
        if field in response and isinstance(response[field], (int, str)):
            if str(response[field]) not in ("0", "200"):
                message = response.get("msg") or response.get("sMsg") or response.get("returnMsg") or "未满足领取条件"
                raise ActivityError(f"接口返回 {response[field]}：{str(message)[:180]}")
    for field in ("flowRet", "modRet"):
        if isinstance(response.get(field), dict):
            ensure_success(response[field])
    return response


class ActivityHttp:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
        self.last_request = 0

    def request(self, method, url, **options):
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
            raise ActivityError("拒绝向非活动域名发送凭证")
        delay = 2 - (time.monotonic() - self.last_request)
        if delay > 0:
            time.sleep(delay)
        self.last_request = time.monotonic()
        response = self.session.request(method, url, timeout=25, allow_redirects=False, **options)
        if response.status_code in (301, 302, 303, 307, 308):
            return response
        if response.status_code != 200:
            raise ActivityError(f"HTTP {response.status_code}，请检查网络或稍后执行")
        if len(response.content) > 4 * 1024 * 1024:
            raise ActivityError("接口响应过大")
        return response

    def json(self, method, url, **options):
        response = self.request(method, url, **options)
        if response.is_redirect:
            raise ActivityError("接口跳转至登录页，请更新授权")
        return ensure_success(parse_json(response.text))


def run_step(summary, label, callback, quiet_success=False):
    try:
        pending_before = len(summary["pending"])
        result = callback()
        status = "待处理" if len(summary["pending"]) > pending_before else "完成"
        summary["actions"].append({"action": label, "result": status})
        if not quiet_success:
            print(f"[{label}] {status}", flush=True)
        return result
    except (ActivityError, requests.RequestException, ValueError, KeyError, TypeError, IndexError, SystemExit) as error:
        if isinstance(error, AssistantAuthError):
            summary["auth_expired"] = True
        message = str(error) if isinstance(error, ActivityError) else f"{type(error).__name__}，请检查配置、网络或接口版本"
        summary["pending"].append(f"{label}：{message}")
        print(f"[{label}] {message}", flush=True)
        return None
