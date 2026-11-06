"""当前活动目录；结束后不再展示和执行。Created by 朱圳。"""
from datetime import datetime
from zoneinfo import ZoneInfo


ACTIVITIES = {
    "chronicle": ("编年有礼与搭档奖励", "", "https://dzhu.qq.com/fe/dnf/calculation4.0/"),
    "assistant_event": ("米歇尔的审判", "2026-11-08 23:59:59", "https://dzhu.qq.com/fe/dnf/activity_template/"),
    "daoju": ("道聚城签到与领奖", "", "https://daoju.qq.com/mall/"),
    "phone": ("绑定手机月度领奖", "2029-03-31 23:59:59", "https://dnf.qq.com/cp/a20230817info/"),
    "forum": ("DNF 官方论坛签到", "", "https://dnf.gamebbs.qq.com/plugin.php?id=k_misign:sign"),
    "xiaoyue": ("小酱油周礼包与生日礼包", "", "https://tool.helper.qq.com/"),
    "xinyue": ("心悦特权专区", "", "https://act.xinyue.qq.com/act/a20231103dnf/index.html"),
    "xinyue_app": ("心悦 App 配置操作", "", "https://xinyue.qq.com/beta/#/download"),
    "landing": ("官网落地页活动", "2026-11-25 18:00:00", "https://dnf.qq.com/cp/celebration/index.html"),
    "jinggai": ("井盖杯强者之路", "2026-11-15 23:59:59", "https://dnf.qq.com/cp/a20261015covers3/index.html"),
    "recall": ("回流引导秘籍", "2026-11-26 23:59:59", "https://dnf.qq.com/cp/a20260107guide/"),
}


def beijing_now():
    return datetime.now(ZoneInfo("Asia/Shanghai"))


def available_activities(now=None):
    clock = now or beijing_now()
    if clock.tzinfo is not None:
        clock = clock.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
    return {key: value for key, value in ACTIVITIES.items()
            if not value[1] or clock <= datetime.strptime(value[1], "%Y-%m-%d %H:%M:%S")}
