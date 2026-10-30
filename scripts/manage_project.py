#!/usr/bin/env python3
"""Axiom-manager：检查项目、中文提交、语义化版本发布。仅使用 Python 3.11+ 标准库。"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from functools import total_ordering


DEFAULT_CONFIG = {
    "schema": 1,
    "auto_push": False,
    "remote": "origin",
    "branch": None,
    "checks": [],
    "check_timeout_seconds": 300,
    "version_file": None,
    "sync_version_files": [],
}
CONFIG_PATH = ".axiom-manager/config.json"
SEMVER = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?\Z"
)
HEADER = re.compile(
    r"(feat|fix|docs|refactor|perf|test|build|ci|chore|style|revert)"
    r"(?:\(([A-Za-z0-9][A-Za-z0-9._/-]*)\))?(!)?: (\S.*)\Z"
)


class ManagerError(Exception):
    """可向用户直接显示的操作错误。"""


def read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def safe_path(root: Path, relative: str) -> Path:
    rel = Path(relative)
    if not relative or not rel.parts or rel.is_absolute() or ".." in rel.parts or rel.parts[0].lower() == ".git":
        raise ManagerError(f"路径必须位于项目内且不能指向 .git：{relative}")
    candidate = root / rel
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise ManagerError(f"路径超出项目：{relative}")
    cursor = root
    for part in rel.parts:
        cursor /= part
        if cursor.is_symlink() or getattr(cursor, "is_junction", lambda: False)():
            raise ManagerError(f"受管理的路径不能经过符号链接或目录联接：{relative}")
    return candidate


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".axiom-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        if path.exists():
            os.chmod(name, path.stat().st_mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def run(root: Path, args: list[str], *, check: bool = True, timeout: int = 300) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(args, cwd=root, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=timeout,
                                env={**os.environ, "PYTHONUTF8": "1"})
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ManagerError(f"命令无法完成：{args[0]}；{exc}") from exc
    if check and result.returncode:
        raise ManagerError(f"命令失败（{result.returncode}）：{' '.join(args)}\n{result.stdout}{result.stderr}".rstrip())
    return result


def git(root: Path, *args: str, check: bool = True) -> str:
    return run(root, ["git", *args], check=check).stdout.rstrip("\r\n")


def load_config(root: Path) -> dict:
    path = safe_path(root, CONFIG_PATH)
    config = dict(DEFAULT_CONFIG)
    if path.exists():
        try:
            incoming = json.loads(read_text(path))
        except (ValueError, UnicodeError) as exc:
            raise ManagerError(f"配置不是有效的 UTF-8 JSON：{path}") from exc
        if not isinstance(incoming, dict):
            raise ManagerError("配置顶层必须是 JSON 对象")
        unknown = set(incoming) - set(config)
        if unknown:
            raise ManagerError(f"未知配置字段：{', '.join(sorted(unknown))}")
        config.update(incoming)
    if type(config["schema"]) is not int or config["schema"] != 1:
        raise ManagerError("不支持的配置 schema；当前为 1")
    if type(config["auto_push"]) is not bool:
        raise ManagerError("auto_push 必须是布尔值")
    if not isinstance(config["remote"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", config["remote"]):
        raise ManagerError("remote 必须是远端名称，例如 origin")
    if config["branch"] is not None and (not isinstance(config["branch"], str) or not config["branch"] or config["branch"].startswith("-")):
        raise ManagerError("branch 必须是分支名称或 null")
    if type(config["check_timeout_seconds"]) is not int or not 1 <= config["check_timeout_seconds"] <= 3600:
        raise ManagerError("check_timeout_seconds 必须为 1–3600 的整数")
    checks = config["checks"]
    if not isinstance(checks, list) or any(not isinstance(c, list) or not c or any(not isinstance(a, str) or not a for a in c) for c in checks):
        raise ManagerError("checks 必须是命令参数数组，例如 [[\"{python}\", \"-m\", \"unittest\"]]")
    if config["version_file"] is not None:
        if not isinstance(config["version_file"], str):
            raise ManagerError("version_file 必须是路径或 null")
        safe_path(root, config["version_file"])
    if not isinstance(config["sync_version_files"], list) or any(not isinstance(p, str) for p in config["sync_version_files"]):
        raise ManagerError("sync_version_files 必须是路径数组")
    for path_value in config["sync_version_files"]:
        safe_path(root, path_value)
    return config


@total_ordering
@dataclass(frozen=True, eq=False)
class Version:
    major: int
    minor: int
    patch: int
    pre: str | None = None
    build: str | None = None

    @classmethod
    def parse(cls, value: str) -> Version:
        match = SEMVER.fullmatch(value)
        if not match or any(p.isdigit() and len(p) > 1 and p[0] == "0" for p in (match[4] or "").split(".")):
            raise ManagerError(f"版本不符合语义化版本规范：{value}")
        return cls(int(match[1]), int(match[2]), int(match[3]), match[4], match[5])

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}" + (f"-{self.pre}" if self.pre else "") + (f"+{self.build}" if self.build else "")

    def key(self) -> tuple:
        pre = (1,) if self.pre is None else (0, tuple((0, int(p)) if p.isdigit() else (1, p) for p in self.pre.split(".")))
        return self.major, self.minor, self.patch, pre

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Version) and self.key() == other.key()

    def __lt__(self, other: Version) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self.key() < other.key()

    def bump(self, level: str) -> Version:
        if level == "major":
            return Version(self.major + 1, 0, 0)
        if level == "minor":
            return Version(self.major, self.minor + 1, 0)
        return Version(self.major, self.minor, self.patch + 1)


def validate_message(message: str) -> re.Match:
    lines = message.strip().splitlines()
    match = HEADER.fullmatch(lines[0]) if lines else None
    if not match:
        raise ManagerError("提交标题应为 type(scope): 中文说明；范围可省略，使用英文冒号和空格")
    if len(lines[0]) > 72:
        raise ManagerError("提交标题不能超过 72 个 Unicode 字符；详细说明请放入正文")
    description = match[4]
    if not re.search(r"[\u3400-\u9fff]", description):
        raise ManagerError("提交说明须包含中文，技术名称可以保留英文")
    if description.strip("。.!！ ") in {"更新", "修改", "更新代码", "修复问题", "修复bug", "优化代码", "修改bug"}:
        raise ManagerError("提交说明过于笼统；请说明具体修改对象和结果")
    if len(lines) > 1 and lines[1].strip():
        raise ManagerError("标题与正文之间必须保留一个空行")
    if match[3] and not re.search(r"^BREAKING[ -]CHANGE: \S.+", message, re.M):
        raise ManagerError("不兼容修改须补充 BREAKING CHANGE:，说明影响和迁移办法")
    return match


def repo_root(root: Path) -> None:
    actual = Path(git(root, "rev-parse", "--show-toplevel")).resolve()
    if actual != root.resolve():
        raise ManagerError(f"--project 必须指向 Git 仓库根目录：{actual}")


def git_path(root: Path, name: str) -> Path:
    value = Path(git(root, "rev-parse", "--git-path", name))
    return value if value.is_absolute() else root / value


def status_entries(root: Path) -> list[tuple[str, str, str | None]]:
    chunks = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all").split("\0")
    entries = []
    i = 0
    while i < len(chunks) and chunks[i]:
        item = chunks[i]
        state, path = item[:2], item[3:]
        old = None
        if "R" in state or "C" in state:
            i += 1
            old = chunks[i]
        entries.append((state, path, old))
        i += 1
    return entries


def ensure_ready(root: Path) -> None:
    repo_root(root)
    if run(root, ["git", "symbolic-ref", "--quiet", "HEAD"], check=False).returncode:
        raise ManagerError("当前为游离 HEAD；请先切换到工作分支")
    for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply", "index.lock"):
        if git_path(root, marker).exists():
            raise ManagerError(f"Git 操作尚未完成（{marker}）；请先处理")
    entries = status_entries(root)
    if any(state not in {"??", "!!"} and state[0] != " " for state, _, _ in entries):
        raise ManagerError("已有暂存内容或冲突；请先处理，工具会保留原暂存区")
    for field in ("user.name", "user.email"):
        if not git(root, "config", "--get", field, check=False).strip():
            raise ManagerError(f"未配置 Git {field}；请先使用 git config 设置")


@contextlib.contextmanager
def operation_lock(root: Path):
    path = git_path(root, "axiom-manager.lock")
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ManagerError(f"已有 Axiom-manager 操作；若进程已结束，请检查后删除锁文件：{path}") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        path.unlink(missing_ok=True)


def readme_check(root: Path) -> None:
    names = ("README.md", "readme.md", "README.rst", "README")
    path = next((safe_path(root, n) for n in names if (root / n).is_file()), None)
    if path is None or not read_text(path).strip():
        raise ManagerError("缺少非空 README；请先说明项目用途和实际使用方法")
    if path.suffix.lower() != ".md":
        return
    text = re.sub(r"```.*?```|~~~.*?~~~", "", read_text(path), flags=re.S)
    from urllib.parse import unquote, urlsplit
    for target in re.findall(r"!?\[[^\]\n]*\]\(([^\n]+?)\)", text):
        target = target.strip()
        if target.startswith("<"):
            target = target[1:].split(">", 1)[0]
        else:
            target = target.split()[0]
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        candidate = root / unquote(parsed.path.lstrip("/"))
        if not candidate.is_file() and not candidate.is_dir():
            raise ManagerError(f"README 中的本地链接不存在：{target}")


def version_value(path: Path, content: str | None = None) -> str:
    text = read_text(path) if content is None else content
    try:
        if path.name == "package.json":
            value = json.loads(text)["version"]
        elif path.name == "pyproject.toml":
            data = tomllib.loads(text)
            project = data.get("project", {})
            poetry = data.get("tool", {}).get("poetry", {})
            if "version" in project.get("dynamic", []):
                raise ManagerError("pyproject.toml 使用动态版本；请显式配置一个受支持的静态 version_file")
            values = [entry["version"] for entry in (project, poetry) if "version" in entry]
            if not values or len(set(values)) != 1:
                raise ManagerError("pyproject.toml 缺少静态版本或两个版本字段不一致")
            value = values[0]
        else:
            value = text.strip()
        if not isinstance(value, str):
            raise ValueError("version 不是字符串")
        Version.parse(value)
        return value
    except (KeyError, ValueError, TypeError) as exc:
        raise ManagerError(f"无法读取版本：{path.name}；{exc}") from exc


def version_files(root: Path, config: dict) -> tuple[Version, list[str]]:
    if config["version_file"]:
        paths = [config["version_file"], *config["sync_version_files"]]
    else:
        paths = [name for name in ("package.json", "pyproject.toml", "VERSION") if (root / name).is_file()]
        paths += config["sync_version_files"]
    paths = list(dict.fromkeys(paths))
    if not paths:
        return Version(0, 1, 0), ["VERSION"]
    values = []
    for name in paths:
        path = safe_path(root, name)
        if not path.is_file():
            raise ManagerError(f"配置的版本文件不存在：{name}")
        values.append(version_value(path))
    if len(set(values)) != 1:
        raise ManagerError("版本来源不一致；请修正内容或通过 version_file / sync_version_files 指定权威来源")
    return Version.parse(values[0]), paths


def changed_version(path: Path, new: Version) -> bytes:
    text = read_text(path) if path.exists() else ""
    eol = "\r\n" if "\r\n" in text else "\n"
    if path.name == "package.json":
        data = json.loads(text)
        data["version"] = str(new)
        return (json.dumps(data, ensure_ascii=False, indent=2).replace("\n", eol) + eol).encode("utf-8")
    if path.name == "pyproject.toml":
        # 只替换受支持表中的 version 字符串，保留注释、其他字段及其版本号。
        lines = text.splitlines(keepends=True)
        section = ""
        replaced = 0
        for i, line in enumerate(lines):
            header = re.match(r"^\s*\[([^\[\]]+)\]\s*(?:#.*)?$", line.rstrip("\r\n"))
            if line.lstrip().startswith("["):
                section = header[1].strip() if header else ""
            if section in {"project", "tool.poetry"}:
                match = re.match(r"^(\s*version\s*=\s*)([\"'])([^\"']*)([\"'])(.*)$", line.rstrip("\r\n"))
                if match and match[2] == match[4]:
                    ending = line[len(line.rstrip("\r\n")):]
                    lines[i] = f"{match[1]}{match[2]}{new}{match[4]}{match[5]}{ending}"
                    replaced += 1
        if not replaced:
            raise ManagerError("无法安全改写 TOML 版本；请使用单行 project.version 或 tool.poetry.version")
        result = "".join(lines)
        if version_value(path, result) != str(new):
            raise ManagerError("改写后的 TOML 版本验证失败")
        return result.encode("utf-8")
    return (str(new) + eol).encode("utf-8")


def lock_updates(root: Path, paths: list[str], current: Version, new: Version) -> dict[str, bytes]:
    updates = {}
    for source in paths:
        if Path(source).name != "package.json":
            continue
        for name in ("package-lock.json", "npm-shrinkwrap.json"):
            rel = (Path(source).parent / name).as_posix()
            path = safe_path(root, rel)
            if not path.exists():
                continue
            data = json.loads(read_text(path))
            if not isinstance(data, dict) or not isinstance(data.get("packages", {}), dict):
                raise ManagerError(f"{rel} 的项目锁文件结构不受支持")
            targets = [data]
            if "" in data.get("packages", {}):
                targets.append(data["packages"][""])
            for target in targets:
                if not isinstance(target, dict):
                    raise ManagerError(f"{rel} 的项目版本条目必须为对象")
                if target.get("version") != str(current):
                    raise ManagerError(f"{rel} 的项目版本与 package.json 不一致")
                target["version"] = str(new)
            updates[rel] = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return updates


def project_checks(root: Path, config: dict, reason: str | None) -> None:
    readme_check(root)
    current, paths = version_files(root, config)
    lock_updates(root, paths, current, current)
    if not config["checks"]:
        if not reason or not reason.strip():
            raise ManagerError("尚未配置 checks；请配置项目验证命令。确无适用命令时传 --no-checks-reason 说明实际检查方法")
        print(f"未运行自动验证命令，原因：{reason.strip()}")
    for command in config["checks"]:
        args = [part.replace("{python}", sys.executable) for part in command]
        print(f"验证命令：{' '.join(args)}")
        result = run(root, args, timeout=config["check_timeout_seconds"])
        if result.stdout.strip():
            print(result.stdout.rstrip())
        if result.stderr.strip():
            print(result.stderr.rstrip())
    # 验证命令可能修改文件，结束后再次检查文件结构和版本一致性。
    readme_check(root)
    current, paths = version_files(root, config)
    lock_updates(root, paths, current, current)
    print("检查：通过（文档内容是否准确仍需结合实际修改核对）")


def selected_changes(root: Path, names: list[str]) -> list[str]:
    selected = []
    for name in names:
        path = safe_path(root, name)
        rel = path.relative_to(root).as_posix()
        if path.is_dir():
            raise ManagerError(f"请逐个列出文件，以免混入无关改动：{name}")
        if rel.startswith(".axiom-manager/backups/") or re.search(r"\.bak(?:-|$)", path.name):
            raise ManagerError(f"备份不应纳入提交：{name}")
        selected.append(rel)
    changed = set()
    for _, path, old in status_entries(root):
        changed.add(path)
        if old:
            changed.add(old)
    return list(dict.fromkeys(name for name in selected if name in changed))


def head(root: Path) -> str:
    return git(root, "rev-parse", "--verify", "HEAD", check=False)


def write_commit(root: Path, names: list[str], message: str) -> str:
    index = git_path(root, "index")
    saved_index = index.read_bytes() if index.exists() else None
    before = head(root)
    try:
        git(root, "--literal-pathspecs", "add", "--", *names)
        staged = git(root, "diff", "--cached", "--name-only", "-z", "--no-renames").split("\0")
        if set(filter(None, staged)) != set(names):
            raise ManagerError("暂存文件与所选文件不一致；请检查重命名、忽略文件或并发修改")
        fd, temp = tempfile.mkstemp(prefix="axiom-commit-", suffix=".txt")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(message.strip() + "\n")
            git(root, "commit", "--file", temp)
        finally:
            os.unlink(temp)
    except Exception:
        if head(root) == before:
            if saved_index is None:
                index.unlink(missing_ok=True)
            else:
                atomic_write(index, saved_index)
        raise
    result = head(root)
    print(f"已提交：{result[:12]} {message.splitlines()[0]}")
    return result


def push_changes(root: Path, config: dict, tag: str | None = None, *, write: bool = False) -> None:
    repo_root(root)
    branch = config["branch"] or git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    git(root, "check-ref-format", "--branch", branch)
    remote = config["remote"]
    if not git(root, "remote", "get-url", remote, check=False):
        raise ManagerError(f"远端 {remote} 不存在；本地提交保持不变")
    args = ["push"]
    if tag:
        Version.parse(tag.removeprefix("v"))
        if not tag.startswith("v") or git(root, "rev-parse", f"refs/tags/{tag}^{{commit}}") != head(root):
            raise ManagerError("推送的发布标签必须指向当前提交")
        args.append("--atomic")
    args.extend([remote, f"HEAD:refs/heads/{branch}"])
    if tag:
        args.append(f"refs/tags/{tag}:refs/tags/{tag}")
    print(f"{'执行' if write else '预览'}：git {' '.join(args)}")
    if write:
        try:
            git(root, *args)
        except ManagerError as exc:
            raise ManagerError(f"本地提交{'和标签' if tag else ''}已保留，推送失败；用 push 子命令重试{'并指定 --tag ' + tag if tag else ''}。\n{exc}") from exc
        print("已推送到远端")


def latest_tag(root: Path) -> tuple[str | None, Version | None]:
    tags = []
    for tag in git(root, "tag", "--merged", "HEAD").splitlines():
        if not tag.startswith("v"):
            continue
        try:
            tags.append((Version.parse(tag[1:]), tag))
        except ManagerError:
            continue
    if not tags:
        return None, None
    version, tag = max(tags, key=lambda item: item[0].key())
    return tag, version


def commit_messages(root: Path, since: str | None) -> list[str]:
    span = f"{since}..HEAD" if since else "HEAD"
    return [s.strip() for s in git(root, "log", "--format=%B%x00", span).split("\0") if s.strip()]


def infer_bump(messages: list[str], current: Version) -> str | None:
    level = None
    for message in messages:
        first = message.splitlines()[0]
        match = HEADER.fullmatch(first)
        if (match and match[3]) or re.search(r"^BREAKING[ -]CHANGE: \S", message, re.M):
            return "minor" if current.major == 0 else "major"
        if match and match[1] == "feat":
            level = "minor"
        elif match and match[1] in {"fix", "perf"} and level is None:
            level = "patch"
    return level


def release_version(current: Version, last: Version | None, messages: list[str], bump: str, explicit: str | None) -> Version:
    if explicit:
        result = Version.parse(explicit)
        if result < current or (last is not None and result <= last):
            raise ManagerError("新版本必须不低于当前文件版本，并高于已有发布标签（构建元数据不增加优先级）")
        return result
    if last is None:
        return current  # 第一次发布沿用当前版本；无版本文件时为 0.1.0。
    if current != last:
        raise ManagerError("当前版本与最近发布标签不同；请通过 --version 明确准备发布的版本")
    if current.pre:
        raise ManagerError("预发布版本请使用 --version 指定下一个预发布或正式版本")
    level = infer_bump(messages, current) if bump == "auto" else bump
    if level is None:
        raise ManagerError("本次只有文档、测试或内部整理，无需自动发版；确需交付时显式指定 --bump 或 --version")
    return current.bump(level)


def merge_notes(notes: list[str]) -> str:
    """累计同一目标版本的预发布说明，保留迁移段落并去掉重复条目。"""
    sections: dict[str, list[str]] = {}
    for note in notes:
        heading = ""
        for line in note.splitlines():
            if line.startswith("### "):
                heading = line
            elif line.strip():
                rows = sections.setdefault(heading, [])
                if line not in rows:
                    rows.append(line)
    return "\n\n".join((heading + "\n\n" if heading else "") + "\n".join(lines) for heading, lines in sections.items())


def release_changelog(root: Path, new: Version, messages: list[str], current: Version | None = None) -> bytes:
    path = safe_path(root, "CHANGELOG.md")
    text = read_text(path) if path.exists() else "# 更新日志\n\n## [Unreleased]\n\n"
    eol = "\r\n" if "\r\n" in text else "\n"
    normalized = text.replace("\r\n", "\n")
    heading = re.search(r"^## (?:\[Unreleased\]|Unreleased|\[待发布\]|待发布)\s*$", normalized, re.M)
    if not heading:
        raise ManagerError("CHANGELOG.md 需包含独立的 ## [Unreleased] 或 ## [待发布] 段，避免覆盖已有结构")
    if re.search(rf"^## \[?{re.escape(str(new))}\]?(?:\s|$)", normalized, re.M):
        raise ManagerError(f"CHANGELOG 已存在版本 {new}")
    following = re.search(r"^## ", normalized[heading.end():], re.M)
    end = heading.end() + following.start() if following else len(normalized)
    pending = normalized[heading.end():end].strip()
    substantive = [line for line in pending.splitlines() if line.strip() and not line.startswith("#") and not line.lstrip().startswith("<!--")]
    if not substantive:
        groups: dict[str, list[str]] = {}
        for message in messages:
            first = message.splitlines()[0]
            match = HEADER.fullmatch(first)
            if match:
                kind = "不兼容变化" if match[3] or re.search(r"^BREAKING[ -]CHANGE:", message, re.M) else {"feat": "新增", "fix": "修复", "perf": "改进"}.get(match[1])
                if kind:
                    groups.setdefault(kind, []).append(match[4])
        pending = "\n\n".join("### " + kind + "\n\n" + "\n".join("- " + item for item in dict.fromkeys(items)) for kind, items in groups.items())
    if current and current.pre and (current.major, current.minor, current.patch) == (new.major, new.minor, new.patch):
        # 正式版需要覆盖该目标版本的全部预发布变化；预发布无新说明时沿用上一版。
        headings = list(re.finditer(r"^## \[([^\]]+)\].*$", normalized, re.M))
        prior_notes = []
        for i, version_heading in enumerate(headings):
            try:
                version = Version.parse(version_heading[1])
            except ManagerError:
                continue
            if not version.pre or (version.major, version.minor, version.patch) != (new.major, new.minor, new.patch):
                continue
            stop = headings[i + 1].start() if i + 1 < len(headings) else len(normalized)
            if new.pre is None or (not pending and version == current):
                prior_notes.append(normalized[version_heading.end():stop].strip())
        if prior_notes:
            pending = merge_notes([pending, *prior_notes])
    if not pending:
        raise ManagerError("没有可整理的用户变化；请在 CHANGELOG 待发布段填写真实更新说明")
    date = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat()
    prefix = normalized[:heading.end()].rstrip()
    suffix = normalized[end:].lstrip("\n")
    result = prefix + f"\n\n## [{new}] - {date}\n\n{pending}\n\n" + suffix
    return result.replace("\n", eol).encode("utf-8")


def release_project(root: Path, config: dict, args: argparse.Namespace) -> None:
    ensure_ready(root)
    if status_entries(root):
        raise ManagerError("发布前工作区必须干净；请先提交已完成的修改")
    if not head(root):
        raise ManagerError("发布前至少需要一个提交")
    planned_head = head(root)
    current, paths = version_files(root, config)
    last_tag, last = latest_tag(root)
    messages = commit_messages(root, last_tag)
    # 标签创建失败后可以直接重试，避免再次增加版本或创建重复发布提交。
    pending_release = git(root, "log", "-1", "--format=%s") == f"chore(release): 发布 v{current}" and last != current
    if pending_release and (not args.version or args.version == str(current)):
        new = current
        updates = {}
        print(f"恢复发布：补建 v{new} 标签")
    else:
        new = release_version(current, last, messages, args.bump, args.version)
        updates = {name: changed_version(safe_path(root, name), new) for name in paths}
        updates.update(lock_updates(root, paths, current, new))
        updates["CHANGELOG.md"] = release_changelog(root, new, messages, current)
        updates = {name: value for name, value in updates.items() if not (root / name).exists() or (root / name).read_bytes() != value}
    tag = f"v{new}"
    if run(root, ["git", "show-ref", "--verify", "--quiet", f"refs/tags/{tag}"], check=False).returncode == 0:
        raise ManagerError(f"标签已存在：{tag}")
    print(f"发布计划：{current} → {new}；标签 {tag}；修改文件：{', '.join(updates) or '无'}")
    if not args.write:
        print("预览完成；加 --write 才会修改文件、提交和创建本地标签")
        return
    with operation_lock(root):
        ensure_ready(root)
        if status_entries(root) or head(root) != planned_head:
            raise ManagerError("工作区在预检后发生变化，请重新检查")
        saved = {name: (root / name).read_bytes() if (root / name).exists() else None for name in updates}
        before = head(root)
        try:
            for name, value in updates.items():
                atomic_write(safe_path(root, name), value)
            project_checks(root, config, args.no_checks_reason)
            ensure_ready(root)
            if head(root) != before:
                raise ManagerError("验证过程中 HEAD 发生变化；已保留现场，请检查并发 Git 操作")
            if any(not (root / name).exists() or (root / name).read_bytes() != value for name, value in updates.items()):
                raise ManagerError("验证命令修改了预定发布文件；已保留不同内容，请检查后重新发布")
            unexpected = {path for _, path, _ in status_entries(root)} - set(updates)
            if unexpected:
                raise ManagerError(f"验证命令产生了额外改动，已保留供检查：{', '.join(sorted(unexpected))}")
            if updates:
                write_commit(root, list(updates), f"chore(release): 发布 {tag}")
        except Exception:
            if head(root) == before:
                for name, original in saved.items():
                    path = root / name
                    if path.exists() and path.read_bytes() == updates[name]:
                        if original is None:
                            path.unlink()
                        else:
                            atomic_write(path, original)
            raise
        try:
            git(root, "tag", "-a", tag, "-m", f"发布 {tag}")
        except ManagerError as exc:
            raise ManagerError(f"发布提交已保留，标签创建失败；修复原因后重试 release。\n{exc}") from exc
        print(f"已创建本地发布标签：{tag}")
        if args.push if args.push is not None else config["auto_push"]:
            push_changes(root, config, tag, write=True)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Axiom-manager：检查、中文 Git 提交和版本发布（写入需 --write）")
    p.add_argument("--project", default=".", help="项目根目录，默认当前目录；放在子命令之前")
    subs = p.add_subparsers(dest="command", required=True)
    subs.add_parser("status", help="显示 Git 状态、当前版本和项目配置")
    c = subs.add_parser("check", help="运行文档、版本和已配置的项目验证命令")
    c.add_argument("--no-checks-reason", help="未配置验证命令时，说明原因和实际检查方法")
    lint = subs.add_parser("lint-message", help="校验中文约定式提交信息")
    group = lint.add_mutually_exclusive_group(required=True)
    group.add_argument("--message", "-m")
    group.add_argument("--message-file")
    commit = subs.add_parser("commit", help="仅暂存指定的本次修改文件并提交；默认预览")
    group = commit.add_mutually_exclusive_group(required=True)
    group.add_argument("--message", "-m")
    group.add_argument("--message-file")
    commit.add_argument("--files", nargs="+", required=True, help="相对项目根目录的文件路径；重命名请包含新旧两个路径")
    commit.add_argument("--no-checks-reason")
    release = subs.add_parser("release", help="同步版本和 CHANGELOG、提交并创建本地标签；默认预览")
    group = release.add_mutually_exclusive_group()
    group.add_argument("--bump", choices=("auto", "patch", "minor", "major"), default="auto")
    group.add_argument("--version", help="明确版本，例如 1.0.0 或 0.2.0-beta.1")
    release.add_argument("--no-checks-reason")
    for child in (commit, release):
        child.add_argument("--write", action="store_true", help="执行实际写入")
        group = child.add_mutually_exclusive_group()
        group.add_argument("--push", action="store_true", dest="push", default=None, help="完成后推送远端")
        group.add_argument("--no-push", action="store_false", dest="push", help="本次只操作本地，覆盖 auto_push")
    push = subs.add_parser("push", help="单独推送或重试推送；不会重复提交")
    push.add_argument("--tag", help="同时原子推送指向 HEAD 的发布标签，例如 v0.1.0")
    push.add_argument("--write", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        root = Path(args.project).expanduser().resolve()
        if not root.is_dir():
            raise ManagerError(f"项目目录不存在：{root}")
        if args.command == "lint-message":
            message = read_text(Path(args.message_file)) if args.message_file else args.message
            validate_message(message)
            print("提交信息：通过")
            return 0
        config = load_config(root)
        if args.command == "status":
            repo_root(root)
            version, paths = version_files(root, config)
            print(f"项目：{root}\n当前版本：{version}（{', '.join(paths)}）\n自动推送：{config['auto_push']}\n验证命令：{len(config['checks'])} 条")
            print(git(root, "status", "--short") or "工作区干净")
        elif args.command == "check":
            project_checks(root, config, args.no_checks_reason)
        elif args.command == "commit":
            message = read_text(Path(args.message_file)) if args.message_file else args.message
            validate_message(message)
            ensure_ready(root)
            names = selected_changes(root, args.files)
            if not names:
                print("所选文件没有实际改动，已跳过提交")
                return 0
            print(f"提交计划：{message.splitlines()[0]}\n文件：{', '.join(names)}")
            if not args.write:
                print("预览完成；加 --write 后运行验证并提交")
                return 0
            with operation_lock(root):
                ensure_ready(root)
                project_checks(root, config, args.no_checks_reason)
                names = selected_changes(root, args.files)
                if not names:
                    raise ManagerError("验证后所选文件已无改动；请重新检查")
                ensure_ready(root)
                write_commit(root, names, message)
                if args.push if args.push is not None else config["auto_push"]:
                    push_changes(root, config, write=True)
        elif args.command == "release":
            release_project(root, config, args)
        elif args.command == "push":
            if args.write:
                with operation_lock(root):
                    push_changes(root, config, args.tag, write=True)
            else:
                push_changes(root, config, args.tag)
        return 0
    except (ManagerError, OSError, UnicodeError, ValueError, TypeError) as exc:
        print(f"操作未完成：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
