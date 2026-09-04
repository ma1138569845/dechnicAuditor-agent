# 能耗主数据修复操作手册（烟台法院实证 2026-09）

> 适用：`ts_institution_energy_main` / `ts_institution_energy_data` / 建筑表 / 计量表 /
> energy_saving 等数据被确认错误或缺失、需要修正。铁律：**先备份、单事务、权威源=账单**。

## 0. 权威源确认（改之前必做）

- 年度总量 = 正式交付报告附录2逐月账单**脚本化加总**（勿心算）
- 用量 = 费用 ÷ 单价（热 89.61 元/GJ、水≈5 元/m³、电≈0.7 元/kWh、气≈4~4.6 元/m³）
- DB 草稿（ver=None）与正式版本（PLxxx）冲突时以账单为准；**草稿仅是线索，草稿也可能错**（实测 2024 电费草稿 752,854.00 亦错，正确 752,860.98）

## 1. 备份快照

待改记录全字段（主表 + periods 子表）SELECT 导出 JSON 到项目目录
`db_fix_backup_<日期>.json`；ts_report_block 报告块修正同样先备份
`ts_report_block_backup_<日期>.json`。备份与修改说明放同一项目目录。

## 2. 事务化修改

- `conn.autocommit = False`，全部 UPDATE/INSERT 后一次 `commit()`，异常 `rollback()`
- UPDATE 时 `total_value` 与 `real_value` 同步改；若该记录 `ts_institution_energy_data`
  周期明细与主表一致地错，**必须同步改**（实测：12 月 51,105→79,305；季度 1623→1787.5）
- `anomaly_status`（版本冲突标记）：数据修对后置 0；未修记录勿动
- 缺失的实物量记录：从草稿复制结构，INSERT 到每个正式版本

## 3. INSERT 版本记录模式（补"草稿有、正式版缺"的记录）

```python
import time, random
def snowflake():  # 19 位雪花风格 id，与现网 id 同量级
    return (int(time.time()*1000) << 22) | (random.getrandbits(22) & 0x3FFFFF)
# main 表：复制草稿字段（year/data_type/energy_code/unit/折标系数/is_alone/filled/
#   required/granularity），version_code=目标版本、is_draft=0、creator/updater='1'
# data 表：period_code/period_name('1月'...'12月')/energy_value/real_value 逐月复制
```

## 4. 版本归一查询 SQL（取数层修复）

`pg_query.py.get_institution_energy`（energy_audit_get_energy 工具底层）与采集脚本
必须版本归一，否则三版本重复返回：

```sql
SELECT m.*, d.period_code, d.energy_value
FROM ts_institution_energy_main m
LEFT JOIN ts_institution_energy_data d ON d.main_id = m.id
WHERE m.deleted = 0 AND m.id IN (
  SELECT DISTINCT ON (mm.year, mm.data_type, mm.energy_code) mm.id
  FROM ts_institution_energy_main mm
  WHERE mm.deleted = 0
  ORDER BY mm.year, mm.data_type, mm.energy_code,
           COALESCE(mm.is_draft,0) DESC,     -- 草稿优先（is_draft=1=最新编辑数据）
           mm.version_code DESC NULLS LAST,  -- 版本号大者优先
           mm.id DESC)
ORDER BY m.year, m.data_type, m.energy_code, d.period_code
```

> 坑：DISTINCT ON 直接作用在 JOIN 结果会每组只留一行、**丢 period 明细**；
> 必须用 `m.id IN (子查询)` 结构。

## 5. 冲突消解原则（采集脚本）

- **禁止多数投票**：错误被复制进多个正式版本后（如 PL0401/0402 均错、仅草稿对），
  投票 2:1 必然选中错误值（烟台法院热力 2024/2025 两年均因此选反）
- 正确做法：草稿优先取用（草稿=最新编辑数据）；同组存在不同值时输出 conflicts 告警清单，
  写入采集产物（如 data.json.collection_report.conflicts）供 V1 检查点消费，不静默消解
- 采集产物须落地人员名单（ts_project_audit_user/audited_user 查了要写进输出——
  实测"查了没落地"导致封面人员表【待补充】）

## 6. 验证清单

- [ ] 全量回查：每个 (year, data_type, energy_code) × 各版本与权威值一致（误差<0.01）
- [ ] periods 与主表 total 自洽（月度加总 = total）
- [ ] 重跑采集脚本：conflicts 清零、缺失项清零
- [ ] 工具重查（energy_audit_get_energy）不再返回重复记录
- [ ] 仓库侧 canonical 测试：`bash scripts/run_tests.sh tests/tools/energy_audit/`
