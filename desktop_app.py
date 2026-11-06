"""账户管理、任务队列与桌面界面。"""
import os
import re
import shutil
import subprocess
import sys
import time
import tkinter as tk
import uuid
import webbrowser
from collections import deque
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from desktop_schedule import is_due, validate_time
from desktop_storage import atomic_write, data_directory, read_json, write_json
from desktop_theme import COLORS, apply_theme, fit_table_columns, style_log
from desktop_details import AccountDetails, read_account_snapshot


def load_accounts(path):
    if not path.exists():
        return []
    accounts = read_json(path)
    if not isinstance(accounts, list):
        raise ValueError("账户配置格式错误")
    identifiers = set()
    for account in accounts:
        identifier = account["id"]
        if not re.fullmatch(r"[a-f0-9]{32}", identifier) or identifier in identifiers:
            raise ValueError("账户标识无效或重复")
        identifiers.add(identifier)
        if not isinstance(account["name"], str) or not account["name"].strip():
            raise ValueError("账户名称无效")
        if not isinstance(account["enabled"], bool):
            raise ValueError("账户定时设置无效")
        validate_time(account["time"])
    return accounts


class DesktopApp:
    def __init__(self, root, directory, accounts):
        self.root = root
        self.directory = directory
        self.accounts = accounts
        self.queue = deque()
        self.current = None
        self.process = None
        self.started = 0
        self.offset = 0
        self.cancelled = False
        self.qr_window = None
        self.qr_image = None
        self.adding_account = None
        self.statuses = {}
        self.checked_accounts = set()
        self.updating = False
        self.details_requested_at = {}
        root.title("DNF 助手 · 多账户任务")
        root.geometry("1480x900")
        root.minsize(1240, 800)
        root.protocol("WM_DELETE_WINDOW", self.close)
        apply_theme(root)
        frame = ttk.Frame(root, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=4, minsize=360)
        frame.rowconfigure(3, weight=1, minsize=140)
        header = ttk.Frame(frame)
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 14))
        ttk.Label(header, text="DNF 助手", style="Title.TLabel").pack(side="left")
        self.overview = tk.StringVar()
        ttk.Label(header, textvariable=self.overview, style="Muted.TLabel").pack(side="left", padx=20, pady=(7, 0))
        ttk.Button(header, text="＋ 扫码添加", command=self.add_account).pack(side="right")
        workspace = ttk.Frame(frame)
        workspace.grid(row=2, column=0, sticky="nsew")
        workspace.columnconfigure(0, weight=1)
        workspace.columnconfigure(1, minsize=510)
        workspace.rowconfigure(0, weight=1)
        account_panel = ttk.Frame(workspace, style="Panel.TFrame", padding=8)
        account_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.details = AccountDetails(workspace)
        self.details.frame.grid(row=0, column=1, sticky="nsew")
        account_heading = ttk.Frame(account_panel, style="Surface.TFrame")
        account_heading.pack(fill="x", pady=(0, 4))
        ttk.Label(account_heading, text="账户任务总览", style="Section.TLabel").pack(side="left")
        self.checked_summary = tk.StringVar(value="")
        self.checked_summary_label = ttk.Label(account_heading, textvariable=self.checked_summary, style="Hint.TLabel")
        self.run_button = ttk.Button(account_heading, text="执行", style="Primary.TButton",
                                     command=lambda: self.enqueue_selected("run"))
        self.run_button.pack(side="right")
        self.select_all_button = ttk.Button(account_heading, text="全选", command=self.toggle_all_checked)
        self.select_all_button.pack(side="right", padx=6)
        columns = ("name", "qq", "role", "level", "experience", "completion", "schedule", "status")
        table = ttk.Frame(account_panel, style="Surface.TFrame")
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, columns=columns, show="tree headings", selectmode="browse", height=4)
        self.tree.column("#0", width=48, minwidth=48, stretch=False, anchor="center")
        self.tree.heading("#0", text="勾选", command=self.toggle_all_checked)
        self.checkbox_images = self.create_checkbox_images()
        for column, title, width in zip(columns, ("备注", "QQ", "角色", "编年", "经验", "任务", "定时", "状态"),
                                        (95, 100, 105, 55, 60, 65, 65, 155)):
            self.tree.heading(column, text=title, anchor="w")
            self.tree.column(column, width=width, minwidth=36, anchor="w")
        fit_table_columns(self.tree)
        self.tree.pack(fill="both", expand=True)
        self.empty_label = ttk.Label(table, text="还没有账户\n点击顶部“添加账户（扫码）”开始。",
                                     style="Hint.TLabel", justify="center")
        self.notice = tk.StringVar(value="就绪")
        log_panel = ttk.Frame(frame, style="Panel.TFrame", padding=(10, 8))
        log_panel.grid(row=3, column=0, sticky="nsew", pady=(8, 0))
        log_heading = ttk.Frame(log_panel, style="Surface.TFrame")
        log_heading.pack(fill="x", pady=(0, 8))
        ttk.Label(log_heading, text="执行日志", style="Section.TLabel").pack(side="left")
        ttk.Button(log_heading, text="清空显示", command=self.clear_log_display).pack(side="right")
        self.logs = ScrolledText(log_panel, height=6, state="disabled", wrap="word")
        style_log(self.logs)
        self.logs.pack(fill="both", expand=True)
        ttk.Label(frame, textvariable=self.notice, style="Muted.TLabel").grid(row=4, column=0, sticky="w", pady=(6, 4))
        footer = ttk.Frame(frame)
        footer.grid(row=5, column=0, sticky="ew")
        ttk.Label(footer, text="定时按电脑时间执行，需保持程序运行；休眠时暂停，唤醒后补执行。",
                  style="Muted.TLabel").pack(side="left")
        ttk.Button(footer, text="最小化到后台", command=root.iconify).pack(side="right")
        from desktop_update import VERSION
        from desktop_update_dialog import show_update_dialog
        ttk.Button(footer, text="检查更新", command=lambda: show_update_dialog(self)).pack(side="right", padx=8)
        ttk.Label(footer, text=f"v{VERSION}", style="Muted.TLabel").pack(side="right", padx=4)
        community = ttk.Frame(frame)
        community.grid(row=6, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(community, text="交流与反馈", style="Muted.TLabel").pack(side="left", padx=(0, 8))
        for title, url in (("QQ 交流群", "https://qm.qq.com/q/5yQlfQPCX"),
                           ("TG 交流群", "https://t.me/+KcwbvZdqOqU5YmZl")):
            ttk.Button(community, text=title, command=lambda url=url: webbrowser.open(url)).pack(side="left", padx=(0, 8))
        self.tree.bind("<<TreeviewSelect>>", self.update_selection)
        self.tree.bind("<Button-1>", self.toggle_checked_click)
        self.tree.bind("<space>", self.toggle_checked_keyboard)
        self.tree.bind("<Button-3>", self.show_account_menu)
        if root.tk.call("tk", "windowingsystem") == "aqua":
            self.tree.bind("<Button-2>", self.show_account_menu)
            self.tree.bind("<Control-Button-1>", self.show_account_menu)
        self.tree.bind("<Shift-F10>", self.show_account_menu_keyboard)
        self.refresh()
        self.log(f"数据目录：{directory}")
        root.after(500, self.tick)

    def account_path(self, account):
        return self.directory / "accounts" / account["id"]

    def persist(self):
        write_json(self.directory / "accounts.json", self.accounts)

    def refresh(self):
        selected = self.tree.selection()
        self.checked_accounts.intersection_update(account["id"] for account in self.accounts)
        self.tree.delete(*self.tree.get_children())
        for index, account in enumerate(self.accounts):
            session, result = read_account_snapshot(self.account_path(account))
            tasks = result.get("tasks", [])
            completion = f"{sum(task.get('my_status') == '已领取' for task in tasks)}/{len(tasks)}" if "tasks" in result else "待查询"
            self.tree.insert("", "end", iid=account["id"], image=self.checkbox_images[account["id"] in self.checked_accounts],
                             tags=("even" if index % 2 == 0 else "odd",), values=(
                account["name"], session.get("uin") or "未登录", session.get("roleName") or "待同步",
                result.get("level") or "—", result.get("exp_total") if result.get("exp_total") is not None else "—",
                completion, account["time"] if account["enabled"] else "未启用",
                self.statuses.get(account["id"], "登录已过期" if result.get("auth_expired") else "待执行" if session else "请扫码登录")))
        self.tree.selection_set([identifier for identifier in selected if self.tree.exists(identifier)])
        self.tree.tag_configure("even", background=COLORS["surface"])
        self.tree.tag_configure("odd", background="#F7F7F9")
        self.overview.set(f"{len(self.accounts)} 个账户，{sum(account['enabled'] for account in self.accounts)} 个已开启每日定时")
        if self.accounts:
            self.empty_label.place_forget()
        else:
            self.empty_label.place(relx=0.5, rely=0.6, anchor="center")
        self.update_selection()

    def update_checked_controls(self):
        count = len(self.checked_accounts)
        self.select_all_button.configure(text="取消全选" if self.accounts and count == len(self.accounts) else "全选")
        self.checked_summary.set(f"已勾选 {count} 个" if count else "")
        if count:
            if not self.checked_summary_label.winfo_manager():
                self.checked_summary_label.pack(side="left", padx=12)
        else:
            self.checked_summary_label.pack_forget()
        self.run_button.configure(state="normal" if count else "disabled")

    def update_selection(self, event=None):
        self.update_checked_controls()
        selected = self.selected_accounts()
        account = selected[0] if len(selected) == 1 else None
        self.details.show(account, self.account_path(account) if account else None)
        if event is not None and account and not self.updating and not self.is_busy(account):
            identifier = account["id"]
            if ((self.account_path(account) / "session.json").exists()
                    and time.monotonic() - self.details_requested_at.get(identifier, float("-inf")) >= 60):
                self.details_requested_at[identifier] = time.monotonic()
                self.enqueue(account, "details")

    def create_checkbox_images(self):
        images = []
        for checked in (False, True):
            image = tk.PhotoImage(master=self.root, width=24, height=24)
            border = COLORS["accent"] if checked else "#8B919A"
            image.put(border, to=(2, 2, 22, 22))
            image.put(COLORS["accent"] if checked else COLORS["surface"], to=(4, 4, 20, 20))
            if checked:
                for x, y in ((6, 11), (7, 12), (8, 13), (9, 14), (10, 13), (11, 12),
                             (12, 11), (13, 10), (14, 9), (15, 8), (16, 7)):
                    image.put("#FFFFFF", to=(x, y, x + 2, y + 3))
            images.append(image)
        return images

    def set_all_checked(self, checked):
        identifiers = {account["id"] for account in self.accounts} if checked else set()
        for identifier in self.checked_accounts.symmetric_difference(identifiers):
            if self.tree.exists(identifier):
                self.tree.item(identifier, image=self.checkbox_images[identifier in identifiers])
        self.checked_accounts = identifiers
        self.update_checked_controls()

    def toggle_all_checked(self):
        self.set_all_checked(len(self.checked_accounts) != len(self.accounts))

    def toggle_checked(self, identifier):
        if not identifier or not self.tree.exists(identifier):
            return
        if identifier in self.checked_accounts:
            self.checked_accounts.remove(identifier)
        else:
            self.checked_accounts.add(identifier)
        self.tree.item(identifier, image=self.checkbox_images[identifier in self.checked_accounts])
        self.update_checked_controls()

    def toggle_checked_click(self, event):
        if self.tree.identify_region(event.x, event.y) == "tree" and self.tree.identify_column(event.x) == "#0":
            identifier = self.tree.identify_row(event.y)
            self.tree.selection_set(identifier)
            self.tree.focus(identifier)
            self.tree.focus_set()
            self.toggle_checked(identifier)
            return "break"

    def toggle_checked_keyboard(self, event):
        self.toggle_checked(self.tree.focus())
        return "break"

    def show_account_menu(self, event):
        identifier = self.tree.identify_row(event.y)
        if identifier and self.tree.identify_region(event.x, event.y) in ("cell", "tree"):
            self.open_account_menu(identifier, event.x_root, event.y_root)
        return "break"

    def show_account_menu_keyboard(self, event):
        identifier = self.tree.focus()
        if identifier:
            bounds = self.tree.bbox(identifier)
            if bounds:
                self.open_account_menu(identifier, self.tree.winfo_rootx() + bounds[0] + 30,
                                       self.tree.winfo_rooty() + bounds[1] + bounds[3])
        return "break"

    def open_account_menu(self, identifier, x, y):
        if not self.tree.exists(identifier):
            return
        self.tree.selection_set(identifier)
        self.tree.focus(identifier)
        self.tree.focus_set()
        self.update_selection()
        menu = tk.Menu(self.tree, tearoff=False)
        for label, action in (("执行此账户", "run"), ("检查此账户任务", "check")):
            menu.add_command(label=label, command=lambda action=action: self.run_account_menu_action(identifier, action))
        menu.add_separator()
        for label, action in (("活动配置", "activities"), ("备注与定时", "edit"),
                              ("扫码更新登录", "login")):
            menu.add_command(label=label, command=lambda action=action: self.run_account_menu_action(identifier, action))
        menu.add_separator()
        menu.add_command(label="取消勾选" if identifier in self.checked_accounts else "勾选此账户",
                         command=lambda: self.toggle_checked(identifier))
        menu.add_command(label="删除此账户…", command=lambda: self.run_account_menu_action(identifier, "delete"))
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def run_account_menu_action(self, identifier, action):
        # 右键执行锁定该行，不能借用批量勾选列表。
        account = next((account for account in self.accounts if account["id"] == identifier), None)
        if account is None:
            return
        self.tree.selection_set(identifier)
        if action in ("run", "check", "login"):
            self.enqueue(account, action)
            return
        commands = {"activities": self.configure_activities, "edit": self.edit_account,
                    "delete": self.delete_account}
        commands[action]()

    def log(self, message):
        self.logs.configure(state="normal")
        self.logs.insert("end", f"{datetime.now():%H:%M:%S}  {message.rstrip()}\n")
        if int(self.logs.index("end-1c").split(".")[0]) > 2500:
            self.logs.delete("1.0", "500.0")
        self.logs.see("end")
        self.logs.configure(state="disabled")

    def clear_log_display(self):
        self.logs.configure(state="normal")
        self.logs.delete("1.0", "end")
        self.logs.configure(state="disabled")

    def selected_accounts(self):
        identifiers = self.tree.selection()
        return [account for account in self.accounts if account["id"] in identifiers]

    def one_account(self):
        selected = self.selected_accounts()
        if len(selected) != 1:
            messagebox.showinfo("选择账户", "请先选中一个账户", parent=self.root)
            return None
        return selected[0]

    def is_busy(self, account):
        return ((self.current and self.current[0]["id"] == account["id"])
                or any(queued[0]["id"] == account["id"] for queued in self.queue))

    def account_dialog(self, account):
        if self.is_busy(account):
            messagebox.showinfo("账户忙碌", "请等待该账户操作结束后再编辑", parent=self.root)
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("编辑账户")
        dialog.configure(background=COLORS["background"])
        dialog.resizable(False, False)
        dialog.transient(self.root)
        panel = ttk.Frame(dialog, padding=20)
        panel.pack()
        ttk.Label(panel, text="安排每日任务", style="Title.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        name = tk.StringVar(value=account["name"])
        schedule = tk.StringVar(value=account["time"])
        enabled = tk.BooleanVar(value=account["enabled"])
        ttk.Label(panel, text="账户备注").grid(row=1, column=0, sticky="w", pady=8)
        entry = ttk.Entry(panel, textvariable=name, width=30)
        entry.grid(row=1, column=1, padx=10)
        ttk.Label(panel, text="每日时间 HH:MM").grid(row=2, column=0, sticky="w", pady=8)
        ttk.Entry(panel, textvariable=schedule, width=30).grid(row=2, column=1, padx=10)
        ttk.Checkbutton(panel, text="启用每日定时（电脑本地时间）", variable=enabled).grid(row=3, columnspan=2, pady=10)

        def save():
            try:
                title = name.get().strip()
                if not title or len(title) > 40:
                    raise ValueError("账户备注需为 1～40 个字符")
                clock = validate_time(schedule.get().strip())
                updated = dict(account)
                updated.update(name=title, time=clock, enabled=enabled.get())
                accounts = [updated if existing is account else existing for existing in self.accounts]
                write_json(self.directory / "accounts.json", accounts)
                self.accounts = accounts
                self.refresh()
                self.tree.selection_set(updated["id"])
                dialog.destroy()
            except (ValueError, OSError) as error:
                messagebox.showerror("无法保存", str(error), parent=dialog)

        ttk.Button(panel, text="保存账户", style="Primary.TButton", command=save).grid(row=4, columnspan=2, pady=8)
        dialog.bind("<Escape>", lambda event: dialog.destroy())
        dialog.grab_set()
        entry.focus_set()

    def add_account(self):
        if self.updating:
            return
        if self.process or self.queue:
            messagebox.showinfo("任务进行中", "请等待当前任务结束，再扫码添加账户。", parent=self.root)
            return
        self.adding_account = {"id": uuid.uuid4().hex, "name": "新账户", "enabled": False, "time": "09:00"}
        self.enqueue(self.adding_account, "login")
        self.start_next()

    def finish_account_addition(self, account, success):
        """扫码成功才保存账户；取消或失败不留下空账户。"""
        if self.adding_account is not account:
            return
        path = self.account_path(account)
        try:
            if success:
                session = read_json(path / "session.json")
                if any(not session.get(key) for key in ("uin", "userId", "token")):
                    raise ValueError("登录态不完整")
                for existing in self.accounts:
                    existing_path = self.account_path(existing) / "session.json"
                    try:
                        saved = read_json(existing_path)
                    except (OSError, ValueError):
                        continue
                    if str(saved.get("uin")) == str(session["uin"]):
                        write_json(existing_path, session, secret=True)
                        self.statuses[existing["id"]] = "登录已更新，正在检查任务"
                        self.refresh()
                        self.tree.selection_set(existing["id"])
                        self.log(f"已更新账户「{existing['name']}」的登录，保留原有备注、定时和活动配置。")
                        return existing
                account["name"] = str(session.get("nickname") or f"QQ {session['uin']}")[:40]
                updated = [*self.accounts, account]
                write_json(self.directory / "accounts.json", updated)
                self.accounts = updated
                self.refresh()
                self.tree.selection_set(account["id"])
                self.log(f"已添加账户：{account['name']}，可在“编辑定时”中修改备注和执行时间。")
                return account
        except (OSError, ValueError, TypeError) as error:
            self.log(f"账户添加未完成（{type(error).__name__}），请重新扫码。")
        finally:
            if account not in self.accounts:
                try:
                    shutil.rmtree(path, ignore_errors=False)
                except FileNotFoundError:
                    pass
                except OSError:
                    self.log("临时登录文件清理失败，请检查本机文件权限。")
                self.statuses.pop(account["id"], None)
            self.adding_account = None

    def edit_account(self):
        account = self.one_account()
        if account:
            self.account_dialog(account)

    def configure_activities(self):
        account = self.one_account()
        if not account:
            return
        if self.is_busy(account):
            messagebox.showinfo("账户忙碌", "请等待任务结束或停止后再修改活动", parent=self.root)
            return
        from activity_dialog import show_activity_dialog
        show_activity_dialog(self.root, self.account_path(account), account["name"])

    def delete_account(self):
        account = self.one_account()
        if not account:
            return
        if self.is_busy(account):
            messagebox.showinfo("账户忙碌", "请先停止该账户的操作", parent=self.root)
            return
        if not messagebox.askyesno("删除账户", f"删除「{account['name']}」及本机凭证和日志？此操作无法撤销。", parent=self.root):
            return
        try:
            remaining = [existing for existing in self.accounts if existing is not account]
            write_json(self.directory / "accounts.json", remaining)
            self.accounts = remaining
            path = self.account_path(account)
            if path.exists():
                shutil.rmtree(path)
            self.refresh()
        except OSError as error:
            self.refresh()
            messagebox.showerror("删除未完全成功", str(error), parent=self.root)

    def enqueue_selected(self, action):
        accounts = (self.selected_accounts() if action == "login" else
                    [account for account in self.accounts if account["id"] in self.checked_accounts])
        if not accounts:
            messagebox.showinfo("选择账户", "请先勾选要执行或检查的账户。", parent=self.root)
        for account in accounts:
            self.enqueue(account, action)

    def enqueue_all(self):
        for account in self.accounts:
            self.enqueue(account, "run")

    def enqueue(self, account, action):
        if self.updating:
            self.log("正在更新，暂不启动任务。")
            return
        if self.is_busy(account):
            if action != "details":
                self.log(f"{account['name']}：已运行或排队，跳过重复点击")
            return
        if action != "login" and not (self.account_path(account) / "session.json").exists():
            self.statuses[account["id"]] = "请先扫码登录"
            self.refresh()
            return
        self.queue.append((account, action))
        if action != "details":
            self.statuses[account["id"]] = "排队中"
        self.refresh()

    def start_next(self):
        if self.process or not self.queue:
            return
        account, action = self.queue.popleft()
        path = self.account_path(account)
        try:
            path.mkdir(parents=True, exist_ok=True)
            atomic_write(path / "current.log", b"")
            (path / "qr_login.png").unlink(missing_ok=True)
            if action == "run" and is_due(account, datetime.now()):
                account["last_scheduled"] = datetime.now().date().isoformat()
                self.persist()
            arguments = [sys.executable]
            if not getattr(sys, "frozen", False):
                arguments.append(str(Path(__file__).with_name("desktop.py")))
            arguments += ["--worker", str(path), action]
            options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
            self.process = subprocess.Popen(arguments, stdin=subprocess.DEVNULL,
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **options)
            self.current = (account, action)
            self.started = time.monotonic()
            self.offset = 0
            self.cancelled = False
            if action != "details":
                self.statuses[account["id"]] = {"login": "等待扫码", "run": "执行中", "check": "检查中"}[action]
                self.log(f"{account['name']}：{self.statuses[account['id']]}")
        except OSError as error:
            self.statuses[account["id"]] = "启动失败"
            self.log(f"启动失败：{error}")
            self.finish_account_addition(account, False)
        self.refresh()

    def read_output(self):
        path = self.account_path(self.current[0]) / "current.log"
        try:
            with path.open("rb") as stream:
                stream.seek(self.offset)
                content = stream.read()
            # 只消费完整行，防止拆开 UTF-8 汉字。
            end = content.rfind(b"\n") + 1
            if end:
                self.offset += end
                self.log(content[:end].decode("utf-8", errors="replace"))
        except OSError:
            pass

    def show_qr(self):
        if self.current[1] != "login" or self.qr_window:
            return
        path = self.account_path(self.current[0]) / "qr_login.png"
        if not path.exists():
            return
        try:
            self.qr_image = tk.PhotoImage(file=str(path))
        except tk.TclError:
            return
        window = tk.Toplevel(self.root)
        self.qr_window = window
        window.title(f"QQ 扫码登录 · {self.current[0]['name']}")
        window.transient(self.root)
        ttk.Label(window, text="请使用手机 QQ 扫码并确认登录", padding=16).pack()
        ttk.Label(window, image=self.qr_image, padding=16).pack()
        ttk.Button(window, text="取消登录", command=self.stop).pack(pady=16)
        window.protocol("WM_DELETE_WINDOW", self.stop)

    def tick(self):
        try:
            if self.process:
                self.read_output()
                self.show_qr()
                code = self.process.poll()
                limit = 300 if self.current[1] == "login" else 7200
                if code is None and time.monotonic() - self.started > limit:
                    self.log("执行超时，正在停止；可检查网络后重新执行")
                    self.stop()
                if code is not None:
                    self.read_output()
                    account, action = self.current
                    status = ("已停止，部分任务可能已完成" if self.cancelled else
                              "登录成功" if action == "login" and code == 0 else
                              "任务详情已刷新（未执行任务）" if action == "details" and code == 0 else
                              "完成" if code == 0 else
                              "有待处理项目，请查看日志" if code == 1 and action != "login" else
                              "失败，请查看日志或重新登录")
                    if action != "login" and code == 1 and not self.cancelled:
                        try:
                            result = read_json(self.account_path(account) / "result.json")
                            if result.get("auth_expired"):
                                status = "登录已过期，请扫码更新"
                        except (OSError, ValueError):
                            pass
                    if action != "details" or code != 0:
                        self.statuses[account["id"]] = f"{datetime.now():%H:%M} {status}"
                    elif any(word in self.statuses.get(account["id"], "") for word in ("登录已过期", "扫码更新", "刷新任务", "任务详情已刷新")):
                        self.statuses.pop(account["id"], None)
                    if action != "details" or code != 0 or self.cancelled:
                        self.log(f"{account['name']}：{status}")
                    login_account = self.finish_account_addition(account, action == "login" and code == 0 and not self.cancelled)
                    for filename in ("qq_oauth.json", "qr_state.json", "qr_login.png"):
                        (self.account_path(account) / filename).unlink(missing_ok=True)
                    if self.qr_window:
                        self.qr_window.destroy()
                        self.qr_window = None
                        self.qr_image = None
                    self.process = self.current = None
                    self.refresh()
                    if action == "login" and code == 0 and not self.cancelled:
                        target = login_account or (account if account in self.accounts else None)
                        if target:
                            self.enqueue(target, "check")
            now = datetime.now()
            for account in self.accounts:
                if is_due(account, now) and not self.is_busy(account):
                    if (self.account_path(account) / "session.json").exists():
                        self.enqueue(account, "run")
            self.start_next()
            running = self.current[0]['name'] if self.current and self.current[1] != "details" else '无'
            waiting = sum(action != "details" for _, action in self.queue)
            self.notice.set(f"运行中：{running}    排队：{waiting}    当前电脑时间：{now:%Y-%m-%d %H:%M:%S}")
        except (OSError, ValueError, tk.TclError) as error:
            self.log(f"操作异常：{type(error).__name__}，请检查本机文件权限")
        finally:
            self.root.after(500, self.tick)

    def stop(self):
        for account, _ in self.queue:
            self.statuses[account["id"]] = "已取消排队"
            # 停止后当天不再自动入队，次日照常执行。
            if account["enabled"]:
                account["last_scheduled"] = datetime.now().date().isoformat()
        self.queue.clear()
        if self.process and self.process.poll() is None:
            self.cancelled = True
            self.process.terminate()
        try:
            self.persist()
        except OSError:
            self.log("停止状态保存失败，请检查本机文件权限")
        self.refresh()

    def close(self):
        if self.updating:
            messagebox.showinfo("正在更新", "请等待下载和校验完成。", parent=self.root)
            return
        if self.process or self.queue or any(account["enabled"] for account in self.accounts):
            if not messagebox.askyesno("退出程序", "退出会停止当前任务与后续定时。需要后台运行时请选择最小化。确定退出？", parent=self.root):
                return
        self.stop()
        if self.process:
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            for filename in ("qq_oauth.json", "qr_state.json", "qr_login.png"):
                (self.account_path(self.current[0]) / filename).unlink(missing_ok=True)
            self.finish_account_addition(self.current[0], False)
        self.root.destroy()


def launch():
    root = tk.Tk()
    root.withdraw()
    directory = data_directory()
    lock = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        lock = open(directory / "desktop.lock", "a+b")
        lock.seek(0)
        if os.name == "nt":
            import msvcrt
            if not lock.read(1):
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        accounts = load_accounts(directory / "accounts.json")
        DesktopApp(root, directory, accounts)
        root.deiconify()
        root.mainloop()
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        messagebox.showerror("无法启动", f"程序可能已运行，或本机配置无法读取。\n"
                             f"请检查：{directory}\n错误类型：{type(error).__name__}\n"
                             "配置文件会保留，不会自动覆盖。", parent=root)
        root.destroy()
        return 2
    finally:
        if lock:
            lock.close()
