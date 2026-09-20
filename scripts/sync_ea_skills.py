#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""能源审计技能发布器：repo skills/energy-audit/ → 主 hermes skills + 各 profile skills 单向发布。

用法:
    python scripts/sync_ea_skills.py            # 实际发布（含删除旧位置清理）
    python scripts/sync_ea_skills.py --dry-run  # 只报告差异不落盘
    python scripts/sync_ea_skills.py --verify   # 只读校验：待发布差异 + hash 一致性（exit 非 0 = 未对齐）

铁律:
    1. 本脚本是发布链的**第二级**：repo `skills/energy-audit/` → 主库 + 6 角色 profile，单向发布。
       上游（第一级）是**技能包镜像**，由 `deploy_ea_skills.py` 发布到 repo；
       权威源是镜像（2026-09-20 决定 A，见 `deployment-ops.md` 第四节）。**禁用 `robocopy /MIR`**。
    2. 禁止手工改 profile 侧技能后不回 repo——下次发布会覆盖。
    3. 角色安装矩阵与 kanban-energy-audit-orchestrator/references/role-definitions.md 保持一致。
"""
import argparse
import hashlib
import os
import re
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_SRC = os.path.join(REPO, "skills", "energy-audit")
HERMES_HOME = os.environ.get("EA_HERMES_HOME") or (os.path.expanduser("~") + r"\AppData\Local\hermes")
MAIN_SKILLS = os.path.join(HERMES_HOME, "skills", "energy-audit")
PROFILES = ["datacollection", "datava", "caliber", "author", "editor", "knowledger"]

# SOUL 源（2026-09-17 新增）：repo skills/energy-audit/_soul/<role>.md → profiles/<role>/SOUL.md
# 背景：SOUL 此前只存在于 profile 侧、无 repo 源，长期漂移（如 caliber SOUL 仍写"4 项指标"）。
# 环境变量 EA_HERMES_HOME 仅用于沙箱验收：不设时行为与旧版完全一致（仍指向 %LOCALAPPDATA%\hermes）。
SOUL_SRC = os.path.join(SKILLS_SRC, "_soul")
SOUL_ROLES = PROFILES

# 角色安装矩阵：skill 目录名 → 需要安装的 profile 列表（全部 skill 都会发布到主 hermes skills）
ROLE_MATRIX = {
    "energy-audit-core": ["datacollection", "datava", "caliber", "author", "editor", "knowledger"],
    "energy-audit-pg-data": ["datacollection", "datava"],
    "energy-audit-report": ["caliber", "author"],
    "energy-audit-report-qa": ["editor"],
    "energy-audit-imitate": ["author"],
    "energy-audit-style": ["author", "editor"],
    "energy-audit-style-extractor": [],
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

# `_` 前缀目录（_soul / _archive）是仓库内部件，不是技能，发布与清理一律跳过
SKIP_NAMES = {"__pycache__", ".omc", ".pytest_cache", ".git", ".hub", ".curator_backups",
              "_soul", "_archive"}


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


# ── 元数据合规轻量检查（2026-09-20 新增）────────────────────────────────────
# 与 tests/skills/test_authoring_standards.py 的机械规则对齐：描述≤60字符、ASCII 句点、
# 无营销词；六必填字段；tags 非空。纯正则实现，不引入 yaml 依赖；仅告警不阻断发布。
REQUIRED_FIELDS = ("name", "description", "version", "author", "license", "platforms")
MARKETING = re.compile(
    r"\b(powerful|comprehensive|seamless|revolutionary|cutting-edge|state-of-the-art)\b", re.I
)


def check_skill_meta(skill_dir):
    """技能目录的元数据合规检查；返回问题列表（空 = 合规）。"""
    p = os.path.join(skill_dir, "SKILL.md")
    try:
        text = open(p, encoding="utf-8").read()
    except OSError:
        return ["SKILL.md 不可读"]
    m = re.search(r"^---\s*$(.*?)^---\s*$", text, re.M | re.S)
    if not m:
        return ["frontmatter 无法解析"]
    fm = m.group(1)
    problems = []
    dm = re.search(r"^description:\s*(.+?)\s*$", fm, re.M)
    if not dm:
        problems.append("缺 description")
    else:
        desc = dm.group(1).strip().strip('"').strip("'")
        if len(desc) > 60:
            problems.append(f"description 超60字符({len(desc)})")
        if not desc.rstrip().endswith("."):
            problems.append("description 未以句点结尾")
        mm = MARKETING.search(desc)
        if mm:
            problems.append(f"description 含营销词 {mm.group(0)}")
    for f in REQUIRED_FIELDS:
        if not re.search(r"^%s:\s*\S" % f, fm, re.M):
            problems.append(f"缺字段 {f}")
    if not re.search(r"^\s*tags:\s*\[?[^\s\]]", fm, re.M):
        problems.append("缺 tags")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    if not os.path.isdir(SKILLS_SRC):
        print(f"[错误] 权威源不存在: {SKILLS_SRC}")
        sys.exit(1)

    skills = sorted(
        d for d in os.listdir(SKILLS_SRC)
        if not d.startswith("_") and os.path.isdir(os.path.join(SKILLS_SRC, d))
    )
    unknown = [s for s in skills if s not in ROLE_MATRIX]
    if unknown:
        print(f"[警告] 权威源中存在矩阵外 skill（不会发布到 profile）: {unknown}")

    # 元数据合规轻量检查（提示不阻断）：与 test_authoring_standards 规则对齐
    noncompliant = [(s, check_skill_meta(os.path.join(SKILLS_SRC, s))) for s in skills]
    noncompliant = [(s, problem) for s, problem in noncompliant if problem]
    if noncompliant:
        print("[警告] 技能元数据不合规（跑 tests/skills/test_authoring_standards.py 定位）:")
        for s, problem in noncompliant:
            print(f"  - {s}: {'; '.join(problem)}")
    else:
        print("✓ 技能元数据合规检查通过（描述/字段/tags）")

    total_changed, total_removed = 0, 0

    # 1) 发布到主 hermes skills/energy-audit/
    print("== 主 hermes skills/energy-audit/ ==")
    for s in skills:
        changed, removed = copy_tree(os.path.join(SKILLS_SRC, s),
                                     os.path.join(MAIN_SKILLS, s),
                                     args.dry_run or args.verify)
        total_changed += changed
        total_removed += removed
        flag = "dry-run" if args.dry_run else ("校验" if args.verify else "发布")
        print(f"  [{flag}] {s}: 变更{changed} 删除{removed}")

    # 2) 清理主目录旧位置
    for stale in MAIN_STALE:
        if os.path.isdir(stale):
            print(f"  [清理] 主目录旧位置: {stale}")
            if not (args.dry_run or args.verify):
                shutil.rmtree(stale)
    # 2b) 清理主目录 energy-audit/ 下矩阵外残留（如已合并删除的 energy-audit-reports）
    if os.path.isdir(MAIN_SKILLS):
        for d in os.listdir(MAIN_SKILLS):
            if d not in skills and d not in SKIP_NAMES and not d.startswith("_"):
                p = os.path.join(MAIN_SKILLS, d)
                print(f"  [清理] 主目录矩阵外残留: {d}")
                if not (args.dry_run or args.verify):
                    shutil.rmtree(p)

    # 2c) 发布 SOUL（repo _soul/<role>.md → profiles/<role>/SOUL.md）
    print("== profile SOUL ==")
    if not os.path.isdir(SOUL_SRC):
        print(f"  [警告] 无 SOUL 源目录: {SOUL_SRC}（跳过，不影响技能发布）")
    else:
        for role in SOUL_ROLES:
            src = os.path.join(SOUL_SRC, f"{role}.md")
            prof_dir = os.path.join(HERMES_HOME, "profiles", role)
            dst = os.path.join(prof_dir, "SOUL.md")
            if not os.path.isfile(src):
                print(f"  [缺失] SOUL 源: _soul/{role}.md")
                continue
            if not os.path.isdir(prof_dir):
                print(f"  [跳过] {role}: profile 不存在")
                continue
            if os.path.isfile(dst) and md5(dst) == md5(src):
                continue
            flag = "dry-run" if args.dry_run else ("校验" if args.verify else "发布")
            print(f"  [{flag}] SOUL {role}.md")
            if not (args.dry_run or args.verify):
                shutil.copy2(src, dst)

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
                                         os.path.join(prof_skills, s),
                                         args.dry_run or args.verify)
            total_changed += changed
            total_removed += removed
            flag = "dry-run" if args.dry_run else ("校验" if args.verify else "发布")
            print(f"  [{flag}] {s}: 变更{changed} 删除{removed}")
        # 清理旧命名 skill
        for stale in PROFILE_STALE.get(prof, []):
            p = os.path.join(HERMES_HOME, "profiles", prof, "skills", stale)
            if os.path.isdir(p):
                print(f"  [清理] {prof} 旧 skill: {stale}")
                if not (args.dry_run or args.verify):
                    shutil.rmtree(p)
        # 清理不在矩阵内的 energy-audit 残留
        if os.path.isdir(prof_skills):
            installed = {s for s, ps in ROLE_MATRIX.items() if prof in ps}
            for d in os.listdir(prof_skills):
                if d not in installed and d not in SKIP_NAMES and not d.startswith("_"):
                    p = os.path.join(prof_skills, d)
                    print(f"  [清理] {prof} 矩阵外残留: {d}")
                    if not (args.dry_run or args.verify):
                        shutil.rmtree(p)

    print(f"\n{'[dry-run]' if args.dry_run else ('[校验]' if args.verify else '[完成]')} 总变更 {total_changed} 文件，删除 {total_removed} 文件")

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
        # SOUL 一致性（repo _soul/<role>.md ↔ profiles/<role>/SOUL.md）
        if os.path.isdir(SOUL_SRC):
            for role in SOUL_ROLES:
                prof_dir = os.path.join(HERMES_HOME, "profiles", role)
                if not os.path.isdir(prof_dir):
                    continue
                src = os.path.join(SOUL_SRC, f"{role}.md")
                dst = os.path.join(prof_dir, "SOUL.md")
                if not os.path.isfile(src):
                    bad += 1
                    print(f"  [缺失] SOUL 源: _soul/{role}.md")
                elif not os.path.isfile(dst) or md5(dst) != md5(src):
                    bad += 1
                    print(f"  [不一致] {role}/SOUL.md")
        print(f"[校验] profile 侧不一致文件: {bad}")
        sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
