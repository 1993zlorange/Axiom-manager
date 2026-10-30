#!/usr/bin/env python3
"""预览、安装、更新或卸载 Axiom-manager；默认不写入。"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys

try:
    from .manage_project import DEFAULT_CONFIG, ManagerError, atomic_write, load_config, read_text, safe_path
except ImportError:
    from manage_project import DEFAULT_CONFIG, ManagerError, atomic_write, load_config, read_text, safe_path


ROOT = Path(__file__).resolve().parents[1]
BEGIN = "<!-- Axiom-manager:begin -->"
END = "<!-- Axiom-manager:end -->"
STATE = ".axiom-manager/install-state.json"
MANAGED = (".axiom-manager/manage.py", ".axiom-manager/config.json")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def find_block(text: str) -> tuple[int, int] | None:
    counts = text.count(BEGIN), text.count(END)
    if counts == (0, 0):
        return None
    if counts != (1, 1) or text.index(END) < text.index(BEGIN):
        raise ManagerError("AGENTS.md 的 Axiom-manager 标记重复、不完整或顺序错误；请先修复，原文件保持不变")
    for marker in (BEGIN, END):
        index = text.index(marker)
        if (index > 0 and text[index - 1] != "\n") or text[index + len(marker):].split("\n", 1)[0].strip("\r"):
            raise ManagerError("Axiom-manager 标记必须各自独占一行")
    start = text.index(BEGIN)
    end = text.index(END) + len(END)
    if text[end:end + 2] == "\r\n":
        end += 2
    elif text[end:end + 1] == "\n":
        end += 1
    return start, end


def load_state(root: Path) -> dict | None:
    path = safe_path(root, STATE)
    if not path.exists():
        return None
    try:
        state = json.loads(read_text(path))
    except (ValueError, UnicodeError) as exc:
        raise ManagerError("安装记录损坏；请检查 .axiom-manager/install-state.json，原文件保持不变") from exc
    if (not isinstance(state, dict) or state.get("schema") != 1
            or not isinstance(state.get("files"), dict)
            or set(state["files"]) != set(MANAGED)
            or not isinstance(state.get("created_files"), list)
            or any(name not in MANAGED for name in state["created_files"])
            or any(not isinstance(v, str) or not re_digest(v) for v in state["files"].values())
            or type(state.get("agents_existed")) is not bool
            or not isinstance(state.get("separator"), str)
            or state["separator"].strip()):
        raise ManagerError("安装记录结构不受支持；原文件保持不变")
    return state


def re_digest(value: str) -> bool:
    return len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def backup_folder(root: Path) -> Path:
    stamp = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime("%Y%m%d-%H%M%S-%f")
    return safe_path(root, f".axiom-manager/backups/{stamp}")


def apply_changes(root: Path, changes: dict[str, bytes | None], *, write: bool) -> None:
    if not changes:
        print("unchanged：所有内容已是当前状态")
        return
    originals = {}
    for name, new in changes.items():
        path = safe_path(root, name)
        if path.exists() and not path.is_file():
            raise ManagerError(f"目标应为文件：{name}")
        old = path.read_bytes() if path.exists() else None
        originals[name] = old
        action = "删除" if new is None else ("创建" if old is None else "更新")
        print(f"{action}：{name}")
    if not write:
        print("预览完成，未写入；加 --write 执行")
        return
    # 安装锁放在目标根，排除同工具并发安装；写入前再次核对原始内容。
    lock = safe_path(root, ".axiom-manager-install.lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ManagerError("已有安装或卸载操作；若进程已结束，请检查后移除 .axiom-manager-install.lock") from exc
    os.close(fd)
    applied = []
    backup = None
    try:
        for name, old in originals.items():
            path = safe_path(root, name)
            actual = path.read_bytes() if path.exists() else None
            if actual != old:
                raise ManagerError(f"文件在预检后发生变化，请重试：{name}")
        if any(old is not None for old in originals.values()):
            backup = backup_folder(root)
            for name, old in originals.items():
                if old is not None:
                    atomic_write(backup / name, old)
        for name, new in changes.items():
            path = safe_path(root, name)
            if new is None:
                path.unlink()
            else:
                atomic_write(path, new)
            applied.append(name)
        for name, new in changes.items():
            path = safe_path(root, name)
            if (new is None and path.exists()) or (new is not None and path.read_bytes() != new):
                raise ManagerError(f"写入后校验失败：{name}")
    except Exception:
        for name in reversed(applied):
            path = safe_path(root, name)
            old = originals[name]
            if old is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write(path, old)
        raise
    finally:
        lock.unlink(missing_ok=True)
    if backup:
        print(f"备份：{backup}")
    print("验证：通过")


def install(root: Path, *, write: bool = False) -> None:
    state = load_state(root)
    agents = safe_path(root, "AGENTS.md")
    old = read_text(agents) if agents.exists() else ""
    found = find_block(old)
    block = read_text(ROOT / "assets/agents-block.md").strip()
    eol = "\r\n" if "\r\n" in old else "\n"
    rendered = (BEGIN + "\n" + block.replace("\r\n", "\n") + "\n" + END + "\n").replace("\n", eol)
    separator = state["separator"] if state else ""
    if found:
        start, end = found
        new = old[:start] + rendered + old[end:]
    else:
        separator = "" if not old or old.endswith(eol * 2) else (eol if old.endswith(eol) else eol * 2)
        new = old + separator + rendered
    changes = {}
    if not agents.exists() or new != old:
        changes["AGENTS.md"] = new.encode("utf-8")
    runtime = (ROOT / "scripts/manage_project.py").read_bytes()
    runner = safe_path(root, MANAGED[0])
    if runner.exists() and runner.read_bytes() != runtime:
        if not state or digest(runner.read_bytes()) != state["files"][MANAGED[0]]:
            raise ManagerError("运行脚本存在本地修改或不属于本安装器；请先保存并处理 .axiom-manager/manage.py")
    if not runner.exists() or runner.read_bytes() != runtime:
        changes[MANAGED[0]] = runtime
    config_path = safe_path(root, MANAGED[1])
    if config_path.exists():
        load_config(root)  # 校验并保留用户配置；重新安装不重置设置。
        config = config_path.read_bytes()
    else:
        config = (json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        changes[MANAGED[1]] = config
    new_state = {
        "schema": 1,
        "version": read_text(ROOT / "VERSION").strip(),
        "agents_existed": state["agents_existed"] if state else agents.exists(),
        "separator": separator,
        "created_files": state["created_files"] if state else [name for name in MANAGED if not (root / name).exists()],
        # 保留最初写入的配置哈希，卸载时识别用户后续改动。
        "files": {MANAGED[0]: digest(runtime), MANAGED[1]: state["files"][MANAGED[1]] if state and config_path.exists() else digest(config)},
    }
    data = (json.dumps(new_state, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    state_path = safe_path(root, STATE)
    if not state_path.exists() or state_path.read_bytes() != data:
        changes[STATE] = data
    apply_changes(root, changes, write=write)


def uninstall(root: Path, *, write: bool = False) -> None:
    state = load_state(root)
    agents = safe_path(root, "AGENTS.md")
    old = read_text(agents) if agents.exists() else ""
    found = find_block(old)
    changes = {}
    if found:
        start, end = found
        prefix, suffix = old[:start], old[end:]
        separator = state["separator"] if state else ""
        if separator and prefix.endswith(separator):
            prefix = prefix[:-len(separator)]
        new = prefix + suffix
        changes["AGENTS.md"] = None if not new and state and not state["agents_existed"] else new.encode("utf-8")
    if state:
        retained = False
        for name, expected in state["files"].items():
            path = safe_path(root, name)
            if path.exists():
                if name not in state["created_files"]:
                    print(f"保留安装前已存在的文件：{name}")
                elif digest(path.read_bytes()) == expected:
                    changes[name] = None
                else:
                    retained = True
                    print(f"保留用户修改的文件：{name}")
        # 保留修改文件的安装记录，方便以后恢复和重复卸载。
        if not retained:
            changes[STATE] = None
    apply_changes(root, changes, write=write)
    if write:
        print("卸载完成；备份和用户修改的文件保留，可检查后手动清理空目录")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="安装或卸载 Axiom-manager，默认仅预览")
    parser.add_argument("target", nargs="?", default=".", help="目标项目根目录")
    parser.add_argument("--write", action="store_true", help="实际写入；已明确要求安装时可直接使用")
    parser.add_argument("--uninstall", action="store_true", help="移除独立规则块及未修改的安装文件")
    args = parser.parse_args(argv)
    try:
        root = Path(args.target).expanduser().resolve()
        if not root.is_dir():
            raise ManagerError(f"目标目录不存在：{root}")
        if args.uninstall:
            uninstall(root, write=args.write)
        else:
            install(root, write=args.write)
        return 0
    except (ManagerError, OSError, UnicodeError, ValueError, TypeError) as exc:
        print(f"安装操作未完成：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
