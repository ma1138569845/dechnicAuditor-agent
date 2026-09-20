#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""能源审计技能部署器（带双写入者守卫）—— 2026-09-20 建，同日两次升级

## 为什么有这个东西

2026-09-20 事故：用 `robocopy /MIR` 把技能包镜像**整体**覆盖到 D 盘
`skills/energy-audit`，抹掉了目标侧未提交改动，git 层面无法恢复。
同日稍后发现：**D 盘 repo 有第二个写入者**（另一会话在同一分支连续提交），
所以 D 盘可能既"脏"又"领先于镜像"。

`/MIR` 有两个致命属性，本脚本各治一条：
  1. 不看目标有没有未提交改动 → **脏文件守卫**：任何将被覆盖/删除、且 git 脏的
     目标文件，直接阻挡。
  2. 不看内容是不是别人新写的 → **部署基线清单**：只允许覆盖"自上次发布以来没被
     动过"的目标文件（内容 == 上次发布时记下的哈希）。对不上 = 有人在目标侧改了
     东西 → 阻挡，交给人裁决。

## 管三棵树（2026-09-20 第二次升级）

镜像是"技能包"，但除 `skills/energy-audit/` 外还带了两个小树。此前它们不在
守卫范围内 → 会**静默落后**（实测 `tools/energy_audit/pg_collector.py` 落后 3 个提交）。

| 范围 | 语义 | 目标多出来的文件 |
|---|---|---|
| `skills/energy-audit` | **完整镜像**（镜像就是全量） | `--mirror` 时删除（仍受守卫） |
| `scripts/` | **子集同步**（只覆盖镜像里有的文件） | **永不删除**（repo 有 90+ 个镜像不带） |
| `tools/` | 同上（镜像只带 `energy_audit/` 的 3 个） | **永不删除** |

内容比对标**行尾归一化**（镜像 CRLF / 检出 LF，不归一化会误报一批文件）。

## 用法

    python scripts/deploy_ea_skills.py --check        # 只报告，不落盘（**永远先跑**）
    python scripts/deploy_ea_skills.py               # 外科式发布（默认）
    python scripts/deploy_ea_skills.py --mirror      # 额外删除 skills 树里目标多出的文件
    python scripts/deploy_ea_skills.py --force       # 跳过守卫
    python scripts/deploy_ea_skills.py --adopt       # 把当前目标状态登记为新基线
    python scripts/deploy_ea_skills.py --backport --yes
                                                     # 反向：目标领先 → 回流到镜像（自动备份）
    python scripts/deploy_ea_skills.py --backport --yes --scope tools
                                                     # 只回流某个范围

> ⚠️ **回流方向的陷阱**：`--backport` 是"目标 → 镜像"。如果**镜像侧正在改同一个
> 文件**（比如你刚改好发布器还没发布），回流会拿目标的旧版把它覆盖掉。
> 所以：回流前先跑 `--check` 看清每个文件谁新谁旧；不确定就用 `--scope` 只回流
> 你确定目标领先的那棵树（本次实测就靠 `--scope tools` 躲过一次）。

发布成功后刷新基线 `repo/_deploy/last_deploy.json`，再调用
`sync_ea_skills.py` 发布到 profiles，并跑一次 `--verify`。

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
MANIFEST = Path(os.environ.get("EA_DEPLOY_MANIFEST")
                or (PKG_ROOT / "_deploy" / "last_deploy.json"))
TARGET_REPO = Path(os.environ.get("EA_TARGET_REPO")
                   or r"D:\data\pyProject\dc_agent\dechnicAuditor-agent")

# (范围, 是否允许删除目标多出的文件)
SCOPES = (
    ("skills/energy-audit", True),      # 完整镜像：这里是技能主体
    ("scripts", False),                 # 子集：发布器本体
    ("tools", False),                   # 子集：skills 引用的实现文件
)

SKIP_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
SKIP_SUFFIX = {".pyc", ".pyo"}
SKIP_NAMES = {".DS_Store", "Thumbs.db"}


def _utf8_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass


def norm_sha(path: Path) -> str:
    """内容哈希，**行尾统一为 LF**：镜像与检出的行尾不同（CRLF vs LF），
    不归一化会把一批文件误报成"已修改"。"""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


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


def scan() -> dict:
    """{范围: {"add": [...], "modify": [...], "delete": [...]}}（相对路径为范围内的相对路径）"""
    result: dict = {}
    for scope, _allow_del in SCOPES:
        src, dst = walk(PKG_ROOT / scope), walk(TARGET_REPO / scope)
        add = sorted(set(src) - set(dst))
        delete = sorted(set(dst) - set(src))
        modify = [rel for rel in sorted(set(src) & set(dst))
                  if norm_sha(src[rel]) != norm_sha(dst[rel])]
        result[scope] = {"add": add, "modify": modify, "delete": delete}
    return result


def git_dirty() -> dict:
    """目标 repo 脏文件：仓库相对路径(posix) → 状态码。`-z` 避免中文路径被引号包裹。"""
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
        out[e[3:].decode("utf-8", "replace")] = code
        i += 2 if code[:1] in ("R", "C") else 1   # 重命名/复制多占一个字段
    return out


def load_manifest() -> dict:
    if not MANIFEST.is_file():
        return {}
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_manifest(note: str, *, from_target: bool = False) -> None:
    root = TARGET_REPO if from_target else PKG_ROOT
    files = {}
    for scope, _ in SCOPES:
        for rel, p in walk(root / scope).items():
            files[f"{scope}/{rel}"] = norm_sha(p)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps({
        "note": note,
        "recorded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "recorded_from": str(root),
        "package": str(PKG_ROOT),
        "target": str(TARGET_REPO),
        "scopes": [s for s, _ in SCOPES],
        "file_count": len(files),
        "files": files,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[基线] 已刷新 {MANIFEST}（{len(files)} 个文件，{len(SCOPES)} 个范围）")


def guard(scanned: dict, dirty: dict, manifest: dict) -> list:
    """返回阻挡项 [(原因, 范围, 相对路径, 细节)]。"""
    blocked, prev = [], (manifest.get("files") or {})
    for scope, allow_del in SCOPES:
        kinds = ("modify", "delete") if allow_del else ("modify",)
        for kind in kinds:
            for rel in scanned[scope][kind]:
                key = f"{scope}/{rel}"
                code = dirty.get(key)
                if code:
                    blocked.append(("目标未提交（git 脏，覆盖即丢失）", scope, rel, code))
                    continue
                want = prev.get(key)
                if want is None:
                    if manifest:
                        blocked.append(("无部署基线记录", scope, rel,
                                        "清单里没有它；先看清楚这个差异从哪来"))
                    continue
                got = norm_sha(TARGET_REPO / key) if (TARGET_REPO / key).is_file() else ""
                if got != want:
                    blocked.append(("目标自上次发布后被改过（可能有别的写入者）",
                                    scope, rel, f"基线 {want[:12]} ≠ 现值 {got[:12]}"))
    return blocked


def report(scanned: dict, blocked: list, dirty: dict, manifest: dict) -> None:
    print(f"[镜像] {PKG_ROOT}")
    print(f"[目标] {TARGET_REPO}")
    print(f"[基线] {MANIFEST if manifest else '（尚无清单——按首次发布处理，只做脏文件守卫）'}")
    total = 0
    for scope, allow_del in SCOPES:
        d = scanned[scope]
        n = len(d["add"]) + len(d["modify"]) + (len(d["delete"]) if allow_del else 0)
        total += n
        print(f"\n--- {scope}（{'完整镜像' if allow_del else '子集同步，不删目标多出的'}）---"
              f"  新增 {len(d['add'])} / 修改 {len(d['modify'])}"
              f" / 目标多出 {len(d['delete'])}{'' if allow_del else '（本范围不处理）'}")
        for kind, mark in (("add", "+"), ("modify", "M")):
            for rel in d[kind][:200]:
                print(f"   {mark} {rel}")
        if allow_del:
            for rel in d["delete"][:200]:
                print(f"   - {rel}")
    print(f"\n[差异] 合计需处理 {total} 个文件")

    touched = {f"{scope}/{r}" for scope, _ in SCOPES
               for k in ("add", "modify", "delete") for r in scanned[scope][k]}
    untouched = sorted(set(dirty) - touched)
    if untouched:
        print(f"\n[提示] 目标有 {len(untouched)} 个脏文件**不在**本次范围内，不会被触碰：")
        for rel in untouched[:10]:
            print(f"   · {rel}  ({dirty[rel]})")
        if len(untouched) > 10:
            print(f"   … 另有 {len(untouched) - 10} 条")
    if blocked:
        print(f"\n[阻挡] {len(blocked)} 个文件不能安全覆盖：")
        for why, scope, rel, detail in blocked:
            print(f"   ✗ [{scope}] {rel}")
            print(f"       原因：{why}（{detail}）")
        print("\n   → 默认拒绝执行。三条出路：")
        print("      · 改动属于别人/未提交 → 先让人提交或备份，再来发布")
        print("      · 确认可以覆盖         → 加 --force")
        print("      · 确认目标领先是正常的 → 加 --adopt 把现状登记为新基线")


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def backport(scanned: dict, *, assume_yes: bool, only: tuple = ()) -> int:
    """目标较新 → 回流到镜像。回流前**整包备份**镜像侧涉及范围，可原样还原。

    only 非空时只处理这些范围（--scope）；用于"只有某棵树目标领先"的场景，
    避免把镜像侧正在编辑的文件覆盖掉。
    """
    jobs = []
    for scope, allow_del in SCOPES:
        if only and scope not in only:
            continue
        d = scanned[scope]
        for rel in d["modify"] + d["add"]:
            jobs.append((scope, rel, "覆盖镜像" if rel in d["modify"] else "镜像补上"))
        if allow_del:
            for rel in d["delete"]:
                jobs.append((scope, rel, "删掉镜像内多余"))
    if not jobs:
        print("[回流] 无差异，无需回流。")
        return 0
    print(f"[回流] 将把 **目标** 的内容写回镜像，涉及 {len(jobs)} 个文件：")
    for scope, rel, what in jobs[:200]:
        print(f"   [{scope}] {rel}  ({what})")
    if len(jobs) > 200:
        print(f"   … 另有 {len(jobs) - 200} 条")
    if not assume_yes:
        print("\n[中止] 回流会改写镜像侧文件。确认无误后重跑并加 --yes。")
        return 1

    active = [s for s, _ in SCOPES if not only or s in only]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = PKG_ROOT / "_deploy" / f"backport_backup_{stamp}"
    for scope in active:
        src = PKG_ROOT / scope
        if src.is_dir():
            shutil.copytree(src, backup / scope)
    print(f"\n[备份] 镜像侧涉及范围已整树备份到 {backup}")

    copied = removed = 0
    for scope, rel, what in jobs:
        tgt = PKG_ROOT / scope / rel
        if what == "删掉镜像内多余":
            if _inside(tgt, PKG_ROOT / scope) and tgt.is_file():
                tgt.unlink()
                removed += 1
            continue
        src = TARGET_REPO / scope / rel
        if src.is_file():
            tgt.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, tgt)
            copied += 1
    print(f"[回流] 镜像更新 {copied} 个文件，删除 {removed} 个。")
    # 基线语义是"目标在上次同步时的样子"，所以回流后要按**目标**记，
    # 否则镜像侧领先的文件（本次就有一个：刚改好的发布器）会被误判成"目标被别人改过"。
    write_manifest("回流后基线（按目标状态记）", from_target=True)
    return 0


def apply_delta(scanned: dict) -> int:
    copied = removed = 0
    for scope, allow_del in SCOPES:
        d = scanned[scope]
        for rel in d["add"] + d["modify"]:
            tgt = TARGET_REPO / scope / rel
            tgt.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(PKG_ROOT / scope / rel, tgt)
            copied += 1
        if allow_del:
            for rel in d["delete"]:
                tgt = TARGET_REPO / scope / rel
                if not _inside(tgt, TARGET_REPO / scope):
                    print(f"[拒绝] 删除越界，已跳过：{tgt}")
                    continue
                if tgt.is_file():
                    tgt.unlink()
                    removed += 1
    print(f"\n[发布] 复制 {copied} 个文件，删除 {removed} 个文件")
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
    ap.add_argument("--mirror", action="store_true",
                    help="额外删除 skills 树里目标多出的文件（scripts/tools 永不删除）")
    ap.add_argument("--force", action="store_true", help="跳过守卫")
    ap.add_argument("--adopt", action="store_true",
                    help="把当前**目标**状态登记为新基线后退出")
    ap.add_argument("--backport", action="store_true",
                    help="把目标里较新的内容回流到镜像（带整树备份）")
    ap.add_argument("--yes", action="store_true", help="配合 --backport：确认执行")
    ap.add_argument("--scope", action="append", default=[],
                    choices=[s for s, _ in SCOPES], help="限定范围（可重复，默认全部）")
    ap.add_argument("--skip-sync", action="store_true", help="不跑 sync_ea_skills.py")
    args = ap.parse_args()

    for scope, _ in SCOPES:
        if not (PKG_ROOT / scope).is_dir():
            print(f"[错误] 镜像范围不存在：{PKG_ROOT / scope}")
            return 1
    if not TARGET_REPO.is_dir():
        print(f"[错误] 目标不存在：{TARGET_REPO}")
        return 1

    manifest = load_manifest()
    if args.adopt:
        print(f"[adopt] 以**当前目标**为基线登记：{TARGET_REPO}")
        write_manifest("adopt：以当时的目标状态为基线（承认目标领先）", from_target=True)
        return 0

    scanned = scan()
    dirty = git_dirty()

    if args.backport:
        return backport(scanned, assume_yes=args.yes, only=tuple(args.scope))

    blocked = guard(scanned, dirty, manifest)
    report(scanned, blocked, dirty, manifest)

    if blocked and not args.force:
        print("\n[中止] 未做任何改动。")
        return 1
    if not any(any(scanned[s][k] for k in ("add", "modify", "delete")) for s, _ in SCOPES):
        print("\n[结论] 镜像与目标已一致，无需发布。")
        if not manifest:
            write_manifest("首次登记（镜像与目标已一致）")
        return 0
    if args.check:
        print("\n[--check] 未做任何改动。")
        return 0

    apply_delta(scanned)
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
