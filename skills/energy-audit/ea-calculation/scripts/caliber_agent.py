#!/usr/bin/env python3
"""
Caliber Agent — 能耗指标计算与第5章生成

输入: ~/projects/energy-audit/<project_name>/data.json (AuditProject)
输出: ~/projects/energy-audit/<project_name>/
       ├── indicators.json     # 4项指标 + 定额对标 + 基准
       ├── chapter5.md         # 第5章完整Markdown
       └── charts/             # 图表文件

用法:
    python caliber_agent.py <project_name>
    python caliber_agent.py "山东省省立医院东院区" --skip-charts
"""

import json, os, sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# Windows GBK 控制台兼容：输出含 emoji/中文，强制 UTF-8 防 UnicodeEncodeError
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# ── 项目路径适配 ──────────────────────────────────────────────
# 脚本位于用户 profile 目录，需先定位项目根，再借用 tools/energy_audit。
# 3 层降级：env → CWD 向上爬 → __file__ 向上爬（与 _paths.py 一致）。

def _resolve_project_root() -> Path:
    """3 层降级：env → CWD 向上爬 → __file__ 向上爬"""

    # Layer 1: 环境变量（CI/Docker/IDE 推荐）
    env = os.environ.get("HERMES_AGENT_HOME")
    if env:
        candidate = Path(env).expanduser().resolve()
        if (candidate / "tools" / "energy_audit" / "indicators.py").is_file():
            return candidate

    # Layer 2: CWD 向上爬（从项目根或子目录运行时）
    cwd = Path.cwd().resolve()
    for parent in [cwd, *cwd.parents]:
        if (parent / "tools" / "energy_audit" / "indicators.py").is_file():
            return parent

    # Layer 3: __file__ 向上爬（脚本被放入项目树内时）
    here = Path(__file__).resolve().parent
    for parent in [here, *here.parents]:
        if (parent / "tools" / "energy_audit" / "indicators.py").is_file():
            return parent

    raise RuntimeError(
        "无法定位项目根目录。请按以下方式修复：\n"
        "  1. 设置环境变量: export HERMES_AGENT_HOME=/path/to/project\n"
        "  2. 从项目根目录运行: cd /path/to/project && python ...\n"
        "  3. 将脚本放入项目内（与 tools/energy_audit 同级）\n"
        f"\n诊断: $PWD={cwd} $HERMES_AGENT_HOME={env!r} __file__={__file__}"
    )


try:
    ROOT_DIR = _resolve_project_root()
except RuntimeError as e:
    print(f"[Caliber] ❌ 路径解析失败\n{e}")
    sys.exit(1)

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from tools.energy_audit.project_data import load_project, AuditProject
    from tools.energy_audit.indicators import (
        YearlyEnergyData,
        calc_unit_area_non_heating_energy,
        compare_with_benchmark,
        calc_unit_area_electricity,
        calc_per_capita_energy,
        calc_water_indicator,
        calc_baseline,
        resolve_coefficient,
        resolve_benchmark,
    )
    from tools.energy_audit.chapter5_agent import generate as gen_chapter5, generate_charts
    TOOLS_AVAILABLE = True
except ImportError as e:
    print(f"[Caliber] ⚠️ 工具导入失败: {e}")
    print(f"[Caliber] sys.path[0]: {sys.path[0]}")
    TOOLS_AVAILABLE = False


# ================================================================
#  数据提取
# ================================================================

def extract_yearly_data(proj: AuditProject) -> List[YearlyEnergyData]:
    """从 AuditProject 提取 YearlyEnergyData 列表"""
    data_list = []
    for ey in proj.energy_yearly:
        year = getattr(ey, 'year', 0)
        d = YearlyEnergyData(
            year=year,
            electricity_kwh=float(getattr(ey, 'electricity_kwh', 0) or 0),
            water_m3=float(getattr(ey, 'water_m3', 0) or 0),
            natural_gas_m3=float(getattr(ey, 'natural_gas_m3', 0) or 0),
            heating_energy_heat=float(getattr(ey, 'heating_energy_heat_gj', 0) or 0),
            heating_energy_kwh=0,       # 需从 sub_items 拆分，此处默认0
            heating_energy_gas=0,
            transportation_petrol_kg=float(getattr(ey, 'petrol_kg', 0) or 0),
            transportation_diesel_kg=float(getattr(ey, 'diesel_kg', 0) or 0),
            building_area=float(getattr(proj.base, 'building_area', 0) or 0),
            people_count=float(getattr(proj.base, 'people_count', 0) or 0),
            coefficients=dict(getattr(ey, 'coefficients', {}) or {}),
        )
        data_list.append(d)
    return sorted(data_list, key=lambda x: x.year)


def resolve_institution_type(proj: AuditProject) -> str:
    """解析机构类型 → medical/government/education"""
    cat = (getattr(proj.base, 'institution_category', '') or '').lower()
    if '医疗' in cat or '医院' in cat:
        return 'medical'
    if '机关' in cat or '党政' in cat:
        return 'government'
    if '教育' in cat or '学校' in cat:
        return 'education'
    return 'medical'  # 默认医疗


# ================================================================
#  指标计算
# ================================================================

def calc_all_indicators(
    proj: AuditProject,
    yearly_data: List[YearlyEnergyData],
) -> dict:
    """计算全部4项指标 + 定额对标 + 能耗基准"""
    if not yearly_data:
        return {'error': '无年度能耗数据'}

    latest = yearly_data[-1]
    inst_type = resolve_institution_type(proj)
    bed_count = getattr(proj.base, 'beds_count', 0) or 0

    results = {
        'project': getattr(proj.base, 'unit_name', ''),
        'year': latest.year,
        'building_area': getattr(proj.base, 'building_area', 0),
        'people_count': getattr(proj.base, 'people_count', 0),
        'institution_type': inst_type,
        'calculated_at': datetime.now().isoformat(),
    }

    # ── 指标 (1): 单位建筑面积非供暖能耗 ──
    r1 = calc_unit_area_non_heating_energy(latest)
    if r1.get('error'):
        # 输入无效（如建筑面积缺失）时结果为 0 值占位，直接对标会误判"先进水平"
        results['unit_area_non_heating_energy'] = {**r1, 'benchmark': None}
    else:
        bm1 = compare_with_benchmark(r1['kgce_per_m2'], inst_type, 'unit_area_non_heating')
        results['unit_area_non_heating_energy'] = {
            **r1,
            'benchmark': bm1,
        }

    # ── 指标 (2): 常规用能系统单位建筑面积电耗 ──
    r2 = calc_unit_area_electricity(latest, institution_type=inst_type)
    results['unit_area_electricity'] = r2

    # ── 指标 (3): 人均综合能耗 ──
    r3 = calc_per_capita_energy(latest, institution_type=inst_type)
    results['per_capita_energy'] = r3

    # ── 指标 (4): 取水指标（医院=床日/机关教育=人均/场馆=面积）──
    r4 = calc_water_indicator(latest, inst_type, bed_count=bed_count)
    results['water_indicator'] = r4

    # ── 5.4: 建筑能耗基准 ──
    baseline = calc_baseline(yearly_data)
    results['baseline'] = baseline

    return results


# ================================================================
#  格式化输出
# ================================================================

def format_indicators_report(results: dict) -> str:
    """生成可读的指标报告"""
    lines = []
    lines.append("=" * 60)
    lines.append("📊 Caliber — 能耗指标计算结果")
    lines.append("=" * 60)
    lines.append(f"项目: {results.get('project', '')}")
    lines.append(f"年度: {results.get('year', '')} | 类型: {results.get('institution_type', '')}")
    lines.append(f"面积: {results.get('building_area', 0):,.0f} m² | "
                 f"人数: {results.get('people_count', 0):,}")
    lines.append("")

    # 指标(1)
    r1 = results.get('unit_area_non_heating_energy', {})
    bm1 = r1.get('benchmark') or {}
    lines.append(f"1. 单位建筑面积非供暖能耗: {r1.get('kgce_per_m2','-')} kgce/(m²·a)")
    lines.append(f"   对标: {bm1.get('评价结果','-')}")
    lines.append(f"   标准: {bm1.get('标准','-')} | 来源: {bm1.get('来源','-')}")
    lines.append(f"   约束值: {bm1.get('约束值','-')}  基准值: {bm1.get('基准值','-')}  引导值: {bm1.get('引导值','-')}")
    lines.append("")

    # 指标(2)
    r2 = results.get('unit_area_electricity', {})
    bm2 = r2.get('benchmark') or {}
    lines.append(f"2. 常规用能系统单位面积电耗: {r2.get('kwh_per_m2','-')} kWh/(m²·a)")
    lines.append(f"   对标: {bm2.get('评价结果','-')}")
    lines.append(f"   标准: {bm2.get('标准','-')} | 来源: {bm2.get('来源','-')}")
    lines.append(f"   约束值: {bm2.get('约束值','-')}  基准值: {bm2.get('基准值','-')}  引导值: {bm2.get('引导值','-')}")
    lines.append("")

    # 指标(3)
    r3 = results.get('per_capita_energy', {})
    bm3 = r3.get('benchmark') or {}
    lines.append(f"3. 人均综合能耗: {r3.get('kgce_per_person','-')} kgce/(人·a)")
    lines.append(f"   对标: {bm3.get('评价结果','-')}")
    lines.append(f"   约束值: {bm3.get('约束值','-')}  基准值: {bm3.get('基准值','-')}  引导值: {bm3.get('引导值','-')}")
    lines.append("")

    # 指标(4) 取水指标
    r4 = results.get('water_indicator') or results.get('per_capita_water', {})  # 旧键兼容
    bm4 = r4.get('benchmark') or {}
    if 'L_per_bed_day' in r4:
        lines.append(f"4. 单位开放床日用水量: {r4.get('L_per_bed_day','-')} L/(床·d)")
    else:
        lines.append(f"4. 人均取水量: {r4.get('m3_per_person','-')} m³/(人·a)")
    lines.append(f"   对标: {bm4.get('评价结果','-')}")
    lines.append(f"   标准: {bm4.get('标准','-')} | 来源: {bm4.get('来源','-')}")
    lines.append("")

    # 基准
    baseline = results.get('baseline', {})
    if baseline and 'usage' in baseline:
        lines.append(f"5. 建筑能耗基准 ({'、'.join(map(str, baseline.get('years', [])))}年):")
        for label, info in baseline.get('usage', {}).items():
            lines.append(f"   {label}: {info['基准值']:,.2f}{info['单位']} [{info['方法']}]")

    lines.append("")
    lines.append("=" * 60)
    return '\n'.join(lines)


# ================================================================
#  完整流程
# ================================================================

def run_caliber(
    project_name: str,
    skip_charts: bool = False,
    output_dir: Optional[str] = None,
) -> dict:
    """执行完整的指标计算与第5章生成流程"""
    if not TOOLS_AVAILABLE:
        return {"error": "工具导入失败"}

    print(f"\n{'='*60}")
    print(f"📊 Caliber — 能耗指标计算与第5章生成")
    print(f"{'='*60}")
    print(f"项目: {project_name}")

    # Step 1: 加载
    print("[1/5] 📂 加载项目数据...")
    proj = load_project(project_name)
    if proj is None:
        msg = f"项目 '{project_name}' 数据不存在"
        print(f"  ❌ {msg}")
        return {"error": msg}
    print(f"  ✅ 加载成功 | 建筑: {len(getattr(proj, 'buildings', []))}栋 | "
          f"能耗: {len(getattr(proj, 'energy_yearly', []))}年")

    # Step 2: 提取
    print("[2/5] 🔄 提取年度能耗数据...")
    yearly_data = extract_yearly_data(proj)
    if not yearly_data:
        print("  ❌ 无有效年度能耗数据")
        return {"error": "无能耗数据"}
    years = sorted(d.year for d in yearly_data)
    print(f"  ✅ {len(yearly_data)} 年 ({', '.join(map(str, years))})")

    # Step 3: 计算指标
    print("[3/5] 🧮 计算4项指标 + 定额对标 + 能耗基准...")
    results = calc_all_indicators(proj, yearly_data)

    # 输出指标预览
    r1 = results.get('unit_area_non_heating_energy', {})
    r2 = results.get('unit_area_electricity', {})
    bm1 = r1.get('benchmark') or {}
    bm2 = r2.get('benchmark') or {}
    print(f"  ✅ 非供暖能耗: {r1.get('kgce_per_m2','-')} kgce/m² [{bm1.get('评价结果','-')}]")
    print(f"  ✅ 常规电耗: {r2.get('kwh_per_m2','-')} kWh/m² [{bm2.get('评价结果','-')}]")
    print(f"  ✅ 人均能耗: {results.get('per_capita_energy',{}).get('kgce_per_person','-')} kgce/人")
    r4 = results.get('water_indicator') or results.get('per_capita_water', {})  # 旧键兼容
    if 'L_per_bed_day' in r4:
        print(f"  ✅ 床日用水: {r4.get('L_per_bed_day','-')} L/(床·d)")
    else:
        print(f"  ✅ 人均取水: {r4.get('m3_per_person','-')} m³/(人·a)")

    # Step 4: 生成第5章
    print("[4/5] 📝 生成第5章 Markdown...")
    out_dir = Path(output_dir) if output_dir else Path.home() / 'projects' / 'energy-audit' / project_name
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        config = {
            'building_area': getattr(proj.base, 'building_area', 0),
            'people_count': getattr(proj.base, 'people_count', 0),
            'unit_name': getattr(proj.base, 'unit_name', project_name),
            'chart_dir': str(out_dir / 'charts'),
            'manual': {
                'energy_data': _build_energy_data_dict(yearly_data, proj),
                'cost_data': {},
                'sub_items': {},
            },
        }
        chapter5_md = gen_chapter5(config, str(out_dir / 'chapter5.md'))
        print(f"  ✅ 第5章: {len(chapter5_md)} 字符 → {out_dir / 'chapter5.md'}")

        # 图表
        if not skip_charts:
            data = {'energy_data': _build_energy_data_dict(yearly_data, proj)}
            try:
                generate_charts(data, config, str(out_dir / 'charts'))
                print(f"  ✅ 图表: {out_dir / 'charts/'}")
            except Exception as e:
                print(f"  ⚠️ 图表生成失败: {e}")
    except Exception as e:
        print(f"  ⚠️ 第5章生成失败: {e}")
        chapter5_md = f"# 第5章\n\n⚠️ 生成失败: {e}\n"

    # Step 5: 持久化
    print("[5/5] 💾 保存结果...")
    # 指标 JSON
    indicators_path = out_dir / 'indicators.json'
    with open(indicators_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(f"  ✅ 指标: {indicators_path}")

    # 文本报告
    report = format_indicators_report(results)
    report_path = out_dir / 'indicators_report.txt'
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"  ✅ 报告: {report_path}")

    # 打印总结
    print(report)

    return {
        'indicators_path': str(indicators_path),
        'chapter5_path': str(out_dir / 'chapter5.md'),
        'indicators': results,
    }


def _build_energy_data_dict(yearly_data: List[YearlyEnergyData], proj: AuditProject) -> dict:
    """将 YearlyEnergyData 列表转为 chapter5_agent 所需的 energy_data dict 格式"""
    energy_data = {}
    for d in yearly_data:
        y = str(d.year)
        energy_data[y] = {
            'electricity': {
                'name': '电能', 'unit': 'kWh',
                'total': d.electricity_kwh,
                'monthly': _get_monthly(proj, d.year, 'monthly_electricity_kwh'),
            },
            'water': {
                'name': '水', 'unit': 't',
                'total': d.water_m3,
                'monthly': _get_monthly(proj, d.year, 'monthly_water_m3'),
            },
            'natural_gas': {
                'name': '天然气', 'unit': 'm³',
                'total': d.natural_gas_m3,
                'monthly': _get_monthly(proj, d.year, 'monthly_natural_gas_m3'),
            },
            'heat': {
                'name': '热能', 'unit': 'GJ',
                'total': d.heating_energy_heat,
                'monthly': [0]*12,
            },
        }
    return energy_data


def _get_monthly(proj, year: int, field: str) -> List[float]:
    """从 AuditProject 中提取某年的月度数据"""
    for ey in getattr(proj, 'energy_yearly', []):
        if getattr(ey, 'year', 0) == year:
            vals = getattr(ey, field, None) or []
            if isinstance(vals, list) and len(vals) == 12:
                return [float(v or 0) for v in vals]
    return [0] * 12


# ================================================================
#  CLI
# ================================================================

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="Caliber — 能耗指标计算与第5章生成")
    parser.add_argument('project_name', help='项目名称')
    parser.add_argument('--skip-charts', action='store_true', help='跳过图表生成')
    parser.add_argument('--output-dir', help='输出目录')
    args = parser.parse_args()

    result = run_caliber(
        project_name=args.project_name,
        skip_charts=args.skip_charts,
        output_dir=args.output_dir,
    )
    if 'error' in result:
        print(f"\n❌ {result['error']}")
        sys.exit(1)
