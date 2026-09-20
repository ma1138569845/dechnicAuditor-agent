#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""能源审计技能部署器（带双写入者守卫）—— 2026-09-20 建，同日升级

## 为什么有这个东西

2026-09-20 事故：用 `robocopy /MIR` 把 E 盘镜像**整体**覆盖到 D 盘
`skills/energy-audit`，抹掉了 D 盘上未提交的文件改动，git 层面无法恢复。
同日稍后发现：**D 盘 repo 有第二个写入者**（另一会话在同一分支连续提交），
所以 D 盘可能既"脏"又"领先于镜像"。

`/MIR` 有两个致命属性，本脚本各治一条：
  1. 不看目标有没有未提交改动 → **脏文件守卫**：任何将被覆盖/删除、且 git 脏的
     目标文件，直接阻挡。
  2. 不看内容是不是别人新写的 → **部署基线清单**：只允许覆盖"自上次发布以来没被
     动过"的目标文件（内容 == 上次发布时记下的哈希）。对不上 = 有人在目标侧改了
     东西 → 阻挡，交给人裁决。

另外默认**只动有差异的文件**（外科式），不做整目录镜像；确有需要再 `--mirror`。
内容比对标**行尾归一化**（E 盘镜像 CRLF / D 盘检出 LF，不归一化会误报 24 个文件）。

## 用法

    python scripts/deploy_ea_skills.py --check        # 只报告，不落盘
    python scripts/deploy_ea_skills.py               # 外科式发布（默认）
    python scripts/deploy_ea_skills.py --mirror      # 额外删除目标多出来的文件
    python scripts/deploy_ea_skills.py --force       # 跳过守卫（明确知道在丢什么）
    python scripts/deploy_ea_skills.py --adopt       # 把当前目标状态登记为新基线
    python scripts/deploy_ea_skills.py --backport --yes
                                                     # 反向：把**目标领先**的内容
                                                     # 回流到镜像（自动备份镜像侧）

发布成功后自动刷新基线 `repo/_deploy/last_deploy.json`，
再调用 `sync_ea_skills.py` 发布到 profiles，并跑一次 `--verify`。

退出码：0 = 成功/无待办；1 = 被守卫拦下或发布失败。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
SRC = PKG_ROOT / "skills" / "energy-audit"
MANIFEST = Path(os.environ.get("EA_DEPLOY_MANIFEST")
                or (PKG_ROOT / "_deploy" / "last_deploy.json"))
TARGET_REPO = Path(os.environ.get("EA_TARGET_REPO")
                   or r"D:\data\pyProject\dc_agent\dechnicAuditor-agent")
TARGET = TARGET_REPO / "skills" / "energy-audit"
SCOPE = "skills/energy-audit/"

SKIP_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
SKIP_SUFFIX = {".pyc", ".pyo"}
SKIP_NAMES = {".DS_Store", "Thumbs.db"}


def _utf8_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass


def norm_sha(path: Path) -> str:
    """内容哈希，**行尾统一为 LF**：E 盘镜像与 D 盘检出的行尾不同（CRLF vs LF），
    不归一化会把一批文件误报成"已修改"。"""
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def walk(root: Path) -> dict:
    out: dict = {}
    if not root.is_dir():
        return out
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if set(p.relative_to(root).parts[:-1]) & SKIP_DIRS:
            continue
        if p.suffix.lower() in SKIP_SUFFIX or p.name in SKIP_NAMES:
            continue
        out[p.relative_to(root).as_posix()] = p
    return out


def diff_tree() -> dict:
    src, dst = walk(SRC), walk(TARGET)
    add = sorted(set(src) - set(dst))
    delete = sorted(set(dst) - set(src))
    modify = [rel for rel in sorted(set(src) & set(dst))
              if norm_sha(src[rel]) != norm_sha(dst[rel])]
    return {"add": add, "modify": modify, "delete": delete}


def git_dirty() -> dict:
    """目标 repo 脏文件：相对路径(posix) → 状态码。`-z` 避免中文路径被引号包裹。"""
    try:
        raw = subprocess.run(["git", "-C", str(TARGET_REPO), "status",
                              "--porcelain", "-z"],
                             capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"[警告] 读不到 git 状态（{exc}）——守卫按'全干净'处理，风险自负")
        return {}
    out, entries = {}, [e for e in raw.split(b"\x00") if e]
    i = 0
    while i < len(entries):
        e = entries[i]
        code = e[:2].decode("ascii", "replace")
        path = e[3:].decode("utf-8", "replace")
        out[path] = code
        if code[:1] in ("R", "C"):
            i += 1          # 重命名/复制在 -z 下多占一个 NUL 字段（原路径）
        i += 1
    return out


def load_manifest() -> dict:
    if not MANIFEST.is_file():
        return {}
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_manifest(note: str, *, from_target: bool = False) -> None:
    root = TARGET if from_target else SRC
    files = {rel: norm_sha(p) for rel, p in walk(root).items()}
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps({
        "note": note,
        "recorded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "recorded_from": str(root),
        "source": str(SRC),
        "target": str(TARGET),
        "file_count": len(files),
        "files": files,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[基线] 已刷新 {MANIFEST}（{len(files)} 个文件）")


def guard(delta: dict, dirty: dict, manifest: dict) -> list:
    """返回阻挡项 [(原因, 相对路径, 细节)]。"""
    blocked = []
    prev = manifest.get("files") or {}
    for kind in ("modify", "delete"):
        for rel in delta[kind]:
            code = dirty.get(SCOPE + rel)
            if code:
                blocked.append(("目标未提交（git 脏，覆盖即丢失）", rel, code))
                continue
            want = prev.get(rel)
            if want is None:
                if manifest:
                    blocked.append(("无部署基线记录", rel, "清单里没有它；先看清楚这个差异从哪来"))
                continue
            got = norm_sha(TARGET / rel) if (TARGET / rel).is_file() else ""
            if got != want:
                blocked.append(("目标自上次发布后被改过（可能有别的写入者）", rel,
                                f"基线 {want[:12]} ≠ 现值 {got[:12]}"))
    return blocked


def report(delta: dict, blocked: list, dirty: dict, manifest: dict) -> None:
    print(f"[源]   {SRC}")
    print(f"[目标] {TARGET}")
    print(f"[基线] {MANIFEST if manifest else '（尚无清单——本次按首次发布处理，只做脏文件守卫）'}")
    print(f"[差异] 新增 {len(delta['add'])} / 修改 {len(delta['modify'])} / 删除 {len(delta['delete'])}")
    for kind, mark in (("add", "+"), ("modify", "M"), ("delete", "-")):
        for rel in delta[kind][:200]:
            print(f"   {mark} {rel}")
        if len(delta[kind]) > 200:
            print(f"   … 另有 {len(delta[kind]) - 200} 条")
    touched = {SCOPE + r for k in ("add", "modify", "delete") for r in delta[k]}
    untouched = sorted(set(dirty) - touched)
    if untouched:
        print(f"\n[提示] 目标有 {len(untouched)} 个脏文件**不在**本次范围内，不会被触碰：")
        for rel in untouched[:15]:
            print(f"   · {rel}  ({dirty[rel]})")
        if len(untouched) > 15:
            print(f"   … 另有 {len(untouched) - 15} 条")
    if blocked:
        print(f"\n[阻挡] {len(blocked)} 个文件不能安全覆盖：")
        for why, rel, detail in blocked:
            print(f"   ✗ {rel}")
            print(f"       原因：{why}（{detail}）")
        print("\n   → 默认拒绝执行。三条出路：")
        print("      · 改动属于别人/未提交 → 先让人提交或备份，再来发布")
        print("      · 确认可以覆盖         → 加 --force")
        print("      · 确认目标领先是正常的 → 加 --adopt 把现状登记为新基线")


def in_target(path: Path) -> bool:
    try:
        path.resolve().relative_to(TARGET.resolve())
        return True
    except ValueError:
        return False


def backport(delta: dict, *, assume_yes: bool) -> int:
    """把目标里较新的内容回流到镜像（E 盘）。回流前**整树备份**镜像侧到
    `_deploy/backport_backup_<时间戳>/`，可原样还原。"""
    rels = delta["modify"] + [r for r in delta["delete"]] + delta["add"]
    if not rels:
        print("[回流] 无差异，无需回流。")
        return 0
    print(f"[回流] 将把 **目标** 的内容写回镜像，涉及 {len(rels)} 个文件：")
    for rel in rels[:200]:
        mark = {"add": "(目标新增→镜像补上)", "modify": "(目标较新→覆盖镜像)",
                "delete": "(镜像多的→删掉)"}
        kind = "modify"
        for k in ("add", "modify", "delete"):
            if rel in delta[k]:
                kind = k
                break
        print(f"   {rel}  {mark[kind]}")
    if len(rels) > 200:
        print(f"   … 另有 {len(rels) - 200} 条")
    if not assume_yes:
        print("\n[中止] 回流会改写镜像侧文件。确认无误后重跑并加 --yes。")
        return 1

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = PKG_ROOT / "_deploy" / f"backport_backup_{stamp}" / "skills" / "energy-audit"
    shutil.copytree(SRC, backup)
    print(f"\n[备份] 镜像侧已整树备份到 {backup}")

    for rel in delta["modify"] + delta["add"]:
        s, d = TARGET / rel, SRC / rel
        if not s.is_file():
            continue
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d)
    removed = 0
    for rel in delta["delete"]:
        d = SRC / rel
        try:
            d.resolve().relative_to(SRC.resolve())
        except ValueError:
            print(f"[拒绝] 删除越界：{d}")
            continue
        if d.is_file():
            d.unlink()
            removed += 1
    print(f"[回流] 镜像侧更新 {len(delta['modify']) + len(delta['add'])} 个文件"
          f"，删除 {removed} 个。")
    write_manifest("回流后基线（镜像与目标已对齐）")
    return 0


def apply_delta(delta: dict, *, mirror: bool) -> int:
    for rel in delta["add"] + delta["modify"]:
        d = TARGET / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SRC / rel, d)
    removed = 0
    for rel in delta["delete"]:
        if not mirror:
            continue
        d = TARGET / rel
        if not in_target(d):
            print(f"[拒绝] 删除目标越界，已跳过：{d}")
            continue
        if d.is_file():
            d.unlink()
            removed += 1
    print(f"\n[发布] 复制 {len(delta['add']) + len(delta['modify'])} 个文件"
          f"，删除 {removed} 个文件（mirror={mirror}）")
    return 0


def run_sync(*extra: str) -> int:
    script = TARGET_REPO / "scripts" / "sync_ea_skills.py"
    if not script.is_file():
        print(f"[跳过] 未找到 {script}")
        return 0
    sys.stdout.flush()      # 否则子进程输出会插到本脚本缓冲输出之前
    return subprocess.run([sys.executable, str(script), *extra]).returncode


def main() -> int:
    _utf8_stdout()
    ap = argparse.ArgumentParser(description="能源审计技能部署（带双写入者守卫）")
    ap.add_argument("--check", action="store_true", help="只报告，不落盘")
    ap.add_argument("--mirror", action="store_true", help="额外删除目标多出来的文件")
    ap.add_argument("--force", action="store_true", help="跳过守卫")
    ap.add_argument("--adopt", action="store_true",
                    help="把当前**目标**状态登记为新基线后退出（承认目标领先）")
    ap.add_argument("--backport", action="store_true",
                    help="把目标里较新的内容回流到镜像（带整树备份）")
    ap.add_argument("--yes", action="store_true", help="配合 --backport：确认执行")
    ap.add_argument("--skip-sync", action="store_true", help="不跑 sync_ea_skills.py")
    args = ap.parse_args()

    if not SRC.is_dir():
        print(f"[错误] 源目录不存在：{SRC}")
        return 1
    if not TARGET.is_dir():
        print(f"[错误] 目标目录不存在：{TARGET}")
        return 1

    manifest = load_manifest()
    if args.adopt:
        print(f"[adopt] 以**当前目标**为基线登记：{TARGET}")
        write_manifest("adopt：以当时的目标状态为基线（承认目标领先）", from_target=True)
        return 0

    delta = diff_tree()
    dirty = git_dirty()

    if args.backport:
        rc = backport(delta, assume_yes=args.yes)
        return rc

    blocked = guard(delta, dirty, manifest)
    report(delta, blocked, dirty, manifest)

    if blocked and not args.force:
        print("\n[中止] 未做任何改动。")
        return 1
    if not any(delta.values()):
        print("\n[结论] 源与目标已一致，无需发布。")
        if not manifest:
            write_manifest("首次登记（源与目标已一致）")
        return 0
    if args.check:
        print("\n[--check] 未做任何改动。")
        return 0

    apply_delta(delta, mirror=args.mirror)
    write_manifest(f"发布后基线（force={args.force}, mirror={args.mirror}）")
    if args.skip_sync:
        return 0
    print("\n=== 发布到 profiles ===")
    rc = run_sync()
    if rc:
        print(f"[错误] sync_ea_skills.py 退出码 {rc}")
        return rc
    print("\n=== 校验 ===")
    return run_sync("--verify")


if __name__ == "__main__":
    sys.exit(main())
