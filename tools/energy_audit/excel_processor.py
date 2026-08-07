"""
能源审计Excel数据处理工具
用于解析和清洗能源审计相关数据
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Union
import os
from datetime import datetime


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
