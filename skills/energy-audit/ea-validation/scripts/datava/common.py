"""三模式共享：Finding / ReviewResult / 路径解析 / IO / 数值工具。

所有数据结构均为 frozen dataclass —— 审查结论一旦生成不再原地修改，
需要变更时用 dataclasses.replace 产生新对象。
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

SCHEMA_VERSION = "2.0.0"

# ── 严重级别 ────────────────────────────────────────────────────
SEV_P0 = "P0"  # 阻塞：数据/逻辑错误，必须修正后重跑
SEV_P1 = "P1"  # 待修：影响报告质量，建议修正
SEV_P2 = "P2"  # 提示：可接受，记录备查

SEV_ORDER: Dict[str, int] = {SEV_P0: 0, SEV_P1: 1, SEV_P2: 2}
SEV_LABEL: Dict[str, str] = {
    SEV_P0: "🔴 P0 阻塞",
    SEV_P1: "🟡 P1 待修",
    SEV_P2: "🔵 P2 提示",
}

# ── 退出码（供上游 Kanban 判断是否 kanban_block）─────────────────
EXIT_OK = 0  # pass / warn —— 可继续流程
EXIT_ERROR = 1  # 执行失败（输入缺失、依赖不可用）
EXIT_BLOCK = 2  # 存在 P0 —— 上游应 kanban_block

STATUS_PASS = "pass"
STATUS_WARN = "warn"
STATUS_BLOCK = "block"
STATUS_ERROR = "error"


@dataclass(frozen=True)
class Finding:
    """一条审查发现。"""

    code: str  # 稳定标识 ex: 'V2.BENCH.EVAL_MISMATCH'
    category: str  # 审查维度 ex: '对标一致性'
    severity: str  # SEV_P0 / SEV_P1 / SEV_P2
    title: str  # 一句话结论
    detail: str = ""  # 证据与推理
    location: str = ""  # 定位 ex: '2023年' / '第5章 5.2' / '段落#182'
    expected: str = ""  # 应为
    actual: str = ""  # 实为
    suggestion: str = ""  # 修正建议

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def sort_findings(findings: Iterable[Finding]) -> List[Finding]:
    """按严重级别升序（P0 在前），同级保持插入顺序。"""
    return sorted(findings, key=lambda f: SEV_ORDER.get(f.severity, 9))


@dataclass(frozen=True)
class ReviewResult:
    """一次审查的完整结论。"""

    mode: str
    project: str
    findings: Tuple[Finding, ...] = ()
    inputs: Dict[str, Any] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)
    artifacts: Dict[str, str] = field(default_factory=dict)
    generated_at: str = ""
    error: str = ""

    # ── 派生属性 ────────────────────────────────────────────
    @property
    def counts(self) -> Dict[str, int]:
        return {
            sev: sum(1 for f in self.findings if f.severity == sev)
            for sev in (SEV_P0, SEV_P1, SEV_P2)
        }

    @property
    def blocking(self) -> bool:
        return bool(self.error) or self.counts[SEV_P0] > 0

    @property
    def status(self) -> str:
        if self.error:
            return STATUS_ERROR
        if self.blocking:
            return STATUS_BLOCK
        return STATUS_WARN if self.counts[SEV_P1] > 0 else STATUS_PASS

    @property
    def exit_code(self) -> int:
        if self.error:
            return EXIT_ERROR
        return EXIT_BLOCK if self.blocking else EXIT_OK

    # ── 序列化 ──────────────────────────────────────────────
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "mode": self.mode,
            "project": self.project,
            "generated_at": self.generated_at or now_iso(),
            "status": self.status,
            "blocking": self.blocking,
            "error": self.error,
            "summary": {**self.counts, "total": len(self.findings), **self.extra},
            "inputs": self.inputs,
            "findings": [f.to_dict() for f in self.findings],
            "artifacts": self.artifacts,
        }

    def render_text(self) -> str:
        head = [
            "=" * 62,
            f"DataVA {self.mode} 审查报告",
            "=" * 62,
            f"项目: {self.project}",
            f"时间: {self.generated_at or now_iso()}",
            f"结论: {self.status.upper()}"
            f"{'（存在 P0，需阻塞流程）' if self.blocking else ''}",
        ]
        if self.error:
            head.append(f"错误: {self.error}")
        for key, value in self.inputs.items():
            head.append(f"输入 {key}: {value}")
        for key, value in self.extra.items():
            head.append(f"指标 {key}: {value}")

        counts = self.counts
        head += [
            "-" * 62,
            f"发现 {len(self.findings)} 项 — "
            f"P0 {counts[SEV_P0]} / P1 {counts[SEV_P1]} / P2 {counts[SEV_P2]}",
            "-" * 62,
        ]

        body: List[str] = []
        if not self.findings:
            body.append("未发现问题 ✓")
        for index, finding in enumerate(self.findings, 1):
            body.append(
                f"[{index}] {SEV_LABEL.get(finding.severity, finding.severity)} "
                f"《{finding.category}》 {finding.title}"
            )
            if finding.location:
                body.append(f"      位置: {finding.location}")
            if finding.detail:
                body.append(f"      证据: {finding.detail}")
            if finding.expected or finding.actual:
                body.append(f"      应为: {finding.expected} | 实为: {finding.actual}")
            if finding.suggestion:
                body.append(f"      建议: {finding.suggestion}")
            body.append(f"      代码: {finding.code}")
            body.append("")

        tail = ["-" * 62]
        for name, path in self.artifacts.items():
            tail.append(f"产出 {name}: {path}")
        tail.append("=" * 62)
        return "\n".join(head + body + tail) + "\n"


def build_result(
    mode: str,
    project: str,
    findings: Sequence[Finding],
    *,
    inputs: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
    error: str = "",
) -> ReviewResult:
    """统一构造入口：排序 findings 并打时间戳。"""
    return ReviewResult(
        mode=mode,
        project=project,
        findings=tuple(sort_findings(findings)),
        inputs=dict(inputs or {}),
        extra=dict(extra or {}),
        generated_at=now_iso(),
        error=error,
    )


def with_artifacts(result: ReviewResult, artifacts: Dict[str, str]) -> ReviewResult:
    """返回附带产出路径的新结论（不修改原对象）。"""
    return replace(result, artifacts={**result.artifacts, **artifacts})


# ── 路径 ────────────────────────────────────────────────────────

def projects_root() -> Path:
    """项目数据根目录。可用 HERMES_PROJECTS_ROOT 覆盖，默认 ~/projects/energy-audit。"""
    env = os.environ.get("HERMES_PROJECTS_ROOT", "").strip()
    if env:
        return Path(env).expanduser()
    return Path.home() / "projects" / "energy-audit"


def project_dir(project: str, output_dir: Optional[str] = None) -> Path:
    """审查产出目录。--output-dir 优先，否则 <projects_root>/<project>/。"""
    return Path(output_dir).expanduser() if output_dir else projects_root() / project


def project_data_path(project: str) -> Path:
    return projects_root() / project / "data.json"


# ── IO ──────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_json(path: Path) -> Optional[Any]:
    """读 JSON。文件不存在或解析失败返回 None（调用方负责降级）。"""
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def write_json(path: Path, data: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    return str(path)


def write_text(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return str(path)


# ── 数值 ────────────────────────────────────────────────────────

def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def pct_change(current: float, previous: float) -> Optional[float]:
    """同比变化率（%）。基数为 0 时返回 None（无法计算，不臆造）。"""
    if previous == 0:
        return None
    return (current - previous) / abs(previous) * 100.0


def fmt_num(value: Any, digits: int = 2) -> str:
    number = safe_float(value, float("nan"))
    if number != number:  # NaN
        return str(value)
    return f"{number:,.{digits}f}".rstrip("0").rstrip(".") if digits else f"{number:,.0f}"
