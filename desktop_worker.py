"""每次操作独立进程，隔离上游模块的账户级全局状态。"""
import os
import re
import sys
from pathlib import Path

from desktop_storage import read_json, write_json


class SafeOutput:
    """过滤接口 URL 和凭证，日志中保留任务结果。"""
    def __init__(self, stream, directory):
        self.stream = stream
        self.directory = directory
        self.redaction_cache = {}

    def write(self, message):
        message = re.sub(r"https?://[^\s\"'<>]+", "[接口地址已隐藏]", message)
        message = re.sub(
            r"(?i)((?:access_?token|token|openid|appOpenid|pay_token|pfkey|qrsig)"
            r"[\"']?\s*[:=]\s*[\"']?)[^\s,\"'}]+", r"\1[已隐藏]", message)
        def redact(value, key=""):
            nonlocal message
            if isinstance(value, dict):
                for field, nested in value.items():
                    redact(nested, field)
            elif isinstance(value, list):
                for nested in value:
                    redact(nested, key)
            elif isinstance(value, str) and value and any(word in key.lower() for word in ("token", "cookie", "openid", "body_hex")):
                message = message.replace(value, "[已隐藏]")
        for filename in ("session.json", "activity_settings.json"):
            try:
                path = self.directory / filename
                metadata = path.stat()
                signature = (metadata.st_mtime_ns, metadata.st_ctime_ns, metadata.st_size, metadata.st_ino)
                cached = self.redaction_cache.get(filename)
                if cached is None or cached[0] != signature:
                    cached = (signature, read_json(path))
                    self.redaction_cache[filename] = cached
                redact(cached[1])
            except (OSError, ValueError):
                pass
        self.stream.write(message)
        self.stream.flush()
        return len(message)

    def flush(self):
        self.stream.flush()


def run_worker(directory, action):
    directory = Path(directory).resolve()
    os.environ["DNFHELPER_ACCOUNT_DIR"] = str(directory)
    original_stdout, original_stderr = sys.stdout, sys.stderr
    with open(directory / "current.log", "w", encoding="utf-8", buffering=1) as stream:
        sys.stdout = sys.stderr = SafeOutput(stream, directory)
        try:
            if action == "login":
                import qq_login
                import login_new_account
                # 重新授权时清除旧身份，避免上游设备参数带入旧账户。
                login_new_account.nc.S.clear()
                login_new_account.nc._AUTH.clear()
                sys.argv = ["qq_login.py", "qr"]
                code = qq_login.main()
                if code:
                    return code
                sys.argv = ["login_new_account.py"]
                return login_new_account.main()
            if action not in ("run", "check", "details"):
                raise ValueError("不支持的操作")
            from activity_runner import run_activities
            summary = run_activities(directory, check_only=action != "run", details_only=action == "details")
            if action == "details":
                try:
                    previous = read_json(directory / "result.json")
                    summary["activity_tasks"] = previous.get("activity_tasks", {})
                except (OSError, ValueError):
                    pass
            # 接口明细可能回显凭证，结果与日志一样作为敏感文件保存。
            write_json(directory / "result.json", summary, secret=True)
            if action != "details":
                print(f"经验：{summary.get('exp_total')}，等级：{summary.get('level', '未知')}")
            for pending in summary["pending"]:
                print(pending)
            return 1 if summary["pending"] else 0
        except SystemExit as error:
            print(f"操作未完成：{error}")
            return 2
        except Exception as error:
            print(f"操作失败（{type(error).__name__}），请检查网络、登录态或活动接口版本。")
            return 2
        finally:
            # 解释器退出时仍会刷新标准流，不能让它指向已关闭的日志。
            sys.stdout, sys.stderr = original_stdout, original_stderr
            for filename in ("qq_oauth.json", "qr_state.json", "qr_login.png"):
                (directory / filename).unlink(missing_ok=True)
