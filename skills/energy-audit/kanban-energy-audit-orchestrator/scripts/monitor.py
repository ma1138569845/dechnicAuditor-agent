#!/usr/bin/env python3
"""
能源审计 Kanban 监控器 — 轮询看板并检测问题。

定期拉取 `hermes kanban list` 和 `events`，发现：
- 卡住的任务（心跳超时）
- 超时任务（超过 max_runtime）
- 反复重试的任务
- 阻塞任务堆积

用法:
    monitor.py --tenant <project-slug> [--interval 30] [--once]

每轮输出快照到 stdout。检测到问题时输出告警到 stderr。
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta

_IS_WINDOWS = sys.platform == "win32"


def hermes_available() -> bool:
    return shutil.which("hermes") is not None


def kanban_list(tenant: str) -> list[dict]:
    """拉取某 tenant 的所有任务。"""
    try:
        out = subprocess.run(
            ["hermes", "kanban", "list", "--tenant", tenant, "--json"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", check=False, shell=_IS_WINDOWS,
        )
        if out.returncode == 0 and out.stdout.strip().startswith("["):
            return json.loads(out.stdout)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # 降级: 文本解析
    out = subprocess.run(
        ["hermes", "kanban", "list", "--tenant", tenant],
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", check=False, shell=_IS_WINDOWS,
    )
    rows = []
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 3:
            rows.append({
                "id": parts[0],
                "status": parts[1] if len(parts) > 1 else "?",
                "assignee": parts[2] if len(parts) > 2 else "?",
                "title": " ".join(parts[3:]) if len(parts) > 3 else "",
                "heartbeat_at": None,
                "max_runtime_s": None,
                "retries": 0,
            })
    return rows


def kanban_show(task_id: str) -> dict | None:
    """获取单个任务详情。"""
    out = subprocess.run(
        ["hermes", "kanban", "show", task_id, "--json"],
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", check=False, shell=_IS_WINDOWS,
    )
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        return None


def detect_issues(tasks: list[dict]) -> list[dict]:
    """检测看板中的问题。

    每项 issue 格式:
      {severity, category, task_id, assignee, message, detail}
    """
    now = datetime.now()
    issues: list[dict] = []

    by_status: dict[str, list] = defaultdict(list)
    for t in tasks:
        by_status[str(t.get("status", "?")).lower()].append(t)

    # 1. 卡住: RUNNING 但无心跳 > 5 分钟
    for t in by_status.get("running", []):
        hb = t.get("heartbeat_at")
        if not hb:
            issues.append({
                "severity": "warning",
                "category": "no_heartbeat",
                "task_id": t["id"],
                "assignee": t.get("assignee", "?"),
                "message": f'{t["id"]} 运行中但无心跳（可能已死）',
                "detail": f'启动时间: {t.get("started_at", "?")}',
            })
            continue
        try:
            hb_dt = datetime.fromisoformat(str(hb).rstrip("Z"))
            gap = (now - hb_dt).total_seconds()
        except ValueError:
            continue
        if gap > 300:  # 5 分钟
            issues.append({
                "severity": "error",
                "category": "heartbeat_timeout",
                "task_id": t["id"],
                "assignee": t.get("assignee", "?"),
                "message": f'{t["id"]} 心跳超时 {gap:.0f}s',
                "detail": f'最后心跳: {hb}',
            })

    # 2. 超时
    for t in by_status.get("running", []):
        started = t.get("started_at")
        max_rt = t.get("max_runtime_s")
        if not started or not max_rt:
            continue
        try:
            started_dt = datetime.fromisoformat(str(started).rstrip("Z"))
            elapsed = (now - started_dt).total_seconds()
        except ValueError:
            continue
        if elapsed > int(max_rt):
            issues.append({
                "severity": "error",
                "category": "overtime",
                "task_id": t["id"],
                "assignee": t.get("assignee", "?"),
                "message": f'{t["id"]} 超时 — 运行 {elapsed:.0f}s, 上限 {max_rt}s',
                "detail": "",
            })

    # 3. 反复重试
    for t in tasks:
        retries = t.get("retries", 0)
        if retries >= 2:
            issues.append({
                "severity": "warning",
                "category": "flapping",
                "task_id": t["id"],
                "assignee": t.get("assignee", "?"),
                "message": f'{t["id"]} 已重试 {retries} 次',
                "detail": f'建议排查根因后 reclaim',
            })

    # 4. 阻塞堆积
    blocked = by_status.get("blocked", [])
    blocked_without_comment = 0
    for t in blocked:
        # 简单检测：看是否有 comment
        detail = kanban_show(t["id"])
        if detail:
            comments = detail.get("comments", [])
            if not comments:
                blocked_without_comment += 1

    if len(blocked) >= 5:
        issues.append({
            "severity": "warning",
            "category": "blocked_pileup",
            "task_id": "N/A",
            "assignee": "N/A",
            "message": f'{len(blocked)} 个任务处于 blocked 状态',
            "detail": f'其中 {blocked_without_comment} 个无评论说明',
        })

    return issues


def snapshot(tenant: str) -> tuple[list[dict], list[dict]]:
    tasks = kanban_list(tenant)
    issues = detect_issues(tasks)
    return tasks, issues


def print_snapshot(tasks: list[dict], issues: list[dict]) -> None:
    # 计数统计
    counts: dict[str, int] = defaultdict(int)
    for t in tasks:
        s = str(t.get("status", "?")).lower()
        counts[s] += 1

    total = len(tasks)
    done = counts.get("done", 0)
    running = counts.get("running", 0)
    ready = counts.get("ready", 0)
    blocked = counts.get("blocked", 0)
    failed = counts.get("failed", 0)
    todo = counts.get("todo", 0)

    pct = f"{done}/{total} ({done*100//total}%)" if total else "0"
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] "
          f"完成 {pct} | ▶{running} ●{ready} ⏸{blocked} ✗{failed} □{todo}")

    # 问题
    if issues:
        print(f"\n  ⚠ 发现问题 ({len(issues)} 项):")
        for iss in issues:
            icon = {"error": "🔴", "warning": "🟡"}.get(iss["severity"], "⚪")
            print(f"     {icon} [{iss['category']}] {iss['message']}")
            if iss.get("detail"):
                print(f"          {iss['detail']}")

    # 快速摘要（只显示 running 和 blocked）
    running_tasks = [t for t in tasks if str(t.get("status", "")).lower() == "running"]
    if running_tasks:
        print(f"\n  ▶ 正在运行 ({len(running_tasks)}):")
        for t in running_tasks[:10]:
            print(f"       {t['id']:14} {t.get('assignee','?'):20} {t.get('title','')[:60]}")

    blocked_tasks = [t for t in tasks if str(t.get("status", "")).lower() == "blocked"]
    if blocked_tasks:
        print(f"\n  ⏸ 阻塞 ({len(blocked_tasks)}):")
        for t in blocked_tasks[:5]:
            print(f"       {t['id']:14} {t.get('assignee','?'):20} {t.get('title','')[:60]}")

    if not running_tasks and not blocked_tasks and total == done:
        print(f"\n  🎉 全部完成！")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--tenant", required=True, help="项目 tenant slug")
    ap.add_argument("--interval", type=int, default=30, help="轮询间隔秒数 (默认 30)")
    ap.add_argument("--once", action="store_true", help="仅输出一次快照")
    args = ap.parse_args()

    if not hermes_available():
        print("✗ 'hermes' CLI 不可用", file=sys.stderr)
        print("  请确保 hermes 在 PATH 中", file=sys.stderr)
        return 1

    if args.once:
        tasks, issues = snapshot(args.tenant)
        print_snapshot(tasks, issues)
        return 2 if issues else 0

    print(f"🔍 监控 tenant '{args.tenant}'，每 {args.interval}s. Ctrl-C 退出。")
    try:
        while True:
            tasks, issues = snapshot(args.tenant)
            print_snapshot(tasks, issues)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n⏹ 已停止")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
