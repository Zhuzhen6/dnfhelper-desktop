"""账户活动开关、独立凭证与高级兑换配置。"""
import json
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from desktop_theme import COLORS, style_log

from activity_catalog import available_activities
from activity_config import load_config, save_config


def show_activity_dialog(parent, directory, name):
    try:
        config = load_config(directory)
    except (ValueError, OSError) as error:
        messagebox.showerror("读取失败", f"活动配置无法读取：{type(error).__name__}", parent=parent)
        return
    window = tk.Toplevel(parent)
    window.title(f"活动配置 · {name}")
    window.geometry("900x830")
    window.minsize(820, 790)
    window.configure(background=COLORS["background"])
    window.transient(parent)
    heading = ttk.Frame(window, padding=(24, 20, 24, 0))
    heading.pack(fill="x")
    ttk.Label(heading, text="活动配置", style="Title.TLabel").pack(side="left")
    ttk.Label(heading, text=name, style="Badge.TLabel").pack(side="right", pady=8)
    ttk.Label(window, text="为这个账户选择任务，手动执行与每日定时共用以下设置。",
              style="Muted.TLabel").pack(anchor="w", padx=24, pady=(8, 16))
    notebook = ttk.Notebook(window)
    notebook.pack(fill="both", expand=True, padx=15, pady=12)
    switches = ttk.Frame(notebook, padding=16, style="Surface.TFrame")
    credentials = ttk.Frame(notebook, padding=16, style="Surface.TFrame")
    advanced = ttk.Frame(notebook, padding=16, style="Surface.TFrame")
    notebook.add(switches, text="活动选择")
    notebook.add(credentials, text="授权与角色")
    notebook.add(advanced, text="兑换与高级配置")
    ttk.Label(switches, text="只展示当前有效活动，到期后自动隐藏并停止执行。", style="Hint.TLabel", wraplength=750).pack(anchor="w", pady=(0, 8))
    variables = {}
    for key, (title, end, url) in available_activities().items():
        row = ttk.Frame(switches, style="Surface.TFrame")
        row.pack(fill="x", pady=0)
        variables[key] = tk.BooleanVar(value=key in config["enabled"])
        ttk.Checkbutton(row, text=title + (f"（至 {end[:10]}）" if end else "（长期）"), variable=variables[key]).pack(side="left")
        ttk.Button(row, text="官方页面", command=lambda url=url: webbrowser.open(url)).pack(side="right")
    lottery = tk.BooleanVar(value=config["lottery"])
    recheckin = tk.BooleanVar(value=config["recheckin"])
    ttk.Checkbutton(switches, text="使用现有免费抽奖次数（米歇尔、落地页、心悦）", variable=lottery).pack(anchor="w", pady=(15, 4))
    ttk.Checkbutton(switches, text="使用米歇尔活动可用补签次数", variable=recheckin).pack(anchor="w")
    ttk.Label(switches, text="消耗碎片、聚豆、手机积分的兑换需在高级配置指定奖励。\n"
              "领取前请先在各官方活动页绑定与助手相同的角色。", style="Hint.TLabel", wraplength=750).pack(anchor="w", pady=8)

    credentials.columnconfigure(1, weight=1)
    fields = {}
    for row, (key, title) in enumerate((("web_cookie", "网页登录 Cookie（含 uin、skey）"),
                                       ("forum_cookie", "DNF 论坛 Cookie"), ("area_id", "游戏区域 area_id（助手模板活动）"),
                                       ("partner_user_id", "编年史固定搭档 userId（可留空）"))):
        ttk.Label(credentials, text=title, style="Surface.TLabel").grid(row=row * 2, column=0, columnspan=2, sticky="w", pady=(8, 2))
        variable = tk.StringVar(value=config[key])
        fields[key] = variable
        ttk.Entry(credentials, textvariable=variable, show="•" if "cookie" in key else "", width=70).grid(
            row=row * 2 + 1, column=0, columnspan=2, sticky="ew")
    oauth_fields = {}
    for offset, (key, title) in enumerate((("daoju_oauth", "道聚城 1101958653"),
                                         ("xinyue_oauth", "心悦特权 101478665"),
                                         ("xinyue_app_oauth", "心悦 App 101484782"))):
        row = 8 + offset * 2
        ttk.Label(credentials, text=f"{title}：openid / access_token", style="Surface.TLabel").grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 2))
        pair = [tk.StringVar(value=config[key].get(field, "")) for field in ("openid", "access_token")]
        oauth_fields[key] = pair
        for column, variable in enumerate(pair):
            ttk.Entry(credentials, textvariable=variable, show="•", width=34).grid(row=row + 1, column=column, sticky="ew", padx=(0, 6))
    ttk.Label(credentials, text="各应用授权不可混用。此处只在本机加密保存；不保存 QQ 密码。\n"
              "Cookie 过期时需重新登录官方页面后更新；论坛 Cookie 请使用当前账户本人登录态。",
              style="Hint.TLabel", wraplength=750).grid(row=14, column=0, columnspan=2, sticky="w", pady=12)

    ttk.Label(advanced, text="JSON 高级配置；留空列表表示不兑换。具体规则见 ACTIVITY_GUIDE.md。\n"
              "chronicle_exchange / daoju_exchange / xinyue_operations：[{\"id\":\"奖励或流程ID\",\"count\":1}]\n"
              "phone_exchange_index：0～6 的字符串或空字符串；心悦 App 操作需 name、body_hex。",
              style="Hint.TLabel", wraplength=750).pack(anchor="w", pady=(0, 10))
    editor = ScrolledText(advanced, font=("Consolas", 11), height=20)
    style_log(editor)
    editor.pack(fill="both", expand=True)
    keys = ("chronicle_exchange", "daoju_exchange", "xinyue_operations", "phone_exchange_index", "xinyue_app_operations",
            "daoju_mobile_game", "daoju_wish")
    editor.insert("1.0", json.dumps({key: config[key] for key in keys}, ensure_ascii=False, indent=2))

    def save():
        try:
            extra = json.loads(editor.get("1.0", "end"))
            if not isinstance(extra, dict) or set(extra) != set(keys):
                raise ValueError("高级配置需保留原有配置键")
            updated = {**config, **extra, "enabled": [key for key, variable in variables.items() if variable.get()],
                       "lottery": lottery.get(), "recheckin": recheckin.get(),
                       **{key: variable.get().strip() for key, variable in fields.items()}}
            for key, pair in oauth_fields.items():
                updated[key] = {field: variable.get().strip() for field, variable in zip(("openid", "access_token"), pair)}
                if not any(updated[key].values()):
                    updated[key] = {}
            save_config(directory, updated)
            window.destroy()
        except (ValueError, OSError) as error:
            messagebox.showerror("保存失败", str(error), parent=window)
    footer = ttk.Frame(window, padding=(24, 0, 24, 16))
    footer.pack(fill="x")
    ttk.Button(footer, text="保存活动配置", style="Primary.TButton", command=save).pack(side="right")
    ttk.Button(footer, text="取消", command=window.destroy).pack(side="right", padx=8)
    window.bind("<Escape>", lambda event: window.destroy())
    window.grab_set()
    window.focus_set()
