# -*- coding: utf-8 -*-
"""bootstrap_pipeline 回归验证：最小 plan 实跑 dry-run + 三卡结构断言。

用法:
    python verify_bootstrap_dryrun.py            # 自动生成最小 plan 并断言
    python verify_bootstrap_dryrun.py <setup.sh> # 直接断言已生成的 setup.sh

断言内容（与技能文档口径一致，2026-09-06 PoC 修正后）:
    1. 任务链 = 采集→V1→计算→V2→R1→R2→R3→V3（8 步串行）
    2. 无 1.7 占位符/回填（正式报告第1章仅 1.1~1.6，审计结论为独立第8章）
    3. 章节标题对齐正式报告（公共机构概况 / 能源资源消费/消耗指标分析 /
       主要能源资源利用系统分析 / 节能效果与节能潜力分析）
    4. md 整章导入指令 doc_insert_markdown ×4（卡1×1 卡2×2 卡3×1）
    5. 禁逐段插入铁律覆盖三卡
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_BOOTSTRAP = _HERE / "bootstrap_pipeline.py"

EXPECT_CHAIN = ["T001_C", "T001_V1", "T001_A", "T001_V2",
                "T001_R1", "T001_R2", "T001_R3", "T001_V3"]
EXPECT_TITLES = [
    "公共机构概况",
    "能源资源消费/消耗指标分析",
    "主要能源资源利用系统分析",
    "节能效果与节能潜力分析",
]

MINIMAL_PLAN = {
    "projects": [{
        "name": "测试法院",
        "slug": "test-court",
        "config": str((_HERE.parent.parent.parent.parent
                       / "tools" / "energy_audit" / "chapter5_config_sample.json")),
        "audit_type": "public_institution",
        "institution_category": "党政",
        "audit_years": [2023, 2024, 2025],
    }],
    "profiles": {
        "collector": "datacollection",
        "validator": "datava",
        "calculator": "caliber",
        "reporter": "author",
        "director": "editor",
    },
}


def assert_setup(path: str) -> None:
    s = Path(path).read_text(encoding="utf-8")
    parents = re.findall(r'--parents "\$\{(\w+)\}"', s)
    assert parents == EXPECT_CHAIN, f"任务链错误: {parents}"
    assert "【1.7审计结论" not in s, "1.7 占位符残留"
    assert "回填第1章 1.7" not in s, "1.7 回填职责残留"
    for t in EXPECT_TITLES:
        assert t in s, f"章节标题缺失: {t}"
    assert "1.1~1.6" in s, "第1章范围未写明 1.1~1.6"
    assert s.count("doc_insert_markdown") == 4, f"md 导入指令数={s.count('doc_insert_markdown')}≠4"
    assert s.count("doc_insert_paragraph_with_text") == 2, "禁逐段铁律（工具全名）应 ×2"
    assert s.count("禁逐段") == 3, "禁逐段铁律（简写）应 ×3"
    assert "格式修复链" in s, "格式修复链指令缺失"
    assert "pdf_path" in s, "双文件交付 metadata 缺失"
    # assignee 断言（2026-09-06 定时炸弹修复后）：三卡固定 reporter，Director 用 director
    m_cards = re.findall(r'"报告卡(\d)[^"]*" \\\s+--assignee (\w+)', s)
    assert len(m_cards) == 3 and all(a == "author" for _, a in m_cards), f"三卡 assignee 错误: {m_cards}"
    m_dir = re.findall(r'"\[D\] 汇总[^"]*" \\\s+--assignee (\w+)', s)
    assert m_dir and all(a == "editor" for a in m_dir), f"Director assignee 错误: {m_dir}"
    print(f"  ✓ 任务链: {' -> '.join(parents)}")
    print("  ✓ 无 1.7 占位符/回填；章节标题对齐正式报告；第1章 1.1~1.6")
    print("  ✓ md 导入×4 + 禁逐段铁律 + 格式修复链 + 双文件 metadata")
    print(f"  ✓ assignee: 三卡={[a for _, a in m_cards]}（reporter），Director={m_dir}")


def main() -> int:
    if len(sys.argv) > 1:
        assert_setup(sys.argv[1])
        print("=== bootstrap 结构断言全部通过 ===")
        return 0

    with tempfile.TemporaryDirectory(prefix="bootstrap_verify_") as tmp:
        plan = Path(tmp) / "plan_dryrun.json"
        plan.write_text(json.dumps(MINIMAL_PLAN, ensure_ascii=False), encoding="utf-8")
        setup = Path(tmp) / "setup_dryrun.sh"
        r = subprocess.run(
            [sys.executable, str(_BOOTSTRAP), str(plan), "--out", str(setup)],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            print("bootstrap 失败:", r.stderr[-2000:])
            return 1
        assert_setup(str(setup))
    print("=== bootstrap dry-run 回归验证全部通过 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
