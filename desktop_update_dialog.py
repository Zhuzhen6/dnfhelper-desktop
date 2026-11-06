"""更新检查在后台线程进行，窗口只在主线程刷新。Created by 朱圳。"""
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText
import webbrowser

from desktop_theme import style_log
from desktop_update import VERSION, RELEASES_URL, download_release, latest_release, version_tuple


def show_update_dialog(app):
    if getattr(app, "update_window", None) and app.update_window.winfo_exists():
        app.update_window.lift()
        return
    window = tk.Toplevel(app.root)
    app.update_window = window
    window.title("检查更新")
    window.geometry("620x490")
    window.transient(app.root)
    panel = ttk.Frame(window, padding=20)
    panel.pack(fill="both", expand=True)
    ttk.Label(panel, text="软件更新", style="Title.TLabel").pack(anchor="w")
    status = tk.StringVar(value=f"当前版本 v{VERSION}，正在检查…")
    ttk.Label(panel, textvariable=status, wraplength=560).pack(anchor="w", pady=12)
    notes = ScrolledText(panel, height=12, wrap="word", state="disabled")
    style_log(notes)
    notes.pack(fill="both", expand=True)
    events = queue.Queue()
    state = {"release": None, "busy": True}
    actions = ttk.Frame(panel)
    actions.pack(fill="x", pady=(12, 0))
    ttk.Button(actions, text="打开 Releases", command=lambda: webbrowser.open(RELEASES_URL)).pack(side="left")

    def background(callback, kind):
        try:
            events.put((kind, callback()))
        except Exception as error:
            events.put(("error", "连接或下载失败，请检查网络后重试。" if not isinstance(error, ValueError) else str(error)))

    def install():
        if state["busy"]:
            return
        if os.name != "nt" or not getattr(sys, "frozen", False):
            webbrowser.open(RELEASES_URL)
            return
        if app.current or app.process or app.queue:
            messagebox.showinfo("任务进行中", "请等待任务结束或停止任务后更新。", parent=window)
            return
        if not messagebox.askyesno("安装更新", "下载并校验后将关闭程序、替换 exe 并重新启动。账户和配置会保留。现在更新？", parent=window):
            return
        state["busy"] = True
        app.updating = True
        button.configure(state="disabled")
        status.set("正在下载并校验更新，请稍候…")
        directory = Path(tempfile.mkdtemp(prefix="dnfhelper-update-"))
        threading.Thread(target=background, args=(lambda: download_release(state["release"], directory), "download"), daemon=True).start()

    button = ttk.Button(actions, text="下载并更新", style="Primary.TButton", command=install, state="disabled")
    button.pack(side="right")

    def close():
        if state["busy"] and app.updating:
            return
        window.destroy()
    window.protocol("WM_DELETE_WINDOW", close)

    def poll():
        if not window.winfo_exists():
            return
        try:
            kind, value = events.get_nowait()
        except queue.Empty:
            window.after(150, poll)
            return
        state["busy"] = False
        if kind == "release":
            state["release"] = value
            newer = version_tuple(value["tag_name"]) > version_tuple(VERSION)
            status.set(f"当前 v{VERSION}，发现新版本 {value['tag_name']}" if newer else f"当前 v{VERSION}，已是最新版本")
            notes.configure(state="normal")
            notes.insert("1.0", str(value.get("body") or "此版本没有更新说明。")[:20000])
            notes.configure(state="disabled")
            button.configure(state="normal" if newer else "disabled")
        elif kind == "download":
            try:
                helper = value.parent / "DNFHelperUpdater.exe"
                shutil.copyfile(sys.executable, helper)
                environment = {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}
                subprocess.Popen([str(helper), "--apply-update", str(os.getpid()), sys.executable, str(value)],
                                 creationflags=subprocess.CREATE_NO_WINDOW, env=environment)
                app.root.destroy()
                return
            except OSError:
                app.updating = False
                status.set("无法启动更新程序，请从 Releases 手动下载。")
                button.configure(state="normal")
        else:
            app.updating = False
            status.set(value)
            if state["release"]:
                button.configure(state="normal")
        window.after(150, poll)

    threading.Thread(target=background, args=(latest_release, "release"), daemon=True).start()
    window.after(150, poll)
