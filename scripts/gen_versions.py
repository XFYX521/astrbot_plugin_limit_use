#!/usr/bin/env python3
"""从 CHANGELOG.md + git 历史生成 versions.json 与 VERSIONS.md。

用法（仓库根目录或任意目录）：

    python scripts/gen_versions.py

数据来源：
- 版本号与变更条目：CHANGELOG.md 的 ``## vX.Y.Z`` 段落
- 发布日期与提交：git 历史中 metadata.yaml 的 version 首次变为该版本的提交
  （v1.0.3 当时未单独提升 metadata 版本号，见 VERSION_OVERRIDES）
- tag / zip 下载地址：仅当该提交上已有同名 git tag 时生成

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

    plugin_id = f"{metadata.get('author')}/{metadata.get('name')}"
    return {
        "name": metadata.get("name"),
        "author": metadata.get("author"),
        "plugin_id": plugin_id,
        "repo": repo,
        "display_name": metadata.get("display_name"),
        "desc": metadata.get("desc"),
        "support_platforms": metadata.get("support_platforms") or [],
        "astrbot_version": metadata.get("astrbot_version") or None,
        "latest": releases[0]["version"] if releases else None,
        "releases": releases,
        "market_record": {plugin_id: build_market_record(metadata, repo, releases)},
    }


def build_market_record(metadata: dict, repo: str, releases: list[dict]) -> dict:
    """按插件市场规范 2026-06-27 生成单条 PluginRecord（仅规范字段）。"""
    latest = releases[0] if releases else {}
    record = {
        "author": metadata.get("author"),
        "name": metadata.get("name"),
        "version": latest.get("version"),
        "repo": repo,
        "desc": metadata.get("desc"),
    }
    for key in ("display_name", "support_platforms", "astrbot_version"):
        value = metadata.get(key)
        if value:
            record[key] = value
    if latest.get("zip_url"):
        record["download_url"] = latest["zip_url"]
    return record


def render_markdown(payload: dict) -> str:
    latest = payload["releases"][0]
    lines = [
        "# 版本列表",
        "",
        f"插件：`{payload['name']}` · 作者：{payload['author']} · "
        f"仓库：{payload['repo']}",
        "",
        f"当前最新版本：**{latest['version']}**（{latest['date']}）"
        + (f"，tag `{latest['tag']}`" if latest["tag"] else ""),
        "",
        "本文件与 `versions.json` 均由 `python scripts/gen_versions.py` 从 "
        "`CHANGELOG.md` 和 git 历史生成，请勿手改。",
        "",
        "| 版本 | 日期 | 提交 | 主要变更 |",
        "|:---|:---|:---|:---|",
    ]
    for rel in payload["releases"]:
        commit = rel["commit"] or "—"
        commit_cell = (
            f"[{commit[:7]}]({payload['repo']}/commit/{commit})" if rel["commit"] else "—"
        )
        summary = rel["changes"][0] if rel["changes"] else ""
        lines.append(
            f"| {rel['version']} | {rel['date'] or '—'} | {commit_cell} | {summary} |"
        )
    lines += [
        "",
        "完整变更见 [CHANGELOG.md](CHANGELOG.md)。",
        "",
        "## 市场记录（可直接使用）",
        "",
        "按插件市场 JSON 规范（2026-06-27）生成的当前版本 `PluginRecord`，"
        "可直接合并进市场源根对象（根 key 即 `plugin_id`）：",
        "",
        "```json",
        json.dumps(payload["market_record"], ensure_ascii=False, indent=2),
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
        "5. 更新插件市场记录：`version` 与 `metadata.yaml` 一致、`repo` 填",
        f"   `{payload['repo']}`、可选 `download_url` 用 `versions.json` 里最新版的 `zip_url`。",
        "",
        "## 说明",
        "",
        "- 市场规范（[2026-06-27](https://docs.astrbot.app/dev/plugin-market/2026-06-27.html)）的 "
        "`PluginRecord` 只有一个 `version` 字段，多版本历史由本文件与 `versions.json` 承载。",
        "- `zip_url` 只在对应 tag 已推送时生成；未打 tag 的历史版本留空。",
        "- `v1.0.3` 当时未单独修改 `metadata.yaml` 的 `version`（到 v1.0.4 提交才更新），"
        "其提交按提交信息定位，见 `scripts/gen_versions.py` 的 `VERSION_OVERRIDES`。",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    payload = build_payload()
    VERSIONS_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    VERSIONS_MD.write_text(render_markdown(payload), encoding="utf-8")
    print(f"已生成 {VERSIONS_JSON.name}（{len(payload['releases'])} 个版本）与 {VERSIONS_MD.name}")


if __name__ == "__main__":
    main()
