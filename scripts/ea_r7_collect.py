# -*- coding: utf-8 -*-
"""R7 全新全流程重编采集驱动（烟台经济技术开发区人民法院）—— 2026-09-07 晚。

阶段 collect : collect_from_pg（显式校验锚点）→ build_and_save_project（照片下载+持久化根 data.json）
阶段 finalize: 照片镜像到 <项目>/data/images 并重写 data.json 路径；按任务口径写项目段
               （audit_years/data_start/data_end/audit_start/audit_end/report_date）；
               注入顶层 pg_project_id/pg_customer_id/audit_years/energy_standards/_note；
               根 data.json 与 data/data.json 双写且字节一致。

一切数值来自 PG dc_energy_audit2 实查；config.json 仅作身份锚点/口径，不取业务数值。
"""
import argparse
import json
import os
import pathlib
import shutil
import sys

WORKDIR = pathlib.Path(r"C:/Users/matianyuan/projects/energy-audit/烟台经济技术开发区人民法院")
CONFIG_PATH = WORKDIR / "config.json"
DATA_JSON = WORKDIR / "data" / "data.json"
ROOT_JSON = WORKDIR / "data.json"
IMAGES_DIR = WORKDIR / "data" / "images"

PROJECT_ID = 2087807622972936194
CUSTOMER_ID = 2083089316391030786
NAME = "烟台经济技术开发区人民法院"

# ---- 任务口径（身份锚点 config，_note 自述仅口径非业务数值）----
AUDIT_YEARS = [2023, 2024, 2025]
DATA_START = "2023-01-01"
DATA_END = "2025-12-31"
AUDIT_START = "2025年1月"
AUDIT_END = "2026年9月"
AUDIT_PERIOD = "2025年1月—2026年9月"
REPORT_DATE = "2026年9月"


def bootstrap_env() -> None:
    """datacollection profile config.yaml 无 energy_audit 段；从默认 Hermes config
    引导 EA_PG_PASSWORD / EA_FILE_BASE_URL 进环境（不打印明文）。"""
    cfg = pathlib.Path(r"C:/Users/matianyuan/AppData/Local/hermes/config.yaml")
    if cfg.exists():
        try:
            import yaml
            data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
            ea = data.get("energy_audit") or {}
            db = ea.get("database") or {}
            fl = ea.get("file") or {}
            if db.get("password"):
                os.environ.setdefault("EA_PG_PASSWORD", str(db["password"]))
            if fl.get("base_url"):
                os.environ.setdefault("EA_FILE_BASE_URL", str(fl["base_url"]))
        except Exception as exc:  # noqa: BLE001
            print("[bootstrap] 默认 hermes config 引导失败:", exc)


def run_collect() -> None:
    from dataclasses import asdict
    from tools.energy_audit.pg_collector import build_and_save_project, collect_from_pg
    from tools.energy_audit.project_data import save_project

    bootstrap_env()
    print(f"[R7] collect_from_pg('{NAME}') …")
    pg_result = collect_from_pg(NAME)
    got_id = pg_result.get("project_id")
    if got_id != PROJECT_ID:
        raise SystemExit(
            f"[R7] 锚点失败: collect_from_pg 命中 project_id={got_id}，期望 {PROJECT_ID}。中止。")
    print(f"[R7] 锚点确认 project_id={got_id} 命中正式登记")

    proj = build_and_save_project(NAME, pg_result=pg_result)
    saved = save_project(proj)  # 内部又 save 一次幂等；实际 build_and_save_project 已 save
    print(f"[R7] build_and_save_project 完成: {saved}")

    data = asdict(proj)
    summary = {
        "project_id": got_id,
        "found_count": len(pg_result.get("found", {})),
        "missing": pg_result.get("missing", []),
        "buildings": len(data.get("buildings", [])),
        "energy_yearly": len(data.get("energy_yearly", [])),
        "energy_monthly": len(data.get("energy_monthly", [])),
        "equipment": len(data.get("equipment", [])),
        "images": len(data.get("images", [])),
        "audit_team": len(data.get("audit_team", [])),
        "cooperation": len(data.get("cooperation", [])),
        "people_count": data.get("base", {}).get("people_count"),
        "base_unit": data.get("base", {}).get("unit_name"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _unique_dest(dest_dir: pathlib.Path, name: str, used: set) -> pathlib.Path:
    cand = dest_dir / name
    stem = pathlib.Path(name).stem
    suffix = pathlib.Path(name).suffix
    i = 1
    while cand.exists() or str(cand) in used:
        cand = dest_dir / f"{stem}_{i}{suffix}"
        i += 1
    return cand


def _mirror_one(src: str, dest_dir: pathlib.Path, cache: dict, used: set) -> str:
    """按源路径缓存：同一源文件只镜像一次，重复引用指向同一目标路径。"""
    if not src:
        return src
    if src in cache:
        return cache[src]
    p = pathlib.Path(src)
    if not p.exists():
        print(f"[finalize] 源图片不存在，保留原路径: {src}")
        return src
    dest = _unique_dest(dest_dir, p.name, used)
    shutil.copy2(str(p), str(dest))
    used.add(str(dest))
    cache[src] = str(dest)
    return str(dest)


def mirror_images(data: dict) -> dict:
    """把 data.json 内引用的图片文件（images[] + energy_saving *_images）镜像到
    <项目>/data/images，并把路径改写到镜像位置（同源只落盘一次）。失败不阻塞。"""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    cache: dict = {}
    used: set = set()

    for img in data.get("images", []) or []:
        old = (img or {}).get("path") or ""
        new = _mirror_one(old, IMAGES_DIR, cache, used)
        if new and new != old:
            img["path"] = new

    for es in data.get("energy_saving", []) or []:
        if isinstance(es, dict):
            for fld in ("management_file_images", "award_certificate_images"):
                lst = es.get(fld) or []
                es[fld] = [_mirror_one(x, IMAGES_DIR, cache, used) for x in lst]
    return data


def _power_of_spec(spec: str):
    """从 spec 提取功率数值（W 口径）。例 '未知 | 40.00W | …' → 40.0"""
    import re
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:W|kW)", spec or "")
    if not m:
        return None
    val = float(m.group(1))
    return val * 1000 if "kW" in m.group(0) else val


def fix_lighting_version_duplicates(data: dict) -> dict:
    """修正 09-07 草稿改名造成的照明重复（版本归一在无 power_unit 表上失效）：

    PG 实况（ts_institution_device_light 40 活动行 = 8 业务行 × 5 版本）：
      - 草稿 4 条：其他特殊灯具等 11/36/40/84W（update_time 2026-09-07 14:27~14:28，
        即用户当日对 4 类特殊灯具的最新编辑，草稿优先原则下为当前口径）
      - 正式 PL0401~0404 快照 4 条：其它特殊灯具等 11/36/40/84W（改名前的旧快照）
    因版本间名称 其他/其它 不一致，_merge_equipment 的 (category,name,spec) 去重无法合并
    → 特殊灯具被双计（照明 12 条 vs 业务真实 8 条）。修正：剔除被草稿取代的 4 条正式
    快照行（其它特殊灯具等），保留草稿行（其他特殊灯具等）。仅当同功率等价行存在时才剔除。
    """
    import re
    eqs = data.get("equipment", []) or []
    draft_rows = []   # 其他特殊灯具等
    formal_rows = []  # 其它特殊灯具等
    for e in eqs:
        if e.get("category") != "照明":
            continue
        name = e.get("name") or ""
        if name == "其他特殊灯具等":
            draft_rows.append(e)
        elif name == "其它特殊灯具等":
            formal_rows.append(e)
    if not draft_rows or not formal_rows:
        return data
    draft_powers = {_power_of_spec(e.get("spec") or "") for e in draft_rows}
    removed = 0
    keep = []
    for e in eqs:
        if (e.get("category") == "照明" and (e.get("name") or "") == "其它特殊灯具等"
                and _power_of_spec(e.get("spec") or "") in draft_powers):
            removed += 1
            continue
        keep.append(e)
    if removed:
        data["equipment"] = keep
        data.setdefault("data_issues", [])
        data["data_issues"].append(
            "设备版本归一修正：照明‘其它特殊灯具等’4条正式快照（PL2026080401~0404，11/36/40/84W）"
            "与 2026-09-07 14:27 草稿改名后的‘其他特殊灯具等’同功率重复（该表无 power_unit 列导致 "
            "pg_query 版本化 SQL 回退全量、按 (name,spec) 去重失效）；按草稿优先原则保留草稿 4 条并剔除 "
            f"旧快照 {removed} 条，防照明数量双计。若用户确需增补灯具请于平台发布正式版本后重采。")
    return data


def run_finalize() -> None:
    bootstrap_env()
    if not ROOT_JSON.exists():
        raise SystemExit(f"[finalize] 找不到根 data.json: {ROOT_JSON}（先运行 collect 阶段）")

    data = json.loads(ROOT_JSON.read_text(encoding="utf-8"))

    base = data.setdefault("base", {})
    # 项目段口径（身份锚点 config 规定，非 PG 业务数值）
    base["audit_start"] = AUDIT_START
    base["audit_end"] = AUDIT_END
    base["audit_period"] = AUDIT_PERIOD
    base["data_start"] = DATA_START
    base["data_end"] = DATA_END
    base["report_date"] = REPORT_DATE
    base["province"] = base.get("province") or "山东"

    # 照明版本重复修正（草稿改名 其它→其他 使 (name,spec) 去重失效）
    data = fix_lighting_version_duplicates(data)

    # 顶层标识与说明
    data["pg_project_id"] = PROJECT_ID
    data["pg_customer_id"] = CUSTOMER_ID
    data["audit_years"] = AUDIT_YEARS
    data["_note"] = (
        "第7轮全新全流程重编（2026-09-07 晚）：工作目录整体删除重建后由 editor 重建，"
        "未引用任何 R4/R5/R6 产物，全部数据 2026-09-07 从 PG dc_energy_audit2 全新采集。"
        f"显式锚定正式登记 pg_project_id={PROJECT_ID}（audit_year 2025-01~2026-09，status=2）"
        f"/ pg_customer_id={CUSTOMER_ID}；同名测试登记 2095793661742092289 已于 2026-09-07 从 PG "
        "删除（预检 ILIKE 唯一命中正式登记），全程以 ID 锚定防同名再建。"
        "折标系数 ts_energy_standard DB 原值注入顶层 energy_standards（三级兜底 DB→用户→GB/T2589 "
        "由后续指标计算处理）。能源消耗 2023-2025 三年完整（data_start=2023-01-01, data_end=2025-12-31）。"
        "缺失数据标【待补充】，禁止编造。"
    )

    # 折标系数 DB 原值（顶层）
    from tools.energy_audit.pg_query import PgDataQuery
    pg = PgDataQuery()
    pg.connect()
    try:
        stds = pg.get_energy_standards() or []
    finally:
        pg.disconnect()
    std_rows = []
    for s in stds:
        keep = {k: v for k, v in s.items()
                if k in ('id', 'energy_code', 'energy_name', 'coefficient',
                         'standard_coal_coefficient', 'unit') and v is not None}
        std_rows.append(keep)
    data["energy_standards"] = std_rows

    # 照片镜像 + 路径改写
    mirror_images(data)

    payload = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    ROOT_JSON.write_text(payload, encoding="utf-8")
    DATA_JSON.parent.mkdir(parents=True, exist_ok=True)
    DATA_JSON.write_text(payload, encoding="utf-8")
    print(f"[finalize] 已写根副本  : {ROOT_JSON} ({ROOT_JSON.stat().st_size} B)")
    print(f"[finalize] 已写采集产物: {DATA_JSON} ({DATA_JSON.stat().st_size} B)")
    print(f"[finalize] 顶层键: {sorted(k for k in data if not k.startswith('_'))}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["collect", "finalize"])
    args = ap.parse_args()
    if args.mode == "collect":
        run_collect()
    else:
        run_finalize()
