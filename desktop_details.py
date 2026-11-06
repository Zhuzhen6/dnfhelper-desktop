"""选中账户的本地角色信息与最近一次任务结果。Created by 朱圳。"""
from tkinter import StringVar, ttk

from desktop_storage import read_json
from desktop_theme import fit_table_columns


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
        ttk.Label(self.frame, text="每日任务详情", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        table = ttk.Frame(self.frame, style="Surface.TFrame")
        table.pack(fill="both", expand=True)
        columns = ("name", "my_exp", "my_status", "partner_exp", "partner_status")
        self.tasks = ttk.Treeview(table, columns=columns, show="headings", height=7)
        self.tasks.tag_configure("done", foreground="#1E6B50")
        self.tasks.tag_configure("pending", foreground="#A36800")
        self.tasks.tag_configure("unfinished", foreground="#73777D")
        for key, title, width in zip(columns, ("任务名称", "我的经验", "我的状态", "队友经验", "队友状态"),
                                     (180, 70, 70, 70, 70)):
            self.tasks.heading(key, text=title, anchor="w")
            self.tasks.column(key, width=width, minwidth=width, stretch=key == "name")
        fit_table_columns(self.tasks)
        self.tasks.pack(fill="both", expand=True)
        self.note = StringVar(value="选择账户后自动刷新任务详情。")
        ttk.Label(self.frame, textvariable=self.note, style="Hint.TLabel", wraplength=440).pack(fill="x", pady=(12, 0))

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
        for task in result.get("tasks", []):
            status = task.get("my_status", "未知")
            tag = "done" if status == "已领取" else "pending" if status == "待领取" else "unfinished"
            self.tasks.insert("", "end", tags=(tag,), values=(task.get("name", "任务"), task.get("my_exp", "—"),
                              task.get("my_status", "未知"), task.get("partner_exp", "—"),
                              task.get("partner_status", "未知")))
        pending = len(result.get("pending", []))
        self.note.set(f"更新于 {result.get('tasks_updated_at', '未知')}，{pending} 项待处理。"
                      if "tasks" in result else "选择账户后自动查询任务详情，请稍候。")
        if expired:
            self.note.set("助手登录已过期，请右键账户选择“扫码更新登录”。")
