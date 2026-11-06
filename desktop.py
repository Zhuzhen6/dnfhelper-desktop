"""DNF 助手桌面入口。Created by 朱圳。"""
import sys


def main():
    if len(sys.argv) == 5 and sys.argv[1] == "--apply-update":
        from desktop_update_install import apply_update
        return apply_update(sys.argv[2], sys.argv[3], sys.argv[4])
    # 在导入 GUI 前进入工作进程，兼容 PyInstaller 无控制台打包。
    if len(sys.argv) == 4 and sys.argv[1] == "--worker":
        from desktop_worker import run_worker
        return run_worker(sys.argv[2], sys.argv[3])
    from desktop_app import launch
    return launch()


if __name__ == "__main__":
    raise SystemExit(main())
