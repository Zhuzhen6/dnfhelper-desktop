"""账户管理、任务队列与桌面界面。"""
import os
import re
import shutil
import subprocess
import sys
import time
import tkinter as tk
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from desktop_schedule import is_due, validate_time
from desktop_storage import atomic_write, data_directory, read_json, write_json


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
        self.statuses = {}
        root.title("DNF 助手 · 多账户任务")
        root.geometry("1040x720")
        root.minsize(900, 600)
        root.protocol("WM_DELETE_WINDOW", self.close)
        style = ttk.Style(root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Treeview", rowheight=32)
        style.configure("TButton", padding=(10, 6))
        frame = ttk.Frame(root, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="DNF 助手", font=("Microsoft YaHei UI", 22, "bold")).pack(anchor="w")
        ttk.Label(frame, text="多账户独立登录 · 每日自动任务 · 随时点击执行").pack(anchor="w", pady=(4, 14))
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill="x", pady=(0, 10))
        for label, command in (("添加账户", self.add_account), ("编辑", self.edit_account),
                               ("扫码登录", lambda: self.enqueue_selected("login")),
                               ("导入登录态", self.import_session),
                               ("删除", self.delete_account)):
            ttk.Button(toolbar, text=label, command=command).pack(side="left", padx=(0, 6))
        columns = ("name", "login", "schedule", "status")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="extended", height=7)
        for column, title, width in zip(columns, ("账户", "本地凭证", "每日定时（电脑时间）", "状态"),
                                        (180, 190, 180, 340)):
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, minwidth=100)
        self.tree.pack(fill="both", expand=True)
        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=12)
        for label, command in (("执行选中账户", lambda: self.enqueue_selected("run")),
                               ("执行全部账户", self.enqueue_all),
                               ("检查登录 / 任务", lambda: self.enqueue_selected("check")),
                               ("停止并清空队列", self.stop),
                               ("最小化", root.iconify)):
            ttk.Button(actions, text=label, command=command).pack(side="left", padx=(0, 6))
        self.notice = tk.StringVar(value="就绪")
        ttk.Label(frame, textvariable=self.notice).pack(anchor="w", pady=(0, 6))
        self.logs = ScrolledText(frame, height=13, state="disabled", font=("Consolas", 10))
        self.logs.pack(fill="both", expand=True)
        ttk.Label(frame, text="定时需程序保持运行；最小化可继续。到点后按账户依次执行，休眠期间无法运行。"
                  "\n启动或唤醒后补执行当天已到点任务；失败不自动重试，可手动执行。游戏内任务需实际完成。",
                  wraplength=970).pack(anchor="w", pady=(10, 0))
        self.refresh()
        self.log(f"数据目录：{directory}")
        root.after(500, self.tick)

    def account_path(self, account):
        return self.directory / "accounts" / account["id"]

    def persist(self):
        write_json(self.directory / "accounts.json", self.accounts)

    def refresh(self):
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for account in self.accounts:
            session_path = self.account_path(account) / "session.json"
            login = "未登录"
            if session_path.exists():
                try:
                    session = read_json(session_path)
                    login = session.get("nickname") or "已保存（可点击检查）"
                except (OSError, ValueError):
                    login = "凭证无法读取，请重新登录"
            self.tree.insert("", "end", iid=account["id"], values=(
                account["name"], login, account["time"] if account["enabled"] else "未启用",
                self.statuses.get(account["id"], "待执行")))
        self.tree.selection_set([identifier for identifier in selected if self.tree.exists(identifier)])

    def log(self, message):
        self.logs.configure(state="normal")
        self.logs.insert("end", f"{datetime.now():%H:%M:%S}  {message.rstrip()}\n")
        if int(self.logs.index("end-1c").split(".")[0]) > 2500:
            self.logs.delete("1.0", "500.0")
        self.logs.see("end")
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

    def account_dialog(self, account=None):
        if account and self.is_busy(account):
            messagebox.showinfo("账户忙碌", "请等待该账户操作结束后再编辑", parent=self.root)
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("编辑账户" if account else "添加账户")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        panel = ttk.Frame(dialog, padding=20)
        panel.pack()
        name = tk.StringVar(value=account["name"] if account else "")
        schedule = tk.StringVar(value=account["time"] if account else "09:00")
        enabled = tk.BooleanVar(value=account["enabled"] if account else False)
        ttk.Label(panel, text="账户备注").grid(row=0, column=0, sticky="w", pady=8)
        entry = ttk.Entry(panel, textvariable=name, width=30)
        entry.grid(row=0, column=1, padx=10)
        ttk.Label(panel, text="每日时间 HH:MM").grid(row=1, column=0, sticky="w", pady=8)
        ttk.Entry(panel, textvariable=schedule, width=30).grid(row=1, column=1, padx=10)
        ttk.Checkbutton(panel, text="启用每日定时（电脑本地时间）", variable=enabled).grid(row=2, columnspan=2, pady=10)

        def save():
            try:
                title = name.get().strip()
                if not title or len(title) > 40:
                    raise ValueError("账户备注需为 1～40 个字符")
                clock = validate_time(schedule.get().strip())
                updated = dict(account) if account else {"id": uuid.uuid4().hex}
                updated.update(name=title, time=clock, enabled=enabled.get())
                accounts = [updated if existing is account else existing for existing in self.accounts]
                if account is None:
                    accounts.append(updated)
                write_json(self.directory / "accounts.json", accounts)
                self.accounts = accounts
                self.refresh()
                self.tree.selection_set(updated["id"])
                dialog.destroy()
            except (ValueError, OSError) as error:
                messagebox.showerror("无法保存", str(error), parent=dialog)

        ttk.Button(panel, text="保存", command=save).grid(row=3, columnspan=2, pady=8)
        dialog.grab_set()
        entry.focus_set()

    def add_account(self):
        self.account_dialog()

    def edit_account(self):
        account = self.one_account()
        if account:
            self.account_dialog(account)

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

    def import_session(self):
        account = self.one_account()
        if not account or self.is_busy(account):
            return
        filename = filedialog.askopenfilename(title="选择已有 session.json", filetypes=[("JSON 登录态", "*.json")])
        if not filename:
            return
        try:
            session = read_json(filename)
            if not isinstance(session, dict) or any(not session.get(key) for key in ("userId", "uin", "token")):
                raise ValueError("登录态必须包含 userId、uin、token")
            write_json(self.account_path(account) / "session.json", session, secret=True)
            self.statuses[account["id"]] = "已导入，建议检查登录"
            self.refresh()
        except (OSError, ValueError) as error:
            messagebox.showerror("导入失败", str(error), parent=self.root)

    def enqueue_selected(self, action):
        accounts = self.selected_accounts()
        if not accounts:
            messagebox.showinfo("选择账户", "请先选中账户，可按 Ctrl 多选", parent=self.root)
        for account in accounts:
            self.enqueue(account, action)

    def enqueue_all(self):
        for account in self.accounts:
            self.enqueue(account, "run")

    def enqueue(self, account, action):
        if self.is_busy(account):
            self.log(f"{account['name']}：已运行或排队，跳过重复点击")
            return
        if action != "login" and not (self.account_path(account) / "session.json").exists():
            self.statuses[account["id"]] = "请先扫码登录或导入登录态"
            self.refresh()
            return
        self.queue.append((account, action))
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
            self.statuses[account["id"]] = {"login": "等待扫码", "run": "执行中", "check": "检查中"}[action]
            self.log(f"{account['name']}：{self.statuses[account['id']]}")
        except OSError as error:
            self.statuses[account["id"]] = "启动失败"
            self.log(f"启动失败：{error}")
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
                limit = 300 if self.current[1] == "login" else 1200
                if code is None and time.monotonic() - self.started > limit:
                    self.log("执行超时，正在停止；可检查网络后重新执行")
                    self.stop()
                if code is not None:
                    self.read_output()
                    account, action = self.current
                    status = ("已停止，部分任务可能已完成" if self.cancelled else
                              "登录成功" if action == "login" and code == 0 else
                              "完成" if code == 0 else
                              "有待处理项目，请查看日志" if code == 1 and action != "login" else
                              "失败，请查看日志或重新登录")
                    self.statuses[account["id"]] = f"{datetime.now():%H:%M} {status}"
                    self.log(f"{account['name']}：{status}")
                    for filename in ("qq_oauth.json", "qr_state.json", "qr_login.png"):
                        (self.account_path(account) / filename).unlink(missing_ok=True)
                    if self.qr_window:
                        self.qr_window.destroy()
                        self.qr_window = None
                        self.qr_image = None
                    self.process = self.current = None
                    self.refresh()
            now = datetime.now()
            for account in self.accounts:
                if is_due(account, now) and not self.is_busy(account):
                    if (self.account_path(account) / "session.json").exists():
                        self.enqueue(account, "run")
            self.start_next()
            self.notice.set(f"运行中：{self.current[0]['name'] if self.current else '无'}"
                            f"    排队：{len(self.queue)}    当前电脑时间：{now:%Y-%m-%d %H:%M:%S}")
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
