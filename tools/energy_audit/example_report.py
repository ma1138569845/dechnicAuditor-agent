"""
能源审计报告生成示例
展示如何使用能源审计工具包生成完整的审计报告
"""

import sys
import os

from tools.energy_audit._paths import PROJECT_ROOT  # noqa: F401

from tools.energy_audit import ReportGenerator


def generate_sample_report():
    """生成示例报告"""
    
    # 创建报告数据
    report_data = {
        'cover': {
            'title': '某市政府机关能源审计报告',
            'audit_organization': '同方德诚科技有限公司',
            'audited_unit': '某市政府机关',
            'audit_period': '2023年1月1日 至 2023年12月31日',
            'report_number': 'EA-2023-001',
            'report_date': '2024年1月15日'
        },
        
        'executive_summary': {
            'purpose': '评估某市政府机关能源使用状况，发现节能潜力，提出节能改造建议，促进公共机构节能减排工作。',
            'scope': '本次审计范围包括办公楼的电力、天然气、热力等能源消耗，涵盖建筑围护结构、供暖系统、空调系统、照明系统等主要用能系统。',
            'standards': [
                'GB/T 13234-2018 用能单位节能量计算方法',
                'GB/T 15587-2008 工业企业能源管理导则',
                'GB/T 23331-2012 能源管理体系要求',
                '公共机构能源审计技术导则',
                '公共机构节能条例',
                '某省公共机构能源审计实施细则'
            ],
            'methodology': '采用现场调查、数据收集、设备检测、人员访谈等方法，结合能源计量统计数据和历史能耗数据进行分析。',
            'conclusions': [
                '该单位能源管理组织架构完善，管理制度健全',
                '能源计量器具配置基本齐全，数据统计规范',
                '人均综合能耗为0.85 tce/人，低于同类型单位平均水平',
                '空调系统和照明系统存在较大的节能潜力',
                '建议实施空调系统变频改造和LED照明改造'
            ]
        },
        
        'unit_overview': {
            'unit_name': '某市政府机关',
            'address': '某市某区某路123号',
            'contact_person': '张三',
            'contact_phone': '0571-88888888',
            'building_area': '25000',
            'floors': '12',
            'construction_year': '2005年',
            'building_structure': '钢筋混凝土框架结构',
            'permanent_staff': '500',
            'floating_population': '200',
            'total_occupants': '700',
            'equipment': [
                {'name': '中央空调机组', 'model': '格力GMV-Pd120W', 'quantity': '4', 'power': '120kW'},
                {'name': '照明灯具', 'model': 'LED面板灯', 'quantity': '2000', 'power': '36W'},
                {'name': '电梯', 'model': '三菱NEXIEZ', 'quantity': '6', 'power': '15kW'},
                {'name': '水泵', 'model': '格兰富CR', 'quantity': '8', 'power': '7.5kW'}
            ]
        },
        
        'energy_management': {
            'organization_structure': '该单位成立了能源管理领导小组，由分管领导任组长，后勤部门负责具体实施，各部门设有能源管理联络员。',
            'policies': [
                '《能源管理制度》',
                '《节能工作考核办法》',
                '《能源消耗统计制度》',
                '《能源计量管理制度》',
                '《空调系统运行管理规定》'
            ],
            'staff': [
                {'name': '李四', 'position': '后勤处处长', 'responsibility': '全面负责能源管理工作', 'contact': '13800138001'},
                {'name': '王五', 'position': '能源管理员', 'responsibility': '日常能源管理和数据统计', 'contact': '13800138002'}
            ],
            'training': [
                {'topic': '公共机构节能知识培训', 'date': '2023年3月', 'participants': '50'},
                {'topic': '能源计量管理培训', 'date': '2023年6月', 'participants': '30'},
                {'topic': '节能技术应用培训', 'date': '2023年9月', 'participants': '40'}
            ]
        },
        
        'measurement_statistics': {
            'meters': [
                {'name': '总电表', 'model': 'DTSD341', 'location': '配电室', 'status': '已检定'},
                {'name': '天然气表', 'model': 'G25', 'location': '锅炉房', 'status': '已检定'},
                {'name': '热量表', 'model': 'ULTIMATE', 'location': '换热站', 'status': '已检定'},
                {'name': '水表', 'model': 'LXL-80', 'location': '水泵房', 'status': '已检定'}
            ],
            'statistics_method': '采用自动抄表系统与人工抄表相结合的方式，每日采集能耗数据，每月汇总统计。',
            'data_recording': '能耗数据通过能源管理系统自动记录，同时保留纸质台账备查。',
            'data_reporting': '每月向上级主管部门报送能耗统计数据，每季度报送节能工作进展情况。'
        },
        
        'consumption_analysis': {
            'energy_types': [
                {'type': '电力', 'consumption': '1,250,000', 'unit': 'kWh', 'percentage': '65.2'},
                {'type': '天然气', 'consumption': '85,000', 'unit': 'm³', 'percentage': '18.5'},
                {'type': '热力', 'consumption': '3,200', 'unit': 'GJ', 'percentage': '12.8'},
                {'type': '汽油', 'consumption': '15,000', 'unit': 'L', 'percentage': '3.5'}
            ],
            'total_consumption': {
                'total': '2,135.6',
                'electricity': '1,250,000',
                'gas': '85,000',
                'heat': '3,200'
            },
            'per_capita': {
                'energy_per_person': '0.85',
                'electricity_per_person': '1,785.7'
            },
            'per_area': {
                'energy_per_area': '0.024',
                'electricity_per_area': '50.0'
            },
            'comparison': {
                'year_over_year': '-3.2',
                'month_over_month': '2.1'
            }
        },
        
        'system_analysis': {
            'electricity_system': '电力系统主要包括照明、空调、办公设备、电梯等用电设备。照明系统仍以荧光灯为主，存在较大的LED改造潜力。空调系统运行时间较长，能效有所下降。',
            'heating_system': '供暖系统采用燃气锅炉集中供暖，锅炉运行效率约为85%，处于正常水平。管网保温状况良好，热损失较小。',
            'cooling_system': '空调系统采用中央空调系统，机组运行年限较长，能效比下降明显。建议进行变频改造或更换高效机组。',
            'lighting_system': '照明系统主要采用T8荧光灯，功率因数较低。建议更换为LED灯具，预计可节能40%以上。',
            'other_systems': '电梯系统采用交流变频调速，运行状况良好。水泵系统采用定频运行，建议改造为变频控制。'
        },
        
        'energy_saving': {
            'implemented_measures': [
                {'name': '办公设备节能管理', 'date': '2022年', 'effect': '年节电约5万kWh'},
                {'name': '空调温度设定优化', 'date': '2023年', 'effect': '年节电约3万kWh'},
                {'name': '照明分时控制', 'date': '2023年', 'effect': '年节电约2万kWh'}
            ],
            'potential_measures': [
                {'name': 'LED照明改造', 'investment': '80万元', 'saving': '年节电40万kWh', 'payback_period': '3年'},
                {'name': '空调变频改造', 'investment': '120万元', 'saving': '年节电25万kWh', 'payback_period': '5年'},
                {'name': '水泵变频改造', 'investment': '30万元', 'saving': '年节电8万kWh', 'payback_period': '4年'},
                {'name': '太阳能热水系统', 'investment': '50万元', 'saving': '年节气1.5万m³', 'payback_period': '6年'}
            ],
            'recommendations': [
                '优先实施LED照明改造，投资回收期短，节能效果明显',
                '逐步实施空调系统变频改造，提高系统能效',
                '加强能源管理，完善计量体系，提高数据准确性',
                '开展节能宣传教育，提高全员节能意识',
                '建立节能考核机制，将节能目标纳入绩效考核'
            ],
            'expected_effects': '通过实施上述节能措施，预计年可节约能源费用约120万元，年可减少二氧化碳排放约500吨，综合节能率可达15%以上。'
        },
        
        'conclusion': {
            'findings': [
                '能源管理组织架构完善，管理制度健全',
                '能源计量器具配置基本齐全，数据统计规范',
                '人均综合能耗为0.85 tce/人，低于同类型单位平均水平',
                '空调系统和照明系统存在较大的节能潜力',
                '已实施的节能措施取得了一定效果',
                '仍有较大的节能空间和改造潜力'
            ],
            'evaluation': '该单位能源利用状况总体良好，能源管理工作较为规范。但在空调系统、照明系统等方面仍有较大的节能潜力，建议加大节能改造力度。',
            'suggestions': [
                '制定节能改造规划，分年度实施节能改造项目',
                '加大节能资金投入，确保节能改造项目顺利实施',
                '加强能源管理队伍建设，提高能源管理水平',
                '建立节能长效机制，持续推进节能减排工作',
                '定期开展能源审计，及时发现和解决能源浪费问题'
            ],
            'follow_up': '建议该单位在本次审计基础上，制定详细的节能改造实施方案，明确时间表和路线图，确保各项节能措施落到实处。同时，建议建立能源管理信息系统，实现能源消耗的实时监控和精细化管理。'
        }
    }
    
    # 创建报告生成器
    generator = ReportGenerator('公共机构')
    generator.set_report_data(report_data)
    
    # 生成完整报告
    print("正在生成公共机构能源审计报告...")
    report_content = generator.generate_full_report()
    
    # 保存报告
    output_path = '公共机构能源审计报告_示例.md'
    generator.save_report(output_path)
    
    print(f"报告生成完成！")
    print(f"报告文件：{output_path}")
    print(f"报告长度：{len(report_content)} 字符")
    
    # 显示报告结构
    print("\n报告结构：")
    print("1. 封面")
    print("2. 目录")
    print("3. 第1章 能源审计执行概要")
    print("4. 第2章 公共机构单位概况")
    print("5. 第3章 能源资源管理状况")
    print("6. 第4章 能源资源计量及统计状况")
    print("7. 第5章 能源资源消费/消耗指标分析")
    print("8. 第6章 主要能源资源利用系统分析")
    print("9. 第7章 节能效果与节能潜力分析")
    print("10. 第8章 审计结论")
    
    return output_path


if __name__ == "__main__":
    generate_sample_report()
