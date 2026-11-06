"""账户活动配置校验与加密保存。"""
import re
import uuid

from activity_catalog import ACTIVITIES
from activity_http import parse_cookie
from desktop_storage import read_json, write_json


def default_config():
    return {"enabled": ["chronicle"], "device_id": uuid.uuid4().hex,
            "area_id": "", "web_cookie": "", "forum_cookie": "",
            "daoju_oauth": {}, "xinyue_oauth": {}, "xinyue_app_oauth": {},
            "lottery": False, "recheckin": False, "partner_user_id": "",
            "chronicle_exchange": [], "daoju_exchange": [], "xinyue_operations": [],
            "phone_exchange_index": "", "xinyue_app_operations": [],
            "daoju_mobile_game": "", "daoju_wish": False}


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError("活动配置必须为 JSON 对象")
    unknown = set(config) - set(default_config())
    if unknown:
        raise ValueError(f"未知配置项：{', '.join(sorted(unknown))}")
    result = {**default_config(), **config}
    enabled = result["enabled"]
    if not isinstance(enabled, list) or any(key not in ACTIVITIES for key in enabled) or len(set(enabled)) != len(enabled):
        raise ValueError("活动列表包含未知或重复项目")
    for key in ("lottery", "recheckin", "daoju_wish"):
        if not isinstance(result[key], bool):
            raise ValueError(f"{key} 必须为 true 或 false")
    if not isinstance(result["daoju_mobile_game"], str) or not re.fullmatch(r"[a-z0-9_]{0,32}", result["daoju_mobile_game"]):
        raise ValueError("手游 bizcode 格式无效，例如 yxzj；留空表示不运行礼包达人")
    if not isinstance(result["device_id"], str) or not re.fullmatch(r"[a-fA-F0-9]{16,64}", result["device_id"]):
        raise ValueError("设备标识无效")
    for key in ("web_cookie", "forum_cookie"):
        parse_cookie(result[key])
    for key in ("area_id", "partner_user_id"):
        if not isinstance(result[key], str) or (result[key] and not re.fullmatch(r"\d{1,24}", result[key])):
            raise ValueError(f"{key} 请填写数字字符串")
    if result["phone_exchange_index"] not in ("", "0", "1", "2", "3", "4", "5", "6"):
        raise ValueError("手机奖励序号需为 0～6 的字符串，或留空")
    for key in ("daoju_oauth", "xinyue_oauth", "xinyue_app_oauth"):
        value = result[key]
        if not isinstance(value, dict) or set(value) - {"openid", "access_token"}:
            raise ValueError(f"{key} 仅支持 openid 和 access_token")
        for field in value:
            if not isinstance(value[field], str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,1024}", value[field]):
                raise ValueError(f"{key} 授权字段格式无效")
        if bool(value.get("openid")) != bool(value.get("access_token")):
            raise ValueError(f"{key} 需同时填写 openid 和 access_token")
    for key in ("chronicle_exchange", "daoju_exchange", "xinyue_operations"):
        items = result[key]
        if not isinstance(items, list) or len(items) > 50:
            raise ValueError(f"{key} 最多配置 50 项")
        for item in items:
            if (not isinstance(item, dict) or set(item) != {"id", "count"}
                    or not isinstance(item["id"], str) or not re.fullmatch(r"[A-Za-z0-9_]{1,80}", item["id"])
                    or type(item["count"]) is not int or not 1 <= item["count"] <= 100):
                raise ValueError(f"{key} 每项需为 id 字符串和 1～100 的 count")
            if key == "xinyue_operations" and not item["id"].isdigit():
                raise ValueError("心悦操作 id 必须为数字")
    operations = result["xinyue_app_operations"]
    if not isinstance(operations, list) or len(operations) > 30:
        raise ValueError("心悦 App 操作最多 30 项")
    for item in operations:
        if (not isinstance(item, dict) or set(item) != {"name", "body_hex"}
                or not isinstance(item["name"], str) or not 1 <= len(item["name"]) <= 40
                or not isinstance(item["body_hex"], str) or not 2 <= len(item["body_hex"]) <= 131072):
            raise ValueError("心悦 App 操作需包含 name 和十六进制 body_hex")
        try:
            bytes.fromhex(item["body_hex"])
        except ValueError as error:
            raise ValueError("心悦 App body_hex 格式无效") from error
    return result


def load_config(directory):
    path = directory / "activities.json"
    return validate_config(read_json(path)) if path.exists() else default_config()


def save_config(directory, config):
    write_json(directory / "activities.json", validate_config(config), secret=True)
