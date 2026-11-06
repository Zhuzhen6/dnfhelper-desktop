"""编年任务明细只保留界面所需字段。Created by 朱圳。"""


def task_status(value, action_id):
    if not action_id:
        return "未提供"
    return {"0": "未完成", "1": "已领取", "2": "待领取"}.get(str(value), "未知")


def normalize_tasks(tasks):
    rows = []
    for task in tasks:
        # 047 是上游已确认的无效任务，不作为可执行任务显示。
        if str(task.get("mActionId", "")) == "047":
            continue
        rows.append({
            "id": str(task.get("mActionId") or task.get("pActionId") or ""),
            "name": str(task.get("name") or "未命名任务"),
            "my_exp": task.get("mExp") if task.get("mExp") is not None else "—",
            "my_status": task_status(task.get("mStatus"), task.get("mActionId")),
            "partner_exp": task.get("pExp") if task.get("pExp") is not None else "—",
            "partner_status": task_status(task.get("pStatus"), task.get("pActionId")),
        })
    return rows
