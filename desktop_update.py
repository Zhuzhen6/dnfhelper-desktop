"""从固定 GitHub Releases 检查更新并校验下载文件。Created by 朱圳。"""
import hashlib
import re
import json
from urllib.parse import urlparse
from pathlib import Path

import requests

VERSION = "0.4.1"
REPOSITORY = "Zhuzhen6/dnfhelper-desktop"
RELEASES_URL = f"https://github.com/{REPOSITORY}/releases"
SOURCE_FILE = Path(__file__).with_name("update_sources.json")


def gitee_repository():
    configuration = json.loads(SOURCE_FILE.read_text(encoding="utf-8"))
    repository = configuration.get("gitee_repository", "")
    if not isinstance(repository, str) or (repository and not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)):
        raise ValueError("Gitee 仓库配置无效")
    return repository


def gitee_release(repository):
    with requests.get(f"https://gitee.com/{repository}/raw/master/update.json", timeout=(8, 12)) as response:
        response.raise_for_status()
        if len(response.content) > 128 * 1024:
            raise ValueError("版本信息过大")
        metadata = response.json()
    version_tuple(metadata.get("version"))
    release = {"tag_name": metadata["version"], "body": metadata.get("notes", ""),
               "source": "gitee", "assets": [{"name": "DNFHelperDesktop.exe",
               "browser_download_url": metadata.get("url"), "size": metadata.get("size"),
               "digest": "sha256:" + str(metadata.get("sha256", ""))}]}
    release_asset(release)
    return release


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r"v?\d+\.\d+\.\d+", value):
        raise ValueError("版本格式无效，仅支持正式版本")
    return tuple(int(part) for part in value.lstrip("v").split("."))


def latest_release():
    repository = gitee_repository()
    if repository:
        try:
            return gitee_release(repository)
        except (requests.RequestException, ValueError, KeyError, TypeError):
            pass
    return github_release()


def github_release():
    with requests.get(f"https://api.github.com/repos/{REPOSITORY}/releases/latest", timeout=25,
                      headers={"Accept": "application/vnd.github+json"}) as response:
        response.raise_for_status()
        release = response.json()
    if release.get("draft") or release.get("prerelease"):
        raise ValueError("未找到正式版本")
    version_tuple(release.get("tag_name"))
    return release


def release_asset(release):
    asset = next((asset for asset in release.get("assets", []) if asset.get("name") == "DNFHelperDesktop.exe"), None)
    if not asset:
        raise ValueError("该版本尚未提供 Windows exe")
    expected_url = f"https://github.com/{REPOSITORY}/releases/download/{release['tag_name']}/DNFHelperDesktop.exe"
    if release.get("source") == "gitee":
        repository = gitee_repository()
        url = urlparse(str(asset.get("browser_download_url", "")))
        allowed = (repository and url.scheme == "https" and url.netloc == "gitee.com"
                   and url.path.startswith(f"/{repository}/") and not url.username and not url.fragment)
    else:
        allowed = asset.get("browser_download_url") == expected_url
    if not allowed:
        raise ValueError("更新文件地址无效")
    digest = asset.get("digest", "")
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
        raise ValueError("该版本缺少 SHA256 校验，暂不支持直接更新")
    size = asset.get("size")
    if type(size) is not int or not 0 < size <= 200 * 1024 * 1024:
        raise ValueError("更新文件大小无效")
    return asset


def download_release(release, directory):
    try:
        return download_asset(release, directory)
    except (requests.RequestException, ValueError, OSError):
        if release.get("source") != "gitee":
            raise
        fallback = github_release()
        original = release_asset(release)
        alternative = release_asset(fallback)
        if (version_tuple(fallback["tag_name"]) != version_tuple(release["tag_name"])
                or alternative["digest"] != original["digest"] or alternative["size"] != original["size"]):
            raise ValueError("Gitee 下载失败，GitHub 未提供相同版本与校验值的附件，请稍后重试")
        return download_asset(fallback, directory)


def download_asset(release, directory):
    asset = release_asset(release)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "DNFHelperDesktop.new.exe"
    digest = hashlib.sha256()
    size = 0
    try:
        with requests.get(asset["browser_download_url"], stream=True, timeout=(15, 45)) as response:
            response.raise_for_status()
            with path.open("wb") as stream:
                for chunk in response.iter_content(256 * 1024):
                    size += len(chunk)
                    if size > asset["size"]:
                        raise ValueError("下载大小超出声明值")
                    digest.update(chunk)
                    stream.write(chunk)
        if size != asset["size"] or digest.hexdigest() != asset["digest"][7:]:
            raise ValueError("下载不完整或 SHA256 校验失败，请重试")
        with path.open("rb") as stream:
            if stream.read(2) != b"MZ":
                raise ValueError("更新文件不是 Windows 程序")
        return path
    except Exception:
        path.unlink(missing_ok=True)
        raise
