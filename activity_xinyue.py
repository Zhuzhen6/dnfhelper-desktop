"""心悦特权专区与 App 操作，分别使用对应应用授权。"""
import json

from activity_http import ActivityError, ensure_success, run_step


def oauth_headers(config):
    oauth = config.get("xinyue_oauth", {})
    if not oauth.get("openid") or not oauth.get("access_token"):
        raise ActivityError("请配置心悦特权授权，appid 为 101478665")
    return {"t-account-type": "qc", "t-mode": "true", "t-appid": "101478665",
            "t-openid": oauth["openid"], "t-access-token": oauth["access_token"]}


def run_xinyue(http, session, config, summary, check_only):
    headers = oauth_headers(config)
    binding = http.json("POST", "https://agw.xinyue.qq.com/amp2.RoleSrv/GetBindRole",
                        json={"game_code": "dnf", "device": "pc", "scene": "ceiba"}, headers=headers)
    roles = binding.get("roles", [])
    role = next((role for role in roles if str(role.get("role_id")) == str(session.get("sRoleId"))
                 and str(role.get("partition_id")) == str(session.get("sPartition"))), None)
    if not role:
        raise ActivityError("心悦绑定角色与助手领奖角色不一致，请先在心悦页绑定")
    if role.get("game_open_id") and str(role["game_open_id"]).lstrip("o0") != str(session["uin"]).lstrip("o0"):
        raise ActivityError("心悦授权与当前 QQ 不一致")

    def call(flow, extra=None):
        response = http.json("POST", "https://agw.xinyue.qq.com/amp2.WPESrv/WPEIndex",
                             params={"flowId": str(flow), "actId": "15488"}, headers=headers,
                             json={"biz_id": "tgclub", "act_id": "15488", "flow_id": int(flow), "role": role,
                                   "data": json.dumps({"pNum": 1, "ceiba_plat_id": "ios", "cExtData": {}, **(extra or {})})})
        value = response.get("data")
        if isinstance(value, str) and value:
            value = json.loads(value)
        if isinstance(value, dict):
            ensure_success(value)
            return value
        return response

    def step(name, flow):
        return run_step(summary, name, lambda: call(flow))
    member = step("查询心悦会员等级", 131053)
    step("查询心悦勇士币", 131050)
    step("查询心悦成就点", 131049)
    step("查询心悦抽奖次数", 131051)
    if check_only or member is None:
        return
    step("领取返利勇士币", 131143)
    level = int(member["value"])
    if level in (0, 10):
        gift_flows = (130718, 130745)
    elif level == 1:
        gift_flows = (130742, 130746)
    elif level in (2, 3):
        gift_flows = (130743, 130785)
    elif level in (4, 5):
        gift_flows = (130744, 130786)
    else:
        raise ActivityError("心悦会员等级规则已更新")
    for flow in gift_flows:
        step(f"领取心悦周期礼包 {flow}", flow)
    for flow, label in ((131323, "高级运镖"), (131322, "中级运镖"), (131305, "初级运镖"),
                        (131432, "队伍三次运镖奖励")):
        step(label, flow)
    for operation in config.get("xinyue_operations", []):
        for _ in range(operation["count"]):
            if step(f"心悦指定任务或兑换 {operation['id']}", int(operation["id"])) is None:
                break
    if config.get("lottery", False):
        tickets = step("刷新心悦抽奖次数", 131051)
        if tickets:
            for index in range(min(max(int(tickets["remain"]), 0), 100)):
                if step(f"心悦抽奖 {index + 1}", 131324) is None:
                    break


def run_xinyue_app(http, config, summary, check_only):
    oauth = config.get("xinyue_app_oauth", {})
    if not oauth.get("openid") or not oauth.get("access_token"):
        raise ActivityError("请配置心悦 App 授权，appid 为 101484782")
    operations = config.get("xinyue_app_operations", [])
    if not operations:
        raise ActivityError("请导入心悦 App 操作请求体；原项目此功能同样需要用户提供抓包配置")
    if check_only:
        print(f"心悦 App 配置包含 {len(operations)} 项操作；加密接口无通用只读校验，不发送操作请求")
        return
    for operation in operations:
        def execute(operation=operation):
            response = http.request("POST", "https://a.xinyue.qq.com/", data=bytes.fromhex(operation["body_hex"]),
                                    headers={"Cookie": f"xyapp_login_type=qc;access_token={oauth['access_token']};openid={oauth['openid']};appid=101484782",
                                             "Referer": "https://apps.game.qq.com/php/tgclub/v2/",
                                             "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                                             "User-Agent": "tgclub/5.7.6.81(Xiaomi MIX 2;android 9;Scale/440;android)"})
            if response.is_redirect:
                raise ActivityError("心悦 App 授权已失效")
            print("心悦 App 已收到 HTTP 200 响应，业务结果需在 App 中核对")
            summary["pending"].append(f"心悦 App {operation['name']}：响应为加密协议，请在 App 核对业务结果")
        run_step(summary, f"心悦 App {operation['name']}", execute)
