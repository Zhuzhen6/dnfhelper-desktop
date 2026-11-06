"""根据已选活动展示计划任务和最近执行结果。Created by 朱圳。"""
from activity_catalog import available_activities


PLANNED_TASKS = {
    "chronicle": ("日常任务与签到", "连续签到奖励", "现有搭档任务与等级礼包"),
    "assistant_event": ("每日活动任务", "今日签到", "累计与周期签到奖励"),
    "phone": ("首次绑定奖励", "本月积分"),
    "landing": ("见面礼包", "深渊任务领奖", "页面浏览任务", "累计抽奖奖励"),
    "jinggai": ("见面礼包", "每日与每周任务领奖", "累计奖励", "排名奖励"),
    "recall": ("回流指引浏览", "回流资格奖励"),
}


def activity_task_rows(config, result):
    """执行结果仅表示最近一次尝试，不推断游戏内完成状态。"""
    rows = []
    for key, (title, _, _) in available_activities().items():
        if key not in config["enabled"]:
            continue
        rows.append((title, "—", "活动", "—", "—"))
        if key == "chronicle" and result.get("tasks"):
            for task in result["tasks"]:
                rows.append((task.get("name", "任务"), task.get("my_exp", "—"),
                             task.get("my_status", "未知"), task.get("partner_exp", "—"),
                             task.get("partner_status", "未知")))
        previous = result.get("activity_tasks", {}).get(key)
        if previous:
            for action in previous:
                rows.append((action["action"], "—", action["result"], "—", "—"))
        else:
            for label in PLANNED_TASKS[key]:
                rows.append((label, "—", "待查询", "—", "—"))
        if config["lottery"] and key in ("assistant_event", "landing") and not previous:
            rows.append(("使用免费抽奖次数", "—", "待查询", "—", "—"))
        if config["recheckin"] and key == "assistant_event" and not previous:
            rows.append(("使用可用补签次数", "—", "待查询", "—", "—"))
    return rows
