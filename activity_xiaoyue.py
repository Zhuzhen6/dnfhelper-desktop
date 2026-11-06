"""小酱油周礼包、生日礼包与生日提醒。"""
import json
import re
from urllib.parse import parse_qs, quote, urlparse

from activity_http import ActivityError, require_cookie_identity, run_step


def run_xiaoyue(http, session, config, summary, check_only):
    cookie = config.get("web_cookie", "")
    require_cookie_identity(cookie, session["uin"])
    headers = {"Cookie": cookie, "Referer": "https://tool.helper.qq.com/"}
    response = http.request("GET", "https://user.game.qq.com/php/helper/xychat/open/redirect/1/2",
                            params={"areaId": session.get("sPartition", ""), "roleName": session.get("roleName", "")}, headers=headers)
    location = response.headers.get("Location", "")
    role_id = parse_qs(urlparse(location).query).get("role_id", [""])[0]
    if not role_id:
        raise ActivityError("小酱油无法获取角色，请更新网页登录 Cookie 并确认角色")

    def encoded(value):
        value = str(value)
        return f's:{len(value.encode())}:"{value}";'

    role = {"source": "xy_games", "game_id": "1", "role_id": role_id,
            "role_name": session.get("roleName", ""), "system_id": "2", "region_id": "1",
            "area_id": "1", "plat_id": "1", "partition_id": session.get("sPartition", ""), "acctype": ""}
    serialized = "a:10:{" + "".join(encoded(key) + encoded(value) for key, value in role.items()) + "}"
    headers["Cookie"] += f"; xychat_login_type=qq; xychat_lumen_role={quote(serialized, safe='')}"

    def call(path, **params):
        return http.json("GET", "https://xyapi.game.qq.com/xiaoyue/" + path,
                         params={"callback": "dnfhelperCallback", **params}, headers=headers)

    info = call("service/async")["result"]
    certificate = info.get("certificate")
    if not certificate:
        raise ActivityError("小酱油未返回 certificate，请重新登录")
    actual_role = info.get("role_info", {})
    if str(actual_role.get("role_id")) != role_id:
        raise ActivityError("小酱油当前角色与所选角色不一致")
    if check_only:
        print("小酱油身份与角色校验完成")
        return
    for question, question_id, robot_type in (("每周礼包", "11175574", "0"), ("生日礼包", "11090757", "0")):
        def claim(question=question, question_id=question_id, robot_type=robot_type):
            result = call("service/ask", question=question, question_id=question_id, robot_type=robot_type,
                          option_type="0", filter=question, rec_more="", certificate=certificate)
            text = json.dumps(result, ensure_ascii=False)
            birthday = re.search(r"你的生日是在(\d{4})年(\d{2})月(\d{2})日", text)
            if birthday:
                print(f"DNF 账号生日：{'-'.join(birthday.groups())}")
            answers = result.get("result", {}).get("answer", [])
            package = next((answer.get("content") for answer in answers
                            if isinstance(answer, dict) and isinstance(answer.get("content"), dict)
                            and all(key in answer["content"] for key in ("token", "ams_id", "package_group_id", "tool_id"))), None)
            if not package:
                raise ActivityError(f"{question}尚不可领或响应结构变化")
            return call("helper/package/get", certificate=certificate,
                        **{key: package[key] for key in ("token", "ams_id", "package_group_id", "tool_id")})
        run_step(summary, f"小酱油{question}", claim)
