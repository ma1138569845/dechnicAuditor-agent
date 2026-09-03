"""DataVA — 三模式数据验证审查包。

模块划分：
    bootstrap             tools.energy_audit 路径解析（不硬编码项目路径）
    common                Finding / ReviewResult / 路径 / IO / 数值工具
    mode_data_check       V1 DATA_CHECK        采集后：完整性 + 异常 + KG + 评级
    mode_indicator_review V2 INDICATOR_REVIEW  计算后：年际对比 + 对标一致性 + 数据一致性
    mode_report_review    V3 REPORT_REVIEW     报告后：跨章一致性 + 章节完整性 + 格式规范
"""

from .common import (
    EXIT_BLOCK,
    EXIT_ERROR,
    EXIT_OK,
    SCHEMA_VERSION,
    SEV_P0,
    SEV_P1,
    SEV_P2,
    Finding,
    ReviewResult,
)

MODES = ("DATA_CHECK", "INDICATOR_REVIEW", "REPORT_REVIEW")

__all__ = [
    "MODES",
    "SCHEMA_VERSION",
    "SEV_P0",
    "SEV_P1",
    "SEV_P2",
    "EXIT_OK",
    "EXIT_ERROR",
    "EXIT_BLOCK",
    "Finding",
    "ReviewResult",
]
