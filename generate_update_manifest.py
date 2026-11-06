"""为实际发布的 exe 生成 Gitee 版本信息，不能使用占位校验值。Created by 朱圳。"""
import argparse
import hashlib
import json
from pathlib import Path

from desktop_update import VERSION


def main():
    parser = argparse.ArgumentParser(description="生成 Gitee update.json")
    parser.add_argument("exe", type=Path)
    parser.add_argument("url", help="已验证可匿名下载的 Gitee 附件直链")
    parser.add_argument("--notes", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("update.json"))
    arguments = parser.parse_args()
    content = arguments.exe.read_bytes()
    manifest = {"version": f"v{VERSION}", "notes": arguments.notes.read_text(encoding="utf-8"),
                "url": arguments.url, "size": len(content), "sha256": hashlib.sha256(content).hexdigest()}
    arguments.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
