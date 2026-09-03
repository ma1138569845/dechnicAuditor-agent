#!/usr/bin/env python3
"""DataVA 三模式审查 CLI 入口。

用法:
    python data_verification_agent.py <项目名> --mode DATA_CHECK [--no-triage] [--skip-completeness]
    python data_verification_agent.py <项目名> --mode INDICATOR_REVIEW
    python data_verification_agent.py <项目名> --mode REPORT_REVIEW [--report <报告.docx>]

模式别名 V1/V2/V3 与全名等价。通用开关：--json / --quiet / --output-dir。

退出码:
    0  pass / warn   放行
    1  error         输入或依赖缺失
    2  block         存在 P0
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from datava.bootstrap import ensure_tools_on_path  # noqa: E402
from datava.common import SEV_P0, ReviewResult  # noqa: E402

MODE_ALIASES = {
    "DATA_CHECK": "DATA_CHECK",
    "V1": "DATA_CHECK",
    "INDICATOR_REVIEW": "INDICATOR_REVIEW",
    "V2": "INDICATOR_REVIEW",
    "REPORT_REVIEW": "REPORT_REVIEW",
    "V3": "REPORT_REVIEW",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DataVA — 能源审计三模式数据验证审查",
    )
    parser.add_argument("project", help="项目名称（对应 ~/projects/energy-audit/<name>/）")
    parser.add_argument(
        "--mode",
        required=True,
        help="审查模式：DATA_CHECK(V1) / INDICATOR_REVIEW(V2) / REPORT_REVIEW(V3)",
    )
    parser.add_argument("--report", help="V3 显式指定报告 .docx 路径")
    parser.add_argument("--output-dir", help="产出目录（默认 ~/projects/energy-audit/<项目名>/）")
    parser.add_argument("--json", action="store_true", help="机器可读 JSON 输出")
    parser.add_argument("--quiet", action="store_true", help="一行摘要输出")
    parser.add_argument("--no-triage", action="store_true", help="V1 保留人工判定，不做自动分诊")
    parser.add_argument("--skip-completeness", action="store_true", help="V1 跳过完整性检查")
    return parser.parse_args(argv)


def dispatch(args: argparse.Namespace, mode: str) -> ReviewResult:
    if mode == "DATA_CHECK":
        from datava import mode_data_check

        return mode_data_check.run(
            args.project,
            output_dir=args.output_dir,
            skip_completeness=args.skip_completeness,
            triage=not args.no_triage,
        )
    if mode == "INDICATOR_REVIEW":
        from datava import mode_indicator_review

        return mode_indicator_review.run(args.project, output_dir=args.output_dir)

    from datava import mode_report_review

    return mode_report_review.run(
        args.project,
        report=args.report,
        output_dir=args.output_dir,
    )


def quiet_line(result: ReviewResult) -> str:
    counts = result.counts
    line = (
        f"{result.mode} {result.status.upper()} "
        f"P0={counts['P0']} P1={counts['P1']} P2={counts['P2']} "
        f"exit={result.exit_code}"
    )
    if result.error:
        line += f" | error: {result.error}"
    elif result.blocking:
        first_p0 = next((f for f in result.findings if f.severity == SEV_P0), None)
        if first_p0:
            line += f" | P0: {first_p0.title}"
    return line


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    mode = MODE_ALIASES.get(args.mode.upper())
    if mode is None:
        print(f"未知模式: {args.mode}（可选 {sorted(MODE_ALIASES)}）", file=sys.stderr)
        return 1

    # 尽力挂载 tools/energy_audit：V1 必需；V2/V3 缺失时各自降级运行
    _, bootstrap_error = ensure_tools_on_path()
    if bootstrap_error:
        print(f"[DataVA] ⚠️ {bootstrap_error}", file=sys.stderr)

    result = dispatch(args, mode)

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    elif args.quiet:
        print(quiet_line(result))
    else:
        print(result.render_text())

    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
