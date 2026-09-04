#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""能源审计技能发布器：repo skills/energy-audit/ → 主 hermes skills + 各 profile skills 单向发布。

用法:
    python scripts/sync_ea_skills.py            # 实际发布（含删除旧位置清理）
    python scripts/sync_ea_skills.py --dry-run  # 只报告差异不落盘
    python scripts/sync_ea_skills.py --verify   # 只校验 hash 一致性并报告

铁律:
    1. repo `skills/energy-audit/` 是唯一权威源（git 管理），本脚本只做单向发布。
    2. 禁止手工改 profile 侧技能后不回 repo——下次发布会覆盖。
    3. 角色安装矩阵与 kanban-energy-audit-orchestrator/references/role-definitions.md 保持一致。
"""
import argparse
import hashlib
import os
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_SRC = os.path.join(REPO, "skills", "energy-audit")
HERMES_HOME = os.path.expanduser("~") + r"\AppData\Local\hermes"
MAIN_SKILLS = os.path.join(HERMES_HOME, "skills", "energy-audit")
PROFILES = ["datacollection", "datava", "caliber", "author", "editor", "knowledger"]

# 角色安装矩阵：skill 目录名 → 需要安装的 profile 列表（全部 skill 都会发布到主 hermes skills）
ROLE_MATRIX = {
    "energy-audit-core": ["datacollection", "datava", "caliber", "author", "editor", "knowledger"],
    "energy-audit-pg-data": ["datacollection", "datava"],
    "energy-audit-report": ["caliber", "author"],
    "energy-audit-report-qa": ["editor"],
    "energy-audit-imitate": ["author"],
    "energy-audit-routing": [],
    "kanban-energy-audit-orchestrator": ["editor"],
    "ea-datacollection": ["datacollection"],
    "ea-validation": ["datava"],
    "ea-calculation": ["caliber", "author"],
    "ea-authoring": ["author"],
}
# knowledger 仅装 energy-audit-core（共享口径），其专属 knowledge-tools /
# structured-document-rag 在 profile 独立分类目录（sync 不管理，勿在此矩阵声明）

# 主目录旧位置清理清单（迁移后遗留的 productivity/ 下旧副本）
MAIN_STALE = [
    os.path.join(HERMES_HOME, "skills", "productivity", "energy-audit-imitate"),
    os.path.join(HERMES_HOME, "skills", "productivity", "energy-audit-pg-data"),
    os.path.join(HERMES_HOME, "skills", "productivity", "energy-audit-report-qa"),
    os.path.join(HERMES_HOME, "skills", "productivity", "energy-audit-reports"),
    os.path.join(HERMES_HOME, "skills", "energy-audit-report"),
]
# profile 旧位置清理清单（旧命名 skill）
PROFILE_STALE = {
    "datacollection": ["data_collection"],
    "datava": ["data_validation"],
    "caliber": ["indicator_calculation", "agent-caliber"],
    "author": ["agent-xiaode", "agent-author"],
    "editor": ["agent-editor"],
}

SKIP_NAMES = {"__pycache__", ".omc", ".pytest_cache", ".git", ".hub", ".curator_backups"}


def walk_files(root):
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_NAMES]
        for f in filenames:
            full = os.path.join(dirpath, f)
            out[os.path.relpath(full, root).replace("\\", "/")] = full
    return out


def md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()


def copy_tree(src, dst, dry_run=False):
    """复制目录；返回 (新增/覆盖数, 删除数)。"""
    changed, removed = 0, 0
    src_files = walk_files(src)
    if os.path.isdir(dst):
        dst_files = walk_files(dst)
        for rel in dst_files:
            if rel not in src_files:
                if not dry_run:
                    os.remove(dst_files[rel])
                removed += 1
    for rel, sp in src_files.items():
        dp = os.path.join(dst, rel.replace("/", os.sep))
        if os.path.exists(dp) and md5(dp) == md5(sp):
            continue
        changed += 1
        if not dry_run:
            os.makedirs(os.path.dirname(dp), exist_ok=True)
            shutil.copy2(sp, dp)
    return changed, removed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    if not os.path.isdir(SKILLS_SRC):
        print(f"[错误] 权威源不存在: {SKILLS_SRC}")
        sys.exit(1)

    skills = sorted(os.listdir(SKILLS_SRC))
    unknown = [s for s in skills if s not in ROLE_MATRIX]
    if unknown:
        print(f"[警告] 权威源中存在矩阵外 skill（不会发布到 profile）: {unknown}")

    total_changed, total_removed = 0, 0

    # 1) 发布到主 hermes skills/energy-audit/
    print("== 主 hermes skills/energy-audit/ ==")
    for s in skills:
        changed, removed = copy_tree(os.path.join(SKILLS_SRC, s),
                                     os.path.join(MAIN_SKILLS, s), args.dry_run)
        total_changed += changed
        total_removed += removed
        flag = "dry-run" if args.dry_run else "发布"
        print(f"  [{flag}] {s}: 变更{changed} 删除{removed}")

    # 2) 清理主目录旧位置
    for stale in MAIN_STALE:
        if os.path.isdir(stale):
            print(f"  [清理] 主目录旧位置: {stale}")
            if not args.dry_run:
                shutil.rmtree(stale)
    # 2b) 清理主目录 energy-audit/ 下矩阵外残留（如已合并删除的 energy-audit-reports）
    if os.path.isdir(MAIN_SKILLS):
        for d in os.listdir(MAIN_SKILLS):
            if d not in skills and d not in SKIP_NAMES:
                p = os.path.join(MAIN_SKILLS, d)
                print(f"  [清理] 主目录矩阵外残留: {d}")
                if not args.dry_run:
                    shutil.rmtree(p)

    # 3) 按矩阵发布到 profiles
    for prof in PROFILES:
        prof_skills = os.path.join(HERMES_HOME, "profiles", prof, "skills", "energy-audit")
        print(f"== profile: {prof} ==")
        if not os.path.isdir(os.path.join(HERMES_HOME, "profiles", prof)):
            print(f"  [跳过] profile 不存在")
            continue
        for s, profs in ROLE_MATRIX.items():
            if prof not in profs:
                continue
            changed, removed = copy_tree(os.path.join(SKILLS_SRC, s),
                                         os.path.join(prof_skills, s), args.dry_run)
            total_changed += changed
            total_removed += removed
            flag = "dry-run" if args.dry_run else "发布"
            print(f"  [{flag}] {s}: 变更{changed} 删除{removed}")
        # 清理旧命名 skill
        for stale in PROFILE_STALE.get(prof, []):
            p = os.path.join(HERMES_HOME, "profiles", prof, "skills", stale)
            if os.path.isdir(p):
                print(f"  [清理] {prof} 旧 skill: {stale}")
                if not args.dry_run:
                    shutil.rmtree(p)
        # 清理不在矩阵内的 energy-audit 残留
        if os.path.isdir(prof_skills):
            installed = {s for s, ps in ROLE_MATRIX.items() if prof in ps}
            for d in os.listdir(prof_skills):
                if d not in installed and d not in SKIP_NAMES:
                    p = os.path.join(prof_skills, d)
                    print(f"  [清理] {prof} 矩阵外残留: {d}")
                    if not args.dry_run:
                        shutil.rmtree(p)

    print(f"\n{'[dry-run]' if args.dry_run else '[完成]'} 总变更 {total_changed} 文件，删除 {total_removed} 文件")

    if args.verify or args.dry_run:
        # 校验：全 profile 与 repo hash 一致性
        bad = 0
        for prof in PROFILES:
            prof_skills = os.path.join(HERMES_HOME, "profiles", prof, "skills", "energy-audit")
            if not os.path.isdir(os.path.join(HERMES_HOME, "profiles", prof)):
                # profile 目录不存在（如被移入 .deleted）→ 跳过校验，避免全量误报
                continue
            for s, profs in ROLE_MATRIX.items():
                if prof not in profs:
                    continue
                src = walk_files(os.path.join(SKILLS_SRC, s))
                dst = walk_files(os.path.join(prof_skills, s))
                for rel, sp in src.items():
                    if rel not in dst or md5(dst[rel]) != md5(sp):
                        bad += 1
                        print(f"  [不一致] {prof}/{s}/{rel}")
        print(f"[校验] profile 侧不一致文件: {bad}")
        sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
