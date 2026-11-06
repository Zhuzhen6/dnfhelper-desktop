"""扫码活动配置校验与加密保存。Created by 朱圳。"""
import re
import uuid
from datetime import datetime

from activity_catalog import ACTIVITIES
from activity_http import ActivityError, parse_cookie, require_cookie_identity
from desktop_storage import read_json, write_json


def default_config():
    return {"enabled": ["chronicle"], "device_id": uuid.uuid4().hex,
            "web_cookie": "", "web_authorized_at": "", "lottery": False, "recheckin": False}


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError("活动配置必须为 JSON 对象")
    if set(config) - set(default_config()):
        raise ValueError("活动配置包含不支持的配置项")
    result = {**default_config(), **config}
    enabled = result["enabled"]
    if not isinstance(enabled, list) or any(key not in ACTIVITIES for key in enabled) or len(set(enabled)) != len(enabled):
        raise ValueError("活动列表包含未知或重复项目")
    for key in ("lottery", "recheckin"):
        if not isinstance(result[key], bool):
            raise ValueError(f"{key} 必须为 true 或 false")
    if not isinstance(result["device_id"], str) or not re.fullmatch(r"[a-fA-F0-9]{16,64}", result["device_id"]):
        raise ValueError("设备标识无效")
    parse_cookie(result["web_cookie"])
    if not isinstance(result["web_authorized_at"], str):
        raise ValueError("授权时间格式无效")
    if result["web_authorized_at"]:
        datetime.strptime(result["web_authorized_at"], "%Y-%m-%d %H:%M:%S")
    return result


def load_config(directory):
    path = directory / "activity_settings.json"
    return validate_config(read_json(path)) if path.exists() else default_config()


def save_config(directory, config):
    write_json(directory / "activity_settings.json", validate_config(config), secret=True)


def save_web_authorization(directory, cookie):
    """按实际 QQ 更新已添加账户，只修改该账户的网页登录授权。"""
    actual_qq = parse_cookie(cookie).get("uin", "").lstrip("o0")
    if not re.fullmatch(r"\d{5,20}", actual_qq) or not parse_cookie(cookie).get("skey"):
        raise ActivityError("网页登录身份不完整，请重新扫码")
    require_cookie_identity(cookie, actual_qq)
    accounts = read_json(directory.parent.parent / "accounts.json")
    for account in accounts:
        identifier = account.get("id", "")
        if not re.fullmatch(r"[a-f0-9]{32}", identifier):
            continue
        target = directory.parent / identifier
        try:
            session = read_json(target / "session.json")
        except (OSError, ValueError):
            continue
        if str(session.get("uin", "")).lstrip("o0") != actual_qq:
            continue
        config = load_config(target)
        save_config(target, {**config, "web_cookie": cookie,
                             "web_authorized_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        return target, account["name"]
    raise ActivityError("未找到该 QQ 对应的账户，请先扫码添加账户")
