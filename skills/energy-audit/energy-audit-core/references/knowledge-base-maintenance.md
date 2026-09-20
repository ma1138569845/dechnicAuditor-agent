# knowledge-base-maintenance — 知识库维护（knowledger 职责）

> **本文是"知识库谁维护、什么时候喂料、喂完怎么算合格"的唯一权威。**
> 读侧（写报告时怎么查）不在本文，见 `WORKFLOW.md` 第六节；
> 本文只管**写侧**（往里放什么、怎么放、怎么验收）。
>
> 背景：定额库（`energy_quota_standards`）与技术规范库
> （`energy_audit_technical_guidelines`）建库后**长期空置**——原因是解析器把标准
> 当报告解析、整篇只切出 1 条垃圾摘要，试一次就没人再喂（2026-09-20 修复）。
> 这件事的教训是：**库建好了没人负责维护，等于没建**。

## 一、三个库各装什么（边界）

| 库（kb_id） | 装什么 | **不装什么** |
|---|---|---|
| `energy_audit_reports` | 已交付的能源审计成稿 | 标准原文、草稿、中间稿 |
| `energy_quota_standards` | **定额 / 限额**类标准（能耗定额、用水定额、建筑能耗限额） | 报告成稿；技术规范/办法 |
| `energy_audit_technical_guidelines` | **技术规范 / 导则 / 办法**（审计技术导则、上级管理办法、地方法规） | 定额类（归 quota）；报告模板 |

三条硬边界：

1. **技能包规则文件不入库**（`chapter-guides-*.md`、`rules.md`、`standards-values.md` 等）——
   它们由 git 管理、随技能发布，入库只会制造第二份副本。
2. **标准原文与报告成稿不混库**：混了以后检索会拿"别人怎么写"当"条文依据"。
3. **必须留归档副本**：库内文件在 `rag/standards/<类别>/` 要有同哈希副本。
   理由见第五节（删除 API 会连磁盘原件一起删）。

## 二、谁在什么时候喂什么

| 触发 | 谁 | 时机 | 动作 |
|---|---|---|---|
| 报告交付定稿 | author | **S16a**（每次交付，固定动作） | 成稿入 `rag/report/<机构类>/` → 入库 → 刷台账（见 `WORKFLOW.md` S16a） |
| 拿到新的/换版标准原文 | **knowledger** | 收到即办，不攒 | 投递区 → `ingest_kb_files.py`（第三节） |
| 例行巡检 | **knowledger** | 每季度，或"检索查不到东西"时随时 | `verify_knowledge_assets.py` + 抽查检索（第四节） |
| 删除错误入库 | **knowledger** | 发现即删 | **先确认归档副本存在**（第五节） |

> 交付件入库是 author 的固定动作；**标准/规范的维护是 knowledger 的专属职责**，
> 两者都不要等别人提醒。

## 三、喂料流程（唯一入口）

工具：`energy-audit-core/scripts/ingest_kb_files.py`（随技能发布，部署环境直接可用）。

```bash
# 1) 把原文丢进投递区（目录按库分好，别丢错）
#    %LOCALAPPDATA%\hermes\rag\standards\_inbox\
#        guidelines\        → 技术规范/导则/办法
#        quota_standards\   → 定额/限额标准
#        reports\           → 一般不手工投（走 S16a）

# 2) 先看会入哪些（只读）
python <skills>/energy-audit-core/scripts/ingest_kb_files.py --dry-run

# 3) 正式入
python <skills>/energy-audit-core/scripts/ingest_kb_files.py
```

脚本做的七件事：查重（sha256）→ 复制进库根 → 扫盘建记录 → 向量化 → 实体/关系 →
wiki 页 → 归档原件 + 记台账。**幂等**，同一份重复投会被 sha256 挡掉。

## 四、验收标准（四条硬指标，缺一不算喂好）

| # | 指标 | 判据 | 不合格说明什么 |
|---|---|---|---|
| 1 | **切片数** | 每份文档切片数 **> 文档数 × 3**（单份至少 >3 条） | 只有 1 条 = 解析器走错路或没有文本层 |
| 2 | **检索命中** | 抽 3 个该标准该能答的问题，能命中条文（`kbs="standards"`） | 命不中 = 切片是垃圾，不是检索的问题 |
| 3 | **归档副本** | 库内每份文件在 `rag/standards/` 有**同哈希**副本 | 没有 = 一旦误删就永久丢失 |
| 4 | **治理检查** | `verify_knowledge_assets.py` 退出码 **0**（P0=0） | 非 0 逐条修完再算完 |

巡检命令：

```bash
python <skills>/energy-audit-core/scripts/verify_knowledge_assets.py
```

其中第 6 项「标准库切片体检」就是指标 1 的自动化版本，第 7 项「归档完备性」是指标 3。

## 五、三条禁令（都是踩过的坑）

1. **删文档前先确认归档副本存在**。`batch_delete_knowledge_documents()` 会调用
   `delete_knowledge_document()`，后者**连磁盘原件一起 `unlink()`**——2026-09-20
   就这样丢过一份 `4452 用水定额`（后来从网上重下并核对封面才补回）。
2. **不要把技能包规则文件入库**（见第一节边界 1）。
3. **不要用 `robocopy /MIR` 发技能**（见 `deployment-ops.md` 第四节、`lessons-learned.md` C5）。

## 六、常见故障对照

| 现象 | 大概率原因 | 处理 |
|---|---|---|
| 库是空的，或只有 1 条切片 | 解析器按报告逻辑切标准（2026-09-20 已修）；或 PDF 是扫描件无文本层 | 重跑 `--reindex-only`；扫描件先 OCR |
| 检索命中不了条文 | 切片是 summary 垃圾 | 看切片（`dump` 一下内容），重入 |
| 实体/关系为 0 | 抽取调 LLM 读超时（偶发） | 补跑 `start_graph_build(doc_id)`；不影响条文检索 |
| 投了但没进库 | 文件名 / 目录投错，或 sha256 已存在 | `--dry-run` 看识别结果 |

## 七、待办清单（谁维护本文谁更新这一节）

- `energy_audit_technical_guidelines` 库首批 17 份规范原文待投递
  （清单见技能包 `_changes/guidelines库喂料清单-20260920.md`）
- `energy_quota_standards` 中 4 份文档实体为 0（LLM 超时），待补跑
- `公共建筑（大型超市）能耗定额.pdf` 为扫描件、0 切片，待 OCR 后重入
