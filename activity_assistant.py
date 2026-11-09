"""助手模板活动：签到、补签、累计奖励和可选抽奖。"""
from activity_catalog import beijing_now
from activity_http import ActivityError, run_step


def run_assistant_event(http, session, config, summary, check_only):
    def call(action, **extra):
        payload = {"r": f"activitytpl/{action}", "activityId": "10085", "source": "dz", "from": "tpl",
                   "cCurrentGameId": "10014", "uin": session["uin"], "userId": session["userId"],
                   "token": session["token"], "serverId": session.get("sPartition", ""),
                   "areaId": session.get("areaId", ""), "originalRoleId": session.get("sRoleId", ""),
                   "cGameId": "1006", "cClientVersionCode": "2103080309",
                   "getNavUaStr": "GameHelper GameHelper_1006/2103080309", **extra}
        if not payload["originalRoleId"] or not payload["serverId"] or not payload["areaId"]:
            raise ActivityError("助手活动缺少角色或 area_id，请重新扫码登录助手以获取角色区域")
        return http.json("POST", "https://dzhu.qq.com/zangyi/activity/act", data=payload)["data"]

    def step(name, action, **extra):
        return run_step(summary, name, lambda: call(action, **extra))

    tasks = step("查询米歇尔任务", "task/config")
    if tasks is None:
        return
    if check_only:
        step("查询米歇尔签到", "checkin/data")
        step("查询米歇尔抽奖次数", "lottery/config")
        return
    for task in tasks["taskConfig"]:
        if int(task["status"]) == 2:
            continue
        if int(task["status"]) == 0:
            if any(word in task["title"] for word in ("疲劳", "通关", "在线", "游戏登录")):
                step(f"领取活动任务 {task['title']}", "task/pickupReward", taskId=task["id"])
                continue
            if step(f"完成活动任务 {task['title']}", "task/done", taskId=task["id"]) is None:
                continue
        step(f"领取活动任务 {task['title']}", "task/pickupReward", taskId=task["id"])
    today = beijing_now().strftime("%Y-%m-%d")
    status = step("查询活动签到状态", "checkin/data")
    calendar = step("查询活动签到日历", "checkin/config")
    if status is None or calendar is None:
        return
    remaining = min(max(int(status["recheckin_count"]), 0), 100)
    for day in calendar["dailyCheckIns"]:
        if day["date"] > today:
            continue
        if day["date"] == today and int(day["status"]) == 0:
            step("活动今日签到", "checkin/checkIn", date=today, reCheckIn=0)
        elif config.get("recheckin", False) and int(day["status"]) == 2 and remaining > 0:
            result = step(f"活动补签 {day['date']}", "checkin/checkIn", date=day["date"], reCheckIn=1)
            if result is not None:
                remaining -= 1
    calendar = step("刷新活动累计签到", "checkin/config")
    if calendar:
        for reward in calendar["totalCheckIns"]:
            if int(reward["status"]) == 1:
                step(f"累计签到 {reward['value']} 天奖励", "checkin/pickupTotalReward", value=reward["value"])
        for reward in calendar["activeCheckIns"]["list"]:
            if int(reward["status"]) == 1:
                step(f"周期签到奖励 {reward['cycleLabel']}", "checkin/pickupActiveCheckInReward", id=reward["id"])
    if config.get("lottery", False):
        lottery = step("查询活动剩余抽奖次数", "lottery/config")
        if lottery:
            for index in range(min(max(int(lottery["remainDrawTimes"]), 0), 100)):
                if step(f"活动抽奖 {index + 1}", "lottery/draw") is None:
                    break
