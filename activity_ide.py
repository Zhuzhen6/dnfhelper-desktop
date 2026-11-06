"""腾讯官网 IDE 活动，读取活动描述中的流程凭证和绑定信息。"""
from urllib.parse import quote

from activity_catalog import beijing_now
from activity_http import ActivityError, require_cookie_identity, run_step


IDE_ACTIVITIES = {
    "phone": "3_Rsi2sk", "landing": "19_4w6dsz",
    "jinggai": "27_TkwEUX", "recall": "80_yv5rVZ",
}


class IdeActivity:
    def __init__(self, http, key, url, session, config):
        self.http, self.key, self.url = http, key, url
        self.session, self.config = session, config
        self.cookie = config.get("web_cookie", "")
        require_cookie_identity(self.cookie, session["uin"])
        self.description = http.json("GET", f"https://comm.ams.game.qq.com/ide/page/{IDE_ACTIVITIES[key]}")

    def call(self, flow, **extra):
        descriptor = self.description.get("flows", {}).get(str(flow))
        if not descriptor or not descriptor.get("sIdeToken"):
            raise ActivityError("活动流程已变更，请更新程序")
        payload = {"iChartId": str(flow), "iSubChartId": str(flow),
                   "sIdeToken": descriptor["sIdeToken"], "e_code": "0", "g_code": "0",
                   "eas_url": quote(self.url, safe=""), **extra}
        return self.http.json("POST", "https://comm.ams.game.qq.com/ide/", data=payload,
                              headers={"Cookie": self.cookie, "Referer": self.url})

    def check_role(self):
        binding = next((item for item in self.description.get("default_tpls", []) if item.get("tpl") == "bind_area"), None)
        if not binding:
            raise ActivityError("未找到活动角色绑定配置")
        result = self.call(binding["query_map_id"])
        role = result.get("jData", {}).get("bindarea")
        if not isinstance(role, dict):
            raise ActivityError("请先在官方活动页绑定领奖角色")
        if not role.get("Farea") or not role.get("FroleId"):
            raise ActivityError("官方活动绑定信息不完整，请先在官方页面绑定领奖角色")
        return role

    def run(self, summary, check_only):
        if run_step(summary, "校验活动领奖角色", self.check_role) is None:
            return
        if check_only:
            return
        def step(name, flow, **extra):
            return run_step(summary, name, lambda: self.call(flow, **extra))
        if self.key == "phone":
            info = step("查询绑定手机月度状态", "414203")
            if info is None:
                return
            value = info["jData"]
            if int(value["bindFlag"]) != 0:
                raise ActivityError("尚未绑定手机，请在官方页面完成绑定")
            if int(value["isGetReward"]) == 0:
                step("领取首次绑定奖励", "415395")
            if int(value["isMonthDo"]) == 0:
                step("领取本月积分", "415262")
        elif self.key == "recall":
            step("记录回流指引浏览", "553425")
            step("领取回流指引奖励", "553424")
        elif self.key == "jinggai":
            step("井盖杯见面礼包", "625772")
            if beijing_now().strftime("%Y-%m-%d") >= "2026-11-09":
                step("井盖杯排名奖励", "625786")
            for flow, name in (("625790", "每日登录"), ("625791", "每日在线"),
                               ("625792", "每日疲劳"), ("625821", "每日命运抉择"),
                               ("625822", "每周深渊"), ("625823", "每周命运抉择")):
                step(f"井盖杯{name}领奖", flow)
            for index in range(1, 6):
                step(f"井盖杯累计奖励 {index}", "625872", rewardIndex=str(index))
        elif self.key == "landing":
            for flow, name in (("626853", "见面礼包"), ("626855", "深渊任务领奖"),
                               ("626859", "记录页面跳转"), ("626858", "浏览助手文章"),
                               ("626860", "浏览指定页面")):
                step(f"落地页{name}", flow)
            info = step("查询落地页抽奖次数", "626849")
            if info is None:
                return
            if self.config.get("lottery", False):
                for index in range(min(max(int(info["jData"]["iLottery"]), 0), 100)):
                    if step(f"落地页抽奖 {index + 1}", "626856") is None:
                        break
            info = step("查询落地页累计次数", "626849")
            if info:
                for index, required in enumerate((3, 6, 9, 12, 16, 20, 24, 28), 1):
                    if int(info["jData"]["iLotteryNum"]) >= required:
                        step(f"落地页累计 {required} 次奖励", "626857", index=str(index))
