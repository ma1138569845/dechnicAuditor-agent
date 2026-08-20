"""ExcelDataProcessor 列头映射 / 模糊匹配 / excel_data 转换 单测。

覆盖：精确匹配、包含匹配（最长别名优先，防单字误吞）、编辑距离兜底、
五类 to_excel_data 输出、数值/int/布尔收敛、未匹配列跳过、build_excel_data 合并。
"""

import pandas as pd
import pytest

from tools.energy_audit.excel_processor import (
    ExcelDataProcessor,
    EXCEL_SCHEMAS,
)


@pytest.fixture
def proc():
    return ExcelDataProcessor("dummy.xlsx")


class TestHeaderMatching:
    def test_exact_match(self, proc):
        assert proc._match_header_to_field('用电量', EXCEL_SCHEMAS['energy']) == 'electricity_kwh'

    def test_exact_match_with_parenthesized_unit(self, proc):
        assert proc._match_header_to_field('电(kWh)', EXCEL_SCHEMAS['energy']) == 'electricity_kwh'

    def test_longest_alias_wins_cost_not_consumed_by_single_char(self, proc):
        # '电费' 不得因单字别名 '电' 落到 electricity_kwh
        assert proc._match_header_to_field('电费', EXCEL_SCHEMAS['energy']) == 'electricity_cost_wan'
        assert proc._match_header_to_field('水费(万元)', EXCEL_SCHEMAS['energy']) == 'water_cost_wan'

    def test_contain_match(self, proc):
        # '用能量' 与 '用电量' 编辑距离 1；与 '电量' 也是 1，按 schema 顺序取首个
        assert proc._match_header_to_field('用能量', EXCEL_SCHEMAS['energy']) == 'electricity_kwh'

    def test_no_match_returns_none(self, proc):
        assert proc._match_header_to_field('随便备注', EXCEL_SCHEMAS['energy']) is None

    def test_base_area_vs_building_area_disambiguated(self, proc):
        # 同一列头 '建筑面积'：base → building_area，buildings → area
        assert proc._match_header_to_field('建筑面积', EXCEL_SCHEMAS['base']) == 'building_area'
        assert proc._match_header_to_field('建筑面积', EXCEL_SCHEMAS['buildings']) == 'area'


class TestToExcelData:
    def test_base_scalars(self, proc):
        df = pd.DataFrame([{'单位名称': '某医院', '用能人数': 1200, '建筑面积': 50000}])
        data = proc.to_excel_data('base', df)
        assert data['unit_name'] == '某医院'
        assert data['people_count'] == 1200
        assert data['building_area'] == 50000.0

    def test_base_empty_returns_empty_dict(self, proc):
        df = pd.DataFrame({'单位名称': pd.Series(dtype='object')})
        assert proc.to_excel_data('base', df) == {}

    def test_energy_rows(self, proc):
        df = pd.DataFrame([
            {'年份': 2022, '用电量': 1000, '用水量': 200},
            {'年份': 2023, '用电量': 1100, '用水量': 210},
        ])
        data = proc.to_excel_data('energy', df)
        assert list(data) == ['energy_yearly']
        ey = data['energy_yearly']
        assert ey[0]['year'] == 2022
        assert ey[0]['electricity_kwh'] == 1000.0
        assert ey[1]['water_m3'] == 210.0

    def test_buildings_rows(self, proc):
        df = pd.DataFrame([{'建筑名称': '门诊楼', '建筑面积': 30000, '地上层数': 12}])
        data = proc.to_excel_data('buildings', df)
        b = data['buildings'][0]
        assert b['name'] == '门诊楼'
        assert b['area'] == 30000.0
        assert b['up_floor'] == 12

    def test_equipment_rows(self, proc):
        df = pd.DataFrame([{'设备名称': 'LED灯', '数量': 200, '分类': '照明'}])
        data = proc.to_excel_data('equipment', df)
        e = data['equipment'][0]
        assert e['name'] == 'LED灯'
        assert e['quantity'] == 200
        assert e['category'] == '照明'

    def test_metering_boolean(self, proc):
        df = pd.DataFrame([{'有无监测系统': '有', '分项计量': '无'}])
        data = proc.to_excel_data('metering', df)
        m = data['metering']
        assert m['has_monitoring_system'] is True
        assert m['has_separate_metering'] is False

    def test_nan_coerced_to_zero(self, proc):
        df = pd.DataFrame([{'年份': 2023, '用电量': None}])
        data = proc.to_excel_data('energy', df)
        assert data['energy_yearly'][0]['electricity_kwh'] == 0

    def test_unmatched_columns_skipped(self, proc):
        df = pd.DataFrame([{'年份': 2023, '随便备注': 'x'}])
        data = proc.to_excel_data('energy', df)
        assert '随便备注' not in data['energy_yearly'][0]


class TestBuildExcelData:
    def test_assembles_full_dict(self, proc):
        sheets = {
            'base': pd.DataFrame([{'单位名称': '某医院'}]),
            'energy': pd.DataFrame([{'年份': 2023, '用电量': 100}]),
            'equipment': pd.DataFrame([{'设备名称': '空调', '数量': 3}]),
        }
        data = proc.build_excel_data(sheets)
        assert data['unit_name'] == '某医院'
        assert data['energy_yearly'][0]['electricity_kwh'] == 100.0
        assert data['equipment'][0]['name'] == '空调'

    def test_unknown_category_ignored(self, proc):
        data = proc.build_excel_data({'unknown': pd.DataFrame([{'a': 1}])})
        assert data == {}