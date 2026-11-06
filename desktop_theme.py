"""桌面界面的颜色、字体与控件样式。Created by 朱圳。"""
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk


COLORS = {
    "background": "#F5F5F7",
    "surface": "#FFFFFF",
    "ink": "#1D1D1F",
    "muted": "#68686D",
    "border": "#E5E5EA",
    "accent": "#0066CC",
    "accent_hover": "#0055B3",
    "selection": "#DCEBFA",
    "danger": "#B4232D",
}


def rounded_image(root, color, radius=8, outline=None):
    """用 Tk 自带图像绘制九宫格背景，无需额外图像依赖。"""
    size = 32
    image = tk.PhotoImage(master=root, width=size, height=size)
    for y in range(size):
        distance = max(radius - y - 0.5, y - (size - radius) + 0.5, 0)
        inset = max(0, round(radius - (radius * radius - distance * distance) ** 0.5))
        image.put(outline or color, to=(inset, y, size - inset, y + 1))
        if outline and 2 <= y < size - 2:
            inner_distance = max(radius - y - 0.5, y - (size - radius) + 0.5, 0)
            inner_inset = max(2, round(radius - ((radius - 2) ** 2 - min(inner_distance, radius - 2) ** 2) ** 0.5))
            image.put(color, to=(inner_inset, y, size - inner_inset, y + 1))
    return image


def install_rounded_styles(root, style):
    """保留 ttk 的键盘和状态行为，仅替换背景外观。"""
    images = []
    for name, colors in (("Secondary", ("#EFEFF2", "#E5E5EA", "#DCDCE1", "#F3F3F5")),
                         ("Primary", (COLORS["accent"], COLORS["accent_hover"], "#004C99", "#B0C8E4"))):
        normal, hover, pressed, disabled = [rounded_image(root, color) for color in colors]
        focus = rounded_image(root, colors[0], outline="#80B5F0")
        images.extend((normal, hover, pressed, disabled, focus))
        element = f"{name}.rounded"
        style.element_create(element, "image", normal, ("disabled", disabled),
                             ("pressed", "!disabled", pressed), ("focus", focus), ("active", hover),
                             border=10, padding=0, sticky="nsew")
        layout = [(element, {"sticky": "nsew", "children": [
            ("Button.padding", {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]})]})]
        style.layout("TButton" if name == "Secondary" else "Primary.TButton", layout)
    panel = rounded_image(root, COLORS["surface"], radius=12)
    images.append(panel)
    style.element_create("Surface.rounded", "image", panel, border=14, padding=0, sticky="nsew")
    style.layout("Panel.TFrame", [("Surface.rounded", {"sticky": "nsew"})])
    # PhotoImage 需保留 Python 引用，防止窗口运行时被回收。
    root.theme_images = images


def apply_theme(root):
    """使用系统中文字体，保证 Windows 与预览环境都能正常显示。"""
    families = set(tkfont.families(root))
    candidates = ("PingFang SC", "Helvetica Neue", "Arial Unicode MS") if root.tk.call("tk", "windowingsystem") == "aqua" else ("Microsoft YaHei UI", "Segoe UI", "Arial Unicode MS")
    family = next((name for name in candidates if name in families), tkfont.nametofont("TkDefaultFont", root).cget("family"))
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        tkfont.nametofont(name, root).configure(family=family, size=11)
    root.configure(background=COLORS["background"])
    # 不设置 *Font：Tk 的全局选项会覆盖 ttk 标题和正文的字体层级。
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=COLORS["background"], foreground=COLORS["ink"], font=(family, 11))
    install_rounded_styles(root, style)
    style.configure("TFrame", background=COLORS["background"])
    style.configure("Surface.TFrame", background=COLORS["surface"])
    style.configure("Panel.TFrame", background=COLORS["background"], borderwidth=0, relief="flat")
    style.configure("TLabel", background=COLORS["background"])
    style.configure("Title.TLabel", font=(family, 23, "bold"))
    style.configure("Muted.TLabel", foreground=COLORS["muted"])
    style.configure("Surface.TLabel", background=COLORS["surface"])
    style.configure("Section.TLabel", background=COLORS["surface"], font=(family, 12, "bold"))
    style.configure("Hint.TLabel", background=COLORS["surface"], foreground=COLORS["muted"])
    style.configure("Badge.TLabel", background=COLORS["surface"], foreground=COLORS["muted"], padding=(8, 4))
    style.configure("TButton", padding=(12, 5), background=COLORS["surface"], relief="flat", font=(family, 10))
    style.map("TButton", foreground=[("disabled", "#88888D")])
    style.configure("Primary.TButton", foreground="#FFFFFF", font=(family, 11, "bold"))
    style.map("Primary.TButton", foreground=[("disabled", "#FFFFFF"), ("!disabled", "#FFFFFF")])
    style.configure("Danger.TButton", foreground=COLORS["danger"])
    style.configure("TMenubutton", padding=(12, 8), background=COLORS["surface"], relief="flat", arrowsize=9)
    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nsew"})])
    style.configure("Treeview", background=COLORS["surface"], fieldbackground=COLORS["surface"],
                    rowheight=31, borderwidth=0, relief="flat", font=(family, 10))
    style.configure("Treeview.Heading", background=COLORS["surface"], foreground=COLORS["muted"],
                    padding=(12, 10), font=(family, 10), relief="flat", borderwidth=0)
    style.layout("Treeview.Heading", [("Treeheading.padding", {"sticky": "nsew", "children": [
        ("Treeheading.text", {"sticky": "we"})]})])
    style.map("Treeview", background=[("selected", COLORS["selection"])],
              foreground=[("selected", COLORS["ink"])])
    style.map("Treeview.Heading", background=[("active", COLORS["surface"])])
    style.configure("TEntry", fieldbackground=COLORS["surface"], padding=8,
                    bordercolor=COLORS["border"], lightcolor=COLORS["border"], darkcolor=COLORS["border"])
    style.map("TEntry", bordercolor=[("focus", COLORS["accent"])])
    style.configure("TCheckbutton", background=COLORS["surface"], padding=(4, 6))
    style.map("TCheckbutton", background=[("active", "#F5F5F7")],
              indicatorbackground=[("selected", COLORS["accent"]), ("!selected", COLORS["surface"])])
    style.configure("TNotebook", background=COLORS["background"], borderwidth=0, tabmargins=(0, 0, 0, 8))
    style.configure("TNotebook.Tab", padding=(20, 10), background="#E9E9ED", borderwidth=0)
    style.map("TNotebook.Tab", background=[("selected", COLORS["surface"])],
              foreground=[("selected", COLORS["ink"])])
    style.configure("Vertical.TScrollbar", background="#C7C7CC", troughcolor=COLORS["surface"],
                    borderwidth=0, arrowsize=12)


def style_log(widget):
    """日志保持可复制、可键盘访问，采用较舒适的行距。"""
    widget.configure(background=COLORS["surface"], foreground=COLORS["ink"], borderwidth=0,
                     highlightthickness=0, padx=16, pady=12, spacing1=3, spacing3=3,
                     selectbackground=COLORS["selection"], selectforeground="#FFFFFF",
                     insertbackground=COLORS["ink"])


def fit_table_columns(tree):
    """隐藏滚动条后按比例分配宽度，保证右侧列仍在窗口内。"""
    columns = tuple(tree["columns"])
    widths = [tree.column(column, "width") for column in columns]

    def resize(event):
        tree_width = tree.column("#0", "width") if "tree" in str(tree["show"]) else 0
        available = max(1, event.width - tree_width - 2)
        total = sum(widths)
        allocated = 0
        for index, (column, width) in enumerate(zip(columns, widths)):
            target = available - allocated if index == len(columns) - 1 else int(available * width / total)
            tree.column(column, width=target, minwidth=1, stretch=False)
            allocated += target

    tree.bind("<Configure>", resize, add="+")


def create_checkbox_images(root):
    """首页和活动选择共用 24px 勾选图像。"""
    images = []
    for checked in (False, True):
        image = tk.PhotoImage(master=root, width=24, height=24)
        image.put(COLORS["accent"] if checked else "#8B919A", to=(2, 2, 22, 22))
        image.put(COLORS["accent"] if checked else COLORS["surface"], to=(4, 4, 20, 20))
        if checked:
            for x, y in ((6, 11), (7, 12), (8, 13), (9, 14), (10, 13), (11, 12),
                         (12, 11), (13, 10), (14, 9), (15, 8), (16, 7)):
                image.put("#FFFFFF", to=(x, y, x + 2, y + 3))
        images.append(image)
    return images
