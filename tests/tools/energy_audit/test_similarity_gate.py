"""防抄查重闸门 similarity_gate 单元测试。"""

import pytest

from tools.energy_audit.similarity_gate import (
    MIN_CONTIGUOUS,
    check_similarity,
    format_flags,
    normalize,
)


class TestNormalize:
    def test_strips_punctuation_and_space(self):
        assert normalize("医院2022年，用电量：5090273 kWh。") == "医院2022年用电量5090273kWh"

    def test_keeps_alnum_and_cjk_only(self):
        assert normalize("由表5.2可知") == "由表52可知"


class TestCheckSimilarity:
    def test_identical_text_fails(self):
        text = "医院2022年全年用电量为5090273千瓦时，较上一年度明显增长，主要原因是制冷季空调系统运行时间延长所致。"
        report = check_similarity(text, [text])
        assert report is not None
        assert report["passed"] is False
        assert report["max_match_len"] >= MIN_CONTIGUOUS

    def test_rewritten_text_passes(self):
        ref = (
            "医院2022年全年用电量为5090273千瓦时，2023年全年用电量为5297546千瓦时，"
            "2024年全年用电量为4996788千瓦时，整体变化平稳。"
        )
        generated = (
            "根据能耗账单统计，该单位2024年消耗电力4833915千瓦时，较2023年有所回落，"
            "三年用电水平总体保持平稳，未出现明显波动，符合机关办公区季节用能规律。"
        )
        report = check_similarity(generated, [ref])
        assert report is not None
        assert report["passed"] is True

    def test_same_structure_copied_sentence_fails(self):
        """仅替换数值的同构句逃不过 n-gram 重合。"""
        ref = (
            "由图5.2分析，医院2022年至2024年总用电量整体平稳，2023年用电量较2022年"
            "增加207273千瓦时，增加率为4.07个百分点。"
        )
        generated = (
            "由图5.2分析，机关2022年至2024年总用电量整体平稳，2023年用电量较2022年"
            "增加120000千瓦时，增加率为3.21个百分点。"
        )
        report = check_similarity(generated, [ref])
        assert report["passed"] is False

    def test_short_text_skipped(self):
        report = check_similarity("医院用能平稳。", ["医院用能平稳。"])
        assert report is None

    def test_no_reference_returns_none(self):
        report = check_similarity("一段足够长的生成文本。" * 10, [])
        assert report is None

    def test_violations_record_matched_fragments(self):
        text = (
            "医院未建设能耗在线监测系统，能源数据以人工抄录为主，能源资源管理精细化程度"
            "有待进一步提高。医院大型医疗设备、手术室净化空调、消毒供应等特殊用能系统"
            "未独立计量，无法单独统计特殊用能系统能耗水平。"
        )
        report = check_similarity(text, [text])
        assert report and not report["passed"]
        assert any(v["length"] >= 8 for v in report["violations"])

    def test_format_flags(self):
        assert format_flags(None).startswith("无参考文本")
        text = (
            "医院未建设能耗在线监测系统，能源数据以人工抄录为主，能源资源管理精细化程度"
            "有待进一步提高。医院大型医疗设备、手术室净化空调、消毒供应等特殊用能系统"
            "未独立计量，无法单独统计特殊用能系统能耗水平。"
        )
        report = check_similarity(text, [text])
        assert "疑似复述" in format_flags(report)
