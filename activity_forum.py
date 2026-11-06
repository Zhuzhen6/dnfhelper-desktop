"""DNF 官方论坛签到，不引入已到期的论坛兑换活动。"""
import html
import re

from activity_http import ActivityError, run_step


def run_forum(http, config, summary, check_only):
    cookie = config.get("forum_cookie", "")
    if not cookie:
        raise ActivityError("请填写该账户的 DNF 论坛 Cookie")
    headers = {"Cookie": cookie, "Referer": "https://dnf.gamebbs.qq.com/"}
    response = http.request("GET", "https://dnf.gamebbs.qq.com/home.php",
                            params={"mod": "spacecp", "ac": "credit"}, headers=headers)
    match = re.search(r"formhash=([a-fA-F0-9]+)", response.text)
    if not match:
        raise ActivityError("论坛 Cookie 已过期或无法读取 formhash")
    if check_only:
        print("论坛登录态可读取")
        return
    def sign():
        result = http.request("POST", "https://dnf.gamebbs.qq.com/plugin.php",
                              params={"id": "k_misign:sign", "operation": "qiandao",
                                      "formhash": match.group(1), "format": "empty"}, headers=headers)
        notice = re.search(r'<div id="messagetext"[^>]*>\s*<p>(.*?)</p>', result.text, re.S)
        if not notice:
            raise ActivityError("论坛未返回可识别的签到结果")
        message = html.unescape(re.sub(r"<[^>]+>", "", notice.group(1))).strip()
        if not any(word in message for word in ("成功", "已签到", "已经签到", "已签过", "已经签过")):
            raise ActivityError(message[:180])
        print(message)
        return True
    run_step(summary, "论坛签到", sign)
