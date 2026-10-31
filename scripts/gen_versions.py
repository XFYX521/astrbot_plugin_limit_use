#!/usr/bin/env python3
"""从 CHANGELOG.md + git 历史生成 versions.json 与 VERSIONS.md。

用法（仓库根目录或任意目录）：

    python scripts/gen_versions.py

数据来源：
- 版本号与变更条目：CHANGELOG.md 的 ``## vX.Y.Z`` 段落
- 发布日期与提交：git 历史中 metadata.yaml 的 version 首次变为该版本的提交
  （v1.0.3 当时未单独提升 metadata 版本号，见 VERSION_OVERRIDES）
- tag / zip 下载地址：仅当该提交上已有同名 git tag 时生成

versions.json 同时是 AstrBot 可直接添加的「插件源」JSON：
- 根对象 ``$meta`` 提供插件源名称等信息（AstrBot 只读取其中的 ``name``，其余内容忽略）；
- 根键 ``<author>/<name>`` 是本插件当前版本的 PluginRecord；
- 多版本历史放在 ``$meta.releases`` 内，避免被市场列表当成插件条目。

只依赖 Python 标准库与 git 命令。
"""

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"
METADATA = ROOT / "metadata.yaml"
VERSIONS_JSON = ROOT / "versions.json"
VERSIONS_MD = ROOT / "VERSIONS.md"

# 这些版本没有单独提升 metadata.yaml 的 version，只能按提交信息定位
VERSION_OVERRIDES = {
    "v1.0.3": "ee22c1cffa47dc3eee9b1308fdc2a7e08ebeecc8",
}

VERSION_RE = re.compile(r"^## (v\d+\.\d+\.\d+)\s*$")

# 插件源 $meta（AstrBot 只用 $meta.name 作为插件源名称）
SOURCE_META_NAME = "XFYX521 插件源"
SOURCE_META_DESC = "XFYX521 的 AstrBot 插件源，提供对话次数限制插件的更新检测"
# 市场记录里可选的展示信息
SHORT_DESC = "按用户限制对话次数，额度用完后签到补充。"
TAGS = ["对话次数", "签到", "额度"]
CATEGORY = "其他"


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=True, encoding="utf-8", errors="replace"
    ).strip()


def git_show(sha: str, path: str) -> str:
    return subprocess.check_output(
        ["git", "show", f"{sha}:{path}"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def read_metadata() -> dict:
    """从 metadata.yaml 读取顶层字段（标量 + 简单字符串列表）。"""
    data = {}
    current_list = None
    for line in METADATA.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- ") and current_list:
            data[current_list].append(stripped[2:].strip().strip("\"'"))
            continue
        if line[0] in " \t":
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        value = value.split(" #", 1)[0].strip()
        if value == "":
            data[key.strip()] = []
            current_list = key.strip()
            continue
        current_list = None
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        data[key.strip()] = value
    return data


def read_changelog() -> dict[str, list[str]]:
    """返回 {版本: [变更条目, ...]}，保持 CHANGELOG 自上而下的顺序。"""
    sections: dict[str, list[str]] = {}
    current = None
    for line in CHANGELOG.read_text(encoding="utf-8").splitlines():
        m = VERSION_RE.match(line)
        if m:
            current = m.group(1)
            sections[current] = []
            continue
        if current is None:
            continue
        if line.startswith("## "):
            current = None
            continue
        if line.startswith("- "):
            sections[current].append(line[2:].strip())
    return sections


def build_release_index() -> dict[str, dict]:
    """遍历 git 历史，记录每个版本首次出现时的提交与日期。"""
    index: dict[str, dict] = {}
    log = git("log", "--reverse", "--format=%H%x09%ad", "--date=short")
    for line in log.splitlines():
        sha, _, date = line.partition("\t")
        try:
            metadata = git_show(sha, "metadata.yaml")
        except subprocess.CalledProcessError:
            continue
        m = re.search(r"^version:\s*(\S+)", metadata, re.MULTILINE)
        if not m:
            continue
        version = m.group(1).strip()
        if version not in index:
            index[version] = {"commit": sha, "date": date}
    for version, sha in VERSION_OVERRIDES.items():
        index[version] = {
            "commit": sha,
            "date": git("show", "-s", "--format=%ad", "--date=short", sha),
        }
    return index


def tags_at(sha: str) -> list[str]:
    out = git("tag", "--points-at", sha)
    return [t for t in out.splitlines() if t]


def build_market_record(metadata: dict, repo: str, latest: dict) -> dict:
    """按插件市场规范 2026-06-27 生成当前版本的 PluginRecord。"""
    record = {
        "author": metadata.get("author"),
        "name": metadata.get("name"),
        "version": latest.get("version"),
        "repo": repo,
        "desc": metadata.get("desc"),
        "short_desc": SHORT_DESC,
        "tags": TAGS,
        "category": CATEGORY,
    }
    for key in ("display_name", "support_platforms", "astrbot_version"):
        value = metadata.get(key)
        if value:
            record[key] = value
    if latest.get("zip_url"):
        record["download_url"] = latest["zip_url"]
        record["updated_at"] = f"{latest['date']}T00:00:00Z"
    return record


def build_payload() -> dict:
    metadata = read_metadata()
    changelog = read_changelog()
    index = build_release_index()
    repo = metadata.get("repo", "").rstrip("/")

    releases = []
    for version in changelog:  # CHANGELOG 顺序：最新在前
        info = index.get(version, {})
        sha = info.get("commit")
        tags = tags_at(sha) if sha else []
        tag = version if version in tags else (tags[0] if tags else None)
        releases.append(
            {
                "version": version,
                "date": info.get("date"),
                "commit": sha,
                "tag": tag,
                "zip_url": f"{repo}/archive/refs/tags/{tag}.zip" if tag else None,
                "changes": changelog[version],
                "note": (
                    "该版本未单独提升 metadata.yaml 的 version（v1.0.4 提交才更新）"
                    if version in VERSION_OVERRIDES
                    else None
                ),
            }
        )

    latest = releases[0]
    plugin_id = f"{metadata.get('author')}/{metadata.get('name')}"
    # 用当前 HEAD 的提交时间作为插件源的生成版本，保证同一提交下输出可复现
    generated_at = git("show", "-s", "--format=%cI", "HEAD")
    registry = {
        "$meta": {
            "schema_version": 1,
            "name": SOURCE_META_NAME,
            "version": generated_at,
            "homepage": repo,
            "repository": repo,
            "description": SOURCE_META_DESC,
            "updated_at": f"{latest['date']}T00:00:00Z",
            # 本仓库扩展：多版本历史（AstrBot 会跳过整个 $meta，不会当成插件条目）
            "releases": releases,
        },
        plugin_id: build_market_record(metadata, repo, latest),
    }
    return {
        "registry": registry,
        "releases": releases,
        "metadata": metadata,
        "repo": repo,
        "plugin_id": plugin_id,
        "latest": latest,
    }


def render_markdown(payload: dict) -> str:
    latest = payload["latest"]
    repo = payload["repo"]
    lines = [
        "# 版本列表",
        "",
        f"插件：`{payload['metadata'].get('name')}` · 作者：{payload['metadata'].get('author')} · "
        f"仓库：{repo}",
        "",
        f"当前最新版本：**{latest['version']}**（{latest['date']}）"
        + (f"，tag `{latest['tag']}`" if latest["tag"] else ""),
        "",
        "本文件与 `versions.json` 均由 `python scripts/gen_versions.py` "
        "从 `CHANGELOG.md` 和 git 历史生成，请勿手改。",
        "",
        "| 版本 | 日期 | 提交 | 主要变更 |",
        "|:---|:---|:---|:---|",
    ]
    for rel in payload["releases"]:
        commit = rel["commit"] or "—"
        commit_cell = (
            f"[{commit[:7]}]({repo}/commit/{commit})" if rel["commit"] else "—"
        )
        summary = rel["changes"][0] if rel["changes"] else ""
        lines.append(
            f"| {rel['version']} | {rel['date'] or '—'} | {commit_cell} | {summary} |"
        )
    lines += [
        "",
        "完整变更见 [CHANGELOG.md](CHANGELOG.md)。",
        "",
        "## 作为插件源使用（自动更新检测）",
        "",
        "`versions.json` 同时是一个可直接添加的 AstrBot 插件源 JSON（`$meta` + 根键 "
        f"`{payload['plugin_id']}`）。在 WebUI「插件市场 → 插件源」中添加：",
        "",
        "```text",
        f"{repo.replace('https://github.com/', 'https://raw.githubusercontent.com/')}/master/versions.json",
        "```",
        "",
        "添加时 AstrBot 会先请求该地址并读取 `$meta.name` 作为源名称。",
        "",
        "**只有 `install_method == \"market\"` 的安装才会显示「有新版本」**，这是 AstrBot "
        "前端的固定门槛（`updates_enabled && install_source.install_method === \"market\"`）。"
        "从链接/文件安装的插件只会看到「强制重新安装」。因此：",
        "",
        "1. 首次安装：添加上述插件源后，直接从该源安装本插件；",
        "2. 已从链接安装：在插件详情中「更换插件源」（后端接口 "
        "`POST /api/plugin/plugins/<plugin_id>/source`）绑定到该源，绑定后刷新插件页即可。",
        "",
        "更新检测的版本比较规则（前端 `has_update`）：市场记录 `version` 与已装 "
        "`metadata.yaml` 的 `version` 都须以 `v?数字` 开头，去掉 `v` 前缀后按 `.` 分段比较数字；"
        "市场版本更高时才提示更新。本文件的当前版本与 `metadata.yaml` 由同一脚本生成，天然一致。",
        "",
        "## 插件市场记录（PluginRecord）",
        "",
        "按插件市场 JSON 规范（[2026-06-27](https://docs.astrbot.app/dev/plugin-market/2026-06-27.html)）"
        "生成的当前版本 `PluginRecord`，可直接作为市场源根对象中 `"
        f"{payload['plugin_id']}` 键的值：",
        "",
        "```json",
        json.dumps(payload["registry"][payload["plugin_id"]], ensure_ascii=False, indent=2),
        "```",
        "",
        "## 发布新版本",
        "",
        "1. 修改 `metadata.yaml` 的 `version`（如 `v1.0.18`），并在 `CHANGELOG.md` 顶部新增对应条目；",
        "2. 在 `main.py` 不做版本号声明（版本只来自 `metadata.yaml`）；",
        "3. 运行 `python scripts/gen_versions.py` 重新生成 `versions.json` 与 `VERSIONS.md`；",
        "4. 提交后打同名 annotated tag 并推送：",
        "",
        "   ```bash",
        "   git tag -a v1.0.18 -m \"v1.0.18\"",
        "   git push origin master --tags",
        "   ```",
        "",
        "5. 若同时维护官方市场记录：`version` 与 `metadata.yaml` 一致、`repo` 填 "
        f"`{repo}`、`download_url` 用最新版的 `zip_url`（需 tag 已推送）。",
        "",
        "## 说明",
        "",
        "- 市场规范里的 `PluginRecord` 只有一个 `version` 字段，多版本历史由 `versions.json` "
        "的 `$meta.releases` 承载（AstrBot 会跳过整个 `$meta`，不会误当成插件条目）。",
        "- `zip_url` 只在对应 tag 已推送时生成；未打 tag 的历史版本留空。",
        "- `v1.0.3` 当时未单独修改 `metadata.yaml` 的 `version`（到 v1.0.4 提交才更新），"
        "其提交按提交信息定位，见 `scripts/gen_versions.py` 的 `VERSION_OVERRIDES`。",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    payload = build_payload()
    text = json.dumps(payload["registry"], ensure_ascii=False, indent=2) + "\n"
    VERSIONS_JSON.write_text(text, encoding="utf-8")
    VERSIONS_MD.write_text(render_markdown(payload), encoding="utf-8")
    print(
        f"已生成 {VERSIONS_JSON.name}（{len(payload['releases'])} 个版本）"
        f"与 {VERSIONS_MD.name}"
    )


if __name__ == "__main__":
    main()
