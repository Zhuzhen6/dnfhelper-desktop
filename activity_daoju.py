"""道聚城签到、任务、聚豆兑换。协议参考 fzls/djc_helper。"""
import time
from datetime import datetime

from activity_http import ActivityError, require_cookie_identity, run_step


PUBLIC_KEY = b"""-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAoYepGcQuSHKCJK3HMQCW
iPVKJ2BGDILSFNWjD5k6Ass77+ZHmhy58zG96eD9jMwjnZwItA8jMGfGBlWTkPp6
yaKWJq0Dxqik99xBaLKnZN+Sxcfk3L8W7Mk+HoZZjurqdIjr73jDQbEzDeS3IzZG
XBm6AkuopduhMHfGAOaENJ3LjxcTN/KKNBfiIzg4CI/TX2RPTawlivlBsKXLKN8z
zziA5PQZfomld+jZX+f7Nn7ki08kqqCVINLVNJnj9JMXQI/2E6s6OVRQP1YE6wF/
qcLB0aEeDZWZyTA6h5a3h+CpCxOtmmTTX0wqH38XBwTMRHFxn9IhiIUTiTSJ053S
EQIDAQAB
-----END PUBLIC KEY-----"""


class DaojuActivity:
    def __init__(self, http, session, config):
        self.http, self.session, self.config = http, session, config
        self.cookie = config.get("web_cookie", "")
        values = require_cookie_identity(self.cookie, session["uin"])
        if not values.get("skey"):
            raise ActivityError("道聚城签到需要含 skey 的网页登录 Cookie")
        token = 5381
        for character in values["skey"]:
            token = (token * 33 + ord(character)) & 0x7fffffff
        self.csrf = token
        self.device = config["device_id"]
        oauth = config.get("daoju_oauth", {})
        self.oauth_cookie = self.cookie
        if oauth.get("openid") and oauth.get("access_token"):
            self.oauth_cookie = (f"djc_appSource=android; djc_appVersion=149; acctype=qc; appid=1101958653; "
                                 f"openid={oauth['openid']}; access_token={oauth['access_token']}")

    def params(self):
        from Crypto.Cipher import AES, PKCS1_v1_5
        from Crypto.PublicKey import RSA
        from Crypto.Util.Padding import pad
        plain = f"{self.session['uin']}+{self.device}+{int(time.time() * 1000)}+149".encode()
        encrypted = AES.new(b"se35d32s63r7m23m", AES.MODE_ECB).encrypt(pad(plain, 16))
        signature = PKCS1_v1_5.new(RSA.import_key(PUBLIC_KEY)).encrypt(encrypted).hex()
        return {"appVersion": "149", "sVersionName": "v4.7.3.0", "sDeviceID": self.device,
                "sDjcSign": signature, "osVersion": "Android-28", "ch": "10000", "appSource": "android"}

    def service(self, name, **extra):
        return self.http.json("GET", "https://djcapp.game.qq.com/daoju/igw/main/",
                              params={**self.params(), "_service": name, **extra},
                              headers={"Cookie": self.oauth_cookie, "Referer": "https://daoju.qq.com/"})

    def sign(self, flow):
        params = {**self.params(), "g_tk": self.csrf, "iFlowId": flow,
                  "month": datetime.now().strftime("%Y%m"), "sign_version": "1.0",
                  "iActivityId": "11117", "sServiceDepartment": "djc", "sServiceType": "dj"}
        return self.http.json("POST", "https://comm.ams.game.qq.com/ams/ame/amesvr",
                              params={"ameVersion": "0.3", "iActivityId": "11117", "sServiceType": "dj",
                                      "sServiceDepartment": "djc", "set_info": "newterminals", **self.params()},
                              data=params, headers={"Cookie": self.cookie, "Referer": "https://daoju.qq.com/"})

    def reward(self, rule):
        return self.http.json("GET", "https://djcapp.game.qq.com/daoju/v3/api/we/usertaskv2/Usertask.php",
                              params={**self.params(), "iAppId": "1001", "appid": "1001", "_app_id": "1001",
                                      "output_format": "json", "iruleId": rule, "optype": "receive_usertask"},
                              headers={"Cookie": self.cookie})

    def run(self, summary, check_only):
        def service(label, name, **extra):
            return run_step(summary, label, lambda: self.service(name, **extra))
        balance = service("查询聚豆余额", "app.bean.balance", method="balance", iAppId="1001", _app_id="1001")
        if balance:
            print(f"聚豆余额：{balance.get('data', {}).get('balance', '未知')}")
        roles = self.service("app.role.bind_list", type="1", output_format="json").get("data", [])
        binding = next((item.get("sRoleInfo") for item in roles if item.get("sBizCode") == "dnf"), None)
        if (not isinstance(binding, dict) or str(binding.get("roleCode")) != str(self.session.get("sRoleId"))
                or str(binding.get("serviceID")) != str(self.session.get("sPartition"))):
            raise ActivityError("道聚城绑定角色与助手所选角色不一致，请先调整官方绑定")
        mobile_roles = {item.get("sBizCode"): item.get("sRoleInfo", {}) for item in roles}
        run_step(summary, "查询道聚城任务", lambda: self.http.json(
            "GET", "https://djcapp.game.qq.com/daoju/v3/api/we/usertaskv2/Usertask.php",
            params={**self.params(), "iAppId": "1001", "optype": "get_usertask_list", "output_format": "json"},
            headers={"Cookie": self.cookie}))
        if check_only:
            return
        service("道聚城 App 登录记录", "app.login.user.first")
        run_step(summary, "道聚城签到", lambda: self.sign("96939"))
        run_step(summary, "领取签到聚豆", lambda: self.sign("324410"))
        status = run_step(summary, "查询本月签到天数", lambda: self.sign("321961"))
        if status:
            days = int(status["modRet"]["jData"]["monthNum"])
            from calendar import monthrange
            now = datetime.now()
            for required, flow in ((3, "322021"), (7, "322036"), (10, "322037"), (15, "322038"),
                                   (20, "322039"), (25, "322040"), (monthrange(now.year, now.month)[1], "881740")):
                if days >= required:
                    run_step(summary, f"累计签到 {required} 天聚豆", lambda flow=flow: self.sign(flow))
        service("道聚城活动中心任务", "app.task.report", task_type="activity_center")
        mobile = self.config.get("daoju_mobile_game", "")
        if mobile:
            run_step(summary, "道聚城礼包达人", lambda: self.mobile_gift(mobile, mobile_roles))
        if self.config.get("daoju_wish", False):
            run_step(summary, "道聚城许愿任务", lambda: self.make_wish(mobile_roles))
        for rule in ("100066", "100040", "302124", "100001", "100002"):
            run_step(summary, f"领取道聚城任务 {rule}", lambda rule=rule: self.reward(rule))
        self.exchange(summary)
        run_step(summary, "兑换有礼任务领奖", lambda: self.reward("327091"))

    def mobile_gift(self, bizcode, roles):
        role = roles.get(bizcode)
        if not role:
            raise ActivityError("指定手游未在道聚城绑定角色")
        result = self.service("app.package.list", bizcode=bizcode, showType="qq", platform="android")
        gifts = sorted((gift for gift in result["data"]["list"]["data"] if int(gift["iCategory"]) == 10),
                       key=lambda gift: int(gift["iSort"]))
        index = datetime.now().weekday()
        if len(gifts) <= index:
            raise ActivityError("该手游缺少当天签到礼包，请选择其他手游")
        self.service("app.package.receive", bizcode=bizcode, iruleId=gifts[index]["iruleId"],
                     systemID=role.get("systemID", ""), sPartition=role.get("areaID", ""),
                     roleCode=role.get("roleCode", ""), sRoleName=role.get("roleName", ""),
                     channelID=role.get("channelID", ""), channelKey=role.get("channelKey", ""),
                     appid="1001", output_format="json", optype="receive_usertask_game")

    def make_wish(self, roles):
        role = roles.get("yxzj")
        if not role or "苹果" in str(role.get("channelKey", "")):
            raise ActivityError("许愿需要在道聚城绑定 Android 王者荣耀角色")
        existing = self.service("app.demand.user.demand", appUid=self.session["uin"], pn="1", ps="5")
        if existing.get("data", {}).get("list"):
            raise ActivityError("已有许愿单，程序保留原单；如需重新许愿请先在道聚城手动管理")
        catalog = self.service("app.goods.list", plat=role.get("systemID", ""), biz="yxzj",
                               wishing="1", view="biz_portal", page="1", ordertype="desc", orderby="dtModifyTime")
        goods = catalog.get("data", {}).get("goods", [])
        if not goods:
            raise ActivityError("当前没有可许愿道具")
        item = goods[0]
        variants = item.get("valiDate", [])
        if not variants:
            raise ActivityError("许愿道具信息不完整")
        self.service("app.demand.create", iActionId=item["type"], iGoodsId=variants[0]["code"],
                     sBizCode="yxzj", partition=role.get("serviceID") or role.get("areaID", ""),
                     iZoneId=role.get("channelID", ""), platid=role.get("systemID", "0"),
                     sZoneDesc=role.get("serviceName", ""), sRoleId=role.get("roleCode", ""),
                     sRoleName=role.get("roleName", ""), sGetterDream="每日许愿", iAppId="1001", _app_id="1001")

    def exchange(self, summary):
        for item in self.config.get("daoju_exchange", []):
            def exchange(item=item):
                if not self.session.get("sRoleId") or not self.session.get("sPartition"):
                    raise ActivityError("聚豆兑换缺少助手领奖角色，请先登录助手")
                for _ in range(item["count"]):
                    self.http.json("GET", "https://apps.game.qq.com/cgi-bin/daoju/v3/hs/i_buy.cgi",
                                   params={**self.params(), "iGoodsSeqId": item["id"],
                                           "iZone": self.session["sPartition"], "lRoleId": self.session["sRoleId"],
                                           "rolename": self.session.get("roleName", ""), "iActionId": "2594",
                                           "iActionType": "26", "_biz_code": "dnf", "biz": "dnf", "appid": "1003",
                                           "_app_id": "1003", "_output_fmt": "1", "_plug_id": "9800", "_from": "app", "_cs": "2"},
                                   headers={"Cookie": self.cookie})
            run_step(summary, f"聚豆兑换 {item['id']}", exchange)
