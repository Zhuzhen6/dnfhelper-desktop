"""编年任务明细只保留界面所需字段。Created by 朱圳。"""


def task_status(value, action_id):
    if not action_id:
        return "未提供"
    return {"0": "未完成", "1": "已领取", "2": "待领取"}.get(str(value), "未知")


def normalize_tasks(tasks):
    rows = []
    for task in tasks:
        rows.append({
            "id": str(task.get("mActionId") or task.get("pActionId") or ""),
            "name": str(task.get("name") or "未命名任务"),
            "my_exp": task.get("mExp") if task.get("mExp") is not None else "—",
            "my_status": task_status(task.get("mStatus"), task.get("mActionId")),
            "partner_exp": task.get("pExp") if task.get("pExp") is not None else "—",
            "partner_status": task_status(task.get("pStatus"), task.get("pActionId")),
        })
    return rows
