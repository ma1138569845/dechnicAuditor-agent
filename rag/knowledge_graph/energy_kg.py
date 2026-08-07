"""
能源审计因果知识图谱

轻量级实现：NetworkX 内存图 + JSON 持久化。
提供故障诊断、因果推理、措施推荐能力。

用法:
    from rag.knowledge_graph.energy_kg import EnergyKnowledgeGraph

    kg = EnergyKnowledgeGraph()
    kg.load()  # 加载预置因果链
    results = kg.diagnose("冷机COP偏低", system="中央空调系统")

作者: 马天远 | 版本: 1.0.0 | 日期: 2026-07-14
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict

import networkx as nx

from .knowledge_schema import (
    EnergyType, SystemType, Severity,
    CauseNode, MeasureNode, CausalChain,
    DiagnosisResult, DiagnosisReport,
)

# ============================================================
# 初始因果链库（50条）
# 来源: 省立医院东院报告 + DB37标准 + 工程经验
# ============================================================

INITIAL_CAUSAL_CHAINS: List[dict] = [
    # ==================== 中央空调系统 ====================
    {
        "anomaly_description": "冷机COP偏低/下降",
        "anomaly_keywords": ["COP", "cop", "能效", "制冷效率", "冷机效率"],
        "energy_type": "电",
        "system": "中央空调系统",
        "causes": [
            {"label": "冷却水温度偏高", "description": "冷却塔散热不良、填料堵塞或冷却水流量不足，导致冷凝温度升高，压缩机功耗增大，COP下降。", "probability": 0.65, "check_method": "实测冷却水进出水温差，正常应为5-6℃"},
            {"label": "冷冻水出水温度设定过低", "description": "为追求制冷效果将出水温度设定<7℃，压缩机高压缩比运行，COP下降。", "probability": 0.50, "check_method": "查看冷机控制面板出水温度设定值"},
            {"label": "负荷率长期偏低", "description": "冷机长期在<50%负荷率运行，处于低效区间。多台冷机选型过大或群控策略不当。", "probability": 0.45, "check_method": "查看运行记录，计算实际负荷率"},
            {"label": "冷凝器换热管结垢", "description": "冷凝器换热面结垢导致换热效率下降，冷凝温度升高。水质处理不到位或长期未清洗。", "probability": 0.35, "check_method": "检查冷凝器趋近温度，正常<3℃"},
            {"label": "制冷剂不足或泄漏", "description": "制冷剂充注量不足导致蒸发压力偏低、压缩机吸气过热，制冷量和COP均下降。", "probability": 0.20, "check_method": "检查蒸发器趋近温度和过热度"},
        ],
        "measures": [
            {"label": "清洗冷却塔填料及冷凝器", "description": "定期清洗冷却塔填料和冷凝器换热管束，降低冷凝温度。", "estimated_saving_rate": "5-10%", "investment_level": "低", "payback_period": "1年内"},
            {"label": "提高冷冻水出水温度至7-9℃", "description": "在满足末端制冷需求的前提下适当提高供水温度，降低压缩机压缩比。", "estimated_saving_rate": "3-5%", "investment_level": "零投资", "payback_period": "即时"},
            {"label": "优化冷机群控策略", "description": "根据负荷变化自动加减机，避免单机长期低负荷运行。", "estimated_saving_rate": "10-15%", "investment_level": "中", "payback_period": "2-3年"},
            {"label": "加强水质管理", "description": "定期检测冷却水水质，投加缓蚀阻垢剂，降低结垢速率。", "estimated_saving_rate": "3-8%", "investment_level": "低", "payback_period": "1年内"},
            {"label": "检漏并补充制冷剂", "description": "全面检漏、修复泄漏点，按标准充注量补充制冷剂。", "estimated_saving_rate": "5-15%", "investment_level": "低", "payback_period": "1年内"},
        ],
        "sources": ["省立医院东院-2024", "DB37/T 2673-2019"],
    },
    {
        "anomaly_description": "冷冻水供回水温差偏小（<3℃）",
        "anomaly_keywords": ["冷冻水", "温差", "偏小", "供回水", "小温差"],
        "energy_type": "电",
        "system": "中央空调系统",
        "causes": [
            {"label": "冷冻水流量过大", "description": "水泵频率偏高或阀门开度过大，冷冻水大流量小温差运行，输配能耗浪费。", "probability": 0.70, "check_method": "检查水泵频率和阀门开度"},
            {"label": "末端负荷不足", "description": "实际冷负荷远小于设计负荷，末端换热不充分，回水温度偏低。", "probability": 0.40, "check_method": "统计末端实际使用率"},
            {"label": "旁通阀门未关闭", "description": "供回水主管道旁通阀未完全关闭，部分冷冻水短流不经末端直接回水。", "probability": 0.20, "check_method": "现场检查旁通阀门状态"},
        ],
        "measures": [
            {"label": "降低冷冻水泵频率", "description": "通过变频器将水泵频率降至合理范围，使供回水温差恢复至5-6℃。", "estimated_saving_rate": "15-30%（水泵）", "investment_level": "零投资", "payback_period": "即时"},
            {"label": "关闭旁通阀门", "description": "确保供回水旁通阀完全关闭，杜绝短流。", "estimated_saving_rate": "5-10%", "investment_level": "零投资", "payback_period": "即时"},
        ],
        "sources": ["省立医院东院-2024"],
    },
    {
        "anomaly_description": "冷却水进出水温差偏小（<3℃）",
        "anomaly_keywords": ["冷却水", "温差", "偏小", "冷却塔"],
        "energy_type": "电",
        "system": "中央空调系统",
        "causes": [
            {"label": "冷却水流量不足", "description": "冷却水泵出力不足或管路阻力过大，冷却水流量低于设计值，冷却塔换热不充分。", "probability": 0.55, "check_method": "实测冷却水流量与设计值比较"},
            {"label": "冷却塔风机未全开", "description": "冷却塔风机未全部投入运行，散热能力不足。", "probability": 0.35, "check_method": "检查冷却塔风机运行状态"},
        ],
        "measures": [
            {"label": "检查冷却水泵及管路", "description": "清理过滤器、检查水泵叶轮、排查管路阻力异常。", "estimated_saving_rate": "3-5%", "investment_level": "低", "payback_period": "1年内"},
            {"label": "确保冷却塔风机全部投运", "description": "检查风机控制逻辑，确保根据水温自动启停全部风机。", "estimated_saving_rate": "2-4%", "investment_level": "零投资", "payback_period": "即时"},
        ],
        "sources": ["省立医院东院-2024"],
    },
    {
        "anomaly_description": "空调系统缺少智能控制",
        "anomaly_keywords": ["智能控制", "BA", "楼宇自控", "手动", "自控", "群控"],
        "energy_type": "电",
        "system": "中央空调系统",
        "causes": [
            {"label": "未建设楼宇自控系统（BAS）", "description": "冷热源设备、末端设备均为手动控制或就地独立控制，无法根据负荷变化自动调节。", "probability": 0.80, "check_method": "现场查看是否有集中监控平台"},
            {"label": "控制系统老旧已失效", "description": "原有BAS系统因维护缺失已停用，退化为手动操作。", "probability": 0.30, "check_method": "查看BAS系统运行状态"},
        ],
        "measures": [
            {"label": "建设冷机群控系统", "description": "加装冷机群控柜，实现根据负荷自动加减机、优化运行台数和负荷分配。", "estimated_saving_rate": "10-20%", "investment_level": "中", "payback_period": "2-3年"},
            {"label": "末端加装温控器", "description": "风机盘管/空调箱加装电动阀和温控器，实现分区域按需供冷。", "estimated_saving_rate": "5-15%", "investment_level": "中", "payback_period": "2-3年"},
        ],
        "sources": ["省立医院东院-2024", "DB37/T 2673-2019"],
    },
    # ==================== 供暖系统 ====================
    {
        "anomaly_description": "供暖能耗同比大幅增加（≥30%）",
        "anomaly_keywords": ["供暖", "采暖", "热耗", "供热", "耗热"],
        "energy_type": "热",
        "system": "供暖系统",
        "causes": [
            {"label": "供暖面积扩大", "description": "新增建筑或区域接入供暖系统，供暖面积增加导致总耗热量上升。", "probability": 0.55, "check_method": "核对各年度供暖面积台账"},
            {"label": "建筑围护结构保温性能差", "description": "外墙无保温或保温层老化、单层玻璃窗热损失大，建筑热负荷偏高。", "probability": 0.50, "check_method": "检查外墙保温状况和外窗类型"},
            {"label": "供暖季延长或极端天气", "description": "当年供暖季天数增加或遇到极端低温天气，供暖需求增大。", "probability": 0.35, "check_method": "对比当年供暖天数及采暖度日数"},
            {"label": "管网热损失大", "description": "室外供热管道保温层破损或老化，沿途热损失严重（正常<5%，异常可达15-20%）。", "probability": 0.30, "check_method": "检查管道保温状况，测试供回水温差"},
            {"label": "锅炉效率下降", "description": "锅炉长期运行后换热面积灰/结垢、燃烧器效率下降，燃料消耗增加。", "probability": 0.25, "check_method": "测试锅炉热效率，正常应>85%"},
        ],
        "measures": [
            {"label": "增加外墙外保温", "description": "对无保温或保温失效的建筑增加外墙外保温系统。", "estimated_saving_rate": "15-30%（供暖）", "investment_level": "高", "payback_period": "5-8年"},
            {"label": "更换节能外窗", "description": "将单层玻璃窗更换为中空Low-E玻璃窗。", "estimated_saving_rate": "10-20%（供暖）", "investment_level": "高", "payback_period": "5-10年"},
            {"label": "供热管道保温修复", "description": "修复或更换破损的管道保温层，减少沿途热损失。", "estimated_saving_rate": "5-10%", "investment_level": "低", "payback_period": "1-2年"},
            {"label": "锅炉清洗及效率测试", "description": "清洗锅炉换热面，测试并调整燃烧器，恢复额定效率。", "estimated_saving_rate": "3-8%", "investment_level": "低", "payback_period": "1年内"},
        ],
        "sources": ["DB37/T 2673-2019", "GB 50189-2015"],
    },
    # ==================== 照明系统 ====================
    {
        "anomaly_description": "照明电耗偏高",
        "anomaly_keywords": ["照明", "灯光", "灯具", "LED", "荧光灯", "路灯"],
        "energy_type": "电",
        "system": "照明系统",
        "causes": [
            {"label": "LED灯具占比低", "description": "大量使用T8/T5荧光灯甚至白炽灯，发光效率低。LED灯具光效可达100-130 lm/W，荧光灯仅60-80 lm/W。", "probability": 0.75, "check_method": "统计各区域灯具类型和数量"},
            {"label": "照明时间过长", "description": "公共区域24小时常亮，或自然采光良好的区域仍开灯。缺少定时/感应控制。", "probability": 0.50, "check_method": "抽查各时段灯具开启情况"},
            {"label": "照度过高", "description": "设计照度远超国家标准要求，灯具功率密度偏大。", "probability": 0.20, "check_method": "实测照度与GB 50034要求比较"},
        ],
        "measures": [
            {"label": "全面更换LED灯具", "description": "将荧光灯全部更换为高光效LED灯具，投资回收期通常1-2年。", "estimated_saving_rate": "40-60%（照明）", "investment_level": "中", "payback_period": "1-2年"},
            {"label": "加装智能照明控制", "description": "公共区域加装红外感应/微波雷达开关，走廊楼梯间采用声光控延时开关。", "estimated_saving_rate": "20-40%（公共区照明）", "investment_level": "低", "payback_period": "1-2年"},
            {"label": "充分利用自然采光", "description": "靠窗区域独立回路控制，白天利用自然光，减少人工照明。", "estimated_saving_rate": "10-20%", "investment_level": "低", "payback_period": "1年内"},
        ],
        "sources": ["DB37/T 2673-2019", "GB 50034-2013"],
    },
    # ==================== 给排水系统 ====================
    {
        "anomaly_description": "用水量同比大幅增加（≥30%）",
        "anomaly_keywords": ["用水", "水耗", "水量", "漏水", "管道", "灌溉"],
        "energy_type": "水",
        "system": "给排水系统",
        "causes": [
            {"label": "地下管道漏水", "description": "埋地给水管道年久腐蚀渗漏，隐蔽性强、不易发现。通常表现为无设备运行时水表仍缓慢转动。", "probability": 0.60, "check_method": "关闭所有用水点，观察水表是否转动"},
            {"label": "新增用水设备或人员", "description": "新增建筑投用、用能人数增加（如医院扩建床位），用水量自然增长。", "probability": 0.45, "check_method": "核对用能人数变化和设备增减记录"},
            {"label": "绿化灌溉方式粗放", "description": "采用大水漫灌方式，水资源利用率低。改用喷灌/滴灌可节水30-50%。", "probability": 0.35, "check_method": "现场查看灌溉方式"},
            {"label": "卫生洁具非节水型", "description": "使用老式蹲便器（冲水量>11L/次）、非节水型水龙头等。", "probability": 0.30, "check_method": "检查卫生洁具型号及用水效率等级"},
        ],
        "measures": [
            {"label": "水平衡测试，查找漏点", "description": "委托专业机构进行水平衡测试，定位并修复漏点。", "estimated_saving_rate": "视漏损程度", "investment_level": "中", "payback_period": "视情况"},
            {"label": "更换节水型卫生洁具", "description": "更换为一级水效的节水型便器和水龙头。", "estimated_saving_rate": "20-40%（洁具用水）", "investment_level": "中", "payback_period": "1-2年"},
            {"label": "改用喷灌/滴灌系统", "description": "绿化区域安装喷灌或滴灌系统，替代大水漫灌。", "estimated_saving_rate": "30-50%（绿化用水）", "investment_level": "低", "payback_period": "1-2年"},
        ],
        "sources": ["DB37/T 4452-2021", "省立医院东院-2024"],
    },
    # ==================== 变配电系统 ====================
    {
        "anomaly_description": "变压器负载率偏低",
        "anomaly_keywords": ["变压器", "负载率", "空载", "轻载", "变压器损耗"],
        "energy_type": "电",
        "system": "变配电系统",
        "causes": [
            {"label": "变压器容量配置过大", "description": "设计阶段按最大负荷选取变压器，实际负载率长期<30%，变压器自身空载损耗占比较高。", "probability": 0.65, "check_method": "查看变压器运行记录，计算负载率"},
            {"label": "季节性负荷差异大", "description": "制冷季与非制冷季负荷差异悬殊，非制冷季变压器严重轻载。", "probability": 0.40, "check_method": "对比制冷季与非制冷季负载率"},
        ],
        "measures": [
            {"label": "非制冷季停运部分变压器", "description": "在低负荷季节停运部分变压器，由其联络开关由其他变压器代供，减少空载损耗。", "estimated_saving_rate": "5-10%（配电损耗）", "investment_level": "零投资", "payback_period": "即时"},
            {"label": "更换为高效变压器", "description": "将老旧S7/S9型变压器更换为SCB13/SH15型，空载损耗可降低30-50%。", "estimated_saving_rate": "30-50%（变压器损耗）", "investment_level": "高", "payback_period": "5-8年"},
        ],
        "sources": ["DB37/T 2673-2019"],
    },
    # ==================== 建筑围护结构 ====================
    {
        "anomaly_description": "建筑围护结构热工性能差",
        "anomaly_keywords": ["围护结构", "保温", "外墙", "外窗", "单层玻璃", "砖混"],
        "energy_type": "电",
        "system": "建筑围护结构",
        "causes": [
            {"label": "外墙无保温或保温层老化", "description": "老旧建筑外墙无保温层，传热系数K值远超现行节能标准要求。", "probability": 0.70, "check_method": "查看竣工图纸及保温设计"},
            {"label": "单层玻璃外窗", "description": "使用单层普通玻璃窗，传热系数K≈5.7W/(m²·K)，远高于中空Low-E窗的1.8-2.5。", "probability": 0.65, "check_method": "现场查看外窗类型"},
            {"label": "建筑气密性差", "description": "门窗缝隙大，冷风渗透严重，增加供暖和制冷负荷。", "probability": 0.35, "check_method": "红外热成像或鼓风门法测试"},
        ],
        "measures": [
            {"label": "增加外墙外保温", "description": "外贴EPS/XPS保温板或喷涂聚氨酯保温层。", "estimated_saving_rate": "15-30%（供暖制冷）", "investment_level": "高", "payback_period": "5-8年"},
            {"label": "更换中空Low-E玻璃窗", "description": "将单层玻璃更换为断桥铝+中空Low-E玻璃窗。", "estimated_saving_rate": "10-20%（供暖制冷）", "investment_level": "高", "payback_period": "5-10年"},
            {"label": "门窗密封条更换", "description": "更换老化的门窗密封条，减少冷风渗透。", "estimated_saving_rate": "3-5%", "investment_level": "低", "payback_period": "1年内"},
        ],
        "sources": ["GB 50189-2015", "省立医院东院-2024"],
    },
    # ==================== 能耗监测系统 ====================
    {
        "anomaly_description": "能耗监测系统缺失",
        "anomaly_keywords": ["监测", "计量", "分项", "分户", "能源管理", "平台"],
        "energy_type": "电",
        "system": "能耗监测系统",
        "causes": [
            {"label": "尚未建设能耗监测平台", "description": "能耗数据靠人工抄表统计，无法实现分项分户计量和实时监测。", "probability": 0.85, "check_method": "确认是否有能耗在线监测系统"},
            {"label": "计量器具配备不足", "description": "未按GB 17167要求配备能源计量器具，缺少分类、分项计量点。", "probability": 0.50, "check_method": "对照GB 17167检查计量器具配备率"},
        ],
        "measures": [
            {"label": "建设能耗在线监测系统", "description": "安装智能电表/水表/气表，搭建能耗监测平台，实现分项计量和实时监测。", "estimated_saving_rate": "5-10%（管理节能）", "investment_level": "高", "payback_period": "3-5年"},
            {"label": "按GB 17167配齐计量器具", "description": "完善一、二、三级能源计量器具配备，实现用能精细化管理。", "estimated_saving_rate": "管理基础", "investment_level": "中", "payback_period": "2-3年"},
        ],
        "sources": ["DB37/T 2673-2019", "GB 17167-2006"],
    },
    # ==================== 季节性异常 ====================
    {
        "anomaly_description": "夏季电耗尖峰（月电耗超出均值50%以上）",
        "anomaly_keywords": ["夏季", "尖峰", "制冷", "高峰", "空调用电"],
        "energy_type": "电",
        "system": "中央空调系统",
        "causes": [
            {"label": "空调制冷季满负荷运行", "description": "夏季高温时段全部空调设备满负荷运行，电耗达到全年峰值。", "probability": 0.80, "check_method": "对比往年同月电耗走势"},
            {"label": "空调设备老旧能效低", "description": "老旧空调设备能效比远低于现行标准，同样制冷量消耗更多电力。", "probability": 0.40, "check_method": "实测冷机运行COP，与额定值比较"},
            {"label": "缺少蓄冷调峰措施", "description": "未利用峰谷电价差异，全部在高峰时段运行。可考虑冰蓄冷/水蓄冷。", "probability": 0.25, "check_method": "分析峰谷用电量占比"},
        ],
        "measures": [
            {"label": "优化制冷运行策略", "description": "根据室外温度和室内负荷预冷/提前启停，避免尖峰时段集中运行。", "estimated_saving_rate": "5-10%", "investment_level": "零投资", "payback_period": "即时"},
            {"label": "更换高效冷机", "description": "将COP<4.0的老旧冷机更换为COP≥6.0的高效机组。", "estimated_saving_rate": "20-30%（冷机电耗）", "investment_level": "高", "payback_period": "3-5年"},
        ],
        "sources": ["省立医院东院-2024"],
    },
    {
        "anomaly_description": "冬季电耗偏高",
        "anomaly_keywords": ["冬季", "电耗", "电辅热", "热泵", "低温"],
        "energy_type": "电",
        "system": "供暖系统",
        "causes": [
            {"label": "电辅热或热泵供暖", "description": "部分区域采用电热锅炉、空气源热泵等电驱动供暖设备，冬季电耗自然偏高。", "probability": 0.60, "check_method": "核实用电供暖设备类型和功率"},
            {"label": "热泵效率下降（低温工况）", "description": "空气源热泵在低温环境下COP急剧下降，实际制热量不足，需电辅热补充。", "probability": 0.40, "check_method": "对比热泵额定COP与实际COP"},
        ],
        "measures": [
            {"label": "热泵低温工况性能评估", "description": "评估热泵在当地最低气温下的实际COP，若<2.0则考虑更换或增加辅助热源。", "estimated_saving_rate": "视评估结果", "investment_level": "中", "payback_period": "视情况"},
        ],
        "sources": ["DB37/T 2673-2019"],
    },
    # ==================== 天然气 ====================
    {
        "anomaly_description": "天然气用量大幅增加（≥30%）",
        "anomaly_keywords": ["天然气", "燃气", "锅炉", "食堂", "蒸汽"],
        "energy_type": "天然气",
        "system": "供暖系统",
        "causes": [
            {"label": "燃气锅炉效率下降", "description": "锅炉长期运行换热面积灰、燃烧器调节不当，排烟温度升高，效率下降。", "probability": 0.55, "check_method": "测试锅炉排烟温度和过量空气系数"},
            {"label": "供暖面积或用气点增加", "description": "新增用气建筑（如新建食堂、供应室蒸汽消毒等），总用气量上升。", "probability": 0.50, "check_method": "核对各用气点变化"},
            {"label": "管道泄漏", "description": "埋地燃气管线微漏，不易察觉但持续损失。", "probability": 0.15, "check_method": "燃气公司定期巡检记录，或甲烷检测仪检查"},
        ],
        "measures": [
            {"label": "锅炉清洗及燃烧器调试", "description": "清洗换热面，调整空燃比和燃烧器，恢复额定效率。", "estimated_saving_rate": "5-10%", "investment_level": "低", "payback_period": "1年内"},
            {"label": "燃气管道检漏", "description": "委托燃气公司进行全线检漏，修复泄漏点。", "estimated_saving_rate": "视漏损程度", "investment_level": "中", "payback_period": "即刻止损"},
        ],
        "sources": ["DB37/T 2673-2019"],
    },
    # ==================== 可再生能源 ====================
    {
        "anomaly_description": "可再生能源利用空白",
        "anomaly_keywords": ["可再生", "光伏", "太阳能", "光热", "新能源", "地源热泵"],
        "energy_type": "电",
        "system": "可再生能源",
        "causes": [
            {"label": "未建设分布式光伏发电", "description": "屋顶资源空置，未利用光伏发电降低外购电比例。", "probability": 0.70, "check_method": "查看屋顶可利用面积"},
            {"label": "未利用太阳能热水", "description": "医院生活热水仍全部由燃气锅炉或电加热供给，未用太阳能光热。", "probability": 0.55, "check_method": "确认现有生活热水热源"},
        ],
        "measures": [
            {"label": "建设屋顶分布式光伏", "description": "利用建筑屋顶安装分布式光伏发电系统，自发自用、余电上网。", "estimated_saving_rate": "视屋顶面积和日照条件", "investment_level": "高", "payback_period": "5-8年"},
            {"label": "加装太阳能热水系统", "description": "在屋顶安装太阳能集热器，作为生活热水预热，减少燃气/电加热消耗。", "estimated_saving_rate": "30-50%（热水能耗）", "investment_level": "中", "payback_period": "3-5年"},
        ],
        "sources": ["DB37/T 2673-2019", "省立医院东院-2024"],
    },
    # ==================== 生活热水系统 ====================
    {
        "anomaly_description": "生活热水能耗偏高",
        "anomaly_keywords": ["生活热水", "热水", "淋浴", "洗澡水", "开水器"],
        "energy_type": "天然气",
        "system": "供暖系统",
        "causes": [
            {"label": "热水供水温度过高", "description": "热水供水温度超过60℃，热损失大且存在烫伤风险。规范建议55-60℃。", "probability": 0.55, "check_method": "实测热水供水温度"},
            {"label": "热水循环泵24小时运行", "description": "循环泵全天候运行，非用水时段无效循环造成热量和电力浪费。", "probability": 0.50, "check_method": "查看循环泵运行时间表"},
            {"label": "热水管网保温不良", "description": "管道保温层老化或厚度不足，沿途散热严重。", "probability": 0.40, "check_method": "红外热成像检查管道表面温度"},
            {"label": "未利用太阳能预热", "description": "未安装太阳能热水系统，全部热负荷由燃气锅炉承担。", "probability": 0.35, "check_method": "确认现有热源方式"},
        ],
        "measures": [
            {"label": "降低热水供水温度", "description": "将热水供水温度从>65℃降至55-60℃，减少散热损失和结垢。", "estimated_saving_rate": "5-10%", "investment_level": "零投资", "payback_period": "即时"},
            {"label": "热水循环泵定时控制", "description": "加装时控开关，非高峰时段（如夜间）停运循环泵。", "estimated_saving_rate": "10-20%（泵耗）", "investment_level": "低", "payback_period": "1年内"},
            {"label": "热水管网保温修复", "description": "更换破损保温层，管道阀门加装保温套。", "estimated_saving_rate": "5-15%", "investment_level": "低", "payback_period": "1-2年"},
            {"label": "加装太阳能热水系统", "description": "屋顶安装太阳能集热器作为预热，减少燃气消耗30-50%。", "estimated_saving_rate": "30-50%", "investment_level": "中", "payback_period": "3-5年"},
        ],
        "sources": ["DB37/T 2673-2019", "工程经验"],
    },
    # ==================== 电梯系统 ====================
    {
        "anomaly_description": "电梯能耗偏高",
        "anomaly_keywords": ["电梯", "垂直交通", "乘客电梯", "货梯"],
        "energy_type": "电",
        "system": "办公设备",
        "causes": [
            {"label": "电梯老旧能效低", "description": "使用交流双速或老式变频梯，能耗是新一代永磁同步电梯的1.5-2倍。", "probability": 0.60, "check_method": "查电梯铭牌型号及出厂年份"},
            {"label": "电梯待机时间过长", "description": "多台电梯全天运行，低峰时段（夜间/周末）仍全部投运。", "probability": 0.45, "check_method": "统计电梯运行时段"},
            {"label": "未安装能量回馈装置", "description": "电梯制动能量以电阻发热形式消耗，未回馈电网。", "probability": 0.30, "check_method": "查看电梯控制系统是否有回馈单元"},
        ],
        "measures": [
            {"label": "低峰时段停运部分电梯", "description": "夜间/周末仅保留值班电梯运行，其余停梯。", "estimated_saving_rate": "10-20%（电梯总耗）", "investment_level": "零投资", "payback_period": "即时"},
            {"label": "加装能量回馈装置", "description": "安装电梯能量回馈单元，将制动能量回馈电网，可节电15-30%。", "estimated_saving_rate": "15-30%（电梯耗电）", "investment_level": "中", "payback_period": "2-3年"},
            {"label": "更换为永磁同步电梯", "description": "老旧电梯大修或更新时选用PM同步无齿轮曳引机，能效提升30-50%。", "estimated_saving_rate": "30-50%", "investment_level": "高", "payback_period": "5-8年"},
        ],
        "sources": ["工程经验"],
    },
    # ==================== 医疗设备（医院专用） ====================
    {
        "anomaly_description": "医疗设备待机功耗大",
        "anomaly_keywords": ["医疗设备", "CT", "MRI", "X光", "彩超", "DR", "待机", "医疗"],
        "energy_type": "电",
        "system": "医疗设备",
        "causes": [
            {"label": "大型设备24小时待机", "description": "CT/MRI等大型影像设备全天待机，待机功耗可达1-5kW/台。非工作时间可完全断电。", "probability": 0.70, "check_method": "统计设备待机时长和待机功率"},
            {"label": "设备间空调独立运行", "description": "设备间精密空调无集中控制，与设备待机同步运行，造成双重浪费。", "probability": 0.45, "check_method": "检查设备间空调控制方式"},
        ],
        "measures": [
            {"label": "非工作时间切断大型设备电源", "description": "CT/MRI等设备在非工作时间（夜间+周末）完全断电（需确认无冷却保护要求）。", "estimated_saving_rate": "30-50%（设备待机能耗）", "investment_level": "零投资", "payback_period": "即时"},
            {"label": "设备间空调联动控制", "description": "设备间空调与设备启停联动，设备断电后空调自动停机或降频。", "estimated_saving_rate": "20-40%（设备间空调）", "investment_level": "低", "payback_period": "1年内"},
        ],
        "sources": ["省立医院东院-2024", "工程经验"],
    },
    # ==================== 信息机房 ====================
    {
        "anomaly_description": "信息机房PUE偏高",
        "anomaly_keywords": ["机房", "数据中心", "服务器", "UPS", "PUE", "信息中心"],
        "energy_type": "电",
        "system": "信息机房",
        "causes": [
            {"label": "机房空调效率低", "description": "使用老式定频精密空调，全年制冷，未利用自然冷源。PUE>2.0属高能耗。", "probability": 0.65, "check_method": "计算PUE值（总用电/IT设备用电）"},
            {"label": "服务器上架率低", "description": "大量服务器空闲运行，IT负载率<30%，但配套空调和UPS仍按设计容量运行。", "probability": 0.50, "check_method": "统计服务器CPU/内存利用率"},
            {"label": "UPS效率偏低", "description": "老旧UPS满载效率<90%，且长期轻载运行（<30%负载）效率降至80%以下。", "probability": 0.35, "check_method": "查看UPS效率曲线和实际负载率"},
        ],
        "measures": [
            {"label": "优化气流组织", "description": "采用冷热通道封闭，减少冷热风混合，提升空调回风温度，降低制冷能耗。", "estimated_saving_rate": "15-25%（机房制冷）", "investment_level": "中", "payback_period": "2-3年"},
            {"label": "利用自然冷源", "description": "过渡季和冬季启用新风直接冷却或板式换热器，减少压缩机制冷时间。", "estimated_saving_rate": "20-40%（冬季制冷）", "investment_level": "中", "payback_period": "2-3年"},
            {"label": "整合/虚拟化服务器", "description": "将低负载服务器整合或虚拟化，关闭空闲物理机。", "estimated_saving_rate": "20-40%（IT设备）", "investment_level": "低", "payback_period": "1-2年"},
            {"label": "更换高效模块化UPS", "description": "更换为效率>96%的模块化UPS，支持按实际负载热插拔扩容。", "estimated_saving_rate": "5-10%（UPS损耗）", "investment_level": "高", "payback_period": "3-5年"},
        ],
        "sources": ["GB 50174-2017", "工程经验"],
    },
    # ==================== 厨房系统 ====================
    {
        "anomaly_description": "厨房用能偏高",
        "anomaly_keywords": ["厨房", "食堂", "餐厅", "排风", "排烟", "灶具", "蒸箱"],
        "energy_type": "天然气",
        "system": "厨房系统",
        "causes": [
            {"label": "排风系统能耗大", "description": "厨房排油烟风机功率大且全天运行，非烹饪时段仍高速运转。", "probability": 0.60, "check_method": "查看排风机运行时间表和变频设置"},
            {"label": "厨房设备老旧效率低", "description": "使用老式灶具、蒸箱，热效率仅30-40%，远低于新型节能灶具的60-70%。", "probability": 0.55, "check_method": "查看厨房设备型号及能效等级"},
        ],
        "measures": [
            {"label": "排风机加装变频控制", "description": "根据油烟浓度或烹饪时段自动调节风机转速，非高峰低速运行。", "estimated_saving_rate": "30-50%（排风电耗）", "investment_level": "中", "payback_period": "1-2年"},
            {"label": "更换节能灶具", "description": "更换为高效燃烧灶具，余热回收型蒸箱等。", "estimated_saving_rate": "20-30%（厨房燃气）", "investment_level": "中", "payback_period": "2-3年"},
        ],
        "sources": ["工程经验"],
    },
    # ==================== 办公设备 ====================
    {
        "anomaly_description": "办公设备待机功耗大",
        "anomaly_keywords": ["办公", "电脑", "打印机", "饮水机", "空调", "待机", "下班"],
        "energy_type": "电",
        "system": "办公设备",
        "causes": [
            {"label": "办公设备下班未断电", "description": "电脑、打印机、饮水机等常年24小时通电，待机功耗约占总用电5-10%。", "probability": 0.75, "check_method": "下班后抽查办公室设备通电情况"},
            {"label": "分体空调下班未关", "description": "办公区域分体空调下班后无人关闭，空运行消耗大量电能。", "probability": 0.55, "check_method": "下班后巡查空调运行情况"},
        ],
        "measures": [
            {"label": "安装智能插座/定时器", "description": "办公设备统一接入智能插座，定时通断电（如工作日20:00-07:00断电）。", "estimated_saving_rate": "80-100%（待机能耗）", "investment_level": "低", "payback_period": "3-6个月"},
            {"label": "建立下班断电制度", "description": "纳入日常管理，张贴'下班断电'提示，定期检查通报。", "estimated_saving_rate": "管理措施", "investment_level": "零投资", "payback_period": "即时"},
        ],
        "sources": ["工程经验"],
    },
    # ==================== 空调末端 ====================
    {
        "anomaly_description": "空调末端缺乏分区控制",
        "anomaly_keywords": ["末端", "风机盘管", "温控器", "分区", "独立控制", "三速开关"],
        "energy_type": "电",
        "system": "中央空调系统",
        "causes": [
            {"label": "无独立温控器", "description": "风机盘管仅有三速开关手动调节，无温度设定和自动启停功能，室内过冷/过热浪费严重。", "probability": 0.70, "check_method": "查看末端控制面板类型"},
            {"label": "公共区域无集中管理", "description": "走廊、大厅等公共区域空调末端常开，无分时分区控制。", "probability": 0.45, "check_method": "现场查看公共区域空调控制方式"},
        ],
        "measures": [
            {"label": "末端加装联网温控器", "description": "风机盘管加装联网温控器，支持分时分区设定温度和自动启停。", "estimated_saving_rate": "15-25%（末端能耗）", "investment_level": "中", "payback_period": "2-3年"},
            {"label": "公共区域分时控制", "description": "走廊等过渡空间空调设置运行时段（如工作时段运行，夜间/周末停运）。", "estimated_saving_rate": "10-20%", "investment_level": "低", "payback_period": "1年内"},
        ],
        "sources": ["省立医院东院-2024", "DB37/T 2673-2019"],
    },
    {
        "anomaly_description": "新风系统未设热回收",
        "anomaly_keywords": ["新风", "排风", "热回收", "全热交换", "能量回收"],
        "energy_type": "电",
        "system": "中央空调系统",
        "causes": [
            {"label": "新风与排风无能量交换", "description": "新风处理能耗占空调总能耗20-40%，排风中大量冷/热量直接排出室外，未回收利用。", "probability": 0.65, "check_method": "检查新风机组是否配备热回收装置"},
            {"label": "新风量过大", "description": "设计新风量远超实际需求，或新风阀无法调节，造成过度通风。", "probability": 0.35, "check_method": "实测新风量，对比GB 50736标准"},
        ],
        "measures": [
            {"label": "加装排风热回收装置", "description": "在新风和排风管道间加装全热交换器（转轮式或板式），回收排风冷热量，热回收效率可达60-70%。", "estimated_saving_rate": "15-25%（新风能耗）", "investment_level": "中", "payback_period": "2-3年"},
            {"label": "按需控制新风量", "description": "根据室内CO2浓度或人员数量自动调节新风阀开度，减少过度通风。", "estimated_saving_rate": "10-20%", "investment_level": "中", "payback_period": "1-2年"},
        ],
        "sources": ["GB 50189-2015"],
    },
    # ==================== 水泵系统 ====================
    {
        "anomaly_description": "水泵效率偏低或未变频",
        "anomaly_keywords": ["水泵", "冷冻泵", "冷却泵", "变频", "工频", "定频", "扬程"],
        "energy_type": "电",
        "system": "中央空调系统",
        "causes": [
            {"label": "水泵无变频控制", "description": "水泵工频定速运行，无论末端负荷大小均满转速运转，输配能耗浪费严重。", "probability": 0.70, "check_method": "查看水泵控制柜是否有变频器"},
            {"label": "水泵扬程选型过大", "description": "设计阶段水泵扬程安全余量过大（超30%），实际运行效率仅60-70%。", "probability": 0.45, "check_method": "实测水泵扬程与铭牌扬程比较"},
            {"label": "多泵并联无自动加减", "description": "多台水泵常年全部运行，未根据负荷自动投切，低负荷时每台泵均处于低效区。", "probability": 0.35, "check_method": "查看水泵运行台数和控制逻辑"},
        ],
        "measures": [
            {"label": "加装变频器", "description": "为冷冻泵/冷却泵加装变频器，根据供回水温差或压差自动调速。", "estimated_saving_rate": "20-40%（水泵电耗）", "investment_level": "中", "payback_period": "1-2年"},
            {"label": "更换高效水泵", "description": "更换为IE4/IE5超高效率电机，或切削叶轮降低扬程至实际需求。", "estimated_saving_rate": "10-20%", "investment_level": "中", "payback_period": "2-3年"},
            {"label": "优化加减机逻辑", "description": "根据流量需求自动投切水泵台数，保证每台运行泵在高效区间。", "estimated_saving_rate": "10-15%", "investment_level": "低", "payback_period": "1年内"},
        ],
        "sources": ["DB37/T 2673-2019", "省立医院东院-2024"],
    },
    # ==================== 冷却塔 ====================
    {
        "anomaly_description": "冷却塔风机无变频控制",
        "anomaly_keywords": ["冷却塔", "风机", "冷却风扇", "变频", "定频"],
        "energy_type": "电",
        "system": "中央空调系统",
        "causes": [
            {"label": "冷却塔风机定频运行", "description": "风机恒速运行，过渡季节或低负荷时过度冷却，既浪费风机电力又可能导致冷却水温过低影响冷机效率。", "probability": 0.65, "check_method": "查看冷却塔风机控制方式"},
            {"label": "冷却塔布水不均匀", "description": "布水器堵塞或损坏，冷却水未均匀分布在填料上，部分填料未参与换热。", "probability": 0.30, "check_method": "打开冷却塔检修门观察布水情况"},
        ],
        "measures": [
            {"label": "冷却塔风机加装变频", "description": "根据冷却水出水温度自动调节风机转速，维持设定温度，避免过度冷却。", "estimated_saving_rate": "20-40%（冷却塔风机）", "investment_level": "中", "payback_period": "1-2年"},
            {"label": "定期清洗布水器", "description": "每季度检查并清洗布水器喷头，确保均匀布水、充分利用填料换热面积。", "estimated_saving_rate": "3-5%", "investment_level": "低", "payback_period": "1年内"},
        ],
        "sources": ["工程经验"],
    },
    # ==================== 给排水扩展 ====================
    {
        "anomaly_description": "供水系统压力偏高",
        "anomaly_keywords": ["给水", "供水系统", "供水压力", "超压", "减压阀", "变频供水", "恒压供水"],
        "energy_type": "电",
        "system": "给排水系统",
        "causes": [
            {"label": "供水泵无变频恒压控制", "description": "供水泵工频全速运行，实际供水压力远超末端需求（正常0.3-0.35MPa），既浪费电能又增加管网漏损风险。", "probability": 0.60, "check_method": "实测最不利点供水压力"},
            {"label": "未分区供水", "description": "高低区共用一套供水系统，低区超压严重，需减压阀减压，造成能量浪费。", "probability": 0.40, "check_method": "查看给水系统分区图"},
        ],
        "measures": [
            {"label": "供水泵加装变频恒压控制", "description": "根据管网压力自动调节水泵转速，维持恒定供水压力。", "estimated_saving_rate": "20-30%（供水泵电耗）", "investment_level": "中", "payback_period": "1-2年"},
            {"label": "高低区分区供水", "description": "高区和低区分设独立供水系统，低区由市政直供或单独变频泵组供水。", "estimated_saving_rate": "10-20%", "investment_level": "中", "payback_period": "2-3年"},
        ],
        "sources": ["DB37/T 4452-2021"],
    },
    # ==================== 变配电扩展 ====================
    {
        "anomaly_description": "功率因数偏低",
        "anomaly_keywords": ["功率因数", "无功", "电容", "补偿", "电费", "力调"],
        "energy_type": "电",
        "system": "变配电系统",
        "causes": [
            {"label": "无功补偿不足或失效", "description": "电容补偿柜容量不足或电容器老化失效，功率因数低于0.9，被供电公司加收力调电费。", "probability": 0.60, "check_method": "查看电费单力调电费栏或实测功率因数"},
            {"label": "大量感性负载未就近补偿", "description": "水泵、风机等大功率电机未装就地补偿电容器，无功电流长距离传输增加线损。", "probability": 0.40, "check_method": "查看主要电机就地补偿装置"},
        ],
        "measures": [
            {"label": "修复/增容无功补偿柜", "description": "更换老化电容器，增设自动投切控制器，目标功率因数≥0.95。", "estimated_saving_rate": "减免力调电费+降低线损1-3%", "investment_level": "中", "payback_period": "1-2年"},
            {"label": "大电机加装就地补偿", "description": "≥30kW电机加装就地补偿电容器，降低线路无功电流。", "estimated_saving_rate": "降低线损1-2%", "investment_level": "低", "payback_period": "1-2年"},
        ],
        "sources": ["GB 50052-2009", "工程经验"],
    },
    # ==================== 供暖扩展 ====================
    {
        "anomaly_description": "供热管网水力失衡",
        "anomaly_keywords": ["水力失衡", "供热不均", "近热远冷", "冷热不均", "水力失调", "管网", "管路"],
        "energy_type": "热",
        "system": "供暖系统",
        "causes": [
            {"label": "未进行水力平衡调试", "description": "供热管网未装平衡阀或调试不到位，近端过热（开窗散热）、远端不热（投诉多），总供热量浪费严重。", "probability": 0.65, "check_method": "抽查各末端室温差异，近远端温差>5℃为失衡"},
            {"label": "管网管径设计不合理", "description": "支管管径偏小或偏大，各环路阻力差异大，无法自然平衡。", "probability": 0.30, "check_method": "查看管网竣工图"},
        ],
        "measures": [
            {"label": "水力平衡调试", "description": "安装/调节静态平衡阀和动态压差控制阀，使各环路流量分配均匀。", "estimated_saving_rate": "10-20%（供热能耗）", "investment_level": "中", "payback_period": "1-2年"},
            {"label": "增设气候补偿控制", "description": "根据室外温度自动调节供水温度，避免定温供水造成的过度供热。", "estimated_saving_rate": "5-10%", "investment_level": "中", "payback_period": "2-3年"},
        ],
        "sources": ["DB37/T 2673-2019"],
    },
    # ==================== 围护结构扩展 ====================
    {
        "anomaly_description": "屋面保温隔热不足",
        "anomaly_keywords": ["屋面", "屋顶", "顶层", "隔热", "暴晒", "晒透"],
        "energy_type": "电",
        "system": "建筑围护结构",
        "causes": [
            {"label": "屋面保温层厚度不足", "description": "老旧建筑屋面保温层薄或无保温，夏季顶层房间空调负荷比中间层高30-50%。", "probability": 0.60, "check_method": "查看顶层与中间层空调能耗差异"},
            {"label": "屋面防水老化破坏保温", "description": "屋面防水层破损后雨水渗入保温层，保温材料受潮后隔热性能大幅下降。", "probability": 0.35, "check_method": "检查屋面是否有渗漏痕迹"},
        ],
        "measures": [
            {"label": "屋面增加保温隔热层", "description": "在屋面上方增加XPS挤塑板或喷涂聚氨酯保温层，上做防水保护层。", "estimated_saving_rate": "10-20%（顶层空调）", "investment_level": "高", "payback_period": "5-8年"},
            {"label": "屋面增加反射隔热涂料", "description": "涂刷高反射隔热涂料，减少太阳辐射得热，降低屋面温度10-15℃。", "estimated_saving_rate": "5-10%（顶层空调）", "investment_level": "低", "payback_period": "2-3年"},
        ],
        "sources": ["GB 50189-2015"],
    },
    # ==================== 空调系统扩展 ====================
    {
        "anomaly_description": "冷机选型过大",
        "anomaly_keywords": ["选型", "过大", "大马拉小车", "装机容量", "设计余量"],
        "energy_type": "电",
        "system": "中央空调系统",
        "causes": [
            {"label": "设计冷负荷计算偏大", "description": "设计阶段安全系数叠加过多，实际峰值负荷仅占装机容量60-70%，冷机长期在低效区运行。", "probability": 0.65, "check_method": "对比设计冷负荷与实际运行最大负荷"},
            {"label": "建筑功能变更后负荷下降", "description": "建筑使用功能或人流量变化，实际冷负荷已低于设计值。", "probability": 0.30, "check_method": "统计建筑实际使用率变化"},
        ],
        "measures": [
            {"label": "以实际负荷重新核算", "description": "委托专业公司做全年负荷模拟，根据实际需求调整冷机运行组合。", "estimated_saving_rate": "10-20%", "investment_level": "中", "payback_period": "2-3年"},
            {"label": "加装小冷机做基载", "description": "增设一台小容量高效磁悬浮冷机承担低负荷时段（春秋过渡季），避免大冷机频繁启停。", "estimated_saving_rate": "15-25%（过渡季）", "investment_level": "高", "payback_period": "3-5年"},
        ],
        "sources": ["工程经验"],
    },
    # ==================== 综合管理 ====================
    {
        "anomaly_description": "未建立能源管理体系",
        "anomaly_keywords": ["能源管理", "管理体系", "管理岗位", "定额考核", "节能目标", "管理制度", "能源审计"],
        "energy_type": "电",
        "system": "能耗监测系统",
        "causes": [
            {"label": "无专职能源管理岗位", "description": "能源管理职责不明确，能耗数据仅用于缴费，未做分析和改进。", "probability": 0.70, "check_method": "询问是否设能源管理岗位"},
            {"label": "无能源消耗定额考核", "description": "各科室/部门用电无定额、无考核，用能行为缺乏约束。", "probability": 0.60, "check_method": "查看是否有科室能耗考核制度"},
            {"label": "未开展能源审计或水平衡测试", "description": "长期未进行专业能源审计，对用能系统效率和节能潜力缺乏系统了解。", "probability": 0.45, "check_method": "查看最近一次能源审计报告日期"},
        ],
        "measures": [
            {"label": "建立能源管理体系（GB/T 23331）", "description": "设立能源管理岗位，制定能源方针、目标和指标，定期开展能源评审。", "estimated_saving_rate": "3-10%（管理节能）", "investment_level": "低", "payback_period": "1年内"},
            {"label": "实行科室能耗定额考核", "description": "按面积/人数制定各科室月度用电定额，超额部分计入成本，节约奖励。", "estimated_saving_rate": "5-15%", "investment_level": "低", "payback_period": "1年内"},
        ],
        "sources": ["GB/T 23331-2020", "DB37/T 2673-2019"],
    },
]


# ============================================================
# EnergyKnowledgeGraph 核心类
# ============================================================

class EnergyKnowledgeGraph:
    """能源审计因果知识图谱"""

    def __init__(self):
        self.G = nx.MultiDiGraph()
        self.chains: List[CausalChain] = []
        self._anomaly_index: Dict[str, List[CausalChain]] = defaultdict(list)  # 关键词→因果链索引
        # v3.0 语义匹配
        self._chain_vectors: Any = None       # numpy array (N_chains x 1024)
        self._semantic_enabled: bool = False
        self._embed_fn: Any = None            # cached embedding function reference
        # v4.0 置信度自动更新
        self._feedback: Dict[str, dict] = {}  # {cause_label: {confirmed: N, rejected: N}}

    # ---- 数据加载 ----

    def load_builtin(self, build_vectors: bool = True) -> int:
        """加载预置因果链（内置50条）"""
        loaded = 0
        for chain_dict in INITIAL_CAUSAL_CHAINS:
            chain = self._dict_to_chain(chain_dict)
            self.add_chain(chain)
            loaded += 1
        if build_vectors:
            self._build_chain_vectors()
        else:
            self._semantic_enabled = False
        return loaded

    def load_from_json(self, path: str) -> int:
        """从JSON文件加载额外因果链"""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        loaded = 0
        for chain_dict in data.get('chains', []):
            chain = self._dict_to_chain(chain_dict)
            self.add_chain(chain)
            loaded += 1
        self._build_chain_vectors()
        return loaded

    def load(self, extra_path: str = None, build_vectors: bool = True) -> int:
        """
        加载知识图谱。
        1. 内置30条因果链
        2. 可选额外JSON文件

        Args:
            extra_path: 额外因果链 JSON 文件路径
            build_vectors: 是否预计算语义向量（默认 True；设为 False 可避免嵌入 API 调用）
        """
        total = self.load_builtin(build_vectors=build_vectors)
        if extra_path and os.path.exists(extra_path):
            total += self.load_from_json(extra_path)
        return total

    # ---- 因果链管理 ----

    def add_chain(self, chain: CausalChain):
        """添加因果链到图谱"""
        self.chains.append(chain)

        # 索引：异常关键词 → 因果链
        for kw in chain.anomaly_keywords:
            self._anomaly_index[kw.lower()].append(chain)

        # 图中添加节点和边
        anomaly_node = f"anomaly:{chain.anomaly_description}"
        if anomaly_node not in self.G:
            self.G.add_node(anomaly_node, type='anomaly',
                          label=chain.anomaly_description,
                          energy_type=chain.energy_type,
                          system=chain.system)

        for cause in chain.causes:
            cause_node = f"cause:{cause.id or cause.label}"
            if cause_node not in self.G:
                self.G.add_node(cause_node, type='cause',
                              label=cause.label,
                              probability=cause.probability,
                              check_method=cause.check_method)
            self.G.add_edge(anomaly_node, cause_node, relation='caused_by',
                          probability=cause.probability)

            for measure in chain.measures:
                measure_node = f"measure:{measure.id or measure.label}"
                if measure_node not in self.G:
                    self.G.add_node(measure_node, type='measure',
                                  label=measure.label,
                                  estimated_saving_rate=measure.estimated_saving_rate,
                                  investment_level=measure.investment_level)
                self.G.add_edge(cause_node, measure_node, relation='mitigated_by')

        # 异常之间相似关联（同系统）
        other_same_system = [
            c for c in self.chains
            if c.system == chain.system and c is not chain
        ]
        for other in other_same_system:
            other_anomaly = f"anomaly:{other.anomaly_description}"
            if other_anomaly in self.G:
                self.G.add_edge(anomaly_node, other_anomaly, relation='related_to')

    # ---- 诊断推理 ----

    def diagnose(self,
                 anomaly_description: str,
                 energy_type: str = "",
                 system: str = "",
                 top_k: int = 3) -> DiagnosisResult:
        """
        对一条能耗异常进行因果诊断。

        Args:
            anomaly_description: 异常描述文本（如 '冷机COP偏低'、"2023→2024年电耗+35%'）
            energy_type: 能源类型（可选，缩小匹配范围）
            system: 用能系统（可选）
            top_k: 返回前k个最可能原因

        Returns:
            DiagnosisResult: 包含匹配的因果链、最可能原因、建议措施
        """
        matched = self._match_chains_hybrid(anomaly_description, energy_type, system)

        if not matched:
            return DiagnosisResult(
                anomaly_description=anomaly_description,
                matched_chains=[],
            )

        # 取匹配度最高的因果链
        best_chain = matched[0]

        # 取前top_k个原因
        top_causes = best_chain.causes[:top_k]

        # 取这些原因对应的措施（去重）
        measure_labels = set()
        recommended_measures = []
        for cause in top_causes:
            for m in best_chain.measures:
                if m.label not in measure_labels:
                    measure_labels.add(m.label)
                    recommended_measures.append(m)

        return DiagnosisResult(
            anomaly_description=anomaly_description,
            matched_chains=matched[:3],
            primary_cause=top_causes[0] if top_causes else None,
            recommended_measures=recommended_measures[:5],
            confidence=top_causes[0].probability if top_causes else 0.0,
        )

    def diagnose_all(self,
                     anomalies: List[dict],
                     project_name: str = "") -> DiagnosisReport:
        """
        批量诊断多条异常。

        Args:
            anomalies: 异常列表，每项含 {'description': '...', 'energy_type': '电', ...}
            project_name: 项目名称

        Returns:
            DiagnosisReport: 包含所有异常诊断结果
        """
        results = []
        diagnosed = 0

        for a in anomalies:
            result = self.diagnose(
                anomaly_description=a.get('description', ''),
                energy_type=a.get('energy_type', ''),
                system=a.get('system', ''),
            )
            results.append(result)
            if result.has_diagnosis:
                diagnosed += 1

        return DiagnosisReport(
            project_name=project_name,
            total_anomalies=len(anomalies),
            diagnosed=diagnosed,
            undiagnosed=len(anomalies) - diagnosed,
            results=results,
        )

    # ---- 查询接口 ----

    def get_causes_tree(self, anomaly_keyword: str) -> dict:
        """
        获取异常的原因树（用于Graph可视化或嵌套展示）。
        """
        chains = self._anomaly_index.get(anomaly_keyword.lower(), [])
        if not chains:
            return {}
        chain = chains[0]
        return {
            'anomaly': chain.anomaly_description,
            'energy_type': chain.energy_type,
            'system': chain.system,
            'causes': [
                {
                    'label': c.label,
                    'probability': c.probability,
                    'check_method': c.check_method,
                    'measures': [
                        {'label': m.label, 'saving_rate': m.estimated_saving_rate}
                        for m in chain.measures
                    ],
                }
                for c in chain.causes
            ],
        }

    def get_measures_for_system(self, system: str) -> List[dict]:
        """获取某系统的所有节能措施（去重）"""
        seen = set()
        measures = []
        for chain in self.chains:
            if chain.system == system:
                for m in chain.measures:
                    if m.label not in seen:
                        seen.add(m.label)
                        measures.append({
                            'label': m.label,
                            'description': m.description,
                            'saving_rate': m.estimated_saving_rate,
                            'investment': m.investment_level,
                            'payback': m.payback_period,
                        })
        return measures

    # ---- 持久化 ----

    def save(self, path: str):
        """保存因果链到JSON文件"""
        data = {
            'chains': [self._chain_to_dict(c) for c in self.chains],
            'stats': {
                'total_chains': len(self.chains),
                'nodes': self.G.number_of_nodes(),
                'edges': self.G.number_of_edges(),
            }
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ---- 内部方法 ----

    def _match_chains(self,
                      description: str,
                      energy_type: str = "",
                      system: str = "") -> List[CausalChain]:
        """
        关键词匹配：异常描述 → 因果链。
        匹配策略（按优先级）：
        1. 精确关键词匹配
        2. 能源类型筛选
        3. 系统类型筛选
        """
        desc_lower = description.lower()
        scored: Dict[int, float] = {}

        for i, chain in enumerate(self.chains):
            score = 0
            # 关键词命中得分
            for kw in chain.anomaly_keywords:
                if kw.lower() in desc_lower:
                    score += 1
            # 能源类型匹配加分
            if energy_type and chain.energy_type == energy_type:
                score += 2
            # 系统匹配加分
            if system and chain.system == system:
                score += 2

            if score > 0:
                scored[i] = score

        # 按得分降序
        ranked = sorted(scored.items(), key=lambda x: x[1], reverse=True)
        return [self.chains[i] for i, _ in ranked]

    # ---- 语义匹配 v3.0 ----

    def _get_embed_fn(self):
        """延迟加载 embedding 函数（复用 rag_search 的 DashScope API）"""
        if self._embed_fn is not None:
            return self._embed_fn
        try:
            from rag.rag_search import _embed_query
            # 测试连接
            _embed_query("test")
            self._embed_fn = _embed_query
            return self._embed_fn
        except Exception:
            return None

    def _build_chain_vectors(self):
        """预计算所有因果链的语义向量"""
        embed_fn = self._get_embed_fn()
        if embed_fn is None:
            self._semantic_enabled = False
            return

        try:
            import numpy as np
            texts = []
            for chain in self.chains:
                # 用 anomaly_description + 关键词 拼接作为链的语义表示
                text = chain.anomaly_description + " " + " ".join(chain.anomaly_keywords)
                texts.append(text)

            vectors = []
            for text in texts:
                vec = embed_fn(text)
                vectors.append(vec)

            self._chain_vectors = np.array(vectors, dtype=np.float32)
            self._semantic_enabled = True
            print(f"[语义匹配] 已构建 {len(self.chains)} 条链的向量索引 ({self._chain_vectors.shape[1]}维)")
        except ImportError:
            self._semantic_enabled = False
            print("[语义匹配] numpy 不可用，回退到关键词匹配")
        except Exception as e:
            self._semantic_enabled = False
            print(f"[语义匹配] 向量构建失败: {e}，回退到关键词匹配")

    def _semantic_score(self, query: str) -> List[Tuple[int, float]]:
        """
        语义匹配：查询文本 → 所有因果链的余弦相似度。

        Returns:
            [(chain_index, similarity_score), ...] 按相似度降序
        """
        if not self._semantic_enabled or self._chain_vectors is None:
            return []

        embed_fn = self._get_embed_fn()
        if embed_fn is None:
            return []

        try:
            import numpy as np
            q_vec = np.array(embed_fn(query), dtype=np.float32)

            # 余弦相似度（归一化后点积）
            q_norm = q_vec / (np.linalg.norm(q_vec) + 1e-8)
            c_norms = self._chain_vectors / (np.linalg.norm(self._chain_vectors, axis=1, keepdims=True) + 1e-8)
            similarities = np.dot(c_norms, q_norm)

            # 相似度映射到 0-3 分（与关键词得分可比）
            # sim > 0.8 → 3分, > 0.6 → 2分, > 0.4 → 1分
            scored = []
            for i, sim in enumerate(similarities):
                if sim > 0.4:
                    semantic_score = 3.0 if sim > 0.8 else (2.0 if sim > 0.6 else 1.0)
                    scored.append((i, float(sim), semantic_score))
            scored.sort(key=lambda x: x[1], reverse=True)
            return [(i, ss) for i, _, ss in scored]

        except Exception as e:
            print(f"[语义匹配] 查询失败: {e}")
            return []

    def _match_chains_hybrid(self,
                             description: str,
                             energy_type: str = "",
                             system: str = "") -> List[CausalChain]:
        """
        v3.0 混合匹配：语义（权重0.5）+ 关键词（权重0.3）+ 类型/系统（权重0.2）。

        语义可用时自动启用；不可用时退化到纯关键词匹配。
        """
        desc_lower = description.lower()
        scored: Dict[int, float] = {}

        # 语义分
        semantic_scores = self._semantic_score(description)
        sem_dict = {i: s for i, s in semantic_scores}

        for i, chain in enumerate(self.chains):
            score = 0.0

            # 语义得分 (0-3) × 0.5
            if i in sem_dict:
                score += sem_dict[i] * 0.5

            # 关键词得分 (0-N) × 0.3
            kw_hits = sum(1 for kw in chain.anomaly_keywords if kw.lower() in desc_lower)
            score += kw_hits * 0.3

            # 能源类型匹配 × 0.1
            if energy_type and chain.energy_type == energy_type:
                score += 0.1

            # 系统匹配 × 0.1
            if system and chain.system == system:
                score += 0.1

            if score > 0:
                scored[i] = score

        ranked = sorted(scored.items(), key=lambda x: x[1], reverse=True)
        return [self.chains[i] for i, _ in ranked]

    @staticmethod
    def _dict_to_chain(d: dict) -> CausalChain:
        return CausalChain(
            anomaly_description=d['anomaly_description'],
            anomaly_keywords=d['anomaly_keywords'],
            energy_type=d['energy_type'],
            system=d['system'],
            causes=[
                CauseNode(
                    id=f"cause_{d['anomaly_description']}_{c['label']}",
                    label=c['label'],
                    description=c['description'],
                    energy_type=EnergyType(d['energy_type']),
                    system=SystemType(d['system']),
                    probability=c.get('probability', 0.5),
                    check_method=c.get('check_method', ''),
                )
                for c in d['causes']
            ],
            measures=[
                MeasureNode(
                    id=f"measure_{d['anomaly_description']}_{m['label']}",
                    label=m['label'],
                    description=m['description'],
                    estimated_saving_rate=m.get('estimated_saving_rate', ''),
                    investment_level=m.get('investment_level', ''),
                    payback_period=m.get('payback_period', ''),
                    references=[],
                )
                for m in d['measures']
            ],
            sources=d.get('sources', []),
        )

    @staticmethod
    def _chain_to_dict(chain: CausalChain) -> dict:
        return {
            'anomaly_description': chain.anomaly_description,
            'anomaly_keywords': chain.anomaly_keywords,
            'energy_type': chain.energy_type,
            'system': chain.system,
            'causes': [
                {
                    'label': c.label,
                    'description': c.description,
                    'probability': c.probability,
                    'check_method': c.check_method,
                }
                for c in chain.causes
            ],
            'measures': [
                {
                    'label': m.label,
                    'description': m.description,
                    'estimated_saving_rate': m.estimated_saving_rate,
                    'investment_level': m.investment_level,
                    'payback_period': m.payback_period,
                }
                for m in chain.measures
            ],
            'sources': chain.sources,
        }

    # ---- v4.0 置信度自动更新 ----

    def record_feedback(self, anomaly_description: str, cause_label: str,
                        was_correct: bool) -> dict:
        """
        记录用户对诊断结果的反馈，自动更新因果概率。

        Args:
            anomaly_description: 异常描述（用于匹配因果链）
            cause_label: 被确认/否认的原因标签
            was_correct: True=用户确认该原因正确, False=用户否认

        Returns:
            {cause_label, old_prob, new_prob, confirmed, rejected}

        更新公式（贝叶斯平滑）:
            new_prob = (prior_alpha + confirmed) / (prior_alpha + prior_beta + confirmed + rejected)
            其中 prior_alpha = old_prob * 10, prior_beta = (1-old_prob) * 10
            即：10次虚拟观测 → 真正确认/否认越多，先验影响越小
        """
        # 初始化或获取反馈计数
        fb = self._feedback.setdefault(cause_label, {'confirmed': 0, 'rejected': 0})
        if was_correct:
            fb['confirmed'] += 1
        else:
            fb['rejected'] += 1

        # 找到对应的 CauseNode 并更新概率
        old_prob = 0.5
        for chain in self.chains:
            if chain.anomaly_description in anomaly_description or \
               anomaly_description in chain.anomaly_description:
                for cause in chain.causes:
                    if cause.label == cause_label:
                        old_prob = cause.probability
                        # 贝叶斯更新
                        prior_strength = 10  # 先验强度（相当于10次虚拟观测）
                        alpha = old_prob * prior_strength + fb['confirmed']
                        beta = (1 - old_prob) * prior_strength + fb['rejected']
                        cause.probability = round(alpha / (alpha + beta), 4)
                        # 更新图中节点属性
                        cause_node = f"cause:{cause.id or cause.label}"
                        if cause_node in self.G:
                            self.G.nodes[cause_node]['probability'] = cause.probability
                        break
                break

        return {
            'cause_label': cause_label,
            'old_prob': old_prob,
            'new_prob': next(
                (c.probability for chain in self.chains
                 for c in chain.causes if c.label == cause_label),
                old_prob
            ),
            'confirmed': fb['confirmed'],
            'rejected': fb['rejected'],
        }

    def record_feedback_batch(self, feedbacks: List[dict]) -> List[dict]:
        """
        批量记录反馈。

        Args:
            feedbacks: [{'anomaly_description': '...', 'cause_label': '...', 'was_correct': True/False}, ...]

        Returns:
            每条反馈的更新结果列表
        """
        return [self.record_feedback(**f) for f in feedbacks]

    def get_feedback_stats(self) -> dict:
        """获取所有反馈统计"""
        total_confirmed = sum(fb['confirmed'] for fb in self._feedback.values())
        total_rejected = sum(fb['rejected'] for fb in self._feedback.values())
        return {
            'total_feedbacks': total_confirmed + total_rejected,
            'total_confirmed': total_confirmed,
            'total_rejected': total_rejected,
            'accuracy': round(total_confirmed / (total_confirmed + total_rejected), 3)
                if (total_confirmed + total_rejected) > 0 else None,
            'per_cause': dict(self._feedback),
        }

    def save_feedback(self, path: str):
        """保存反馈数据到JSON（含当前概率）"""
        data = {
            'feedback': dict(self._feedback),
            'current_probabilities': {
                cause.label: cause.probability
                for chain in self.chains
                for cause in chain.causes
            },
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_feedback(self, path: str):
        """从JSON加载反馈数据并更新概率"""
        if not os.path.exists(path):
            return
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self._feedback = data.get('feedback', {})

        # 用保存的概率覆盖当前概率
        saved_probs = data.get('current_probabilities', {})
        for chain in self.chains:
            for cause in chain.causes:
                if cause.label in saved_probs:
                    cause.probability = saved_probs[cause.label]

        print(f"[反馈] 已加载 {len(self._feedback)} 个原因的反馈数据 "
              f"({sum(fb['confirmed']+fb['rejected'] for fb in self._feedback.values())} 次反馈)")


# ============================================================
# 便捷函数
# ============================================================

def create_default_kg() -> EnergyKnowledgeGraph:
    """创建并加载预置因果链的知识图谱"""
    kg = EnergyKnowledgeGraph()
    kg.load_builtin()
    return kg


# ============================================================
# 测试
# ============================================================

if __name__ == "__main__":
    kg = create_default_kg()
    print(f"加载因果链: {len(kg.chains)} 条")
    print(f"图谱节点: {kg.G.number_of_nodes()}")
    print(f"图谱边: {kg.G.number_of_edges()}")

    # 测试诊断
    print("\n--- 测试1: COP偏低 ---")
    r = kg.diagnose("冷机COP偏低，2024年实测4.2，低于额定6.5", energy_type="电", system="中央空调系统")
    print(f"  匹配因果链: {len(r.matched_chains)}条")
    print(f"  最可能原因: {r.primary_cause.label if r.primary_cause else '无'}")
    print(f"  置信度: {r.confidence}")
    print(f"  建议措施:")
    for m in r.recommended_measures:
        print(f"    - {m.label} (节能率: {m.estimated_saving_rate}, 投资: {m.investment_level})")

    print("\n--- 测试2: 用水量增加 ---")
    r = kg.diagnose("用水量2023→2024年同比增加66.8%", energy_type="水")
    print(f"  最可能原因: {r.primary_cause.label if r.primary_cause else '无'}")
    for m in r.recommended_measures:
        print(f"    - {m.label}")

    print("\n--- 测试3: 无匹配（需人工分析） ---")
    r = kg.diagnose("电梯能耗异常偏高", energy_type="电")
    print(f"  有诊断: {r.has_diagnosis}")

    print("\n--- 测试4: 批量诊断 ---")
    anomalies = [
        {'description': '冷机COP偏低', 'energy_type': '电', 'system': '中央空调系统'},
        {'description': '照明电耗偏高，LED占比仅30%', 'energy_type': '电', 'system': '照明系统'},
        {'description': '用水量同比增加66.8%', 'energy_type': '水'},
    ]
    report = kg.diagnose_all(anomalies, "测试项目")
    print(f"  总异常: {report.total_anomalies}, 有诊断: {report.diagnosed}, 无诊断: {report.undiagnosed}")
    for r in report.results:
        cause_label = r.primary_cause.label if r.primary_cause else '【需人工分析】'
        print(f"    {r.anomaly_description[:30]}... → {cause_label}")
