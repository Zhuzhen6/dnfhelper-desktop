"""按账户配置串行执行活动，一个活动失败不影响后续活动。"""
from activity_catalog import available_activities
from activity_config import load_config
from activity_http import ActivityError, ActivityHttp, run_step
from desktop_storage import read_json


def run_activities(directory, check_only=False):
    config = load_config(directory)
    session = read_json(directory / "session.json")
    if any(not session.get(key) for key in ("userId", "uin", "token")):
        raise ActivityError("助手登录态字段不完整，请重新扫码")
    http = ActivityHttp()
    summary = {"actions": [], "pending": [], "exp_total": None, "activities": []}
    catalog = available_activities()
    try:
        for key in config["enabled"]:
            if key not in catalog:
                print("已跳过到期活动")
                continue
            name, _, url = catalog[key]
            print(f"\n开始活动：{name}", flush=True)
            before = len(summary["pending"])
            def execute():
                if key == "chronicle":
                    import daily
                    from activity_chronicle import run_chronicle_extras
                    result = run_step(summary, "编年有礼日常任务", lambda: daily.run(check_only=check_only))
                    if result:
                        summary["actions"].extend(result["actions"])
                        summary["pending"].extend(result["pending"])
                        summary["exp_total"] = result.get("exp_total")
                        summary["level"] = result.get("level")
                    run_chronicle_extras(config, summary, check_only)
                elif key == "assistant_event":
                    from activity_assistant import run_assistant_event
                    run_assistant_event(http, session, config, summary, check_only)
                elif key in ("phone", "landing", "jinggai", "recall"):
                    from activity_ide import IdeActivity
                    IdeActivity(http, key, url, session, config).run(summary, check_only)
                elif key == "daoju":
                    from activity_daoju import DaojuActivity
                    DaojuActivity(http, session, config).run(summary, check_only)
                elif key == "forum":
                    from activity_forum import run_forum
                    run_forum(http, config, summary, check_only)
                elif key == "xiaoyue":
                    from activity_xiaoyue import run_xiaoyue
                    run_xiaoyue(http, session, config, summary, check_only)
                elif key == "xinyue":
                    from activity_xinyue import run_xinyue
                    run_xinyue(http, session, config, summary, check_only)
                elif key == "xinyue_app":
                    from activity_xinyue import run_xinyue_app
                    run_xinyue_app(http, config, summary, check_only)
            run_step(summary, name, execute)
            summary["activities"].append({"id": key, "name": name,
                                           "status": "有待处理项" if len(summary["pending"]) > before else "检查完成" if check_only else "执行完成"})
    finally:
        http.session.close()
    return summary
