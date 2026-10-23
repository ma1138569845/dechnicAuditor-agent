"""地区 × 报告族路由。

报告族决定章节、指标、标准包、蓝本和 QA 口径。当前接入：

- 山东 × 公共机构（兼容既有主链）；
- 浙江 × 公共建筑；
- 山东 × 公共建筑；
- 浙江 × 公共机构。

建筑功能（医院、学校、办公等）不能单独决定报告族；同一医院既可能是公共
机构，也可能是公共建筑，必须由 ``unit_type + province`` 选择。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


PUBLIC_INSTITUTION = "public_institution"
PUBLIC_BUILDING = "public_building"
SHANDONG = "山东"
ZHEJIANG = "浙江"
STANDARDS_ROOT = "energy-audit-core/references/standards"
SHANDONG_PUBLIC_BUILDING_PACK = f"{STANDARDS_ROOT}/shandong/public_building/"
ZHEJIANG_PUBLIC_BUILDING_PACK = f"{STANDARDS_ROOT}/zhejiang/"
ZHEJIANG_PUBLIC_INSTITUTION_PACK = (
    f"{STANDARDS_ROOT}/zhejiang/public_institution/"
)


class ReportFamilyUnsupported(ValueError):
    """当前技能包没有对应地区或报告族的标准与规则。"""


@dataclass(frozen=True)
class ReportFamilyContext:
    family: str
    region: str = ""
    standard_pack: str = ""
    supported: bool = True
    label: str = ""

    @property
    def is_public_building(self) -> bool:
        return self.family == PUBLIC_BUILDING

    @property
    def is_zhejiang(self) -> bool:
        return self.region == ZHEJIANG

    @property
    def is_shandong(self) -> bool:
        return self.region == SHANDONG

    @property
    def is_zhejiang_public_building(self) -> bool:
        return self.is_public_building and self.is_zhejiang

    @property
    def is_shandong_public_building(self) -> bool:
        return self.is_public_building and self.is_shandong

    @property
    def is_zhejiang_public_institution(self) -> bool:
        return self.family == PUBLIC_INSTITUTION and self.is_zhejiang


def _clean(value: Any) -> str:
    return str(value or "").strip()


def resolve_report_family(base: Mapping[str, Any]) -> ReportFamilyContext:
    """解析项目所属报告族；不支持时抛出可读错误。

    空 ``unit_type`` 按公共机构处理，以兼容早于本字段的旧项目。
    """
    unit_type = _clean(base.get("unit_type")) or "公共机构"
    province = _clean(base.get("province"))

    if unit_type == "公共机构":
        if ZHEJIANG in province:
            return ReportFamilyContext(
                family=PUBLIC_INSTITUTION,
                region=ZHEJIANG,
                standard_pack=ZHEJIANG_PUBLIC_INSTITUTION_PACK,
                label="公共机构（浙江）",
            )
        return ReportFamilyContext(
            family=PUBLIC_INSTITUTION,
            region=province,
            standard_pack=(
                "energy-audit-core/references/standards-values.md"
                if SHANDONG in province
                else ""
            ),
            label=f"公共机构（{province}）" if province else "公共机构",
        )

    if unit_type == "公共建筑":
        if SHANDONG in province:
            return ReportFamilyContext(
                family=PUBLIC_BUILDING,
                region=SHANDONG,
                standard_pack=SHANDONG_PUBLIC_BUILDING_PACK,
                label="公共建筑（山东）",
            )
        if ZHEJIANG not in province:
            shown = province or "空"
            raise ReportFamilyUnsupported(
                "公共建筑报告族目前仅接入山东、浙江标准包"
                f"（当前省份：{shown}）"
            )
        return ReportFamilyContext(
            family=PUBLIC_BUILDING,
            region=ZHEJIANG,
            standard_pack=ZHEJIANG_PUBLIC_BUILDING_PACK,
            label="公共建筑（浙江）",
        )

    raise ReportFamilyUnsupported(
        f"不支持的报告族：{unit_type}（当前支持公共机构、山东公共建筑、"
        "浙江公共建筑）"
    )


def is_public_building(base: Mapping[str, Any]) -> bool:
    return resolve_report_family(base).family == PUBLIC_BUILDING

