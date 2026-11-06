"""选中账户的本地角色信息与最近一次任务结果。Created by 朱圳。"""
from tkinter import StringVar, ttk

from desktop_storage import read_json
from activity_config import load_config
from activity_tasks import activity_task_rows


def read_account_snapshot(directory):
    """只读取本机保存的信息，切换账户时不触发网络请求。"""
    values = []
    for filename in ("session.json", "result.json"):
        try:
            value = read_json(directory / filename)
            values.append(value if isinstance(value, dict) else {})
        except (OSError, ValueError):
            values.append({})
    return values


class AccountDetails:
    def __init__(self, parent):
        self.frame = ttk.Frame(parent, style="Panel.TFrame", padding=16)
        ttk.Label(self.frame, text="账户详情", style="Section.TLabel").pack(anchor="w")
        self.identity = StringVar(value="选择一个账户，查看角色与任务结果。")
        ttk.Label(self.frame, textvariable=self.identity, style="Hint.TLabel", wraplength=440,
                  justify="left").pack(fill="x", pady=(12, 16))
        ttk.Label(self.frame, text="已选活动任务详情", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        self.note = StringVar(value="选择账户后自动刷新任务详情。")
        ttk.Label(self.frame, textvariable=self.note, style="Hint.TLabel", wraplength=440).pack(
            side="bottom", fill="x", pady=(12, 0))
        table = ttk.Frame(self.frame, style="Surface.TFrame")
        table.pack(fill="both", expand=True)
        columns = ("my_exp", "my_status", "partner_exp", "partner_status")
        style = ttk.Style(parent)
        style.configure("ActivityTasks.Treeview.Heading", padding=(4, 10))
        self.tasks = ttk.Treeview(table, columns=columns, show="tree headings", height=7,
                                  style="ActivityTasks.Treeview")
        self.tasks.heading("#0", text="活动 / 任务", anchor="w")
        self.tasks.column("#0", width=200, minwidth=120, stretch=True)
        self.tasks.tag_configure("activity", background="#EDF3FA", foreground="#1D1D1F")
        self.tasks.tag_configure("done", foreground="#1E6B50")
        self.tasks.tag_configure("pending", foreground="#A36800")
        self.tasks.tag_configure("unfinished", foreground="#73777D")
        for key, title, width in zip(columns, ("我的经验", "我的状态", "队友经验", "队友状态"),
                                     (70, 70, 70, 70)):
            self.tasks.heading(key, text=title, anchor="w")
            self.tasks.column(key, width=width, minwidth=width, stretch=False)
        self.tasks.pack(fill="both", expand=True)

    def show(self, account, directory=None):
        self.tasks.delete(*self.tasks.get_children())
        if account is None:
            self.identity.set("选择一个账户，查看角色与任务结果。")
            self.note.set("多选时可批量执行，详情只显示单个账户。")
            return
        session, result = read_account_snapshot(directory)
        self.identity.set(
            f"{account['name']}    QQ  {session.get('uin') or '未登录'}\n"
            f"角色  {session.get('roleName') or '待同步'}    等级  {session.get('roleLevel') or '—'}\n"
            f"区服  {session.get('serverName') or '待同步'}\n"
            f"编年等级  {result.get('level') or '—'}    经验  {result.get('exp_total') if result.get('exp_total') is not None else '—'}\n"
            f"每日定时  {account['time'] if account['enabled'] else '未开启'}")
        expired = result.get("auth_expired") or any(
            "-30003" in str(message) or "auth verification failed" in str(message)
            for message in result.get("pending", []))
        try:
            config = load_config(directory)
            rows = activity_task_rows(config, result)
            group = ""
            for values in rows:
                status = values[2]
                if status == "活动":
                    group = self.tasks.insert("", "end", text=values[0], open=True,
                                              tags=("activity",), values=("", "", "", ""))
                    continue
                tag = "done" if status in ("已领取", "完成") else "pending" if status in ("待领取", "待处理") else "unfinished"
                self.tasks.insert(group, "end", text=values[0], tags=(tag,), values=values[1:])
        except (OSError, ValueError):
            self.note.set("活动配置读取失败，请重新保存活动配置。")
            return
        pending = len(result.get("pending", []))
        self.note.set(f"更新于 {result.get('tasks_updated_at', '未知')}，{pending} 项待处理。"
                      if "tasks" in result else "已列出所选活动计划；待查询不代表已完成。")
        if expired:
            self.note.set("助手登录已过期，请右键账户选择“扫码更新登录”。")
