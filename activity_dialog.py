"""仅通过扫码授权的账户活动选择。Created by 朱圳。"""
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from activity_catalog import WEB_ACTIVITIES, available_activities
from activity_config import load_config, save_config, save_web_authorization
from desktop_storage import read_json
from desktop_theme import COLORS, create_checkbox_images


def show_activity_dialog(parent, directory, name, on_change=None):
    try:
        config = load_config(directory)
    except (ValueError, OSError) as error:
        messagebox.showerror("读取失败", str(error), parent=parent)
        return
    window = tk.Toplevel(parent)
    window.withdraw()
    window.title(f"活动配置 · {name}")
    window.geometry(f"820x{min(900, max(600, window.winfo_screenheight() - 100))}")
    window.minsize(760, 600)
    window.configure(background=COLORS["background"])
    window.transient(parent)
    heading = ttk.Frame(window, padding=(24, 20, 24, 0))
    heading.pack(fill="x")
    ttk.Label(heading, text="活动配置", style="Title.TLabel").pack(side="left")
    ttk.Label(heading, text=name, style="Badge.TLabel").pack(side="right", pady=8)
    ttk.Label(window, text="勾选活动并保存，手动执行与每日定时共用以下设置。",
              style="Muted.TLabel").pack(anchor="w", padx=24, pady=(8, 16))
    footer = ttk.Frame(window, padding=(24, 12, 24, 16))
    footer.pack(side="bottom", fill="x")
    content = ttk.Frame(window)
    content.pack(fill="both", expand=True, padx=16)
    canvas = tk.Canvas(content, background=COLORS["background"], highlightthickness=0,
                       borderwidth=0, yscrollincrement=20)
    canvas.pack(side="left", fill="both", expand=True)
    panel = ttk.Frame(canvas, padding=16, style="Panel.TFrame")
    panel_item = canvas.create_window((0, 0), window=panel, anchor="nw")
    panel.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda event: canvas.itemconfigure(panel_item, width=event.width))

    def scroll_content(event):
        if canvas.yview() != (0.0, 1.0):
            if getattr(event, "num", None) in (4, 5):
                amount = -1 if event.num == 4 else 1
            elif not event.delta:
                return
            else:
                amount = -int(event.delta / 120) if abs(event.delta) >= 120 else (-1 if event.delta > 0 else 1)
            canvas.yview_scroll(amount, "units")
        return "break"

    window.bind("<MouseWheel>", scroll_content)
    window.bind("<Button-4>", scroll_content)
    window.bind("<Button-5>", scroll_content)
    def authorization_text():
        if not config["web_cookie"]:
            return "○ 未授权 · 官网类活动需扫码授权"
        updated = config["web_authorized_at"]
        return "✓ 授权已保存，待验证" + (f" · {updated}" if updated else " · 已保存")

    authorization_status = tk.StringVar(value=authorization_text())
    authorization = ttk.Frame(panel, style="Surface.TFrame")
    authorization.pack(fill="x", pady=(0, 14))
    authorization_label = ttk.Label(authorization, textvariable=authorization_status, style="Hint.TLabel",
                                    foreground="#23834B" if config["web_cookie"] else COLORS["muted"])
    authorization_label.pack(side="left")

    def authorize_web():
        try:
            session = read_json(directory / "session.json")
        except (ValueError, OSError):
            session = {}
        if not session.get("uin"):
            messagebox.showinfo("请先登录", "请先为该账户扫码登录助手。", parent=window)
            return
        from activity_web_login import show_web_login

        def received(cookie):
            target, target_name = save_web_authorization(directory, cookie)
            if target == directory:
                config.update(load_config(target))
                authorization_status.set(authorization_text())
                authorization_label.configure(foreground="#23834B")
            else:
                authorization_status.set(authorization_text())
            if on_change:
                on_change()
            window.after(100, lambda: messagebox.showinfo(
                "扫码授权成功", f"已更新「{target_name}」的网页登录授权，已自动保存。", parent=window))

        show_web_login(window, received)

    ttk.Button(authorization, text="扫码授权", command=authorize_web).pack(side="right")
    window.checkbox_images = create_checkbox_images(window)
    variables = {}
    style = ttk.Style(window)
    style.layout("Activity.TCheckbutton", [("Checkbutton.padding", {"sticky": "nswe", "children": [
        ("Checkbutton.focus", {"sticky": "nswe", "children": [("Checkbutton.label", {"sticky": "nswe"})]})]})])

    def checkbox(parent_frame, text, variable):
        control = ttk.Checkbutton(parent_frame, text=text, variable=variable, compound="left")
        # 保留键盘操作和焦点，只用首页图像替换系统小勾选框。
        control.configure(style="Activity.TCheckbutton", image=(window.checkbox_images[0], "selected", window.checkbox_images[1]))
        control.pack(side="left")
        return control

    selection_bar = ttk.Frame(panel, style="Surface.TFrame")
    selection_bar.pack(fill="x", pady=(0, 8))
    ttk.Label(selection_bar, text="活动选择", style="Section.TLabel").pack(side="left")

    def update_select_all():
        select_all.configure(text="取消全选" if variables and all(value.get() for value in variables.values()) else "全选")

    def toggle_all():
        checked = not all(value.get() for value in variables.values())
        for value in variables.values():
            value.set(checked)
        update_select_all()

    select_all = ttk.Button(selection_bar, text="全选", command=toggle_all)
    select_all.pack(side="right")
    for key, (title, end, url) in available_activities().items():
        row = ttk.Frame(panel, style="Surface.TFrame")
        row.pack(fill="x", pady=3)
        variables[key] = tk.BooleanVar(value=key in config["enabled"])
        checkbox(row, title, variables[key])
        variables[key].trace_add("write", lambda *args: update_select_all())
        ttk.Button(row, text="官方页面", command=lambda url=url: webbrowser.open(url)).pack(side="right")
        ttk.Label(row, text=f"至 {end[:10]}" if end else "长期", style="Hint.TLabel").pack(side="right", padx=10)
    update_select_all()
    ttk.Separator(panel).pack(fill="x", pady=12)
    lottery = tk.BooleanVar(value=config["lottery"])
    recheckin = tk.BooleanVar(value=config["recheckin"])
    for text, variable in (("使用现有免费抽奖次数（米歇尔、落地页）", lottery),
                           ("使用米歇尔活动可用补签次数", recheckin)):
        row = ttk.Frame(panel, style="Surface.TFrame")
        row.pack(fill="x", pady=2)
        checkbox(row, text, variable)
    ttk.Label(panel, text="区域与角色自动读取助手账户；活动到期后自动隐藏。\n"
              "官网活动按官方页面当前绑定角色领奖；不满足资格的奖励会提示原因。",
              style="Hint.TLabel", wraplength=710).pack(anchor="w", pady=(14, 0))

    def save():
        selected = [key for key, variable in variables.items() if variable.get()]
        if WEB_ACTIVITIES.intersection(selected) and not config["web_cookie"]:
            messagebox.showinfo("需要扫码授权", "所选官网类活动需要网页登录授权，请先点击“扫码授权”。", parent=window)
            return
        try:
            saved = load_config(directory)
            save_config(directory, {**saved, "enabled": selected,
                                    "lottery": lottery.get(), "recheckin": recheckin.get()})
            if on_change:
                on_change()
            window.destroy()
        except (ValueError, OSError) as error:
            messagebox.showerror("保存失败", str(error), parent=window)

    ttk.Button(footer, text="保存活动配置", style="Primary.TButton", command=save).pack(side="right")
    ttk.Button(footer, text="取消", command=window.destroy).pack(side="right", padx=8)
    window.bind("<Escape>", lambda event: window.destroy())
    window.deiconify()
    window.grab_set()
    window.focus_set()
