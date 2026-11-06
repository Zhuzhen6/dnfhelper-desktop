#!/usr/bin/env python3
"""
用 QQ OAuth 凭证换 DNF 助手登录态，写出 session.json。

⚠ 思路示例。字段名与 App 版本相关，换版本需重新核对。

链路
----
    1. QQ 扫码           → openid + access_token   （见 qq_login.py）
    2. POST /user/login  → userId + token           （助手登录态）
    3. 直接可用          → 写 session.json 供 daily.py 使用

`/user/login` 的坑（这个错误码很有误导性）
-------------------------------------------
    -20002 服务器繁忙  ← 其实不是繁忙，是**少必填字段**
                         必须带 loginType=qqConnect（小写 l，不是 cLoginType）
    -20001 服务器繁忙  ← uin / cUin 是上一个账号的残留值
                         不要带 sdkp / sdkv / pf，带了也会退回 -20001

`uin` / `cUin` 必须都是当前账号的 QQ 号。

用法
----
    python login_new_account.py             # 有 qq_oauth.json 就直接换登录态
    python login_new_account.py --qr        # 一条龙：出码 → 扫码 → 换登录态 → 写 session.json
    python login_new_account.py --dry-run   # 只打印，不写 session.json
"""
import os
import sys

import native_client as nc
from desktop_storage import account_directory, read_json, write_json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OAUTH = str(account_directory() / "qq_oauth.json")
SESS = str(account_directory() / "session.json")


def parse_oauth() -> dict:
    if not os.path.exists(OAUTH):
        raise SystemExit("没有 qq_oauth.json，先跑 python qq_login.py qr 扫码")
    d = read_json(OAUTH)
    for k in ("openid", "access_token"):
        if not d.get(k):
            raise SystemExit(f"qq_oauth.json 缺少 {k}，重新扫码")
    return d


def main() -> int:
    args = sys.argv[1:]
    dry = "--dry-run" in args

    # --qr：一条龙 —— 出二维码、等扫码、换登录态、写 session.json
    if "--qr" in args or not os.path.exists(OAUTH):
        if not os.path.exists(OAUTH):
            print("没有 qq_oauth.json，先走扫码流程。\n")
        import subprocess
        r = subprocess.run([sys.executable,
                            os.path.join(BASE_DIR, "qq_login.py"), "qr"])
        if r.returncode != 0:
            return r.returncode

    oauth = parse_oauth()
    print("QQ 授权凭证已读取")

    # uin 不作为前置条件。
    #
    # ptuiCB 的成功 URL 有两种形态：一种带 uin=，一种（proxy.htm 形态）不带。
    # 但 `/user/login` 本身不需要 uin —— 它从 access_token 反查身份，
    # 响应里会直接返回 uin。所以这里能拿到就带上，拿不到就不带，
    # 不要因为缺 uin 就中止流程。
    uin = str(oauth.get("uin") or "")
    if not uin:
        url = oauth.get("_url", "")
        import re as _re
        m = _re.search(r"[?&#]uin=(\d+)", url)
        if m:
            uin = m.group(1)
    print(f"uin          = {uin or '（由服务端返回）'}")

    p = nc._device_params("1006")
    p.update({
        "appOpenid": oauth["openid"],
        "openid": oauth["openid"],
        "accessToken": oauth["access_token"],
        "loginType": "qqConnect",   # ★ 必需，且必须是这个大小写
    })
    # 这两个是上一个账号的残留，登录成功后才有值
    for k in ("userId", "token", "cUin", "uin"):
        p.pop(k, None)
    if uin:
        p.update({"uin": uin, "cUin": uin})

    r = nc.post("/user/login", p, auth=False)
    code = r.get("returnCode")
    print(f"/user/login -> returnCode={code} {r.get('returnMsg', '')}")
    if code != 0:
        return 3

    d = r["data"]
    sess = {
        "userId": d["userId"],
        "uin": d["uin"],
        "token": d["token"],
        "accessToken": oauth["access_token"],
        "appOpenid": oauth["openid"],
        # 角色字段：任务侧不需要，领礼包必须要。下面 fill_role() 自动填。
        "uniqueRoleId": "", "sRoleId": "", "sPartition": "",
        "gameId": "1006", "game_code": "dnf",
        "serverName": "", "roleName": "", "roleJob": "",
        "roleLevel": "", "areaName": "",
        "nickname": d.get("userName", ""),
        "appidTask": "1000042",
    }

    # 拿角色。礼包接口要这几组字段，缺了或填错就是
    #   2009 角色错误，请点击页面的[切换角色]按钮
    # 注意两个 ID 是**交叉对应**的，很容易填反：
    #   sRoleId      ← chatroles.originalRoleId   （活动页 URL 里叫 roleId）
    #   uniqueRoleId ← chatroles.roleId           （活动页 URL 里叫 uniqueRoleId）
    role_note = ""
    try:
        nc.use_auth(d["userId"], d["token"], d["uin"])
        roles = nc.chat_roles()
        if roles:
            m = next((x for x in roles if x.get("isMainRole")), roles[0])
            sess.update({
                "sRoleId": str(m.get("originalRoleId", "")),
                "uniqueRoleId": str(m.get("roleId", "")),
                "sPartition": str(m.get("serverId", "")),
                "serverName": m.get("serverName", ""),
                "roleName": m.get("roleName", ""),
                "roleJob": m.get("roleJob", ""),
                "roleLevel": str(m.get("level", "")),
                "areaName": m.get("areaName", ""),
                "areaId": str(m.get("areaId", "")),
            })
            role_note = (f"{m.get('roleName')} {m.get('serverName')} "
                         f"Lv.{m.get('level')}（共 {len(roles)} 个角色）")
        else:
            role_note = "未找到角色，礼包会报 2009"
    except Exception as ex:  # noqa: BLE001
        role_note = f"取角色失败：{ex}（礼包会报 2009）"

    print("\n登录成功：")
    print(f"  昵称   = {sess['nickname']}")
    print(f"  userId = {sess['userId']}")
    print(f"  角色   = {role_note}")
    if dry:
        print("\n--dry-run，未写 session.json")
        return 0

    write_json(SESS, sess, secret=True)
    print(f"\n已安全保存登录态：{SESS}，请勿外传")
    print("下一步：python daily.py --check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
