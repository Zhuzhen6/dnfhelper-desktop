"""按账户配置串行执行活动，一个活动失败不影响后续活动。"""
from activity_catalog import available_activities
from activity_config import load_config
from activity_http import ActivityError, ActivityHttp, run_step
from desktop_storage import read_json
from desktop_tasks import normalize_tasks
from datetime import datetime


def run_activities(directory, check_only=False, details_only=False):
    config = load_config(directory)
    if details_only:
        check_only = True
        config = {**config, "enabled": ["chronicle"]}
    session = read_json(directory / "session.json")
    if any(not session.get(key) for key in ("userId", "uin", "token")):
        raise ActivityError("助手登录态字段不完整，请重新扫码")
    http = ActivityHttp()
    summary = {"actions": [], "pending": [], "exp_total": None, "activities": []}
    catalog = available_activities()
    try:
        for key in catalog:
            if key not in config["enabled"]:
                continue
            name, _, url = catalog[key]
            if not details_only:
                print(f"\n开始活动：{name}", flush=True)
            before = len(summary["pending"])
            action_start = len(summary["actions"])
            def execute():
                if key == "chronicle":
                    import daily
                    from activity_chronicle import run_chronicle_extras
                    if details_only:
                        tasks = daily.merged_tasks()
                        summary["tasks"] = normalize_tasks(tasks)
                        summary["tasks_updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        import peak_client as pc
                        from activity_http import ensure_success
                        top = ensure_success(pc.call("POST", "/yoyo/dnf/getuseractivitytopinfo")).get("data", {})
                        summary["exp_total"] = top.get("totalExp")
                        summary["level"] = top.get("level")
                        return
                    # 先只读验证登录，失效时停止本活动，避免连续错误和误报 KeyError。
                    daily.merged_tasks()
                    result = run_step(summary, "编年有礼日常任务", lambda: daily.run(check_only=check_only))
                    if result:
                        summary["actions"].extend(result["actions"])
                        summary["pending"].extend(result["pending"])
                        summary["exp_total"] = result.get("exp_total")
                        summary["level"] = result.get("level")
                    run_chronicle_extras(summary, check_only)
                    # 补充领奖流程完成后重新查询，避免把领奖前状态作为最终结果。
                    tasks = run_step(summary, "刷新每日任务详情", daily.merged_tasks)
                    if tasks is not None:
                        summary["tasks"] = normalize_tasks(tasks)
                        summary["tasks_updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                elif key == "assistant_event":
                    from activity_assistant import run_assistant_event
                    run_assistant_event(http, session, config, summary, check_only)
                elif key in ("phone", "landing", "jinggai", "recall"):
                    from activity_ide import IdeActivity
                    IdeActivity(http, key, url, session, config).run(summary, check_only)
            run_step(summary, "只读查询任务详情" if details_only else name, execute, quiet_success=details_only)
            if not details_only:
                records = [{"action": item["action"], "result": item["result"]}
                           for item in summary["actions"][action_start:]]
                records.extend({"action": message, "result": "待处理"} for message in summary["pending"][before:])
                summary.setdefault("activity_tasks", {})[key] = records
            summary["activities"].append({"id": key, "name": name,
                                           "status": "有待处理项" if len(summary["pending"]) > before else "检查完成" if check_only else "执行完成"})
    finally:
        http.session.close()
    return summary
