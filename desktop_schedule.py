"""每日定时规则，按电脑本地时间判断。"""
from datetime import datetime


def validate_time(value):
    try:
        parsed = datetime.strptime(value, "%H:%M")
    except (ValueError, TypeError) as error:
        raise ValueError("时间请填写为 HH:MM，例如 09:30") from error
    if parsed.strftime("%H:%M") != value:
        raise ValueError("时间请填写为 HH:MM，例如 09:30")
    return value


def is_due(account, now):
    return (account["enabled"] and now.strftime("%H:%M") >= account["time"]
            and account.get("last_scheduled") != now.date().isoformat())
