"""
能源审计Excel数据处理工具
用于解析和清洗能源审计相关数据
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Union
import os
from datetime import datetime


# ============================================================
# Excel → excel_data 字典转换（供 pg_collector.build_and_save_project 合并）
#
# 每个数据类别定义：标准字段 → 候选列头别名列表。
# 列头匹配优先级：精确 > 包含（最长别名优先）> 编辑距离。
# 输出 schema 与 collect_from_pg 的 found 结构一致：
#   - base 标量直接进 excel_data 顶层（unit_name/address/...）
#   - 集合类进 excel_data['buildings'|'energy_yearly'|'equipment'|'metering']
# ============================================================

EXCEL_SCHEMAS = {
    'base': {
        'unit_name': ['单位名称', '被审计单位名称', '被审计单位', '单位'],
        'unit_short': ['单位简称', '简称'],
        'address': ['地址', '单位地址'],
        'province': ['省份', '省'],
        'unit_type': ['审计类型', '单位类型'],
        'institution_category': ['机构类别'],
        'specific_type': ['具体类型'],
        'basic_situation': ['基本情况', '单位概况'],
        'contact_person': ['联系人'],
        'contact_phone': ['联系电话', '电话'],
        'auditor': ['审计机构', '审计单位'],
        'building_area': ['建筑面积', '总面积'],
        'people_count': ['用能人数', '职工数', '人数'],
        'beds_count': ['床位数', '床位'],
        'audit_start': ['审计开始', '审计起始'],
        'audit_end': ['审计结束', '审计截止'],
        'data_start': ['数据开始', '数据起始'],
        'data_end': ['数据结束', '数据截止'],
        'report_date': ['报告日期'],
    },
    'buildings': {
        'name': ['建筑名称', '楼栋', '建筑'],
        'address': ['地址'],
        'year': ['竣工年份', '建成年份'],
        'function': ['建筑功能', '功能'],
        'area': ['建筑面积', '面积'],
        'use_area': ['使用面积'],
        'cooling_area': ['供冷面积'],
        'heating_area': ['供热面积'],
        'floors': ['层数', '楼层'],
        'up_floor': ['地上层数'],
        'down_floor': ['地下层数'],
        'structure': ['结构形式', '结构'],
        'insulation': ['外墙保温', '保温形式'],
        'cooling_source': ['冷源', '供冷方式'],
        'heating_source': ['热源', '供暖方式'],
    },
    'energy': {
        'year': ['年份', '年度'],
        'electricity_kwh': ['用电量', '用电', '电量', '电(kWh)', '电'],
        'water_m3': ['用水量', '用水', '水量', '水(m³)', '水'],
        'natural_gas_m3': ['天然气', '燃气', '气量', '气(m³)', '气'],
        'heating_energy_heat_gj': ['热能', '供热量', '供热'],
        'petrol_kg': ['汽油'],
        'diesel_kg': ['柴油'],
        'electricity_cost_wan': ['电费', '电费(万元)'],
        'water_cost_wan': ['水费', '水费(万元)'],
        'natural_gas_cost_wan': ['燃气费', '气费'],
        'heating_cost_wan': ['热费', '供暖费'],
    },
    'equipment': {
        'name': ['设备名称', '设备'],
        'category': ['分类', '设备分类'],
        'spec': ['规格', '规格型号'],
        'quantity': ['数量', '台数', '设备数量'],
        'independent_metering': ['独立计量', '是否独立计量', '单独计量'],
    },
    'metering': {
        'has_monitoring_system': ['有无监测系统', '监测系统'],
        'has_separate_metering': ['分项计量'],
        'has_household_metering': ['分户计量'],
        'has_shared_office': ['合署办公', '是否合署办公'],
        'has_household_payment': ['分户缴费'],
        'electric_meters': ['电表数量', '电表数'],
        'water_meters': ['水表数量', '水表数'],
        'gas_meters': ['气表数量', '气表数'],
        'heat_meters': ['热量表数量', '热量表数'],
    },
}

# 各类别中按 float / int / bool 收敛的字段
EXCEL_NUMERIC_FIELDS = {
    'base': {'building_area'},
    'buildings': {'area', 'use_area', 'cooling_area', 'heating_area'},
    'energy': {'electricity_kwh', 'water_m3', 'natural_gas_m3', 'heating_energy_heat_gj',
               'petrol_kg', 'diesel_kg', 'electricity_cost_wan', 'water_cost_wan',
               'natural_gas_cost_wan', 'heating_cost_wan'},
    'equipment': set(),
    'metering': set(),
}
EXCEL_INT_FIELDS = {
    'base': {'people_count', 'beds_count'},
    'buildings': {'year', 'up_floor', 'down_floor'},
    'energy': {'year'},
    'equipment': {'quantity'},
    'metering': {'electric_meters', 'water_meters', 'gas_meters', 'heat_meters'},
}
EXCEL_BOOL_FIELDS = {
    'metering': {'has_monitoring_system', 'has_separate_metering', 'has_household_metering',
                 'has_shared_office', 'has_household_payment'},
}

# 各类别输出到 excel_data 的顶层键；base 的标量直接进顶层（None）
EXCEL_OUTPUT_KEYS = {
    'base': None,
    'buildings': 'buildings',
    'energy': 'energy_yearly',
    'equipment': 'equipment',
    'metering': 'metering',
}


class ExcelDataProcessor:
    """Excel数据处理器"""
    
    def __init__(self, file_path: str):
        """
        初始化Excel数据处理器
        
        Args:
            file_path: Excel文件路径
        """
        self.file_path = file_path
        self.data = None
        self.metadata = {}
        
    def read_excel(self, sheet_name: Union[str, int] = 0) -> pd.DataFrame:
        """
        读取Excel文件
        
        Args:
            sheet_name: 工作表名称或索引
            
        Returns:
            DataFrame数据
        """
        try:
            if self.file_path.endswith('.csv'):
                self.data = pd.read_csv(self.file_path)
            else:
                self.data = pd.read_excel(self.file_path, sheet_name=sheet_name)
            
            # 记录元数据
            self.metadata = {
                'file_path': self.file_path,
                'sheet_name': sheet_name,
                'rows': len(self.data),
                'columns': len(self.data.columns),
                'read_time': datetime.now().isoformat()
            }
            
            return self.data
            
        except Exception as e:
            raise Exception(f"读取Excel文件失败: {str(e)}")
    
    def clean_data(self, df: pd.DataFrame = None) -> pd.DataFrame:
        """
        清洗数据
        
        Args:
            df: 待清洗的DataFrame，如果为None则使用self.data
            
        Returns:
            清洗后的DataFrame
        """
        if df is None:
            df = self.data.copy()
        
        # 1. 处理缺失值
        df = self._handle_missing_values(df)
        
        # 2. 数据类型转换
        df = self._convert_data_types(df)
        
        # 3. 异常值处理
        df = self._handle_outliers(df)
        
        # 4. 重复数据处理
        df = self._handle_duplicates(df)
        
        return df
    
    def _handle_missing_values(self, df: pd.DataFrame) -> pd.DataFrame:
        """处理缺失值"""
        # 数值列用均值填充
        numeric_columns = df.select_dtypes(include=[np.number]).columns
        for col in numeric_columns:
            if df[col].isnull().sum() > 0:
                mean_val = df[col].mean()
                df[col].fillna(mean_val, inplace=True)
        
        # 分类列用众数填充
        categorical_columns = df.select_dtypes(include=['object']).columns
        for col in categorical_columns:
            if df[col].isnull().sum() > 0:
                mode_val = df[col].mode()[0] if not df[col].mode().empty else '未知'
                df[col].fillna(mode_val, inplace=True)
        
        return df
    
    def _convert_data_types(self, df: pd.DataFrame) -> pd.DataFrame:
        """转换数据类型"""
        # 尝试转换日期列
        for col in df.columns:
            if df[col].dtype == 'object':
                try:
                    df[col] = pd.to_datetime(df[col])
                except Exception:
                    pass
        
        return df
    
    def _handle_outliers(self, df: pd.DataFrame) -> pd.DataFrame:
        """处理异常值"""
        numeric_columns = df.select_dtypes(include=[np.number]).columns
        
        for col in numeric_columns:
            # 使用IQR方法检测异常值
            Q1 = df[col].quantile(0.25)
            Q3 = df[col].quantile(0.75)
            IQR = Q3 - Q1
            
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR
            
            # 将异常值替换为边界值
            df[col] = df[col].clip(lower=lower_bound, upper=upper_bound)
        
        return df
    
    def _handle_duplicates(self, df: pd.DataFrame) -> pd.DataFrame:
        """处理重复数据"""
        # 删除完全重复的行
        df = df.drop_duplicates()
        
        return df
    
    def calculate_energy_indicators(self, df: pd.DataFrame, 
                                  energy_col: str, 
                                  area_col: str = None, 
                                  people_col: str = None) -> Dict:
        """
        通用 DataFrame 能耗指标（非能源审计专业指标）。

        该函数仅做简单的列汇总/同比统计，不涉及折标系数、定额对标、
        非供暖能耗拆分等审计专业计算。若需要专业能源审计指标，请使用
        tools.energy_audit.indicators.compute_project_indicators。

        Args:
            df: 包含能耗数据的DataFrame
            energy_col: 能耗列名
            area_col: 面积列名（可选）
            people_col: 人数列名（可选）
            
        Returns:
            包含各种能耗指标的字典
        """
        indicators = {}
        
        # 总能耗
        total_energy = df[energy_col].sum()
        indicators['total_energy'] = total_energy
        
        # 平均能耗
        indicators['average_energy'] = df[energy_col].mean()
        
        # 最大能耗
        indicators['max_energy'] = df[energy_col].max()
        
        # 最小能耗
        indicators['min_energy'] = df[energy_col].min()
        
        # 单位面积能耗
        if area_col and area_col in df.columns:
            total_area = df[area_col].sum()
            if total_area > 0:
                indicators['energy_per_area'] = total_energy / total_area
        
        # 人均能耗
        if people_col and people_col in df.columns:
            total_people = df[people_col].sum()
            if total_people > 0:
                indicators['energy_per_person'] = total_energy / total_people
        
        # 同比变化（如果有时间列）
        date_columns = df.select_dtypes(include=['datetime64']).columns
        if len(date_columns) > 0:
            date_col = date_columns[0]
            df_sorted = df.sort_values(date_col)
            if len(df_sorted) >= 2:
                first_half = df_sorted.iloc[:len(df_sorted)//2][energy_col].mean()
                second_half = df_sorted.iloc[len(df_sorted)//2:][energy_col].mean()
                if first_half > 0:
                    indicators['year_over_year_change'] = (second_half - first_half) / first_half * 100
        
        return indicators
    
    def export_to_json(self, df: pd.DataFrame = None, output_path: str = None) -> str:
        """
        导出为JSON格式
        
        Args:
            df: 待导出的DataFrame
            output_path: 输出文件路径
            
        Returns:
            JSON字符串或文件路径
        """
        if df is None:
            df = self.data
        
        if output_path:
            df.to_json(output_path, orient='records', force_ascii=False, indent=2)
            return output_path
        else:
            return df.to_json(orient='records', force_ascii=False, indent=2)
    
    def export_to_csv(self, df: pd.DataFrame = None, output_path: str = None) -> str:
        """
        导出为CSV格式
        
        Args:
            df: 待导出的DataFrame
            output_path: 输出文件路径
            
        Returns:
            CSV字符串或文件路径
        """
        if df is None:
            df = self.data
        
        if output_path:
            df.to_csv(output_path, index=False, encoding='utf-8-sig')
            return output_path
        else:
            return df.to_csv(index=False, encoding='utf-8-sig')
    
    def generate_summary(self, df: pd.DataFrame = None) -> Dict:
        """
        生成数据摘要
        
        Args:
            df: 待摘要的DataFrame
            
        Returns:
            数据摘要字典
        """
        if df is None:
            df = self.data
        
        summary = {
            'basic_info': {
                'total_rows': len(df),
                'total_columns': len(df.columns),
                'memory_usage': df.memory_usage(deep=True).sum()
            },
            'column_info': {},
            'statistics': {}
        }
        
        # 列信息
        for col in df.columns:
            col_info = {
                'dtype': str(df[col].dtype),
                'non_null_count': df[col].count(),
                'null_count': df[col].isnull().sum(),
                'unique_count': df[col].nunique()
            }
            
            # 数值列统计
            if df[col].dtype in ['int64', 'float64']:
                col_info.update({
                    'mean': df[col].mean(),
                    'std': df[col].std(),
                    'min': df[col].min(),
                    'max': df[col].max(),
                    'median': df[col].median()
                })
            
            summary['column_info'][col] = col_info
        
        # 整体统计
        numeric_columns = df.select_dtypes(include=[np.number]).columns
        if len(numeric_columns) > 0:
            summary['statistics'] = {
                'numeric_columns': list(numeric_columns),
                'total_numeric_values': df[numeric_columns].count().sum(),
                'total_missing_values': df.isnull().sum().sum()
            }

        return summary

    # ============================================================
    # Excel → excel_data 字典转换（供 build_and_save_project 合并）
    # ============================================================

    @staticmethod
    def _levenshtein(a: str, b: str) -> int:
        """编辑距离，用于列头模糊匹配。"""
        if a == b:
            return 0
        la, lb = len(a), len(b)
        if la == 0:
            return lb
        if lb == 0:
            return la
        prev = list(range(lb + 1))
        for i in range(1, la + 1):
            cur = [i] + [0] * lb
            for j in range(1, lb + 1):
                cur[j] = min(prev[j] + 1, cur[j - 1] + 1,
                             prev[j - 1] + (a[i - 1] != b[j - 1]))
            prev = cur
        return prev[lb]

    def _match_header_to_field(self, header: str,
                               schema: Dict[str, List[str]]) -> Optional[str]:
        """列头 → 标准字段名，匹配优先级：精确 > 包含（最长别名优先）> 编辑距离。

        单字别名（如 '电'）仅用于包含匹配兜底；'电费' 会优先命中更长的
        '电费'/'电费(万元)'，避免被单字 '电' 误吞到 electricity_kwh。
        """
        if header is None:
            return None
        h = str(header).strip().lower()
        if not h:
            return None

        # 1) 精确匹配
        for field, aliases in schema.items():
            for alias in aliases:
                if str(alias).strip().lower() == h:
                    return field

        # 2) 包含匹配（优先最长别名）
        best_alias, best_field, best_len = None, None, 0
        for field, aliases in schema.items():
            for alias in aliases:
                a = str(alias).strip().lower()
                if not a:
                    continue
                if a in h or h in a:
                    if len(a) > best_len:
                        best_len, best_alias, best_field = len(a), a, field
        if best_field is not None:
            return best_field

        # 3) 编辑距离兜底（容忍轻微拼写差异）
        best_d, best_field = 2, None
        for field, aliases in schema.items():
            for alias in aliases:
                a = str(alias).strip().lower()
                if not a:
                    continue
                d = self._levenshtein(h, a)
                if d < best_d:
                    best_d, best_field = d, field
        return best_field

    def _normalize_columns(self, df: pd.DataFrame,
                           category: str) -> Tuple[Dict[str, str], List[str]]:
        """列头标准化：{标准字段: 原始列名}。返回 (映射, 未匹配列名列表)。

        同一标准字段只接受第一个匹配列，避免重复。
        """
        schema = EXCEL_SCHEMAS.get(category)
        if schema is None:
            raise ValueError(f"未知 Excel 类别: {category}，可选 {list(EXCEL_SCHEMAS)}")
        mapping, unmatched, used = {}, [], set()
        for col in df.columns:
            field = self._match_header_to_field(col, schema)
            if field and field not in used:
                mapping[field] = col
                used.add(field)
            elif not field:
                unmatched.append(str(col))
        return mapping, unmatched

    @staticmethod
    def _coerce(value, numeric: bool = False, integer: bool = False,
                boolean: bool = False):
        """单元格值按目标字段类型收敛：NaN/None → 0 或 ''；布尔列识别 有/是/1。"""
        if value is None:
            return False if boolean else (0 if numeric or integer else '')
        try:
            is_na = bool(pd.isna(value))
        except Exception:
            is_na = False
        if is_na:
            return False if boolean else (0 if numeric or integer else '')
        if boolean:
            return str(value).strip() in ('有', '是', '1', '1.0', 'true', 'True', 'TRUE')
        if integer:
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return 0
        if numeric:
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0
        return str(value)

    def to_excel_data(self, category: str = 'base', df: pd.DataFrame = None) -> dict:
        """把 DataFrame 按类别转换为 excel_data 字典片段。

        Args:
            category: 'base' | 'buildings' | 'energy' | 'equipment' | 'metering'
            df: 目标 DataFrame；缺省用 self.data（read_excel 的产物）

        Returns:
            base → 顶层标量字典；其余 → {输出键: 记录列表/dict}。
            未匹配的列跳过并打印提示（不进入结果）。
        """
        if df is None:
            df = self.data
        if df is None:
            raise ValueError("请先 read_excel() 或传入 df")

        mapping, unmatched = self._normalize_columns(df, category)
        if unmatched:
            print(f"[excel] {category} 未匹配的列已跳过: {', '.join(unmatched)}")

        numeric = EXCEL_NUMERIC_FIELDS.get(category, set())
        integer = EXCEL_INT_FIELDS.get(category, set())
        boolean = EXCEL_BOOL_FIELDS.get(category, set())
        output_key = EXCEL_OUTPUT_KEYS.get(category)

        def _row_to_rec(series) -> dict:
            rec = {}
            for field, col in mapping.items():
                rec[field] = self._coerce(series[col],
                                          field in numeric,
                                          field in integer,
                                          field in boolean)
            return rec

        if category == 'base':
            if len(df) == 0:
                return {}
            return _row_to_rec(df.iloc[0])

        rows = [_row_to_rec(r) for _, r in df.iterrows()]
        if output_key is None:
            return rows
        if category == 'metering':
            return {output_key: rows[0] if rows else {}}
        return {output_key: rows}

    def build_excel_data(self, sheets: Dict[str, pd.DataFrame]) -> dict:
        """把多类别 DataFrame 合并为完整的 excel_data 字典。

        Args:
            sheets: {类别: DataFrame}，如
                {'base': df_base, 'buildings': df_buildings, 'energy': df_energy,
                 'equipment': df_equipment, 'metering': df_metering}

        Returns:
            可直接传给 build_and_save_project(excel_data=...) 的字典。
        """
        result = {}
        for category, df in sheets.items():
            if category not in EXCEL_SCHEMAS:
                print(f"[excel] 忽略未知类别: {category}")
                continue
            result.update(self.to_excel_data(category, df))
        return result


def compute_audit_indicators(project) -> Dict:
    """
    计算专业能源审计指标（委托给 indicators.py）。

    Args:
        project: AuditProject 实例

    Returns:
        由 indicators.compute_project_indicators 返回的指标字典
    """
    from tools.energy_audit.indicators import compute_project_indicators
    return compute_project_indicators(project)


# 使用示例
if __name__ == "__main__":
    # 示例：处理能耗数据
    processor = ExcelDataProcessor("能耗数据.xlsx")
    
    # 读取数据
    data = processor.read_excel()
    
    # 清洗数据
    cleaned_data = processor.clean_data()
    
    # 计算通用 DataFrame 指标（非审计专业指标）
    indicators = processor.calculate_energy_indicators(
        cleaned_data,
        energy_col='能耗量',
        area_col='建筑面积',
        people_col='用能人数'
    )
    
    print("通用能耗指标:", indicators)
    
    # 生成摘要
    summary = processor.generate_summary()
    print("数据摘要:", summary)
    
    # 若需要专业能源审计指标，请使用：
    # from tools.energy_audit.project_data import AuditProject
    # result = compute_audit_indicators(project)
    # print("专业审计指标:", result)
