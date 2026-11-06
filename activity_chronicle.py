"""编年史补充功能，领取现有搭档奖励和指定碎片兑换。"""
from activity_http import ActivityError, ensure_success, run_step


def run_chronicle_extras(config, summary, check_only):
    import peak_client as pc
    import daily

    def call(method, path, extra=None):
        return ensure_success(pc.call(method, path, extra))

    partner_id = config.get("partner_user_id", "")
    if partner_id and not check_only:
        run_step(summary, "绑定指定搭档", lambda: call("POST", "/yoyo/dnf/bindUserPartner",
                 {"pUserId": partner_id, "isBind": "1"}))
    seen = set()
    for app_view, query in ((False, daily.task_snapshot), (True, daily.task_snapshot_app)):
        tasks = run_step(summary, "查询搭档任务（App）" if app_view else "查询搭档任务（H5）", query)
        for task in tasks or []:
            identifier = str(task.get("pActionId") or "")
            if not identifier or identifier in seen:
                continue
            seen.add(identifier)
            if int(task.get("pStatus", -1)) == 2 and not check_only:
                run_step(summary, f"搭档任务 {task.get('name', identifier)}",
                         lambda identifier=identifier, app_view=app_view: ensure_success(pc.claim_task(identifier))
                         if app_view else call("POST", "/yoyo/dnf/doactionincrexp", {"actionId": identifier}))

    signs = run_step(summary, "查询连续签到奖励", lambda: call("GET", "/peak/list/sign"))
    if signs and not check_only:
        for gift in signs.get("gifts", []):
            if int(gift.get("status", -1)) == 0:
                run_step(summary, f"连续签到奖励 {gift.get('date', '')}",
                         lambda gift=gift: ensure_success(pc.claim_sign(gift["date"])))
    basic = run_step(summary, "查询搭档等级礼包", lambda: call("GET", "/peak/list/basic"))
    if basic and basic.get("hasPartner") and not check_only:
        for gift in basic.get("basic2List", []):
            if int(gift.get("isLock", 1)) == 0 and int(gift.get("isUsed", 1)) == 0:
                run_step(summary, f"搭档礼包 {gift.get('giftName', '')}", lambda gift=gift: call(
                    "GET", "/peak/send/basic", {"isLock": "0", "amsid": gift["sLbCode"],
                     "iLbSel1": gift["iLbSel1"], "num": "1", "mold": "2"}))
    catalog = run_step(summary, "查询碎片兑换列表", lambda: call("GET", "/peak/list/exchange"))
    if catalog is None:
        return
    for gift in catalog.get("gifts", []):
        print(f"兑换项：{gift.get('sLbcode')} · {gift.get('sName')} · 消耗 {gift.get('iCard')} 碎片")
    if check_only:
        return
    gifts = {gift["sLbcode"]: gift for gift in catalog.get("gifts", [])}
    for item in config.get("chronicle_exchange", []):
        def exchange(item=item):
            gift = gifts.get(item["id"])
            if not gift or int(gift.get("isLock", 1)) != 0:
                raise ActivityError("指定奖励不存在或尚未解锁")
            for _ in range(item["count"]):
                call("GET", "/peak/send/exchange", {"exNum": "1", "iCard": gift["iCard"],
                     "amsid": gift["sLbcode"], "iNum": gift["iNum"], "isLock": gift["isLock"]})
        run_step(summary, f"碎片兑换 {item['id']}", exchange)
